"""
Import scholarships from a CSV file.

    python manage.py updatemodel Dataset/sample_scholarships.csv
    python manage.py updatemodel studyportal1.csv --clear

Column names are matched case-insensitively, and the old scraper column names
(Title, Links, apply_date, ...) still work. Re-running is safe: rows are matched
on (title, link) and updated rather than duplicated.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app1 import recommender
from app1.models import Country, FieldOfInterest, Scholarship, TypeOfDegree

# model field -> accepted CSV headers (lower-case)
COLUMN_ALIASES = {
    "title": ["title"],
    "link": ["link", "links", "url"],
    "image_link": ["image_link", "image", "image_url"],
    "university_name": ["university_name", "university name", "university"],
    "tution_structure": ["tution_structure", "tuition_structure", "tuition"],
    "degree": ["degree"],
    "subject": ["subject", "field", "field_of_study"],
    "eligibility": ["eligibility"],
    "country": ["country"],
    "apply_date": ["apply_date", "deadline", "applydate"],
    "scholarship_details": ["scholarship_details", "details", "description"],
}


def _field_limits():
    return {f.name: getattr(f, "max_length", None) for f in Scholarship._meta.get_fields() if hasattr(f, "max_length")}


class Command(BaseCommand):
    help = "Import or update scholarships from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", nargs="?", default="Dataset/sample_scholarships.csv")
        parser.add_argument("--clear", action="store_true", help="Delete existing scholarships first.")

    def handle(self, csv_path, clear, **options):
        path = Path(csv_path)
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            headers = {h.strip().lower(): h for h in (reader.fieldnames or [])}
            mapping = {}
            for field, aliases in COLUMN_ALIASES.items():
                for alias in aliases:
                    if alias in headers:
                        mapping[field] = headers[alias]
                        break
            if "title" not in mapping:
                raise CommandError("CSV needs a 'title' column.")
            rows = list(reader)

        limits = _field_limits()
        created = updated = skipped = 0

        with transaction.atomic():
            if clear:
                Scholarship.objects.all().delete()
            for row in rows:
                data = {}
                for field, column in mapping.items():
                    value = (row.get(column) or "").strip()
                    if value.lower() in {"nan", "none", "null"}:
                        value = ""
                    limit = limits.get(field)
                    data[field] = value[:limit] if limit else value
                if not data.get("title"):
                    skipped += 1
                    continue
                _, was_created = Scholarship.objects.update_or_create(
                    title=data.pop("title"), link=data.pop("link", ""), defaults=data,
                )
                created += was_created
                updated += not was_created
            self._sync_lookups()

        recommender.invalidate()
        self.stdout.write(self.style.SUCCESS(
            f"Imported {created} new, updated {updated}, skipped {skipped} rows without a title."
        ))

    def _sync_lookups(self):
        """Keep the search dropdowns (countries, subjects, degrees) in step with the data."""
        for name in Scholarship.objects.exclude(country="").values_list("country", flat=True).distinct():
            Country.objects.get_or_create(name=name)
        for model, field in ((FieldOfInterest, "subject"), (TypeOfDegree, "degree")):
            values = Scholarship.objects.exclude(**{field: ""}).values_list(field, flat=True).distinct()
            for name in values:
                model.objects.get_or_create(name=name, profile=None)
