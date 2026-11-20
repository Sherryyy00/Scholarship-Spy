"""
Safe handling of user uploads.

CVs (PDF, DOCX, TXT)
  * checked by content ("magic bytes"), not by file name or browser-supplied type
  * size and page limits so a huge or malicious file can't tie up the server
  * text is extracted in memory and the file is thrown away (we never store CVs)
  * contact details (emails, phone numbers, links) are stripped before the text
    is saved or used, so personal data doesn't end up in the database

Profile photos (JPEG, PNG, WebP)
  * verified with Pillow and re-encoded as a fresh JPEG
  * re-encoding drops anything hidden in the file, including EXIF/GPS location
  * saved under a random name, so user-chosen file names never reach the disk
"""

import io
import re
import uuid
import zipfile

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

CV_MAX_BYTES = 5 * 1024 * 1024
CV_MAX_PAGES = 15
CV_MAX_CHARS = 20_000
CV_MIN_CHARS = 150

PHOTO_MAX_BYTES = 3 * 1024 * 1024
PHOTO_MAX_PIXELS = 20_000_000
PHOTO_SIZE = (400, 400)


# ---------------------------------------------------------------- CVs

def _sniff(head):
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    return None


def _pdf_text(data):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValidationError("This PDF is password protected. Please upload an unlocked copy.")
        if len(reader.pages) > CV_MAX_PAGES:
            raise ValidationError(f"Your CV has more than {CV_MAX_PAGES} pages. Please upload a shorter version.")
        parts, total = [], 0
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
            total += len(text)
            if total > CV_MAX_CHARS:
                break
        return "\n".join(parts)
    except ValidationError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise ValidationError("We couldn't read this PDF. Try saving it again or upload a Word file.") from exc


def _docx_text(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                raise ValidationError("This doesn't look like a Word (.docx) file.")
            # Guard against zip bombs: the unpacked document must stay small.
            if zf.getinfo("word/document.xml").file_size > 20 * 1024 * 1024:
                raise ValidationError("This Word file is too large to process.")
        import docx

        document = docx.Document(io.BytesIO(data))
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                lines.append(" ".join(cell.text for cell in row.cells))
        return "\n".join(lines)
    except ValidationError:
        raise
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise ValidationError("We couldn't read this Word file. Try saving it again as .docx or PDF.") from exc


def _txt_text(data):
    if b"\x00" in data[:4096]:
        raise ValidationError("Please upload a PDF, Word (.docx) or plain text file.")
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValidationError("We couldn't read this text file.")


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RE = re.compile(r"(https?://|www\.)\S+|\b\S+\.(com|org|net|io|me|dev)(/\S*)?\b", re.I)
# Digits with at most one separator between them, e.g. "+44 7700 900123", "(020) 7946-0018".
PHONE_RE = re.compile(r"(?<![\w-])\+?\(?\d(?:\)?[ .-]?\(?\d){8,}(?!\w)")


def _strip_phone(match):
    """Only treat it as a phone number if it has 10+ digits (keeps date ranges like 2021 - 2024)."""
    return " " if sum(ch.isdigit() for ch in match.group(0)) >= 10 else match.group(0)


def clean_cv_text(text):
    """Remove contact details and layout noise; keep the words that describe the person."""
    text = EMAIL_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    text = PHONE_RE.sub(_strip_phone, text)
    text = re.sub(r"[•▪●◦■□►✓✔|]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:CV_MAX_CHARS]


def extract_cv_text(uploaded):
    """Return cleaned text from an uploaded CV, or raise ValidationError with a friendly message."""
    if uploaded.size > CV_MAX_BYTES:
        raise ValidationError("Your CV is larger than 5 MB. Please upload a smaller file.")
    data = uploaded.read()
    name = (uploaded.name or "").lower()
    kind = _sniff(data[:8])

    if kind == "pdf":
        text = _pdf_text(data)
    elif kind == "zip" and name.endswith(".docx"):
        text = _docx_text(data)
    elif kind is None and name.endswith(".txt"):
        text = _txt_text(data)
    else:
        raise ValidationError("Please upload your CV as a PDF, Word (.docx) or plain text file.")

    text = clean_cv_text(text)
    if len(text) < CV_MIN_CHARS:
        raise ValidationError(
            "We couldn't find enough text in your CV. If it's a scanned image, "
            "please upload a text-based PDF or Word file, or write a short statement instead."
        )
    return text


# ---------------------------------------------------------------- education level

# Highest level first. Used to suggest the *next* degree level when the user hasn't chosen one.
_LEVELS = [
    ("phd", re.compile(r"\b(ph\.?\s?d|doctorate|doctoral)\b", re.I)),
    ("masters", re.compile(r"\b(master'?s?|m\.?sc|m\.?a\.?|mba|m\.?eng|mphil|llm|postgraduate)\b", re.I)),
    ("bachelors", re.compile(r"\b(bachelor'?s?|b\.?sc|b\.?a\.?|b\.?eng|b\.?tech|bba|undergraduate degree|bs\b)", re.I)),
    ("school", re.compile(r"\b(a[- ]?levels?|high school|secondary school|gcses?|igcse|ib diploma|"
                          r"intermediate|f\.?sc|matric(ulation)?|sixth form)\b", re.I)),
]
NEXT_LEVEL = {"school": "Bachelors", "bachelors": "Masters", "masters": "PhD", "phd": "PhD", None: ""}


# Sentences about what someone *wants* to study say nothing about what they've completed.
_ASPIRATION = re.compile(
    r"\b(want|wants|wish|hope|hoping|plan|planning|aim|aiming|apply|applying|pursue|pursuing|"
    r"seek|seeking|looking to|would like|interested in|dream|goal|aspire|intend)\b", re.I)


def completed_level(text):
    """Rough guess at the highest degree someone has completed or is studying (not one they hope to do)."""
    sentences = re.split(r"(?<=[.!?])\s+|\n|[,;]\s*|\s+(?:and|but)\s+", text)
    factual = " ".join(s for s in sentences if not _ASPIRATION.search(s))
    for level, pattern in _LEVELS:
        if pattern.search(factual):
            return level
    return None


def suggested_degree(text):
    return NEXT_LEVEL[completed_level(text)]


# ---------------------------------------------------------------- photos

def process_profile_photo(uploaded):
    """Validate an uploaded image and return a safe re-encoded JPEG as a ContentFile."""
    if uploaded.size > PHOTO_MAX_BYTES:
        raise ValidationError("Profile photos must be smaller than 3 MB.")
    data = uploaded.read()
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()  # detects truncated/corrupt files
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError("Please upload a JPG, PNG or WebP image.")
            if img.width * img.height > PHOTO_MAX_PIXELS:
                raise ValidationError("That image is too large. Please upload a smaller photo.")
            img = img.convert("RGB")
            img.thumbnail(PHOTO_SIZE)
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=88)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError("That file isn't a valid image.") from exc
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.jpg")
