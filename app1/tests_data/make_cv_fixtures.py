"""
Regenerates the sample CVs used in tests (fictional person, reserved example contact details).
Needs reportlab: pip install reportlab python-docx
    python app1/tests_data/make_cv_fixtures.py
"""
from pathlib import Path

import docx
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
LINES = [
    "Alex Example",
    "alex.example@example.com | +44 7700 900123 | linkedin.com/in/alex-example",
    "",
    "EDUCATION",
    "BSc (Hons) Electrical Engineering, Example University, 2021 - 2024, First Class",
    "Final year project: forecasting wind turbine power output from weather data using Python",
    "",
    "EXPERIENCE",
    "Graduate Engineer, Example Energy Ltd, 2024 - present",
    "Analysed offshore wind and solar energy generation data and supported grid integration studies.",
    "",
    "SKILLS",
    "Python, MATLAB, power systems, renewable energy systems, energy forecasting, sustainability",
    "",
    "GOALS",
    "I want to study a masters in renewable energy engineering focused on offshore wind power and sustainable power grids.",
]


def make_pdf():
    c = canvas.Canvas(str(HERE / "sample_cv.pdf"), pagesize=A4)
    y = 800
    for line in LINES:
        c.drawString(50, y, line)
        y -= 18
    c.save()


def make_docx():
    d = docx.Document()
    for line in LINES:
        d.add_paragraph(line)
    d.save(HERE / "sample_cv.docx")


if __name__ == "__main__":
    make_pdf()
    make_docx()
    print("written")
