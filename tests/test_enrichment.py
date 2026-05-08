from __future__ import annotations

import unittest

from jobradai.enrichment import (
    build_recruiter_message,
    effective_remote_check,
    effective_salary_check,
    infer_start_date_check,
)
from jobradai.models import Job


class EnrichmentTests(unittest.TestCase):
    def test_start_date_detects_compatible_contextual_month(self) -> None:
        job = Job(
            source="ATS",
            source_type="ats",
            title="Graduate AI Engineer",
            company="Acme",
            url="https://example.com",
            description="The cohort start date is September 2026 in Dublin.",
        ).as_dict()
        result = infer_start_date_check(job, {"constraints": {"target_start_after": "2026-08"}})
        self.assertEqual(result["check"], "compatible")
        self.assertEqual(result["evidence"], "2026-09")

    def test_start_date_detects_immediate_as_too_soon(self) -> None:
        job = Job(
            source="ATS",
            source_type="ats",
            title="Data Engineer",
            company="Acme",
            url="https://example.com",
            description="Immediate start required for this position.",
        ).as_dict()
        self.assertEqual(infer_start_date_check(job)["check"], "too_soon")

    def test_start_date_ignores_non_contextual_dates(self) -> None:
        job = Job(
            source="ATS",
            source_type="ats",
            title="Data Engineer",
            company="Acme",
            url="https://example.com",
            description="Posted in May 2026. The team builds AI platforms.",
        ).as_dict()
        self.assertEqual(infer_start_date_check(job)["check"], "unknown")

    def test_salary_and_remote_fill_unknown_from_description(self) -> None:
        job = Job(
            source="ATS",
            source_type="ats",
            title="AI Engineer",
            company="Acme",
            url="https://example.com",
            description="Salary range EUR 55,000 - 65,000. Hybrid work from home two days per week.",
        ).as_dict()
        self.assertEqual(effective_salary_check(job, {"salary_check": "unknown"}, {"constraints": {"minimum_annual_salary_eur": 45000}}), "meets_or_likely")
        self.assertEqual(effective_remote_check(job, {"remote_check": "unknown"}), "meets")

    def test_recruiter_message_mentions_soft_checks(self) -> None:
        message = build_recruiter_message(
            {
                "title": "AI Engineer",
                "company": "Acme",
                "last_start_date_check": "unknown",
                "last_salary_check": "unknown",
                "last_remote_check": "unknown",
                "last_application_angle": "Mettre en avant RAG et MLOps.",
            }
        )
        self.assertIn("aout/septembre 2026", message)
        self.assertIn("remuneration", message)
        self.assertIn("teletravail", message)


if __name__ == "__main__":
    unittest.main()
