"""
Measure recommender quality on a labelled set of queries (see app1/evaluation.py).

    python manage.py evaluate_recommender            # compare configurations
    python manage.py evaluate_recommender --failures # also list queries the default gets wrong

Runs on an in-memory copy of the evaluation corpus, so it never touches your data.
"""

from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.test.utils import setup_test_environment

from app1 import recommender
from app1.evaluation import HELDOUT, QUERIES, evaluate

VARIANTS = [
    ("baseline: words only", recommender.Config(expand_abbreviations=False, stem=False, char_weight=0.0)),
    ("+ abbreviations", recommender.Config(expand_abbreviations=True, stem=False, char_weight=0.0)),
    ("+ stemming", recommender.Config(expand_abbreviations=False, stem=True, char_weight=0.0)),
    ("+ char n-grams 0.3", recommender.Config(expand_abbreviations=False, stem=False, char_weight=0.3)),
    ("abbrev + stem", recommender.Config(expand_abbreviations=True, stem=True, char_weight=0.0)),
    ("abbrev + stem + char 0.2", recommender.Config(expand_abbreviations=True, stem=True, char_weight=0.2)),
    ("abbrev + stem + char 0.3", recommender.Config(expand_abbreviations=True, stem=True, char_weight=0.3)),
    ("abbrev + stem + char 0.5", recommender.Config(expand_abbreviations=True, stem=True, char_weight=0.5)),
]


def load_corpus():
    """The evaluation corpus: demo CSV + curated official programmes + Erasmus Mundus RSS sample."""
    from app1.ingest import run_scraper
    from app1.scrapers.curated import CuratedOfficialScraper
    from app1.scrapers.erasmus_mundus import ErasmusMundusRSSScraper

    call_command("updatemodel", "Dataset/sample_scholarships.csv", verbosity=0)
    run_scraper(CuratedOfficialScraper(delay=0))
    rss = ErasmusMundusRSSScraper(delay=0)
    sample = (Path(__file__).resolve().parents[2] / "tests_data" / "erasmus_mundus_rss.xml").read_text(encoding="utf-8")
    with mock.patch.object(rss, "fetch", return_value=sample):
        run_scraper(rss)


class Command(BaseCommand):
    help = "Evaluate the recommender on labelled queries and compare configurations."

    def add_arguments(self, parser):
        parser.add_argument("--failures", action="store_true", help="List queries the default config ranks wrongly")

    def handle(self, *args, failures=False, **options):
        from app1.models import Scholarship

        setup_test_environment()
        old_name = connection.creation.create_test_db(verbosity=0, autoclobber=True)
        try:
            load_corpus()
            rows = list(Scholarship.objects.all())
            titles = {r.id: r.title for r in rows}
            self.stdout.write(f"Corpus: {len(rows)} scholarships\n")
            for label, queries in ((f"Tuning set ({len(QUERIES)} queries)", QUERIES),
                                   (f"Held-out set ({len(HELDOUT)} queries, never tuned on)", HELDOUT)):
                self.stdout.write(f"\n{label}")
                self.stdout.write(f"{'configuration':30} {'MRR':>6}  {'Hit@1':>6}  {'Hit@3':>6}  {'nDCG@5':>6}")
                for name, config in VARIANTS + [("DEFAULT (production)", recommender.DEFAULT_CONFIG)]:
                    index = recommender.build_index(rows, config)
                    scores = evaluate(lambda q: [m.scholarship_id for m in index.rank(q, top_n=10)], titles, queries)
                    self.stdout.write(f"{name:30} {scores.row()}")
            if failures:
                index = recommender.build_index(rows, recommender.DEFAULT_CONFIG)
                scores = evaluate(lambda q: [m.scholarship_id for m in index.rank(q, top_n=10)], titles, QUERIES + HELDOUT)
                self.stdout.write("\nQueries where the right answer wasn't first (default config, both sets):")
                for query, wanted, pos, got in scores.failures:
                    self.stdout.write(f"  - {query!r}: wanted {wanted!r} at #{pos or '-'}, got {got!r}")
        finally:
            connection.creation.destroy_test_db(old_name, verbosity=0)
