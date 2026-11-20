import re
from pathlib import Path

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from app1 import views
from app1.scrapers.erasmus_mundus import ErasmusMundusRSSScraper
from app1.scrapers.base import ScraperError

TEMPLATES = Path(__file__).parent / "templates"


class Base(TestCase):
    def setUp(self):
        cache.clear()


class HeaderTests(Base):
    def test_csp_blocks_inline_scripts(self):
        r = self.client.get(reverse("home"))
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp.split("script-src")[1].split(";")[0])
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("Permissions-Policy", r.headers)
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_no_inline_javascript_in_templates(self):
        """CSP would block it, so the page would silently break."""
        for path in TEMPLATES.rglob("*.html"):
            if "emails" in path.parts:
                continue
            text = path.read_text()
            self.assertNotRegex(text, r"<script>|<script\s+type=\"text/javascript\">", path.name)
            self.assertNotRegex(text, r"\son(click|change|submit|load|input)=", path.name)
            self.assertNotIn("javascript:", text, path.name)

    def test_oversized_request_rejected_early(self):
        r = self.client.post(reverse("login"), data="x", content_type="text/plain",
                             CONTENT_LENGTH=str(50 * 1024 * 1024))
        self.assertEqual(r.status_code, 413)


class ProductionSettingsTests(TestCase):
    def test_deploy_check_is_clean(self):
        """Only the two HSTS opt-ins remain. They are deliberate: on a shared host
        subdomain (e.g. *.onrender.com) you don't control the other subdomains,
        and preloading is a long-term commitment for your own domain."""
        import os, secrets, subprocess, sys
        env = dict(os.environ, DJANGO_DEBUG="False", DJANGO_SECRET_KEY=secrets.token_urlsafe(50),
                   DJANGO_ALLOWED_HOSTS="example.com", DJANGO_HSTS_SECONDS="31536000")
        out = subprocess.run([sys.executable, "manage.py", "check", "--deploy"],
                             cwd=Path(__file__).parent.parent, env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        found = set(re.findall(r"\((security\.\w+)\)", out.stdout + out.stderr))
        self.assertLessEqual(found, {"security.W005", "security.W021"}, out.stdout + out.stderr)


class ClientIpTests(Base):
    def _req(self, xff=None, remote="10.0.0.1"):
        from django.test import RequestFactory
        meta = {"REMOTE_ADDR": remote}
        if xff:
            meta["HTTP_X_FORWARDED_FOR"] = xff
        return RequestFactory().get("/", **meta)

    def test_ignores_forwarded_header_without_proxy(self):
        self.assertEqual(views._client_ip(self._req("1.2.3.4")), "10.0.0.1")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_uses_proxy_entry_not_spoofed_one(self):
        # The client sent "6.6.6.6"; the host's proxy appended the real address.
        self.assertEqual(views._client_ip(self._req("6.6.6.6, 81.2.69.160")), "81.2.69.160")


class RegistrationThrottleTests(Base):
    def test_sign_ups_limited_per_visitor(self):
        for i in range(views.REGISTRATIONS_PER_HOUR):
            self.client.post(reverse("Registration"), {"username": f"u{i}"})
        r = self.client.post(reverse("Registration"), {"username": "one-more"})
        self.assertEqual(r.status_code, 429)


class VerificationTests(Base):
    def test_link_works_once(self):
        user = User.objects.create_user("v", "v@example.com", "Str0ng-pass-123")
        token = user.profile.email_token
        self.client.get(reverse("verify", args=[token]))
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.is_verified)
        self.assertNotEqual(user.profile.email_token, token)


class PasswordResetTests(Base):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("reset", "reset@example.com", "Old-pass-12345")

    def test_full_reset_flow(self):
        r = self.client.post(reverse("password_reset"), {"email": "RESET@example.com"})
        self.assertRedirects(r, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://\S+", mail.outbox[0].body).group(0)
        path = "/" + link.split("/", 3)[3]
        r = self.client.get(path, follow=True)
        self.assertContains(r, "Choose a new password")
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "Brand-new-pass-987", "new_password2": "Brand-new-pass-987"})
        self.assertRedirects(r, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-new-pass-987"))
        # The link can't be reused.
        r = self.client.get(path, follow=True)
        self.assertContains(r, "Link expired")

    def test_unknown_email_looks_the_same(self):
        r = self.client.post(reverse("password_reset"), {"email": "nobody@example.com"})
        self.assertRedirects(r, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_requests_are_rate_limited(self):
        for _ in range(views.PASSWORD_RESETS_PER_HOUR):
            self.client.post(reverse("password_reset"), {"email": "reset@example.com"})
        r = self.client.post(reverse("password_reset"), {"email": "reset@example.com"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(len(mail.outbox), views.PASSWORD_RESETS_PER_HOUR)

    def test_login_page_links_to_reset(self):
        self.assertContains(self.client.get(reverse("login")), reverse("password_reset"))


class XmlSafetyTests(TestCase):
    def test_entity_expansion_refused(self):
        bomb = ('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa">'
                '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><rss><channel><item>'
                '<title>&b;</title></item></channel></rss>')
        with self.assertRaises(ScraperError):
            list(ErasmusMundusRSSScraper.parse(bomb))


class AdminUrlTests(TestCase):
    def test_admin_path_is_configurable(self):
        from django.conf import settings
        self.assertTrue(settings.ADMIN_URL.endswith("/"))
        self.assertEqual(reverse("admin:index"), "/" + settings.ADMIN_URL)
