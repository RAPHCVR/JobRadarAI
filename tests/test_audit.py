from __future__ import annotations

import json
import os
import tempfile
import unittest

from pathlib import Path

from jobradai.audit import build_audit, write_audit
from jobradai.config import load_config
from jobradai.fingerprint import jobs_fingerprint


class AuditTests(unittest.TestCase):
    def test_build_audit_counts_remote_salary_and_priorities(self) -> None:
        config = load_config(load_env=False)
        jobs = [
            {
                "market": "france",
                "remote": False,
                "location": "Paris, Remote",
                "salary": "Annuel de 55000 Euros",
                "score_parts": {"work_mode": 95},
            },
            {
                "market": "ireland",
                "remote": False,
                "location": "Dublin",
                "salary": "",
                "title": "Graduate Data Programme",
                "description": "Graduate programme for data engineering, Python and SQL.",
                "score_parts": {"work_mode": 58},
            },
        ]
        sources = [
            {"name": "france_travail", "ok": True, "skipped": False},
            {"name": "business_france_vie", "ok": True, "skipped": False, "count": 600},
        ]
        shortlist = {
            "count": 1,
            "selection_mode": "balanced",
            "selection_summary": {"available_jobs": 2, "selected_jobs": 1, "available_vie": 0, "selected_vie": 0},
            "batches": [{}],
            "items": [{"priority": "apply_now"}],
        }
        report = build_audit(jobs, sources, shortlist, config)
        self.assertEqual(report["total_jobs"], 2)
        self.assertEqual(report["remote"]["all_with_signal"], 1)
        self.assertEqual(report["salary"]["all_meeting_minimum"], 1)
        self.assertEqual(report["llm_shortlist"]["priority_counts"]["apply_now"], 1)
        self.assertEqual(report["graduate_programs"]["target_detected"], 1)
        self.assertTrue(report["restriction"]["checks"]["min_score_large"])
        self.assertTrue(report["restriction"]["checks"]["llm_balanced_or_all"])

    def test_write_audit_ignores_stale_shortlist_older_than_jobs(self) -> None:
        config = load_config(load_env=False)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "jobs.json").write_text(json.dumps([{"market": "france", "score": 50}]), encoding="utf-8")
            (output / "sources.json").write_text(json.dumps([]), encoding="utf-8")
            (output / "llm_shortlist.json").write_text(
                json.dumps({"count": 1, "selection_mode": "balanced", "items": [{"priority": "apply_now"}]}),
                encoding="utf-8",
            )
            os.utime(output / "llm_shortlist.json", (1, 1))
            os.utime(output / "jobs.json", (2, 2))
            report = write_audit(output, config)
        self.assertFalse(report["llm_shortlist"]["available"])

    def test_write_audit_ignores_shortlist_with_wrong_fingerprint(self) -> None:
        config = load_config(load_env=False)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            jobs = [{"stable_id": "current", "market": "france", "score": 50}]
            (output / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
            (output / "sources.json").write_text(json.dumps([]), encoding="utf-8")
            (output / "llm_shortlist.json").write_text(
                json.dumps(
                    {
                        "count": 1,
                        "jobs_fingerprint": jobs_fingerprint([{"stable_id": "old", "score": 50}]),
                        "selection_mode": "balanced",
                        "selection_summary": {"available_jobs": 1},
                        "items": [{"stable_id": "old", "priority": "apply_now"}],
                    }
                ),
                encoding="utf-8",
            )
            os.utime(output / "jobs.json", (2, 2))
            os.utime(output / "llm_shortlist.json", (3, 3))
            report = write_audit(output, config)
        self.assertFalse(report["llm_shortlist"]["available"])

    def test_write_audit_accepts_shortlist_with_current_fingerprint(self) -> None:
        config = load_config(load_env=False)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            jobs = [{"stable_id": "current", "market": "france", "score": 50}]
            (output / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
            (output / "sources.json").write_text(json.dumps([]), encoding="utf-8")
            (output / "llm_shortlist.json").write_text(
                json.dumps(
                    {
                        "count": 1,
                        "jobs_fingerprint": jobs_fingerprint(jobs),
                        "selection_mode": "balanced",
                        "selection_summary": {"available_jobs": 1, "selected_jobs": 1},
                        "items": [{"stable_id": "current", "priority": "apply_now"}],
                    }
                ),
                encoding="utf-8",
            )
            report = write_audit(output, config)
        self.assertTrue(report["llm_shortlist"]["available"])

    def test_write_audit_merges_current_llm_augments(self) -> None:
        config = load_config(load_env=False)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            jobs = [
                {"stable_id": "base", "market": "france", "source": "France Travail", "score": 70},
                {"stable_id": "vie", "market": "germany", "source": "Business France VIE", "score": 70},
                {"stable_id": "extra", "market": "ireland", "source": "JobSpy Direct", "score": 70},
            ]
            (output / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
            (output / "sources.json").write_text(json.dumps([]), encoding="utf-8")
            (output / "llm_shortlist.json").write_text(
                json.dumps(
                    {
                        "count": 1,
                        "jobs_fingerprint": jobs_fingerprint(jobs),
                        "selection_mode": "wide",
                        "selection_summary": {"available_jobs": 3, "selected_jobs": 1, "available_vie": 1, "selected_vie": 0},
                        "endpoint_counts": {"responses": 1},
                        "fallback_items": 0,
                        "fallback_batches": 0,
                        "batches": [{"ids": ["base"]}],
                        "items": [{"stable_id": "base", "priority": "apply_now"}],
                    }
                ),
                encoding="utf-8",
            )
            augment_dir = output / "llm_augments"
            augment_dir.mkdir()
            (augment_dir / "targeted.json").write_text(
                json.dumps(
                    {
                        "endpoint_counts": {"responses_sdk": 2},
                        "fallback_items": 1,
                        "fallback_batches": 1,
                        "quality": {"fallback_errors": ["schema_retry"]},
                        "batches": [{"ids": ["vie"]}, {"ids": ["extra"]}],
                        "items": [
                            {"stable_id": "vie", "priority": "shortlist"},
                            {"stable_id": "extra", "priority": "skip"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = write_audit(output, config)
        llm = report["llm_shortlist"]
        self.assertEqual(llm["count"], 3)
        self.assertEqual(llm["batch_count"], 3)
        self.assertEqual(llm["fallback_items"], 1)
        self.assertAlmostEqual(llm["fallback_ratio"], 1 / 3)
        self.assertEqual(llm["endpoint_counts"], {"responses": 1, "responses_sdk": 2})
        self.assertEqual(llm["priority_counts"], {"apply_now": 1, "shortlist": 1, "skip": 1})
        self.assertEqual(llm["selection_summary"]["selected_jobs"], 3)
        self.assertEqual(llm["selection_summary"]["selected_vie"], 1)
        self.assertEqual(report["restriction"]["llm_selected_vie"], 1)

    def test_empty_corpus_is_p0_not_false_ok(self) -> None:
        config = load_config(load_env=False)
        report = build_audit([], [], {}, config)
        p0_items = [item["item"] for item in report["p_items"] if item["priority"] == "P0"]
        self.assertTrue(any("Corpus vide" in item for item in p0_items))
        self.assertFalse(any("Aucun blocage runtime" in item for item in p0_items))

    def test_missing_sources_file_is_p1(self) -> None:
        config = load_config(load_env=False)
        jobs = [{"market": "france", "score": 50}]
        report = build_audit(jobs, [], {}, config)
        p1_items = [item["item"] for item in report["p_items"] if item["priority"] == "P1"]
        self.assertTrue(any("sources.json absent ou illisible" in item for item in p1_items))

    def test_vdab_and_serpapi_skips_are_pn_not_action_items(self) -> None:
        config = load_config(load_env=False)
        jobs = [{"market": "belgium", "score": 50}]
        sources = [
            {"name": "business_france_vie", "ok": True, "skipped": False, "count": 600},
            {"name": "forem", "ok": True, "skipped": False, "count": 20},
            {"name": "actiris", "ok": True, "skipped": False, "count": 50},
            {"name": "vdab_generic", "ok": True, "skipped": True, "reason": "desactive"},
            {"name": "serpapi_google_jobs", "ok": True, "skipped": True, "reason": "desactive"},
        ]
        report = build_audit(jobs, sources, {"count": 1, "selection_mode": "balanced", "items": []}, config)
        pn_items = [item["item"] for item in report["p_items"] if item["priority"] == "PN"]
        self.assertTrue(any("VDAB direct est mis de cote" in item for item in pn_items))
        self.assertTrue(any("SerpAPI Google Jobs est mis de cote" in item for item in pn_items))
        self.assertFalse(
            any(item["priority"] in {"P2", "P3"} and ("VDAB" in item["item"] or "SerpAPI" in item["item"]) for item in report["p_items"])
        )


if __name__ == "__main__":
    unittest.main()
