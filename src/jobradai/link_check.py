from __future__ import annotations

import concurrent.futures
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobradai.fingerprint import jobs_fingerprint
from jobradai.redaction import redact_sensitive, redact_url


AGGREGATOR_DOMAINS = (
    "indeed.",
    "jooble.",
    "linkedin.",
    "glassdoor.",
)
ANTI_BOT_PATTERNS = (
    "security check",
    "cloudflare",
    "captcha",
    "access denied",
    "verify you are human",
    "unusual traffic",
)
ACTIONABLE_PRIORITIES = {"apply_now", "shortlist", "maybe"}


def verify_links(
    *,
    input_path: Path,
    output_dir: Path,
    shortlist_path: Path | None = None,
    limit: int = 160,
    timeout_seconds: int = 10,
    workers: int = 12,
) -> dict[str, Any]:
    jobs = _load_jobs(input_path)
    shortlist = _load_shortlist(shortlist_path) if shortlist_path else {}
    selected, selection = _build_link_selection(jobs, shortlist, limit=limit)
    output_dir.mkdir(parents=True, exist_ok=True)
    max_workers = max(1, min(workers, max(1, len(selected))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        items = list(executor.map(lambda job: check_job_link(job, timeout_seconds=timeout_seconds), selected))
    status_counts = dict(Counter(str(item.get("status", "unknown")) for item in items))
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "jobs_fingerprint": jobs_fingerprint(jobs),
        "limit": limit,
        "timeout_seconds": timeout_seconds,
        "workers": max_workers,
        "available_jobs": len(jobs),
        "checked_count": len(items),
        "selection": selection,
        "status_counts": status_counts,
        "items": items,
    }
    (output_dir / "link_checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "link_checks.md").write_text(_link_markdown(result), encoding="utf-8")
    return result


def check_job_link(job: dict[str, Any], *, timeout_seconds: int = 10) -> dict[str, Any]:
    url = str(job.get("apply_url") or job.get("url") or "").strip()
    base = {
        "stable_id": str(job.get("stable_id") or ""),
        "title": str(job.get("title") or ""),
        "company": str(job.get("company") or ""),
        "source": str(job.get("source") or ""),
        "source_type": str(job.get("source_type") or ""),
        "market": str(job.get("market") or ""),
        "url": redact_url(url),
        "domain": _domain(url),
    }
    parsed = _parse_http_url(url)
    if parsed is None:
        return {**base, "status": "invalid_url", "http_status": None, "reason": "URL absente ou non HTTP(S)."}
    if _is_aggregator(parsed.netloc):
        return {
            **base,
            "status": "browser_required",
            "http_status": None,
            "reason": "Lien agregateur/scraper a verifier dans un navigateur avant candidature.",
        }
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "JobRadarAI/0.1 (+local personal job search; link check)",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(4096).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            return {
                **base,
                "status": _classify_http_response(parsed.netloc, int(response.status), body),
                "http_status": int(response.status),
                "final_url": redact_url(response.geturl()),
                "reason": _reason_for_response(parsed.netloc, int(response.status), body),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        return {
            **base,
            "status": _classify_http_response(parsed.netloc, int(exc.code), body),
            "http_status": int(exc.code),
            "final_url": redact_url(exc.url),
            "reason": _reason_for_response(parsed.netloc, int(exc.code), body),
        }
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
        return {
            **base,
            "status": "unreachable",
            "http_status": None,
            "reason": redact_sensitive(str(exc))[:300],
        }


def _select_jobs_for_link_check(
    jobs: list[dict[str, Any]],
    shortlist: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    return _build_link_selection(jobs, shortlist, limit=limit)[0]


def _build_link_selection(
    jobs: list[dict[str, Any]],
    shortlist: dict[str, Any],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected_ids: set[str] = set()
    skipped_ids: set[str] = set()
    selected: list[dict[str, Any]] = []
    selected_from_shortlist = 0
    selected_from_top = 0
    shortlist_priority_counts: Counter[str] = Counter()

    def add(job: dict[str, Any]) -> bool:
        stable_id = str(job.get("stable_id") or job.get("url") or "")
        if not stable_id or stable_id in selected_ids:
            return False
        selected_ids.add(stable_id)
        selected.append(job)
        return True

    by_id = {str(job.get("stable_id") or ""): job for job in jobs if isinstance(job, dict)}
    for item in shortlist.get("items", []) if isinstance(shortlist, dict) else []:
        if not isinstance(item, dict):
            continue
        stable_id = str(item.get("stable_id") or "")
        priority = str(item.get("priority") or "unknown").strip().lower() or "unknown"
        shortlist_priority_counts[priority] += 1
        if priority == "skip":
            if stable_id:
                skipped_ids.add(stable_id)
            continue
        if priority not in ACTIONABLE_PRIORITIES and priority != "unknown":
            continue
        job = by_id.get(stable_id)
        if job and add(job):
            selected_from_shortlist += 1
    capped = len(jobs) if limit <= 0 else max(0, limit)
    for job in jobs[:capped]:
        stable_id = str(job.get("stable_id") or "")
        if stable_id and stable_id in skipped_ids:
            continue
        if add(job):
            selected_from_top += 1
    selection = {
        "mode": "llm_actionable_plus_top_non_skip" if shortlist_priority_counts else "top_only",
        "top_limit": capped,
        "shortlist_items": sum(shortlist_priority_counts.values()),
        "shortlist_priority_counts": dict(shortlist_priority_counts),
        "shortlist_skip_items": int(shortlist_priority_counts.get("skip", 0)),
        "selected_from_shortlist": selected_from_shortlist,
        "selected_from_top": selected_from_top,
        "selected_count": len(selected),
    }
    return selected, selection


def _classify_http_response(host: str, status: int, body: str) -> str:
    text = body.lower()
    if status in {404, 410}:
        return "expired"
    if status in {401, 403, 429} or _is_browser_only_conflict(host, status):
        return "browser_required"
    if any(pattern in text for pattern in ANTI_BOT_PATTERNS):
        return "browser_required"
    if _is_aggregator(host):
        return "browser_required"
    if 200 <= status < 400:
        return "direct_ok"
    if 500 <= status < 600:
        return "server_error"
    return "needs_review"


def _reason_for_response(host: str, status: int, body: str) -> str:
    if status in {404, 410}:
        return "Offre possiblement expiree ou lien supprime."
    if status in {401, 403, 429} or _is_browser_only_conflict(host, status):
        return f"HTTP {status}: acces protege, rate-limit ou verification navigateur requise."
    if any(pattern in body.lower() for pattern in ANTI_BOT_PATTERNS):
        return "Page protegee par anti-bot ou verification humaine."
    if _is_aggregator(host):
        return "Agregateur a ouvrir manuellement avant candidature."
    if 200 <= status < 400:
        return "Lien direct accessible cote serveur."
    if 500 <= status < 600:
        return f"HTTP {status}: erreur temporaire possible cote site."
    return f"HTTP {status}: verifier manuellement."


def _link_markdown(result: dict[str, Any]) -> str:
    counts = result.get("status_counts", {})
    lines = [
        "# Verification Liens",
        "",
        f"- Genere le: {result.get('generated_at', '')}",
        f"- Offres verifiees: **{result.get('checked_count', 0)}** / **{result.get('available_jobs', 0)}**",
        f"- Selection: `{result.get('selection', {})}`",
        f"- Statuts: `{counts}`",
        "",
        "## A Traiter En Priorite",
        "",
    ]
    priority_statuses = {"expired", "browser_required", "unreachable", "server_error", "needs_review", "invalid_url"}
    priority = [item for item in result.get("items", []) if item.get("status") in priority_statuses]
    if not priority:
        lines.append("- Aucun lien problematique dans l'echantillon verifie.")
    for item in priority[:80]:
        lines.append(
            f"- `{item.get('status')}` HTTP `{item.get('http_status') or 'n/a'}` | "
            f"{item.get('title')} - {item.get('company')} | {item.get('source')} | "
            f"{item.get('reason')} | {item.get('url')}"
        )
    lines.extend(["", "## Direct OK", ""])
    for item in [row for row in result.get("items", []) if row.get("status") == "direct_ok"][:80]:
        lines.append(
            f"- {item.get('title')} - {item.get('company')} | {item.get('source')} | {item.get('url')}"
        )
    return "\n".join(lines) + "\n"


def _load_jobs(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Format jobs invalide dans {path}: liste attendue.")
    return [job for job in data if isinstance(job, dict)]


def _load_shortlist(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return _with_shortlist_augments(path.parent, data)


def _with_shortlist_augments(output_dir: Path, shortlist: dict[str, Any]) -> dict[str, Any]:
    augment_dir = output_dir / "llm_augments"
    if not augment_dir.exists():
        return shortlist
    base_items = [item for item in shortlist.get("items", []) if isinstance(item, dict)]
    seen = {str(item.get("stable_id") or "") for item in base_items}
    augmented: list[dict[str, Any]] = []
    augment_files: list[str] = []
    for path in sorted(augment_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items = data.get("items", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            continue
        added_from_file = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            stable_id = str(item.get("stable_id") or "")
            if not stable_id or stable_id in seen:
                continue
            seen.add(stable_id)
            augmented.append(item)
            added_from_file += 1
        if added_from_file:
            augment_files.append(str(path))
    if not augmented:
        return shortlist
    merged_items = base_items + augmented
    priority_counts = Counter(str(item.get("priority") or "unknown") for item in merged_items)
    merged = dict(shortlist)
    merged["items"] = merged_items
    merged["count"] = len(merged_items)
    merged["priority_counts"] = dict(priority_counts)
    merged["augment_count"] = len(augmented)
    merged["augment_files"] = augment_files
    return merged


def _parse_http_url(url: str) -> urllib.parse.SplitResult | None:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed


def _domain(url: str) -> str:
    parsed = _parse_http_url(url)
    return parsed.netloc.lower() if parsed else ""


def _is_aggregator(host: str) -> bool:
    normalized = host.lower()
    return any(domain in normalized for domain in AGGREGATOR_DOMAINS)


def _is_browser_only_conflict(host: str, status: int) -> bool:
    return status == 409 and host.lower().endswith("francetravail.fr")
