"""
Content-based scholarship recommender.

How it works:
1. Text is normalised: common abbreviations are expanded ("AI" -> "artificial
   intelligence") and, optionally, words are reduced to their stem so
   "engineer", "engineers" and "engineering" match.
2. Every scholarship (title and subject weighted double, plus degree, country,
   university, eligibility and description) becomes a TF-IDF vector of words
   and word pairs, with English and domain-specific filler words removed.
3. Optionally a second TF-IDF over character n-grams is blended in, which
   tolerates typos ("machne lerning") and partial words.
4. The statement/CV (plus saved interests) is vectorised the same way and
   scholarships are ranked by cosine similarity.

Which of these options are switched on is decided by measurement, not guesswork:
see evaluation.py and `python manage.py evaluate_recommender`.

The fitted index is built once and cached in memory, and rebuilt automatically
when scholarships change (see signals.py), so requests stay fast.
"""

import re
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

DEFAULT_TOP_N = 20
MIN_SCORE = 0.01  # below this, a match is essentially noise
RELATIVE_CUTOFF = 0.10  # drop results weaker than 10% of the best match

# Small multiplier for scholarships at the degree level the user is likely aiming for
# (e.g. a CV showing a bachelor's degree -> Masters). Enough to break near-ties, not to override relevance.
DEGREE_BOOST = 1.15

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
STOP_WORDS = ENGLISH_STOP_WORDS | DOMAIN_STOP_WORDS

# Abbreviations and informal words people use in statements, mapped to the words listings use.
# Only unambiguous ones: e.g. "LLM" is left out (a law degree or a large language model).
ABBREVIATIONS = {
    "ai": "artificial intelligence", "ml": "machine learning", "dl": "deep learning",
    "nlp": "natural language processing", "cs": "computer science", "comp sci": "computer science",
    "bi": "business intelligence", "mba": "business administration", "stats": "statistics",
    "econ": "economics", "econs": "economics", "maths": "mathematics", "math": "mathematics",
    "mech": "mechanical", "renewables": "renewable energy", "pv": "solar", "biotech": "biotechnology",
    "bioinfo": "bioinformatics", "ir": "international relations", "pr": "public relations",
    "ux": "user experience design", "nhs": "health", "fintech": "finance technology",
}
_ABBREV_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, ABBREVIATIONS), key=len, reverse=True)) + r")\b", re.I)
_TOKEN_RE = re.compile(r"(?u)\b[a-z][a-z]+\b")


@dataclass(frozen=True)
class Config:
    expand_abbreviations: bool = True
    stem: bool = True
    char_weight: float = 0.3  # share of the score from character n-grams (0 = words only)


# Chosen by `manage.py evaluate_recommender` (Nov 2026, 21-listing corpus):
#                         tuning MRR   held-out MRR
#   words only (old)        0.750         0.802
#   abbrev + stem           0.893         0.938
#   abbrev + stem + char.3  0.982         0.938   <- default: fixes typos without hurting unseen queries
#   abbrev + stem + char.5  1.000         0.938   (no held-out gain; likely overfitting the tuning set)
DEFAULT_CONFIG = Config()


@dataclass(frozen=True)
class Match:
    scholarship_id: int
    score: float
    terms: tuple = ()  # words/phrases the query and scholarship share, strongest first


# ---------------------------------------------------------------- text processing

def expand(text):
    return _ABBREV_RE.sub(lambda m: f"{m.group(0)} {ABBREVIATIONS[m.group(0).lower()]}", text)


class _Analyzer:
    """Tokenise -> drop stop words -> (optionally) stem -> unigrams + bigrams.

    Remembers the most common original word for each stem, so explanations
    can say "engineering" rather than "engin".
    """

    def __init__(self, config):
        self.config = config
        self.surface = defaultdict(Counter)
        if config.stem:
            import snowballstemmer

            self._stem = snowballstemmer.stemmer("english").stemWord
        else:
            self._stem = None

    def tokens(self, text):
        out = []
        for word in _TOKEN_RE.findall(text.lower()):
            if word in STOP_WORDS:
                continue
            token = self._stem(word) if self._stem else word
            self.surface[token][word] += 1
            out.append(token)
        return out

    def __call__(self, text):
        if self.config.expand_abbreviations:
            text = expand(text)
        toks = self.tokens(text)
        return toks + [f"{a} {b}" for a, b in zip(toks, toks[1:])]

    def readable(self, term):
        return " ".join(self.surface[t].most_common(1)[0][0] if self.surface.get(t) else t for t in term.split())


# ---------------------------------------------------------------- index

