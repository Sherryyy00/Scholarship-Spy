"""
Offline evaluation of the recommender.

A fixed set of realistic queries, each labelled with the scholarship(s) that
should rank first, is run against a fixed corpus (the demo CSV, the curated
official programmes and the Erasmus Mundus RSS sample). We report standard
ranking metrics so changes to the recommender can be judged on evidence:

    MRR      mean reciprocal rank of the first relevant result (1.0 = always first)
    Hit@1    share of queries where a relevant result is ranked first
    Hit@3    share of queries with a relevant result in the top 3
    nDCG@5   ranking quality of the top 5 (rewards several relevant results ranked high)

Run:  python manage.py evaluate_recommender
"""

import math
from dataclasses import dataclass

# (query, [titles that count as a correct answer]). Titles are matched by substring.
QUERIES = [
    # abbreviations and synonyms
    ("I want to do a masters in AI and ML", ["Data Science Masters", "Artificial Intelligence PhD"]),
    ("CS grad who codes in Python and wants to build software and web apps", ["Software Engineering"]),
    ("MBA style analytics, Power BI dashboards and BI for managers", ["Business Analytics"]),
    ("stats and econ", ["Finance and Economics"]),
    # plain topic descriptions
    ("renewable energy, wind farms and solar panels", ["Renewable Energy"]),
    ("offshore wind power forecasting", ["Renewable Energy"]),
    ("I'm a nurse hoping to train as a midwife", ["Nursing and Midwifery"]),
    ("epidemiology and global health research", ["Public Health"]),
    ("genomics and single-cell RNA analysis", ["Bioinformatics"]),
    ("spatial transcriptomics of ovarian cancer tumours", ["Bioinformatics"]),
    ("human rights and international law", ["Law and Human Rights"]),
    ("painting, illustration and creative media", ["Fine Arts"]),
    ("investment, econometrics and financial modelling", ["Finance and Economics"]),
    ("robotics and thermodynamics", ["Mechanical Engineering"]),
    ("quantum computing and physics", ["Quantum Technologies"]),
    ("marine biotechnology and the ocean", ["Marine Biotechnology"]),
    ("microscopy imaging with deep learning", ["Advanced Microscopy"]),
    # official programmes that look alike
    ("fully funded one year UK masters for future leaders in any subject", ["Chevening"]),
    ("from Nigeria, want a fully funded full-time UK masters on development topics", ["Commonwealth Master's", "Commonwealth Shared"]),
    ("part-time online masters with a UK university while staying in my home country", ["Distance Learning"]),
    ("German masters in any subject with a monthly stipend", ["DAAD Study Scholarships"]),
    ("development-related postgraduate course in Germany for professionals with work experience", ["DAAD EPOS"]),
    # word forms, typos and very short queries
    ("renewables engineer", ["Renewable Energy"]),
    ("economy and banking", ["Finance and Economics"]),
    ("machne lerning and statistcs", ["Data Science Masters"]),
    ("nursing", ["Nursing and Midwifery"]),
    ("artificial intelligence research doctorate", ["Artificial Intelligence PhD"]),
    # a whole CV (noisy, long)
    (
        "Alex Example. EDUCATION BSc (Hons) Electrical Engineering, Example University, 2021 - 2024, First Class. "
        "Final year project: forecasting wind turbine power output from weather data using Python. EXPERIENCE "
        "Graduate Engineer, Example Energy Ltd. Analysed offshore wind and solar energy generation data and "
        "supported grid integration studies. SKILLS Python, MATLAB, power systems, renewable energy systems.",
        ["Renewable Energy"],
    ),
]


# Held-out queries: written separately and NEVER used to tune settings. If a setting only
# improves QUERIES but not these, it's overfitting.
HELDOUT = [
    ("I'd love to research how machine learning can predict disease outbreaks", ["Public Health", "Data Science", "Artificial Intelligence"]),
    ("wind and solar grids", ["Renewable Energy"]),
    ("I paint and want to go to art school abroad", ["Fine Arts"]),
    ("legal studies, justice and human rights advocacy", ["Law and Human Rights"]),
    ("software developer, databases and cloud", ["Software Engineering"]),
    ("midwifery", ["Nursing and Midwifery"]),
    ("genome sequencing data in R", ["Bioinformatics"]),
    ("I want to manage data teams and build dashboards for executives", ["Business Analytics"]),
    ("financial markets and economic policy", ["Finance and Economics"]),
    ("robots and manufacturing design", ["Mechanical Engineering"]),
    ("quantum physics", ["Quantum Technologies"]),
    ("coral and fisheries, marine life biotech", ["Marine Biotechnology"]),
    ("UK government scholarship for leaders", ["Chevening"]),
    ("study in Germany fully funded", ["DAAD Study Scholarships", "DAAD EPOS"]),
    ("deep lerning for computer vison", ["Artificial Intelligence PhD", "Advanced Microscopy"]),
    ("climate and sustainable power engineering", ["Renewable Energy"]),
]


@dataclass
class Scores:
    mrr: float
    hit1: float
    hit3: float
    ndcg5: float
    failures: list

    def row(self):
        return f"{self.mrr:6.3f}  {self.hit1:6.1%}  {self.hit3:6.1%}  {self.ndcg5:6.3f}"


def _relevant(title, wanted):
    return any(w.lower() in title.lower() for w in wanted)


def evaluate(rank_fn, titles_by_id, queries=QUERIES, k=5):
    """rank_fn(query) -> list of scholarship ids, best first."""
    rr, h1, h3, nd, failures = [], 0, 0, [], []
    for query, wanted in queries:
        ranked = rank_fn(query)
        flags = [_relevant(titles_by_id[i], wanted) for i in ranked]
        first = next((pos for pos, ok in enumerate(flags, start=1) if ok), None)
        rr.append(1 / first if first else 0.0)
        h1 += first == 1
        h3 += bool(first and first <= 3)
        dcg = sum(1 / math.log2(p + 1) for p, ok in enumerate(flags[:k], start=1) if ok)
        n_rel = min(k, sum(_relevant(t, wanted) for t in titles_by_id.values()))
        idcg = sum(1 / math.log2(p + 1) for p in range(1, n_rel + 1)) or 1
        nd.append(dcg / idcg)
        if first != 1:
            got = titles_by_id[ranked[0]] if ranked else "(nothing)"
            failures.append((query[:60], wanted[0], first, got[:50]))
    n = len(queries)
    return Scores(sum(rr) / n, h1 / n, h3 / n, sum(nd) / n, failures)
