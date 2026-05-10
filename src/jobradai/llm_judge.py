from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobradai.early_career import early_career_signal
from jobradai.fingerprint import jobs_fingerprint
from jobradai.text import clean_html, normalize_space


DEFAULT_BASE_URL = "https://codex.raphcvr.me/v1"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_REASONING_EFFORT = "medium"
DEFAULT_SELECTION_MODE = "wide"
DEFAULT_TIMEOUT_SECONDS = 360
DEFAULT_CONCURRENCY = 1
DEFAULT_BATCH_SIZE = 10
DEFAULT_TRANSPORT = "auto"
LOCAL_SCORE_WEIGHT = 0.40
LLM_SCORE_WEIGHT = 0.60
LLM_BATCH_MAX_ATTEMPTS = 3
LLM_BATCH_RETRY_SECONDS = 45
DEFAULT_MAX_FALLBACK_RATIO = 0.01
VALID_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}
VALID_TRANSPORTS = {"auto", "sdk", "raw"}
VALID_SELECTION_MODES = {"top", "balanced", "wide", "vie", "all"}
VALID_PRIORITIES = {"apply_now", "shortlist", "maybe", "skip"}
VALID_LEVEL_FITS = {"junior_ok", "stretch", "too_senior", "too_junior", "unknown"}
VALID_SALARY_CHECKS = {"meets_or_likely", "unknown", "below_min"}
VALID_REMOTE_CHECKS = {"meets", "unknown", "weak"}
VALID_START_DATE_CHECKS = {"compatible", "too_soon", "unknown"}
VALID_LANGUAGE_CHECKS = {"english_ok", "french_ok", "local_language_required", "unknown"}
VALID_REMOTE_LOCATION_VALIDITY = {"compatible", "restricted", "incompatible", "unknown"}


class LLMJudgeError(RuntimeError):
    pass


class LLMCallError(LLMJudgeError):
    pass


class LLMHTTPError(LLMCallError):
    def __init__(self, status: int, url: str, body: str) -> None:
        self.status = status
        self.url = url
        self.body = _redact(body)
        super().__init__(f"LLM HTTP {status} sur {_safe_url(url)}: {self.body[:800]}")


