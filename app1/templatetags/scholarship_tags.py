"""
Thumbnails for scholarship cards.

Order of preference:
1. The listing's own image (image_link), if it has one.
2. A photo of the destination country, if we ship one in static/assets/img/countries/.
3. A generated SVG card coloured by subject, showing the subject and country.
   Generated in-process, so it needs no network and never shows "image skipped".
"""

import hashlib
from html import escape
from urllib.parse import quote

from django import template
from django.templatetags.static import static

register = template.Library()

COUNTRY_PHOTOS = {
    "united kingdom": "london.jpeg", "uk": "london.jpeg", "england": "london.jpeg", "scotland": "london.jpeg",
    "germany": "germanyy.jpeg",
    "canada": "canada.jpeg",
    "united states": "usa.jpeg", "usa": "usa.jpeg", "united states of america": "usa.jpeg",
    "japan": "japan.jpeg",
    "australia": "australia.jpeg",
    "switzerland": "switz.jpeg",
}

# Calm, high-contrast gradients that sit well next to the site's navy (#31526B).
PALETTES = [
    ("#31526B", "#4F7C9C"), ("#2E6B5E", "#4E9C88"), ("#5B4B8A", "#8371B8"), ("#8A4B5B", "#B8717F"),
    ("#7A5A1E", "#B28B3D"), ("#1E5A7A", "#3D86B2"), ("#3F6B2E", "#6C9C4E"), ("#6B3F2E", "#9C6C4E"),
]

# Rough subject families -> a simple icon drawn in SVG
ICONS = {
    "tech": ("computer", "data", "software", "artificial", "ai", "ict", "engineering", "quantum", "physics", "math"),
    "life": ("bio", "health", "medic", "nurs", "marine", "life", "environment", "water", "geo", "energy", "agri"),
    "society": ("law", "econom", "business", "finance", "social", "politic", "migration", "humanit", "education", "art"),
}

ICON_PATHS = {
    # simple outline glyphs, 48x48, drawn at the top of the card
    "tech": '<rect x="6" y="10" width="36" height="24" rx="3"/><path d="M16 40h16M24 34v6"/>',
    "life": '<path d="M24 6c8 8 14 15 14 22a14 14 0 0 1-28 0c0-7 6-14 14-22z"/>',
    "society": '<path d="M8 18l16-9 16 9M12 18v16M20 18v16M28 18v16M36 18v16M6 38h36"/>',
    "default": '<path d="M4 18l20-9 20 9-20 9z"/><path d="M12 22v9c0 3 6 6 12 6s12-3 12-6v-9"/>',
}


def _family(text):
    t = text.lower()
    for family, words in ICONS.items():
        if any(w in t for w in words):
            return family
    return "default"


def _wrap(text, width=15, lines=3):
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1][: width - 1].rstrip() + "…"
    return out


def generated_thumbnail(subject, country, degree=""):
    label = (subject.split(";")[0].strip() if subject else "") or degree or "Scholarship"
    key = int(hashlib.md5(label.lower().encode()).hexdigest(), 16)
    dark, light = PALETTES[key % len(PALETTES)]
    icon = ICON_PATHS[_family(f"{subject} {degree}")]

    lines = _wrap(label)
    start_y = 168 - (len(lines) - 1) * 15
    text = "".join(
        f'<text x="150" y="{start_y + i * 30}" text-anchor="middle" font-size="22" font-weight="600">{escape(l)}</text>'
        for i, l in enumerate(lines)
    )
    country_short = country.split("(")[0].strip()
    footer = escape(" · ".join(p for p in (degree, country_short) if p)[:26])

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{dark}"/>'
        f'<stop offset="1" stop-color="{light}"/></linearGradient></defs>'
        '<rect width="300" height="300" fill="url(#g)"/>'
        '<circle cx="250" cy="40" r="90" fill="#fff" opacity=".06"/><circle cx="40" cy="280" r="70" fill="#fff" opacity=".06"/>'
        f'<g transform="translate(126 52)" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" '
        f'stroke-linejoin="round" opacity=".9">{icon}</g>'
        f'<g fill="#fff" font-family="Poppins, Segoe UI, Arial, sans-serif">{text}'
        f'<text x="150" y="262" text-anchor="middle" font-size="15" opacity=".85">{footer}</text></g></svg>'
    )
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


@register.simple_tag
def scholarship_image(scholarship):
    image = (getattr(scholarship, "image_link", "") or "").strip()
    if image.startswith(("http://", "https://")):
        return image
    country = (scholarship.country or "").strip()
    photo = COUNTRY_PHOTOS.get(country.lower())
    if photo:
        return static(f"assets/img/countries/{photo}")
    return generated_thumbnail(scholarship.subject or "", country, scholarship.degree or "")


@register.simple_tag
def deadline_badge(scholarship):
    """A small coloured badge describing how long is left to apply."""
    from django.utils.html import format_html

    deadline = getattr(scholarship, "deadline", None)
    if not deadline:
        return ""
    days = scholarship.days_left
    # Built by hand: strftime's "%-d" (no leading zero) doesn't work on Windows.
    title = f"{deadline.day} {deadline:%B %Y}" + (" (estimated, check the official site)" if scholarship.deadline_estimated else "")
    if days < 0:
        return format_html('<span class="dl-badge dl-closed" title="{}"><i class="bi bi-x-circle"></i> Closed</span>', title)
    if days == 0:
        text, tone = "Closes today", "dl-urgent"
    elif days <= 14:
        text, tone = f"Closes in {days} day{'s' if days != 1 else ''}", "dl-urgent"
    elif days <= 45:
        text, tone = f"Closes {deadline.day} {deadline:%b}", "dl-soon"
    else:
        text, tone = f"Closes {deadline.day} {deadline:%b %Y}", "dl-later"
    if scholarship.deadline_estimated:
        text += " (est.)"
    return format_html('<span class="dl-badge {}" title="{}"><i class="bi bi-calendar-event"></i> {}</span>', tone, title, text)
