from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobradai.early_career import early_career_signal
from jobradai.enrichment import infer_start_date_check
from jobradai.text import normalize_space


FIT_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}
START_ORDER = {"compatible": 0, "unknown": 1, "too_soon": 2}


def write_graduate_digest(output_dir: Path, jobs: list[dict[str, Any]], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _graduate_rows(jobs, profile or {})
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "target_count": len([row for row in rows if row["early_career_fit"] in {"high", "medium"}]),
        "doctoral_count": len([row for row in rows if row["doctoral_program"]]),
        "industrial_doctoral_count": len([row for row in rows if row["industrial_doctoral"]]),
        "fit_counts": dict(Counter(row["early_career_fit"] for row in rows)),
        "start_date_counts": dict(Counter(row["start_date_check"] for row in rows)),
        "items": rows,
    }
    (output_dir / "graduate_programs.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "graduate_programs.md").write_text(_graduate_markdown(payload), encoding="utf-8")
    return payload


def _graduate_rows(jobs: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for job in jobs:
        signal = early_career_signal(job)
        if signal.get("early_career_fit") == "none":
            continue
        start = infer_start_date_check(job, profile)
        rows.append(
            {
                "stable_id": normalize_space(str(job.get("stable_id") or "")),
                "score": _float(job.get("score")),
                "early_career_fit": signal.get("early_career_fit", "none"),
                "structured_program": bool(signal.get("structured_program")),
                "doctoral_program": bool(signal.get("doctoral_program")),
                "industrial_doctoral": bool(signal.get("industrial_doctoral")),
                "start_date_check": start.get("check", "unknown"),
                "start_date_evidence": start.get("evidence", ""),
                "title": normalize_space(str(job.get("title") or "")),
                "company": normalize_space(str(job.get("company") or "")),
                "market": normalize_space(str(job.get("market") or "")),
                "location": normalize_space(str(job.get("location") or "")),
                "source": normalize_space(str(job.get("source") or "")),
                "source_type": normalize_space(str(job.get("source_type") or "")),
                "salary": normalize_space(str(job.get("salary") or "")),
                "remote": bool(job.get("remote")),
                "url": normalize_space(str(job.get("url") or "")),
                "signals": signal.get("signals", []) if isinstance(signal.get("signals"), list) else [],
                "risks": signal.get("risks", []) if isinstance(signal.get("risks"), list) else [],
            }
        )
    rows.sort(
        key=lambda item: (
            FIT_ORDER.get(str(item["early_career_fit"]), 99),
            START_ORDER.get(str(item["start_date_check"]), 99),
            -float(item["score"] or 0),
            str(item["company"]).lower(),
        )
    )
    return rows


def _graduate_markdown(payload: dict[str, Any]) -> str:
    rows = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    target = [row for row in rows if row.get("early_career_fit") in {"high", "medium"}]
    low = [row for row in rows if row.get("early_career_fit") == "low"]
    lines = [
        "# Graduate / Early Careers / Doctoral",
        "",
        f"- Genere le: {payload.get('generated_at', '')}",
        f"- Signaux detectes: **{payload.get('count', 0)}**",
        f"- Cibles high/medium: **{payload.get('target_count', 0)}**",
        f"- Doctorats/CIFRE detectes: **{payload.get('doctoral_count', 0)}** dont industriels/CIFRE: **{payload.get('industrial_doctoral_count', 0)}**",
        f"- Fits: `{payload.get('fit_counts', {})}`",
        f"- Start dates: `{payload.get('start_date_counts', {})}`",
        "",
        "## Cibles Prioritaires",
        "",
    ]
    if not target:
        lines.append("- Aucun programme/role early-career ou doctorat data/AI/software prioritaire detecte dans ce corpus.")
    for item in target[:120]:
        lines.extend(_row_lines(item))
    lines.extend(["", "## A Verifier / Low Fit", ""])
    if not low:
        lines.append("- Aucun signal low-fit a verifier.")
    for item in low[:80]:
        lines.extend(_row_lines(item))
    return "\n".join(lines) + "\n"


def _row_lines(item: dict[str, Any]) -> list[str]:
    signals = "; ".join(str(value) for value in item.get("signals", []) if value) or "n/a"
    risks = "; ".join(str(value) for value in item.get("risks", []) if value) or "n/a"
    if item.get("industrial_doctoral"):
        structured = "industrial_doctoral"
    elif item.get("doctoral_program"):
        structured = "doctoral"
    else:
        structured = "structured" if item.get("structured_program") else "role"
    score = _float(item.get("score"))
    return [
        (
            f"- `{item.get('early_career_fit')}` `{structured}` start `{item.get('start_date_check')}` "
            f"| {score:.1f} | {item.get('title')} - {item.get('company')} "
            f"| {item.get('market') or 'n/a'} | {item.get('source') or 'n/a'} | {item.get('url')}"
        ),
        f"  - Signaux: {signals}",
        f"  - Risques: {risks}",
        f"  - Lieu/salaire: {item.get('location') or 'n/a'} | {item.get('salary') or 'n/a'}",
    ]


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
