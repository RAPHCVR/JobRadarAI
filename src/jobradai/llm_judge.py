from __future__ import annotations

import json
import os
import re
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
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_SELECTION_MODE = "balanced"
DEFAULT_TIMEOUT_SECONDS = 360
VALID_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}
VALID_SELECTION_MODES = {"top", "balanced", "vie", "all"}
VALID_PRIORITIES = {"apply_now", "shortlist", "maybe", "skip"}
VALID_LEVEL_FITS = {"junior_ok", "stretch", "too_senior", "too_junior", "unknown"}
VALID_SALARY_CHECKS = {"meets_or_likely", "unknown", "below_min"}
VALID_REMOTE_CHECKS = {"meets", "unknown", "weak"}
VALID_START_DATE_CHECKS = {"compatible", "too_soon", "unknown"}


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

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        timeout_seconds: int | None = None,
    ) -> "LLMSettings":
        effort = reasoning_effort or os.environ.get("JOBRADAR_LLM_REASONING_EFFORT") or DEFAULT_REASONING_EFFORT
        effort = effort.lower().strip()
        if effort not in VALID_EFFORTS:
            raise LLMJudgeError(
                "JOBRADAR_LLM_REASONING_EFFORT invalide. "
                f"Valeurs supportees: {', '.join(sorted(VALID_EFFORTS))}."
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
    batch_size: int = 5,
    selection_mode: str = DEFAULT_SELECTION_MODE,
    settings: LLMSettings | None = None,
    dry_run: bool = False,
    progress: bool = False,
) -> dict[str, Any]:
    jobs = _load_jobs(input_path)
    selected = _select_jobs(jobs, limit=limit, mode=selection_mode)
    profile_summary = _profile_summary(profile)
    compact_jobs = [_compact_job(job) for job in selected]
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_size = max(1, min(batch_size, max(1, len(selected))))

    if dry_run:
        preview = {
            "generated_at": _now(),
            "dry_run": True,
            "batch_size": batch_size,
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

    judgements: dict[str, dict[str, Any]] = {}
    batch_runs: list[dict[str, Any]] = []
    pairs = list(zip(selected, compact_jobs, strict=True))
    chunks = _chunks(pairs, batch_size)
    for batch_index, chunk in enumerate(chunks, start=1):
        if progress:
            print(f"judge_batch_start={batch_index}/{len(chunks)} jobs={len(chunk)}", flush=True)
        chunk_judgements, chunk_runs = _judge_chunk(settings, profile_summary, chunk)
        judgements.update(chunk_judgements)
        batch_runs.extend(chunk_runs)
        if progress:
            print(f"judge_batch_done={batch_index}/{len(chunks)} cumulative={len(judgements)}", flush=True)

    annotated = _merge_judgements(selected, judgements)
    annotated.sort(key=lambda item: (item["combined_score"], item["score"]), reverse=True)
    endpoints = sorted({str(run.get("endpoint", "")) for run in batch_runs if run.get("endpoint")})
    response_ids = [str(run.get("response_id", "")) for run in batch_runs if run.get("response_id")]
    result = {
        "generated_at": _now(),
        "model": settings.model,
        "base_url": settings.base_url,
        "reasoning_effort": settings.reasoning_effort,
        "endpoint": ",".join(endpoints) if endpoints else "",
        "response_id": response_ids[0] if response_ids else "",
        "response_ids": response_ids,
        "usage": _sum_usage(run.get("usage") for run in batch_runs),
        "batches": batch_runs,
        "batch_size": batch_size,
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

    market_order = [
        "ireland",
        "switzerland",
        "belgium",
        "singapore",
        "france",
        "remote_europe",
        "netherlands",
        "luxembourg",
        "uk",
        "germany",
    ]
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
    except LLMJudgeError:
        if len(pairs) <= 1:
            raise
        middle = len(pairs) // 2
        left_judgements, left_runs = _judge_chunk(settings, profile_summary, pairs[:middle])
        right_judgements, right_runs = _judge_chunk(settings, profile_summary, pairs[middle:])
        left_judgements.update(right_judgements)
        return left_judgements, left_runs + right_runs


def _ensure_complete_judgements(judgements: dict[str, dict[str, Any]], jobs: list[dict[str, Any]]) -> None:
    expected = [str(job.get("stable_id") or "") for job in jobs]
    expected = [item for item in expected if item]
    missing = [stable_id for stable_id in expected if stable_id not in judgements]
    if missing:
        preview = ", ".join(missing[:5])
        extra = f" (+{len(missing) - 5})" if len(missing) > 5 else ""
        raise LLMJudgeError(f"Reponse LLM incomplete: {len(missing)} jugement(s) manquant(s): {preview}{extra}.")


def call_model(settings: LLMSettings, request_payload: dict[str, Any]) -> ModelResult:
    attempts: list[tuple[str, dict[str, Any]]] = [
        ("responses", _responses_payload(settings, request_payload, json_mode=True)),
        ("responses_plain", _responses_payload(settings, request_payload, json_mode=False)),
        ("chat_completions", _chat_payload(settings, request_payload)),
    ]
    errors: list[str] = []
    for endpoint_name, payload in attempts:
        url = _endpoint_url(settings.base_url, endpoint_name)
        try:
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
            "technique, l'intake/cohorte, la date de demarrage et le risque de programme business generaliste.\n\n"
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
            "- level_fit: junior_ok, stretch, too_senior, too_junior ou unknown.\n"
            "- salary_check: meets_or_likely, unknown ou below_min.\n"
            "- remote_check: meets, unknown ou weak.\n"
            "- start_date_check: compatible si l'offre indique un demarrage apres juillet 2026 ou negociable; "
            "too_soon si ASAP/immediat/avant aout 2026; unknown si absent. C'est un signal soft, pas un motif de skip seul.\n"
            "- start_date_evidence: extrait ou date courte, vide si unknown.\n"
            "- why et risks: 1 a 4 phrases courtes chacune, en francais.\n"
            "- application_angle: une phrase concrete pour adapter CV/message.\n"
            "- N'invente pas une information absente de l'offre.\n\n"
            f"Profil:\n{json.dumps(profile_summary, ensure_ascii=False, indent=2)}\n\n"
            f"Offres:\n{json.dumps(jobs, ensure_ascii=False, indent=2)}"
        ),
        "job_count": len(jobs),
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
        payload["text"] = {"format": {"type": "json_object"}}
    return payload


def _chat_payload(settings: LLMSettings, request_payload: dict[str, Any]) -> dict[str, Any]:
    max_output_tokens = _max_output_tokens(int(request_payload.get("job_count") or 1))
    payload: dict[str, Any] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": request_payload["system"]},
            {"role": "user", "content": request_payload["user"]},
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_output_tokens,
    }
    if settings.reasoning_effort != "none":
        payload["reasoning_effort"] = settings.reasoning_effort
    return payload


