from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jobradai.webapp import WebAuth, filter_jobs, validate_state_patch


class WebAppTests(unittest.TestCase):
    def test_filter_jobs_keeps_priority_order_and_searches_augmented_fields(self) -> None:
        jobs = [
            {"stable_id": "1", "queue_bucket": "maybe", "last_combined_score": 95, "company": "A"},
            {"stable_id": "2", "queue_bucket": "apply_now", "last_combined_score": 50, "company": "B"},
            {
                "stable_id": "3",
                "queue_bucket": "shortlist",
                "last_combined_score": 90,
                "company": "C",
                "experience_evidence": "semantic web and knowledge graph",
            },
        ]

        ordered = filter_jobs(jobs, {})
        self.assertEqual([job["stable_id"] for job in ordered], ["2", "3", "1"])
        self.assertEqual(filter_jobs(jobs, {"q": "knowledge graph"})[0]["stable_id"], "3")

    def test_validate_state_patch_rejects_unknown_enums_and_truncates_text(self) -> None:
        with self.assertRaises(ValueError):
            validate_state_patch({"application_status": "random"})

        clean = validate_state_patch({"application_status": "applied", "notes": "x" * 6000, "unknown": "ignored"})
        self.assertEqual(clean["application_status"], "applied")
        self.assertEqual(len(clean["notes"]), 5000)
        self.assertNotIn("unknown", clean)

    def test_web_auth_cookie_roundtrip_and_expiry_tamper_check(self) -> None:
        auth = WebAuth(password="secret", session_secret="s" * 32, cookie_secure=False)
        cookie = auth.issue_cookie()
        token = cookie.split(";", 1)[0].split("=", 1)[1]

        self.assertTrue(auth.check_password("secret"))
        self.assertFalse(auth.check_password("wrong"))
        self.assertTrue(auth.validate_cookie(token))
        self.assertFalse(auth.validate_cookie(token + "tampered"))

    def test_cv_metadata_can_use_runs_cv_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "runs" / "latest").mkdir(parents=True)
            (root / "runs" / "cv").mkdir(parents=True)
            (root / "config" / "sources.toml").write_text('[run]\noutput_dir = "runs/latest"\n', encoding="utf-8")
            (root / "config" / "profile.toml").write_text("[profile]\n", encoding="utf-8")
            (root / "config" / "markets.toml").write_text("[markets]\n", encoding="utf-8")
            (root / "runs" / "cv" / "main.tex").write_text("CV source", encoding="utf-8")

            from jobradai.webapp import WebDataStore

            metadata = WebDataStore(root=root).cv_metadata()
            self.assertTrue(metadata["tex_available"])
            self.assertEqual(metadata["tex_url"], "/api/cv.tex")


if __name__ == "__main__":
    unittest.main()
