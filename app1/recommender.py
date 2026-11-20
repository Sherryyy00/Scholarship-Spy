"""
Content-based scholarship recommender.

How it works:
1. Every scholarship's text (title, subject, degree, country, details...) is turned
   into a TF-IDF vector, using unigrams and bigrams with English stop words removed.
2. The user's personal statement (plus their saved fields of interest) is turned
   into a vector with the same vocabulary.
3. Scholarships are ranked by cosine similarity to the statement.

The fitted index is built once and cached in memory. It is rebuilt automatically
when scholarships change (see signals.py), so requests stay fast.

This replaces the old approach, which loaded a 170 MB GloVe file on every request
and then ignored the result and returned the first 20 rows.
"""

import threading
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

DEFAULT_TOP_N = 20
MIN_SCORE = 0.01  # below this, a match is essentially noise
RELATIVE_CUTOFF = 0.10  # drop results weaker than 10% of the best match

# Words that appear in almost every statement, CV or listing and say nothing about fit.
# Degree levels are handled separately (filters and the degree boost), so they're excluded here too.
DOMAIN_STOP_WORDS = {
    "example", "demo", "year", "years", "month", "months", "using", "use", "used", "want", "wants", "would",
    "like", "also", "study", "studies", "studying", "studied", "student", "students", "university",
    "universities", "college", "school", "experience", "experienced", "project", "projects", "work", "worked",
    "working", "skills", "skill", "goal", "goals", "interest", "interested", "passion", "passionate", "hope",
    "plan", "help", "make", "good", "great", "strong", "including", "level", "course", "courses", "programme",
    "programmes", "program", "programs", "degree", "degrees", "master", "masters", "bachelor", "bachelors",
    "phd", "doctorate", "undergraduate", "postgraduate", "graduate", "scholarship", "scholarships", "apply",
    "application", "applicants", "candidates", "eligible", "international", "present", "current", "currently",
    "dear", "sincerely", "hons", "first", "class", "contact", "official", "check", "details", "website",
}


@dataclass(frozen=True)
class Match:
    scholarship_id: int
    score: float
    terms: tuple = ()  # words/phrases the query and scholarship share, strongest first


# Small multiplier for scholarships at the degree level the user is likely aiming for
# (e.g. a CV showing a bachelor's degree -> Masters). Enough to break near-ties, not to override relevance.
DEGREE_BOOST = 1.15


class _Index:
    def __init__(self, ids, matrix, vectorizer, degrees):
        self.ids = ids
        self.matrix = matrix
        self.vectorizer = vectorizer
        self.degrees = degrees  # lower-cased degree text per row, for the soft boost
        self.features = vectorizer.get_feature_names_out()


_lock = threading.Lock()
_index = None


def invalidate():
    """Drop the cached index. Called whenever a scholarship is saved or deleted."""
    global _index
    with _lock:
        _index = None


def _build_index():
    from .models import Scholarship  # local import keeps this module import-safe

    rows = list(Scholarship.objects.all().only(
        "id", "title", "subject", "degree", "country",
        "university_name", "eligibility", "scholarship_details",
    ))
    if not rows:
        return None
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    vectorizer = TfidfVectorizer(
        stop_words=list(ENGLISH_STOP_WORDS | DOMAIN_STOP_WORDS),
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
        max_df=0.9 if len(rows) > 10 else 1.0,
        strip_accents="unicode",
    )
    matrix = vectorizer.fit_transform(s.search_text() for s in rows)
    return _Index([s.id for s in rows], matrix, vectorizer, [(s.degree or "").lower() for s in rows])


def _get_index():
    global _index
    with _lock:
        if _index is None:
            _index = _build_index()
        return _index


def _shared_terms(index, query_vec, row, limit=4):
    """Features present in both the query and the scholarship, ranked by their combined weight."""
    q = query_vec.tocsr()
    d = index.matrix.getrow(row)
    weights = dict(zip(d.indices, d.data))
    shared = [(q_w * weights[i], i) for i, q_w in zip(q.indices, q.data) if i in weights]
    shared.sort(reverse=True)
    terms, seen_words = [], set()
    for _, i in shared:
        term = index.features[i]
        words = set(term.split())
        if words & seen_words:  # skip "data" if "data science" is already shown
            continue
        seen_words |= words
        terms.append(term)
        if len(terms) == limit:
            break
    return tuple(terms)


def recommend(statement, extra_terms=(), top_n=DEFAULT_TOP_N, candidate_ids=None, boost_degree=""):
    """
    Return up to top_n Match objects, best first.

    statement:     the user's personal statement and/or cleaned CV text
    extra_terms:   extra keywords (e.g. the user's fields of interest)
    candidate_ids: optional set of scholarship ids to restrict results to
                   (e.g. after filtering by degree or country)
    boost_degree:  optional degree level ("Masters", "PhD"...) to gently favour
    """
    index = _get_index()
    if index is None:
        return []

    query = " ".join([statement or "", *extra_terms]).strip()
    if not query:
        return []

    query_vec = index.vectorizer.transform([query])
    if query_vec.nnz == 0:  # no overlap with the vocabulary at all
        return []

    scores = linear_kernel(query_vec, index.matrix).ravel()  # tf-idf rows are L2-normalised
    if boost_degree:
        level = boost_degree.lower().rstrip("s")[:6]  # "masters" -> "master", "phd" -> "phd"
        for i, degree in enumerate(index.degrees):
            if level and level in degree:
                scores[i] *= DEGREE_BOOST
    order = scores.argsort()[::-1]

    results = []
    best = None
    for i in order:
        score = float(scores[i])
        if score < MIN_SCORE:
            break
        sid = index.ids[i]
        if candidate_ids is not None and sid not in candidate_ids:
            continue
        best = best or score
        if score < best * RELATIVE_CUTOFF:
            break
        results.append(Match(sid, round(min(score, 1.0), 4), _shared_terms(index, query_vec, i)))
        if len(results) >= top_n:
            break
    return results
