from __future__ import annotations

import unittest

from jobradai.enrichment import (
    build_recruiter_message,
    effective_remote_check,
    effective_salary_check,
    infer_language_check,
    infer_remote_location_validity,
    infer_start_date_check,
    populate_structured_job_fields,
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

    def test_language_and_remote_location_signals_are_soft_structured_fields(self) -> None:
        local_language = Job(
            source="ATS",
            source_type="ats",
            title="Data Engineer",
            company="Acme",
            url="https://example.com",
            description="German fluent required. Remote US only roles are not supported.",
        ).as_dict()
        self.assertEqual(infer_language_check(local_language), "local_language_required")
        self.assertEqual(infer_remote_location_validity(local_language), "incompatible")

    def test_remote_location_uses_profile_locations_before_market_scoring(self) -> None:
        job = Job(
            source="JobSpy",
            source_type="scraper_api",
            title="AI Engineer",
            company="Acme",
            url="https://example.com",
            location="Warsaw",
            description="AI platform team.",
        ).as_dict()
        profile = {
            "search": {"primary_locations": ["Warsaw"], "target_markets": ["poland"]},
            "personal": {"major_cities": ["Prague"]},
        }
        self.assertEqual(infer_remote_location_validity(job, profile), "compatible")

    def test_remote_location_rejects_us_only_before_anywhere_signal(self) -> None:
        job = Job(
            source="Remote Board",
            source_type="public_api",
            title="LLM Engineer",
            company="Acme",
            url="https://example.com",
            description="Work remotely from anywhere in the United States.",
            remote=True,
        ).as_dict()
        self.assertEqual(infer_remote_location_validity(job), "incompatible")

    def test_populate_structured_job_fields_adds_salary_language_and_remote_validity(self) -> None:
        job = Job(
            source="SwissDevJobs",
            source_type="public_api",
            title="Data Engineer",
            company="Acme",
            url="https://example.com",
            location="Zurich, Switzerland",
            country="Switzerland",
            salary="CHF 80'000 - 110'000 per year",
            description="Working English required. Hybrid work. Minimum of 3 years experience with Python.",
        )
        [enriched] = populate_structured_job_fields([job], {"search": {"target_markets": ["switzerland"]}})
        self.assertEqual(enriched.salary_currency, "CHF")
        self.assertEqual(enriched.salary_normalized_annual_eur, 113300)
        self.assertEqual(enriched.language_check, "english_ok")
        self.assertEqual(enriched.remote_location_validity, "compatible")
        self.assertEqual(enriched.required_years, 3)
        self.assertEqual(enriched.experience_check, "stretch")
        self.assertIn("3 years experience", enriched.experience_evidence)

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
