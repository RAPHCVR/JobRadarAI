from __future__ import annotations

import concurrent.futures
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobradai.early_career import early_career_signal
from jobradai.enrichment import (
    build_recruiter_message,
    effective_language_check,
    effective_remote_check,
    effective_remote_location_validity,
    effective_salary_check,
    effective_start_date_check,
)
from jobradai.link_check import check_job_link


SCHEMA = """
CREATE TABLE IF NOT EXISTS job_history (
  stable_id TEXT PRIMARY KEY,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  seen_count INTEGER NOT NULL DEFAULT 0,
  absent_count INTEGER NOT NULL DEFAULT 0,
  last_absent_run TEXT,
  presence_status TEXT NOT NULL,
  last_run TEXT,
  title TEXT NOT NULL,
  company TEXT NOT NULL,
  url TEXT NOT NULL,
  location TEXT,
  deadline TEXT,
  market TEXT,
  source TEXT,
  source_type TEXT,
  score REAL,
  salary_normalized_annual_eur REAL,
  last_priority TEXT,
  last_combined_score REAL,
  last_level_fit TEXT,
  last_salary_check TEXT,
  last_remote_check TEXT,
  last_language_check TEXT,
  last_remote_location_validity TEXT,
  last_start_date_check TEXT,
  last_start_date_evidence TEXT,
  last_application_angle TEXT,
  last_recruiter_message TEXT,
  last_llm_seen TEXT,
  last_link_status TEXT,
  last_link_http_status INTEGER,
  last_link_checked_at TEXT,
  last_link_reason TEXT,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_history_presence ON job_history(presence_status);
CREATE INDEX IF NOT EXISTS idx_job_history_priority ON job_history(last_priority);
CREATE INDEX IF NOT EXISTS idx_job_history_score ON job_history(score DESC);
CREATE INDEX IF NOT EXISTS idx_job_history_last_seen ON job_history(last_seen DESC);
CREATE TABLE IF NOT EXISTS run_history (
  run_name TEXT PRIMARY KEY,
  generated_at TEXT NOT NULL,
  current_jobs INTEGER NOT NULL,
  known_jobs INTEGER NOT NULL,
  new_jobs INTEGER NOT NULL,
  returned_jobs INTEGER NOT NULL,
  missing_this_run INTEGER NOT NULL,
  rechecked_stale INTEGER NOT NULL,
  queue_count INTEGER NOT NULL,
  active_jobs INTEGER NOT NULL,
  stale_jobs INTEGER NOT NULL,
  expired_jobs INTEGER NOT NULL,
  summary_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_history_generated ON run_history(generated_at DESC);
"""


RELEVANT_PRIORITIES = {"apply_now", "shortlist"}
QUEUE_PRIORITIES = {"apply_now": 0, "shortlist": 1, "high_score": 2, "maybe": 3}
EXPIRED_LINK_STATUSES = {"expired", "unreachable", "invalid_url"}


