from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from jobradai.models import Job
from jobradai.store import write_sqlite


class StoreTests(unittest.TestCase):
    def test_write_sqlite_represents_current_snapshot_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.sqlite"
            first = Job(source="A", source_type="ats", title="AI Engineer", company="Acme", url="https://a.example/job")
            second = Job(source="B", source_type="ats", title="Data Engineer", company="Beta", url="https://b.example/job")
            write_sqlite(path, [first, second])
            write_sqlite(path, [second])
            with closing(sqlite3.connect(path)) as conn:
                rows = conn.execute("SELECT title FROM jobs").fetchall()
            self.assertEqual(rows, [("Data Engineer",)])


if __name__ == "__main__":
    unittest.main()