class Index:
    def __init__(self, ids, texts, degrees, config=DEFAULT_CONFIG):
        self.ids = list(ids)
        self.config = config
        self.degrees = degrees  # lower-cased degree text per row, for the soft boost
        n = len(self.ids)
        self.analyzer = _Analyzer(config)
        self.word_vec = TfidfVectorizer(analyzer=self.analyzer, sublinear_tf=True, min_df=1, max_df=0.9 if n > 10 else 1.0)
        self.word_matrix = self.word_vec.fit_transform(texts)
        self.features = self.word_vec.get_feature_names_out()
        self.char_vec = self.char_matrix = None
        if config.char_weight > 0:
            self.char_vec = TfidfVectorizer(
                analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1,
                preprocessor=lambda t: (expand(t) if config.expand_abbreviations else t).lower(),
            )
            self.char_matrix = self.char_vec.fit_transform(texts)

    def scores(self, query):
        """(similarity per row, query word vector). Rows are L2-normalised, so the dot product is cosine."""
        q_word = self.word_vec.transform([query])
        sims = linear_kernel(q_word, self.word_matrix).ravel()
        if self.char_vec is not None:
            w = self.config.char_weight
            char_sims = linear_kernel(self.char_vec.transform([query]), self.char_matrix).ravel()
            sims = (1 - w) * sims + w * char_sims
        return sims, q_word

    def shared_terms(self, q_word, row, limit=4):
        """Features present in both the query and the scholarship, ranked by their combined weight."""
        q = q_word.tocsr()
        d = self.word_matrix.getrow(row)
        weights = dict(zip(d.indices, d.data))
        shared = sorted(((q_w * weights[i], i) for i, q_w in zip(q.indices, q.data) if i in weights), reverse=True)
        terms, seen = [], set()
        for _, i in shared:
            term = self.analyzer.readable(self.features[i])
            words = set(term.split())
            if words & seen:  # skip "data" if "data science" is already shown
                continue
            seen |= words
            terms.append(term)
            if len(terms) == limit:
                break
        return tuple(terms)

    def rank(self, query, top_n=DEFAULT_TOP_N, candidate_ids=None, boost_degree=""):
        if not query.strip():
            return []
        sims, q_word = self.scores(query)
        if q_word.nnz == 0 and self.char_vec is None:
            return []
        if boost_degree:
            level = boost_degree.lower().rstrip("s")[:6]  # "masters" -> "master", "phd" -> "phd"
            for i, degree in enumerate(self.degrees):
                if level and level in degree:
                    sims[i] *= DEGREE_BOOST
        results, best = [], None
        for i in sims.argsort()[::-1]:
            score = float(sims[i])
            if score < MIN_SCORE:
                break
            sid = self.ids[i]
            if candidate_ids is not None and sid not in candidate_ids:
                continue
            best = best or score
            if score < best * RELATIVE_CUTOFF:
                break
            results.append(Match(sid, round(min(score, 1.0), 4), self.shared_terms(q_word, i)))
            if len(results) >= top_n:
                break
        return results


def build_index(rows, config=DEFAULT_CONFIG):
    """rows: Scholarship objects (anything with id, search_text() and degree)."""
    rows = list(rows)
    if not rows:
        return None
    return Index([r.id for r in rows], [r.search_text() for r in rows], [(r.degree or "").lower() for r in rows], config)


# ---------------------------------------------------------------- cached production index

_lock = threading.Lock()
_index = None


def invalidate():
    """Drop the cached index. Called whenever a scholarship is saved or deleted."""
    global _index
    with _lock:
        _index = None


def _get_index():
    global _index
    with _lock:
        if _index is None:
            from .models import Scholarship  # local import keeps this module import-safe

            _index = build_index(Scholarship.objects.all().only(
                "id", "title", "subject", "degree", "country",
                "university_name", "eligibility", "scholarship_details",
            ))
        return _index


def recommend(statement, extra_terms=(), top_n=DEFAULT_TOP_N, candidate_ids=None, boost_degree=""):
    """
    Return up to top_n Match objects, best first.

    statement:     the user's personal statement and/or cleaned CV text
    extra_terms:   extra keywords (e.g. the user's fields of interest)
    candidate_ids: optional set of scholarship ids to restrict results to
    boost_degree:  optional degree level ("Masters", "PhD"...) to gently favour
    """
    index = _get_index()
    if index is None:
        return []
    query = " ".join([statement or "", *extra_terms]).strip()
    return index.rank(query, top_n=top_n, candidate_ids=candidate_ids, boost_degree=boost_degree)
