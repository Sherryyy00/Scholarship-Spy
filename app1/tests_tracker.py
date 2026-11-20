"""Deadlines, sorting, saved scholarships, the application tracker and reminder emails."""

import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .deadlines import next_occurrence, parse_deadline, roll_forward_estimated
from .models import SavedScholarship, Scholarship
from .reminders import send_reminders
from .templatetags.scholarship_tags import deadline_badge

PASSWORD = "Str0ng-Passphrase!"
T = date(2026, 11, 20)


class DeadlineParserTests(TestCase):
    def test_formats(self):
        cases = {
            "31 March": (date(2027, 3, 31), True),
            "March 31, 2027": (date(2027, 3, 31), False),
            "31/03/2027": (date(2027, 3, 31), False),          # UK day-first
            "2027-03-31": (date(2027, 3, 31), False),
            "Deadline: 15 Jan 27": (date(2027, 1, 15), False),
            "15th of January": (date(2027, 1, 15), True),
            "10 Sept 2027": (date(2027, 9, 10), False),
            "20 November": (date(2026, 11, 20), True),         # today counts
        }
        for text, expected in cases.items():
            with self.subTest(text):
                self.assertEqual(parse_deadline(text, T), expected)

    def test_vague_or_invalid_text_gives_no_date(self):
        for text in ("Usually October to January (check website)", "Deadlines vary by country",
                     "See the Chevening application timeline", "31 September", "", None):
            with self.subTest(text):
                self.assertEqual(parse_deadline(text, T), (None, False))

    def test_leap_day(self):
        self.assertEqual(next_occurrence(2, 29, T), date(2028, 2, 29))

    def test_saved_on_model_and_updated_when_text_changes(self):
        s = Scholarship.objects.create(title="A", apply_date="1 March 2027")
        self.assertEqual(s.deadline, date(2027, 3, 1))
        s.apply_date = "Varies by course"
        s.save()
        s.refresh_from_db()
        self.assertIsNone(s.deadline)

    def test_estimated_deadlines_roll_forward(self):
        s = Scholarship.objects.create(title="A", apply_date="31 March")
        Scholarship.all_objects.filter(pk=s.pk).update(deadline=date(2026, 3, 31))  # pretend it's last year's
        self.assertEqual(roll_forward_estimated(T), 1)
        s.refresh_from_db()
        self.assertEqual(s.deadline, date(2027, 3, 31))

    def test_explicit_past_deadline_is_not_rolled(self):
        s = Scholarship.objects.create(title="A", apply_date="1 March 2020")
        roll_forward_estimated(T)
        s.refresh_from_db()
        self.assertEqual(s.deadline, date(2020, 3, 1))
        self.assertTrue(s.is_closed)


class BadgeAndSortTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.soon = Scholarship.objects.create(title="Soon", apply_date=(today + timedelta(days=5)).isoformat())
        self.later = Scholarship.objects.create(title="Later", apply_date=(today + timedelta(days=100)).isoformat())
        self.closed = Scholarship.objects.create(title="Closed", apply_date="1 January 2020")
        self.undated = Scholarship.objects.create(title="Aardvark undated", apply_date="Varies")

    def test_badges(self):
        self.assertIn("Closes in 5 days", deadline_badge(self.soon))
        self.assertIn("dl-urgent", deadline_badge(self.soon))
        self.assertIn("Closed", deadline_badge(self.closed))
        self.assertEqual(deadline_badge(self.undated), "")

    def test_closing_soon_sort(self):
        r = self.client.get(reverse("scholarships"), {"sort": "deadline"})
        titles = [s.title for s in r.context["scholarships"]]
        self.assertEqual(titles[:2], ["Soon", "Later"])
        self.assertNotIn("Closed", titles)            # closed ones are left out
        self.assertEqual(titles[-1], "Aardvark undated")  # undated go last
        self.assertEqual(r.context["qs"], "sort=deadline")

    def test_sort_kept_with_search_filters(self):
        r = self.client.get(reverse("search_results"), {"scholarship_title": "o", "sort": "deadline"})
        self.assertIn("sort=deadline", r.context["qs"])
        self.assertIn("scholarship_title=o", r.context["qs"])

    def test_unknown_sort_ignored(self):
        r = self.client.get(reverse("scholarships"), {"sort": "drop table"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["sort"], "")


class SavingTests(TestCase):
    def setUp(self):
        self.s = Scholarship.objects.create(title="Fund", apply_date="31 March")
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)

    def toggle(self, **headers):
        return self.client.post(reverse("toggle_saved", args=[self.s.pk]), **headers)

    def test_toggle_json(self):
        r = self.toggle(HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(json.loads(r.content), {"saved": True, "count": 1})
        r = self.toggle(HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(json.loads(r.content)["saved"], False)
        self.assertFalse(SavedScholarship.objects.exists())

    def test_toggle_form_redirects_to_safe_next_only(self):
        r = self.client.post(reverse("toggle_saved", args=[self.s.pk]), {"next": "https://evil.example/"})
        self.assertRedirects(r, reverse("scholarship_detail", args=[self.s.pk]), fetch_redirect_response=False)
        r = self.client.post(reverse("toggle_saved", args=[self.s.pk]), {"next": "/scholarships.html"})
        self.assertEqual(r.url, "/scholarships.html")

    def test_requires_login_and_post(self):
        self.assertEqual(self.client.get(reverse("toggle_saved", args=[self.s.pk])).status_code, 405)
        self.client.logout()
        r = self.toggle()
        self.assertIn(reverse("login"), r.url)
        self.assertFalse(SavedScholarship.objects.exists())

    def test_cannot_save_hidden_listing(self):
        self.s.is_active = False
        self.s.save()
        self.assertEqual(self.toggle().status_code, 404)

    def test_bookmark_state_shown_on_listing(self):
        self.toggle()
        r = self.client.get(reverse("scholarships"))
        self.assertContains(r, 'aria-pressed="true"')


class TrackerTests(TestCase):
    def setUp(self):
        self.s = Scholarship.objects.create(title="Fund", apply_date="31 March")
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.mine = SavedScholarship.objects.create(profile=self.alice.profile, scholarship=self.s)
        self.theirs = SavedScholarship.objects.create(profile=self.bob.profile, scholarship=self.s)
        self.client.login(username="alice", password=PASSWORD)

    def test_board_groups_by_status(self):
        self.mine.status = SavedScholarship.APPLIED
        self.mine.save()
        r = self.client.get(reverse("my_applications"))
        cols = {c["key"]: c["items"] for c in r.context["columns"]}
        self.assertEqual(cols["applied"], [self.mine])
        self.assertEqual(r.context["total"], 1)  # Bob's isn't shown

    def test_update_status_and_notes(self):
        self.client.post(reverse("update_application", args=[self.mine.pk]), {"status": "interview", "notes": " Bring transcripts "})
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.status, self.mine.notes), ("interview", "Bring transcripts"))

    def test_invalid_status_rejected(self):
        r = self.client.post(reverse("update_application", args=[self.mine.pk]), {"status": "hacked"}, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.status_code, 400)

    def test_cannot_touch_other_users_items(self):
        for name in ("update_application", "remove_application"):
            r = self.client.post(reverse(name, args=[self.theirs.pk]), {"status": "applied"})
            self.assertEqual(r.status_code, 404)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.status, "interested")

    def test_remove(self):
        self.client.post(reverse("remove_application", args=[self.mine.pk]))
        self.assertFalse(SavedScholarship.objects.filter(pk=self.mine.pk).exists())

    def test_reminder_setting_on_profile_edit(self):
        self.client.post(reverse("userprofileedit"), {"first_name": "Al"})  # checkbox unticked
        self.alice.profile.refresh_from_db()
        self.assertFalse(self.alice.profile.email_reminders)
        self.client.post(reverse("userprofileedit"), {"email_reminders": "on"})
        self.alice.profile.refresh_from_db()
        self.assertTrue(self.alice.profile.email_reminders)

    def test_pages_render(self):
        for url in (reverse("my_applications"), reverse("userprofile"), reverse("scholarship_detail", args=[self.s.pk])):
            self.assertEqual(self.client.get(url).status_code, 200)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="https://spy.example")
class ReminderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sherry", "sherry@example.com", PASSWORD, first_name="Sherry")
        self.profile = self.user.profile
        self.profile.is_verified = True
        self.profile.save(update_fields=["is_verified"])

    def test_unverified_email_gets_nothing(self):
        self.profile.is_verified = False
        self.profile.save(update_fields=["is_verified"])
        self.save(3)
        self.assertEqual(send_reminders(today=T), (0, 0))
        self.assertEqual(len(mail.outbox), 0)

    def save(self, days, status=SavedScholarship.INTERESTED, title=None):
        deadline = T + timedelta(days=days)
        s = Scholarship.objects.create(title=title or f"Closes in {days}", apply_date=deadline.isoformat())
        return SavedScholarship.objects.create(profile=self.profile, scholarship=s, status=status)

    def test_one_digest_per_user(self):
        self.save(10)
        self.save(2)
        self.save(40)  # too far away
        sent, items = send_reminders(today=T)
        self.assertEqual((sent, items), (1, 2))
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "2 saved scholarships close soon")
        self.assertIn("Closes in 10", msg.body)
        self.assertNotIn("Closes in 40", msg.body)
        self.assertIn("https://spy.example/reminders/unsubscribe/", msg.body)
        self.assertIn("List-Unsubscribe", msg.extra_headers)
        self.assertTrue(msg.alternatives)  # HTML version

    def test_each_reminder_sent_once(self):
        item = self.save(10)
        send_reminders(today=T)
        send_reminders(today=T)
        self.assertEqual(len(mail.outbox), 1)
        # ...then the final reminder when it's 3 days away
        send_reminders(today=T + timedelta(days=7))
        self.assertEqual(len(mail.outbox), 2)
        item.refresh_from_db()
        self.assertEqual(item.reminded_3_for, item.scholarship.deadline)
        send_reminders(today=T + timedelta(days=8))
        self.assertEqual(len(mail.outbox), 2)

    def test_saved_late_gets_only_final_reminder(self):
        item = self.save(1)
        send_reminders(today=T)
        item.refresh_from_db()
        self.assertEqual(item.reminded_14_for, item.scholarship.deadline)
        self.assertEqual(item.reminded_3_for, item.scholarship.deadline)

    def test_closes_today_subject(self):
        self.save(0)
        send_reminders(today=T)
        self.assertEqual(mail.outbox[0].subject, "A saved scholarship closes today")

    def test_skips_applied_opted_out_and_no_email(self):
        self.save(5, status=SavedScholarship.APPLIED)
        send_reminders(today=T)
        self.assertEqual(len(mail.outbox), 0)
        self.save(5, title="Other")
        self.profile.email_reminders = False
        self.profile.save()
        send_reminders(today=T)
        self.assertEqual(len(mail.outbox), 0)
        self.profile.email_reminders = True
        self.profile.save()
        self.user.email = ""
        self.user.save()
        send_reminders(today=T)
        self.assertEqual(len(mail.outbox), 0)

    def test_dry_run_sends_nothing(self):
        self.save(5)
        self.assertEqual(send_reminders(today=T, dry_run=True), (1, 1))
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(SavedScholarship.objects.get().reminded_14_for)

    def test_unsubscribe_link(self):
        self.save(5)
        send_reminders(today=T)
        link = next(w for w in mail.outbox[0].body.split() if "/reminders/unsubscribe/" in w)
        r = self.client.get(link.replace("https://spy.example", ""))
        self.assertContains(r, "unsubscribed")
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.email_reminders)

    def test_tampered_unsubscribe_token(self):
        r = self.client.get(reverse("unsubscribe_reminders", args=["not-a-real-token"]))
        self.assertRedirects(r, reverse("home"))
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_reminders)
