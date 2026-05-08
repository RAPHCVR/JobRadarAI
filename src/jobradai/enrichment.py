from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from jobradai.scoring import _annual_salary_estimate, _vie_monthly_allowance
from jobradai.text import clean_html, normalize_space, text_blob


START_DATE_CHECKS = {"compatible", "too_soon", "unknown"}
SALARY_CHECKS = {"meets_or_likely", "unknown", "below_min"}
REMOTE_CHECKS = {"meets", "unknown", "weak"}

DEFAULT_TARGET_START_AFTER = date(2026, 8, 1)
DEFAULT_AVAILABILITY_NOTE = (
    "Je termine mon stage AI Researcher chez Aubay en juillet 2026 et suis disponible "
    "a partir d'aout/septembre 2026."
)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "janvier": 1,
    "feb": 2,
    "february": 2,
    "fevrier": 2,
    "mar": 3,
    "march": 3,
    "mars": 3,
    "apr": 4,
    "april": 4,
    "avril": 4,
    "may": 5,
    "mai": 5,
    "jun": 6,
    "june": 6,
    "juin": 6,
    "jul": 7,
    "july": 7,
    "juillet": 7,
    "aug": 8,
    "august": 8,
    "aout": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "septembre": 9,
    "oct": 10,
    "october": 10,
    "octobre": 10,
    "nov": 11,
    "november": 11,
    "novembre": 11,
    "dec": 12,
    "december": 12,
    "decembre": 12,
}

_MONTH_RE = "|".join(sorted((re.escape(key) for key in _MONTHS), key=len, reverse=True))
_START_CONTEXT_RE = re.compile(
    r"\b("
    r"start|starting|starts|commence|commencement|debut|demarrage|demarrer|"
    r"prise de poste|date de debut|available|availability|disponible|"
    r"intake|cohort|rentree|entry date|joining date"
    r")\b",
    re.IGNORECASE,
)
_IMMEDIATE_START_RE = re.compile(
    r"\b("
    r"asap|immediate start|start immediately|available immediately|"
    r"des que possible|d que possible|immediat|immediate availability|urgent start"
    r")\b",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(rf"\b(?P<month>{_MONTH_RE})\.?\s+(?P<year>20\d{{2}})\b", re.IGNORECASE)
_YEAR_MONTH_RE = re.compile(r"\b(?P<year>20\d{2})[-/](?P<month>0?[1-9]|1[0-2])\b")
_RENTREE_RE = re.compile(r"\brentree\s+(?P<year>20\d{2})\b", re.IGNORECASE)


def infer_start_date_check(job: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, str]:
    """Infer a soft start-date compatibility signal from explicit job text only."""

    target_start = _target_start_after(profile or {})
    text = _job_text(job)
    if not text:
        return {"check": "unknown", "evidence": ""}

    normalized = _strip_accents(text).lower()
    immediate = _IMMEDIATE_START_RE.search(normalized)
    if immediate:
        return {"check": "too_soon", "evidence": _snippet(text, immediate.start(), immediate.end())}

    explicit_date = _find_contextual_start_date(normalized)
    if explicit_date is None:
        return {"check": "unknown", "evidence": ""}

    check = "compatible" if explicit_date >= target_start else "too_soon"
    return {"check": check, "evidence": explicit_date.isoformat()[:7]}


def effective_start_date_check(
    job: dict[str, Any],
    shortlist_item: dict[str, Any] | None,
    profile: dict[str, Any] | None = None,
) -> tuple[str, str]:
    llm_check = _enum((shortlist_item or {}).get("start_date_check"), START_DATE_CHECKS, "unknown")
    llm_evidence = normalize_space(str((shortlist_item or {}).get("start_date_evidence") or ""))[:500]
    if llm_check != "unknown":
        return llm_check, llm_evidence
    inferred = infer_start_date_check(job, profile)
    return inferred["check"], inferred["evidence"]


def effective_salary_check(
    job: dict[str, Any],
    shortlist_item: dict[str, Any] | None,
    profile: dict[str, Any] | None = None,
) -> str:
    llm_check = _enum((shortlist_item or {}).get("salary_check"), SALARY_CHECKS, "unknown")
    if llm_check != "unknown":
        return llm_check
    profile = profile or {}
    if _is_vie_job(job):
        monthly = _vie_monthly_allowance(_salary_blob(job))
        minimum = _float(profile.get("constraints", {}).get("vie_minimum_monthly_allowance_eur"), 1800)
        if monthly is None:
            return "unknown"
        return "meets_or_likely" if monthly >= minimum else "below_min"
    annual = _annual_salary_estimate(_salary_blob(job))
    minimum = _float(profile.get("constraints", {}).get("minimum_annual_salary_eur"), 45000)
    if annual is None:
        return "unknown"
    if annual < minimum * 0.90:
        return "below_min"
    return "meets_or_likely"


def effective_remote_check(job: dict[str, Any], shortlist_item: dict[str, Any] | None) -> str:
    llm_check = _enum((shortlist_item or {}).get("remote_check"), REMOTE_CHECKS, "unknown")
    if llm_check != "unknown":
        return llm_check
    blob = _strip_accents(_job_text(job)).lower()
    if bool(job.get("remote")):
        return "meets"
    if re.search(r"\b(fully remote|remote-first|remote first|remote europe|hybrid|hybride|teletravail|home office|work from home)\b", blob):
        return "meets"
    if re.search(r"\b(onsite only|on-site only|fully onsite|office-based|presentiel|no remote|non remote)\b", blob):
        return "weak"
    return "unknown"


def build_recruiter_message(item: dict[str, Any]) -> str:
    title = normalize_space(str(item.get("title") or "votre offre"))
    company = normalize_space(str(item.get("company") or "votre equipe"))
    angle = normalize_space(str(item.get("last_application_angle") or ""))
    start_check = normalize_space(str(item.get("last_start_date_check") or "unknown"))
    salary_check = normalize_space(str(item.get("last_salary_check") or "unknown"))
    remote_check = normalize_space(str(item.get("last_remote_check") or "unknown"))

    lines = [
        "Bonjour,",
        "",
        f"Je vous contacte au sujet de l'offre {title} chez {company}.",
    ]
    if angle:
        lines.append(f"Mon angle principal: {angle}")
    else:
        lines.append(
            "Mon angle principal: profil data/IA oriente production, LLM/RAG/MLOps et recherche appliquee."
        )
    lines.append(DEFAULT_AVAILABILITY_NOTE)

    confirmations: list[str] = []
    if start_check in {"unknown", "too_soon"}:
        confirmations.append("le calendrier de demarrage est compatible avec une disponibilite aout/septembre 2026")
    if salary_check == "unknown":
        confirmations.append("la fourchette de remuneration est compatible avec une cible d'au moins 45k EUR/an")
    elif salary_check == "below_min":
        confirmations.append("la remuneration est negociable ou compensee par le perimetre de mission")
    if remote_check == "unknown":
        confirmations.append("le rythme hybride/remote permet au moins deux jours de teletravail")
    elif remote_check == "weak":
        confirmations.append("un rythme hybride est envisageable malgre l'indication presentielle")

    if confirmations:
        lines.append("Pouvez-vous me confirmer ces points: " + " ; ".join(confirmations) + " ?")
    else:
        lines.append("Je serais interesse par un echange pour verifier le fit et les prochaines etapes.")
    lines.extend(["", "Bien cordialement,"])
    return "\n".join(lines)


def availability_note(profile: dict[str, Any] | None = None) -> str:
    constraints = (profile or {}).get("constraints", {})
    note = normalize_space(str(constraints.get("availability_note") or ""))
    return note or DEFAULT_AVAILABILITY_NOTE


def _find_contextual_start_date(normalized: str) -> date | None:
    candidates: list[date] = []
    for match in _MONTH_YEAR_RE.finditer(normalized):
        if not _has_start_context(normalized, match.start(), match.end()):
            continue
        month = _MONTHS.get(match.group("month").lower().rstrip("."))
        if month:
            candidates.append(date(int(match.group("year")), month, 1))
    for match in _YEAR_MONTH_RE.finditer(normalized):
        if not _has_start_context(normalized, match.start(), match.end()):
            continue
        candidates.append(date(int(match.group("year")), int(match.group("month")), 1))
    for match in _RENTREE_RE.finditer(normalized):
        candidates.append(date(int(match.group("year")), 9, 1))
    return min(candidates) if candidates else None


def _has_start_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 90) : min(len(text), end + 60)]
    return bool(_START_CONTEXT_RE.search(window))


