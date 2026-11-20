"""
Scheduled jobs: the daily scrape and the deadline reminder emails.

Ways to run them (pick whichever suits where the site runs):

1. Automatically inside the website (default while developing):
   with SCHEDULER_AUTOSTART on, `runserver` / gunicorn start a background thread
   that checks every minute and runs any job that's due.
2. A separate worker process:       python manage.py run_scheduler
3. A cron job / platform scheduler:  python manage.py run_jobs   (e.g. every hour)

Whichever you use, each job runs at most once per day: a run is "claimed" by
inserting a JobRun row, and the database refuses a second row for the same day.
If the site was asleep at the scheduled time, the job runs as soon as it wakes.
"""

import io
import logging
import os
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import time as dtime

from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _time_from_env(name, default):
    value = os.environ.get(name, default)
    hour, minute = (int(x) for x in value.split(":"))
    return dtime(hour, minute)


@dataclass(frozen=True)
class Job:
    name: str
    at: dtime          # earliest time of day (UTC) it may run
    command: str
    args: tuple = ()
    description: str = ""


JOBS = [
    Job("daily_scrape", _time_from_env("SCRAPE_AT", "03:00"), "scrape", ("--delay", "2"),
        "Collect fresh scholarships from every enabled source."),
    Job("deadline_reminders", _time_from_env("REMINDERS_AT", "08:00"), "send_deadline_reminders", (),
        "Email users whose saved scholarships close soon."),
]


def due_jobs(now=None):
    """Jobs whose time has come today and that haven't been claimed today."""
    from .models import JobRun

    now = now or timezone.now()
    today = now.date()
    done = set(JobRun.objects.filter(run_date=today).values_list("job", flat=True))
    return [j for j in JOBS if now.time() >= j.at and j.name not in done]


def claim(job, run_date):
    """Insert today's JobRun row. Returns it, or None if another process got there first."""
    from .models import JobRun

    try:
        with transaction.atomic():
            return JobRun.objects.create(job=job.name, run_date=run_date)
    except IntegrityError:
        return None


def run_job(job, now=None):
    """Run one job if nobody else has today. Returns the JobRun, or None if skipped."""
    from .models import JobRun

    now = now or timezone.now()
    run = claim(job, now.date())
    if run is None:
        return None
    out = io.StringIO()
    try:
        call_command(job.command, *job.args, stdout=out, stderr=out)
        run.status = JobRun.SUCCESS
    except BaseException:  # noqa: BLE001 - record any failure, keep the scheduler alive
        out.write(traceback.format_exc())
        run.status = JobRun.FAILED
        logger.exception("Scheduled job %s failed", job.name)
    run.output = out.getvalue()[-20000:]
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "output", "finished_at"])
    return run


def run_due_jobs(now=None):
    return [r for r in (run_job(j, now) for j in due_jobs(now)) if r]


# ---------------------------------------------------------------- background thread

_started = False
_start_lock = threading.Lock()


def _loop(interval):
    time.sleep(10)  # let the web server finish starting
    while True:
        try:
            close_old_connections()
            for run in run_due_jobs():
                logger.info("Scheduled job %s finished: %s", run.job, run.status)
        except Exception:
            logger.exception("Scheduler tick failed")
        finally:
            close_old_connections()
        time.sleep(interval)


def start_background_scheduler(interval=60):
    """Start the scheduler thread once per process."""
    global _started
    with _start_lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_loop, args=(interval,), name="scholarship-spy-scheduler", daemon=True).start()
    logger.info("Background scheduler started (checks every %ss)", interval)
    return True
