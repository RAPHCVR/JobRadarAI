from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_snapshot(
    *,
    output_dir: Path,
    history_dir: Path,
    name: str | None = None,
) -> dict[str, Any]:
    if not output_dir.exists():
        raise FileNotFoundError(f"Dossier output introuvable: {output_dir}")
    stamp = _safe_snapshot_name(name or datetime.now().strftime("%Y%m%d-%H%M%S"))
    target = history_dir / stamp
    target.mkdir(parents=True, exist_ok=False)
    files: list[dict[str, Any]] = []
    for source in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if not source.is_file():
            continue
        destination = target / source.name
        shutil.copy2(source, destination)
        files.append({"name": source.name, "bytes": destination.stat().st_size})
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": stamp,
        "source_output_dir": str(output_dir.resolve()),
        "snapshot_dir": str(target.resolve()),
        "files": files,
        "summary": _summary_from_snapshot(target),
    }
    (target / "snapshot.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "latest.txt").write_text(stamp + "\n", encoding="utf-8")
    return manifest


def _summary_from_snapshot(path: Path) -> dict[str, Any]:
    audit = _read_json(path / "audit.json", {})
    if isinstance(audit, dict) and audit:
        return {
            "total_jobs": audit.get("total_jobs", 0),
            "sources_ok": (audit.get("source_status") or {}).get("ok", 0)
            if isinstance(audit.get("source_status"), dict)
            else 0,
            "source_errors": len((audit.get("source_status") or {}).get("errors", []))
            if isinstance(audit.get("source_status"), dict)
            else 0,
            "llm_count": (audit.get("llm_shortlist") or {}).get("count", 0)
            if isinstance(audit.get("llm_shortlist"), dict)
            else 0,
            "link_checked_count": (audit.get("link_checks") or {}).get("checked_count", 0)
            if isinstance(audit.get("link_checks"), dict)
            else 0,
        }
    jobs = _read_json(path / "jobs.json", [])
    return {"total_jobs": len(jobs) if isinstance(jobs, list) else 0}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _safe_snapshot_name(value: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z_.-]+", "-", value.strip())
    clean = clean.strip(".-")
    if not clean:
        raise ValueError("Nom de snapshot vide.")
    return clean[:80]
