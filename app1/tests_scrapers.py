from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from . import recommender
from .ingest import run_scraper
from .models import Country, FieldOfInterest, Scholarship, ScrapeRun
from .scrapers import BaseScraper, DisallowedByRobots, ScrapedScholarship, ScraperError
from .scrapers.erasmus_mundus import ErasmusMundusCatalogueScraper, ErasmusMundusRSSScraper

DATA = Path(__file__).parent / "tests_data"
RSS = (DATA / "erasmus_mundus_rss.xml").read_text(encoding="utf-8")
CATALOGUE = (DATA / "erasmus_mundus_catalogue_synthetic.html").read_text(encoding="utf-8")


class FakeScraper(BaseScraper):
    """In-memory source so ingest logic can be tested without the network."""

    name = "fake"
    label = "Fake source"
    attribution = "Fake source, for tests"

    def __init__(self, items=None, error=None, **kw):
        super().__init__(**kw)
        self.items, self.error = items or [], error

    def scrape(self):
        if self.error:
            raise self.error
        yield from self.items


def item(n, **kw):
    return ScrapedScholarship(title=f"Programme {n}", source_id=f"id-{n}", link=f"https://example.org/{n}",
                              country="Spain", subject="Biology", **kw)


class ErasmusRSSParserTests(TestCase):
    def setUp(self):
        self.items = list(ErasmusMundusRSSScraper.parse(RSS))

    def test_parses_all_titled_items(self):
        self.assertEqual(len(self.items), 3)  # the untitled item is skipped

    def test_field_mapping(self):
        q = self.items[0]
        self.assertEqual(q.title, "Quantum Technologies and Engineering Erasmus Mundus Master Plus")
        self.assertEqual(q.link, "https://www.quanteem.eu/")
        self.assertEqual(q.source_id, "https://www.eacea.ec.europa.eu/node/1584")
        self.assertEqual(q.subject, "Physics")        # code 'QUANTIC' dropped, '(PHY)' stripped
        self.assertEqual(q.degree, "Masters")
        self.assertIn("Aarhus Universitet", q.university_name)
        self.assertIn("24 months / 120 ECTS", q.scholarship_details)
        self.assertIn("101325739", q.scholarship_details)

    def test_subjects_joined(self):
        self.assertEqual(self.items[2].subject, "Computer Science; Physics")

    def test_invalid_xml(self):
        with self.assertRaises(ScraperError):
            list(ErasmusMundusRSSScraper.parse("<rss><channel><item>"))

    def test_scrape_uses_fetch(self):
        scraper = ErasmusMundusRSSScraper(delay=0)
        with mock.patch.object(scraper, "fetch", return_value=RSS) as fetch:
            self.assertEqual(len(list(scraper.scrape())), 3)
        fetch.assert_called_once()


class ErasmusCatalogueParserTests(TestCase):
    def test_synthetic_page(self):
        items = ErasmusMundusCatalogueScraper.parse(CATALOGUE)
        self.assertEqual([i.title for i in items], [
            "Master in Applied Sustainability Science",
            "European Master in Migration and Intercultural Relations",
            "Erasmus Mundus Joint Master in Economics of Globalisation and European Integration",
        ])
        self.assertEqual(items[0].country, "Italy, Serbia, Germany, France")
        self.assertEqual(items[2].country, "Europe")  # no locations listed
        self.assertEqual(items[0].source_id, "https://www.master-mass.eu")

    def test_pagination_stops_on_empty_page(self):
        scraper = ErasmusMundusCatalogueScraper(delay=0)
        pages = [CATALOGUE, CATALOGUE, "<html><main>No results</main></html>"]
        with mock.patch.object(scraper, "fetch", side_effect=pages) as fetch:
            items = list(scraper.scrape())
        self.assertEqual(len(items), 3)   # second page repeats -> deduplicated, then stops
        self.assertLessEqual(fetch.call_count, 3)

    def test_disabled_until_verified(self):
        self.assertFalse(ErasmusMundusCatalogueScraper.enabled)


class PolitenessTests(TestCase):
    def test_robots_disallow_is_respected(self):
        scraper = FakeScraper(delay=0)
        robots = mock.Mock(status_code=200, ok=True, text="User-agent: *\nDisallow: /private\n")
        with mock.patch.object(scraper.session, "get", return_value=robots) as get:
            self.assertTrue(scraper.allowed_by_robots("https://site.example/public"))
            self.assertFalse(scraper.allowed_by_robots("https://site.example/private/page"))
            with self.assertRaises(DisallowedByRobots):
                scraper.fetch("https://site.example/private/page")
        self.assertEqual(get.call_count, 1)  # robots.txt fetched once and cached

    def test_forbidden_robots_blocks_everything(self):
        scraper = FakeScraper(delay=0)
        with mock.patch.object(scraper.session, "get", return_value=mock.Mock(status_code=403, ok=False)):
            self.assertFalse(scraper.allowed_by_robots("https://site.example/anything"))

    def test_identifies_itself(self):
        self.assertIn("ScholarshipSpyBot", FakeScraper().session.headers["User-Agent"])


