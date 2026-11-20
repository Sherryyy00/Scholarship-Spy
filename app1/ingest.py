"""
Save scraped listings into the database.

* New listings are created; known ones (same source + source_id) are updated.
* Every listing seen in a run gets last_seen_at = now and is_active = True.
* Listings from that source NOT seen in a successful run are deactivated
  (hidden from the site, never deleted), because they've been removed at source.

Safety net: if a run finds far fewer listings than are currently active
(e.g. the site changed layout and the parser broke), nothing is deactivated.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import recommender
from .models import Country, FieldOfInterest, Scholarship, ScrapeRun, TypeOfDegree

logger = logging.getLogger(__name__)

# Only deactivate missing listings if this run found at least this share of the active ones.
MIN_COVERAGE_TO_DEACTIVATE = 0.5


def _limits():
    return {f.name: f.max_length for f in Scholarship._meta.fields if getattr(f, "max_length", None)}


def run_scraper(scraper, dry_run=False, deactivate_missing=True):
    """Run one scraper end to end. Returns the ScrapeRun (unsaved when dry_run)."""
    run = ScrapeRun(source=scraper.name)
    if not dry_run:
        run.save()

    try:
        items = list(scraper.scrape())
    except Exception as exc:  # record any failure, don't crash the whole schedule
        logger.exception("Scraper %s failed", scraper.name)
        run.status, run.error, run.finished_at = ScrapeRun.STATUS_FAILED, str(exc)[:5000], timezone.now()
        if not dry_run:
            run.save()
        return run, []

    run.found = len(items)
    if dry_run:
        run.status = ScrapeRun.STATUS_SUCCESS
        return run, items

    save_items(scraper, items, run, deactivate_missing=deactivate_missing)
    return run, items


def save_items(scraper, items, run, deactivate_missing=True):
    limits = _limits()
    now = timezone.now()
    seen_ids = set()

    with transaction.atomic():
        for item in items:
            fields = item.as_model_fields()
            for name, value in fields.items():
                if limits.get(name):
                    fields[name] = value[: limits[name]]
            source_id = fields.pop("source_id")
            if not fields["title"] or not source_id or source_id in seen_ids:
                continue
            seen_ids.add(source_id)
            defaults = {**fields, "attribution": scraper.attribution, "last_seen_at": now, "is_active": True}
            try:
                with transaction.atomic():
                    _, created = Scholarship.all_objects.update_or_create(
                        source=scraper.name, source_id=source_id, defaults=defaults,
                    )
            except IntegrityError:
                # Same title+link already exists from another source (e.g. an old CSV import). Keep that row.
                logger.info("Skipping duplicate listing %r", fields["title"])
                continue
            if created:
                run.created += 1
            else:
                run.updated += 1

        if deactivate_missing:
            active = Scholarship.all_objects.filter(source=scraper.name, is_active=True)
            active_count = active.count()
            if seen_ids and len(seen_ids) >= MIN_COVERAGE_TO_DEACTIVATE * active_count:
                run.deactivated = active.exclude(source_id__in=seen_ids).update(is_active=False)
            elif active_count:
                logger.warning(
                    "%s found %d of %d active listings; not deactivating anything",
                    scraper.name, len(seen_ids), active_count,
                )

        sync_lookups()

    run.status, run.finished_at = ScrapeRun.STATUS_SUCCESS, timezone.now()
    run.save()
    recommender.invalidate()
    return run


def sync_lookups():
    """Keep the search dropdowns (countries, subjects, degrees) in step with the data."""
    live = Scholarship.objects.all()
    for name in live.exclude(country="").values_list("country", flat=True).distinct():
        Country.objects.get_or_create(name=name)
    for model, field in ((FieldOfInterest, "subject"), (TypeOfDegree, "degree")):
        for value in live.exclude(**{field: ""}).values_list(field, flat=True).distinct():
            # Multi-subject listings are stored as "A; B" - add each part.
            for name in (v.strip() for v in value.split(";")):
                if name:
                    model.objects.get_or_create(name=name, profile=None)
