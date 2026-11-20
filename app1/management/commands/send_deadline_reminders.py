"""
Email users about saved scholarships that are about to close.

Run once a day (cron, Windows Task Scheduler, or your host's scheduler):

    python manage.py send_deadline_reminders
    python manage.py send_deadline_reminders --dry-run   # count only, send nothing
"""

from django.core.management.base import BaseCommand

from app1.reminders import send_reminders


class Command(BaseCommand):
    help = "Send 14-day and 3-day deadline reminders for saved scholarships."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show how many would be sent without sending")

    def handle(self, *args, dry_run=False, **options):
        emails, items = send_reminders(dry_run=dry_run)
        verb = "Would send" if dry_run else "Sent"
        self.stdout.write(self.style.SUCCESS(f"{verb} {emails} email(s) covering {items} saved scholarship(s)."))
