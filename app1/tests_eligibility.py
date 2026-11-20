from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import geo
from .eligibility import ELIGIBLE, NOT_ELIGIBLE, UNKNOWN, check, minimum_gpa, nationality_rule
from .models import History, Recommendation, Scholarship

PASSWORD = "Str0ng-Passphrase!"


def profile(nationality="", qualification="", cgpa=None):
    return SimpleNamespace(nationality=nationality, highest_qualification=qualification, cgpa=cgpa)


def sch(eligibility, country="United Kingdom", degree="Masters", details=""):
    return Scholarship(eligibility=eligibility, country=country, degree=degree, scholarship_details=details)


class GeoTests(TestCase):
    def test_normalise(self):
        for text, expected in (("Pakistani", "Pakistan"), ("pk", "Pakistan"), ("British", "United Kingdom"),
                               ("Korea, Republic of", "South Korea"), ("nowhere", "")):
            self.assertEqual(geo.normalise_country(text), expected)

    def test_group_lists_use_known_country_names(self):
        names = set(geo.all_countries())
        for group in (geo.EU, geo.COMMONWEALTH, geo.HIGH_INCOME):
            self.assertFalse(group - names)
        self.assertEqual(len(geo.EU), 27)
        self.assertEqual(len(geo.COMMONWEALTH), 56)

    def test_groups(self):
        self.assertTrue(geo.in_group("Pakistan", "commonwealth_lmic"))
        self.assertFalse(geo.in_group("Canada", "commonwealth_lmic"))   # high income
        self.assertFalse(geo.in_group("Egypt", "commonwealth"))
        self.assertTrue(geo.in_group("Egypt", "developing"))


class RuleTests(TestCase):
    def test_rule_detection(self):
        cases = {
            "International students": "international",
            "All nationalities": "any",
            "Students worldwide": "any",
            "UK and EU students": "uk_eu",
            "Developing countries": "developing",
            "Citizens of eligible low and middle income Commonwealth countries": "commonwealth_lmic",
            "International graduates (country-specific rules apply)": "listed_countries",
            "Emerging leaders from Chevening-eligible countries": "listed_countries",
            "Strong academic record": None,
        }
        for text, rule in cases.items():
            self.assertEqual(nationality_rule(text), rule, text)

    def test_nationality(self):
        pk, uk, de = profile("Pakistan"), profile("United Kingdom"), profile("Germany")
        self.assertEqual(check(sch("International students"), pk).status, ELIGIBLE)
        self.assertEqual(check(sch("International students"), uk).status, NOT_ELIGIBLE)   # host nationals
        self.assertEqual(check(sch("UK and EU students"), de).status, ELIGIBLE)
        self.assertEqual(check(sch("UK and EU students"), pk).status, NOT_ELIGIBLE)
        self.assertEqual(check(sch("Developing countries"), uk).status, NOT_ELIGIBLE)
        self.assertEqual(check(sch("Chevening-eligible countries"), pk).status, UNKNOWN)  # never guess a list
        self.assertEqual(check(sch("Chevening-eligible countries"), uk).status, NOT_ELIGIBLE)

    def test_host_country_with_note(self):
        r = check(sch("International students", country="United Kingdom (distance learning)"), profile("United Kingdom"))
        self.assertEqual(r.status, NOT_ELIGIBLE)

    def test_degree_level(self):
        masters = sch("All nationalities", degree="Masters")
        self.assertEqual(check(masters, profile("Pakistan", "BSc Computer Science")).status, ELIGIBLE)
        r = check(masters, profile("Pakistan", "MSc Data Science"))
        self.assertEqual(r.status, NOT_ELIGIBLE)
        self.assertIn("already have a master's", r.reasons[0])
        self.assertEqual(check(sch("All nationalities", degree="PhD"), profile("Pakistan", "MSc")).status, ELIGIBLE)

    def test_gpa(self):
        s = sch("All nationalities", details="Applicants need a minimum CGPA of 3.5.")
        self.assertEqual(minimum_gpa(s), Decimal("3.5"))
        self.assertEqual(check(s, profile("Pakistan", "BSc", Decimal("3.40"))).status, NOT_ELIGIBLE)
        self.assertEqual(check(s, profile("Pakistan", "BSc", Decimal("3.60"))).status, ELIGIBLE)
        self.assertIsNone(minimum_gpa(sch("All nationalities", details="GPA 9.0 or above")))  # not a 4-point scale

    def test_missing_profile_is_unknown_not_blocked(self):
        r = check(sch("International students"), profile())
        self.assertEqual(r.status, UNKNOWN)
        self.assertIn("Add your nationality", r.reasons[0])


class EligibilityViewTests(TestCase):
    def setUp(self):
        self.open = Scholarship.objects.create(title="Open to all", eligibility="All nationalities", country="Canada", degree="Masters")
        self.ukeu = Scholarship.objects.create(title="UK and EU only", eligibility="UK and EU students", country="United Kingdom", degree="Masters")
        self.vague = Scholarship.objects.create(title="Vague", eligibility="Strong academic record", country="Japan", degree="Masters")
        self.user = User.objects.create_user("sherry", "s@example.com", PASSWORD)
        self.user.profile.nationality = "Pakistan"
        self.user.profile.highest_qualification = "BSc Computer Science"
        self.user.profile.save()
        self.client.login(username="sherry", password=PASSWORD)

    def test_eligible_only_filter(self):
        r = self.client.get(reverse("scholarships"), {"eligible": "1"})
        titles = {s.title for s in r.context["scholarships"]}
        self.assertEqual(titles, {"Open to all", "Vague"})   # unknown is kept, not hidden
        self.assertIn("eligible=1", r.context["qs"])

    def test_filter_ignored_when_logged_out(self):
        self.client.logout()
        r = self.client.get(reverse("scholarships"), {"eligible": "1"})
        self.assertEqual(r.context["scholarships"].paginator.count, 3)

    def test_badges_on_listing(self):
        r = self.client.get(reverse("scholarships"))
        self.assertContains(r, "You can apply")
        self.assertContains(r, "Not eligible")

    def test_detail_panel(self):
        r = self.client.get(reverse("scholarship_detail", args=[self.ukeu.pk]))
        self.assertContains(r, "You may not be eligible")
        self.assertContains(r, "Only for UK and EU nationals")

    def test_results_hide_ineligible_by_default(self):
        h = History.objects.create(profile=self.user.profile, personal_statement="x")
        for rank, s in enumerate((self.ukeu, self.open), start=1):
            Recommendation.objects.create(history=h, scholarship=s, rank=rank, score=1.0 / rank)
        r = self.client.get(reverse("recommendation_results", args=[h.pk]))
        self.assertEqual([x.scholarship.title for x in r.context["recommendations"]], ["Open to all"])
        self.assertEqual(r.context["hidden_count"], 1)
        r = self.client.get(reverse("recommendation_results", args=[h.pk]), {"all": "1"})
        self.assertEqual(len(r.context["recommendations"]), 2)

    def test_profile_nationality_must_be_a_country(self):
        self.client.post(reverse("userprofileedit"), {"nationality": "Atlantis"})
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.nationality, "Pakistan")
        self.client.post(reverse("userprofileedit"), {"nationality": "british"})
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.nationality, "United Kingdom")
