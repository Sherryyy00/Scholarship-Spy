"""
Run any scheduled jobs that are due now (each runs at most once a day).
Designed for cron / platform schedulers, e.g. every hour:

    python manage.py run_jobs
    python manage.py run_jobs --list
    python manage.py run_jobs --force deadline_reminders   # run one now (still once per day)
"""

from django.core.management.base import BaseCommand, CommandError

from app1.jobs import JOBS, run_due_jobs, run_job


class Command(BaseCommand):
    help = "Run scheduled jobs that are due."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true")
        parser.add_argument("--force", metavar="JOB", help="Run this job now, ignoring its time of day")

    def handle(self, *args, **opts):
        if opts["list"]:
            for job in JOBS:
                self.stdout.write(f"{job.name:20} daily after {job.at:%H:%M} UTC  {job.description}")
            return
        if opts["force"]:
            job = next((j for j in JOBS if j.name == opts["force"]), None)
            if job is None:
                raise CommandError(f"Unknown job {opts['force']}. Use --list.")
            runs = [r for r in [run_job(job)] if r]
        else:
            runs = run_due_jobs()
        if not runs:
            self.stdout.write("Nothing due.")
        for run in runs:
            self.stdout.write(f"{run.job}: {run.status}")
