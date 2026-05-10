from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from jobradai.history import sync_history
from jobradai.models import Job


class HistoryTests(unittest.TestCase):
    def test_sync_history_carries_forward_previous_relevant_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            first = Job(
                source="ATS",
                source_type="ats",
                title="Applied AI Engineer",
                company="Acme",
                url="https://jobs.example.com/acme-ai",
                market="ireland",
                score=82,
            ).as_dict()
            second = Job(
                source="ATS",
                source_type="ats",
                title="Data Engineer",
                company="Beta",
                url="https://jobs.example.com/beta-data",
                market="france",
                score=78,
            ).as_dict()
            self._write_run(output, [first, second], shortlist_items=[{"stable_id": first["stable_id"], "priority": "apply_now", "combined_score": 91}])
            initial = sync_history(output_dir=output, history_db=history_db, run_name="run-1", recheck_stale_limit=0)
            self.assertEqual(initial["current_jobs"], 2)
            self.assertEqual(initial["new_jobs"], 2)
            self.assertEqual(initial["queue_priority_counts"]["apply_now"], 1)
            self.assertTrue((output / "application_messages.md").exists())
            self.assertTrue((output / "history_dashboard.md").exists())
            self.assertTrue((output / "weekly_digest.md").exists())

            self._write_run(output, [second], shortlist_items=[])
            followup = sync_history(output_dir=output, history_db=history_db, run_name="run-2", recheck_stale_limit=0)
            self.assertEqual(followup["current_jobs"], 1)
            self.assertEqual(followup["missing_this_run"], 1)
            carried = [item for item in followup["items"] if item["stable_id"] == first["stable_id"]][0]
            self.assertEqual(carried["presence_status"], "stale")
            self.assertEqual(carried["queue_bucket"], "apply_now")

    def test_sync_history_marks_missing_relevant_job_expired_after_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            job = Job(
                source="ATS",
                source_type="ats",
                title="ML Engineer",
                company="Gone",
                url="https://jobs.example.com/gone",
                market="uk",
                score=88,
            ).as_dict()
            self._write_run(output, [job], shortlist_items=[{"stable_id": job["stable_id"], "priority": "shortlist"}])
            sync_history(output_dir=output, history_db=history_db, run_name="run-1", recheck_stale_limit=0)
            self._write_run(output, [], shortlist_items=[])
            with closing(sqlite3.connect(history_db)) as conn:
                conn.execute(
                    "UPDATE job_history SET last_link_status = 'expired', presence_status = 'active' WHERE stable_id = ?",
                    (job["stable_id"],),
                )
                conn.commit()
            result = sync_history(output_dir=output, history_db=history_db, run_name="run-2", recheck_stale_limit=0)
            self.assertFalse(any(item["stable_id"] == job["stable_id"] for item in result["items"]))
            with closing(sqlite3.connect(history_db)) as conn:
                status = conn.execute(
                    "SELECT presence_status FROM job_history WHERE stable_id = ?",
                    (job["stable_id"],),
                ).fetchone()[0]
            self.assertEqual(status, "expired")

    def test_sync_history_is_idempotent_for_same_run_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            job = Job(
                source="ATS",
                source_type="ats",
                title="Data Engineer",
                company="Acme",
                url="https://jobs.example.com/data",
                market="france",
                score=81,
            ).as_dict()
            self._write_run(output, [job], shortlist_items=[{"stable_id": job["stable_id"], "priority": "shortlist"}])
            first = sync_history(output_dir=output, history_db=history_db, run_name="same-run", recheck_stale_limit=0)
            second = sync_history(output_dir=output, history_db=history_db, run_name="same-run", recheck_stale_limit=0)
            self.assertEqual(first["new_jobs"], 1)
            self.assertEqual(second["new_jobs"], 1)
            with closing(sqlite3.connect(history_db)) as conn:
                seen_count = conn.execute(
                    "SELECT seen_count FROM job_history WHERE stable_id = ?",
                    (job["stable_id"],),
                ).fetchone()[0]
            self.assertEqual(seen_count, 1)

    def test_sync_history_adds_start_date_and_recruiter_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            job = Job(
                source="ATS",
                source_type="ats",
                title="Graduate AI Engineer",
                company="Acme",
                url="https://jobs.example.com/graduate-ai",
                market="ireland",
                description="The programme start date is September 2026. Salary EUR 55,000. Hybrid remote.",
                score=85,
            ).as_dict()
            self._write_run(
                output,
                [job],
                shortlist_items=[
                    {
                        "stable_id": job["stable_id"],
                        "priority": "apply_now",
                        "combined_score": 90,
                        "salary_check": "unknown",
                        "remote_check": "unknown",
                    }
                ],
            )
            result = sync_history(
                output_dir=output,
                history_db=history_db,
                run_name="run-1",
                recheck_stale_limit=0,
                profile={"constraints": {"target_start_after": "2026-08", "minimum_annual_salary_eur": 45000}},
            )
            [item] = result["items"]
            self.assertEqual(item["last_start_date_check"], "compatible")
            self.assertEqual(item["last_salary_check"], "meets_or_likely")
            self.assertEqual(item["last_remote_check"], "meets")
            self.assertIn("aout/septembre 2026", item["last_recruiter_message"])
            queue_md = (output / "application_queue.md").read_text(encoding="utf-8")
            messages_md = (output / "application_messages.md").read_text(encoding="utf-8")
            self.assertNotIn("n/ay", queue_md)
            self.assertNotIn("n/ay", messages_md)
            self.assertIn("exp `unknown`/n/a |", queue_md)

    def test_sync_history_ranks_queue_by_combined_score_within_priority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            local_high = Job(
                source="ATS",
                source_type="ats",
                title="Data Platform Engineer",
                company="Local High",
                url="https://jobs.example.com/local-high",
                market="france",
                score=95,
            ).as_dict()
            llm_high = Job(
                source="ATS",
                source_type="ats",
                title="Applied AI Engineer",
                company="LLM High",
                url="https://jobs.example.com/llm-high",
                market="ireland",
                score=50,
            ).as_dict()
            self._write_run(
                output,
                [local_high, llm_high],
                shortlist_items=[
                    {"stable_id": local_high["stable_id"], "priority": "shortlist", "combined_score": 60},
                    {"stable_id": llm_high["stable_id"], "priority": "shortlist", "combined_score": 90},
                ],
            )
            result = sync_history(output_dir=output, history_db=history_db, run_name="run-1", recheck_stale_limit=0)
            self.assertEqual(result["items"][0]["stable_id"], llm_high["stable_id"])
            self.assertEqual(result["items"][0]["ranking_score"], 90)

    def test_sync_history_excludes_too_senior_items_from_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            job = Job(
                source="ATS",
                source_type="ats",
                title="Senior AI Engineer",
                company="Acme",
                url="https://jobs.example.com/senior-ai",
                market="france",
                score=82,
            ).as_dict()
            self._write_run(
                output,
                [job],
                shortlist_items=[
                    {
                        "stable_id": job["stable_id"],
                        "priority": "shortlist",
                        "level_fit": "too_senior",
                        "combined_score": 85,
                    }
                ],
            )
            result = sync_history(output_dir=output, history_db=history_db, run_name="run-1", recheck_stale_limit=0)
            self.assertFalse(any(item["stable_id"] == job["stable_id"] for item in result["items"]))

    def test_sync_history_excludes_deterministic_too_senior_items_from_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            job = Job(
                source="ATS",
                source_type="ats",
                title="Applied AI Engineer",
                company="Acme",
                url="https://jobs.example.com/applied-ai",
                market="france",
                score=86,
                required_years=7,
                experience_check="too_senior",
                experience_evidence="7 years of professional experience",
            ).as_dict()
            self._write_run(
                output,
                [job],
                shortlist_items=[
                    {
                        "stable_id": job["stable_id"],
                        "priority": "shortlist",
                        "level_fit": "stretch",
                        "combined_score": 88,
                    }
                ],
            )
            result = sync_history(output_dir=output, history_db=history_db, run_name="run-1", recheck_stale_limit=0)
            self.assertFalse(any(item["stable_id"] == job["stable_id"] for item in result["items"]))

    def test_sync_history_keeps_stretch_items_with_moderate_required_years(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            job = Job(
                source="ATS",
                source_type="ats",
                title="Data Engineer II",
                company="Acme",
                url="https://jobs.example.com/data-ii",
                market="france",
                score=80,
                required_years=3,
                experience_check="stretch",
                experience_evidence="3 years experience",
            ).as_dict()
            self._write_run(
                output,
                [job],
                shortlist_items=[
                    {
                        "stable_id": job["stable_id"],
                        "priority": "shortlist",
                        "level_fit": "stretch",
                        "combined_score": 82,
                    }
                ],
            )
            result = sync_history(output_dir=output, history_db=history_db, run_name="run-1", recheck_stale_limit=0)
            self.assertTrue(any(item["stable_id"] == job["stable_id"] for item in result["items"]))

    def test_sync_history_keeps_too_senior_when_llm_marks_junior_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            job = Job(
                source="ATS",
                source_type="ats",
                title="AI Engineer All Levels",
                company="Acme",
                url="https://jobs.example.com/ai-all-levels",
                market="france",
                score=84,
                required_years=5,
                experience_check="too_senior",
                experience_evidence="5 years experience",
            ).as_dict()
            self._write_run(
                output,
                [job],
                shortlist_items=[
                    {
                        "stable_id": job["stable_id"],
                        "priority": "shortlist",
                        "level_fit": "junior_ok",
                        "combined_score": 86,
                    }
                ],
            )
            result = sync_history(output_dir=output, history_db=history_db, run_name="run-1", recheck_stale_limit=0)
            self.assertTrue(any(item["stable_id"] == job["stable_id"] for item in result["items"]))

    def test_sync_history_writes_dedicated_vie_priority_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            output.mkdir()
            history_db = root / "history" / "job_history.sqlite"
            judged_vie = Job(
                source="Business France VIE",
                source_type="official_api",
                title="Data Analyst - Strategic Partnerships",
                company="Flash",
                url="https://mon-vie-via.businessfrance.fr/offres/data-analyst",
                market="spain",
                location="Barcelone",
                salary="Indemnite VIE mensuelle 2676.00 EUR",
                employment_type="VIE 12 mois",
                score=54,
            ).as_dict()
            unjudged_vie = Job(
                source="Business France VIE",
                source_type="official_api",
                title="Data Management & Analytical Method Lifecycle",
                company="Baxter",
                url="https://mon-vie-via.businessfrance.fr/offres/data-management",
                market="belgium",
                location="Belgique",
                salary="Indemnite VIE mensuelle 2955.00 EUR",
                employment_type="VIE 12 mois",
                description="Data management, analytical method lifecycle and automation tooling.",
                score=48,
            ).as_dict()
            self._write_run(
                output,
                [judged_vie, unjudged_vie],
                shortlist_items=[
                    {
                        "stable_id": judged_vie["stable_id"],
                        "priority": "shortlist",
                        "combined_score": 72,
                        "level_fit": "junior_ok",
                    }
                ],
            )
            result = sync_history(output_dir=output, history_db=history_db, run_name="run-1", recheck_stale_limit=0)
            self.assertEqual(result["vie_queue_count"], 2)
            buckets = {item["stable_id"]: item["vie_bucket"] for item in result["vie_items"]}
            self.assertEqual(buckets[judged_vie["stable_id"]], "shortlist")
            self.assertEqual(buckets[unjudged_vie["stable_id"]], "unjudged_technical")
            self.assertTrue((output / "vie_priority_queue.md").exists())
            vie_md = (output / "vie_priority_queue.md").read_text(encoding="utf-8")
            self.assertIn("Data Analyst - Strategic Partnerships", vie_md)
            self.assertIn("Data Management & Analytical Method Lifecycle", vie_md)

    def _write_run(self, output: Path, jobs: list[dict], shortlist_items: list[dict]) -> None:
        (output / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
        (output / "llm_shortlist.json").write_text(
            json.dumps({"items": shortlist_items, "count": len(shortlist_items), "selection_mode": "balanced"}, ensure_ascii=False),
            encoding="utf-8",
        )
        link_items = [
            {
                "stable_id": job["stable_id"],
                "status": "direct_ok",
                "http_status": 200,
                "reason": "Lien direct accessible cote serveur.",
            }
            for job in jobs
        ]
        (output / "link_checks.json").write_text(json.dumps({"items": link_items}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
