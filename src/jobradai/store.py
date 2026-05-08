from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jobradai.models import Job


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  stable_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  company TEXT NOT NULL,
  url TEXT NOT NULL,
  location TEXT,
  market TEXT,
  score REAL,
  payload_json TEXT NOT NULL,
  captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_market ON jobs(market);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
"""


def write_sqlite(path: Path, jobs: list[Job]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM jobs")
        conn.executemany(
            """
            INSERT INTO jobs (
              stable_id, source, source_type, title, company, url,
              location, market, score, payload_json, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stable_id) DO UPDATE SET
              source=excluded.source,
              source_type=excluded.source_type,
              title=excluded.title,
              company=excluded.company,
              url=excluded.url,
              location=excluded.location,
              market=excluded.market,
              score=excluded.score,
              payload_json=excluded.payload_json,
              captured_at=excluded.captured_at
            """,
            [
                (
                    job.stable_id,
                    job.source,
                    job.source_type,
                    job.title,
                    job.company,
                    job.url,
                    job.location,
                    job.market,
                    job.score,
                    json.dumps(job.as_dict(), ensure_ascii=False),
                    job.captured_at,
                )
                for job in jobs
            ],
        )
        conn.commit()
    finally:
        conn.close()
