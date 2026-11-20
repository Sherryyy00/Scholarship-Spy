"""
Long-running scheduler process (for a separate "worker" on a host):

    python manage.py run_scheduler
"""

import time

from django.core.management.base import BaseCommand

from app1.jobs import start_background_scheduler


class Command(BaseCommand):
    help = "Run the job scheduler in the foreground (Ctrl+C to stop)."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Seconds between checks")

    def handle(self, *args, interval=60, **options):
        start_background_scheduler(interval)
        self.stdout.write(self.style.SUCCESS("Scheduler running. Press Ctrl+C to stop."))
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            self.stdout.write("Stopped.")
