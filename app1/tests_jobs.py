from datetime import datetime, timezone as dt_tz
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from app1 import jobs
from app1.models import JobRun, Scholarship


def at(hour, minute=0):
    return datetime(2026, 11, 20, hour, minute, tzinfo=dt_tz.utc)


class SchedulerTests(TestCase):
    def setUp(self):
        Scholarship.objects.create(title="Existing")

    def test_empty_site_scrapes_straight_away(self):
        Scholarship.all_objects.all().delete()
        self.assertEqual([j.name for j in jobs.due_jobs(at(1))], ["daily_scrape"])

    def test_nothing_due_before_scheduled_time(self):
        self.assertEqual(jobs.due_jobs(at(1)), [])

    def test_jobs_become_due_after_their_time(self):
        names = [j.name for j in jobs.due_jobs(at(9))]
        self.assertEqual(names, ["daily_scrape", "deadline_reminders"])

    @mock.patch("app1.jobs.call_command")
    def test_each_job_runs_once_per_day(self, cmd):
        jobs.run_due_jobs(at(9))
        jobs.run_due_jobs(at(10))
        self.assertEqual(cmd.call_count, 2)
        self.assertEqual(JobRun.objects.filter(status=JobRun.SUCCESS).count(), 2)

    @mock.patch("app1.jobs.call_command")
    def test_runs_again_next_day(self, cmd):
        jobs.run_due_jobs(at(9))
        jobs.run_due_jobs(datetime(2026, 11, 21, 9, tzinfo=dt_tz.utc))
        self.assertEqual(cmd.call_count, 4)

    def test_second_claim_same_day_loses(self):
        job = jobs.JOBS[0]
        self.assertIsNotNone(jobs.claim(job, at(9).date()))
        self.assertIsNone(jobs.claim(job, at(9).date()))

    @mock.patch("app1.jobs.call_command", side_effect=RuntimeError("site down"))
    def test_failure_is_recorded_not_raised(self, cmd):
        runs = jobs.run_due_jobs(at(9))
        self.assertTrue(all(r.status == JobRun.FAILED for r in runs))
        self.assertIn("site down", runs[0].output)

    @mock.patch("app1.jobs.call_command")
    def test_run_jobs_force_and_list(self, cmd):
        call_command("run_jobs", "--list", stdout=mock.MagicMock())
        call_command("run_jobs", "--force", "deadline_reminders", stdout=mock.MagicMock())
        cmd.assert_called_once()
        self.assertTrue(JobRun.objects.filter(job="deadline_reminders").exists())


class AutostartTests(TestCase):
    def test_not_started_for_management_commands(self):
        from app1.apps import _is_web_server
        with mock.patch("sys.argv", ["manage.py", "migrate"]):
            self.assertFalse(_is_web_server())
        with mock.patch("sys.argv", ["manage.py", "test"]):
            self.assertFalse(_is_web_server())

    def test_started_for_web_servers(self):
        from app1.apps import _is_web_server
        with mock.patch("sys.argv", ["/venv/bin/gunicorn", "project1.wsgi"]):
            self.assertTrue(_is_web_server())
        with mock.patch("sys.argv", ["manage.py", "runserver", "--noreload"]):
            self.assertTrue(_is_web_server())

    @override_settings(SCHEDULER_AUTOSTART=False)
    def test_setting_can_switch_it_off(self):
        from django.apps import apps
        with mock.patch("app1.apps._is_web_server", return_value=True), \
             mock.patch("app1.jobs.start_background_scheduler") as start:
            apps.get_app_config("app1").ready()
        start.assert_not_called()
