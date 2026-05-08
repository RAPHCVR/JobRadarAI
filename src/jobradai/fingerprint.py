from __future__ import annotations

import hashlib
import json
from typing import Any


def jobs_fingerprint(jobs: list[dict[str, Any]]) -> str:
    records: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        records.append(
            {
                "stable_id": str(job.get("stable_id") or ""),
                "source": str(job.get("source") or ""),
                "title": str(job.get("title") or ""),
                "company": str(job.get("company") or ""),
                "url": str(job.get("url") or ""),
                "score": _rounded_score(job.get("score")),
            }
        )
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rounded_score(value: Any) -> float | str:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return ""
