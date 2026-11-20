import logging

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def get_all_countries():
    """Fetch country names from restcountries.com. Returns [] if the API is unavailable."""
    try:
        response = requests.get("https://restcountries.com/v3.1/all?fields=name", timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Could not fetch country list")
        return []
    return sorted(c["name"]["common"] for c in response.json())


def send_email_token(email, token):
    link = settings.SITE_URL + reverse("verify", args=[token])
    try:
        send_mail(
            subject="Verify your Scholarship Spy account",
            message=f"Welcome to Scholarship Spy!\n\nClick the link below to verify your account:\n{link}\n",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )
    except Exception:
        logger.exception("Failed to send verification email to %s", email)
        return False
    return True
