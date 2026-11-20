"""
Collect scholarships from the registered sources.

    python manage.py scrape --list                     # show sources
    python manage.py scrape                            # run every enabled source
    python manage.py scrape erasmus_mundus_rss         # run one source
    python manage.py scrape erasmus_mundus_catalogue --dry-run --save-html samples/
                                                       # test a parser without touching the DB

Schedule it once a day (cron, Windows Task Scheduler or the GitHub Actions
workflow in .github/workflows/scrape.yml) to keep listings fresh.
"""

from django.core.management.base import BaseCommand, CommandError

from app1.ingest import run_scraper
from app1.scrapers import SCRAPERS


class Command(BaseCommand):
    help = "Scrape scholarships from registered sources."

    def add_arguments(self, parser):
        parser.add_argument("sources", nargs="*", help="Source names (default: all enabled sources)")
        parser.add_argument("--list", action="store_true", help="List available sources and exit")
        parser.add_argument("--dry-run", action="store_true", help="Fetch and parse, but don't save")
        parser.add_argument("--save-html", metavar="DIR", help="Save every downloaded page to DIR")
        parser.add_argument("--delay", type=float, help="Seconds between requests (default 2)")
        parser.add_argument("--no-deactivate", action="store_true",
                            help="Don't hide listings that have disappeared from the source")

    def handle(self, *args, **opts):
        if opts["list"]:
            for name, cls in SCRAPERS.items():
                state = "enabled" if cls.enabled else "experimental (run by name)"
                self.stdout.write(f"{name:28} {cls.label}  [{state}]")
            return

        names = opts["sources"] or [n for n, c in SCRAPERS.items() if c.enabled]
        unknown = [n for n in names if n not in SCRAPERS]
        if unknown:
            raise CommandError(f"Unknown source(s): {', '.join(unknown)}. Use --list to see options.")

        failed = False
        for name in names:
            scraper = SCRAPERS[name](delay=opts["delay"], save_html_dir=opts["save_html"])
            self.stdout.write(f"→ {scraper.label}")
            run, items = run_scraper(scraper, dry_run=opts["dry_run"], deactivate_missing=not opts["no_deactivate"])

            if run.status == "failed":
                failed = True
                self.stderr.write(self.style.ERROR(f"  failed: {run.error}"))
                continue
            if opts["dry_run"]:
                self.stdout.write(f"  found {run.found} listings (dry run, nothing saved)")
                for item in items[:10]:
                    self.stdout.write(f"   • {item.title}  |  {item.country}  |  {item.subject or '-'}  |  {item.link}")
                if len(items) > 10:
                    self.stdout.write(f"   … and {len(items) - 10} more")
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"  found {run.found}: {run.created} new, {run.updated} updated, {run.deactivated} hidden as removed"
                ))

        if failed:
            raise CommandError("One or more sources failed. See ScrapeRun in the admin for details.")
