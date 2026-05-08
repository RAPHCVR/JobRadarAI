from __future__ import annotations

import unittest

from jobradai.early_career import early_career_score, early_career_signal


class EarlyCareerTests(unittest.TestCase):
    def test_structured_graduate_data_program_is_high_fit(self) -> None:
        job = {
            "title": "Graduate Data Programme",
            "description": "Two year graduate programme for data engineering, Python, SQL and machine learning.",
        }
        signal = early_career_signal(job)
        self.assertTrue(signal["is_early_career"])
        self.assertTrue(signal["structured_program"])
        self.assertEqual(signal["early_career_fit"], "high")
        score, reason = early_career_score(job)
        self.assertGreater(score, 80)
        self.assertIn("compatible", reason)

    def test_business_graduate_program_is_low_fit(self) -> None:
        job = {
            "title": "Finance Graduate Scheme",
            "description": "Rotations across audit, tax, sales and business development.",
        }
        signal = early_career_signal(job)
        self.assertEqual(signal["early_career_fit"], "low")
        self.assertTrue(signal["risks"])

    def test_regular_senior_role_has_no_early_signal(self) -> None:
        job = {"title": "Senior Data Engineer", "description": "Python SQL Spark platform."}
        signal = early_career_signal(job)
        self.assertFalse(signal["is_early_career"])
        self.assertEqual(signal["early_career_fit"], "none")


if __name__ == "__main__":
    unittest.main()
