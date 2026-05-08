from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from jobradai.http import HttpClient, HttpError
from jobradai.models import Job
from jobradai.queries import select_query_terms
from jobradai.text import clean_html, contains_any, normalize_space, text_blob


def query_terms(config: dict[str, Any], *, limit: int | None = None, early_career_min: int = 0) -> list[str]:
    return select_query_terms(config, limit=limit, early_career_min=early_career_min)


def fetch_business_france_vie(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("business_france_vie", {})
    endpoint = str(settings.get("endpoint") or "https://civiweb-api-prd.azurewebsites.net/api/Offers/search")
    limit = int(settings.get("page_size") or settings.get("results_per_query", 100) or 100)
    max_results = int(settings.get("max_results", 1200) or 1200)
    max_queries = int(settings.get("max_queries", 10) or 10)
    scan_all = bool(settings.get("scan_all", True))
    query_scan = bool(settings.get("query_scan", False))
    terms = [str(term).strip() for term in settings.get("queries", []) if str(term).strip()]
    if not terms:
        terms = query_terms(config, limit=max_queries, early_career_min=2)
    scan_terms: list[str | None] = []
    if scan_all:
        scan_terms.append(None)
    if query_scan or not scan_terms:
        scan_terms.extend(terms[:max_queries])

    jobs: list[Job] = []
    seen: set[str] = set()
    for term in scan_terms:
        for item in _business_france_pages(endpoint, http, term=term, limit=limit, max_results=max_results):
            if str(item.get("missionType") or item.get("missionTypeEn") or "").upper() != "VIE":
                continue
            offer_id = str(item.get("id") or item.get("reference") or "").strip()
            if offer_id and offer_id in seen:
                continue
            if offer_id:
                seen.add(offer_id)
            jobs.append(_business_france_vie_job(item))
    return jobs


def _business_france_pages(
    endpoint: str,
    http: HttpClient,
    *,
    term: str | None,
    limit: int,
    max_results: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skip = 0
    page_size = max(1, min(limit, 200))
    cap = max(page_size, max_results)
    while skip < cap:
        payload: dict[str, Any] = {"skip": skip, "limit": page_size}
        if term:
            payload["query"] = term
            payload["searchQuery"] = term
        body = json.dumps(payload).encode("utf-8")
        data = http.fetch_json(
            endpoint,
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            body=body,
        )
        page = data.get("result", []) if isinstance(data, dict) else []
        if not isinstance(page, list) or not page:
            break
        rows.extend(item for item in page if isinstance(item, dict))
        total = _safe_int(data.get("count")) if isinstance(data, dict) else None
        skip += page_size
        if len(page) < page_size:
            break
        if total is not None and skip >= total:
            break
    return rows


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _business_france_vie_job(item: dict[str, Any]) -> Job:
    offer_id = str(item.get("id") or "").strip()
    city = normalize_space(item.get("cityNameEn") or item.get("cityName") or item.get("cityAffectation"))
    country = normalize_space(item.get("countryNameEn") or item.get("countryName"))
    duration = item.get("missionDuration")
    mission_type = normalize_space(item.get("missionTypeEn") or item.get("missionType") or "VIE")
    telework = bool(item.get("teleworkingAvailable"))
    tags = [
        "vie",
        "volontariat international en entreprise",
        normalize_space(str(item.get("countryId") or "")),
    ]
    if telework:
        tags.append("teletravail possible")
    description = clean_html(
        text_blob(
            item.get("organizationPresentation"),
            item.get("missionDescription"),
            item.get("missionProfile"),
            item.get("contactURL"),
        )
    )
    salary = _vie_allowance(item.get("indemnite"))
    url = f"https://mon-vie-via.businessfrance.fr/offres/{offer_id}" if offer_id else ""
    return Job(
        source="Business France VIE",
        source_type="official_api",
        title=normalize_space(item.get("missionTitle")),
        company=normalize_space(item.get("organizationName")),
        url=url,
        apply_url=url,
        location=normalize_space(", ".join(part for part in [city, country] if part)),
        country=country,
        remote=telework,
        description=description,
        posted_at=item.get("startBroadcastDate") or item.get("creationDate") or "",
        salary=salary,
        employment_type=normalize_space(f"{mission_type} {duration} mois" if duration else mission_type),
        tags=[tag for tag in tags if tag],
        raw_id=normalize_space(item.get("reference") or offer_id),
    )


def _vie_allowance(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    return f"Indemnite VIE mensuelle {amount:.2f} EUR"


def fetch_remotive(config: dict[str, Any], http: HttpClient) -> list[Job]:
    jobs: list[Job] = []
    for term in query_terms(config, limit=20, early_career_min=5):
        data = http.fetch_json("https://remotive.com/api/remote-jobs", {"search": term, "limit": 80})
        for item in data.get("jobs", []):
            jobs.append(
                Job(
                    source="Remotive",
                    source_type="public_api",
                    title=normalize_space(item.get("title")),
                    company=normalize_space(item.get("company_name")),
                    url=item.get("url", ""),
                    apply_url=item.get("url", ""),
                    location=normalize_space(item.get("candidate_required_location") or "Remote"),
                    remote=True,
                    description=clean_html(item.get("description")),
                    posted_at=item.get("publication_date") or "",
                    salary=normalize_space(item.get("salary")),
                    employment_type=normalize_space(item.get("job_type")),
                    tags=[normalize_space(item.get("category"))],
                    raw_id=str(item.get("id", "")),
                )
            )
    return jobs


def fetch_forem(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("forem", {})
    endpoint = str(
        settings.get("endpoint")
        or "https://www.odwb.be/api/explore/v2.1/catalog/datasets/offres-d-emploi-forem/records"
    )
    max_queries = int(settings.get("max_queries", 14) or 14)
    results_per_query = int(settings.get("results_per_query", 60) or 60)
    jobs: list[Job] = []
    seen: set[str] = set()
    for term in query_terms(config, limit=max_queries, early_career_min=3):
        data = http.fetch_json(
            endpoint,
            {
                "limit": max(1, min(results_per_query, 100)),
                "where": _ods_search_query(term),
                "order_by": "datedebutdiffusion desc",
            },
        )
        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue
            if not _matches_query_signal(item, term):
                continue
            raw_id = normalize_space(item.get("numerooffreforem"))
            if raw_id and raw_id in seen:
                continue
            if raw_id:
                seen.add(raw_id)
            jobs.append(_forem_job(item))
    return jobs


def _forem_job(item: dict[str, Any]) -> Job:
    localities = _as_list(item.get("lieuxtravaillocalite"))
    regions = [region for region in _as_list(item.get("lieuxtravailregion")) if region.upper() != "BELGIQUE"]
    source = normalize_space(item.get("source"))
    description = text_blob(
        item.get("metier"),
        item.get("typecontrat"),
        item.get("regimetravail"),
        ", ".join(_as_list(item.get("secteurs"))),
        ", ".join(_as_list(item.get("niveauxetudes"))),
        ", ".join(_as_list(item.get("langues"))),
        item.get("experiencerequise"),
        f"Origine: {source}" if source else None,
    )
    return Job(
        source="Le Forem Open Data",
        source_type="official_api",
        title=normalize_space(item.get("titreoffre")),
        company=normalize_space(item.get("nomemployeur") or source),
        url=item.get("url", ""),
        apply_url=item.get("url", ""),
        location=normalize_space(", ".join(localities or regions)),
        country="Belgium",
        description=clean_html(description),
        posted_at=item.get("datedebutdiffusion") or "",
        employment_type=normalize_space(text_blob(item.get("typecontrat"), item.get("regimetravail"))),
        tags=[tag for tag in [source, *regions, *_as_list(item.get("secteurs"))] if tag],
        raw_id=normalize_space(item.get("numerooffreforem") or item.get("referenceexterne")),
    )


def fetch_actiris(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("actiris", {})
    endpoint = str(settings.get("endpoint") or "https://www.actiris.brussels/Umbraco/api/OffersApi/GetAllOffers")
    max_queries = int(settings.get("max_queries", 14) or 14)
    page_size = max(1, min(int(settings.get("page_size", 20) or 20), 50))
    max_pages = max(1, min(int(settings.get("max_pages", 2) or 2), 5))
    jobs: list[Job] = []
    seen: set[str] = set()
    for term in query_terms(config, limit=max_queries, early_career_min=3):
        for page in range(1, max_pages + 1):
            body = json.dumps(
                {
                    "offreFilter": {"texte": term},
                    "pageOption": {"page": page, "pageSize": page_size},
                }
            ).encode("utf-8")
            data = http.fetch_json(
                endpoint,
                method="POST",
                headers={"Accept": "application/json", "Content-Type": "application/json", "Accept-Language": "fr"},
                body=body,
            )
            rows = data.get("items", []) if isinstance(data, dict) else []
            if not rows:
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                if not _matches_query_signal(item, term):
                    continue
                raw_id = normalize_space(item.get("reference"))
                if raw_id and raw_id in seen:
                    continue
                if raw_id:
                    seen.add(raw_id)
                jobs.append(_actiris_job(item))
            if len(rows) < page_size:
                break
    return jobs


def _actiris_job(item: dict[str, Any]) -> Job:
    reference = normalize_space(item.get("reference"))
    employer = item.get("employeur") or {}
    company = employer.get("nomFr") or employer.get("nomNl") if isinstance(employer, dict) else ""
    title = clean_html(item.get("titreFr") or item.get("titreNl"))
    city = clean_html(item.get("communeFr") or item.get("communeNl"))
    postal = normalize_space(item.get("codePostal"))
    contract = clean_html(item.get("typeContratLibelle") or item.get("typeContrat"))
    url = f"https://www.actiris.brussels/fr/citoyens/detail-offre-d-emploi/?reference={reference}" if reference else ""
    description = text_blob(
        title,
        company,
        contract,
        item.get("dureeContratLibelle"),
        item.get("regimeTravail"),
        city,
        postal,
        item.get("codeDomaineImt"),
    )
    return Job(
        source="Actiris",
        source_type="official_api",
        title=title,
        company=clean_html(company),
        url=url,
        apply_url=url,
        location=normalize_space(", ".join(part for part in [city, postal] if part)),
        country="Belgium" if item.get("codePays") == "BE" else normalize_space(item.get("codePays")),
        description=clean_html(description),
        posted_at=item.get("dateCreation") or item.get("dateModification") or "",
        employment_type=contract,
        tags=[tag for tag in [item.get("typeContrat"), item.get("typeOffre"), item.get("codeDomaineImt")] if tag],
        raw_id=reference,
    )


def _ods_search_query(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [normalize_space(str(item)) for item in value if normalize_space(str(item))]
    return [normalize_space(str(value))]


_GENERIC_QUERY_WORDS = {
    "engineer",
    "ingenieur",
    "ingénieur",
    "h",
    "f",
    "x",
}


def _matches_query_signal(item: dict[str, Any], term: str) -> bool:
    words = [word for word in _word_tokens(term) if word not in _GENERIC_QUERY_WORDS]
    if not words:
        return True
    blob_words = set(_word_tokens(json.dumps(item, ensure_ascii=False)))
    return any(word in blob_words for word in words)


def _word_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9]+", normalized.lower())


def fetch_arbeitnow(config: dict[str, Any], http: HttpClient) -> list[Job]:
    data = http.fetch_json("https://www.arbeitnow.com/api/job-board-api", {"page": 1})
    terms = [term.lower() for term in query_terms(config)]
    jobs: list[Job] = []
    for item in data.get("data", []):
        blob = text_blob(item.get("title"), item.get("description"), " ".join(item.get("tags") or [])).lower()
        if terms and not contains_any(blob, terms):
            continue
        jobs.append(
            Job(
                source="Arbeitnow",
                source_type="public_api",
                title=normalize_space(item.get("title")),
                company=normalize_space(item.get("company_name")),
                url=item.get("url", ""),
                apply_url=item.get("url", ""),
                location=normalize_space(item.get("location") or "Remote"),
                remote=bool(item.get("remote")),
                description=clean_html(item.get("description")),
                posted_at=str(item.get("created_at") or ""),
                tags=[normalize_space(t) for t in item.get("tags") or []],
                raw_id=str(item.get("slug") or item.get("id") or ""),
            )
        )
    return jobs


def fetch_remoteok(config: dict[str, Any], http: HttpClient) -> list[Job]:
    data = http.fetch_json("https://remoteok.com/api")
    terms = [term.lower() for term in query_terms(config)]
    jobs: list[Job] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        blob = text_blob(item.get("position"), item.get("description"), " ".join(item.get("tags") or [])).lower()
        if terms and not contains_any(blob, terms):
            continue
        jobs.append(
            Job(
                source="RemoteOK",
                source_type="public_api",
                title=normalize_space(item.get("position")),
                company=normalize_space(item.get("company")),
                url=item.get("url") or item.get("apply_url") or "",
                apply_url=item.get("apply_url") or item.get("url") or "",
                location=normalize_space(item.get("location") or "Remote"),
                remote=True,
                description=clean_html(item.get("description")),
                posted_at=item.get("date") or "",
                salary=_salary_range(item),
                tags=[normalize_space(str(t)) for t in item.get("tags") or []],
                raw_id=str(item.get("id") or ""),
            )
        )
    return jobs


def fetch_jobicy(config: dict[str, Any], http: HttpClient) -> list[Job]:
    jobs: list[Job] = []
    for term in query_terms(config, limit=20, early_career_min=5):
        tag = term.lower().replace(" ", "-").replace("/", "-")
        try:
            data = http.fetch_json("https://jobicy.com/api/v2/remote-jobs", {"count": 50, "tag": tag})
        except HttpError as exc:
            if "HTTP 429" in str(exc):
                continue
            raise
        for item in data.get("jobs", []):
            jobs.append(
                Job(
                    source="Jobicy",
                    source_type="public_api",
                    title=normalize_space(item.get("jobTitle")),
                    company=normalize_space(item.get("companyName")),
                    url=item.get("url", ""),
                    apply_url=item.get("url", ""),
                    location=normalize_space(item.get("jobGeo") or "Remote"),
                    remote=True,
                    description=clean_html(item.get("jobDescription")),
                    posted_at=item.get("pubDate") or "",
                    employment_type=normalize_space(item.get("jobType")),
                    salary=normalize_space(item.get("annualSalaryMin") or ""),
                    tags=[normalize_space(t) for t in item.get("jobIndustry") or []],
                    raw_id=str(item.get("id") or ""),
                )
            )
    return jobs


def fetch_himalayas(config: dict[str, Any], http: HttpClient) -> list[Job]:
    data = http.fetch_json("https://himalayas.app/jobs/api", {"limit": 100})
    terms = [term.lower() for term in query_terms(config)]
    rows = data.get("jobs") if isinstance(data, dict) else []
    jobs: list[Job] = []
    for item in rows or []:
        blob = text_blob(item.get("title"), item.get("description"), " ".join(item.get("tags") or [])).lower()
        if terms and not contains_any(blob, terms):
            continue
        company = item.get("company") or {}
        jobs.append(
            Job(
                source="Himalayas",
                source_type="public_api",
                title=normalize_space(item.get("title")),
                company=normalize_space(company.get("name") if isinstance(company, dict) else ""),
                url=item.get("applicationLink") or item.get("url") or "",
                apply_url=item.get("applicationLink") or item.get("url") or "",
                location=normalize_space(item.get("location") or "Remote"),
                remote=True,
                description=clean_html(item.get("description")),
                posted_at=item.get("pubDate") or item.get("createdAt") or "",
                salary=normalize_space(item.get("salary") or ""),
                tags=[normalize_space(str(t)) for t in item.get("tags") or []],
                raw_id=str(item.get("id") or ""),
            )
        )
    return jobs


def _salary_range(item: dict[str, Any]) -> str:
    minimum = item.get("salary_min")
    maximum = item.get("salary_max")
    if minimum and maximum:
        return f"{minimum}-{maximum}"
    if minimum:
        return f"{minimum}+"
    return ""
