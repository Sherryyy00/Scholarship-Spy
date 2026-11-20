"""
Registry of scholarship sources. To add one:

1. Check the site's terms of use and robots.txt allow automated access.
2. Create a module here with a BaseScraper subclass (see erasmus_mundus.py).
3. Add it to SCRAPERS below.
4. Add a test with a saved sample page in app1/tests_data/.
"""

from .base import BaseScraper, DisallowedByRobots, ScrapedScholarship, ScraperError
from .erasmus_mundus import ErasmusMundusCatalogueScraper, ErasmusMundusRSSScraper

SCRAPERS = {cls.name: cls for cls in (ErasmusMundusRSSScraper, ErasmusMundusCatalogueScraper)}

__all__ = ["SCRAPERS", "BaseScraper", "ScrapedScholarship", "ScraperError", "DisallowedByRobots"]
