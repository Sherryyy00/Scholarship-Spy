"""
Turn free-text application deadlines into real dates.

Scraped and hand-written listings describe deadlines in many ways:

    "31 March"            -> next 31 March (estimated: no year given)
    "March 31, 2027"      -> 2027-03-31
    "31/03/2027"          -> 2027-03-31 (UK style: day first)
    "2027-03-31"          -> 2027-03-31
    "Deadline: 15 Jan 27" -> 2027-01-15
    "Usually October to January (check website)" -> None (too vague to guess)

parse_deadline() returns (date, estimated). "estimated" is True when the text
had no year, so we assumed the next time that day comes round. Those dates are
rolled forward each year by roll_forward_estimated().
"""

import re
from datetime import date

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(\d{4}|\d{2})"

# Ranges like "October to January" or "varies" are too vague to turn into one date.
_VAGUE = re.compile(r"\b(to|until|between|varies|vary|rolling|usually|typically|ongoing|open all year)\b", re.I)

_PATTERNS = [
    # 2027-03-31
    ("iso", re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")),
    # 31/03/2027, 31.03.2027, 31-03-27 (UK: day first)
    ("dmy_num", re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\b")),
    # 31 March 2027, 31st Mar 27
    ("dmy", re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MONTH}\.?,?\s+{_YEAR}\b", re.I)),
    # March 31, 2027
    ("mdy", re.compile(rf"\b{_MONTH}\.?\s+{_DAY},?\s+{_YEAR}\b", re.I)),
    # 31 March (no year)
    ("dm", re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MONTH}\b", re.I)),
    # March 31 (no year)
    ("md", re.compile(rf"\b{_MONTH}\.?\s+{_DAY}\b", re.I)),
]


def _month(word):
    word = word.lower().rstrip(".")
    return MONTHS.get(word) or MONTHS[word[:3]]


def _year(text):
    y = int(text)
    return y + 2000 if y < 100 else y


def _safe_date(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def next_occurrence(month, day, today=None):
    """The next time this day/month comes round, today included."""
    today = today or date.today()
    for year in (today.year, today.year + 1, today.year + 2):  # +2 covers 29 Feb
        candidate = _safe_date(year, month, day)
        if candidate and candidate >= today:
            return candidate
    return None


def parse_deadline(text, today=None):
    """Return (date or None, estimated: bool)."""
    if not text:
        return None, False
    t = " ".join(str(text).split())
    for kind, pattern in _PATTERNS:
        m = pattern.search(t)
        if not m:
            continue
        g = m.groups()
        if kind == "iso":
            return _safe_date(int(g[0]), int(g[1]), int(g[2])), False
        if kind == "dmy_num":
            return _safe_date(_year(g[2]), int(g[1]), int(g[0])), False
        if kind == "dmy":
            return _safe_date(_year(g[2]), _month(g[1]), int(g[0])), False
        if kind == "mdy":
            return _safe_date(_year(g[2]), _month(g[0]), int(g[1])), False
        # No year given: only trust it if the text isn't describing a vague range.
        if _VAGUE.search(t):
            return None, False
        month_word, day = (g[1], g[0]) if kind == "dm" else (g[0], g[1])
        found = next_occurrence(_month(month_word), int(day), today)
        return found, found is not None
    return None, False


def days_left(deadline, today=None):
    if deadline is None:
        return None
    return (deadline - (today or date.today())).days


def roll_forward_estimated(today=None):
    """Move yearless ('estimated') deadlines that have passed on to next year. Returns how many changed."""
    from .models import Scholarship

    today = today or date.today()
    changed = 0
    for s in Scholarship.all_objects.filter(deadline_estimated=True, deadline__lt=today):
        new = next_occurrence(s.deadline.month, s.deadline.day, today)
        if new and new != s.deadline:
            Scholarship.all_objects.filter(pk=s.pk).update(deadline=new)
            changed += 1
    return changed
