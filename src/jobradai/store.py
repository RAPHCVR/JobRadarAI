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
  deadline TEXT,
  language_check TEXT,
  remote_location_validity TEXT,
  salary_normalized_annual_eur REAL,
  required_years REAL,
  experience_check TEXT,
  experience_evidence TEXT,
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
        _ensure_columns(conn)
        conn.execute("DELETE FROM jobs")
        conn.executemany(
            """
            INSERT INTO jobs (
              stable_id, source, source_type, title, company, url,
              location, market, score, deadline, language_check, remote_location_validity,
              salary_normalized_annual_eur, required_years, experience_check, experience_evidence, payload_json, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stable_id) DO UPDATE SET
              source=excluded.source,
              source_type=excluded.source_type,
              title=excluded.title,
              company=excluded.company,
              url=excluded.url,
              location=excluded.location,
              market=excluded.market,
              score=excluded.score,
              deadline=excluded.deadline,
              language_check=excluded.language_check,
              remote_location_validity=excluded.remote_location_validity,
              salary_normalized_annual_eur=excluded.salary_normalized_annual_eur,
              required_years=excluded.required_years,
              experience_check=excluded.experience_check,
              experience_evidence=excluded.experience_evidence,
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
                    job.deadline,
                    job.language_check,
                    job.remote_location_validity,
                    job.salary_normalized_annual_eur,
                    job.required_years,
                    job.experience_check,
                    job.experience_evidence,
                    json.dumps(job.as_dict(), ensure_ascii=False),
                    job.captured_at,
                )
                for job in jobs
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(jobs)")}
    additions = {
        "deadline": "TEXT",
        "language_check": "TEXT",
        "remote_location_validity": "TEXT",
        "salary_normalized_annual_eur": "REAL",
        "required_years": "REAL",
        "experience_check": "TEXT",
        "experience_evidence": "TEXT",
    }
    for name, column_type in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {column_type}")
