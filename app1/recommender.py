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


@dataclass(frozen=True)
class Match:
    scholarship_id: int
    score: float


class _Index:
    def __init__(self, ids, matrix, vectorizer):
        self.ids = ids
        self.matrix = matrix
        self.vectorizer = vectorizer


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
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
        max_df=0.9 if len(rows) > 10 else 1.0,
        strip_accents="unicode",
    )
    matrix = vectorizer.fit_transform(s.search_text() for s in rows)
    return _Index([s.id for s in rows], matrix, vectorizer)


def _get_index():
    global _index
    with _lock:
        if _index is None:
            _index = _build_index()
        return _index


def recommend(statement, extra_terms=(), top_n=DEFAULT_TOP_N, candidate_ids=None):
    """
    Return up to top_n Match objects, best first.

    statement:     the user's personal statement
    extra_terms:   extra keywords (e.g. the user's fields of interest)
    candidate_ids: optional set of scholarship ids to restrict results to
                   (e.g. after filtering by degree or country)
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
    order = scores.argsort()[::-1]

    results = []
    for i in order:
        score = float(scores[i])
        if score < MIN_SCORE:
            break
        sid = index.ids[i]
        if candidate_ids is not None and sid not in candidate_ids:
            continue
        results.append(Match(sid, round(score, 4)))
        if len(results) >= top_n:
            break
    return results
