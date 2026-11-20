"""
Shared plumbing for every scholarship source.

Each source subclasses BaseScraper and implements scrape(), yielding
ScrapedScholarship objects. The base class takes care of being a good citizen:

* identifies itself with a clear User-Agent and contact URL
* checks robots.txt before every request and refuses disallowed URLs
* waits between requests (default 2 seconds) so we never hammer a site
* retries temporary failures (429, 5xx, timeouts) with back-off
* can save every page it downloads (--save-html) for debugging parsers

Before adding a new source, read its terms of use. Only add sites that allow
automated access, and always fill in `attribution`.
"""

import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

USER_AGENT = "ScholarshipSpyBot/1.0 (+https://github.com/Sherryyy00/Scholarship-Spy)"


class ScraperError(Exception):
    pass


class DisallowedByRobots(ScraperError):
    pass


@dataclass
class ScrapedScholarship:
    """One listing as a scraper found it. Field names match the Scholarship model."""

    title: str
    source_id: str
    link: str = ""
    source_url: str = ""
    university_name: str = ""
    tution_structure: str = ""
    degree: str = ""
    subject: str = ""
    eligibility: str = ""
    country: str = ""
    apply_date: str = ""
    scholarship_details: str = ""
    image_link: str = ""

    def as_model_fields(self):
        return {k: (v or "").strip() for k, v in asdict(self).items()}


class BaseScraper:
    #: short unique id, used in the database and on the command line
    name = ""
    #: human-readable name shown in the admin and on scholarship pages
    label = ""
    #: credit line shown next to every listing from this source
    attribution = ""
    #: set False for sources whose parser still needs checking against the live site
    enabled = True
    #: seconds to wait between requests to the same site
    delay = 2.0
    timeout = 30

    def __init__(self, session=None, delay=None, save_html_dir=None, respect_robots=True):
        self.session = session or self._build_session()
        if delay is not None:
            self.delay = delay
        self.save_html_dir = Path(save_html_dir) if save_html_dir else None
        self.respect_robots = respect_robots
        self._robots = {}
        self._last_request = 0.0
        self._saved = 0

    # ---- to implement in subclasses ----

    def scrape(self):
        """Yield ScrapedScholarship objects."""
        raise NotImplementedError

    # ---- helpers ----

    @staticmethod
    def _build_session():
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
        retry = Retry(
            total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"), respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def allowed_by_robots(self, url):
        if not self.respect_robots:
            return True
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots:
            parser = RobotFileParser()
            try:
                resp = self.session.get(f"{root}/robots.txt", timeout=self.timeout)
                # No robots.txt (404) means everything is allowed; 401/403 means we should stay out.
                if resp.status_code in (401, 403):
                    parser.disallow_all = True
                elif resp.ok:
                    parser.parse(resp.text.splitlines())
                else:
                    parser.allow_all = True
            except requests.RequestException:
                logger.warning("Could not read robots.txt for %s; treating as allowed", root)
                parser.allow_all = True
            self._robots[root] = parser
        return self._robots[root].can_fetch(USER_AGENT, url)

    def fetch(self, url):
        """GET a page politely and return its text."""
        if not self.allowed_by_robots(url):
            raise DisallowedByRobots(f"robots.txt disallows {url}")

        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ScraperError(f"Failed to fetch {url}: {exc}") from exc
        finally:
            self._last_request = time.monotonic()

        if self.save_html_dir:
            self.save_html_dir.mkdir(parents=True, exist_ok=True)
            self._saved += 1
            suffix = ".xml" if "xml" in resp.headers.get("Content-Type", "") or "rss" in url else ".html"
            path = self.save_html_dir / f"{self.name}_{self._saved:03d}{suffix}"
            path.write_text(resp.text, encoding="utf-8")
            logger.info("Saved %s -> %s", url, path)
        return resp.text
