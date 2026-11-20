"""
Who can apply? Compare a user's profile with a scholarship's eligibility text.

Every result is one of:
    eligible      - the rules we could read all say yes
    not_eligible  - at least one rule clearly says no (with the reason)
    unknown       - we can't tell (vague text, or the profile is missing details)

We only ever HIDE "not_eligible" results, and only when the user asks to,
so a vague listing is never hidden by mistake. The site always tells users
to confirm on the official website.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from . import geo
from .uploads import completed_level

ELIGIBLE, NOT_ELIGIBLE, UNKNOWN = "eligible", "not_eligible", "unknown"

# ---------------------------------------------------------------- nationality rules

# (pattern, rule). First match wins, so the more specific ones come first.
_RULES = [
    (re.compile(r"commonwealth", re.I) , "commonwealth_lmic_or_all"),
    (re.compile(r"\b(uk|united kingdom)\b.{0,20}\b(eu|european union)\b|\b(eu|european union)\b.{0,20}\b(uk|united kingdom)\b", re.I), "uk_eu"),
    (re.compile(r"\b(eu|european union|eea)\s+(students|citizens|nationals)\b", re.I), "eu"),
    (re.compile(r"\b(home|uk)\s+(students|citizens|nationals|residents)\b", re.I), "uk"),
    (re.compile(r"\b(developing|newly industriali[sz]ed|low[- ]income|lmic|global south)\b", re.I), "developing"),
    (re.compile(r"\b(all nationalities|any nationality|students worldwide|worldwide|all countries|any country|open to all)\b", re.I), "any"),
    (re.compile(r"eligible countries|country-specific|selected countries|certain countries", re.I), "listed_countries"),
    (re.compile(r"\binternational\b", re.I), "international"),
]


@dataclass
class Result:
    status: str = UNKNOWN
    reasons: list = field(default_factory=list)  # human-readable, shown on the site

    @property
    def is_eligible(self):
        return self.status == ELIGIBLE

    @property
    def is_blocked(self):
        return self.status == NOT_ELIGIBLE


def nationality_rule(text):
    text = text or ""
    for pattern, rule in _RULES:
        if pattern.search(text):
            if rule == "commonwealth_lmic_or_all":
                return "commonwealth_lmic" if re.search(r"low|middle|least developed|developing", text, re.I) else "commonwealth"
            return rule
    return None


def _host_country(scholarship):
    return geo.normalise_country(scholarship.country.split("(")[0]) if scholarship.country else ""


def check_nationality(scholarship, nationality):
    """Return (status, reason) for the nationality part only."""
    rule = nationality_rule(scholarship.eligibility)
    if rule is None:
        return UNKNOWN, ""
    if not nationality:
        return UNKNOWN, "Add your nationality to your profile to check eligibility."
    host = _host_country(scholarship)

    if rule == "any":
        return ELIGIBLE, "Open to all nationalities."
    if rule == "international":
        if host and nationality == host:
            return NOT_ELIGIBLE, f"For international students, so {nationality} nationals usually can't apply."
        return ELIGIBLE, "Open to international students."
    if rule == "listed_countries":
        if host and nationality == host:
            return NOT_ELIGIBLE, f"Not open to {nationality} nationals."
        return UNKNOWN, "Open to a list of countries. Check the official list."

    group_names = {
        "uk_eu": ("UK and EU nationals", ("uk", "eu")),
        "eu": ("EU nationals", ("eu",)),
        "uk": ("UK nationals", ("uk",)),
        "developing": ("people from developing countries", ("developing",)),
        "commonwealth": ("Commonwealth citizens", ("commonwealth",)),
        "commonwealth_lmic": ("citizens of low and middle income Commonwealth countries", ("commonwealth_lmic",)),
    }
    label, groups = group_names[rule]
    if any(geo.in_group(nationality, g) for g in groups):
        return ELIGIBLE, f"Open to {label}."
    return NOT_ELIGIBLE, f"Only for {label}."


# ---------------------------------------------------------------- degree level

_LEVEL_RANK = {"school": 0, "bachelors": 1, "masters": 2, "phd": 3}
_LEVEL_NAME = {"bachelors": "a bachelor's degree", "masters": "a master's degree", "phd": "a PhD"}


def scholarship_level(scholarship):
    d = (scholarship.degree or "").lower()
    if "phd" in d or "doctor" in d:
        return "phd"
    if "master" in d:
        return "masters"
    if "bachelor" in d or "undergrad" in d:
        return "bachelors"
    return None


def check_level(scholarship, qualification):
    """Someone who already holds a degree usually can't get funding to study at that level again."""
    level = scholarship_level(scholarship)
    have = completed_level(qualification or "")
    if not level or not have:
        return UNKNOWN, ""
    if _LEVEL_RANK[have] >= _LEVEL_RANK[level]:
        return NOT_ELIGIBLE, f"For {_LEVEL_NAME[level]}. You already have {_LEVEL_NAME.get(have, 'this level')}."
    return ELIGIBLE, ""


# ---------------------------------------------------------------- grades

_GPA = re.compile(
    r"(?:minimum|min\.?|at least)\s+(?:a\s+)?(?:c?gpa|grade point average)\s*(?:of)?\s*(\d(?:\.\d{1,2})?)"
    r"|(?:c?gpa)\s*(?:of)?\s*(\d(?:\.\d{1,2})?)\s*(?:/\s*4(?:\.0)?)?\s*(?:or\s+(?:above|higher|more)|\+)",
    re.I,
)


def minimum_gpa(scholarship):
    m = _GPA.search(f"{scholarship.eligibility} {scholarship.scholarship_details}")
    if not m:
        return None
    try:
        value = Decimal(m.group(1) or m.group(2))
    except (InvalidOperation, TypeError):
        return None
    return value if Decimal("0") < value <= Decimal("4") else None


def check_gpa(scholarship, cgpa):
    required = minimum_gpa(scholarship)
    if required is None or cgpa is None:
        return UNKNOWN, ""
    if Decimal(cgpa) < required:
        return NOT_ELIGIBLE, f"Needs a GPA of at least {required}. Yours is {cgpa}."
    return ELIGIBLE, ""


# ---------------------------------------------------------------- combined

def check(scholarship, profile):
    """Full eligibility check of one scholarship for one profile."""
    nationality = geo.normalise_country(profile.nationality) if profile else ""
    parts = [
        check_nationality(scholarship, nationality),
        check_level(scholarship, profile.highest_qualification if profile else ""),
        check_gpa(scholarship, profile.cgpa if profile else None),
    ]
    blocked = [reason for status, reason in parts if status == NOT_ELIGIBLE]
    if blocked:
        return Result(NOT_ELIGIBLE, blocked)
    nat_status, nat_reason = parts[0]
    reasons = [r for _, r in parts if r]
    if nat_status == ELIGIBLE:
        return Result(ELIGIBLE, reasons)
    return Result(UNKNOWN, reasons)


def check_many(scholarships, profile):
    """{scholarship_id: Result} for a list of scholarships."""
    return {s.pk: check(s, profile) for s in scholarships}


def blocked_ids(queryset, profile):
    """IDs in a queryset this profile is clearly NOT eligible for (used to filter lists)."""
    if not profile:
        return set()
    fields = ("id", "eligibility", "country", "degree", "scholarship_details")
    return {s.pk for s in queryset.only(*fields) if check(s, profile).is_blocked}