def _target_start_after(profile: dict[str, Any]) -> date:
    constraints = profile.get("constraints", {}) if isinstance(profile.get("constraints"), dict) else {}
    explicit = _parse_year_month(str(constraints.get("target_start_after") or ""))
    if explicit:
        return explicit
    current = profile.get("current_experience", {}) if isinstance(profile.get("current_experience"), dict) else {}
    end = _parse_year_month(str(current.get("end") or ""))
    if not end:
        return DEFAULT_TARGET_START_AFTER
    month = end.month + 1
    year = end.year
    if month > 12:
        month = 1
        year += 1
    return date(year, month, 1)


def _parse_year_month(value: str) -> date | None:
    match = re.match(r"^\s*(20\d{2})-(0?[1-9]|1[0-2])(?:-\d{1,2})?\s*$", value)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), 1)


def _salary_blob(job: dict[str, Any]) -> str:
    return text_blob(
        str(job.get("salary") or ""),
        clean_html(str(job.get("description") or ""))[:5000],
        str(job.get("employment_type") or ""),
        " ".join(str(item) for item in job.get("tags", []) if item) if isinstance(job.get("tags"), list) else "",
    )


def _job_text(job: dict[str, Any]) -> str:
    return text_blob(
        str(job.get("title") or ""),
        str(job.get("company") or ""),
        str(job.get("location") or ""),
        str(job.get("salary") or ""),
        str(job.get("employment_type") or ""),
        " ".join(str(item) for item in job.get("tags", []) if item) if isinstance(job.get("tags"), list) else "",
        clean_html(str(job.get("description") or ""))[:8000],
    )


def _snippet(text: str, start: int, end: int) -> str:
    begin = max(0, start - 50)
    finish = min(len(text), end + 80)
    return normalize_space(text[begin:finish])[:500]


def _strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )


def _is_vie_job(job: dict[str, Any]) -> bool:
    source = normalize_space(str(job.get("source") or "")).lower()
    employment = normalize_space(str(job.get("employment_type") or "")).lower()
    tags_value = job.get("tags", [])
    tags = " ".join(str(item) for item in tags_value) if isinstance(tags_value, list) else str(tags_value)
    tags = normalize_space(tags).lower()
    return (
        "business france vie" in source
        or bool(re.search(r"\bv\.?i\.?e\b", employment))
        or "volontariat international en entreprise" in tags
    )


def _enum(value: Any, allowed: set[str], default: str) -> str:
    raw = normalize_space(str(value or "")).lower()
    return raw if raw in allowed else default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
