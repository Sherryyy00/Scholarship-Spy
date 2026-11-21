import re
from io import StringIO
from pathlib import Path
from urllib.parse import unquote

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Scholarship
from .scrapers import SCRAPERS
from .scrapers.curated import PROGRAMMES
from .templatetags.scholarship_tags import scholarship_image

TEMPLATES = Path(__file__).parent / "templates"


class ThumbnailTests(TestCase):
    def test_own_image_wins(self):
        s = Scholarship(title="A", image_link="https://img.example/a.jpg", country="Germany")
        self.assertEqual(scholarship_image(s), "https://img.example/a.jpg")

    def test_country_photo(self):
        s = Scholarship(title="A", country="United Kingdom")
        self.assertTrue(scholarship_image(s).endswith("countries/london.jpeg"))

    def test_generated_svg_is_valid_and_labelled(self):
        import xml.dom.minidom
        s = Scholarship(title="A", country="Europe", subject="Computer Science; Physics", degree="Masters")
        url = scholarship_image(s)
        self.assertTrue(url.startswith("data:image/svg+xml"))
        svg = unquote(url.split(",", 1)[1])
        xml.dom.minidom.parseString(svg)  # raises if malformed
        self.assertIn(">Computer<", svg)
        self.assertIn(">Science<", svg)
        self.assertNotIn("Physics", svg)  # only the first subject is shown

    def test_text_is_escaped(self):
        s = Scholarship(title="A", subject="<script>alert(1)</script>")
        self.assertNotIn("<script>", unquote(scholarship_image(s)))

    def test_no_skipped_placeholder_anywhere(self):
        for f in TEMPLATES.rglob("*.html"):
            self.assertNotIn("image_skipped", f.read_text(), f.name)


class LinkTests(TestCase):
    def test_internal_links_open_in_same_tab(self):
        """Only external sites may use target=_blank, and they must use rel=noopener."""
        tag = re.compile(r"<a\b[^>]*target=\"_blank\"[^>]*>", re.S)
        for f in TEMPLATES.rglob("*.html"):
            for a in tag.findall(f.read_text()):
                href = re.search(r'href="([^"]*)"', a).group(1)
                with self.subTest(file=f.name, href=href):
                    self.assertFalse(href.startswith("{% url"), "internal link opens a new tab")
                    self.assertIn("noopener", a)

    def test_footer_has_no_dead_links(self):
        html = (TEMPLATES / "footer.html").read_text()
        self.assertNotIn('href="#"', html)


class HomePageTests(TestCase):
    def setUp(self):
        call_command("updatemodel", "Dataset/sample_scholarships.csv", stdout=StringIO())

    def test_real_stats_and_destinations(self):
        r = self.client.get(reverse("home"))
        self.assertEqual(r.context["stats"]["scholarships"], Scholarship.objects.count())
        uk = next(d for d in r.context["destinations"] if d["name"] == "United Kingdom")
        self.assertEqual(uk["count"], 2)
        self.assertNotContains(r, "Lorem ipsum")
        self.assertNotContains(r, "purecounter")

    def test_mobile_menu_and_active_link(self):
        r = self.client.get(reverse("subjects"))
        self.assertContains(r, "mobile-nav-toggle")
        self.assertRegex(r.content.decode(), r'class="active" href="/subjects"')

    def test_listing_pages_render_thumbnails(self):
        User.objects.create_user("u", "u@example.com", "Str0ng-Passphrase!")
        self.client.login(username="u", password="Str0ng-Passphrase!")
        for url in (reverse("scholarships"), reverse("search_results") + "?country=Canada"):
            r = self.client.get(url)
            self.assertContains(r, 'class="sch-card"')


class CuratedSourceTests(TestCase):
    def test_registered_and_enabled(self):
        self.assertIn("curated_official", SCRAPERS)
        self.assertTrue(SCRAPERS["curated_official"].enabled)

    def test_entries_link_to_official_sites(self):
        official = ("chevening.org", "cscuk.fcdo.gov.uk", "daad.de")
        for p in PROGRAMMES:
            with self.subTest(p.title):
                self.assertTrue(any(d in p.link for d in official), p.link)
                self.assertTrue(p.source_id and p.country and p.degree)

    def test_scrape_loads_without_network(self):
        call_command("scrape", "curated_official", stdout=StringIO())
        live = Scholarship.objects.filter(source="curated_official")
        self.assertEqual(live.count(), len(PROGRAMMES))
        r = self.client.get(reverse("scholarship_detail", args=[live.get(title="Chevening Scholarships").pk]))
        self.assertContains(r, "Summary written by Scholarship Spy")


class AboutPageTests(TestCase):
    def test_no_placeholder_or_invented_testimonials(self):
        r = self.client.get(reverse("about"))
        self.assertEqual(r.status_code, 200)
        for text in ("Lorem", "Proin iaculis", "Saul Goodman", "purecounter"):
            self.assertNotContains(r, text)
        self.assertIn("stats", r.context)


class ListingLayoutTests(TestCase):
    def setUp(self):
        call_command("updatemodel", "Dataset/sample_scholarships.csv", stdout=StringIO())

    def test_old_dashboard_theme_not_loaded(self):
        """profile_style.css (old dashboard theme) overrode the design; no page may load it."""
        for f in TEMPLATES.rglob("*.html"):
            self.assertNotIn("profile_style.css", f.read_text(), f.name)

    def test_pagination_keeps_filters(self):
        r = self.client.get(reverse("search_results"), {"degree": "Masters"})
        self.assertEqual(r.context["qs"], "degree=Masters")

    def test_detail_shows_similar_scholarships(self):
        s = Scholarship.objects.get(title__contains="Data Science")
        r = self.client.get(reverse("scholarship_detail", args=[s.pk]))
        self.assertTrue(r.context["similar"])
        self.assertNotIn(s, r.context["similar"])

    def test_category_pages_have_heading(self):
        r = self.client.get(reverse("category_degree", args=["Masters"]))
        self.assertContains(r, "Masters scholarships")


class DestinationCardTests(TestCase):
    def test_cards_follow_the_data(self):
        from app1.models import Scholarship
        for i in range(3):
            Scholarship.objects.create(title=f"EM {i}", country="Europe")
        Scholarship.objects.create(title="UK one", country="United Kingdom")
        cards = self.client.get("/").context["destinations"]
        self.assertEqual([c["name"] for c in cards], ["Europe (Erasmus Mundus)", "United Kingdom"])
        self.assertEqual(cards[0]["count"], 3)
        self.assertTrue(all(c["count"] for c in cards))
