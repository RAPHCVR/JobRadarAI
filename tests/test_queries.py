from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
