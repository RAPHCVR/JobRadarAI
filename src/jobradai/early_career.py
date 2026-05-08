from __future__ import annotations

import re
import unicodedata
from typing import Any

from jobradai.text import clean_html, normalize_space, text_blob


EARLY_CAREER_FITS = {"high", "medium", "low", "none"}

_STRUCTURED_RE = re.compile(
    r"\b("
    r"graduate(?:\s+[a-z0-9/&+.-]+){0,5}\s+(?:programme|program|scheme)|"
    r"graduate programme|graduate program|graduate scheme|graduate development program|"
    r"graduate development programme|tech grad program|tech graduate program|graduate accelerator|"
    r"early careers? programme|early careers? program|campus programme|campus program|"
    r"early talent programme|early talent program|emerging talent program|emerging talent programme|"
    r"trainee programme|trainee program|academy programme|academy program|future leaders programme|future leaders program"
    r")\b",
    re.IGNORECASE,
)
_EARLY_RE = re.compile(
    r"\b("
    r"new grad|new graduate|early careers?|campus|entry[- ]level|junior|"
    r"early talent|emerging talent|associate engineer|associate data|trainee|academy|"
    r"school leaver|young graduate|future leaders"
    r")\b",
    re.IGNORECASE,
)
_EARLY_CONTEXT_RE = re.compile(
    r"\b(new grad|new graduate|early careers?|campus hiring|early talent|emerging talent|future leaders)\b",
    re.IGNORECASE,
)
_GRADUATE_ROLE_RE = re.compile(
    r"\b("
    r"graduate\s+(?:data|ai|artificial intelligence|machine learning|ml|software|technology|tech|analytics?|engineering|engineer|analyst|scientist)|"
    r"(?:data|ai|machine learning|ml|software|technology|tech|analytics?|engineering)\s+graduate"
    r")\b",
    re.IGNORECASE,
)
_TECH_RE = re.compile(
    r"\b("
    r"data engineer|data engineering|data platform|analytics engineer|data analyst|data science|"
    r"data scientist|ai engineer|artificial intelligence|machine learning|ml engineer|"
    r"software engineer|backend engineer|platform engineer|mlops|llmops|llm|genai|"
    r"rag|research engineer|applied scientist|nlp|cloud engineer|devops|kubernetes|python|sql"
    r")\b",
    re.IGNORECASE,
)
_TARGET_TITLE_RE = re.compile(
    r"\b("
    r"data engineer|data analyst|data scientist|data science|analytics engineer|"
    r"graduate data|data programme|data program|data analytics|analytics|"
    r"ai engineer|artificial intelligence|machine learning|ml engineer|software engineer|"
    r"backend engineer|platform engineer|mlops|llmops|llm|genai|research engineer|"
    r"applied scientist|nlp|cloud engineer|devops engineer"
    r")\b",
    re.IGNORECASE,
)
_TITLE_MISMATCH_RE = re.compile(
    r"\b("
    r"sales engineer|sales|account|business development|customer success|customer solutions|"
    r"product manager|project manager|program manager|campaign manager|ads specialist|"
    r"marketing|recruiter|talent acquisition|support engineer|bartender|hospitality|"
    r"finance|audit|tax|legal|hr|human resources"
    r")\b",
    re.IGNORECASE,
)
_BUSINESS_ONLY_RE = re.compile(
    r"\b("
    r"sales|account executive|account manager|business development|marketing|recruiter|"
    r"talent acquisition|customer success|finance graduate|audit graduate|tax graduate|"
    r"consulting graduate|management trainee|product manager|program manager"
    r")\b",
    re.IGNORECASE,
)
_INTERNSHIP_RE = re.compile(r"\b(internship|intern|stage|alternance|apprentice|apprenticeship)\b", re.IGNORECASE)


def early_career_signal(job: dict[str, Any]) -> dict[str, Any]:
    title = normalize_space(str(job.get("title") or ""))
    title_only_blob = _normalise(title)
    title_context_blob = _normalise(
        text_blob(
            title,
            str(job.get("employment_type") or ""),
            " ".join(str(item) for item in job.get("tags", []) if item) if isinstance(job.get("tags"), list) else "",
        )
    )
    blob = _normalise(
        text_blob(
            title,
            str(job.get("company") or ""),
            str(job.get("location") or ""),
            str(job.get("employment_type") or ""),
            " ".join(str(item) for item in job.get("tags", []) if item) if isinstance(job.get("tags"), list) else "",
            clean_html(str(job.get("description") or ""))[:6000],
        )
    )
    if not blob:
        return _empty()

    structured = bool(_STRUCTURED_RE.search(blob))
    graduate_role = bool(_GRADUATE_ROLE_RE.search(title_only_blob))
    early_role = bool(_EARLY_RE.search(title_context_blob))
    early_context = bool(_EARLY_CONTEXT_RE.search(blob))
    early = early_role or early_context or graduate_role
    if not structured and not early:
        return _empty()

    tech = bool(_TECH_RE.search(blob))
    title_target = bool(_TARGET_TITLE_RE.search(title_only_blob))
    title_mismatch = bool(_TITLE_MISMATCH_RE.search(title_only_blob))
    business_only = bool(_BUSINESS_ONLY_RE.search(blob)) and not tech
    internship = bool(_INTERNSHIP_RE.search(blob))
    signals: list[str] = []
    risks: list[str] = []
    if structured:
        signals.append("programme structure graduate/early-careers")
    elif graduate_role:
        signals.append("role graduate tech explicite")
    elif early_role or graduate_role:
        signals.append("niveau junior/new-grad explicite")
    elif early_context:
        signals.append("contexte campus/early-careers explicite")
    if tech:
        signals.append("signal data/AI/software")
    if business_only:
        risks.append("programme business/generaliste peu technique")
    if internship:
        risks.append("stage/alternance detecte")
    if title_mismatch:
        risks.append("titre hors coeur data/AI engineering")

    if internship or title_mismatch:
        fit = "low"
    elif tech and structured and title_target:
        fit = "high"
    elif tech and structured:
        fit = "medium"
    elif title_target and tech and early:
        fit = "medium"
    else:
        fit = "low"

    return {
        "is_early_career": True,
        "structured_program": structured,
        "early_career_fit": fit,
        "signals": signals[:4],
        "risks": risks[:4],
    }


def early_career_score(job: dict[str, Any]) -> tuple[float, str]:
    signal = early_career_signal(job)
    fit = signal["early_career_fit"]
    if fit == "high":
        return 88.0, "Graduate/early-career structure et technique: tres compatible new-grad"
    if fit == "medium":
        return 72.0, "Signal graduate/junior compatible, fit technique a verifier"
    if fit == "low":
        return 38.0, "Signal early-career detecte mais programme peu technique ou trop stage"
    return 50.0, ""


def is_target_early_career(job: dict[str, Any]) -> bool:
    return early_career_signal(job).get("early_career_fit") in {"high", "medium"}


def _empty() -> dict[str, Any]:
    return {
        "is_early_career": False,
        "structured_program": False,
        "early_career_fit": "none",
        "signals": [],
        "risks": [],
    }


def _normalise(value: str) -> str:
    stripped = "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )
    return normalize_space(stripped).lower()
