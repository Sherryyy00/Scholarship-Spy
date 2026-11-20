"""Template context shared by every page."""

from functools import lru_cache
from pathlib import Path

from django.conf import settings

STATIC_DIR = Path(__file__).parent / "static"
VERSIONED = ("assets/css/custom.css", "assets/js/main.js")


@lru_cache(maxsize=1)
def _asset_version():
    """Changes whenever our own CSS/JS changes, so browsers fetch the new file instead of a cached one."""
    stamps = [int((STATIC_DIR / p).stat().st_mtime) for p in VERSIONED if (STATIC_DIR / p).exists()]
    return str(max(stamps, default=0))


def assets(request):
    if settings.DEBUG:
        _asset_version.cache_clear()  # pick up edits immediately while developing
    return {"asset_version": _asset_version()}