def sync_history(
    *,
    output_dir: Path,
    history_db: Path,
    run_name: str | None = None,
    recheck_stale_limit: int = 40,
    timeout_seconds: int = 10,
    workers: int = 8,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    jobs = _read_json(output_dir / "jobs.json", [])
    if not isinstance(jobs, list):
        raise ValueError(f"Format jobs invalide dans {output_dir / 'jobs.json'}")
    jobs = [job for job in jobs if isinstance(job, dict)]
    shortlist = _read_json(output_dir / "llm_shortlist.json", {})
    shortlist = shortlist if isinstance(shortlist, dict) else {}
    link_checks = _read_json(output_dir / "link_checks.json", {})
    link_checks = link_checks if isinstance(link_checks, dict) else {}

    now = datetime.now(timezone.utc).isoformat()
    run = run_name or datetime.now().strftime("%Y%m%d-%H%M%S")
    profile = profile or {}
    output_dir.mkdir(parents=True, exist_ok=True)
    history_db.parent.mkdir(parents=True, exist_ok=True)

    shortlist_by_id = _shortlist_by_id(shortlist)
    link_by_id = _link_by_id(link_checks)
    current_ids = {str(job.get("stable_id") or "") for job in jobs if job.get("stable_id")}

    conn = sqlite3.connect(history_db)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        _ensure_schema(conn)
        before_ids = _all_ids(conn)
        previous_statuses = _status_by_id(conn)
        previous_summary = _latest_run_summary(conn, exclude_run=run)
        existing_run_summary = _run_summary(conn, run_name=run)
        for job in jobs:
            stable_id = str(job.get("stable_id") or "")
            if not stable_id:
                continue
            _upsert_current_job(
                conn,
                job=job,
                shortlist_item=shortlist_by_id.get(stable_id),
                link_item=link_by_id.get(stable_id),
                now=now,
                run_name=run,
                profile=profile,
            )
        missing_ids = sorted(before_ids - current_ids)
        returned_ids = sorted(stable_id for stable_id in current_ids if previous_statuses.get(stable_id) in {"stale", "expired"})
        _mark_missing(conn, missing_ids, run_name=run)
        stale_rechecks = _select_stale_rechecks(conn, limit=recheck_stale_limit)
        rechecked = _recheck_jobs(stale_rechecks, timeout_seconds=timeout_seconds, workers=workers)
        for item in rechecked:
            _update_link_status(conn, item, checked_at=now, mark_expired=True)
        queue = _queue_rows(conn)
        presence_counts = _presence_counts(conn)
        source_counts = _source_counts(conn)
        result = {
            "generated_at": now,
            "run_name": run,
            "history_db": str(history_db.resolve()),
            "current_jobs": len(jobs),
            "known_jobs": len(before_ids | current_ids),
            "new_jobs": len(current_ids - before_ids),
            "returned_jobs": len(returned_ids),
            "returned_ids": returned_ids[:200],
            "missing_this_run": len(missing_ids),
            "rechecked_stale": len(rechecked),
            "queue_count": len(queue),
            "queue_status_counts": dict(Counter(str(item.get("presence_status", "")) for item in queue)),
            "queue_priority_counts": dict(Counter(str(item.get("queue_bucket", "")) for item in queue)),
            "presence_counts": presence_counts,
            "source_counts": source_counts,
            "previous_run": previous_summary,
            "items": queue,
        }
        _preserve_same_run_counters(result, existing_run_summary)
        result["history_dashboard"] = _dashboard_summary(result)
        _upsert_run_summary(conn, run_name=run, generated_at=now, summary=result["history_dashboard"])
        conn.commit()
    finally:
        conn.close()

    (output_dir / "application_queue.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "application_queue.md").write_text(_queue_markdown(result), encoding="utf-8")
    (output_dir / "application_messages.json").write_text(
        json.dumps(_application_messages(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "application_messages.md").write_text(_application_messages_markdown(result), encoding="utf-8")
    (output_dir / "history_dashboard.json").write_text(
        json.dumps(result["history_dashboard"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "history_dashboard.md").write_text(_history_dashboard_markdown(result["history_dashboard"]), encoding="utf-8")
    (output_dir / "weekly_digest.json").write_text(
        json.dumps(result["history_dashboard"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "weekly_digest.md").write_text(_weekly_digest_markdown(result["history_dashboard"]), encoding="utf-8")
    return result


def _upsert_current_job(
    conn: sqlite3.Connection,
    *,
    job: dict[str, Any],
    shortlist_item: dict[str, Any] | None,
    link_item: dict[str, Any] | None,
    now: str,
    run_name: str,
    profile: dict[str, Any],
) -> None:
    stable_id = str(job.get("stable_id") or "")
    existing = conn.execute("SELECT * FROM job_history WHERE stable_id = ?", (stable_id,)).fetchone()
    previous_priority = str(existing["last_priority"] or "") if existing else ""
    priority = str((shortlist_item or {}).get("priority") or previous_priority)
    combined_score = _float_or_none((shortlist_item or {}).get("combined_score"))
    if combined_score is None and existing:
        combined_score = _float_or_none(existing["last_combined_score"])
    link_status = str((link_item or {}).get("status") or (existing["last_link_status"] if existing else "") or "")
    link_http_status = _int_or_none((link_item or {}).get("http_status"))
    if link_http_status is None and existing:
        link_http_status = _int_or_none(existing["last_link_http_status"])
    presence_status = "expired" if link_status in EXPIRED_LINK_STATUSES else "active"
    first_seen = str(existing["first_seen"]) if existing else now
    same_run = bool(existing and str(existing["last_run"] or "") == run_name)
    seen_count = int(existing["seen_count"] or 0) if same_run and existing else int(existing["seen_count"] or 0) + 1 if existing else 1
    llm_seen = now if shortlist_item else (str(existing["last_llm_seen"] or "") if existing else "")
    salary_check = effective_salary_check(job, shortlist_item, profile)
    if salary_check == "unknown" and existing and existing["last_salary_check"]:
        salary_check = str(existing["last_salary_check"])
    remote_check = effective_remote_check(job, shortlist_item)
    if remote_check == "unknown" and existing and existing["last_remote_check"]:
        remote_check = str(existing["last_remote_check"])
    language_check = effective_language_check(job, shortlist_item)
    if language_check == "unknown" and existing and existing["last_language_check"]:
        language_check = str(existing["last_language_check"])
    remote_location_validity = effective_remote_location_validity(job, shortlist_item, profile)
    if remote_location_validity == "unknown" and existing and existing["last_remote_location_validity"]:
        remote_location_validity = str(existing["last_remote_location_validity"])
    start_date_check, start_date_evidence = effective_start_date_check(job, shortlist_item, profile)
    if start_date_check == "unknown" and existing and existing["last_start_date_check"]:
        start_date_check = str(existing["last_start_date_check"])
        start_date_evidence = str(existing["last_start_date_evidence"] or "")
    application_angle = str((shortlist_item or {}).get("application_angle") or (existing["last_application_angle"] if existing else "") or "")
    recruiter_message = build_recruiter_message(
        {
            "title": job.get("title") or "",
            "company": job.get("company") or "",
            "last_application_angle": application_angle,
            "last_start_date_check": start_date_check,
            "last_salary_check": salary_check,
            "last_remote_check": remote_check,
            "last_language_check": language_check,
            "last_remote_location_validity": remote_location_validity,
        }
    )
    conn.execute(
        """
        INSERT INTO job_history (
          stable_id, first_seen, last_seen, seen_count, absent_count, presence_status, last_run,
          title, company, url, location, deadline, market, source, source_type, score, salary_normalized_annual_eur,
          last_priority, last_combined_score, last_level_fit, last_salary_check, last_remote_check,
          last_language_check, last_remote_location_validity,
          last_start_date_check, last_start_date_evidence, last_application_angle, last_recruiter_message, last_llm_seen,
          last_link_status, last_link_http_status, last_link_checked_at, last_link_reason, payload_json
        ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(stable_id) DO UPDATE SET
          last_seen=excluded.last_seen,
          seen_count=excluded.seen_count,
          absent_count=0,
          presence_status=excluded.presence_status,
          last_run=excluded.last_run,
          title=excluded.title,
          company=excluded.company,
          url=excluded.url,
          location=excluded.location,
          deadline=excluded.deadline,
          market=excluded.market,
          source=excluded.source,
          source_type=excluded.source_type,
          score=excluded.score,
          salary_normalized_annual_eur=excluded.salary_normalized_annual_eur,
          last_priority=excluded.last_priority,
          last_combined_score=excluded.last_combined_score,
          last_level_fit=excluded.last_level_fit,
          last_salary_check=excluded.last_salary_check,
          last_remote_check=excluded.last_remote_check,
          last_language_check=excluded.last_language_check,
          last_remote_location_validity=excluded.last_remote_location_validity,
          last_start_date_check=excluded.last_start_date_check,
          last_start_date_evidence=excluded.last_start_date_evidence,
          last_application_angle=excluded.last_application_angle,
          last_recruiter_message=excluded.last_recruiter_message,
          last_llm_seen=excluded.last_llm_seen,
          last_link_status=excluded.last_link_status,
          last_link_http_status=excluded.last_link_http_status,
          last_link_checked_at=excluded.last_link_checked_at,
          last_link_reason=excluded.last_link_reason,
          payload_json=excluded.payload_json
        """,
        (
            stable_id,
            first_seen,
            now,
            seen_count,
            presence_status,
            run_name,
            str(job.get("title") or ""),
            str(job.get("company") or ""),
            str(job.get("url") or ""),
            str(job.get("location") or ""),
            str(job.get("deadline") or ""),
            str(job.get("market") or ""),
            str(job.get("source") or ""),
            str(job.get("source_type") or ""),
            _float_or_none(job.get("score")),
            _float_or_none(job.get("salary_normalized_annual_eur")),
            priority,
            combined_score,
            str((shortlist_item or {}).get("level_fit") or (existing["last_level_fit"] if existing else "") or ""),
            salary_check,
            remote_check,
            language_check,
            remote_location_validity,
            start_date_check,
            start_date_evidence,
            application_angle,
            recruiter_message,
            llm_seen,
            link_status,
            link_http_status,
            now if link_item else (str(existing["last_link_checked_at"] or "") if existing else ""),
            str((link_item or {}).get("reason") or (existing["last_link_reason"] if existing else "") or ""),
            json.dumps(job, ensure_ascii=False),
        ),
    )


def _mark_missing(conn: sqlite3.Connection, stable_ids: list[str], *, run_name: str) -> None:
    for stable_id in stable_ids:
        row = conn.execute("SELECT presence_status, absent_count FROM job_history WHERE stable_id = ?", (stable_id,)).fetchone()
        if not row or row["presence_status"] == "expired":
            continue
        conn.execute(
            """
            UPDATE job_history
            SET absent_count = CASE WHEN COALESCE(last_absent_run, '') = ? THEN absent_count ELSE absent_count + 1 END,
                last_absent_run = ?,
                presence_status = CASE WHEN last_link_status IN ('expired', 'unreachable', 'invalid_url') THEN 'expired' ELSE 'stale' END
            WHERE stable_id = ?
            """,
            (run_name, run_name, stable_id),
        )


def _select_stale_rechecks(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    rows = conn.execute(
        """
        SELECT stable_id, payload_json
        FROM job_history
        WHERE presence_status = 'stale'
          AND (
            last_priority IN ('apply_now', 'shortlist')
            OR score >= 75
          )
        ORDER BY
          CASE last_priority WHEN 'apply_now' THEN 0 WHEN 'shortlist' THEN 1 ELSE 2 END,
          score DESC,
          last_seen DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    jobs: list[dict[str, Any]] = []
    for row in rows:
        try:
            job = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            continue
        if isinstance(job, dict):
            jobs.append(job)
    return jobs


def _recheck_jobs(jobs: list[dict[str, Any]], *, timeout_seconds: int, workers: int) -> list[dict[str, Any]]:
    if not jobs:
        return []
    max_workers = max(1, min(workers, len(jobs)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(lambda job: check_job_link(job, timeout_seconds=timeout_seconds), jobs))


def _update_link_status(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    *,
    checked_at: str,
    mark_expired: bool,
) -> None:
    status = str(item.get("status") or "")
    stable_id = str(item.get("stable_id") or "")
    if not stable_id:
        return
    presence_sql = "presence_status"
    if mark_expired and status in EXPIRED_LINK_STATUSES:
        presence_sql = "'expired'"
    conn.execute(
        f"""
        UPDATE job_history
        SET last_link_status = ?,
            last_link_http_status = ?,
            last_link_checked_at = ?,
            last_link_reason = ?,
            presence_status = {presence_sql}
        WHERE stable_id = ?
        """,
        (
            status,
            _int_or_none(item.get("http_status")),
            checked_at,
            str(item.get("reason") or ""),
            stable_id,
        ),
    )


def _queue_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM job_history
        WHERE presence_status != 'expired'
          AND COALESCE(last_level_fit, '') NOT IN ('too_senior', 'too_junior')
          AND (
            last_priority IN ('apply_now', 'shortlist', 'maybe')
            OR score >= 75
          )
        ORDER BY
          CASE
            WHEN presence_status = 'active' THEN 0
            ELSE 1
          END,
          CASE last_priority
            WHEN 'apply_now' THEN 0
            WHEN 'shortlist' THEN 1
            WHEN 'maybe' THEN 3
            ELSE 2
          END,
          score DESC,
          last_seen DESC
        LIMIT 600
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        job_payload = _payload_dict(item.get("payload_json"))
        if _deterministic_experience_too_senior(item, job_payload):
            continue
        early_signal = early_career_signal(job_payload or item)
        item["early_career_fit"] = early_signal.get("early_career_fit", "none")
        item["early_career_structured"] = bool(early_signal.get("structured_program"))
        item["early_career_signals"] = early_signal.get("signals", [])
        item["early_career_risks"] = early_signal.get("risks", [])
        item["required_years"] = job_payload.get("required_years")
        item["experience_check"] = job_payload.get("experience_check") or "unknown"
        item["experience_evidence"] = job_payload.get("experience_evidence") or ""
        priority = str(item.get("last_priority") or "")
        score = float(item.get("score") or 0)
        if priority in RELEVANT_PRIORITIES:
            bucket = priority
        elif priority == "maybe":
            bucket = "maybe"
        elif score >= 75:
            bucket = "high_score"
        else:
            bucket = "other"
        item["queue_bucket"] = bucket
        if not item.get("last_recruiter_message"):
            item["last_recruiter_message"] = build_recruiter_message(item)
        item.pop("payload_json", None)
        items.append(item)
        if len(items) >= 300:
            break
    return items


def _deterministic_experience_too_senior(item: dict[str, Any], job_payload: dict[str, Any]) -> bool:
    if str(item.get("last_level_fit") or "") == "junior_ok":
        return False
    return str(job_payload.get("experience_check") or "").strip().lower() == "too_senior"


def _queue_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Application Queue",
        "",
        f"- Genere le: {result.get('generated_at', '')}",
        f"- Run: `{result.get('run_name', '')}`",
        f"- Offres courantes: **{result.get('current_jobs', 0)}**",
        f"- Offres connues historique: **{result.get('known_jobs', 0)}**",
        f"- Nouvelles offres: **{result.get('new_jobs', 0)}**",
        f"- Absentes ce run: **{result.get('missing_this_run', 0)}**",
        f"- Anciennes offres pertinentes reverifiees: **{result.get('rechecked_stale', 0)}**",
        f"- Queue dedupee: **{result.get('queue_count', 0)}**",
        f"- Statuts queue: `{result.get('queue_status_counts', {})}`",
        f"- Priorites queue: `{result.get('queue_priority_counts', {})}`",
        "",
    ]
    early_rows = [
        item
        for item in result.get("items", [])
        if item.get("early_career_fit") in {"high", "medium"}
    ]
    lines.extend(["## Graduate / Early Careers", ""])
    if not early_rows:
        lines.append("- Aucun item graduate/early-career high/medium dans la queue actuelle.")
    for item in early_rows[:80]:
        status = item.get("presence_status") or ""
        link_status = item.get("last_link_status") or "not_checked"
        score = float(item.get("score") or 0)
        structured = "structured" if item.get("early_career_structured") else "role"
        signals = "; ".join(str(value) for value in item.get("early_career_signals", []) if value) or "n/a"
        lines.append(
            f"- `{status}` link `{link_status}` | {score:.1f} | fit `{item.get('early_career_fit')}` "
            f"`{structured}` | start `{item.get('last_start_date_check') or 'unknown'}` | "
            f"niveau `{item.get('last_level_fit') or 'unknown'}` | "
            f"exp `{item.get('experience_check') or 'unknown'}`/{_required_years_label(item.get('required_years'))} | "
            f"deadline `{item.get('deadline') or 'n/a'}` | langue `{item.get('last_language_check') or 'unknown'}` | "
            f"{item.get('title')} - {item.get('company')} | {item.get('market')} | {item.get('url')}"
        )
        lines.append(f"  - Signaux: {signals}")
    lines.append("")
    sections = [
        ("Apply Now", "apply_now"),
        ("Shortlist", "shortlist"),
        ("High Score", "high_score"),
        ("Maybe", "maybe"),
    ]
    items = result.get("items", [])
    for title, bucket in sections:
        rows = [item for item in items if item.get("queue_bucket") == bucket]
        lines.extend([f"## {title}", ""])
        if not rows:
            lines.append("- Aucun item.")
        for item in rows[:80]:
            status = item.get("presence_status") or ""
            link_status = item.get("last_link_status") or "not_checked"
            score = float(item.get("score") or 0)
            lines.append(
                f"- `{status}` link `{link_status}` | {score:.1f} | "
                f"start `{item.get('last_start_date_check') or 'unknown'}` | "
                f"niveau `{item.get('last_level_fit') or 'unknown'}` | "
                f"exp `{item.get('experience_check') or 'unknown'}`/{_required_years_label(item.get('required_years'))} | "
                f"salaire `{item.get('last_salary_check') or 'unknown'}` | "
                f"remote `{item.get('last_remote_check') or 'unknown'}` | "
                f"langue `{item.get('last_language_check') or 'unknown'}` | "
                f"remote/localisation `{item.get('last_remote_location_validity') or 'unknown'}` | "
                f"deadline `{item.get('deadline') or 'n/a'}` | "
                f"{item.get('title')} - {item.get('company')} | {item.get('market')} | "
                f"{item.get('url')}"
            )
            if item.get("last_application_angle"):
                lines.append(f"  - Angle: {item.get('last_application_angle')}")
        lines.append("")
    return "\n".join(lines)


def _shortlist_by_id(shortlist: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = shortlist.get("items", []) if isinstance(shortlist, dict) else []
    return {
        str(item.get("stable_id") or ""): item
        for item in items
        if isinstance(item, dict) and item.get("stable_id")
    }


def _link_by_id(link_checks: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = link_checks.get("items", []) if isinstance(link_checks, dict) else []
    return {
        str(item.get("stable_id") or ""): item
        for item in items
        if isinstance(item, dict) and item.get("stable_id")
    }


def _all_ids(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute("SELECT stable_id FROM job_history")}


def _ensure_schema(conn: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(job_history)")}
    additions = {
        "last_absent_run": "TEXT",
        "deadline": "TEXT",
        "salary_normalized_annual_eur": "REAL",
        "last_language_check": "TEXT",
        "last_remote_location_validity": "TEXT",
        "last_start_date_check": "TEXT",
        "last_start_date_evidence": "TEXT",
        "last_application_angle": "TEXT",
        "last_recruiter_message": "TEXT",
    }
    for name, column_type in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE job_history ADD COLUMN {name} {column_type}")


def _status_by_id(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["stable_id"]): str(row["presence_status"] or "")
        for row in conn.execute("SELECT stable_id, presence_status FROM job_history")
    }


def _presence_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT presence_status, COUNT(*) AS count FROM job_history GROUP BY presence_status").fetchall()
    return {str(row["presence_status"] or "unknown"): int(row["count"] or 0) for row in rows}


def _source_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT source, COUNT(*) AS count
        FROM job_history
        GROUP BY source
        ORDER BY count DESC, source ASC
        LIMIT 30
        """
    ).fetchall()
    return {str(row["source"] or "unknown"): int(row["count"] or 0) for row in rows}


def _latest_run_summary(conn: sqlite3.Connection, *, exclude_run: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT summary_json
        FROM run_history
        WHERE run_name != ?
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        (exclude_run,),
    ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["summary_json"])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _run_summary(conn: sqlite3.Connection, *, run_name: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT summary_json FROM run_history WHERE run_name = ?", (run_name,)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["summary_json"])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _preserve_same_run_counters(result: dict[str, Any], existing_summary: dict[str, Any] | None) -> None:
    if not existing_summary:
        return
    if int(existing_summary.get("current_jobs") or -1) != int(result.get("current_jobs") or 0):
        return
    if int(existing_summary.get("known_jobs") or -1) != int(result.get("known_jobs") or 0):
        return
    for key in ("new_jobs", "returned_jobs"):
        result[key] = int(existing_summary.get(key) or result.get(key) or 0)
    if existing_summary.get("returned_ids"):
        result["returned_ids"] = existing_summary.get("returned_ids", [])


def _upsert_run_summary(
    conn: sqlite3.Connection,
    *,
    run_name: str,
    generated_at: str,
    summary: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO run_history (
          run_name, generated_at, current_jobs, known_jobs, new_jobs, returned_jobs,
          missing_this_run, rechecked_stale, queue_count, active_jobs, stale_jobs, expired_jobs, summary_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_name) DO UPDATE SET
          generated_at=excluded.generated_at,
          current_jobs=excluded.current_jobs,
          known_jobs=excluded.known_jobs,
          new_jobs=excluded.new_jobs,
          returned_jobs=excluded.returned_jobs,
          missing_this_run=excluded.missing_this_run,
          rechecked_stale=excluded.rechecked_stale,
          queue_count=excluded.queue_count,
          active_jobs=excluded.active_jobs,
          stale_jobs=excluded.stale_jobs,
          expired_jobs=excluded.expired_jobs,
          summary_json=excluded.summary_json
        """,
        (
            run_name,
            generated_at,
            int(summary.get("current_jobs") or 0),
            int(summary.get("known_jobs") or 0),
            int(summary.get("new_jobs") or 0),
            int(summary.get("returned_jobs") or 0),
            int(summary.get("missing_this_run") or 0),
            int(summary.get("rechecked_stale") or 0),
            int(summary.get("queue_count") or 0),
            int(summary.get("active_jobs") or 0),
            int(summary.get("stale_jobs") or 0),
            int(summary.get("expired_jobs") or 0),
            json.dumps(summary, ensure_ascii=False),
        ),
    )


def _dashboard_summary(result: dict[str, Any]) -> dict[str, Any]:
    presence = result.get("presence_counts", {}) if isinstance(result.get("presence_counts"), dict) else {}
    previous = result.get("previous_run") if isinstance(result.get("previous_run"), dict) else None
    summary = {
        "generated_at": result.get("generated_at", ""),
        "run_name": result.get("run_name", ""),
        "previous_run_name": previous.get("run_name") if previous else "",
        "current_jobs": int(result.get("current_jobs") or 0),
        "known_jobs": int(result.get("known_jobs") or 0),
        "new_jobs": int(result.get("new_jobs") or 0),
        "returned_jobs": int(result.get("returned_jobs") or 0),
        "missing_this_run": int(result.get("missing_this_run") or 0),
        "rechecked_stale": int(result.get("rechecked_stale") or 0),
        "queue_count": int(result.get("queue_count") or 0),
        "active_jobs": int(presence.get("active") or 0),
        "stale_jobs": int(presence.get("stale") or 0),
        "expired_jobs": int(presence.get("expired") or 0),
        "presence_counts": presence,
        "queue_status_counts": result.get("queue_status_counts", {}),
        "queue_priority_counts": result.get("queue_priority_counts", {}),
        "source_counts": result.get("source_counts", {}),
        "returned_ids": result.get("returned_ids", []),
    }
    if previous:
        summary["deltas_vs_previous"] = {
            "current_jobs": summary["current_jobs"] - int(previous.get("current_jobs") or 0),
            "known_jobs": summary["known_jobs"] - int(previous.get("known_jobs") or 0),
            "new_jobs": summary["new_jobs"] - int(previous.get("new_jobs") or 0),
            "queue_count": summary["queue_count"] - int(previous.get("queue_count") or 0),
            "active_jobs": summary["active_jobs"] - int(previous.get("active_jobs") or 0),
            "stale_jobs": summary["stale_jobs"] - int(previous.get("stale_jobs") or 0),
            "expired_jobs": summary["expired_jobs"] - int(previous.get("expired_jobs") or 0),
        }
    else:
        summary["deltas_vs_previous"] = {}
    return summary


def _application_messages(result: dict[str, Any]) -> dict[str, Any]:
    items = [
        {
            "stable_id": item.get("stable_id"),
            "queue_bucket": item.get("queue_bucket"),
            "title": item.get("title"),
            "company": item.get("company"),
            "url": item.get("url"),
            "market": item.get("market"),
            "start_date_check": item.get("last_start_date_check") or "unknown",
            "salary_check": item.get("last_salary_check") or "unknown",
            "remote_check": item.get("last_remote_check") or "unknown",
            "language_check": item.get("last_language_check") or "unknown",
            "remote_location_validity": item.get("last_remote_location_validity") or "unknown",
            "required_years": item.get("required_years"),
            "experience_check": item.get("experience_check") or "unknown",
            "experience_evidence": item.get("experience_evidence") or "",
            "deadline": item.get("deadline") or "",
            "application_angle": item.get("last_application_angle") or "",
            "message": item.get("last_recruiter_message") or build_recruiter_message(item),
        }
        for item in result.get("items", [])
        if item.get("queue_bucket") in {"apply_now", "shortlist", "high_score"}
    ]
    return {
        "generated_at": result.get("generated_at", ""),
        "run_name": result.get("run_name", ""),
        "count": len(items),
        "items": items,
    }


def _application_messages_markdown(result: dict[str, Any]) -> str:
    payload = _application_messages(result)
    lines = [
        "# Messages RH",
        "",
        f"- Genere le: {payload.get('generated_at', '')}",
        f"- Run: `{payload.get('run_name', '')}`",
        f"- Messages: **{payload.get('count', 0)}**",
        "",
    ]
    for index, item in enumerate(payload["items"][:120], start=1):
        lines.extend(
            [
                f"## {index}. {item.get('title')} - {item.get('company')}",
                "",
                f"- Bucket: `{item.get('queue_bucket')}` | Marche: `{item.get('market')}`",
                f"- Checks: start `{item.get('start_date_check')}` | salaire `{item.get('salary_check')}` | remote `{item.get('remote_check')}` | langue `{item.get('language_check')}` | remote/localisation `{item.get('remote_location_validity')}` | experience `{item.get('experience_check')}`/{_required_years_label(item.get('required_years'))} | deadline `{item.get('deadline') or 'n/a'}`",
                f"- URL: {item.get('url')}",
                "",
                "```text",
                str(item.get("message") or ""),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _history_dashboard_markdown(summary: dict[str, Any]) -> str:
    deltas = summary.get("deltas_vs_previous", {}) if isinstance(summary.get("deltas_vs_previous"), dict) else {}
    lines = [
        "# Dashboard historique",
        "",
        f"- Genere le: {summary.get('generated_at', '')}",
        f"- Run: `{summary.get('run_name', '')}`",
        f"- Run precedent: `{summary.get('previous_run_name') or 'n/a'}`",
        f"- Offres courantes: **{summary.get('current_jobs', 0)}**",
        f"- Offres connues: **{summary.get('known_jobs', 0)}**",
        f"- Nouvelles offres: **{summary.get('new_jobs', 0)}**",
        f"- Offres revenues: **{summary.get('returned_jobs', 0)}**",
        f"- Offres disparues ce run: **{summary.get('missing_this_run', 0)}**",
        f"- Offres expirees historiques: **{summary.get('expired_jobs', 0)}**",
        f"- Queue candidature: **{summary.get('queue_count', 0)}**",
        f"- Presence: `{summary.get('presence_counts', {})}`",
        f"- Deltas vs precedent: `{deltas}`",
        "",
        "## Sources historiques",
        "",
    ]
    sources = summary.get("source_counts", {}) if isinstance(summary.get("source_counts"), dict) else {}
    for source, count in list(sources.items())[:20]:
        lines.append(f"- `{source}`: {count}")
    return "\n".join(lines)


def _weekly_digest_markdown(summary: dict[str, Any]) -> str:
    deltas = summary.get("deltas_vs_previous", {}) if isinstance(summary.get("deltas_vs_previous"), dict) else {}
    lines = [
        "# Weekly Digest",
        "",
        f"- Run courant: `{summary.get('run_name', '')}`",
        f"- Run compare: `{summary.get('previous_run_name') or 'n/a'}`",
        "",
        "## Changements",
        "",
        f"- Nouvelles offres: **{summary.get('new_jobs', 0)}**",
        f"- Offres revenues: **{summary.get('returned_jobs', 0)}**",
        f"- Offres disparues: **{summary.get('missing_this_run', 0)}**",
        f"- Offres expirees historiques: **{summary.get('expired_jobs', 0)}**",
        f"- Queue candidature: **{summary.get('queue_count', 0)}**",
        f"- Deltas: `{deltas}`",
    ]
    returned = summary.get("returned_ids", [])
    if returned:
        lines.extend(["", "## Offres revenues", ""])
        for stable_id in returned[:30]:
            lines.append(f"- `{stable_id}`")
    return "\n".join(lines)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _required_years_label(value: Any) -> str:
    if value in (None, ""):
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    formatted = str(int(number)) if number.is_integer() else f"{number:g}"
    return f"{formatted}y"


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
