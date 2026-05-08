from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from jobradai.early_career import early_career_score, early_career_signal
from jobradai.models import Job
from jobradai.text import days_old, normalize_space, text_blob


TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
ROLE_NEGATIVE_KEYS = {
    "account_executive",
    "account_manager",
    "business_development",
    "customer_success",
    "marketing",
    "product_manager",
    "program_manager",
    "recruiter",
    "sales_only",
    "solution_engineer",
    "support_engineer",
}


@dataclass(slots=True)
class MarketMatch:
    key: str
    label: str
    score: float
    practicality_score: float
    salary_score: float
    visa_score: float
    language_score: float
    notes: str


def score_jobs(jobs: list[Job], profile: dict[str, Any], markets_config: dict[str, Any]) -> list[Job]:
    market_index = markets_config.get("markets", {})
    for job in jobs:
        market = infer_market(job, market_index)
        job.market = market.key
        technical, tech_reasons = _technical_score(job, profile)
        source_score = _source_score(job)
        freshness_score = _freshness_score(job)
        role_score, role_reasons = _role_score(job, profile)
        salary_signal = _salary_signal(job, profile)
        work_mode_score, work_mode_reason = _work_mode_score(job)
        location_fit_score, location_fit_reason = _location_fit_score(job, profile)
        early_score, early_reason = early_career_score(job.as_dict())
        market_practicality = (
            market.score * 0.42
            + market.practicality_score * 0.18
            + market.salary_score * 0.18
            + market.visa_score * 0.12
            + market.language_score * 0.10
        )
        total = (
            technical * 0.29
            + role_score * 0.16
            + market_practicality * 0.16
            + source_score * 0.11
            + freshness_score * 0.08
            + salary_signal * 0.08
            + work_mode_score * 0.06
            + location_fit_score * 0.04
            + early_score * 0.02
        )
        total = max(0.0, min(100.0, total))
        job.score = round(total, 2)
        job.score_parts = {
            "technical": round(technical, 2),
            "role": round(role_score, 2),
            "market_practicality": round(market_practicality, 2),
            "source": round(source_score, 2),
            "freshness": round(freshness_score, 2),
            "salary": round(salary_signal, 2),
            "work_mode": round(work_mode_score, 2),
            "location_fit": round(location_fit_score, 2),
            "early_career": round(early_score, 2),
        }
        job.reasons = _top_unique(
            [
                f"Marche: {market.label} ({market.notes})",
                *role_reasons,
                early_reason,
                *tech_reasons,
                _source_reason(job),
                _freshness_reason(job),
                _salary_reason(job, profile),
                work_mode_reason,
                location_fit_reason,
            ]
        )
    return sorted(jobs, key=lambda item: item.score, reverse=True)


def infer_market(job: Job, markets: dict[str, Any]) -> MarketMatch:
    location_blob = text_blob(job.location, job.country, " ".join(job.tags)).lower()
    if _looks_us_only(location_blob):
        return _market("other", markets.get("other", {}))
    best_key = "other"
    best_hits = 0
    for key, data in markets.items():
        if key in {"remote_europe", "other"}:
            continue
        aliases = [str(alias).lower() for alias in data.get("aliases", [])]
        hits = sum(1 for alias in aliases if alias and alias in location_blob)
        if hits > best_hits:
            best_key = key
            best_hits = hits
    if best_hits == 0 and _remote_is_targetable(job, location_blob):
        best_key = "remote_europe"
    return _market(best_key, markets.get(best_key, {}))


def _remote_is_targetable(job: Job, location_blob: str) -> bool:
    if any(token in location_blob for token in ["europe", "emea", "worldwide", "anywhere", "global"]):
        return True
    compact = location_blob.replace(",", " ").replace(";", " ").strip()
    if job.remote and compact in {"", "remote"}:
        return True
    if job.remote and compact.startswith("remote ") and len(compact.split()) <= 3:
        return True
    return False


