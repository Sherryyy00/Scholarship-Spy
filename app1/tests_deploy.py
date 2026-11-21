import os
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from app1.storage import CloudinaryMediaStorage


class HealthCheckTests(TestCase):
    @override_settings(ALLOWED_HOSTS=["example.com"], SECURE_SSL_REDIRECT=True)
    def test_answers_any_host_over_http(self):
        r = self.client.get("/healthz", HTTP_HOST="10.0.0.5:10000")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"ok")

    @override_settings(ALLOWED_HOSTS=["example.com"])
    def test_other_pages_still_check_host(self):
        self.assertEqual(self.client.get("/", HTTP_HOST="evil.test").status_code, 400)


class AvatarTests(TestCase):
    def test_default_avatar_is_a_static_file(self):
        user = User.objects.create_user("a", "a@example.com", "Pass-word-123")
        self.assertIn("assets/img/default-avatar.jpg", user.profile.avatar_url)
        self.assertEqual(self.client.get(user.profile.avatar_url).status_code, 200)


class SuperuserTests(TestCase):
    ENV = {"DJANGO_SUPERUSER_USERNAME": "boss", "DJANGO_SUPERUSER_EMAIL": "boss@example.com",
           "DJANGO_SUPERUSER_PASSWORD": "Very-strong-pass-42"}

    def test_created_once_and_verified(self):
        with mock.patch.dict(os.environ, self.ENV):
            call_command("ensure_superuser", stdout=mock.MagicMock())
            call_command("ensure_superuser", stdout=mock.MagicMock())
        user = User.objects.get(username="boss")
        self.assertTrue(user.is_superuser and user.profile.is_verified)
        self.assertEqual(User.objects.filter(username="boss").count(), 1)

    def test_skips_without_variables(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DJANGO_SUPERUSER_USERNAME", None)
            call_command("ensure_superuser", stdout=mock.MagicMock())
        self.assertFalse(User.objects.filter(is_superuser=True).exists())


class CloudinaryStorageTests(TestCase):
    @mock.patch("app1.storage.cloudinary.uploader.upload")
    def test_upload_uses_random_name_and_https_url(self, upload):
        from django.core.files.base import ContentFile
        import cloudinary
        cloudinary.config(cloud_name="demo", api_key="k", api_secret="s")
        storage = CloudinaryMediaStorage()
        name = storage.save("profile_pics/me.jpg", ContentFile(b"jpeg"))
        self.assertRegex(name, r"^profile_pics/[0-9a-f]{32}\.jpg$")
        self.assertTrue(upload.call_args.kwargs["public_id"].startswith("scholarship-spy/profile_pics/"))
        self.assertTrue(storage.url(name).startswith("https://res.cloudinary.com/demo/"))


class DatabaseUrlTests(TestCase):
    def test_neon_url_parses(self):
        import dj_database_url
        cfg = dj_database_url.parse("postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/db?sslmode=require",
                                    conn_max_age=60, conn_health_checks=True)
        self.assertEqual(cfg["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(cfg["OPTIONS"]["sslmode"], "require")
