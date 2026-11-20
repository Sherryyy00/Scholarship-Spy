"""
Country reference data used for eligibility checks.

* Country names come from ISO 3166 (pycountry), using common names
  ("South Korea", "Iran") where ISO's official name is awkward.
* Group lists below are static snapshots. They change rarely, but they DO
  change, so each list says where it came from and when it was last checked.
  Eligibility shown on the site is always "likely": users are told to confirm
  on the official website.
"""

from functools import lru_cache

import pycountry

# A few ISO names that read badly in a dropdown.
_NAME_OVERRIDES = {
    "Korea, Republic of": "South Korea",
    "Korea, Democratic People's Republic of": "North Korea",
    "Iran, Islamic Republic of": "Iran",
    "Russian Federation": "Russia",
    "Viet Nam": "Vietnam",
    "Lao People's Democratic Republic": "Laos",
    "Syrian Arab Republic": "Syria",
    "Moldova, Republic of": "Moldova",
    "Tanzania, United Republic of": "Tanzania",
    "Venezuela, Bolivarian Republic of": "Venezuela",
    "Bolivia, Plurinational State of": "Bolivia",
    "Türkiye": "Turkey",
    "Taiwan, Province of China": "Taiwan",
    "Palestine, State of": "Palestine",
    "Micronesia, Federated States of": "Micronesia",
    "Congo, The Democratic Republic of the": "DR Congo",
    "Brunei Darussalam": "Brunei",
    "Cabo Verde": "Cape Verde",
    "Côte d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Eswatini": "Eswatini",
    "Holy See (Vatican City State)": "Vatican City",
}


def _display(country):
    name = getattr(country, "common_name", None) or country.name
    return _NAME_OVERRIDES.get(name, _NAME_OVERRIDES.get(country.name, name))


@lru_cache(maxsize=1)
def all_countries():
    """Sorted list of country display names."""
    return sorted({_display(c) for c in pycountry.countries})


@lru_cache(maxsize=1)
def _lookup():
    """Map lower-cased names, ISO codes and common alternatives to a display name."""
    table = {}
    for c in pycountry.countries:
        display = _display(c)
        for key in {c.name, display, getattr(c, "official_name", ""), getattr(c, "common_name", ""), c.alpha_2, c.alpha_3}:
            if key:
                table[key.lower()] = display
    table.update({k.lower(): v for k, v in _ALIASES.items()})
    return table


# Nationality words and common alternative names -> country display name.
_ALIASES = {
    "UK": "United Kingdom", "Britain": "United Kingdom", "Great Britain": "United Kingdom", "England": "United Kingdom",
    "Scotland": "United Kingdom", "Wales": "United Kingdom", "Northern Ireland": "United Kingdom",
    "British": "United Kingdom", "English": "United Kingdom", "Scottish": "United Kingdom", "Welsh": "United Kingdom",
    "USA": "United States", "US": "United States", "America": "United States", "American": "United States",
    "Pakistani": "Pakistan", "Indian": "India", "Bangladeshi": "Bangladesh", "Sri Lankan": "Sri Lanka",
    "Nepali": "Nepal", "Nepalese": "Nepal", "Afghan": "Afghanistan", "Chinese": "China", "Japanese": "Japan",
    "Korean": "South Korea", "Vietnamese": "Vietnam", "Filipino": "Philippines", "Indonesian": "Indonesia",
    "Malaysian": "Malaysia", "Singaporean": "Singapore", "Thai": "Thailand", "Iranian": "Iran", "Iraqi": "Iraq",
    "Turkish": "Turkey", "Saudi": "Saudi Arabia", "Emirati": "United Arab Emirates", "Egyptian": "Egypt",
    "Nigerian": "Nigeria", "Ghanaian": "Ghana", "Kenyan": "Kenya", "Ugandan": "Uganda", "Tanzanian": "Tanzania",
    "Ethiopian": "Ethiopia", "South African": "South Africa", "Zimbabwean": "Zimbabwe", "Zambian": "Zambia",
    "Cameroonian": "Cameroon", "Rwandan": "Rwanda", "Moroccan": "Morocco", "Algerian": "Algeria",
    "Tunisian": "Tunisia", "Sudanese": "Sudan", "Somali": "Somalia", "Jordanian": "Jordan", "Lebanese": "Lebanon",
    "Syrian": "Syria", "Palestinian": "Palestine", "Brazilian": "Brazil", "Mexican": "Mexico",
    "Colombian": "Colombia", "Argentinian": "Argentina", "Argentine": "Argentina", "Chilean": "Chile",
    "Peruvian": "Peru", "Canadian": "Canada", "Australian": "Australia", "New Zealander": "New Zealand",
    "German": "Germany", "French": "France", "Italian": "Italy", "Spanish": "Spain", "Portuguese": "Portugal",
    "Dutch": "Netherlands", "Belgian": "Belgium", "Irish": "Ireland", "Polish": "Poland", "Romanian": "Romania",
    "Greek": "Greece", "Swedish": "Sweden", "Norwegian": "Norway", "Danish": "Denmark", "Finnish": "Finland",
    "Swiss": "Switzerland", "Austrian": "Austria", "Russian": "Russia", "Ukrainian": "Ukraine",
    "Kazakh": "Kazakhstan", "Uzbek": "Uzbekistan", "Jamaican": "Jamaica", "Trinidadian": "Trinidad and Tobago",
    "Mauritian": "Mauritius", "Maldivian": "Maldives", "Burmese": "Myanmar", "Cambodian": "Cambodia",
}


