from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from . import recommender
from .models import Feedback, History, Profile, Recommendation, Scholarship

STATEMENT_DS = (
    "I am a computer science graduate who wants to study a masters in data science. "
    "I have worked with Python, SQL and Power BI dashboards, and I want to go deeper into "
    "machine learning, statistics and big data analytics. My goal is to work as a data "
    "scientist building artificial intelligence models that help businesses make decisions."
)
STATEMENT_ENERGY = (
    "My passion is renewable energy and climate. I want to do a masters in energy engineering "
    "focused on offshore wind power, solar energy and forecasting electricity demand so that "
    "power grids can run on sustainable sources. I studied electrical engineering and did a "
    "final year project on wind turbine output prediction using historical weather data."
)


class SampleDataMixin:
    @classmethod
    def setUpTestData(cls):
        call_command("updatemodel", "Dataset/sample_scholarships.csv", verbosity=0)

    def setUp(self):
        recommender.invalidate()


class RecommenderTests(SampleDataMixin, TestCase):
    def top_titles(self, statement, n=3):
        matches = recommender.recommend(statement, top_n=n)
        by_id = Scholarship.objects.in_bulk([m.scholarship_id for m in matches])
        return [by_id[m.scholarship_id].title for m in matches]

    def test_data_science_statement_ranks_data_science_first(self):
        self.assertIn("Data Science", self.top_titles(STATEMENT_DS)[0])

    def test_energy_statement_ranks_renewable_energy_first(self):
        self.assertIn("Renewable Energy", self.top_titles(STATEMENT_ENERGY)[0])

    def test_different_statements_give_different_results(self):
        self.assertNotEqual(self.top_titles(STATEMENT_DS), self.top_titles(STATEMENT_ENERGY))

    def test_scores_are_sorted_descending(self):
        scores = [m.score for m in recommender.recommend(STATEMENT_DS)]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_unrelated_text_returns_nothing(self):
        self.assertEqual(recommender.recommend("zzzz qqqq xxyyzz"), [])

    def test_candidate_filter(self):
        energy = Scholarship.objects.get(title__contains="Renewable")
        matches = recommender.recommend(STATEMENT_DS, candidate_ids={energy.id})
        self.assertTrue(all(m.scholarship_id == energy.id for m in matches))

    def test_index_refreshes_when_scholarship_added(self):
        recommender.recommend(STATEMENT_DS)  # build cache
        new = Scholarship.objects.create(
            title="Marine Biology Ocean Research Grant",
            subject="Marine Biology",
            scholarship_details="coral reefs ocean ecosystems marine biology fieldwork",
        )
        matches = recommender.recommend("I love marine biology, coral reefs and the ocean")
        self.assertEqual(matches[0].scholarship_id, new.id)

    def test_empty_database(self):
        Scholarship.objects.all().delete()
        self.assertEqual(recommender.recommend(STATEMENT_DS), [])


class ImportCommandTests(TestCase):
    def test_import_is_idempotent(self):
        call_command("updatemodel", "Dataset/sample_scholarships.csv", verbosity=0)
        count = Scholarship.objects.count()
        call_command("updatemodel", "Dataset/sample_scholarships.csv", verbosity=0)
        self.assertEqual(Scholarship.objects.count(), count)
        self.assertGreater(count, 0)


