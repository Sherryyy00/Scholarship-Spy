"""
Hand-curated official programmes (Chevening, Commonwealth, DAAD).

Why not scrape these?
* DAAD: its imprint says downloading and printing are for personal, private,
  non-commercial use only, and all website content is copyright protected.
* Commonwealth Scholarship Commission (cscuk.fcdo.gov.uk): "All rights reserved".
* Chevening: one scheme with a few variants, so a scraper adds little.

So instead of copying their pages, each entry below is a short summary written
for Scholarship Spy, stating key facts and linking to the official page. Nothing
is fetched from the network. Review these once a year when new rounds open.

Last reviewed: November 2026.
"""

from .base import BaseScraper, ScrapedScholarship

ATTRIBUTION = "Summary written by Scholarship Spy. Official details are on the provider's website"

PROGRAMMES = [
    ScrapedScholarship(
        source_id="chevening-scholarships",
        title="Chevening Scholarships",
        link="https://www.chevening.org/scholarships/",
        university_name="Any eligible UK university",
        tution_structure="Fully funded",
        degree="Masters",
        subject="All subjects",
        eligibility="Emerging leaders from Chevening-eligible countries",
        country="United Kingdom",
        apply_date="See the Chevening application timeline",
        scholarship_details=(
            "The UK government's international scholarship programme, funded by the Foreign, Commonwealth and "
            "Development Office. It supports outstanding emerging leaders to complete a fully funded one-year "
            "master's degree at a UK university, in any subject. Variants include the standard scheme, a scheme "
            "for Small Island Developing States (SIDS) and an ASEAN scheme, each with its own list of eligible "
            "countries. Check the official site for work-experience requirements and dates."
        ),
    ),
    ScrapedScholarship(
        source_id="commonwealth-masters",
        title="Commonwealth Master's Scholarships",
        link="https://cscuk.fcdo.gov.uk/scholarships/commonwealth-masters-scholarships/",
        university_name="Participating UK universities",
        tution_structure="Fully funded: tuition, living allowance, travel",
        degree="Masters",
        subject="Development-related subjects",
        eligibility="Citizens of eligible low and middle income Commonwealth countries",
        country="United Kingdom",
        apply_date="Usually closes in October (check the CSC website)",
        scholarship_details=(
            "Run by the Commonwealth Scholarship Commission in the UK and funded by the FCDO. For candidates from "
            "eligible low and middle income Commonwealth countries to study a full-time taught master's degree at "
            "a UK university. Awards cover approved tuition fees, a monthly living allowance and return travel. "
            "Study must fit one of the CSC's development themes, and applicants also need a nomination from a "
            "national nominating agency or university."
        ),
    ),
    ScrapedScholarship(
        source_id="commonwealth-shared",
        title="Commonwealth Shared Scholarships",
        link="https://cscuk.fcdo.gov.uk/?p=23761",
        university_name="Participating UK universities",
        tution_structure="Fully funded (jointly with the UK university)",
        degree="Masters",
        subject="Development-related subjects",
        eligibility="Least developed and middle income Commonwealth countries",
        country="United Kingdom",
        apply_date="Varies by university (check the CSC website)",
        scholarship_details=(
            "Master's scholarships co-funded by the Commonwealth Scholarship Commission and UK universities, for "
            "talented students from least developed and middle income Commonwealth countries who could not "
            "otherwise afford to study in the UK and have not previously studied for a year or more in a "
            "high-income country. Master's courses only. You must also secure admission to the course."
        ),
    ),
    ScrapedScholarship(
        source_id="commonwealth-distance-learning",
        title="Commonwealth Distance Learning Master's Scholarships",
        link="https://cscuk.fcdo.gov.uk/scholarships/commonwealth-distance-learning-scholarships-candidates/",
        university_name="Participating UK universities (online)",
        tution_structure="Tuition fees covered",
        degree="Masters",
        subject="Development-related subjects",
        eligibility="Citizens of eligible low and middle income Commonwealth countries",
        country="United Kingdom (distance learning)",
        apply_date="Varies by university (check the CSC website)",
        scholarship_details=(
            "For candidates from eligible low and middle income Commonwealth countries to study a part-time taught "
            "master's degree with a UK university while staying in their home country. Master's courses only. "
            "Apply for admission to an approved course and for the scholarship through the CSC's online system."
        ),
    ),
    ScrapedScholarship(
        source_id="daad-study-scholarships-masters",
        title="DAAD Study Scholarships: Master Studies for All Academic Disciplines",
        link="https://www.daad.de/go/en/stipa50026200",
        university_name="State or state-recognised German universities",
        tution_structure="Monthly stipend, health insurance, travel allowance",
        degree="Masters",
        subject="All subjects",
        eligibility="International graduates (country-specific rules apply)",
        country="Germany",
        apply_date="Deadlines vary by country (check DAAD)",
        scholarship_details=(
            "Offered by the German Academic Exchange Service (DAAD) for international graduates who want to "
            "complete a full master's degree, or one year of study as part of a master's at their home "
            "university, at a German university. Open to almost all subjects; the DAAD runs separate programmes "
            "for music, fine art, performing arts and architecture. Includes a monthly payment, health insurance "
            "and a travel allowance."
        ),
    ),
    ScrapedScholarship(
        source_id="daad-epos-development",
        title="DAAD EPOS: Development-Related Postgraduate Courses",
        link="https://www.daad.de/go/en/stipa50076777",
        university_name="Selected German universities",
        tution_structure="Monthly stipend",
        degree="Masters",
        subject="Development-related subjects",
        eligibility="Graduates from developing and newly industrialised countries with 2+ years' work experience",
        country="Germany",
        apply_date="Deadlines vary by course (check DAAD)",
        scholarship_details=(
            "DAAD scholarships for graduates from developing and newly industrialised countries, in any "
            "discipline, with at least two years' professional experience. Funds a postgraduate or master's "
            "degree (and in exceptional cases a doctorate) on a list of development-related courses at German "
            "universities. Funding lasts 12 to 42 months depending on the programme."
        ),
    ),
]


class CuratedOfficialScraper(BaseScraper):
    name = "curated_official"
    label = "Official programmes (curated summaries)"
    attribution = ATTRIBUTION

    def scrape(self):
        for item in PROGRAMMES:
            yield ScrapedScholarship(**{**item.__dict__, "source_url": item.link})
