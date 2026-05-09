from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

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
    if item.get("missionStartDate"):
        tags.append(f"mission start {normalize_space(item.get('missionStartDate'))}")
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
        deadline=item.get("endBroadcastDate") or item.get("dateCandidature") or "",
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


def fetch_euraxess(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("euraxess", {})
    endpoint = str(settings.get("endpoint") or "https://euraxess.ec.europa.eu/jobs/search")
    max_pages = max(1, min(int(settings.get("max_pages", 10) or 10), 25))
    max_results = max(1, min(int(settings.get("max_results", 120) or 120), 300))
    jobs: list[Job] = []
    seen: set[str] = set()
    for page in range(max_pages):
        url = endpoint if page == 0 else f"{endpoint}?page={page}"
        html = http.fetch_text(url)
        for item in _euraxess_articles(html):
            if not _euraxess_match(item):
                continue
            raw_id = normalize_space(item.get("raw_id") or item.get("url"))
            if raw_id and raw_id in seen:
                continue
            if raw_id:
                seen.add(raw_id)
            jobs.append(
                Job(
                    source="EURAXESS",
                    source_type="official_portal",
                    title=normalize_space(item.get("title")),
                    company=normalize_space(item.get("company")),
                    url=normalize_space(item.get("url")),
                    apply_url=normalize_space(item.get("url")),
                    location=normalize_space(item.get("location")),
                    description=clean_html(item.get("description")),
                    posted_at=normalize_space(item.get("posted_at")),
                    deadline=normalize_space(item.get("deadline")),
                    employment_type=normalize_space(item.get("research_profile")),
                    tags=[tag for tag in ["EURAXESS", normalize_space(item.get("research_field"))] if tag],
                    raw_id=raw_id,
                )
            )
            if len(jobs) >= max_results:
                return jobs
    return jobs


def _euraxess_match(item: dict[str, Any]) -> bool:
    blob = _word_blob(item)
    technical_terms = {
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "reinforcement learning",
        "data science",
        "data scientist",
        "data engineering",
        "synthetic data",
        "computer science",
        "computer vision",
        "natural language processing",
        "nlp",
        "software",
        "informatics",
        "algorithm",
        "optimization",
        "optimisation",
        "digital twin",
        "interpretability",
        "explainability",
        "ai safety",
        "knowledge graph",
        "semantic web",
        "robotics",
        "ai",
        "ml",
    }
    if any(_term_matches_blob(blob, term) for term in technical_terms):
        return True
    doctoral_terms = {
        "msca",
        "marie sklodowska curie",
        "doctoral network",
        "industrial doctorate",
        "doctoral candidate",
        "doctoral researcher",
    }
    doctoral_tech_terms = {
        "trustworthy ai",
        "ai safety",
        "large language model",
        "llm",
        "genai",
        "interpretability",
        "explainability",
        "knowledge graph",
        "semantic web",
        "machine learning",
        "data driven",
        "digital",
    }
    has_doctoral_marker = any(_term_matches_blob(blob, term) for term in doctoral_terms)
    return has_doctoral_marker and any(_term_matches_blob(blob, term) for term in doctoral_tech_terms)


def fetch_doctorat_gouv(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("doctorat_gouv", {})
    endpoint = str(settings.get("endpoint") or "https://app.doctorat.gouv.fr/api/propositions-these")
    queries = [str(term).strip() for term in settings.get("queries", []) if str(term).strip()]
    if not queries:
        queries = [term for term in query_terms(config, limit=12, early_career_min=6) if _is_doctoral_query(term)]
    if not queries:
        queries = ["CIFRE", "LLM", "machine learning", "data science", "NLP", "intelligence artificielle"]
    max_queries = max(1, min(int(settings.get("max_queries", len(queries)) or len(queries)), 20))
    page_size = max(1, min(int(settings.get("page_size", 20) or 20), 50))
    max_pages = max(1, min(int(settings.get("max_pages", 2) or 2), 10))
    max_results = max(1, min(int(settings.get("max_results", 160) or 160), 500))
    include_assigned = bool(settings.get("include_assigned", False))

    jobs: list[Job] = []
    seen: set[str] = set()
    for term in queries[:max_queries]:
        for page in range(max_pages):
            data = http.fetch_json(
                endpoint,
                {
                    "page": page,
                    "size": page_size,
                    "query": term,
                    "sortField": "dateMiseEnLigne",
                    "sortDirection": "DESC",
                },
                headers={"Accept": "application/json"},
            )
            rows = data.get("content", []) if isinstance(data, dict) else []
            if not rows:
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                raw_id = normalize_space(str(item.get("id") or item.get("matricule") or item.get("urlCandidature") or ""))
                if raw_id and raw_id in seen:
                    continue
                if not include_assigned and normalize_space(str(item.get("sujetAttribue") or "")).casefold() == "oui":
                    continue
                if not _doctorat_gouv_match(item):
                    continue
                if raw_id:
                    seen.add(raw_id)
                jobs.append(_doctorat_gouv_job(item))
                if len(jobs) >= max_results:
                    return jobs
            if len(rows) < page_size:
                break
    return jobs


def _doctorat_gouv_job(item: dict[str, Any]) -> Job:
    raw_id = normalize_space(str(item.get("id") or item.get("matricule") or ""))
    funding_types = _as_list(item.get("financementTypes"))
    employer = normalize_space(item.get("financementEmployeur"))
    institution = normalize_space(item.get("etablissementLibelle") or item.get("uniteRechercheLibelle"))
    company = employer or institution or "Plateforme Nationale du Doctorat"
    title = normalize_space(item.get("theseTitre") or item.get("theseTitreAnglais") or item.get("specialite"))
    city = normalize_space(item.get("etablissementVille") or item.get("uniteRechercheVille"))
    url = normalize_space(item.get("urlCandidature") or item.get("urlInfosComplementaires"))
    if not url and raw_id:
        url = f"https://app.doctorat.gouv.fr/proposition?id={quote(raw_id, safe='')}"
    financing = normalize_space(
        text_blob(
            ", ".join(funding_types),
            item.get("financementOrigine"),
            f"Employeur: {employer}" if employer else "",
            item.get("financementEtat"),
        )
    )
    description = clean_html(
        text_blob(
            item.get("domaine"),
            item.get("specialite"),
            item.get("thematiqueRecherche"),
            item.get("resume"),
            item.get("objectif"),
            item.get("contexte"),
            item.get("methodeDeTravail"),
            item.get("profilRecherche"),
            item.get("conditionsMaterielles"),
            financing,
        )
    )
    language_bits = [
        f"anglais {item.get('niveauAnglaisRequis')}" if item.get("niveauAnglaisRequis") else "",
        f"francais {item.get('niveauFrancaisRequis')}" if item.get("niveauFrancaisRequis") else "",
    ]
    tags = [
        "doctorat.gouv.fr",
        "doctorat",
        *funding_types,
        normalize_space(item.get("domaine")),
        normalize_space(item.get("specialite")),
        normalize_space(item.get("source")),
        normalize_space(item.get("financementOrigine")),
        normalize_space(item.get("dateDebutThese") and f"debut these {item.get('dateDebutThese')}"),
        *[bit for bit in language_bits if bit],
    ]
    employment_type = normalize_space(text_blob("Doctorat", ", ".join(funding_types), item.get("financementEtat")))
    return Job(
        source="Doctorat.gouv.fr",
        source_type="official_api",
        title=title,
        company=company,
        url=url,
        apply_url=url,
        location=city,
        country="France",
        description=description,
        posted_at=normalize_space(item.get("dateMiseEnLigne") or item.get("dateCreation") or item.get("dateMaj")),
        deadline=normalize_space(item.get("dateLimiteCandidature")),
        employment_type=employment_type,
        tags=[tag for tag in tags if tag],
        raw_id=raw_id,
    )


def _doctorat_gouv_match(item: dict[str, Any]) -> bool:
    blob = _word_blob(
        {
            "title": normalize_space(item.get("theseTitre") or item.get("theseTitreAnglais")),
            "company": normalize_space(item.get("financementEmployeur") or item.get("etablissementLibelle")),
            "description": text_blob(
                item.get("domaine"),
                item.get("specialite"),
                item.get("thematiqueRecherche"),
                item.get("resume"),
                item.get("objectif"),
                item.get("contexte"),
                item.get("profilRecherche"),
                item.get("financementOrigine"),
                " ".join(_as_list(item.get("financementTypes"))),
            ),
        }
    )
    strong_terms = {
        "artificial intelligence",
        "intelligence artificielle",
        "machine learning",
        "apprentissage automatique",
        "deep learning",
        "reinforcement learning",
        "data science",
        "data scientist",
        "big data",
        "data engineering",
        "llm",
        "large language model",
        "nlp",
        "natural language processing",
        "traitement automatique",
        "multi agent",
        "multi agents",
        "systemes multi agents",
        "jumeau numerique",
        "digital twin",
        "software",
        "software engineering",
        "cloud native",
        "interpretability",
        "interprétabilité",
        "interpretabilite",
        "explainability",
        "explicabilite",
        "explicabilité",
        "ai safety",
        "knowledge graph",
        "graphe de connaissances",
        "semantic web",
        "web semantique",
        "web sémantique",
        "optimization",
        "optimisation",
        "computer science",
        "informatique",
        "statistique",
        "statistics",
        "neural",
        "ia",
        "ai",
    }
    return any(_term_matches_blob(blob, term) for term in strong_terms)


def _is_doctoral_query(term: str) -> bool:
    lowered = _strip_accents(term).lower()
    return any(token in lowered for token in ["cifre", "phd", "doctor", "these", "thesis"])


def fetch_academictransfer(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("academictransfer", {})
    token_page = str(settings.get("token_page") or "https://www.academictransfer.com/en/jobs/?q=phd")
    endpoint = str(settings.get("endpoint") or "https://api.academictransfer.com/vacancies/")
    queries = [str(term).strip() for term in settings.get("queries", []) if str(term).strip()]
    if not queries:
        queries = ["phd machine learning", "phd data science", "phd artificial intelligence", "phd software"]
    max_queries = max(1, min(int(settings.get("max_queries", len(queries)) or len(queries)), 12))
    page_size = max(1, min(int(settings.get("page_size", 10) or 10), 50))
    max_pages = max(1, min(int(settings.get("max_pages", 2) or 2), 10))
    max_results = max(1, min(int(settings.get("max_results", 80) or 80), 300))
    token = _academictransfer_public_token(http.fetch_text(token_page, headers={"Accept": "text/html,*/*"}))
    if not token:
        raise HttpError("AcademicTransfer public access token introuvable")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json; version=2"}

    jobs: list[Job] = []
    seen: set[str] = set()
    for term in queries[:max_queries]:
        for page in range(max_pages):
            data = http.fetch_json(
                endpoint,
                {"limit": page_size, "offset": page * page_size, "search": term},
                headers=headers,
            )
            rows = data.get("results", []) if isinstance(data, dict) else []
            if not rows:
                break
            for item in rows:
                if not isinstance(item, dict) or not item.get("is_active", True):
                    continue
                raw_id = normalize_space(str(item.get("external_id") or item.get("id") or item.get("absolute_url") or ""))
                if raw_id and raw_id in seen:
                    continue
                if not _academictransfer_match(item):
                    continue
                if raw_id:
                    seen.add(raw_id)
                jobs.append(_academictransfer_job(item))
                if len(jobs) >= max_results:
                    return jobs
            if not data.get("next"):
                break
    return jobs


def _academictransfer_public_token(html: str) -> str:
    token_ref = re.search(r'\$satDataApiPublicAccessToken":(\d+)', html)
    script_match = re.search(r'<script[^>]+id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, flags=re.S)
    if not token_ref or not script_match:
        return ""
    try:
        data = json.loads(script_match.group(1))
        token = data[int(token_ref.group(1))]
    except (TypeError, ValueError, IndexError, json.JSONDecodeError):
        return ""
    return token if isinstance(token, str) else ""


def _academictransfer_job(item: dict[str, Any]) -> Job:
    title = normalize_space(item.get("title"))
    company = normalize_space(item.get("organisation_name") or "AcademicTransfer")
    city = normalize_space(item.get("city"))
    country_code = normalize_space(str(item.get("country_code") or ""))
    country = "Netherlands" if country_code.upper() == "NL" else country_code
    url = normalize_space(item.get("absolute_url"))
    min_salary = item.get("min_salary")
    max_salary = item.get("max_salary")
    salary = _academictransfer_salary(min_salary, max_salary)
    department = _flat_text(item.get("department_name"))
    education_level = _flat_text(item.get("education_level"))
    contract_type = _flat_text(item.get("contract_type"))
    available_positions = _flat_text(item.get("available_positions"))
    description = clean_html(
        text_blob(
            _flat_text(item.get("excerpt")),
            _flat_text(item.get("description")),
            _flat_text(item.get("requirements")),
            _flat_text(item.get("contract_terms")),
            _flat_text(item.get("organisation_description")),
            _flat_text(item.get("department_description")),
        )
    )
    research_fields = _flatten_strings(item.get("research_fields"))
    tags = [
        "AcademicTransfer",
        "PhD",
        department,
        education_level,
        contract_type,
        *research_fields,
    ]
    employment_type = normalize_space(text_blob("PhD", education_level, contract_type, available_positions))
    return Job(
        source="AcademicTransfer",
        source_type="public_api",
        title=title,
        company=company,
        url=url,
        apply_url=url,
        location=normalize_space(", ".join(part for part in [city, country] if part)),
        country=country,
        description=description,
        posted_at=normalize_space(item.get("created_datetime")),
        deadline=normalize_space(item.get("end_date")),
        salary=salary,
        employment_type=employment_type,
        tags=[tag for tag in tags if tag],
        raw_id=normalize_space(str(item.get("external_id") or item.get("id") or "")),
    )


def _academictransfer_salary(min_salary: Any, max_salary: Any) -> str:
    min_value = _salary_value_text(min_salary)
    max_value = _salary_value_text(max_salary)
    if min_value and max_value:
        return f"EUR {min_value} - {max_value} monthly"
    if min_value or max_value:
        return f"EUR {min_value or max_value} monthly"
    return ""


def _salary_value_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return normalize_space(str(value))
    return f"{numeric:.0f}"


def _academictransfer_match(item: dict[str, Any]) -> bool:
    title = normalize_space(item.get("title"))
    title_blob = _strip_accents(title).lower()
    if not re.search(r"\b(ph\.?d|doctoral|doctorate)\b", title_blob):
        return False
    if re.search(r"\b(postdoc|post-doc|professor|lecturer|project leader|manager)\b", title_blob):
        return False
    blob = _word_blob(
        {
            "title": title,
            "company": normalize_space(item.get("organisation_name")),
            "description": text_blob(
                _flat_text(item.get("excerpt")),
                _flat_text(item.get("description")),
                _flat_text(item.get("requirements")),
                _flat_text(item.get("research_fields")),
                _flat_text(item.get("department_name")),
            ),
        }
    )
    strong_terms = {
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "data science",
        "data scientist",
        "data engineering",
        "software",
        "computer science",
        "nlp",
        "natural language processing",
        "computer vision",
        "interpretability",
        "explainability",
        "ai safety",
        "knowledge graph",
        "semantic web",
        "optimization",
        "optimisation",
        "causal",
        "llm",
        "ai",
        "ml",
    }
    return any(_term_matches_blob(blob, term) for term in strong_terms)


def _flat_text(value: Any) -> str:
    return normalize_space(" ".join(_flatten_strings(value)))


def fetch_weworkremotely(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("weworkremotely", {})
    feeds = settings.get(
        "feeds",
        [
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        ],
    )
    return _rss_jobs(
        config,
        http,
        feeds=[str(feed) for feed in feeds if str(feed).strip()],
        source="We Work Remotely",
        country="Remote",
        remote=True,
        max_items=int(settings.get("max_items", 120) or 120),
    )


def fetch_swissdevjobs(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("swissdevjobs", {})
    return _rss_jobs(
        config,
        http,
        feeds=[str(settings.get("feed") or "https://swissdevjobs.ch/rss")],
        source="SwissDevJobs",
        country="Switzerland",
        remote=False,
        max_items=int(settings.get("max_items", 260) or 260),
    )


def fetch_germantechjobs(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("germantechjobs", {})
    return _rss_jobs(
        config,
        http,
        feeds=[str(settings.get("feed") or "https://germantechjobs.de/rss")],
        source="GermanTechJobs",
        country="Germany",
        remote=False,
        max_items=int(settings.get("max_items", 400) or 400),
    )


def _rss_jobs(
    config: dict[str, Any],
    http: HttpClient,
    *,
    feeds: list[str],
    source: str,
    country: str,
    remote: bool,
    max_items: int,
) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    per_feed = max(1, min(max_items, 1000))
    for feed in feeds:
        if not feed:
            continue
        root = ET.fromstring(http.fetch_text(feed))
        for item in root.findall(".//item")[:per_feed]:
            raw_title = normalize_space(item.findtext("title"))
            link = normalize_space(item.findtext("link"))
            description = item.findtext("description") or ""
            if not raw_title or not link:
                continue
            parsed = _parse_rss_title(raw_title, source)
            blob_item = {"title": parsed["title"], "description": description, "source": source}
            if not _rss_like_match(blob_item, config):
                continue
            raw_id = link.split("?", 1)[0].rstrip("/")
            if raw_id in seen:
                continue
            seen.add(raw_id)
            clean_description = clean_html(description)
            salary = parsed["salary"] or _rss_salary(clean_description)
            location = _wwr_headquarters(description) if source == "We Work Remotely" else country
            jobs.append(
                Job(
                    source=source,
                    source_type="public_api",
                    title=parsed["title"],
                    company=parsed["company"],
                    url=link,
                    apply_url=link,
                    location=location or country,
                    country=country if country != "Remote" else "",
                    remote=remote or "remote" in text_blob(raw_title, clean_description, location).lower(),
                    description=clean_description,
                    posted_at=normalize_space(item.findtext("pubDate")),
                    salary=salary,
                    tags=[source],
                    raw_id=raw_id,
                )
            )
    return jobs


def _parse_rss_title(raw_title: str, source: str) -> dict[str, str]:
    title = normalize_space(raw_title)
    salary = ""
    bracket = re.search(r"\[([^\]]*(?:€|eur|chf|gbp|£|usd|\$|sek|nok|dkk)[^\]]*)\]", title, re.IGNORECASE)
    if bracket:
        salary = normalize_space(bracket.group(1))
        title = normalize_space(title.replace(bracket.group(0), ""))
    company = source
    if source == "We Work Remotely" and ":" in title:
        company, title = [normalize_space(part) for part in title.split(":", 1)]
    elif " @ " in title:
        title, company = [normalize_space(part) for part in title.rsplit(" @ ", 1)]
    return {"title": title, "company": company, "salary": salary}


def _rss_salary(description: str) -> str:
    match = re.search(r"\bSalary:\s*([^.;\n]+(?:per year|annuel|year)?)", description, flags=re.IGNORECASE)
    return normalize_space(match.group(1)) if match else ""


def _wwr_headquarters(description: str) -> str:
    match = re.search(r"Headquarters:\s*</strong>\s*([^<]+)", description, flags=re.IGNORECASE)
    if match:
        return clean_html(match.group(1))
    match = re.search(r"\bHeadquarters:\s*([^.\n<]+)", description, flags=re.IGNORECASE)
    return clean_html(match.group(1)) if match else "Remote"


def _rss_like_match(item: dict[str, Any], config: dict[str, Any]) -> bool:
    for term in query_terms(config, limit=24, early_career_min=5):
        if _matches_query_signal(item, term):
            return True
    blob = _word_blob(item)
    strong_terms = {
        "ai",
        "llm",
        "rag",
        "mlops",
        "machine learning",
        "data science",
        "data engineer",
        "data scientist",
        "analytics engineer",
        "research engineer",
        "ai research engineer",
        "applied scientist",
        "interpretability",
        "explainability",
        "ai safety",
        "knowledge graph",
        "semantic web",
        "ml engineer",
        "python",
        "kubernetes",
        "databricks",
        "snowflake",
    }
    return any(_term_matches_blob(blob, term) for term in strong_terms)


def _term_matches_blob(blob: str, term: str) -> bool:
    if " " in term:
        return term in blob
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", blob) is not None


def _word_blob(item: dict[str, Any]) -> str:
    return _strip_accents(
        text_blob(
            str(item.get("title") or ""),
            str(item.get("company") or ""),
            str(item.get("description") or ""),
            " ".join(str(tag) for tag in item.get("tags", []) if tag) if isinstance(item.get("tags"), list) else "",
        )
    ).lower()


def _euraxess_articles(html: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for article in re.findall(r'<article class="ecl-content-item">(.*?)</article>', html, flags=re.S):
        title_match = re.search(r'<h3 class="ecl-content-block__title">.*?<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', article, flags=re.S)
        if not title_match:
            continue
        href = normalize_space(title_match.group(1))
        title = clean_html(title_match.group(2))
        cleaned = clean_html(article)
        company = cleaned.split(" Posted on:", 1)[0] if " Posted on:" in cleaned else "EURAXESS"
        rows.append(
            {
                "title": title,
                "company": normalize_space(company),
                "url": href if href.startswith("http") else f"https://euraxess.ec.europa.eu{href}",
                "description": _between(cleaned, title, "Work Locations:") or cleaned,
                "location": _between(cleaned, "Work Locations:", "Research Field:"),
                "research_field": _between(cleaned, "Research Field:", "Researcher Profile:"),
                "research_profile": _between(cleaned, "Researcher Profile:", "Funding Programme:"),
                "posted_at": _between(cleaned, "Posted on:", title),
                "deadline": _after(cleaned, "Application Deadline:"),
                "raw_id": href.rsplit("/", 1)[-1],
            }
        )
    return rows


def _between(value: str, start: str, end: str) -> str:
    if start not in value:
        return ""
    tail = value.split(start, 1)[1]
    if end in tail:
        tail = tail.split(end, 1)[0]
    return normalize_space(tail)


def _after(value: str, start: str) -> str:
    if start not in value:
        return ""
    return normalize_space(value.split(start, 1)[1])


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


def fetch_bundesagentur(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("bundesagentur", {})
    endpoint = str(
        settings.get("endpoint") or "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
    )
    api_key = str(settings.get("api_key") or "jobboerse-jobsuche")
    page_size = max(1, min(int(settings.get("page_size", 20) or 20), 50))
    max_pages = max(1, min(int(settings.get("max_pages", 1) or 1), 5))
    max_queries = int(settings.get("max_queries", 8) or 8)
    configured_terms = [str(term).strip() for term in settings.get("queries", []) if str(term).strip()]
    terms = configured_terms or query_terms(config, limit=max_queries, early_career_min=2)
    allowed_countries = {
        normalize_space(str(country)).casefold()
        for country in settings.get("countries", ["Deutschland"])
        if normalize_space(str(country))
    }

    jobs: list[Job] = []
    seen: set[str] = set()
    headers = {"Accept": "application/json", "X-API-Key": api_key}
    for term in terms[:max_queries]:
        for page in range(1, max_pages + 1):
            data = http.fetch_json(
                endpoint,
                {"was": term, "size": page_size, "page": page, "angebotsart": 1},
                headers=headers,
            )
            rows = data.get("stellenangebote", []) if isinstance(data, dict) else []
            if not rows:
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                country = _bundesagentur_country(item)
                if allowed_countries and country and country.casefold() not in allowed_countries:
                    continue
                raw_id = normalize_space(item.get("refnr"))
                if raw_id and raw_id in seen:
                    continue
                if raw_id:
                    seen.add(raw_id)
                jobs.append(_bundesagentur_job(item))
            if len(rows) < page_size:
                break
    return jobs


def _bundesagentur_job(item: dict[str, Any]) -> Job:
    raw_id = normalize_space(item.get("refnr"))
    workplace = item.get("arbeitsort") or {}
    city = normalize_space(workplace.get("ort") if isinstance(workplace, dict) else "")
    region = normalize_space(workplace.get("region") if isinstance(workplace, dict) else "")
    country = _bundesagentur_country(item) or "Deutschland"
    country_label = _bundesagentur_country_label(country)
    external_url = normalize_space(item.get("externeUrl"))
    url = external_url or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{quote(raw_id, safe='')}"
    description = text_blob(
        item.get("beruf"),
        item.get("titel"),
        item.get("arbeitgeber"),
        item.get("eintrittsdatum"),
        city,
        region,
        country,
    )
    return Job(
        source="Bundesagentur Jobsuche",
        source_type="official_api",
        title=normalize_space(item.get("titel")),
        company=normalize_space(item.get("arbeitgeber")),
        url=url,
        apply_url=url,
        location=normalize_space(", ".join(part for part in [city, region, country] if part)),
        country=country_label,
        description=description,
        posted_at=item.get("aktuelleVeroeffentlichungsdatum") or item.get("modifikationsTimestamp") or "",
        employment_type=normalize_space(text_blob(item.get("beruf"), "CDI/contrat a verifier")),
        tags=[tag for tag in [normalize_space(item.get("beruf")), "Bundesagentur", country, region] if tag],
        raw_id=raw_id,
    )


def _bundesagentur_country(item: dict[str, Any]) -> str:
    workplace = item.get("arbeitsort") or {}
    return normalize_space(workplace.get("land") if isinstance(workplace, dict) else "")


def _bundesagentur_country_label(country: str) -> str:
    normalized = country.casefold()
    if normalized == "deutschland":
        return "Germany"
    if normalized in {"österreich", "oesterreich"}:
        return "Austria"
    if normalized == "schweiz":
        return "Switzerland"
    return country


def fetch_jobtechdev_sweden(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("jobtechdev_sweden", {})
    endpoint = str(settings.get("endpoint") or "https://jobsearch.api.jobtechdev.se/search")
    page_size = max(1, min(int(settings.get("page_size", 20) or 20), 100))
    max_pages = max(1, min(int(settings.get("max_pages", 1) or 1), 5))
    max_queries = int(settings.get("max_queries", 8) or 8)
    configured_terms = [str(term).strip() for term in settings.get("queries", []) if str(term).strip()]
    terms = configured_terms or query_terms(config, limit=max_queries, early_career_min=2)

    jobs: list[Job] = []
    seen: set[str] = set()
    for term in terms[:max_queries]:
        for page in range(max_pages):
            data = http.fetch_json(endpoint, {"q": term, "limit": page_size, "offset": page * page_size})
            rows = data.get("hits", []) if isinstance(data, dict) else []
            if not rows:
                break
            for item in rows:
                if not isinstance(item, dict) or item.get("removed"):
                    continue
                raw_id = normalize_space(item.get("id"))
                if raw_id and raw_id in seen:
                    continue
                if raw_id:
                    seen.add(raw_id)
                jobs.append(_jobtechdev_sweden_job(item))
            if len(rows) < page_size:
                break
    return jobs


def _jobtechdev_sweden_job(item: dict[str, Any]) -> Job:
    raw_id = normalize_space(item.get("id"))
    application = item.get("application_details") or {}
    employer = item.get("employer") or {}
    address = item.get("workplace_address") or {}
    description = item.get("description") or {}
    url = normalize_space(item.get("webpage_url")) or f"https://arbetsformedlingen.se/platsbanken/annonser/{quote(raw_id, safe='')}"
    apply_url = normalize_space(application.get("url") if isinstance(application, dict) else "") or url
    location = _jobtechdev_location(address if isinstance(address, dict) else {})
    job = Job(
        source="JobTechDev Sweden",
        source_type="official_api",
        title=normalize_space(item.get("headline")),
        company=normalize_space(employer.get("name") if isinstance(employer, dict) else ""),
        url=url,
        apply_url=apply_url,
        location=location,
        country="Sweden",
        description=clean_html(description.get("text_formatted") or description.get("text") if isinstance(description, dict) else ""),
        posted_at=item.get("publication_date") or "",
        deadline=item.get("application_deadline") or item.get("last_publication_date") or "",
        salary=normalize_space(item.get("salary_description")),
        employment_type=normalize_space(
            text_blob(
                _label_from_dict(item.get("employment_type")),
                _label_from_dict(item.get("duration")),
                _label_from_dict(item.get("working_hours_type")),
            )
        ),
        tags=[
            tag
            for tag in [
                _label_from_dict(item.get("occupation")),
                _label_from_dict(item.get("occupation_group")),
                _label_from_dict(item.get("occupation_field")),
                normalize_space(item.get("source_type")),
            ]
            if tag
        ],
        raw_id=raw_id,
    )
    job.remote = "remote" in text_blob(job.title, job.description, job.location).lower()
    return job


def _jobtechdev_location(address: dict[str, Any]) -> str:
    return normalize_space(
        ", ".join(
            part
            for part in [
                normalize_space(address.get("city") or address.get("municipality")),
                normalize_space(address.get("region")),
                normalize_space(address.get("country") or "Sverige"),
            ]
            if part
        )
    )


def fetch_nav_norway(config: dict[str, Any], http: HttpClient) -> list[Job]:
    settings = config.get("nav_norway", {})
    endpoint = str(settings.get("endpoint") or "https://arbeidsplassen.nav.no/stillinger/api/search")
    page_size = max(1, min(int(settings.get("page_size", 25) or 25), 50))
    max_pages = max(1, min(int(settings.get("max_pages", 1) or 1), 5))
    max_queries = int(settings.get("max_queries", 8) or 8)
    configured_terms = [str(term).strip() for term in settings.get("queries", []) if str(term).strip()]
    terms = configured_terms or query_terms(config, limit=max_queries, early_career_min=2)

    jobs: list[Job] = []
    seen: set[str] = set()
    for term in terms[:max_queries]:
        for page in range(max_pages):
            data = http.fetch_json(endpoint, {"q": term, "size": page_size, "from": page * page_size})
            hits = data.get("hits", {}).get("hits", []) if isinstance(data, dict) else []
            if not hits:
                break
            for hit in hits[:page_size]:
                item = hit.get("_source") if isinstance(hit, dict) else None
                if not isinstance(item, dict) or str(item.get("status") or "").upper() not in {"", "ACTIVE"}:
                    continue
                raw_id = normalize_space(item.get("uuid"))
                if raw_id and raw_id in seen:
                    continue
                if raw_id:
                    seen.add(raw_id)
                jobs.append(_nav_norway_job(item))
            if len(hits) < page_size:
                break
    return jobs


def _nav_norway_job(item: dict[str, Any]) -> Job:
    raw_id = normalize_space(item.get("uuid"))
    properties = item.get("properties") or {}
    employer = item.get("employer") or {}
    location_rows = item.get("locationList") or []
    location = _nav_norway_location(location_rows)
    country = _nav_country_label(_nav_country(location_rows)) or "Norway"
    tags = _nav_tags(item)
    description = text_blob(
        item.get("generatedSearchMetadata", {}).get("shortSummary")
        if isinstance(item.get("generatedSearchMetadata"), dict)
        else "",
        " ".join(_flatten_strings(properties.get("keywords") if isinstance(properties, dict) else "")),
        " ".join(tags),
    )
    url = f"https://arbeidsplassen.nav.no/stillinger/stilling/{quote(raw_id, safe='')}"
    job = Job(
        source="NAV Arbeidsplassen",
        source_type="official_api",
        title=normalize_space(item.get("title")),
        company=normalize_space(item.get("businessName") or employer.get("name") if isinstance(employer, dict) else item.get("businessName")),
        url=url,
        apply_url=url,
        location=location,
        country=country,
        description=clean_html(description),
        posted_at=item.get("published") or "",
        deadline=item.get("expires") or "",
        employment_type=normalize_space(
            text_blob(
                " ".join(_flatten_strings(properties.get("education") if isinstance(properties, dict) else "")),
                " ".join(_flatten_strings(properties.get("experience") if isinstance(properties, dict) else "")),
                item.get("medium"),
            )
        ),
        tags=tags,
        raw_id=raw_id,
    )
    job.remote = any(term in text_blob(job.title, job.description, job.location).lower() for term in ("remote", "hjemmekontor"))
    return job


def _nav_norway_location(rows: list[Any]) -> str:
    parts: list[str] = []
    for item in rows[:3]:
        if not isinstance(item, dict):
            continue
        label = normalize_space(
            ", ".join(
                part
                for part in [
                    normalize_space(item.get("city")),
                    normalize_space(item.get("county")),
                    normalize_space(item.get("country") or "NORGE"),
                ]
                if part
            )
        )
        if label:
            parts.append(label)
    return normalize_space("; ".join(parts))


def _nav_country(rows: list[Any]) -> str:
    for item in rows:
        if isinstance(item, dict) and normalize_space(item.get("country")):
            return normalize_space(item.get("country"))
    return ""


def _nav_country_label(country: str) -> str:
    normalized = country.casefold()
    if normalized == "norge":
        return "Norway"
    if normalized == "danmark":
        return "Denmark"
    if normalized == "sveits":
        return "Switzerland"
    if normalized == "tyskland":
        return "Germany"
    if normalized in {"østerrike", "osterrike", "oesterrike"}:
        return "Austria"
    if normalized == "spania":
        return "Spain"
    if normalized in {"sverige", "sweden"}:
        return "Sweden"
    if normalized in {"finland", "suomi"}:
        return "Finland"
    return country


def _nav_tags(item: dict[str, Any]) -> list[str]:
    properties = item.get("properties") or {}
    tags: list[str] = []
    if isinstance(properties, dict):
        tags.extend(_flatten_strings(properties.get("searchtagsai")))
        tags.extend(_flatten_strings(properties.get("workLanguage")))
    for row in item.get("categoryList") or []:
        if isinstance(row, dict):
            tags.append(normalize_space(row.get("name")))
    for row in item.get("occupationList") or []:
        if isinstance(row, dict):
            tags.extend([normalize_space(row.get("level1")), normalize_space(row.get("level2"))])
    return [tag for tag in tags if tag]


def _label_from_dict(value: Any) -> str:
    if isinstance(value, dict):
        return normalize_space(value.get("label") or value.get("name"))
    return normalize_space(str(value or ""))


def _flatten_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [normalize_space(value)] if normalize_space(value) else []
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            if isinstance(item, dict):
                output.extend(_flatten_strings(item.get("label") or item.get("name")))
            else:
                output.extend(_flatten_strings(item))
        return output
    return [normalize_space(str(value))] if normalize_space(str(value)) else []


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


def _strip_accents(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


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
