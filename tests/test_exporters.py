from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jobradai.exporters import _csv_cell, _safe_url, export_all
from jobradai.models import Job


class ExporterSecurityTests(unittest.TestCase):
    def test_csv_cell_neutralizes_formula_prefixes(self) -> None:
        self.assertEqual(_csv_cell("=cmd|' /C calc'!A0"), "'=cmd|' /C calc'!A0")
        self.assertEqual(_csv_cell("+SUM(A1:A2)"), "'+SUM(A1:A2)")
        self.assertEqual(_csv_cell("@HYPERLINK"), "'@HYPERLINK")
        self.assertEqual(_csv_cell("normal text"), "normal text")

    def test_safe_url_allows_only_http_urls(self) -> None:
        self.assertEqual(_safe_url("https://example.com/job"), "https://example.com/job")
        self.assertEqual(_safe_url("http://example.com/job"), "http://example.com/job")
        self.assertEqual(_safe_url("javascript:alert(1)"), "")
        self.assertEqual(_safe_url("file:///C:/Windows/win.ini"), "")

    def test_export_all_writes_graduate_digest(self) -> None:
        job = Job(
            source="test",
            source_type="ats",
            title="Graduate Data Programme",
            company="Example",
            url="https://example.com/graduate",
            location="Paris, France",
            description="Graduate programme in data engineering, Python and SQL. Intake September 2026.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            export_all(Path(tmp), [job], [], profile={"constraints": {"target_start_after": "2026-08"}})
            payload = json.loads((Path(tmp) / "graduate_programs.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["target_count"], 1)
            self.assertTrue((Path(tmp) / "graduate_programs.md").exists())

    def test_graduate_digest_counts_industrial_doctorates(self) -> None:
        job = Job(
            source="test",
            source_type="official_api",
            title="Doctorant CIFRE IA - Machine Learning",
            company="Example AI",
            url="https://example.com/cifre",
            location="Paris, France",
            description="CIFRE industrial PhD in applied AI research, Python, LLM evaluation and explainability.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            export_all(Path(tmp), [job], [], profile={"constraints": {"target_start_after": "2026-08"}})
            payload = json.loads((Path(tmp) / "graduate_programs.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["target_count"], 1)
            self.assertEqual(payload["doctoral_count"], 1)
            self.assertEqual(payload["industrial_doctoral_count"], 1)


if __name__ == "__main__":
    unittest.main()
