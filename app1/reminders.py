"""
Deadline reminder emails.

Each user gets at most one email per run: a digest of their saved scholarships
(status Interested or Preparing) that close within 14 days, and again within
3 days. A reminder is recorded against the specific deadline it was sent for,
so re-running is safe and next year's deadline gets fresh reminders.
"""

import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .deadlines import roll_forward_estimated
from .models import SavedScholarship

logger = logging.getLogger(__name__)

FIRST_REMINDER_DAYS = 14
FINAL_REMINDER_DAYS = 3


def due_reminders(today=None):
    """Return {user: [(saved_item, kind, days_left), ...]} for reminders that should go out now."""
    today = today or timezone.localdate()
    items = (
        SavedScholarship.objects
        .filter(
            status__in=SavedScholarship.REMIND_STATUSES,
            profile__email_reminders=True,
            scholarship__is_active=True,
            scholarship__deadline__gte=today,
            scholarship__deadline__lte=today + timedelta(days=FIRST_REMINDER_DAYS),
        )
        .exclude(profile__user__email="")
        .select_related("scholarship", "profile__user")
        .order_by("scholarship__deadline")
    )
    due = defaultdict(list)
    for item in items:
        deadline = item.scholarship.deadline
        days = (deadline - today).days
        if days <= FINAL_REMINDER_DAYS and item.reminded_3_for != deadline:
            due[item.profile.user].append((item, "final", days))
        elif days > FINAL_REMINDER_DAYS and item.reminded_14_for != deadline:
            due[item.profile.user].append((item, "first", days))
    return due


def _absolute(path):
    return settings.SITE_URL + path


def build_email(user, entries):
    from .views import unsubscribe_token

    context = {
        "user": user,
        "entries": [
            {
                "title": item.scholarship.title,
                "days": days,
                "deadline": item.scholarship.deadline,
                "estimated": item.scholarship.deadline_estimated,
                "status": item.get_status_display(),
                "url": _absolute(reverse("scholarship_detail", args=[item.scholarship.pk])),
                "official_url": item.scholarship.link,
            }
            for item, _, days in entries
        ],
        "tracker_url": _absolute(reverse("my_applications")),
        "unsubscribe_url": _absolute(reverse("unsubscribe_reminders", args=[unsubscribe_token(user)])),
    }
    soonest = min(days for _, _, days in entries)
    count = len(entries)
    if soonest == 0:
        subject = "A saved scholarship closes today"
    elif count == 1:
        subject = f"{entries[0][0].scholarship.title[:60]} closes in {soonest} day{'s' if soonest != 1 else ''}"
    else:
        subject = f"{count} saved scholarships close soon"

    msg = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string("app1/emails/deadline_reminder.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
        headers={"List-Unsubscribe": f"<{context['unsubscribe_url']}>"},
    )
    msg.attach_alternative(render_to_string("app1/emails/deadline_reminder.html", context), "text/html")
    return msg


def send_reminders(today=None, dry_run=False):
    """Send all due reminders. Returns (emails_sent, items_reminded)."""
    today = today or timezone.localdate()
    roll_forward_estimated(today)
    sent = reminded = 0
    for user, entries in due_reminders(today).items():
        if dry_run:
            sent += 1
            reminded += len(entries)
            continue
        try:
            build_email(user, entries).send()
        except Exception:
            logger.exception("Failed to send deadline reminder to user %s", user.pk)
            continue
        for item, kind, _ in entries:
            deadline = item.scholarship.deadline
            if kind == "final":
                item.reminded_3_for = deadline
                item.reminded_14_for = item.reminded_14_for or deadline  # no point sending the 14-day one later
            else:
                item.reminded_14_for = deadline
            item.save(update_fields=["reminded_14_for", "reminded_3_for"])
        sent += 1
        reminded += len(entries)
    return sent, reminded
