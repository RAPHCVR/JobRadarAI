from __future__ import annotations

import traceback
from dataclasses import dataclass, field
import re
from typing import Callable

from jobradai.config import AppConfig
from jobradai.http import HttpClient
from jobradai.models import Job, SourceRun
from jobradai.redaction import redact_sensitive
from jobradai.scoring import score_jobs
from jobradai.sources.ats import fetch_ats_feed
from jobradai.sources.optional import (
    fetch_adzuna,
    fetch_france_travail,
    fetch_jobspy_direct,
    fetch_jobspy_api,
    fetch_jooble,
    fetch_serpapi,
    fetch_vdab_generic,
)
from jobradai.sources.public import (
    fetch_actiris,
    fetch_arbeitnow,
    fetch_business_france_vie,
    fetch_forem,
    fetch_himalayas,
    fetch_jobicy,
    fetch_remoteok,
    fetch_remotive,
)


@dataclass(slots=True)
class PipelineResult:
    jobs: list[Job]
    source_runs: list[SourceRun] = field(default_factory=list)


def run_pipeline(config: AppConfig, max_per_source: int | None = None) -> PipelineResult:
    http = HttpClient()
    source_runs: list[SourceRun] = []
    jobs: list[Job] = []

    public_sources: list[tuple[str, Callable[[dict, HttpClient], list[Job]]]] = [
        ("business_france_vie", fetch_business_france_vie),
        ("forem", fetch_forem),
        ("actiris", fetch_actiris),
        ("remotive", fetch_remotive),
        ("arbeitnow", fetch_arbeitnow),
        ("remoteok", fetch_remoteok),
        ("jobicy", fetch_jobicy),
        ("himalayas", fetch_himalayas),
    ]
    enabled_public = config.sources.get("public_sources", {})
    for name, fetcher in public_sources:
        if not enabled_public.get(name, False):
            source_runs.append(SourceRun(name=name, ok=True, skipped=True, reason="desactive"))
            continue
        _collect(name, lambda f=fetcher: f(config.sources, http), jobs, source_runs, max_per_source)

    for feed in config.sources.get("ats_feeds", []):
        name = f"ats:{feed.get('name', feed.get('url', 'unknown'))}"
        _collect(name, lambda current=feed: fetch_ats_feed(current, http), jobs, source_runs, max_per_source)

    optional_sources: list[tuple[str, Callable[[dict, HttpClient], tuple[list[Job], str]]]] = [
        ("adzuna", fetch_adzuna),
        ("france_travail", fetch_france_travail),
        ("serpapi_google_jobs", fetch_serpapi),
        ("jooble", fetch_jooble),
        ("jobspy_api", fetch_jobspy_api),
        ("jobspy_direct", fetch_jobspy_direct),
        ("vdab_generic", fetch_vdab_generic),
    ]
    enabled_optional = config.sources.get("optional_sources", {})
    for name, fetcher in optional_sources:
        if not enabled_optional.get(name, False):
            if bool(config.sources.get("run", {}).get("report_disabled_sources", False)):
                source_runs.append(SourceRun(name=name, ok=True, skipped=True, reason="desactive"))
            continue
        def optional_call(f=fetcher) -> list[Job]:
            rows, reason = f(config.sources, http)
            if reason:
                reason = redact_sensitive(reason)
                if _optional_reason_is_soft_skip(reason):
                    source_runs.append(SourceRun(name=name, ok=True, skipped=True, reason=reason))
                else:
                    source_runs.append(SourceRun(name=name, ok=False, skipped=False, reason=reason))
            return rows
        _collect(name, optional_call, jobs, source_runs, max_per_source, skip_empty_run_already_recorded=True)

    jobs = dedupe_jobs(jobs)
    jobs = score_jobs(jobs, config.profile, config.markets)
    target_markets = set(config.profile.get("search", {}).get("target_markets", []))
    if target_markets:
        jobs = [job for job in jobs if job.market in target_markets]
    min_score = float(config.sources.get("run", {}).get("min_score", 0))
    if min_score > 0:
        jobs = [job for job in jobs if job.score >= min_score]
    return PipelineResult(jobs=jobs, source_runs=source_runs)


def _optional_reason_is_soft_skip(reason: str) -> bool:
    normalized = reason.strip().lower()
    soft_prefixes = (
        "missing_config:",
        "service_unavailable:",
    )
    return normalized.startswith(soft_prefixes)


def dedupe_jobs(jobs: list[Job]) -> list[Job]:
    best: dict[str, Job] = {}
    loose_index: dict[str, str] = {}
    for job in jobs:
        if not job.title or not job.company or not job.url:
            continue
        key = _soft_dedupe_key(job) or _dedupe_key(job)
        loose = _loose_dedupe_key(job)
        if loose in loose_index:
            existing_key = loose_index[loose]
            existing = best.get(existing_key)
            if existing and _companies_similar(existing.company, job.company):
                key = existing_key
        current = best.get(key)
        if current is None or _source_rank(job.source_type) > _source_rank(current.source_type):
            best[key] = job
            loose_index[loose] = key
    return list(best.values())


def _collect(
    name: str,
    call: Callable[[], list[Job]],
    jobs: list[Job],
    source_runs: list[SourceRun],
    max_per_source: int | None,
    skip_empty_run_already_recorded: bool = False,
) -> None:
    before = len(source_runs)
    try:
        rows = call()
        if max_per_source:
            rows = rows[:max_per_source]
        jobs.extend(rows)
        if rows or not skip_empty_run_already_recorded or len(source_runs) == before:
            source_runs.append(SourceRun(name=name, ok=True, count=len(rows), skipped=False))
    except Exception as exc:  # noqa: BLE001 - source isolation is intentional
        reason = f"{type(exc).__name__}: {exc}"
        if len(str(exc)) < 300:
            reason = redact_sensitive(reason)
        else:
            reason = redact_sensitive(traceback.format_exc(limit=1))
        source_runs.append(SourceRun(name=name, ok=False, count=0, reason=reason))


def _dedupe_key(job: Job) -> str:
    url = job.url.split("?")[0].rstrip("/").lower()
    title = job.title.lower().strip()
    company = job.company.lower().strip()
    return f"{company}|{title}|{url}"


def _soft_dedupe_key(job: Job) -> str:
    title = _norm_for_dedupe(job.title)
    company = _norm_for_dedupe(job.company)
    location = _norm_for_dedupe(job.location)
    return f"soft|{company}|{title}|{location}"


def _norm_for_dedupe(value: str) -> str:
    lower = value.lower()
    lower = re.sub(r"\b(m/f/d|f/m/d|h/f|it|freelance|contract|permanent|perm|hybrid|remote|holding|gmbh|ltd|limited|inc|sa|sas|ag)\b", " ", lower)
    lower = re.sub(r"[^a-z0-9]+", " ", lower)
    return re.sub(r"\s+", " ", lower).strip()


def _loose_dedupe_key(job: Job) -> str:
    title = _norm_for_dedupe(job.title)
    location = _norm_for_dedupe(job.location)
    return f"loose|{title}|{location}"


def _companies_similar(a: str, b: str) -> bool:
    left = _norm_for_dedupe(a)
    right = _norm_for_dedupe(b)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _source_rank(source_type: str) -> int:
    return {
        "official_api": 5,
        "ats": 4,
        "paid_api": 3,
        "public_api": 2,
        "scraper_api": 1,
    }.get(source_type, 0)