class SearchTests(SampleDataMixin, TestCase):
    def test_filters_combine(self):
        r = self.client.get(reverse("search_results"), {"country": "Canada", "degree": "Bachelors"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["number_of_scholarships"], 1)

    def test_literal_none_and_blank_values_are_ignored(self):
        r = self.client.get(reverse("search_results"), {"country": "Canada", "degree": " ", "scholarship_title": "None"})
        self.assertEqual(r.context["number_of_scholarships"], 2)

    def test_no_filters_redirects_home(self):
        self.assertRedirects(self.client.get(reverse("search_results")), reverse("home"))

    def test_bad_page_number_does_not_crash(self):
        r = self.client.get(reverse("search_results"), {"country": "Canada", "page": "abc"})
        self.assertEqual(r.status_code, 200)

    def test_degree_list_pages(self):
        for name in ("scholarshipone", "scholarshiptwo", "scholarshipthree"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_legacy_search_redirects(self):
        r = self.client.get(reverse("search"), {"degree": "Masters", "query": "Canada"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("degree=Masters", r.url)


class PublicPagesTests(SampleDataMixin, TestCase):
    def test_public_pages_render(self):
        s = Scholarship.objects.first()
        urls = [
            reverse(n) for n in (
                "home", "subjects", "about", "trainers", "pricing", "scholarships",
                "contact", "login", "Registration",
            )
        ] + [
            reverse("scholarship_detail", args=[s.pk]),
            reverse("category_degree", args=["Masters"]),
            reverse("category_subjects", args=["Data"]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_missing_scholarship_is_404(self):
        self.assertEqual(self.client.get(reverse("scholarship_detail", args=[99999])).status_code, 404)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountTests(TestCase):
    def register(self, **overrides):
        data = {
            "username": "sherry", "first_name": "Sherry", "last_name": "Adil",
            "email": "sherry@example.com", "password1": "Str0ng-Passphrase!", "password2": "Str0ng-Passphrase!",
        }
        data.update(overrides)
        return self.client.post(reverse("Registration"), data)

    def test_registration_sends_working_verification_link(self):
        self.assertRedirects(self.register(), reverse("login"))
        profile = Profile.objects.get(user__username="sherry")
        self.assertEqual(len(mail.outbox), 1)
        link = reverse("verify", args=[profile.email_token])
        self.assertIn(link, mail.outbox[0].body)
        self.client.get(link)
        profile.refresh_from_db()
        self.assertTrue(profile.is_verified)

    def test_duplicate_email_rejected(self):
        self.register()
        r = self.register(username="other")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_weak_password_rejected(self):
        r = self.register(password1="123", password2="123")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_invalid_token(self):
        self.assertRedirects(self.client.get(reverse("verify", args=["nope"])), reverse("login"))

    def test_login_and_safe_next_redirect(self):
        User.objects.create_user("u", "u@example.com", "Str0ng-Passphrase!")
        r = self.client.post(reverse("login") + "?next=https://evil.example/", {"username": "u", "password": "Str0ng-Passphrase!"})
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)

    def test_password_change_keeps_session(self):
        User.objects.create_user("u", "u@example.com", "Str0ng-Passphrase!")
        self.client.login(username="u", password="Str0ng-Passphrase!")
        r = self.client.post(reverse("password_reset_settings"), {
            "old_password": "Str0ng-Passphrase!", "new_password": "An0ther-Passphrase!",
            "retype_new_password": "An0ther-Passphrase!",
        })
        self.assertRedirects(r, reverse("userprofile"))
        self.assertTrue(User.objects.get(username="u").check_password("An0ther-Passphrase!"))
        self.assertEqual(self.client.get(reverse("userprofile")).status_code, 200)


class ProfileTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", "Str0ng-Passphrase!")
        self.bob = User.objects.create_user("bob", "bob@example.com", "Str0ng-Passphrase!")
        self.client.login(username="alice", password="Str0ng-Passphrase!")

    def test_cannot_edit_another_users_profile(self):
        # The old view trusted a hidden email field, so this used to edit Bob.
        self.client.post(reverse("userprofileedit"), {"hidden_user_email": "bob@example.com", "first_name": "Hacked"})
        self.bob.refresh_from_db()
        self.alice.refresh_from_db()
        self.assertEqual(self.bob.first_name, "")
        self.assertEqual(self.alice.first_name, "Hacked")

    def test_cgpa_validation(self):
        self.client.post(reverse("userprofileedit"), {"cgpa": "4.5"})
        self.alice.profile.refresh_from_db()
        self.assertIsNone(self.alice.profile.cgpa)
        self.client.post(reverse("userprofileedit"), {"cgpa": "3.75"})
        self.alice.profile.refresh_from_db()
        self.assertEqual(str(self.alice.profile.cgpa), "3.75")

    def test_email_must_be_unique(self):
        self.client.post(reverse("userprofileedit"), {"email": "bob@example.com"})
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.email, "alice@example.com")

    def test_login_required_pages_redirect(self):
        self.client.logout()
        for name in ("userprofile", "my_recommendations", "my_history", "feedback"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302)
            self.assertIn(reverse("login"), r.url)

    def test_add_interest_and_feedback(self):
        self.client.post(reverse("add_field_of_interest"), {"fieldOfInterest": "Data Science"})
        self.client.post(reverse("add_field_of_interest"), {"fieldOfInterest": "Data Science"})
        self.assertEqual(self.alice.profile.fieldofinterest_set.count(), 1)
        self.client.post(reverse("feedback"), {"feedback": "Great site", "emoji": "1"})
        self.assertEqual(Feedback.objects.count(), 1)


class RecommendationViewTests(SampleDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        User.objects.create_user("alice", "alice@example.com", "Str0ng-Passphrase!")
        self.client.login(username="alice", password="Str0ng-Passphrase!")

    def test_short_statement_rejected(self):
        r = self.client.get(reverse("my_recommendations"), {"statement": "too short"})
        self.assertEqual(r.context["scholarships"], "")
        self.assertFalse(History.objects.exists())

    def test_recommendations_are_ranked_and_saved(self):
        r = self.client.get(reverse("my_recommendations"), {"statement": STATEMENT_DS})
        self.assertEqual(r.status_code, 200)
        first = r.context["scholarships"][0]
        self.assertIn("Data Science", first.title)
        history = History.objects.get()
        self.assertEqual(Recommendation.objects.filter(history=history, rank=1).get().scholarship, first)

        # Same statement again reuses the history row
        self.client.get(reverse("my_recommendations"), {"statement": STATEMENT_DS})
        self.assertEqual(History.objects.count(), 1)

        r = self.client.get(reverse("my_history"))
        self.assertContains(r, first.title)