@dataclass(slots=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str = DEFAULT_MODEL
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    transport: str = DEFAULT_TRANSPORT

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        timeout_seconds: int | None = None,
        transport: str | None = None,
    ) -> "LLMSettings":
        effort = reasoning_effort or os.environ.get("JOBRADAR_LLM_REASONING_EFFORT") or DEFAULT_REASONING_EFFORT
        effort = effort.lower().strip()
        if effort not in VALID_EFFORTS:
            raise LLMJudgeError(
                "JOBRADAR_LLM_REASONING_EFFORT invalide. "
                f"Valeurs supportees: {', '.join(sorted(VALID_EFFORTS))}."
            )
        selected_transport = (transport or os.environ.get("JOBRADAR_LLM_TRANSPORT") or DEFAULT_TRANSPORT).lower().strip()
        if selected_transport not in VALID_TRANSPORTS:
            raise LLMJudgeError(
                "JOBRADAR_LLM_TRANSPORT invalide. "
                f"Valeurs supportees: {', '.join(sorted(VALID_TRANSPORTS))}."
            )
        return cls(
            base_url=(base_url or os.environ.get("JOBRADAR_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
            api_key=os.environ.get("JOBRADAR_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
            model=model or os.environ.get("JOBRADAR_LLM_MODEL") or DEFAULT_MODEL,
            reasoning_effort=effort,
            timeout_seconds=timeout_seconds
            or int(
                os.environ.get("JOBRADAR_LLM_TIMEOUT_SECONDS")
                or os.environ.get("JOBRADAR_LLM_TIMEOUT")
                or str(DEFAULT_TIMEOUT_SECONDS)
            ),
            transport=selected_transport,
        )


@dataclass(slots=True)
class ModelResult:
    text: str
    endpoint: str
    response_id: str = ""
    usage: dict[str, Any] | None = None


def judge_jobs(
    *,
    input_path: Path,
    output_dir: Path,
    profile: dict[str, Any],
    limit: int = 30,
    batch_size: int = DEFAULT_BATCH_SIZE,
    concurrency: int = DEFAULT_CONCURRENCY,
    selection_mode: str = DEFAULT_SELECTION_MODE,
    settings: LLMSettings | None = None,
    dry_run: bool = False,
    progress: bool = False,
    max_fallback_ratio: float = DEFAULT_MAX_FALLBACK_RATIO,
) -> dict[str, Any]:
    jobs = _load_jobs(input_path)
    selected = _select_jobs(jobs, limit=limit, mode=selection_mode)
    profile_summary = _profile_summary(profile)
    compact_jobs = [_compact_job(job) for job in selected]
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_size = max(1, min(batch_size, max(1, len(selected))))
    chunks = _chunks(list(zip(selected, compact_jobs, strict=True)), batch_size)
    concurrency = max(1, min(concurrency, max(1, len(chunks))))

    if dry_run:
        preview = {
            "generated_at": _now(),
            "dry_run": True,
            "batch_size": batch_size,
            "concurrency": concurrency,
            "score_weights": {"local": LOCAL_SCORE_WEIGHT, "llm": LLM_SCORE_WEIGHT},
            "selection_mode": selection_mode,
            "profile": profile_summary,
            "jobs": compact_jobs,
            "expected_output": _expected_schema(),
        }
        _write_json(output_dir / "llm_payload_preview.json", preview)
        return preview

    preview_path = output_dir / "llm_payload_preview.json"
    if preview_path.exists():
        preview_path.unlink()

    settings = settings or LLMSettings.from_env()
    if not settings.api_key:
        raise LLMJudgeError(
            "Cle LLM absente. Definis JOBRADAR_LLM_API_KEY dans config/.env "
            "ou OPENAI_API_KEY dans l'environnement."
        )
    _remove_previous_shortlist_outputs(output_dir)

    batch_runs: list[dict[str, Any]]
    judgements, batch_runs = _judge_chunks(
        settings,
        profile_summary,
        chunks,
        concurrency=concurrency,
        progress=progress,
    )
    quality = _judge_quality_summary(batch_runs, expected_count=len(selected))
    _validate_judge_quality(quality, max_fallback_ratio=max_fallback_ratio)

    annotated = _merge_judgements(selected, judgements)
    annotated.sort(key=lambda item: (item["combined_score"], item["score"]), reverse=True)
    endpoints = sorted({str(run.get("endpoint", "")) for run in batch_runs if run.get("endpoint")})
    response_ids = [str(run.get("response_id", "")) for run in batch_runs if run.get("response_id")]
    priority_counts = _counts(str(item.get("priority", "")) for item in annotated)
    result = {
        "generated_at": _now(),
        "model": settings.model,
        "base_url": settings.base_url,
        "reasoning_effort": settings.reasoning_effort,
        "transport": settings.transport,
        "endpoint": ",".join(endpoints) if endpoints else "",
        "response_id": response_ids[0] if response_ids else "",
        "response_ids": response_ids,
        "usage": _sum_usage(run.get("usage") for run in batch_runs),
        "batches": batch_runs,
        "batch_size": batch_size,
        "concurrency": concurrency,
        "score_weights": {"local": LOCAL_SCORE_WEIGHT, "llm": LLM_SCORE_WEIGHT},
        "quality": quality,
        "fallback_items": quality["fallback_items"],
        "fallback_batches": quality["fallback_batches"],
        "fallback_ratio": quality["fallback_ratio"],
        "endpoint_counts": quality["endpoint_counts"],
        "priority_counts": priority_counts,
        "input": str(input_path),
        "jobs_fingerprint": jobs_fingerprint(jobs),
        "limit": limit,
        "selection_mode": selection_mode,
        "selection_summary": _selection_summary(jobs, selected),
        "count": len(annotated),
        "items": annotated,
    }
    _write_json(output_dir / "llm_shortlist.json", result)
    _write_markdown(output_dir / "llm_shortlist.md", result)
    return result


def _select_jobs(jobs: list[dict[str, Any]], *, limit: int, mode: str) -> list[dict[str, Any]]:
    normalized_mode = normalize_space(mode).lower() or DEFAULT_SELECTION_MODE
    if normalized_mode not in VALID_SELECTION_MODES:
        raise LLMJudgeError(
            "Mode de selection LLM invalide. "
            f"Valeurs supportees: {', '.join(sorted(VALID_SELECTION_MODES))}."
        )
    if normalized_mode == "all" or limit <= 0:
        return jobs
    capped_limit = max(1, limit)
    if normalized_mode == "top":
        return jobs[:capped_limit]
    if normalized_mode == "vie":
        selected = sorted([job for job in jobs if _is_vie_job(job)], key=_fit_rank, reverse=True)
        return (selected or jobs)[:capped_limit]
    if normalized_mode == "wide":
        return _select_wide_jobs(jobs, capped_limit)
    return _select_balanced_jobs(jobs, capped_limit)


def _select_balanced_jobs(jobs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(candidates: list[dict[str, Any]], quota: int) -> None:
        if quota <= 0:
            return
        for job in candidates:
            if len(selected) >= limit or quota <= 0:
                return
            key = str(job.get("stable_id") or job.get("url") or id(job))
            if key in seen:
                continue
            seen.add(key)
            selected.append(job)
            quota -= 1

    add(jobs, max(1, int(limit * 0.45)))
    vie_jobs = sorted([job for job in jobs if _is_vie_job(job)], key=_fit_rank, reverse=True)
    vie_quota = max(1, int(limit * 0.25))
    if limit >= 100:
        vie_quota = max(vie_quota, 30)
    add(vie_jobs, vie_quota)
    early_jobs = sorted([job for job in jobs if _is_target_early_career(job)], key=_fit_rank, reverse=True)
    early_quota = max(1, int(limit * 0.10))
    if limit >= 100:
        early_quota = max(early_quota, 15)
    add(early_jobs, early_quota)

    market_order = _market_order()
    market_buckets = {market: [job for job in jobs if job.get("market") == market] for market in market_order}
    while len(selected) < limit:
        progressed = False
        for market in market_order:
            before = len(selected)
            add(market_buckets.get(market, []), 1)
            progressed = progressed or len(selected) > before
            if len(selected) >= limit:
                break
        if not progressed:
            break

    add(jobs, limit - len(selected))
    return selected


def _select_wide_jobs(jobs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    score_sorted = sorted(jobs, key=lambda job: (_safe_float(job.get("score"), 0.0), _fit_rank(job)), reverse=True)

    def add(candidates: list[dict[str, Any]], quota: int) -> None:
        if quota <= 0:
            return
        for job in candidates:
            if len(selected) >= limit or quota <= 0:
                return
            key = str(job.get("stable_id") or job.get("url") or id(job))
            if key in seen:
                continue
            seen.add(key)
            selected.append(job)
            quota -= 1

    high_signal = [job for job in score_sorted if _safe_float(job.get("score"), 0.0) >= 60.0]
    add(high_signal, limit)
    if len(selected) >= limit:
        return selected

    vie_jobs = sorted(
        [job for job in jobs if _is_vie_job(job) and _safe_float(job.get("score"), 0.0) >= 45.0],
        key=_fit_rank,
        reverse=True,
    )
    add(vie_jobs, max(30, int(limit * 0.12)))

    early_jobs = sorted(
        [
            job
            for job in jobs
            if _is_target_early_career(job) and _safe_float(job.get("score"), 0.0) >= 45.0
        ],
        key=_fit_rank,
        reverse=True,
    )
    add(early_jobs, max(20, int(limit * 0.08)))

    market_buckets = {
        market: [job for job in score_sorted if job.get("market") == market and _safe_float(job.get("score"), 0.0) >= 45.0]
        for market in _market_order()
    }
    while len(selected) < limit:
        progressed = False
        for market in _market_order():
            before = len(selected)
            add(market_buckets.get(market, []), 1)
            progressed = progressed or len(selected) > before
            if len(selected) >= limit:
                break
        if not progressed:
            break

    add(score_sorted, limit - len(selected))
    return selected


def _market_order() -> list[str]:
    return [
        "france",
        "ireland",
        "switzerland",
        "belgium",
        "singapore",
        "remote_europe",
        "netherlands",
        "luxembourg",
        "uk",
        "germany",
        "austria",
        "sweden",
        "denmark",
        "norway",
        "finland",
        "spain",
        "portugal",
        "estonia",
        "poland",
        "czechia",
    ]


def _fit_rank(job: dict[str, Any]) -> float:
    parts = job.get("score_parts", {})
    parts = parts if isinstance(parts, dict) else {}
    technical = _safe_float(parts.get("technical"), 0.0)
    role = _safe_float(parts.get("role"), 0.0)
    score = _safe_float(job.get("score"), 0.0)
    return technical * 0.55 + role * 0.25 + score * 0.20


def _selection_summary(all_jobs: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "available_jobs": len(all_jobs),
        "selected_jobs": len(selected),
        "available_vie": len([job for job in all_jobs if _is_vie_job(job)]),
        "selected_vie": len([job for job in selected if _is_vie_job(job)]),
        "available_early_career": len([job for job in all_jobs if _is_target_early_career(job)]),
        "selected_early_career": len([job for job in selected if _is_target_early_career(job)]),
        "selected_markets": _counts(str(job.get("market", "")) for job in selected),
        "selected_sources": _counts(str(job.get("source", "")) for job in selected),
    }


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items(), key=lambda item: (-item[1], item[0])))


def _judge_chunks(
    settings: LLMSettings,
    profile_summary: dict[str, Any],
    chunks: list[list[tuple[dict[str, Any], dict[str, Any]]]],
    *,
    concurrency: int,
    progress: bool,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if not chunks:
        return {}, []

    max_workers = max(1, min(concurrency, len(chunks)))
    if max_workers == 1:
        judgements: dict[str, dict[str, Any]] = {}
        batch_runs: list[dict[str, Any]] = []
        for batch_index, chunk in enumerate(chunks, start=1):
            if progress:
                print(f"judge_batch_start={batch_index}/{len(chunks)} jobs={len(chunk)} concurrency=1", flush=True)
            chunk_judgements, chunk_runs = _judge_chunk_with_retries(settings, profile_summary, chunk)
            judgements.update(chunk_judgements)
            batch_runs.extend(chunk_runs)
            if progress:
                print(f"judge_batch_done={batch_index}/{len(chunks)} cumulative={len(judgements)}", flush=True)
        return judgements, batch_runs

    completed: dict[int, tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]] = {}
    in_flight: dict[concurrent.futures.Future, int] = {}
    total = len(chunks)
    next_batch_index = 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        def submit(batch_index: int) -> None:
            chunk = chunks[batch_index - 1]
            if progress:
                print(
                    f"judge_batch_start={batch_index}/{total} jobs={len(chunk)} concurrency={max_workers}",
                    flush=True,
                )
            in_flight[executor.submit(_judge_chunk_with_retries, settings, profile_summary, chunk)] = batch_index

        while next_batch_index <= total and len(in_flight) < max_workers:
            submit(next_batch_index)
            next_batch_index += 1

        while in_flight:
            done, _ = concurrent.futures.wait(in_flight, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                batch_index = in_flight.pop(future)
                try:
                    completed[batch_index] = future.result()
                except BaseException:
                    for pending in in_flight:
                        pending.cancel()
                    raise
                if progress:
                    cumulative = sum(len(chunk_judgements) for chunk_judgements, _ in completed.values())
                    print(f"judge_batch_done={batch_index}/{total} cumulative={cumulative}", flush=True)
                if next_batch_index <= total:
                    submit(next_batch_index)
                    next_batch_index += 1

    judgements: dict[str, dict[str, Any]] = {}
    batch_runs: list[dict[str, Any]] = []
    for batch_index in range(1, total + 1):
        chunk_judgements, chunk_runs = completed[batch_index]
        judgements.update(chunk_judgements)
        batch_runs.extend(chunk_runs)
    return judgements, batch_runs


def _judge_chunk(
    settings: LLMSettings,
    profile_summary: dict[str, Any],
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    originals = [pair[0] for pair in pairs]
    compact_jobs = [pair[1] for pair in pairs]
    try:
        request_payload = _judge_request_payload(profile_summary, compact_jobs)
        model_result = call_model(settings, request_payload)
        raw_json = parse_json_object(model_result.text)
        judgements = _normalise_judgements(raw_json, originals)
        _ensure_complete_judgements(judgements, originals)
        run = {
            "count": len(pairs),
            "ids": [job.get("stable_id", "") for job in originals],
            "endpoint": model_result.endpoint,
            "response_id": model_result.response_id,
            "usage": model_result.usage or {},
        }
        return judgements, [run]
    except LLMCallError:
        raise
    except LLMJudgeError as exc:
        if len(pairs) <= 1:
            raise LLMJudgeError(f"Jugement structurel invalide pour singleton: {exc}") from exc
        middle = len(pairs) // 2
        left_judgements, left_runs = _judge_chunk(settings, profile_summary, pairs[:middle])
        right_judgements, right_runs = _judge_chunk(settings, profile_summary, pairs[middle:])
        left_judgements.update(right_judgements)
        return left_judgements, left_runs + right_runs


def _judge_chunk_with_retries(
    settings: LLMSettings,
    profile_summary: dict[str, Any],
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    last_error = ""
    for attempt in range(1, LLM_BATCH_MAX_ATTEMPTS + 1):
        try:
            judgements, runs = _judge_chunk(settings, profile_summary, pairs)
            if attempt > 1:
                for run in runs:
                    run["retry_attempt"] = attempt
            return judgements, runs
        except (LLMCallError, LLMJudgeError) as exc:
            last_error = str(exc)
            if attempt >= LLM_BATCH_MAX_ATTEMPTS:
                break
            time.sleep(LLM_BATCH_RETRY_SECONDS * attempt)

    originals = [pair[0] for pair in pairs]
    judgements = {
        str(job.get("stable_id", "")): _default_judgement(str(job.get("stable_id", "")))
        for job in originals
        if job.get("stable_id")
    }
    run = {
        "count": len(pairs),
        "ids": [str(job.get("stable_id", "")) for job in originals if job.get("stable_id")],
        "endpoint": "fallback_default",
        "response_id": "",
        "usage": {},
        "error": last_error,
        "attempts": LLM_BATCH_MAX_ATTEMPTS,
    }
    return judgements, [run]


def _ensure_complete_judgements(judgements: dict[str, dict[str, Any]], jobs: list[dict[str, Any]]) -> None:
    expected = [str(job.get("stable_id") or "") for job in jobs]
    expected = [item for item in expected if item]
    missing = [stable_id for stable_id in expected if stable_id not in judgements]
    if missing:
        preview = ", ".join(missing[:5])
        extra = f" (+{len(missing) - 5})" if len(missing) > 5 else ""
        raise LLMJudgeError(f"Reponse LLM incomplete: {len(missing)} jugement(s) manquant(s): {preview}{extra}.")


def _judge_quality_summary(batch_runs: list[dict[str, Any]], *, expected_count: int) -> dict[str, Any]:
    endpoint_counts = _counts(str(run.get("endpoint", "")) for run in batch_runs)
    fallback_runs = [run for run in batch_runs if run.get("endpoint") == "fallback_default"]
    fallback_items = sum(int(run.get("count") or 0) for run in fallback_runs)
    expected = max(0, int(expected_count))
    fallback_ratio = (fallback_items / expected) if expected else 0.0
    return {
        "expected_items": expected,
        "batch_count": len(batch_runs),
        "fallback_batches": len(fallback_runs),
        "fallback_items": fallback_items,
        "fallback_ratio": round(fallback_ratio, 6),
        "endpoint_counts": endpoint_counts,
        "fallback_errors": [str(run.get("error", ""))[:500] for run in fallback_runs if run.get("error")][:10],
    }


def _validate_judge_quality(quality: dict[str, Any], *, max_fallback_ratio: float) -> None:
    ratio = _safe_float(quality.get("fallback_ratio"), 0.0)
    fallback_items = int(quality.get("fallback_items") or 0)
    expected_items = int(quality.get("expected_items") or 0)
    if fallback_items and ratio > max(0.0, max_fallback_ratio):
        raise LLMJudgeError(
            "Qualite judge LLM insuffisante: "
            f"{fallback_items}/{expected_items} offre(s) en fallback_default "
            f"({ratio:.1%}, maximum {max_fallback_ratio:.1%}). "
            "Aucun llm_shortlist final n'a ete ecrit; relancer avec un provider/effort/batch plus stable."
        )


def call_model(settings: LLMSettings, request_payload: dict[str, Any]) -> ModelResult:
    attempts = _transport_attempts(settings, request_payload)
    errors: list[str] = []
    for endpoint_name, payload in attempts:
        try:
            if endpoint_name == "responses_sdk":
                data = _post_responses_sdk(settings, payload)
            else:
                url = _endpoint_url(settings.base_url, endpoint_name)
                data = _post_json(url, payload, settings.api_key, settings.timeout_seconds)
            text = extract_output_text(data)
            if not text:
                raise LLMJudgeError(f"Reponse LLM sans texte sur {endpoint_name}.")
            return ModelResult(
                text=text,
                endpoint=endpoint_name,
                response_id=str(data.get("id", "")),
                usage=data.get("usage") if isinstance(data.get("usage"), dict) else None,
            )
        except LLMHTTPError as exc:
            if exc.status in {401, 403}:
                raise
            errors.append(str(exc))
        except LLMJudgeError as exc:
            errors.append(str(exc))
    raise LLMCallError("Tous les appels LLM ont echoue:\n- " + "\n- ".join(errors))


def _transport_attempts(settings: LLMSettings, request_payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    attempts: list[tuple[str, dict[str, Any]]] = []
    responses_json = _responses_payload(settings, request_payload, json_mode=True)
    if settings.transport in {"auto", "sdk"}:
        if _openai_sdk_available():
            attempts.append(("responses_sdk", responses_json))
        elif settings.transport == "sdk":
            raise LLMCallError("Transport OpenAI SDK demande mais le package `openai` est indisponible.")
    if settings.transport in {"auto", "raw"}:
        attempts.extend(
            [
                ("responses", responses_json),
                ("responses_plain", _responses_payload(settings, request_payload, json_mode=False)),
                ("chat_completions", _chat_payload(settings, request_payload)),
            ]
        )
    if not attempts:
        raise LLMCallError(f"Aucun transport LLM disponible pour `{settings.transport}`.")
    return attempts


def _openai_sdk_available() -> bool:
    return importlib.util.find_spec("openai") is not None


def _post_responses_sdk(settings: LLMSettings, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
    except ImportError as exc:
        raise LLMCallError("Package OpenAI SDK indisponible.") from exc

    url = _endpoint_url(settings.base_url, "responses")
    try:
        client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )
        response = client.responses.create(**payload)
    except APIStatusError as exc:
        body = ""
        response = getattr(exc, "response", None)
        if response is not None:
            body = getattr(response, "text", "") or ""
        raise LLMHTTPError(int(getattr(exc, "status_code", 0) or 0), url, body or str(exc)) from exc
    except (APIConnectionError, APITimeoutError) as exc:
        raise LLMCallError(f"Erreur reseau LLM SDK sur {_safe_url(url)}: {_redact(str(exc))}") from exc
    except Exception as exc:
        raise LLMJudgeError(f"Erreur SDK OpenAI sur {_safe_url(url)}: {_redact(str(exc))}") from exc

    if hasattr(response, "model_dump"):
        data = response.model_dump(mode="json")
    elif isinstance(response, dict):
        data = response
    else:
        raise LLMJudgeError("Reponse SDK OpenAI inattendue.")
    if not isinstance(data, dict):
        raise LLMJudgeError("Reponse SDK OpenAI non objet.")
    return data


def extract_output_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            elif isinstance(content, str):
                parts.append(content)
    if parts:
        return "\n".join(part for part in parts if part).strip()

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append(part["text"])
                    if parts:
                        return "\n".join(parts).strip()
            text = first.get("text")
            if isinstance(text, str):
                return text.strip()
    return ""


def parse_json_object(text: str) -> dict[str, Any] | list[Any]:
    cleaned = _strip_code_fence(text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise LLMJudgeError("La reponse LLM ne contient pas de JSON exploitable.")


def _load_jobs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise LLMJudgeError(f"Fichier introuvable: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise LLMJudgeError(f"Format jobs invalide dans {path}: liste attendue.")
    return [job for job in data if isinstance(job, dict)]


def _profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    weights = profile.get("weights", {})
    must_have = weights.get("must_have", {}) if isinstance(weights, dict) else {}
    good = weights.get("good_signals", {}) if isinstance(weights, dict) else {}
    return {
        "headline": profile.get("profile", {}).get("headline", ""),
        "summary": profile.get("profile", {}).get("summary", ""),
        "languages": profile.get("profile", {}).get("languages", []),
        "location": profile.get("profile", {}).get("current_location", ""),
        "career": profile.get("career", {}),
        "current_experience": profile.get("current_experience", {}),
        "constraints": profile.get("constraints", {}),
        "target_markets": profile.get("search", {}).get("target_markets", []),
        "target_titles": profile.get("search", {}).get("titles", [])[:30],
        "strong_keywords": _top_weighted_terms(must_have, minimum=7, limit=30),
        "positive_keywords": _top_weighted_terms(good, minimum=6, limit=20),
    }


def _top_weighted_terms(values: dict[str, Any], *, minimum: int, limit: int) -> list[str]:
    rows: list[tuple[str, float]] = []
    for key, value in values.items():
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        if score >= minimum:
            rows.append((key, score))
    rows.sort(key=lambda item: (-item[1], item[0]))
    return [key for key, _ in rows[:limit]]


def _compact_job(job: dict[str, Any]) -> dict[str, Any]:
    description = clean_html(str(job.get("description", "")))
    early_signal = early_career_signal(job)
    return {
        "stable_id": job.get("stable_id", ""),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "market": job.get("market", ""),
        "location": job.get("location", ""),
        "remote": bool(job.get("remote", False)),
        "salary": job.get("salary", ""),
        "salary_normalized_annual_eur": job.get("salary_normalized_annual_eur"),
        "salary_currency": job.get("salary_currency", ""),
        "deadline": job.get("deadline", ""),
        "language_check": job.get("language_check", "unknown"),
        "remote_location_validity": job.get("remote_location_validity", "unknown"),
        "required_years": job.get("required_years"),
        "experience_check": job.get("experience_check", "unknown"),
        "experience_evidence": job.get("experience_evidence", ""),
        "posted_at": job.get("posted_at", ""),
        "source": job.get("source", ""),
        "source_type": job.get("source_type", ""),
        "employment_type": job.get("employment_type", ""),
        "tags": job.get("tags", [])[:12] if isinstance(job.get("tags"), list) else [],
        "url": job.get("url", ""),
        "score": job.get("score", 0),
        "score_parts": job.get("score_parts", {}),
        "early_career": early_signal,
        "deterministic_reasons": job.get("reasons", [])[:10],
        "description_excerpt": description[:1000],
    }


def _judge_request_payload(profile_summary: dict[str, Any], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "system": (
            "Tu es un recruteur technique senior specialise data engineering, IA appliquee, "
            "LLM/MLOps et recherche IA en Europe. Tu dois reclasser une shortlist d'offres "
            "pour un profil junior/new-grad, sans inventer les informations absentes. "
            "Si le salaire, le remote, le niveau ou la date de demarrage ne sont pas explicites, marque unknown. "
            "Ne sois pas excessivement restrictif: skip est reserve aux vrais mismatches; "
            "les offres prometteuses mais incompletes doivent rester shortlist ou maybe. "
            "Retourne uniquement un JSON valide."
        ),
        "user": (
            "Evalue les offres suivantes pour ce profil. Le score deterministe local reste utile, "
            "mais tu dois corriger les faux positifs, notamment les postes trop seniors pour un junior. "
            "Favorise les roles data/AI/LLM/research coherents avec un stage AI Researcher chez Aubay "
            "de fevrier 2026 a juillet 2026 sur l'explicabilite/interpretabilite mecanistique de l'IA.\n\n"
            "Contraintes fortes: salaire vise >= 45k EUR/an, hybride/remote avec au moins 2 jours "
            "de teletravail souhaites, disponibilite apres le stage actuel donc demarrage cible "
            "a partir d'aout/septembre 2026, preference grandes villes, France/Irlande/Suisse/Belgique/"
            "Singapour/Europe anglophone pertinents. Aucun secteur exclu. Pour les missions VIE "
            "Business France, evalue l'indemnite mensuelle a part: le VIE est un statut indemnise, "
            "pas un CDI, donc ne compare pas son indemnite au seuil brut annuel CDI 45k. Ne marque "
            "below_min que si l'offre publie une information explicitement faible ou incoherente; sinon "
            "meets_or_likely ou unknown selon les donnees. Pour un VIE junior-compatible avec un titre "
            "data/IA/software pertinent, favorise shortlist/apply_now selon le fit; ne le skip pas juste "
            "parce que le remote, le salaire CDI ou le niveau exact sont a verifier. Pour les graduate "
            "programmes, new grad, early careers, campus et trainee programmes, ne penalise pas le label "
            "graduate/junior seul si le role est data/AI/software/research; evalue surtout le contenu "
            "technique, l'intake/cohorte, la date de demarrage et le risque de programme business generaliste. "
            "Pour les doctorats en entreprise, CIFRE, industrial PhD ou doctoral researcher, garde l'offre "
            "si elle est appliquee data/AI/LLM/research et si le statut/salaire semble compatible; sois plus "
            "prudent avec les PhD purement academiques sans entreprise, salaire ou sujet technique clair.\n\n"
            "Utilise aussi les signaux structures deadline, language_check, remote_location_validity, "
            "required_years et experience_check quand ils sont "
            "renseignes. Un besoin explicite de langue locale non maitrisee ou une restriction remote hors Europe "
            "doit etre un risque fort, mais pas un skip automatique si le role est excellent et que l'information "
            "reste negociable/verifiable. En revanche, si experience_check vaut too_senior ou required_years >= 5 "
            "sans signal explicite junior/new-grad/all-levels, le poste doit normalement etre skip.\n\n"
            "Retour attendu, strictement en JSON:\n"
            f"{json.dumps(_expected_schema(), ensure_ascii=False)}\n\n"
            "Regles:\n"
            "- fit_score: entier 0-100, coherence globale pour candidater maintenant.\n"
            "- priority: apply_now, shortlist, maybe ou skip.\n"
            "- apply_now: tres bon fit actionnable, meme si quelques checks salaire/remote restent a faire.\n"
            "- shortlist: bon fit ou VIE prometteur a verifier; ne pas confondre avec skip.\n"
            "- maybe: fit partiel, pivot possible, ou info trop incomplete.\n"
            "- skip: uniquement role clairement hors cible, trop senior, trop business/non-tech, ou incompatibilite forte.\n"
            "- Un graduate programme data/AI/software coherent doit rester apply_now/shortlist/maybe selon le fit, pas skip par defaut.\n"
            "- Un CIFRE/industrial PhD data/AI/research coherent est un angle opportuniste valable; verifie salaire/statut/entreprise et ne le classe pas comme stage.\n"
            "- Pour ce profil junior/new-grad, une exigence 2+ ans est un stretch a verifier, 3-4+ ans requis doit rarement etre apply_now, "
            "et 5+ ans ou titre senior/staff/lead/principal doit normalement etre too_senior/skip sauf signal explicite new-grad/all-levels.\n"
            "- level_fit: junior_ok, stretch, too_senior, too_junior ou unknown.\n"
            "- salary_check: meets_or_likely, unknown ou below_min.\n"
            "- remote_check: meets, unknown ou weak.\n"
            "- start_date_check: compatible si l'offre indique un demarrage apres juillet 2026 ou negociable; "
            "too_soon si ASAP/immediat/avant aout 2026; unknown si absent. C'est un signal soft, pas un motif de skip seul.\n"
            "- start_date_evidence: extrait ou date courte, vide si unknown.\n"
            "- language_check: english_ok, french_ok, local_language_required ou unknown.\n"
            "- remote_location_validity: compatible, restricted, incompatible ou unknown.\n"
            "- why et risks: 1 a 4 phrases courtes chacune, en francais.\n"
            "- application_angle: une phrase concrete pour adapter CV/message.\n"
            "- N'invente pas une information absente de l'offre.\n\n"
            f"Profil:\n{json.dumps(profile_summary, ensure_ascii=False, indent=2)}\n\n"
            f"Offres:\n{json.dumps(jobs, ensure_ascii=False, indent=2)}"
        ),
        "job_count": len(jobs),
        "job_ids": [str(job.get("stable_id", "")) for job in jobs if job.get("stable_id")],
    }


def _expected_schema() -> dict[str, Any]:
    return {
        "items": [
            {
                "stable_id": "id de l'offre",
                "fit_score": 0,
                "priority": "apply_now|shortlist|maybe|skip",
                "level_fit": "junior_ok|stretch|too_senior|too_junior|unknown",
                "salary_check": "meets_or_likely|unknown|below_min",
                "remote_check": "meets|unknown|weak",
                "start_date_check": "compatible|too_soon|unknown",
                "start_date_evidence": "date ou extrait justifiant le check",
                "language_check": "english_ok|french_ok|local_language_required|unknown",
                "remote_location_validity": "compatible|restricted|incompatible|unknown",
                "why": ["raison courte"],
                "risks": ["risque court"],
                "application_angle": "angle CV/message",
            }
        ]
    }


def _responses_payload(settings: LLMSettings, request_payload: dict[str, Any], *, json_mode: bool) -> dict[str, Any]:
    max_output_tokens = _max_output_tokens(int(request_payload.get("job_count") or 1))
    payload: dict[str, Any] = {
        "model": settings.model,
        "instructions": request_payload["system"],
        "input": request_payload["user"],
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    if settings.reasoning_effort != "none":
        payload["reasoning"] = {"effort": settings.reasoning_effort}
    if json_mode:
        payload["text"] = {"format": _structured_output_format(request_payload)}
    return payload


def _chat_payload(settings: LLMSettings, request_payload: dict[str, Any]) -> dict[str, Any]:
    max_output_tokens = _max_output_tokens(int(request_payload.get("job_count") or 1))
    payload: dict[str, Any] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": request_payload["system"]},
            {"role": "user", "content": request_payload["user"]},
        ],
        "response_format": _chat_response_format(request_payload),
        "max_completion_tokens": max_output_tokens,
    }
    if settings.reasoning_effort != "none":
        payload["reasoning_effort"] = settings.reasoning_effort
    return payload


def _structured_output_format(request_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "jobradai_judge",
        "strict": True,
        "schema": _judgement_json_schema(request_payload),
    }


def _chat_response_format(request_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "jobradai_judge",
            "strict": True,
            "schema": _judgement_json_schema(request_payload),
        },
    }


def _judgement_json_schema(request_payload: dict[str, Any]) -> dict[str, Any]:
    job_ids = [str(item) for item in request_payload.get("job_ids", []) if str(item)]
    stable_id_schema: dict[str, Any] = {"type": "string"}
    if job_ids:
        stable_id_schema["enum"] = job_ids
    item_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "stable_id": stable_id_schema,
            "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "priority": {"type": "string", "enum": sorted(VALID_PRIORITIES)},
            "level_fit": {"type": "string", "enum": sorted(VALID_LEVEL_FITS)},
            "salary_check": {"type": "string", "enum": sorted(VALID_SALARY_CHECKS)},
            "remote_check": {"type": "string", "enum": sorted(VALID_REMOTE_CHECKS)},
            "start_date_check": {"type": "string", "enum": sorted(VALID_START_DATE_CHECKS)},
            "start_date_evidence": {"type": "string"},
            "language_check": {"type": "string", "enum": sorted(VALID_LANGUAGE_CHECKS)},
            "remote_location_validity": {"type": "string", "enum": sorted(VALID_REMOTE_LOCATION_VALIDITY)},
            "why": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {"type": "string"},
            },
            "risks": {
                "type": "array",
                "minItems": 0,
                "maxItems": 4,
                "items": {"type": "string"},
            },
            "application_angle": {"type": "string"},
        },
        "required": [
            "stable_id",
            "fit_score",
            "priority",
            "level_fit",
            "salary_check",
            "remote_check",
            "start_date_check",
            "start_date_evidence",
            "language_check",
            "remote_location_validity",
            "why",
            "risks",
            "application_angle",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "minItems": len(job_ids),
                "maxItems": len(job_ids),
                "items": item_schema,
            }
        },
        "required": ["items"],
    }


def _endpoint_url(base_url: str, endpoint_name: str) -> str:
    if endpoint_name in {"responses", "responses_plain", "responses_sdk"}:
        return f"{base_url}/responses"
    if endpoint_name == "chat_completions":
        return f"{base_url}/chat/completions"
    raise LLMJudgeError(f"Endpoint LLM inconnu: {endpoint_name}")


def _post_json(url: str, payload: dict[str, Any], api_key: str, timeout_seconds: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LLMHTTPError(exc.code, url, body) from exc
    except urllib.error.URLError as exc:
        raise LLMCallError(f"Erreur reseau LLM sur {_safe_url(url)}: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise LLMCallError(f"Erreur reseau LLM sur {_safe_url(url)}: {_redact(str(exc))}") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise LLMJudgeError(f"Reponse LLM non JSON sur {_safe_url(url)}.") from exc
    if not isinstance(parsed, dict):
        raise LLMJudgeError(f"Reponse LLM inattendue sur {_safe_url(url)}.")
    return parsed


def _normalise_judgements(raw: dict[str, Any] | list[Any], jobs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: list[Any]
    if isinstance(raw, dict):
        rows = raw.get("items", [])
    else:
        rows = raw
    if not isinstance(rows, list):
        raise LLMJudgeError("JSON LLM invalide: champ items liste attendu.")
    allowed_ids = {str(job.get("stable_id", "")) for job in jobs}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        stable_id = str(row.get("stable_id", ""))
        if stable_id not in allowed_ids:
            continue
        priority = _enum(row.get("priority"), VALID_PRIORITIES, "maybe")
        level_fit = _enum(row.get("level_fit"), VALID_LEVEL_FITS, "unknown")
        if level_fit in {"too_senior", "too_junior"} and priority in {"apply_now", "shortlist"}:
            priority = "skip"
        result[stable_id] = {
            "stable_id": stable_id,
            "judge_status": "model",
            "fit_score": _clamp_score(row.get("fit_score", 50)),
            "priority": priority,
            "level_fit": level_fit,
            "salary_check": _enum(row.get("salary_check"), VALID_SALARY_CHECKS, "unknown"),
            "remote_check": _enum(row.get("remote_check"), VALID_REMOTE_CHECKS, "unknown"),
            "start_date_check": _enum(row.get("start_date_check"), VALID_START_DATE_CHECKS, "unknown"),
            "start_date_evidence": normalize_space(str(row.get("start_date_evidence", "")))[:500],
            "language_check": _enum(row.get("language_check"), VALID_LANGUAGE_CHECKS, "unknown"),
            "remote_location_validity": _enum(row.get("remote_location_validity"), VALID_REMOTE_LOCATION_VALIDITY, "unknown"),
            "why": _string_list(row.get("why"))[:4],
            "risks": _string_list(row.get("risks"))[:4],
            "application_angle": normalize_space(str(row.get("application_angle", "")))[:500],
        }
    return result


def _merge_judgements(jobs: list[dict[str, Any]], judgements: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for job in jobs:
        stable_id = str(job.get("stable_id", ""))
        judgement = judgements.get(stable_id) or _default_judgement(stable_id)
        score = _safe_float(job.get("score", 0.0))
        fit_score = _safe_float(judgement.get("fit_score", 50.0))
        merged.append(
            {
                "stable_id": stable_id,
                "combined_score": round((score * LOCAL_SCORE_WEIGHT) + (fit_score * LLM_SCORE_WEIGHT), 2),
                "score": round(score, 2),
                "llm_fit_score": round(fit_score, 2),
                "llm_judge_status": judgement.get("judge_status", "model"),
                "priority": judgement["priority"],
                "level_fit": judgement["level_fit"],
                "salary_check": judgement["salary_check"],
                "remote_check": judgement["remote_check"],
                "start_date_check": judgement["start_date_check"],
                "start_date_evidence": judgement["start_date_evidence"],
                "language_check": judgement.get("language_check", "unknown"),
                "remote_location_validity": judgement.get("remote_location_validity", "unknown"),
                "why": judgement["why"],
                "risks": judgement["risks"],
                "application_angle": judgement["application_angle"],
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "market": job.get("market", ""),
                "location": job.get("location", ""),
                "salary": job.get("salary", ""),
                "salary_normalized_annual_eur": job.get("salary_normalized_annual_eur"),
                "deadline": job.get("deadline", ""),
                "required_years": job.get("required_years"),
                "experience_check": job.get("experience_check", "unknown"),
                "experience_evidence": job.get("experience_evidence", ""),
                "source": job.get("source", ""),
                "url": job.get("url", ""),
                "deterministic_reasons": job.get("reasons", [])[:8],
            }
        )
    return merged


def _default_judgement(stable_id: str) -> dict[str, Any]:
    return {
        "stable_id": stable_id,
        "judge_status": "fallback_default",
        "fit_score": 50,
        "priority": "maybe",
        "level_fit": "unknown",
        "salary_check": "unknown",
        "remote_check": "unknown",
        "start_date_check": "unknown",
        "start_date_evidence": "",
        "language_check": "unknown",
        "remote_location_validity": "unknown",
        "why": ["Le LLM n'a pas renvoye de jugement exploitable pour cette offre."],
        "risks": ["Verification manuelle requise."],
        "application_angle": "",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_previous_shortlist_outputs(output_dir: Path) -> None:
    for name in ("llm_shortlist.json", "llm_shortlist.md"):
        path = output_dir / name
        if path.exists():
            path.unlink()


def _write_markdown(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Shortlist LLM",
        "",
        f"- Genere le: {result['generated_at']}",
        f"- Modele: `{result['model']}`",
        f"- Effort: `{result['reasoning_effort']}`",
        f"- Endpoint: `{result['endpoint']}`",
        f"- Selection: `{result.get('selection_mode', 'n/a')}`",
        f"- Resume selection: `{result.get('selection_summary', {})}`",
        f"- Batchs: **{len(result.get('batches', []))}** x max `{result.get('batch_size', 'n/a')}`",
        f"- Parallele: `{result.get('concurrency', 1)}` batch(s) simultane(s)",
        f"- Score combine: local `{LOCAL_SCORE_WEIGHT:.0%}` | LLM `{LLM_SCORE_WEIGHT:.0%}`",
        f"- Qualite: fallback `{result.get('fallback_items', 0)}` / `{result['count']}` ({result.get('fallback_ratio', 0):.1%}) | endpoints `{result.get('endpoint_counts', {})}`",
        f"- Priorites: `{result.get('priority_counts', {})}`",
        f"- Offres jugees: **{result['count']}**",
        "",
        "## Classement",
        "",
    ]
    for index, item in enumerate(result["items"], start=1):
        why = "; ".join(item.get("why", [])) or "n/a"
        risks = "; ".join(item.get("risks", [])) or "n/a"
        lines.extend(
            [
                f"### {index}. {item['title']} - {item['company']} ({item['combined_score']:.1f})",
                f"- Scores: local `{item['score']:.1f}` | LLM `{item['llm_fit_score']:.1f}` | priorite `{item['priority']}`",
                f"- Fit: niveau `{item['level_fit']}` | salaire `{item['salary_check']}` | remote `{item['remote_check']}` | start `{item['start_date_check']}` | langue `{item.get('language_check', 'unknown')}` | remote/localisation `{item.get('remote_location_validity', 'unknown')}`",
                f"- Evidence demarrage: {item.get('start_date_evidence') or 'n/a'}",
                f"- Marche: `{item['market']}` | Lieu: {item['location'] or 'n/a'} | Source: `{item['source']}`",
                f"- Salaire publie: {item['salary'] or 'n/a'} | normalise EUR/an: {item.get('salary_normalized_annual_eur') or 'n/a'} | deadline: {item.get('deadline') or 'n/a'}",
                f"- Experience extraite: `{item.get('experience_check', 'unknown')}` | annees `{item.get('required_years') or 'n/a'}` | evidence: {item.get('experience_evidence') or 'n/a'}",
                f"- URL: {item['url']}",
                f"- Pourquoi: {why}",
                f"- Risques: {risks}",
                f"- Angle candidature: {item.get('application_angle') or 'n/a'}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _max_output_tokens(job_count: int) -> int:
    return max(1600, min(6000, 800 + job_count * 650))


def _sum_usage(usages: Any) -> dict[str, Any]:
    total: dict[str, Any] = {}
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        _merge_numeric_dict(total, usage)
    return total


def _merge_numeric_dict(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            child = target.setdefault(key, {})
            if isinstance(child, dict):
                _merge_numeric_dict(child, value)
        elif isinstance(value, (int, float)):
            target[key] = target.get(key, 0) + value


def _strip_code_fence(value: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else value


def _clamp_score(value: Any) -> int:
    return int(max(0, min(100, round(_safe_float(value, 50.0)))))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _enum(value: Any, allowed: set[str], default: str) -> str:
    raw = normalize_space(str(value or "")).lower()
    return raw if raw in allowed else default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [normalize_space(str(item))[:500] for item in value if normalize_space(str(item))]
    if isinstance(value, str) and normalize_space(value):
        return [normalize_space(value)[:500]]
    return []


def _safe_url(url: str) -> str:
    secret = os.environ.get("JOBRADAR_LLM_API_KEY")
    return url.replace(secret, "[REDACTED]") if secret else url


def _redact(value: str) -> str:
    redacted = value
    for key in ("JOBRADAR_LLM_API_KEY", "OPENAI_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-[REDACTED]", redacted)
    return redacted


def _is_vie_job(job: dict[str, Any]) -> bool:
    source = normalize_space(str(job.get("source", ""))).lower()
    employment = normalize_space(str(job.get("employment_type", ""))).lower()
    tags_value = job.get("tags", [])
    tags = " ".join(str(item) for item in tags_value) if isinstance(tags_value, list) else str(tags_value)
    tags = normalize_space(tags).lower()
    return (
        "business france vie" in source
        or bool(re.search(r"\bv\.?i\.?e\b", employment))
        or "volontariat international en entreprise" in tags
    )


def _is_target_early_career(job: dict[str, Any]) -> bool:
    return early_career_signal(job).get("early_career_fit") in {"high", "medium"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
