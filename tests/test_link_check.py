from __future__ import annotations

import unittest
import tempfile
import json
from pathlib import Path

from jobradai.link_check import _classify_http_response, _select_jobs_for_link_check
from jobradai.snapshot import write_snapshot


class LinkCheckTests(unittest.TestCase):
    def test_classifies_direct_and_expired_links(self) -> None:
        self.assertEqual(_classify_http_response("jobs.ashbyhq.com", 200, "<html>ok</html>"), "direct_ok")
        self.assertEqual(_classify_http_response("example.com", 404, "not found"), "expired")
        self.assertEqual(_classify_http_response("example.com", 410, "gone"), "expired")

    def test_classifies_aggregators_and_antibot_as_browser_required(self) -> None:
        self.assertEqual(_classify_http_response("ie.indeed.com", 200, "<html>ok</html>"), "browser_required")
        self.assertEqual(_classify_http_response("jobs.example.com", 403, "forbidden"), "browser_required")
        self.assertEqual(_classify_http_response("jobs.example.com", 200, "Cloudflare Security Check"), "browser_required")

    def test_selection_keeps_shortlist_items_beyond_top_limit(self) -> None:
        jobs = [
            {"stable_id": "top", "url": "https://example.com/top"},
            {"stable_id": "later", "url": "https://example.com/later"},
        ]
        selected = _select_jobs_for_link_check(jobs, {"items": [{"stable_id": "later"}]}, limit=1)
        self.assertEqual([job["stable_id"] for job in selected], ["later", "top"])

    def test_selection_skips_llm_skip_even_when_job_is_top_ranked(self) -> None:
        jobs = [
            {"stable_id": "skipped-top", "url": "https://example.com/skipped"},
            {"stable_id": "actionable", "url": "https://example.com/actionable"},
            {"stable_id": "fallback", "url": "https://example.com/fallback"},
        ]
        shortlist = {
            "items": [
                {"stable_id": "skipped-top", "priority": "skip"},
                {"stable_id": "actionable", "priority": "shortlist"},
            ]
        }
        selected = _select_jobs_for_link_check(jobs, shortlist, limit=3)
        self.assertEqual([job["stable_id"] for job in selected], ["actionable", "fallback"])

    def test_write_snapshot_copies_outputs_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "latest"
            history = root / "history"
            output.mkdir()
            (output / "jobs.json").write_text(json.dumps([{"stable_id": "a"}]), encoding="utf-8")
            (output / "audit.json").write_text(json.dumps({"total_jobs": 1, "source_status": {"ok": 1, "errors": []}}), encoding="utf-8")
            manifest = write_snapshot(output_dir=output, history_dir=history, name="test snapshot")
            snapshot_dir = Path(manifest["snapshot_dir"])
            self.assertTrue((snapshot_dir / "jobs.json").exists())
            self.assertTrue((snapshot_dir / "snapshot.json").exists())
            self.assertEqual((history / "latest.txt").read_text(encoding="utf-8").strip(), "test-snapshot")


if __name__ == "__main__":
    unittest.main()