def _market(key: str, data: dict[str, Any]) -> MarketMatch:
    return MarketMatch(
        key=key,
        label=data.get("label", key),
        score=float(data.get("market_score", 60)),
        practicality_score=float(data.get("practicality_score", 60)),
        salary_score=float(data.get("salary_score", 60)),
        visa_score=float(data.get("visa_score", 60)),
        language_score=float(data.get("language_score", 60)),
        notes=data.get("notes", ""),
    )


def _looks_us_only(location_blob: str) -> bool:
    target_country_tokens = [
        "ireland",
        "france",
        "belgium",
        "switzerland",
        "singapore",
        "netherlands",
        "luxembourg",
        "united kingdom",
        "germany",
        "europe",
        "emea",
    ]
    if any(token in location_blob for token in target_country_tokens):
        return False
    if re.search(r"\bus-[a-z]{2}\b|\bus-[a-z]{2}-", location_blob):
        return True
    if any(token in location_blob for token in ["united states", " usa", "u.s.", "dublin, ca", "california"]):
        return True
    return False


def _technical_score(job: Job, profile: dict[str, Any]) -> tuple[float, list[str]]:
    weights = profile.get("weights", {})
    must_have = weights.get("must_have", {})
    good_signals = weights.get("good_signals", {})
    negative = weights.get("negative_signals", {})
    blob = _tokens(text_blob(job.title, job.description, " ".join(job.tags), job.employment_type))
    title_tokens = _tokens(job.title)
    positive = 0.0
    max_positive = _technical_ceiling(must_have, good_signals)
    reasons: list[str] = []
    for key, weight in must_have.items():
        if _keyword_hit(key, blob):
            positive += float(weight) * 1.35
            reasons.append(f"Signal fort: {key.replace('_', ' ')}")
    for key, weight in good_signals.items():
        if _keyword_hit(key, blob):
            positive += float(weight) * 0.75
            reasons.append(f"Signal utile: {key.replace('_', ' ')}")
    penalty = 0.0
    for key, weight in negative.items():
        try:
            penalty_weight = abs(float(weight))
        except (TypeError, ValueError):
            continue
        if penalty_weight <= 0:
            continue
        tokens = title_tokens if key in ROLE_NEGATIVE_KEYS else blob
        if _keyword_hit(key, tokens):
            penalty += penalty_weight
            reasons.append(f"Penalite: {key.replace('_', ' ')}")
    score = 100.0 * positive / max(max_positive, 1.0)
    score = max(0.0, min(100.0, score - penalty))
    if not reasons:
        reasons.append("Peu de signaux data/IA/LLM explicites")
    return score, reasons[:8]


def _technical_ceiling(must_have: dict[str, Any], good_signals: dict[str, Any]) -> float:
    must_ceiling = sum(sorted((float(v) for v in must_have.values()), reverse=True)[:8]) * 1.35
    good_ceiling = sum(sorted((float(v) for v in good_signals.values()), reverse=True)[:5]) * 0.75
    return max(must_ceiling + good_ceiling, 1.0)


def _role_score(job: Job, profile: dict[str, Any]) -> tuple[float, list[str]]:
    titles = [title.lower() for title in profile.get("search", {}).get("titles", [])]
    title = job.title.lower()
    score = 45.0
    reasons: list[str] = []
    matched_target = False
    early_signal = early_career_signal(job.as_dict())
    for target in titles:
        if target in title:
            score = 92.0
            matched_target = True
            reasons.append(f"Titre tres proche: {target}")
            break
    level_penalty, level_reason = _level_mismatch_penalty(job, title, profile)
    if level_penalty:
        score -= level_penalty
        reasons.append(level_reason)
    elif "senior" in title or "staff" in title or "lead" in title or "principal" in title:
        score += 3
        reasons.append("Niveau senior/lead potentiellement pertinent")
    if any(term in title for term in ["intern", "internship", "stage", "apprentice", "alternance"]):
        score -= 42
        reasons.append("Stage/alternance trop junior pour la cible actuelle")
    elif "junior" in title or "graduate" in title or "new grad" in title or "entry level" in title:
        if profile.get("career", {}).get("entry_level_allowed", False):
            if early_signal.get("early_career_fit") in {"high", "medium"}:
                score += 4
                reasons.append("Niveau graduate/junior tech compatible avec profil new-grad")
            else:
                score -= 4
                reasons.append("Niveau junior/graduate acceptable si salaire et fit solides")
        else:
            score -= 35
            reasons.append("Niveau trop junior")
    elif early_signal.get("early_career_fit") in {"high", "medium"} and profile.get("career", {}).get("entry_level_allowed", False):
        score += 4
        reasons.append("Programme early-career tech compatible avec profil new-grad")
    if "research" in title:
        score += 5
        reasons.append("Axe recherche detecte")
    if _is_vie_job(job):
        if _is_junior_profile(profile):
            score += 8
            reasons.append("VIE: mission internationale compatible junior/new-grad")
        else:
            score += 2
            reasons.append("VIE: mission internationale a evaluer separement d'un CDI")
    penalty, reason = _non_target_title_penalty(title, matched_target)
    if penalty:
        score -= penalty
        reasons.append(reason)
    return max(0.0, min(100.0, score)), reasons


