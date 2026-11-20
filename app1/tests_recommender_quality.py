"""Guards recommender quality: fails if a change makes rankings measurably worse."""

from django.test import TestCase

from . import recommender
from .evaluation import HELDOUT, QUERIES, evaluate
from .management.commands.evaluate_recommender import load_corpus
from .models import Scholarship


class RecommenderQualityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_corpus()

    def setUp(self):
        self.rows = list(Scholarship.objects.all())
        self.titles = {r.id: r.title for r in self.rows}

    def score(self, config, queries):
        index = recommender.build_index(self.rows, config)
        return evaluate(lambda q: [m.scholarship_id for m in index.rank(q, top_n=10)], self.titles, queries)

    def test_default_meets_quality_bar(self):
        tuning = self.score(recommender.DEFAULT_CONFIG, QUERIES)
        heldout = self.score(recommender.DEFAULT_CONFIG, HELDOUT)
        self.assertGreaterEqual(tuning.mrr, 0.95, tuning.failures)
        self.assertGreaterEqual(heldout.mrr, 0.90, heldout.failures)
        self.assertEqual(heldout.hit3, 1.0, heldout.failures)

    def test_default_beats_plain_tfidf(self):
        plain = recommender.Config(expand_abbreviations=False, stem=False, char_weight=0.0)
        for queries in (QUERIES, HELDOUT):
            self.assertGreater(self.score(recommender.DEFAULT_CONFIG, queries).mrr, self.score(plain, queries).mrr)

    def test_explanations_use_real_words_not_stems(self):
        index = recommender.build_index(self.rows)
        match = index.rank("renewables engineer working on offshore wind", top_n=1)[0]
        self.assertTrue(match.terms)
        for term in match.terms:
            self.assertNotIn("engin", term.split())
            self.assertNotIn("renew", term.split())

    def test_abbreviation_expansion(self):
        self.assertIn("artificial intelligence", recommender.expand("I like AI"))
        self.assertEqual(recommender.expand("Thai food"), "Thai food")  # whole words only

    def test_typo_tolerance(self):
        index = recommender.build_index(self.rows)
        top = Scholarship.objects.get(pk=index.rank("machne lerning and statistcs", top_n=1)[0].scholarship_id)
        self.assertIn("Data Science", top.title)
