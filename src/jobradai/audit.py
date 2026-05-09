from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobradai.config import AppConfig
from jobradai.early_career import early_career_signal
from jobradai.fingerprint import jobs_fingerprint
from jobradai.scoring import _annual_salary_estimate


def write_audit(output_dir: Path, config: AppConfig) -> dict[str, Any]:
    jobs_path = output_dir / "jobs.json"
    jobs = _read_json(jobs_path, [])
    sources = _read_json(output_dir / "sources.json", [])
    shortlist = _read_fresh_shortlist(output_dir / "llm_shortlist.json", jobs_path, jobs)
    link_checks = _read_fresh_job_artifact(output_dir / "link_checks.json", jobs_path, jobs)
    application_queue = _read_json(output_dir / "application_queue.json", {})
    history_dashboard = _read_json(output_dir / "history_dashboard.json", {})
    report = build_audit(
        jobs,
        sources,
        shortlist,
        config,
        link_checks=link_checks,
        application_queue=application_queue if isinstance(application_queue, dict) else {},
        history_dashboard=history_dashboard if isinstance(history_dashboard, dict) else {},
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "audit.md").write_text(_audit_markdown(report), encoding="utf-8")
    return report


def _read_fresh_shortlist(shortlist_path: Path, jobs_path: Path, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    if not shortlist_path.exists():
        return {}
    try:
        if jobs_path.exists() and shortlist_path.stat().st_mtime < jobs_path.stat().st_mtime:
            return {}
    except OSError:
        return {}
    data = _read_json(shortlist_path, {})
    if not isinstance(data, dict):
        return {}
    return data if _shortlist_matches_jobs(data, jobs) else {}


def _shortlist_matches_jobs(shortlist: dict[str, Any], jobs: list[dict[str, Any]]) -> bool:
    expected_fingerprint = jobs_fingerprint(jobs)
    actual_fingerprint = str(shortlist.get("jobs_fingerprint") or "")
    if actual_fingerprint:
        return actual_fingerprint == expected_fingerprint

    selection = shortlist.get("selection_summary", {})
    if not isinstance(selection, dict):
        return False
    try:
        if int(selection.get("available_jobs", -1)) != len(jobs):
            return False
    except (TypeError, ValueError):
        return False

    job_ids = {str(job.get("stable_id") or "") for job in jobs if isinstance(job, dict) and job.get("stable_id")}
    if not job_ids:
        return False
    item_ids = {
        str(item.get("stable_id") or "")
        for item in shortlist.get("items", [])
        if isinstance(item, dict) and item.get("stable_id")
    }
    batch_ids: set[str] = set()
    for batch in shortlist.get("batches", []):
        if not isinstance(batch, dict):
            continue
        ids = batch.get("ids", [])
        if isinstance(ids, list):
            batch_ids.update(str(item) for item in ids if item)
    candidate_ids = item_ids | batch_ids
    return bool(candidate_ids) and candidate_ids.issubset(job_ids)


def _read_fresh_job_artifact(artifact_path: Path, jobs_path: Path, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    if not artifact_path.exists():
        return {}
    try:
        if jobs_path.exists() and artifact_path.stat().st_mtime < jobs_path.stat().st_mtime:
            return {}
    except OSError:
        return {}
    data = _read_json(artifact_path, {})
    if not isinstance(data, dict):
        return {}
    expected_fingerprint = jobs_fingerprint(jobs)
    actual_fingerprint = str(data.get("jobs_fingerprint") or "")
    return data if actual_fingerprint == expected_fingerprint else {}


def build_audit(
    jobs: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    shortlist: dict[str, Any],
    config: AppConfig,
    *,
    link_checks: dict[str, Any] | None = None,
    application_queue: dict[str, Any] | None = None,
    history_dashboard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    markets = config.markets.get("markets", {})
    minimum_salary = float(config.profile.get("constraints", {}).get("minimum_annual_salary_eur", 0) or 0)
    by_market = Counter(str(job.get("market", "unknown")) for job in jobs)
    vie_jobs = [job for job in jobs if _is_vie_job(job)]
    salary_jobs = [job for job in jobs if job.get("salary") and not _is_vie_job(job)]
    salary_meets = [
        job for job in salary_jobs if (_job_annual_eur(job) or 0) >= minimum_salary
    ]
    remote_signal = [job for job in jobs if _has_remote_signal(job)]
    top30 = jobs[:30]
    priority_counts = Counter()
    if isinstance(shortlist, dict):
        priority_counts = Counter(str(item.get("priority", "unknown")) for item in shortlist.get("items", []))
    source_status = _source_status(sources)
    link_checks = link_checks or {}
    application_queue = application_queue or {}
    history_dashboard = history_dashboard or {}
    graduate_summary = _graduate_summary(jobs, application_queue, shortlist)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_jobs": len(jobs),
        "top30_count": len(top30),
        "markets": [_market_row(key, count, markets.get(key, {})) for key, count in by_market.most_common()],
        "source_status": source_status,
        "remote": {
            "all_with_signal": len(remote_signal),
            "all_share": _share(len(remote_signal), len(jobs)),
            "top30_with_signal": len([job for job in top30 if _has_remote_signal(job)]),
            "top30_share": _share(len([job for job in top30 if _has_remote_signal(job)]), len(top30)),
        },
        "salary": {
            "minimum_eur": minimum_salary,
            "scope": "hors VIE, car l'indemnite VIE n'est pas comparable a un brut annuel CDI",
            "all_with_salary": len(salary_jobs),
            "all_with_salary_share": _share(len(salary_jobs), len(jobs)),
            "all_meeting_minimum": len(salary_meets),
            "top30_with_salary": len([job for job in top30 if job.get("salary") and not _is_vie_job(job)]),
            "top30_meeting_minimum": len(
                [
                    job
                    for job in top30
                    if not _is_vie_job(job)
                    and (_job_annual_eur(job) or 0) >= minimum_salary
                ]
            ),
        },
        "structured_signals": {
            "with_deadline": len([job for job in jobs if job.get("deadline")]),
            "language_check_counts": dict(Counter(str(job.get("language_check") or "unknown") for job in jobs)),
            "remote_location_validity_counts": dict(Counter(str(job.get("remote_location_validity") or "unknown") for job in jobs)),
            "salary_currency_counts": dict(Counter(str(job.get("salary_currency") or "unknown") for job in salary_jobs)),
            "normalized_salary_count": len([job for job in salary_jobs if job.get("salary_normalized_annual_eur") is not None]),
            "experience_check_counts": dict(Counter(str(job.get("experience_check") or "unknown") for job in jobs)),
            "required_years_count": len([job for job in jobs if job.get("required_years") is not None]),
        },
        "vie": _vie_summary(vie_jobs),
        "language_market": _language_market_rows(by_market, markets),
        "llm_shortlist": {
            "available": bool(shortlist),
            "count": int(shortlist.get("count", 0)) if isinstance(shortlist, dict) else 0,
            "batch_count": len(shortlist.get("batches", [])) if isinstance(shortlist, dict) else 0,
            "selection_mode": shortlist.get("selection_mode", "") if isinstance(shortlist, dict) else "",
            "selection_summary": shortlist.get("selection_summary", {}) if isinstance(shortlist, dict) else {},
            "priority_counts": dict(priority_counts),
            "top_apply_now": [
                {
                    "title": item.get("title", ""),
                    "company": item.get("company", ""),
                    "market": item.get("market", ""),
                    "combined_score": item.get("combined_score", 0),
                    "level_fit": item.get("level_fit", ""),
                    "salary_check": item.get("salary_check", ""),
                    "remote_check": item.get("remote_check", ""),
                }
                for item in shortlist.get("items", [])
                if item.get("priority") == "apply_now"
            ][:10]
            if isinstance(shortlist, dict)
            else [],
        },
        "graduate_programs": graduate_summary,
        "link_checks": _link_check_summary(link_checks),
        "application_queue": _application_queue_summary(application_queue),
        "history_dashboard": _history_dashboard_summary(history_dashboard),
        "restriction": _restriction_summary(jobs, sources, shortlist, config),
        "p_items": _p_items(
            sources,
            shortlist,
            link_checks,
            application_queue,
            total_jobs=len(jobs),
            vie_count=len(vie_jobs),
            graduate_summary=graduate_summary,
        ),
    }


def _application_queue_summary(application_queue: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(application_queue, dict) or not application_queue:
        return {"available": False, "queue_count": 0, "start_date_counts": {}, "salary_counts": {}, "remote_counts": {}, "language_counts": {}, "remote_location_counts": {}}
    items = [item for item in application_queue.get("items", []) if isinstance(item, dict)]
    return {
        "available": True,
        "queue_count": int(application_queue.get("queue_count", len(items)) or 0),
        "status_counts": application_queue.get("queue_status_counts", {}),
        "priority_counts": application_queue.get("queue_priority_counts", {}),
        "start_date_counts": dict(Counter(str(item.get("last_start_date_check") or "unknown") for item in items)),
        "salary_counts": dict(Counter(str(item.get("last_salary_check") or "unknown") for item in items)),
        "remote_counts": dict(Counter(str(item.get("last_remote_check") or "unknown") for item in items)),
        "language_counts": dict(Counter(str(item.get("last_language_check") or "unknown") for item in items)),
        "remote_location_counts": dict(Counter(str(item.get("last_remote_location_validity") or "unknown") for item in items)),
    }


def _graduate_summary(
    jobs: list[dict[str, Any]],
    application_queue: dict[str, Any],
    shortlist: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for job in jobs:
        signal = early_career_signal(job)
        fit = str(signal.get("early_career_fit") or "none")
        if fit == "none":
            continue
        rows.append(
            {
                "title": job.get("title", ""),
                "stable_id": job.get("stable_id", ""),
                "company": job.get("company", ""),
                "market": job.get("market", ""),
                "score": job.get("score", 0),
                "fit": fit,
                "structured_program": bool(signal.get("structured_program")),
                "doctoral_program": bool(signal.get("doctoral_program")),
                "industrial_doctoral": bool(signal.get("industrial_doctoral")),
                "url": job.get("url", ""),
            }
        )
    rows.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}.get(str(item["fit"]), 9), -_safe_float(item["score"])))
    queue_items = application_queue.get("items", []) if isinstance(application_queue, dict) else []
    queue_items = [item for item in queue_items if isinstance(item, dict)]
    queue_early = [item for item in queue_items if item.get("early_career_fit") in {"high", "medium"}]
    target_ids = {str(row.get("stable_id") or "") for row in rows if row["fit"] in {"high", "medium"} and row.get("stable_id")}
    shortlist_items = shortlist.get("items", []) if isinstance(shortlist, dict) else []
    shortlist_items = [item for item in shortlist_items if isinstance(item, dict)]
    shortlist_early = [item for item in shortlist_items if str(item.get("stable_id") or "") in target_ids]
    return {
        "available": True,
        "detected": len(rows),
        "target_detected": len([row for row in rows if row["fit"] in {"high", "medium"}]),
        "structured_detected": len([row for row in rows if row["structured_program"]]),
        "doctoral_detected": len([row for row in rows if row["doctoral_program"]]),
        "industrial_doctoral_detected": len([row for row in rows if row["industrial_doctoral"]]),
        "fit_counts": dict(Counter(str(row["fit"]) for row in rows)),
        "queue_target_count": len(queue_early),
        "llm_target_count": len(shortlist_early),
        "llm_target_priority_counts": dict(Counter(str(item.get("priority") or "unknown") for item in shortlist_early)),
        "top": rows[:15],
    }


def _history_dashboard_summary(history_dashboard: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(history_dashboard, dict) or not history_dashboard:
        return {"available": False}
    keys = [
        "run_name",
        "previous_run_name",
        "current_jobs",
        "known_jobs",
        "new_jobs",
        "returned_jobs",
        "missing_this_run",
        "active_jobs",
        "stale_jobs",
        "expired_jobs",
        "queue_count",
        "deltas_vs_previous",
    ]
    return {"available": True, **{key: history_dashboard.get(key) for key in keys}}


def _link_check_summary(link_checks: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(link_checks, dict) or not link_checks:
        return {"available": False, "checked_count": 0, "status_counts": {}, "problem_count": 0}
    counts = link_checks.get("status_counts", {})
    counts = counts if isinstance(counts, dict) else {}
    problem_statuses = {"expired", "browser_required", "unreachable", "server_error", "needs_review", "invalid_url"}
    problem_count = sum(int(counts.get(status, 0) or 0) for status in problem_statuses)
    return {
        "available": True,
        "checked_count": int(link_checks.get("checked_count", 0) or 0),
        "status_counts": counts,
        "problem_count": problem_count,
        "direct_ok": int(counts.get("direct_ok", 0) or 0),
        "browser_required": int(counts.get("browser_required", 0) or 0),
        "expired": int(counts.get("expired", 0) or 0),
        "unreachable": int(counts.get("unreachable", 0) or 0),
        "needs_review": int(counts.get("needs_review", 0) or 0),
        "server_error": int(counts.get("server_error", 0) or 0),
    }


def _market_row(key: str, count: int, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "market": key,
        "count": count,
        "label": data.get("label", key),
        "market_score": data.get("market_score", 0),
        "practicality_score": data.get("practicality_score", 0),
        "salary_score": data.get("salary_score", 0),
        "visa_score": data.get("visa_score", 0),
        "language_score": data.get("language_score", 0),
        "notes": data.get("notes", ""),
    }


def _source_status(sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": len([source for source in sources if source.get("ok") and not source.get("skipped")]),
        "skipped": len([source for source in sources if source.get("skipped")]),
        "errors": [
            {"name": source.get("name", ""), "reason": source.get("reason", "")}
            for source in sources
            if not source.get("ok")
        ],
        "skipped_reasons": [
            {"name": source.get("name", ""), "reason": source.get("reason", "")}
            for source in sources
            if source.get("skipped")
        ],
    }


def _restriction_summary(
    jobs: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    shortlist: dict[str, Any],
    config: AppConfig,
) -> dict[str, Any]:
    run_config = config.sources.get("run", {})
    business_france_count = _source_count(sources, "business_france_vie")
    vie_jobs = [job for job in jobs if _is_vie_job(job)]
    selection_summary = shortlist.get("selection_summary", {}) if isinstance(shortlist, dict) else {}
    llm_mode = str(shortlist.get("selection_mode", "")) if isinstance(shortlist, dict) else ""
    min_score = float(run_config.get("min_score", 0) or 0)
    score_bands = {
        "35_45": len([job for job in jobs if 35 <= _safe_float(job.get("score")) < 45]),
        "45_60": len([job for job in jobs if 45 <= _safe_float(job.get("score")) < 60]),
        "60_75": len([job for job in jobs if 60 <= _safe_float(job.get("score")) < 75]),
        "75_plus": len([job for job in jobs if _safe_float(job.get("score")) >= 75]),
    }
    checks = {
        "min_score_large": min_score <= 35,
        "business_france_scan_all": bool(config.sources.get("business_france_vie", {}).get("scan_all", False)),
        "business_france_source_large": business_france_count >= 500,
        "llm_balanced_or_all": llm_mode in {"balanced", "all", "vie"},
        "llm_vie_coverage_ok": int(selection_summary.get("selected_vie", 0) or 0)
        >= min(20, int(selection_summary.get("available_vie", len(vie_jobs)) or 0)),
    }
    blocking = [name for name, ok in checks.items() if not ok]
    verdict = (
        "OK: corpus large, VIE scanne largement, seuil local bas, tri final confie au LLM."
        if not blocking
        else "A surveiller: " + ", ".join(blocking)
    )
    return {
        "verdict": verdict,
        "checks": checks,
        "min_score": min_score,
        "max_results_per_source": int(run_config.get("max_results_per_source", 0) or 0),
        "score_bands": score_bands,
        "business_france_vie_source_count": business_france_count,
        "final_vie_count": len(vie_jobs),
        "llm_selection_mode": llm_mode,
        "llm_selected_vie": int(selection_summary.get("selected_vie", 0) or 0),
        "llm_available_vie": int(selection_summary.get("available_vie", len(vie_jobs)) or 0),
    }


def _source_count(sources: list[dict[str, Any]], name: str) -> int:
    for source in sources:
        if str(source.get("name", "")) == name:
            return int(source.get("count", 0) or 0)
    return 0


def _language_market_rows(by_market: Counter[str], markets: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, count in by_market.most_common():
        data = markets.get(key, {})
        language_score = float(data.get("language_score", 0) or 0)
        rows.append(
            {
                "market": key,
                "count": count,
                "language_fit": _language_fit(key, language_score),
                "practicality_score": float(data.get("practicality_score", 0) or 0),
                "visa_score": float(data.get("visa_score", 0) or 0),
                "salary_score": float(data.get("salary_score", 0) or 0),
            }
        )
    return rows


def _vie_summary(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    allowances = [_vie_monthly_allowance(str(job.get("salary") or "")) for job in jobs]
    allowances = [value for value in allowances if value is not None]
    return {
        "count": len(jobs),
        "by_market": dict(Counter(str(job.get("market", "unknown")) for job in jobs)),
        "with_monthly_allowance": len(allowances),
        "min_monthly_allowance_eur": min(allowances) if allowances else None,
        "max_monthly_allowance_eur": max(allowances) if allowances else None,
        "top": [
            {
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "market": job.get("market", ""),
                "location": job.get("location", ""),
                "salary": job.get("salary", ""),
                "url": job.get("url", ""),
                "score": job.get("score", 0),
            }
            for job in jobs[:10]
        ],
    }


def _job_annual_eur(job: dict[str, Any]) -> float | None:
    value = job.get("salary_normalized_annual_eur")
    try:
        if value is not None:
            return float(value)
    except (TypeError, ValueError):
        pass
    return _annual_salary_estimate(str(job.get("salary") or ""))


def _language_fit(market: str, language_score: float) -> str:
    if market in {"france", "ireland", "uk", "singapore", "remote_europe"}:
        return "fort: francais/anglais compatible"
    if market in {"belgium", "luxembourg", "netherlands"}:
        return "bon: francais/anglais souvent utile"
    if market in {"switzerland", "germany"}:
        return "variable: anglais possible, langue locale a verifier"
    return "a verifier"


def _has_remote_signal(job: dict[str, Any]) -> bool:
    if bool(job.get("remote")):
        return True
    parts = [
        str(job.get("location") or ""),
        str(job.get("employment_type") or ""),
        str(job.get("description") or "")[:1200],
    ]
    blob = " ".join(parts).lower()
    if re.search(r"\b(remote|hybrid|hybride|teletravail|télétravail|home office|work from home)\b", blob):
        return True
    score_parts = job.get("score_parts")
    return isinstance(score_parts, dict) and float(score_parts.get("work_mode", 0) or 0) >= 86


def _p_items(
    sources: list[dict[str, Any]],
    shortlist: dict[str, Any],
    link_checks: dict[str, Any],
    application_queue: dict[str, Any],
    *,
    total_jobs: int,
    vie_count: int,
    graduate_summary: dict[str, Any],
) -> list[dict[str, str]]:
    errors = [source for source in sources if not source.get("ok")]
    skipped = {str(source.get("name", "")): str(source.get("reason", "")) for source in sources if source.get("skipped")}
    ok_names = {str(source.get("name", "")) for source in sources if source.get("ok") and not source.get("skipped")}
    items: list[dict[str, str]] = []
    if errors:
        items.append({"priority": "P0", "item": "Corriger les sources en erreur: " + ", ".join(str(e.get("name")) for e in errors)})
    elif total_jobs <= 0:
        items.append({"priority": "P0", "item": "Corpus vide: verifier jobs.json, le run d'ingestion et les filtres avant toute candidature."})
    else:
        items.append({"priority": "P0", "item": "Aucun blocage runtime detecte sur le dernier run."})
    if not sources:
        items.append({"priority": "P1", "item": "sources.json absent ou illisible: relancer le run complet pour confirmer l'etat des connecteurs."})
    if not shortlist:
        items.append({"priority": "P1", "item": "Executer le judge LLM balanced pour filtrer les faux positifs et couvrir les VIE/marches cibles."})
    link_summary = _link_check_summary(link_checks)
    if not link_summary["available"]:
        items.append({"priority": "P1", "item": "Executer la verification des liens/apply sur la shortlist avant candidature."})
    elif link_summary["expired"] or link_summary["unreachable"]:
        count = int(link_summary["expired"]) + int(link_summary["unreachable"])
        items.append({"priority": "P1", "item": f"Traiter {count} lien(s) expire(s) ou injoignable(s) detecte(s) par le verifier."})
    if link_summary["available"] and link_summary["browser_required"]:
        items.append({"priority": "P1", "item": f"Ouvrir manuellement {link_summary['browser_required']} lien(s) agregateur/protege(s) avant candidature."})
    if link_summary["available"] and (link_summary["needs_review"] or link_summary["server_error"]):
        count = int(link_summary["needs_review"]) + int(link_summary["server_error"])
        items.append({"priority": "P1", "item": f"Verifier manuellement {count} lien(s) en statut needs_review/server_error avant candidature."})
    items.append({"priority": "P1", "item": "Verifier manuellement salaire et remote avant candidature quand l'offre ne les publie pas."})
    queue_summary = _application_queue_summary(application_queue)
    start_counts = queue_summary.get("start_date_counts", {}) if queue_summary.get("available") else {}
    if int(start_counts.get("unknown", 0) or 0) or int(start_counts.get("too_soon", 0) or 0):
        items.append(
            {
                "priority": "P2",
                "item": "Utiliser start_date_check comme signal soft: confirmer avec RH les dates unknown/too_soon, sans skipper automatiquement.",
            }
        )
    items.append(
        {
            "priority": "P2",
            "item": "Utiliser deadline, language_check, remote_location_validity, required_years, experience_check et salary_normalized_annual_eur comme signaux soft; hard-filter seulement remote explicitement incompatible, langue locale obligatoire non compensee ou too_senior sans signal junior/all-levels.",
        }
    )
    if "vdab_generic" in skipped:
        missing_belgium_public = [name for name in ("forem", "actiris") if name not in ok_names]
        if missing_belgium_public:
            items.append(
                {
                    "priority": "P1",
                    "item": "Corriger/ajouter les sources Belgique publiques: " + ", ".join(missing_belgium_public) + ".",
                }
            )
        else:
            items.append(
                {
                    "priority": "PN",
                    "item": "VDAB direct est mis de cote: acces public/partenaire non exploitable ici, Forem et Actiris couvrent deja la Belgique sans cle.",
                }
            )
    if "serpapi_google_jobs" in skipped:
        items.append({"priority": "PN", "item": "SerpAPI Google Jobs est mis de cote: quota trop faible pour la routine."})
    if "business_france_vie" not in ok_names or vie_count <= 0:
        items.append({"priority": "P1", "item": "Activer/corriger la source officielle Business France VIE."})
    if int(graduate_summary.get("target_detected", 0) or 0) > 0 and int(graduate_summary.get("llm_target_count", 0) or 0) == 0:
        items.append(
            {
                "priority": "P2",
                "item": "Verifier la couverture graduate/early-career apres le prochain judge: le corpus en detecte, mais la queue n'en remonte pas encore.",
            }
        )
    items.append({"priority": "P2", "item": "Tester les candidatures/messages manuellement; aucune action LinkedIn automatique de masse."})
    return sorted(items, key=lambda item: _priority_rank(item["priority"]))


def _priority_rank(priority: str) -> tuple[int, str]:
    normalized = str(priority).strip().upper()
    if normalized == "PN":
        return 998, priority
    match = re.fullmatch(r"P(\d+)", normalized)
    if match:
        return int(match.group(1)), priority
    return 999, priority


def _audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Audit JobRadarAI",
        "",
        f"- Genere le: {report['generated_at']}",
        f"- Offres retenues: **{report['total_jobs']}**",
        f"- Sources OK: **{report['source_status']['ok']}** | ignorees: **{report['source_status']['skipped']}** | erreurs: **{len(report['source_status']['errors'])}**",
        f"- Remote/hybride detecte: **{report['remote']['all_with_signal']}** ({report['remote']['all_share']}%)",
        f"- Salaire publie hors VIE: **{report['salary']['all_with_salary']}** ({report['salary']['all_with_salary_share']}%), dont >= {report['salary']['minimum_eur']:.0f} EUR: **{report['salary']['all_meeting_minimum']}**",
        f"- Deadlines publiees: **{report['structured_signals']['with_deadline']}** | salaires normalises EUR/an: **{report['structured_signals']['normalized_salary_count']}**",
        f"- Annees d'experience extraites: **{report['structured_signals']['required_years_count']}**",
        f"- VIE Business France retenus: **{report['vie']['count']}**",
        "",
        "## Marches Et Langues",
        "",
    ]
    for row in report["markets"]:
        lines.append(
            f"- `{row['market']}`: {row['count']} offres | praticite {row['practicality_score']} | salaire {row['salary_score']} | visa {row['visa_score']} | langue {row['language_score']} - {row['notes']}"
        )
    lines.extend(["", "## Signaux Structures", ""])
    structured = report["structured_signals"]
    lines.append(f"- Langues: `{structured['language_check_counts']}`")
    lines.append(f"- Remote/localisation: `{structured['remote_location_validity_counts']}`")
    lines.append(f"- Experience: `{structured['experience_check_counts']}`")
    lines.append(f"- Devises salaire: `{structured['salary_currency_counts']}`")
    lines.extend(["", "## VIE", ""])
    vie = report["vie"]
    if vie["count"]:
        lines.append(
            f"- Missions retenues: **{vie['count']}** | indemnite mensuelle indiquee: **{vie['with_monthly_allowance']}** | marches: `{vie['by_market']}`"
        )
        if vie["min_monthly_allowance_eur"] is not None:
            lines.append(
                f"- Indemnite mensuelle observee: **{vie['min_monthly_allowance_eur']:.0f}** a **{vie['max_monthly_allowance_eur']:.0f}** EUR"
            )
        for item in vie["top"]:
            lines.append(
                f"- {item['title']} - {item['company']} ({item['market']}, {item['score']}) | {item['location']} | {item['salary']} | {item['url']}"
            )
    else:
        lines.append("- Aucune mission VIE retenue apres scoring/filtrage.")
    lines.extend(["", "## Shortlist LLM", ""])
    llm = report["llm_shortlist"]
    if llm["available"]:
        selection = llm.get("selection_summary", {})
        lines.append(
            f"- Offres jugees: **{llm['count']}** | batchs: **{llm['batch_count']}** | priorites: `{llm['priority_counts']}`"
        )
        lines.append(
            f"- Selection: `{llm.get('selection_mode') or 'n/a'}` | VIE selectionnes: **{selection.get('selected_vie', 0)}** / **{selection.get('available_vie', 0)}** | corpus juge: **{selection.get('selected_jobs', llm['count'])}** / **{selection.get('available_jobs', report['total_jobs'])}**"
        )
        for item in llm["top_apply_now"]:
            lines.append(
                f"- apply_now: {item['title']} - {item['company']} ({item['market']}, {item['combined_score']}) | niveau {item['level_fit']} | salaire {item['salary_check']} | remote {item['remote_check']}"
            )
    else:
        lines.append("- Judge LLM non encore execute.")
    graduate = report["graduate_programs"]
    lines.extend(["", "## Graduate / Early Careers / Doctoral", ""])
    lines.append(
        f"- Signaux detectes: **{graduate['detected']}** | high/medium: **{graduate['target_detected']}** | structures: **{graduate['structured_detected']}** | doctorats/CIFRE: **{graduate.get('doctoral_detected', 0)}** dont industriels/CIFRE: **{graduate.get('industrial_doctoral_detected', 0)}** | LLM: **{graduate['llm_target_count']}** | queue: **{graduate['queue_target_count']}**"
    )
    lines.append(f"- Fits: `{graduate['fit_counts']}` | priorites LLM: `{graduate['llm_target_priority_counts']}`")
    for item in graduate["top"][:8]:
        lines.append(
            f"- `{item['fit']}` {item['title']} - {item['company']} ({item['market']}, {item['score']}) | {item['url']}"
        )
    links = report["link_checks"]
    lines.extend(["", "## Verification Liens", ""])
    if links["available"]:
        lines.append(
            f"- Liens verifies: **{links['checked_count']}** | statuts: `{links['status_counts']}` | problemes: **{links['problem_count']}**"
        )
    else:
        lines.append("- Verification liens/apply non encore executee.")
    queue = report["application_queue"]
    history = report["history_dashboard"]
    lines.extend(["", "## Queue Multi-Run", ""])
    if queue["available"]:
        lines.append(
            f"- Queue dedupee: **{queue['queue_count']}** | priorites: `{queue.get('priority_counts', {})}` | statuts: `{queue.get('status_counts', {})}`"
        )
        lines.append(
            f"- Checks queue: start `{queue.get('start_date_counts', {})}` | salaire `{queue.get('salary_counts', {})}` | remote `{queue.get('remote_counts', {})}` | langue `{queue.get('language_counts', {})}` | remote/localisation `{queue.get('remote_location_counts', {})}`"
        )
    else:
        lines.append("- Queue multi-run non encore generee.")
    if history["available"]:
        lines.append(
            f"- Historique: run `{history.get('run_name')}` vs `{history.get('previous_run_name') or 'n/a'}` | nouvelles **{history.get('new_jobs', 0)}** | disparues **{history.get('missing_this_run', 0)}** | stale **{history.get('stale_jobs', 0)}** | expirees **{history.get('expired_jobs', 0)}**"
        )
    restriction = report["restriction"]
    lines.extend(
        [
            "",
            "## Restriction",
            "",
            f"- Verdict: {restriction['verdict']}",
            f"- Seuil local: **{restriction['min_score']:.0f}** | max/source: **{restriction['max_results_per_source']}** | score bands: `{restriction['score_bands']}`",
            f"- Business France VIE brut: **{restriction['business_france_vie_source_count']}** | VIE retenus: **{restriction['final_vie_count']}** | VIE juges LLM: **{restriction['llm_selected_vie']}** / **{restriction['llm_available_vie']}**",
        ]
    )
    lines.extend(["", "## P0 A PN", ""])
    for item in report["p_items"]:
        lines.append(f"- `{item['priority']}`: {item['item']}")
    return "\n".join(lines) + "\n"


def _share(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(value * 100 / total, 1)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_vie_job(job: dict[str, Any]) -> bool:
    source = str(job.get("source") or "").lower()
    employment = str(job.get("employment_type") or "").lower()
    tags = " ".join(str(tag) for tag in job.get("tags", [])).lower() if isinstance(job.get("tags"), list) else ""
    return "business france vie" in source or bool(re.search(r"\bv\.?i\.?e\b", employment)) or "volontariat international en entreprise" in tags


def _vie_monthly_allowance(salary: str) -> float | None:
    raw = salary.lower()
    if "vie" not in raw and "volontariat" not in raw:
        return None
    values: list[float] = []
    for match in re.finditer(r"\d+(?:[ .]\d{3})*(?:[,.]\d+)?", raw):
        compact = match.group(0).replace(" ", "")
        if re.fullmatch(r"\d+[,.]\d{1,2}", compact):
            compact = compact.replace(",", ".")
        else:
            compact = compact.replace(".", "").replace(",", "")
        try:
            number = float(compact)
        except ValueError:
            continue
        if number >= 10:
            values.append(number)
    if not values:
        return None
    best = max(values)
    if best > 10000:
        return best / 12
    return best


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
