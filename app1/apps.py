import os
import sys

from django.apps import AppConfig


def _is_web_server():
    """True for the process that actually serves requests (runserver child or gunicorn)."""
    argv = " ".join(sys.argv)
    if "runserver" in argv:
        # With auto-reload, Django runs the server in a child process with RUN_MAIN set.
        return os.environ.get("RUN_MAIN") == "true" or "--noreload" in argv
    return "gunicorn" in os.path.basename(sys.argv[0]) or "gunicorn" in os.environ.get("SERVER_SOFTWARE", "")


class App1Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app1"

    def ready(self):
        import app1.signals  # noqa: F401

        from django.conf import settings

        if settings.SCHEDULER_AUTOSTART and _is_web_server():
            from .jobs import start_background_scheduler

            start_background_scheduler()
