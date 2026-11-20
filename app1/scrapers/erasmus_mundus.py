"""
Erasmus Mundus Joint Masters, from the EU's official catalogue (EACEA).

Licence: content on European Commission websites may be reused under CC BY 4.0
provided the source is credited (Commission Decision 2011/833/EU). We credit
the catalogue on every listing via `attribution`.

Two sources:

* erasmus_mundus_rss      - the catalogue's RSS feed. Stable XML with rich tags
                            (study area, duration, universities), but only the
                            30 most recently added programmes. Fully tested.
* erasmus_mundus_catalogue - the paginated catalogue pages (~190 programmes).
                            EXPERIMENTAL: the HTML parser is written defensively
                            but has not yet been checked against a saved live
                            page. Run it with --dry-run --save-html first.
"""

import re
from collections import defaultdict
from html import unescape

from bs4 import BeautifulSoup
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as ET  # safe against XML bombs / external entities

from .base import BaseScraper, ScrapedScholarship, ScraperError

CATALOGUE_URL = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"
RSS_URL = "https://www.eacea.ec.europa.eu/node/253/rss_en"
ATTRIBUTION = "Erasmus Mundus Catalogue, European Education and Culture Executive Agency. © European Union, CC BY 4.0"

COMMON = {
    "degree": "Masters",
    "tution_structure": "Erasmus Mundus scholarship (most programmes)",
    "eligibility": "Students worldwide",
    "apply_date": "Usually October to January (check programme website)",
}

ATOM = "{http://www.w3.org/2005/Atom}"


def _join(values, limit):
    """Join unique values with '; ' and keep within a column limit."""
    seen, out = set(), []
    for v in values:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    text = "; ".join(out)
    return text if len(text) <= limit else text[: limit - 1].rsplit(";", 1)[0] + "…"


def _tidy_university(name):
    """'UNIVERSITA DEGLI STUDI DI MILANO' -> 'Universita Degli Studi Di Milano'."""
    return name.title() if name.isupper() else name


def _clean_subject(value):
    """'Physics (PHY)' -> 'Physics'. Drops all-caps programme codes like 'QUANTIC'."""
    value = re.sub(r"\s*\([A-Z]{2,5}\)\s*$", "", value).strip()
    return "" if re.fullmatch(r"[A-Z0-9_\-]{2,12}", value) else value


class ErasmusMundusRSSScraper(BaseScraper):
    name = "erasmus_mundus_rss"
    label = "Erasmus Mundus Catalogue (RSS)"
    attribution = ATTRIBUTION

    def scrape(self):
        yield from self.parse(self.fetch(RSS_URL))

    @classmethod
    def parse(cls, xml_text):
        try:
            root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
        except (ET.ParseError, DefusedXmlException) as exc:
            raise ScraperError(f"RSS is not valid XML: {exc}") from exc

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            link = (item.findtext("link") or "").strip()
            source_id = (item.findtext(f"{ATOM}id") or item.findtext("guid") or link).strip()

            cats = defaultdict(list)
            for cat in item.findall("category"):
                cats[cat.get("domain", "")].append((cat.text or "").strip())

            studies = [s for s in map(_clean_subject, cats["Studies"]) if s]
            thematic = cats["Thematic global"]
            duration = ", ".join(cats["ECTS Duration"])
            years = ", ".join(cats["Years for EMJMD"])
            universities = [_tidy_university(u) for u in cats["EMJMD Universities"]]

            description_html = unescape(item.findtext("description") or "")
            overview = BeautifulSoup(description_html, "html.parser").find("a", href=True)

            details = [f"{title} is an Erasmus Mundus Joint Master delivered by a consortium of universities."]
            if studies or thematic:
                details.append("Study area: " + _join(studies + thematic, 400) + ".")
            if duration:
                details.append(f"Duration: {duration}.")
            if universities:
                details.append("Partner universities: " + _join(universities, 1000) + ".")
            if years:
                details.append(f"Selected for EU funding: {years}.")
            if overview:
                details.append(f"EU project overview: {overview['href']}")
            details.append("Contact the consortium through the programme website for courses, "
                           "application steps and scholarship availability.")

            yield ScrapedScholarship(
                title=title,
                source_id=source_id,
                link=link,
                source_url=CATALOGUE_URL,
                university_name=_join(universities, 200),
                subject=_join(studies or thematic, 200),
                country="Europe",
                scholarship_details=" ".join(details),
                **COMMON,
            )


class ErasmusMundusCatalogueScraper(BaseScraper):
    name = "erasmus_mundus_catalogue"
    label = "Erasmus Mundus Catalogue"
    attribution = ATTRIBUTION
    enabled = False  # flip to True once the parser has been checked against a saved page
    max_pages = 30   # safety stop (~20 programmes per page, ~10 pages today)

    def scrape(self):
        seen = set()
        for page in range(self.max_pages):
            html = self.fetch(f"{CATALOGUE_URL}?page={page}")
            items = [i for i in self.parse(html) if i.source_id not in seen]
            if not items:
                break
            for item in items:
                seen.add(item.source_id)
                yield item

    @classmethod
    def parse(cls, html):
        """
        Each catalogue entry shows: the programme title, a link to its website,
        an optional "Project locations" list of countries, and a
        "<ACRONYM> - Project overview" link. We anchor on the overview link,
        which every entry has, and read the rest from its container.
        """
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup
        results = []
        for overview in main.find_all(string=re.compile(r"project overview", re.I)):
            card = cls._card_for(overview)
            if card is None:
                continue
            item = cls._parse_card(card)
            if item and item.source_id not in {r.source_id for r in results}:
                results.append(item)
        return results

    @staticmethod
    def _card_for(node):
        """Walk up from the 'Project overview' text to the element holding one whole entry."""
        el = node.parent
        for _ in range(6):
            if el is None or el.parent is None:
                return None
            # Stop once the container holds an external programme link besides the overview link.
            links = [a["href"] for a in el.find_all("a", href=True)]
            external = [h for h in links if "europa.eu" not in h and h.startswith("http")]
            if external and len(el.find_all(string=re.compile(r"project overview", re.I))) == 1:
                return el
            el = el.parent
        return None

    @staticmethod
    def _parse_card(card):
        links = card.find_all("a", href=True)
        website = next((a for a in links if a["href"].startswith("http") and "europa.eu" not in a["href"]), None)
        if website is None:
            return None

        heading = card.find(re.compile(r"^h[1-6]$"))
        title = heading.get_text(" ", strip=True) if heading else ""
        overview_text = card.find(string=re.compile(r"project overview", re.I)) or ""
        acronym = re.split(r"\s*-\s*project overview", str(overview_text), flags=re.I)[0].strip()
        if not title:
            title = website.get_text(" ", strip=True)
            if title.startswith("http"):
                title = acronym or title

        countries = ""
        loc_label = card.find(string=re.compile(r"project locations", re.I))
        if loc_label:
            nxt = loc_label.find_next(string=lambda s: s.strip() and not re.search(r"project locations", s, re.I))
            if nxt and card in [p for p in nxt.parents]:
                countries = nxt.strip(" -\n\t")

        details = f"{title} is an Erasmus Mundus Joint Master delivered by a consortium of universities"
        details += f" in {countries}." if countries else "."
        details += (" Contact the consortium through the programme website for courses, "
                    "application steps and scholarship availability.")

        return ScrapedScholarship(
            title=title[:300],
            source_id=website["href"].rstrip("/"),
            link=website["href"],
            source_url=CATALOGUE_URL,
            subject="",
            country=countries[:100] or "Europe",
            scholarship_details=details,
            **COMMON,
        )