def _level_mismatch_penalty(job: Job, title: str, profile: dict[str, Any]) -> tuple[float, str]:
    career = profile.get("career", {})
    target_level = str(career.get("target_level", "")).lower()
    if not _is_junior_profile(profile):
        return 0.0, ""

    penalties: list[tuple[float, str]] = []
    title_penalties = [
        ("head of", 45.0),
        ("director", 45.0),
        ("principal", 38.0),
        ("staff", 34.0),
        ("lead", 32.0),
        ("architect", 28.0),
        ("senior consultant", 28.0),
        ("senior", 22.0),
    ]
    for token, penalty in title_penalties:
        if token in title:
            penalties.append((penalty, f"Niveau {token} en tension avec profil junior/new-grad"))

    blob = text_blob(job.title, job.description, job.employment_type).lower()
    years = _required_years(blob)
    if years >= 5:
        penalties.append((28.0, f"Experience exigee elevee: {years:.0f}+ ans"))
    elif years >= 3:
        penalties.append((14.0, f"Experience exigee a verifier: {years:.0f}+ ans"))

    if not penalties:
        return 0.0, ""
    penalty, reason = max(penalties, key=lambda item: item[0])
    return penalty, reason


def _required_years(blob: str) -> float:
    years: list[float] = []
    patterns = [
        r"(\d+(?:[,.]\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience",
        r"(\d+(?:[,.]\d+)?)\s*\+?\s*ans?\s+d['e ]experience",
        r"experience\s+(?:of\s+)?(\d+(?:[,.]\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"experience\s+de\s+(\d+(?:[,.]\d+)?)\s*\+?\s*ans?",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, blob):
            try:
                years.append(float(match.group(1).replace(",", ".")))
            except ValueError:
                continue
    return max(years, default=0.0)


def _non_target_title_penalty(title: str, matched_target: bool) -> tuple[float, str]:
    if matched_target:
        return 0.0, ""
    hard_mismatches = [
        "account executive",
        "account manager",
        "business development",
        "business developer",
        "commercial solution engineer",
        "customer success",
        "field marketing",
        "growth marketing",
        "product marketing",
        "recruiter",
        "sales manager",
        "sales representative",
        "talent acquisition",
    ]
    softer_mismatches = [
        "product manager",
        "program manager",
        "project manager",
        "support engineer",
        "solution engineer",
        "solutions engineer",
        "solution architect",
    ]
    if any(term in title for term in hard_mismatches):
        return 40.0, "Penalite titre: role business/sales/recrutement"
    if any(term in title for term in softer_mismatches):
        return 24.0, "Penalite titre: role adjacent mais pas coeur data/IA engineering"
    return 0.0, ""


def _source_score(job: Job) -> float:
    if job.source_type == "official_api":
        return 95.0
    if job.source_type == "ats":
        return 92.0
    if job.source_type == "paid_api":
        return 82.0
    if job.source_type == "public_api":
        return 74.0
    if job.source_type == "scraper_api":
        return 58.0
    return 50.0


def _freshness_score(job: Job) -> float:
    age = days_old(job.posted_at)
    if age is None:
        return 45.0
    if age <= 1:
        return 100.0
    if age <= 3:
        return 90.0
    if age <= 7:
        return 78.0
    if age <= 21:
        return 60.0
    if age <= 60:
        return 35.0
    return 15.0


def _salary_signal(job: Job, profile: dict[str, Any]) -> float:
    if _is_vie_job(job):
        monthly = _vie_monthly_allowance(job.salary)
        minimum = float(profile.get("constraints", {}).get("vie_minimum_monthly_allowance_eur", 0) or 0)
        if monthly is None:
            return 58.0
        if monthly >= 3200:
            return 84.0
        if monthly >= 2700:
            return 76.0
        if monthly >= 2200:
            return 68.0
        if minimum and monthly >= minimum:
            return 60.0
        return 42.0
    minimum = float(profile.get("constraints", {}).get("minimum_annual_salary_eur", 0) or 0)
    annual = _annual_salary_estimate(job.salary)
    if annual is None:
        return 52.0
    if minimum and annual < minimum * 0.90:
        return 18.0
    if minimum and annual < minimum:
        return 35.0
    if annual >= 140000:
        return 100.0
    if annual >= 100000:
        return 94.0
    if annual >= 75000:
        return 84.0
    if annual >= 55000:
        return 72.0
    if minimum and annual >= minimum:
        return 60.0
    return 45.0


def _source_reason(job: Job) -> str:
    labels = {
        "official_api": "Source propre/officielle",
        "ats": "Source ATS directe, generalement fraiche et fiable",
        "paid_api": "Agregateur API payant/controle",
        "public_api": "API publique sans login",
        "scraper_api": "Fallback scraper, a verifier avant action",
    }
    return labels.get(job.source_type, "Source inconnue")


def _freshness_reason(job: Job) -> str:
    age = days_old(job.posted_at)
    if age is None:
        return "Date de publication non fournie"
    return f"Fraicheur: {age:.1f} jours"


def _salary_reason(job: Job, profile: dict[str, Any]) -> str:
    if _is_vie_job(job):
        monthly = _vie_monthly_allowance(job.salary)
        if monthly is None:
            return "Indemnite VIE non indiquee, non comparable a un brut CDI"
        return f"Indemnite VIE: ~{monthly:.0f} EUR/mois, non comparee a un brut CDI"
    minimum = float(profile.get("constraints", {}).get("minimum_annual_salary_eur", 0) or 0)
    annual = _annual_salary_estimate(job.salary)
    if annual is None:
        suffix = f", a verifier vs min {minimum:.0f} EUR" if minimum else ""
        return f"Salaire non indique{suffix}"
    if minimum and annual < minimum:
        return f"Salaire estime sous minimum: ~{annual:.0f} EUR/an < {minimum:.0f}"
    return f"Salaire estime/indique: ~{annual:.0f} EUR/an"


def _annual_salary_estimate(salary: str) -> float | None:
    raw = normalize_space(salary).lower()
    if not raw:
        return None
    values = _salary_numbers(raw)
    if not values:
        return None
    best = max(values)
    if any(token in raw for token in ["hour", "heure", "horaire"]) and best < 1000:
        return best * 1820
    if any(token in raw for token in ["day", "daily", "jour", "journalier"]) and best < 2000:
        return best * 220
    if any(token in raw for token in ["week", "weekly", "semaine", "hebdo"]) and best < 5000:
        return best * 52
    if any(token in raw for token in ["month", "monthly", "mois", "mensuel"]) and best < 10000:
        return best * 12
    if best < 10000:
        return None
    return best


def _vie_monthly_allowance(salary: str) -> float | None:
    raw = normalize_space(salary).lower()
    if "vie" not in raw and "volontariat" not in raw:
        return None
    values = _salary_numbers(raw)
    if not values:
        return None
    best = max(values)
    if best > 10000:
        return best / 12
    return best


def _salary_numbers(value: str) -> list[float]:
    numbers: list[float] = []
    for match in re.finditer(r"(\d+(?:[.,]\d+)?)\s*k\b", value):
        numbers.append(float(match.group(1).replace(",", ".")) * 1000)
    for match in re.finditer(r"\d+(?:[ .]\d{3})*(?:[,.]\d+)?", value):
        raw = match.group(0)
        compact = raw.replace(" ", "")
        if re.fullmatch(r"\d+[,.]\d{1,2}", compact):
            compact = compact.replace(",", ".")
        else:
            compact = compact.replace(".", "").replace(",", "")
        try:
            number = float(compact)
        except ValueError:
            continue
        if number >= 10:
            numbers.append(number)
    return numbers


def _work_mode_score(job: Job) -> tuple[float, str]:
    blob = text_blob(job.title, job.location, job.description, job.employment_type, " ".join(job.tags)).lower()
    location_blob = text_blob(job.location, job.country, job.employment_type, " ".join(job.tags)).lower()
    if (
        job.remote
        or any(token in blob for token in ["fully remote", "remote-first", "remote first", "remote europe"])
        or re.search(r"\bremote\b", location_blob)
    ):
        return 95.0, "Mode travail: remote explicite"
    hybrid_tokens = [
        "hybrid",
        "hybride",
        "teletravail",
        "télétravail",
        "home office",
        "work from home",
        "2 days remote",
        "two days remote",
        "2 jours",
        "deux jours",
    ]
    if any(token in blob for token in hybrid_tokens):
        return 86.0, "Mode travail: hybride/teletravail explicite"
    onsite_tokens = ["onsite only", "on-site only", "fully onsite", "office-based", "presentiel", "présentiel"]
    if any(token in blob for token in onsite_tokens):
        return 28.0, "Mode travail: presentiel strict, sous preference 2j remote"
    return 58.0, "Mode travail non indique, a verifier vs preference 2j remote"


def _location_fit_score(job: Job, profile: dict[str, Any]) -> tuple[float, str]:
    constraints = profile.get("constraints", {})
    aliases = [str(city).lower() for city in constraints.get("major_cities", [])]
    blob = text_blob(job.location, job.country, " ".join(job.tags)).lower()
    if not blob:
        return 55.0, "Localisation peu detaillee"
    if any(alias and alias in blob for alias in aliases):
        return 90.0, "Localisation: grande ville cible"
    if job.market == "remote_europe" or any(token in blob for token in ["remote europe", "emea", "europe"]):
        return 82.0, "Localisation: remote Europe compatible"
    if job.market in set(profile.get("search", {}).get("target_markets", [])):
        return 66.0, "Localisation: marche cible, ville a verifier"
    return 45.0, "Localisation hors preference"


def _is_vie_job(job: Job) -> bool:
    source = normalize_space(job.source).lower()
    employment = normalize_space(job.employment_type).lower()
    tags = text_blob(" ".join(job.tags)).lower()
    if "business france vie" in source:
        return True
    return bool(re.search(r"\bv\.?i\.?e\b", employment)) or "volontariat international en entreprise" in tags


def _is_junior_profile(profile: dict[str, Any]) -> bool:
    target_level = str(profile.get("career", {}).get("target_level", "")).lower()
    return any(token in target_level for token in ["junior", "new_grad", "entry"])


def _tokens(value: str) -> set[str]:
    normalized = normalize_space(value).lower()
    tokens = set(TOKEN_RE.findall(normalized))
    compact = normalized.replace("-", " ").replace("/", " ")
    words = TOKEN_RE.findall(compact)
    tokens.update(words)
    for size in (2, 3):
        for index in range(0, max(0, len(words) - size + 1)):
            tokens.add("_".join(words[index : index + size]))
    if re.search(r"\bllms?\b", normalized) or "large language model" in normalized:
        tokens.add("llm")
    if re.search(r"\brag\b", normalized) or "retrieval augmented" in normalized:
        tokens.add("rag")
    if "data engineer" in normalized or "data engineering" in normalized:
        tokens.add("data_engineering")
    if (
        "graduate programme" in normalized
        or "graduate program" in normalized
        or "graduate scheme" in normalized
        or re.search(r"\bgraduate(?:\s+[a-z0-9/&+.-]+){0,5}\s+(?:programme|program|scheme)\b", normalized)
    ):
        tokens.add("graduate_program")
        tokens.add("early_career")
    if "new grad" in normalized or "new graduate" in normalized:
        tokens.add("new_grad")
        tokens.add("early_career")
    if (
        "early careers" in normalized
        or "early career" in normalized
        or "early talent" in normalized
        or "emerging talent" in normalized
        or "campus" in normalized
    ):
        tokens.add("campus_hiring")
        tokens.add("early_career")
    if "llmops" in normalized or "llm ops" in normalized:
        tokens.add("llmops")
    if "mlops" in normalized or "ml ops" in normalized:
        tokens.add("mlops")
    if "vector database" in normalized or "vector db" in normalized:
        tokens.add("vector_database")
    if "applied research" in normalized:
        tokens.add("applied_research")
    if "mechanistic interpretability" in normalized or "interpretability" in normalized and "mechanistic" in normalized:
        tokens.add("mechanistic_interpretability")
    if (
        "explainability" in normalized
        or "explicabilite" in normalized
        or "explicabilité" in normalized
        or re.search(r"\bxai\b", normalized)
        or "interpretability" in normalized
        or "interprétabilité" in normalized
        or "interpretabilite" in normalized
    ):
        tokens.add("explainability")
    if "ai safety" in normalized or "safety training" in normalized or "safeguards" in normalized:
        tokens.add("ai_safety")
    if "information retrieval" in normalized:
        tokens.add("information_retrieval")
    if "knowledge graph" in normalized or "knowledge graphs" in normalized:
        tokens.add("knowledge_graph")
    if "time series" in normalized or "timeseries" in normalized or "séries temporelles" in normalized:
        tokens.add("time_series")
    if "anomaly detection" in normalized or "detection d anomal" in normalized or "détection d anomal" in normalized:
        tokens.add("anomaly_detection")
    if "root cause" in normalized or re.search(r"\brca\b", normalized):
        tokens.add("root_cause_analysis")
    if "azure kubernetes service" in normalized or re.search(r"\baks\b", normalized):
        tokens.add("aks")
    if "azure devops" in normalized:
        tokens.add("azure_devops")
    if "github actions" in normalized:
        tokens.add("github_actions")
    if "document intelligence" in normalized:
        tokens.add("document_intelligence")
    if "open telemetry" in normalized or "opentelemetry" in normalized:
        tokens.add("opentelemetry")
    if "vector search" in normalized:
        tokens.add("vector_database")
    if "ragas" in normalized:
        tokens.add("ragas")
    if "websocket" in normalized or "websockets" in normalized:
        tokens.add("websockets")
    if "prompt engineer" in normalized and "software" not in normalized and "platform" not in normalized:
        tokens.add("prompt_engineer_only")
    if "product manager" in normalized:
        tokens.add("product_manager")
    if "program manager" in normalized:
        tokens.add("program_manager")
    if "account executive" in normalized:
        tokens.add("account_executive")
    if "account manager" in normalized:
        tokens.add("account_manager")
    if "business development" in normalized or "business developer" in normalized:
        tokens.add("business_development")
    if "customer success" in normalized:
        tokens.add("customer_success")
    if "marketing" in normalized:
        tokens.add("marketing")
    if "recruiter" in normalized or "talent acquisition" in normalized:
        tokens.add("recruiter")
    if "solution engineer" in normalized or "solutions engineer" in normalized or "solution architect" in normalized:
        tokens.add("solution_engineer")
    if "support engineer" in normalized:
        tokens.add("support_engineer")
    if "apprentice" in normalized or "apprenticeship" in normalized or "alternance" in normalized:
        tokens.add("apprenticeship")
    if "sales" in normalized and "engineer" not in normalized:
        tokens.add("sales_only")
    return tokens


def _keyword_hit(key: str, tokens: set[str]) -> bool:
    normalized = key.lower().replace("-", "_").replace(" ", "_")
    return normalized in tokens or normalized.replace("_", "") in {token.replace("_", "") for token in tokens}


def _top_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= 10:
            break
    return output
