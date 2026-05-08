from __future__ import annotations

import unittest

from jobradai.models import Job
from jobradai.pipeline import _optional_reason_is_soft_skip, dedupe_jobs, run_pipeline
from jobradai.sources.optional import JOBSPY_PACKAGE


class PipelineTests(unittest.TestCase):
    def test_dedupe_prefers_ats_over_public(self) -> None:
        public = Job(
            source="Public",
            source_type="public_api",
            title="Data Engineer",
            company="Acme",
            url="https://jobs.example.com/1?utm=x",
        )
        ats = Job(
            source="ATS",
            source_type="ats",
            title="Data Engineer",
            company="Acme",
            url="https://jobs.example.com/1",
        )
        result = dedupe_jobs([public, ats])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_type, "ats")

    def test_optional_source_reason_classification(self) -> None:
        self.assertTrue(_optional_reason_is_soft_skip("missing_config: SERPAPI_KEY absent"))
        self.assertTrue(_optional_reason_is_soft_skip("service_unavailable: JobSpy API injoignable sur http://127.0.0.1:8000"))
        self.assertFalse(_optional_reason_is_soft_skip("auth_error: token France Travail absent"))
        self.assertFalse(_optional_reason_is_soft_skip("runtime_error: JobSpy direct timeout apres 900s"))
        self.assertFalse(_optional_reason_is_soft_skip("JobSpy direct sortie JSON invalide"))

    def test_jobspy_package_is_pinned(self) -> None:
        self.assertRegex(JOBSPY_PACKAGE, r"^python-jobspy==\d+\.\d+\.\d+$")

    def test_disabled_optional_sources_are_not_reported_by_default(self) -> None:
        class Config:
            profile = {}
            markets = {"markets": {"other": {}}}
            sources = {
                "run": {},
                "public_sources": {
                    "business_france_vie": False,
                    "forem": False,
                    "actiris": False,
                    "remotive": False,
                    "arbeitnow": False,
                    "remoteok": False,
                    "jobicy": False,
                    "himalayas": False,
                },
                "optional_sources": {},
                "ats_feeds": [],
            }

        result = run_pipeline(Config())
        names = [run.name for run in result.source_runs]
        self.assertNotIn("serpapi_google_jobs", names)
        self.assertNotIn("vdab_generic", names)


if __name__ == "__main__":
    unittest.main()