class IngestTests(TestCase):
    def test_create_then_update(self):
        run, _ = run_scraper(FakeScraper([item(1), item(2)], delay=0))
        self.assertEqual((run.status, run.created, run.updated), ("success", 2, 0))

        changed = item(1)
        changed.title = "Programme 1 (renamed)"
        run, _ = run_scraper(FakeScraper([changed, item(2)], delay=0))
        self.assertEqual((run.created, run.updated), (0, 2))
        s = Scholarship.objects.get(source="fake", source_id="id-1")
        self.assertEqual(s.title, "Programme 1 (renamed)")
        self.assertEqual(s.attribution, "Fake source, for tests")
        self.assertIsNotNone(s.last_seen_at)

    def test_removed_listings_are_hidden_not_deleted(self):
        run_scraper(FakeScraper([item(n) for n in range(1, 5)], delay=0))
        run, _ = run_scraper(FakeScraper([item(n) for n in range(1, 4)], delay=0))
        self.assertEqual(run.deactivated, 1)
        self.assertFalse(Scholarship.objects.filter(source_id="id-4").exists())       # hidden from site
        self.assertTrue(Scholarship.all_objects.filter(source_id="id-4").exists())    # still stored

        run_scraper(FakeScraper([item(n) for n in range(1, 5)], delay=0))            # comes back
        self.assertTrue(Scholarship.objects.filter(source_id="id-4").exists())

    def test_broken_scraper_does_not_wipe_data(self):
        run_scraper(FakeScraper([item(n) for n in range(10)], delay=0))
        run, _ = run_scraper(FakeScraper([item(0)], delay=0))  # parser "broke": 1 of 10 found
        self.assertEqual(run.deactivated, 0)
        self.assertEqual(Scholarship.objects.filter(source="fake").count(), 10)

    def test_failed_run_is_recorded(self):
        run, _ = run_scraper(FakeScraper(error=ScraperError("site down"), delay=0))
        self.assertEqual(run.status, ScrapeRun.STATUS_FAILED)
        self.assertIn("site down", ScrapeRun.objects.get().error)

    def test_dry_run_saves_nothing(self):
        run, items = run_scraper(FakeScraper([item(1)], delay=0), dry_run=True)
        self.assertEqual(len(items), 1)
        self.assertFalse(Scholarship.objects.exists())
        self.assertFalse(ScrapeRun.objects.exists())

    def test_lookups_split_multi_subjects(self):
        run_scraper(FakeScraper([ScrapedScholarship(
            title="X", source_id="x", subject="Computer Science; Physics", country="Europe")], delay=0))
        names = set(FieldOfInterest.objects.filter(profile=None).values_list("name", flat=True))
        self.assertTrue({"Computer Science", "Physics"} <= names)
        self.assertTrue(Country.objects.filter(name="Europe").exists())

    def test_long_values_are_truncated(self):
        run_scraper(FakeScraper([ScrapedScholarship(title="T" * 500, source_id="long", subject="S" * 500)], delay=0))
        s = Scholarship.objects.get(source_id="long")
        self.assertEqual(len(s.title), 300)


class EndToEndTests(TestCase):
    def setUp(self):
        recommender.invalidate()

    def test_scraped_listings_are_searchable_and_recommended(self):
        scraper = ErasmusMundusRSSScraper(delay=0)
        with mock.patch.object(scraper, "fetch", return_value=RSS):
            run_scraper(scraper)

        r = self.client.get(reverse("search_results"), {"field_of_interest": "Physics"})
        self.assertEqual(r.context["number_of_scholarships"], 2)

        quantum = Scholarship.objects.get(link="https://www.quanteem.eu/")
        r = self.client.get(reverse("scholarship_detail", args=[quantum.pk]))
        self.assertContains(r, "CC BY 4.0")
        self.assertContains(r, "Last checked")

        matches = recommender.recommend("I want to study marine biotechnology, ocean ecosystems and water science")
        top = Scholarship.objects.get(pk=matches[0].scholarship_id)
        self.assertIn("Marine Biotechnology", top.title)

    def test_hidden_listing_is_404(self):
        s = Scholarship.objects.create(title="Old", is_active=False)
        self.assertEqual(self.client.get(reverse("scholarship_detail", args=[s.pk])).status_code, 404)


class ScrapeCommandTests(TestCase):
    def test_list(self):
        from io import StringIO
        out = StringIO()
        call_command("scrape", "--list", stdout=out)
        self.assertIn("erasmus_mundus_rss", out.getvalue())
        self.assertIn("experimental", out.getvalue())

    def test_unknown_source(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("scrape", "nope")

    def test_runs_enabled_sources(self):
        from io import StringIO
        with mock.patch.object(ErasmusMundusRSSScraper, "fetch", return_value=RSS):
            call_command("scrape", stdout=StringIO())
        self.assertEqual(Scholarship.objects.filter(source="erasmus_mundus_rss").count(), 3)
        self.assertFalse(Scholarship.objects.filter(source="erasmus_mundus_catalogue").exists())
