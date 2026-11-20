"""Tests for the logged-in area: security fixes, CV recommendations, interests, history, feedback."""

import io
from pathlib import Path

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from . import recommender
from .models import Feedback, FieldOfInterest, History, Program, Recommendation, Scholarship
from .uploads import clean_cv_text, completed_level, suggested_degree

DATA = Path(__file__).parent / "tests_data"
PASSWORD = "Str0ng-Passphrase!"
STATEMENT = (
    "I am a computer science graduate who wants to study a masters in data science. I have worked with "
    "Python, SQL and Power BI dashboards and I want to go deeper into machine learning, statistics and big "
    "data analytics so I can build artificial intelligence models that help organisations decide better."
)


def upload(name, content=None):
    data = content if content is not None else (DATA / name).read_bytes()
    return SimpleUploadedFile(name, data)


def image_bytes(fmt="PNG", size=(800, 600)):
    buf = io.BytesIO()
    Image.new("RGB", size, (49, 82, 107)).save(buf, format=fmt)
    return buf.getvalue()


class AccountTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("updatemodel", "Dataset/sample_scholarships.csv", verbosity=0)

    def setUp(self):
        cache.clear()
        recommender.invalidate()
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD, first_name="Alice")
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)


# ---------------------------------------------------------------- login

class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user("sherry", "Sherry@Example.com", PASSWORD)

    def post(self, ident, pw=PASSWORD):
        return self.client.post(reverse("login"), {"username": ident, "password": pw})

    def test_login_with_username(self):
        self.assertRedirects(self.post("sherry"), reverse("home"), fetch_redirect_response=False)

    def test_login_with_email_any_case(self):
        self.assertRedirects(self.post("sherry@example.com"), reverse("home"), fetch_redirect_response=False)

    def test_wrong_password(self):
        r = self.post("sherry@example.com", "nope")
        self.assertContains(r, "Invalid username/email or password")

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.post("sherry", "wrong")
        r = self.post("sherry")  # correct password, but locked
        self.assertEqual(r.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_success_clears_failures(self):
        for _ in range(3):
            self.post("sherry", "wrong")
        self.post("sherry")
        self.client.logout()
        for _ in range(3):
            self.post("sherry", "wrong")
        self.assertRedirects(self.post("sherry"), reverse("home"), fetch_redirect_response=False)

    def test_form_does_not_ask_browser_to_autofill(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, 'autocomplete="off"')
        self.assertContains(r, "Username or email")

    def test_logout_requires_post(self):
        self.client.login(username="sherry", password=PASSWORD)
        self.client.get(reverse("logout"))
        self.assertIn("_auth_user_id", self.client.session)  # GET does nothing
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


# ---------------------------------------------------------------- profile photo

@override_settings(MEDIA_ROOT="/tmp/scholarship-spy-test-media")
class PhotoUploadTests(AccountTestCase):
    def test_valid_image_is_reencoded_with_random_name(self):
        f = SimpleUploadedFile("../../evil name.png", image_bytes("PNG"), content_type="image/png")
        self.client.post(reverse("userprofileedit"), {"photo": f})
        photo = User.objects.get(pk=self.alice.pk).profile.photo
        self.assertTrue(photo.name.startswith("profile_pics/"))
        self.assertTrue(photo.name.endswith(".jpg"))
        self.assertNotIn("evil", photo.name)
        with Image.open(photo.path) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertLessEqual(max(img.size), 400)

    def test_html_disguised_as_image_is_rejected(self):
        f = SimpleUploadedFile("x.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg")
        r = self.client.post(reverse("userprofileedit"), {"photo": f}, follow=True)
        self.assertContains(r, "isn&#x27;t a valid image")
        self.assertEqual(User.objects.get(pk=self.alice.pk).profile.photo.name, "default.jpg")

    def test_svg_rejected(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'
        self.client.post(reverse("userprofileedit"), {"photo": SimpleUploadedFile("a.svg", svg)})
        self.assertEqual(User.objects.get(pk=self.alice.pk).profile.photo.name, "default.jpg")

    def test_oversized_file_rejected(self):
        big = SimpleUploadedFile("big.png", b"0" * (3 * 1024 * 1024 + 1))
        r = self.client.post(reverse("userprofileedit"), {"photo": big}, follow=True)
        self.assertContains(r, "smaller than 3 MB")


# ---------------------------------------------------------------- CV handling

class CVTextTests(TestCase):
    def test_contact_details_removed_dates_kept(self):
        text = clean_cv_text("Jo Bloggs jo@mail.com +44 7700 900123 https://linkedin.com/in/jo 2019 - 2022 BSc Physics")
        self.assertNotIn("jo@mail.com", text)
        self.assertNotIn("7700", text)
        self.assertNotIn("linkedin", text)
        self.assertIn("2019 - 2022", text)
        self.assertIn("BSc Physics", text)

    def test_next_degree_level(self):
        self.assertEqual(suggested_degree("BSc Computer Science 2023. I want to do a masters."), "Masters")
        self.assertEqual(suggested_degree("I have an MSc in Data Science and want a PhD."), "PhD")
        self.assertEqual(suggested_degree("Finishing A-levels and want to study engineering"), "Bachelors")
        self.assertIsNone(completed_level("My dream is a PhD in physics"))


class CVRecommendationTests(AccountTestCase):
    def post(self, **data):
        files = {k: v for k, v in data.items() if hasattr(v, "read")}
        fields = {k: v for k, v in data.items() if k not in files}
        return self.client.post(reverse("my_recommendations"), {**fields, **files})

    def test_pdf_cv_only(self):
        r = self.post(cv=upload("sample_cv.pdf"))
        history = History.objects.get(profile=self.alice.profile)
        self.assertRedirects(r, reverse("recommendation_results", args=[history.pk]))
        self.assertEqual(history.input_type, History.INPUT_CV)
        self.assertNotIn("example.com", history.cv_text)  # contact details stripped before saving
        top = history.top_scholarships.first()
        self.assertIn("Renewable Energy", top.title)

    def test_docx_cv_only(self):
        self.post(cv=upload("sample_cv.docx"))
        top = History.objects.get().top_scholarships.first()
        self.assertIn("Renewable Energy", top.title)

    def test_statement_and_cv_together(self):
        self.post(statement="Short note: I love wind power.", cv=upload("sample_cv.pdf"))
        h = History.objects.get()
        self.assertEqual(h.input_type, History.INPUT_BOTH)

    def test_results_explain_matches_and_show_percent(self):
        self.post(cv=upload("sample_cv.pdf"))
        h = History.objects.get()
        first = Recommendation.objects.filter(history=h).order_by("rank").first()
        self.assertTrue(first.matched_terms_list)
        r = self.client.get(reverse("recommendation_results", args=[h.pk]))
        self.assertContains(r, "Why it matched")
        self.assertContains(r, "100%")

    def test_degree_and_country_filters(self):
        self.post(statement=STATEMENT, degree="Bachelors", country="")
        h = History.objects.get()
        self.assertTrue(h.top_scholarships.exists())
        self.assertTrue(all("bachelor" in s.degree.lower() for s in h.top_scholarships))

    def test_rejects_non_cv_files(self):
        for name, content in (("cv.exe", b"MZ\x90\x00binary"), ("cv.pdf", b"not really a pdf"),
                              ("cv.docx", b"PK\x03\x04garbage")):
            with self.subTest(name):
                r = self.post(cv=upload(name, content))
                self.assertEqual(r.status_code, 400)
        self.assertFalse(History.objects.exists())

    def test_rejects_large_cv(self):
        r = self.post(cv=upload("cv.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024)))
        self.assertContains(r, "larger than 5 MB", status_code=400)

    def test_short_statement_without_cv_rejected(self):
        r = self.post(statement="too short")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(History.objects.exists())

    def test_nothing_submitted(self):
        r = self.post(statement="")
        self.assertContains(r, "Write a personal statement or upload your CV", status_code=400)

    def test_cv_file_is_not_stored(self):
        self.post(cv=upload("sample_cv.pdf"))
        h = History.objects.get()
        self.assertEqual(h.cv_filename, "sample_cv.pdf")
        self.assertFalse(any(f.name for f in h._meta.fields if f.get_internal_type() == "FileField"))


class StatementPrivacyTests(AccountTestCase):
    def test_statement_sent_by_post_not_in_url(self):
        r = self.client.post(reverse("my_recommendations"), {"statement": STATEMENT})
        self.assertNotIn("statement", r.url)
        self.assertNotIn("data", r.url)

    def test_get_with_statement_does_nothing(self):
        self.client.get(reverse("my_recommendations"), {"statement": STATEMENT})
        self.assertFalse(History.objects.exists())

    def test_cannot_view_other_users_results(self):
        h = History.objects.create(profile=self.bob.profile, personal_statement=STATEMENT)
        self.assertEqual(self.client.get(reverse("recommendation_results", args=[h.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("rerun_recommendations", args=[h.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("delete_history", args=[h.pk])).status_code, 404)
        self.assertTrue(History.objects.filter(pk=h.pk).exists())


# ---------------------------------------------------------------- interests

class InterestTests(AccountTestCase):
    def add(self, name):
        return self.client.post(reverse("add_field_of_interest"), {"fieldOfInterest": name})

    def test_suggestions_for_beginners(self):
        r = self.client.get(reverse("add_field_of_interest"))
        suggestions = r.context["starter_interests"] + r.context["popular_interests"]
        self.assertIn("Data Science", suggestions)
        self.assertTrue(r.context["popular_interests"])
        self.assertFalse(any("subject" in p.lower() for p in r.context["popular_interests"]))
        self.assertFalse(set(r.context["starter_interests"]) & set(r.context["popular_interests"]))

    def test_added_interest_disappears_from_suggestions(self):
        self.add("Data Science")
        r = self.client.get(reverse("add_field_of_interest"))
        self.assertNotIn("Data Science", r.context["starter_interests"] + r.context["popular_interests"])

    def test_case_insensitive_duplicates_and_limit(self):
        self.add("Data Science")
        self.add("data science")
        self.assertEqual(self.alice.profile.fieldofinterest_set.count(), 1)
        for n in range(20):
            self.add(f"Topic {n}")
        self.assertEqual(self.alice.profile.fieldofinterest_set.count(), 15)

    def test_remove_own_only(self):
        mine = FieldOfInterest.objects.create(name="Law", profile=self.alice.profile)
        theirs = FieldOfInterest.objects.create(name="Art", profile=self.bob.profile)
        self.assertEqual(self.client.post(reverse("remove_field_of_interest", args=[theirs.pk])).status_code, 404)
        self.client.post(reverse("remove_field_of_interest", args=[mine.pk]))
        self.assertFalse(FieldOfInterest.objects.filter(pk=mine.pk).exists())
        self.assertTrue(FieldOfInterest.objects.filter(pk=theirs.pk).exists())

    def test_remove_needs_post(self):
        mine = FieldOfInterest.objects.create(name="Law", profile=self.alice.profile)
        self.assertEqual(self.client.get(reverse("remove_field_of_interest", args=[mine.pk])).status_code, 405)

    def test_user_interests_never_leak_into_public_dropdowns(self):
        self.add("My Secret Hobby")
        r = self.client.get(reverse("home"))
        self.assertNotContains(r, "My Secret Hobby")

    def test_programme_remove_own_only(self):
        theirs = Program.objects.create(name="X", profile=self.bob.profile)
        self.assertEqual(self.client.post(reverse("remove_current_program", args=[theirs.pk])).status_code, 404)


# ---------------------------------------------------------------- history

class HistoryTests(AccountTestCase):
    def test_delete_one_and_clear(self):
        h1 = History.objects.create(profile=self.alice.profile, personal_statement="a")
        History.objects.create(profile=self.alice.profile, personal_statement="b")
        other = History.objects.create(profile=self.bob.profile, personal_statement="c")
        self.client.post(reverse("delete_history", args=[h1.pk]))
        self.assertEqual(self.alice.profile.history_set.count(), 1)
        self.client.post(reverse("clear_history"))
        self.assertEqual(self.alice.profile.history_set.count(), 0)
        self.assertTrue(History.objects.filter(pk=other.pk).exists())

    def test_history_page_lists_only_own(self):
        History.objects.create(profile=self.bob.profile, personal_statement="Bob's private statement")
        r = self.client.get(reverse("my_history"))
        self.assertNotContains(r, "Bob&#x27;s private statement")


# ---------------------------------------------------------------- feedback

class FeedbackTests(AccountTestCase):
    def test_new_feedback_needs_approval(self):
        self.client.post(reverse("feedback"), {"feedback": "Lovely site", "emoji": "4"})
        fb = Feedback.objects.get()
        self.assertFalse(fb.is_approved)
        self.assertNotContains(self.client.get(reverse("home")), "Lovely site")
        fb.is_approved = True
        fb.save()
        self.assertContains(self.client.get(reverse("home")), "Lovely site")

    def test_script_is_escaped(self):
        Feedback.objects.create(content="<script>alert(1)</script>", profile=self.alice.profile, is_approved=True)
        r = self.client.get(reverse("home"))
        self.assertNotContains(r, "<script>alert(1)</script>")

    def test_rate_limited_and_validated(self):
        for i in range(5):
            self.client.post(reverse("feedback"), {"feedback": f"Message number {i}", "emoji": "9"})
        self.assertEqual(Feedback.objects.count(), 3)
        self.assertTrue(all(f.emoji == "" for f in Feedback.objects.all()))  # invalid emoji value dropped


# ---------------------------------------------------------------- account deletion

class DeleteAccountTests(AccountTestCase):
    def test_wrong_password_keeps_account(self):
        self.client.post(reverse("delete_account"), {"password": "nope"})
        self.assertTrue(User.objects.filter(pk=self.alice.pk).exists())

    def test_deletes_everything(self):
        History.objects.create(profile=self.alice.profile, personal_statement="x")
        FieldOfInterest.objects.create(name="Law", profile=self.alice.profile)
        Feedback.objects.create(content="hi there", profile=self.alice.profile)
        self.client.post(reverse("delete_account"), {"password": PASSWORD})
        self.assertFalse(User.objects.filter(username="alice").exists())
        self.assertFalse(History.objects.filter(personal_statement="x").exists())
        self.assertFalse(Feedback.objects.filter(content="hi there").exists())
        self.assertNotIn("_auth_user_id", self.client.session)


# ---------------------------------------------------------------- every account page renders

class AccountPagesRenderTests(AccountTestCase):
    def test_all_pages_render_for_logged_in_user(self):
        h = History.objects.create(profile=self.alice.profile, personal_statement=STATEMENT)
        names = ["userprofile", "userprofileedit", "add_field_of_interest", "current_program",
                 "my_recommendations", "my_history", "feedback", "password_reset_settings", "delete_account"]
        for name in names:
            with self.subTest(name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse("recommendation_results", args=[h.pk])).status_code, 200)

    def test_no_password_maxlength_limit(self):
        r = self.client.get(reverse("password_reset_settings"))
        self.assertNotContains(r, 'maxlength="30"')
