"""
Create the admin account from environment variables if it doesn't exist yet.
Safe to run on every start (useful on hosts without a shell):

    DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the admin user from DJANGO_SUPERUSER_* variables, once."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not (username and password):
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/PASSWORD not set; skipping.")
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Admin user {username} already exists.")
            return
        user = User.objects.create_superuser(
            username=username, email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""), password=password)
        user.profile.is_verified = True
        user.profile.save(update_fields=["is_verified"])
        self.stdout.write(self.style.SUCCESS(f"Created admin user {username}."))