def normalise_country(text):
    """'Pakistani', 'PK', 'pakistan' -> 'Pakistan'. Returns '' if not recognised."""
    if not text:
        return ""
    return _lookup().get(" ".join(str(text).split()).lower(), "")


# --- Groups ---------------------------------------------------------------

# European Union, 27 members. Checked November 2026.
EU = {
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Denmark", "Estonia", "Finland",
    "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta",
    "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden",
}

# Commonwealth of Nations, 56 members (thecommonwealth.org). Checked November 2026.
COMMONWEALTH = {
    "Antigua and Barbuda", "Australia", "Bahamas", "Bangladesh", "Barbados", "Belize", "Botswana", "Brunei",
    "Cameroon", "Canada", "Cyprus", "Dominica", "Eswatini", "Fiji", "Gabon", "Gambia", "Ghana", "Grenada",
    "Guyana", "India", "Jamaica", "Kenya", "Kiribati", "Lesotho", "Malawi", "Malaysia", "Maldives", "Malta",
    "Mauritius", "Mozambique", "Namibia", "Nauru", "New Zealand", "Nigeria", "Pakistan", "Papua New Guinea",
    "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa", "Seychelles",
    "Sierra Leone", "Singapore", "Solomon Islands", "South Africa", "Sri Lanka", "Tanzania", "Togo", "Tonga",
    "Trinidad and Tobago", "Tuvalu", "Uganda", "United Kingdom", "Vanuatu", "Zambia",
}

# World Bank high-income economies (FY2026 classification, approximate). Used to tell
# "developing" / "low and middle income" countries apart. Everything else counts as LMIC.
HIGH_INCOME = {
    "Andorra", "Antigua and Barbuda", "Aruba", "Australia", "Austria", "Bahamas", "Bahrain", "Barbados", "Belgium",
    "Bermuda", "Brunei", "Bulgaria", "Canada", "Cayman Islands", "Chile", "Croatia", "Curaçao", "Cyprus",
    "Czech Republic", "Denmark", "Estonia", "Faroe Islands", "Finland", "France", "French Polynesia", "Germany",
    "Gibraltar", "Greece", "Greenland", "Guam", "Guyana", "Hong Kong", "Hungary", "Iceland", "Ireland",
    "Isle of Man", "Israel", "Italy", "Japan", "South Korea", "Kuwait", "Latvia", "Liechtenstein", "Lithuania",
    "Luxembourg", "Macao", "Malta", "Monaco", "Nauru", "Netherlands", "New Caledonia", "New Zealand",
    "Northern Mariana Islands", "Norway", "Oman", "Palau", "Panama", "Poland", "Portugal", "Puerto Rico", "Qatar",
    "Romania", "Russia", "San Marino", "Saudi Arabia", "Seychelles", "Singapore", "Sint Maarten (Dutch part)",
    "Slovakia", "Slovenia", "Spain", "Saint Kitts and Nevis", "Sweden", "Switzerland", "Taiwan",
    "Trinidad and Tobago", "Turks and Caicos Islands", "United Arab Emirates", "United Kingdom", "United States",
    "Uruguay", "Virgin Islands, British", "Virgin Islands, U.S.",
}


def in_group(country, group):
    country = normalise_country(country) or country
    if group == "eu":
        return country in EU
    if group == "uk":
        return country == "United Kingdom"
    if group == "commonwealth":
        return country in COMMONWEALTH
    if group == "commonwealth_lmic":
        return country in COMMONWEALTH and country not in HIGH_INCOME
    if group == "developing":
        return country not in HIGH_INCOME
    raise ValueError(f"Unknown group {group}")
