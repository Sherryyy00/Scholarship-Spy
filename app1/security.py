"""
Security headers and request limits that Django doesn't add by itself.

Content-Security-Policy: scripts only from this site (there is no inline JavaScript),
so an injected <script> tag can't run even if a template bug ever let one through.
"""

from django.conf import settings
from django.http import HttpResponse

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com data:",
    "img-src 'self' data: https:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class HealthCheckMiddleware:
    """Answer /healthz before host and HTTPS checks: the host's health checker and
    uptime pingers may call it by internal address or plain HTTP."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Refuse oversized bodies before Django reads them (CV and photo limits are 5 MB and 3 MB).
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length > settings.MAX_REQUEST_BYTES:
            return HttpResponse("Upload too large.", status=413, content_type="text/plain")

        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response