def _endpoint_url(base_url: str, endpoint_name: str) -> str:
    if endpoint_name in {"responses", "responses_plain"}:
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
        result[stable_id] = {
            "stable_id": stable_id,
            "fit_score": _clamp_score(row.get("fit_score", 50)),
            "priority": _enum(row.get("priority"), VALID_PRIORITIES, "maybe"),
            "level_fit": _enum(row.get("level_fit"), VALID_LEVEL_FITS, "unknown"),
            "salary_check": _enum(row.get("salary_check"), VALID_SALARY_CHECKS, "unknown"),
            "remote_check": _enum(row.get("remote_check"), VALID_REMOTE_CHECKS, "unknown"),
            "start_date_check": _enum(row.get("start_date_check"), VALID_START_DATE_CHECKS, "unknown"),
            "start_date_evidence": normalize_space(str(row.get("start_date_evidence", "")))[:500],
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
                "combined_score": round((score * 0.70) + (fit_score * 0.30), 2),
                "score": round(score, 2),
                "llm_fit_score": round(fit_score, 2),
                "priority": judgement["priority"],
                "level_fit": judgement["level_fit"],
                "salary_check": judgement["salary_check"],
                "remote_check": judgement["remote_check"],
                "start_date_check": judgement["start_date_check"],
                "start_date_evidence": judgement["start_date_evidence"],
                "why": judgement["why"],
                "risks": judgement["risks"],
                "application_angle": judgement["application_angle"],
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "market": job.get("market", ""),
                "location": job.get("location", ""),
                "salary": job.get("salary", ""),
                "source": job.get("source", ""),
                "url": job.get("url", ""),
                "deterministic_reasons": job.get("reasons", [])[:8],
            }
        )
    return merged


def _default_judgement(stable_id: str) -> dict[str, Any]:
    return {
        "stable_id": stable_id,
        "fit_score": 50,
        "priority": "maybe",
        "level_fit": "unknown",
        "salary_check": "unknown",
        "remote_check": "unknown",
        "start_date_check": "unknown",
        "start_date_evidence": "",
        "why": ["Le LLM n'a pas renvoye de jugement exploitable pour cette offre."],
        "risks": ["Verification manuelle requise."],
        "application_angle": "",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
                f"- Fit: niveau `{item['level_fit']}` | salaire `{item['salary_check']}` | remote `{item['remote_check']}` | start `{item['start_date_check']}`",
                f"- Evidence demarrage: {item.get('start_date_evidence') or 'n/a'}",
                f"- Marche: `{item['market']}` | Lieu: {item['location'] or 'n/a'} | Source: `{item['source']}`",
                f"- Salaire publie: {item['salary'] or 'n/a'}",
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
