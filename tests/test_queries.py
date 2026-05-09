from __future__ import annotations

import unittest

from jobradai.config import load_config
from jobradai.queries import select_query_items, select_query_terms


class QuerySelectionTests(unittest.TestCase):
    def test_limited_selection_keeps_minimum_early_career_queries(self) -> None:
        config = {
            "queries": [
                {"term": "LLM Engineer", "priority": 10},
                {"term": "Applied AI Engineer", "priority": 10},
                {"term": "GenAI Engineer", "priority": 10},
                {"term": "Data Engineer", "priority": 9},
                {"term": "MLOps Engineer", "priority": 9},
                {"term": "Graduate Data Engineer", "priority": 8, "category": "early_career"},
                {"term": "New Grad Software Engineer", "priority": 8, "category": "early_career"},
            ]
        }
        selected = select_query_terms(config, limit=5, early_career_min=2)
        self.assertEqual(len(selected), 5)
        self.assertIn("Graduate Data Engineer", selected)
        self.assertIn("New Grad Software Engineer", selected)
        self.assertIn("LLM Engineer", selected)

    def test_public_items_do_not_expose_internal_index(self) -> None:
        config = {"queries": [{"term": "Campus Data Engineer", "priority": 7}]}
        [item] = select_query_items(config, limit=1, early_career_min=1)
        self.assertNotIn("_index", item)
        self.assertEqual(item["category"], "early_career")

    def test_doctoral_queries_are_kept_as_early_specialty(self) -> None:
        config = {
            "queries": [
                {"term": "LLM Engineer", "priority": 10},
                {"term": "Applied AI Engineer", "priority": 10},
                {"term": "Data Engineer", "priority": 9},
                {"term": "CIFRE IA", "priority": 7},
            ]
        }
        selected = select_query_items(config, limit=3, early_career_min=1)
        terms = [item["term"] for item in selected]
        self.assertIn("CIFRE IA", terms)
        doctoral = next(item for item in selected if item["term"] == "CIFRE IA")
        self.assertEqual(doctoral["category"], "research_doctoral")

    def test_real_config_includes_p2_variants_in_routine_wide_selection(self) -> None:
        config = load_config(load_env=False).sources
        selected = select_query_terms(config, limit=24, early_career_min=5)
        for term in [
            "ML Engineer",
            "AI Research Engineer",
            "AI/ML Engineer",
            "ML Ops Engineer",
            "LLM Application Engineer",
        ]:
            self.assertIn(term, selected)

    def test_real_config_keeps_low_volume_niche_watch_terms_available(self) -> None:
        config = load_config(load_env=False).sources
        selected = select_query_items(config)
        by_term = {item["term"]: item for item in selected}
        for term in [
            "Applied Scientist",
            "Interpretability Engineer",
            "Explainability Engineer",
            "AI Safety Engineer",
            "Knowledge Graph Engineer",
            "Semantic Web Engineer",
        ]:
            self.assertEqual(by_term[term]["category"], "niche_watch")


if __name__ == "__main__":
    unittest.main()
