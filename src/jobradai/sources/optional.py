from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from jobradai.http import HttpClient, HttpError
from jobradai.models import Job
from jobradai.queries import select_query_items, select_query_terms
from jobradai.text import clean_html, normalize_space, text_blob

JOBSPY_PACKAGE = os.getenv("JOBRADAR_JOBSPY_PACKAGE", "python-jobspy==1.1.82")
JOBSPY_DEFAULT_TIMEOUT_SECONDS = 240


def fetch_adzuna(config: dict[str, Any], http: HttpClient) -> tuple[list[Job], str]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return [], "missing_config: ADZUNA_APP_ID/ADZUNA_APP_KEY absents"
    settings = dict(config.get("adzuna", {}))
    countries = [
        normalize_space(str(country)).lower()
        for country in settings.get("countries", ["fr", "gb", "de", "at", "pl"])
        if normalize_space(str(country))
    ]
    max_queries = int(settings.get("max_queries", 16) or 16)
    results_per_page = max(1, min(int(settings.get("results_per_page", 30) or 30), 50))
    jobs: list[Job] = []
    for country in countries:
        for query in select_query_items(config, limit=max_queries, early_career_min=4):
            term = query.get("term", "")
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            data = http.fetch_json(
                url,
                {
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": results_per_page,
                    "what": term,
                    "content-type": "application/json",
                    "sort_by": "date",
                },
            )
            for item in data.get("results", []):
                jobs.append(
                    Job(
                        source=f"Adzuna {country}",
                        source_type="official_api",
                        title=normalize_space(item.get("title")),
                        company=normalize_space((item.get("company") or {}).get("display_name")),
                        url=item.get("redirect_url", ""),
                        apply_url=item.get("redirect_url", ""),
                        location=normalize_space((item.get("location") or {}).get("display_name")),
                        description=clean_html(item.get("description")),
                        posted_at=item.get("created") or "",
                        salary=_salary(item),
                        raw_id=str(item.get("id") or ""),
                    )
                )
    return jobs, ""


def fetch_serpapi(config: dict[str, Any], http: HttpClient) -> tuple[list[Job], str]:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        return [], "missing_config: SERPAPI_KEY absent"
    jobs: list[Job] = []
    locations = ["Ireland", "Switzerland", "Belgium", "Singapore", "France", "Netherlands", "Luxembourg"]
    for query in select_query_items(config, limit=6, early_career_min=2):
        for location in locations:
            data = http.fetch_json(
                "https://serpapi.com/search.json",
                {
                    "engine": "google_jobs",
                    "q": query.get("term", ""),
                    "location": location,
                    "api_key": key,
                    "hl": "en",
                },
            )
            for item in data.get("jobs_results", []):
                apply_options = item.get("apply_options") or []
                apply_url = apply_options[0].get("link") if apply_options else item.get("share_link", "")
                jobs.append(
                    Job(
                        source="SerpAPI Google Jobs",
                        source_type="paid_api",
                        title=normalize_space(item.get("title")),
                        company=normalize_space(item.get("company_name")),
                        url=apply_url or item.get("share_link", ""),
                        apply_url=apply_url or item.get("share_link", ""),
                        location=normalize_space(item.get("location")),
                        description=clean_html(item.get("description")),
                        posted_at=(item.get("detected_extensions") or {}).get("posted_at", ""),
                        salary=normalize_space((item.get("detected_extensions") or {}).get("salary")),
                        raw_id=str(item.get("job_id") or ""),
                    )
                )
    return jobs, ""


def fetch_jooble(config: dict[str, Any], http: HttpClient) -> tuple[list[Job], str]:
    key = os.getenv("JOOBLE_API_KEY")
    if not key:
        return [], "missing_config: JOOBLE_API_KEY absent"
    jobs: list[Job] = []
    settings = dict(config.get("jooble", {}))
    max_queries = int(settings.get("max_queries", 8) or 8)
    locations = [
        normalize_space(str(location))
        for location in settings.get(
            "locations",
            ["Ireland", "Switzerland", "Belgium", "Singapore", "France", "Netherlands", "Luxembourg", "United Kingdom", "Germany"],
        )
        if normalize_space(str(location))
    ]
    for query in select_query_items(config, limit=max_queries, early_career_min=2):
        for location in locations:
            body = json.dumps({"keywords": query.get("term"), "location": location, "page": 1}).encode("utf-8")
            data = http.fetch_json(
                f"https://jooble.org/api/{key}",
                method="POST",
                headers={"Content-Type": "application/json"},
                body=body,
            )
            for item in data.get("jobs", []):
                jobs.append(
                    Job(
                        source="Jooble",
                        source_type="paid_api",
                        title=normalize_space(item.get("title")),
                        company=normalize_space(item.get("company")),
                        url=item.get("link", ""),
                        apply_url=item.get("link", ""),
                        location=normalize_space(item.get("location")),
                        description=clean_html(item.get("snippet")),
                        posted_at=item.get("updated") or "",
                        salary=normalize_space(item.get("salary")),
                        raw_id=str(item.get("id") or item.get("link") or ""),
                    )
                )
    return jobs, ""


def fetch_jobspy_api(config: dict[str, Any], http: HttpClient) -> tuple[list[Job], str]:
    base = os.getenv("JOBSPY_API_URL", "").rstrip("/")
    if not base:
        return [], "missing_config: JOBSPY_API_URL absent"
    if not _quick_health(base):
        return [], f"service_unavailable: JobSpy API injoignable sur {base}"
    headers = {}
    api_key = os.getenv("JOBSPY_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    settings = dict(config.get("jobspy_direct", {}))
    sites = [str(site).strip() for site in settings.get("sites", ["indeed"]) if str(site).strip()]
    if settings.get("include_linkedin") or os.getenv("JOBRADAR_JOBSPY_LINKEDIN", "").lower() in {"1", "true", "yes"}:
        if "linkedin" not in sites:
            sites.append("linkedin")
    max_queries = int(settings.get("max_queries", 8) or 8)
    results_wanted = int(settings.get("results_wanted", 12) or 12)
    hours_old = int(settings.get("hours_old", 336) or 336)
    locations = [
        str(item.get("label", "")).strip()
        for item in settings.get("locations", [])
        if isinstance(item, dict) and str(item.get("label", "")).strip()
    ] or ["Ireland", "Switzerland", "Belgium", "Singapore", "France"]
    jobs: list[Job] = []
    failures: list[str] = []
    for query in select_query_items(config, limit=max_queries, early_career_min=3):
        for location in locations:
            try:
                data = http.fetch_json(
                    f"{base}/api/v1/search_jobs",
                    {
                        "site_name": sites,
                        "search_term": query.get("term"),
                        "location": location,
                        "results_wanted": results_wanted,
                        "hours_old": hours_old,
                        "linkedin_fetch_description": "false",
                    },
                    headers=headers,
                )
            except HttpError as exc:
                failures.append(str(exc))
                continue
            for item in data.get("jobs", []):
                jobs.append(
                    Job(
                        source="JobSpy API",
                        source_type="scraper_api",
                        title=normalize_space(item.get("TITLE") or item.get("title")),
                        company=normalize_space(item.get("COMPANY") or item.get("company")),
                        url=item.get("LINK") or item.get("job_url") or "",
                        apply_url=item.get("LINK") or item.get("job_url") or "",
                        location=normalize_space(item.get("LOCATION") or item.get("location")),
                        description=clean_html(item.get("DESCRIPTION") or item.get("description")),
                        posted_at=item.get("DATE") or item.get("date_posted") or "",
                        salary=normalize_space(item.get("salary") or ""),
                        raw_id=str(item.get("id") or item.get("LINK") or ""),
                    )
                )
    if not jobs and failures:
        first = failures[0][:300]
        if all("HTTP 401" in failure or "HTTP 403" in failure for failure in failures):
            return [], f"auth_error: JobSpy API search refusee sur toutes les requetes: {first}"
        return [], f"runtime_error: JobSpy API {len(failures)} recherche(s) echouee(s), premiere erreur: {first}"
    return jobs, ""


def fetch_jobspy_direct(config: dict[str, Any], http: HttpClient) -> tuple[list[Job], str]:
    del http
    uv = shutil.which("uv")
    if not uv:
        return [], "uv absent, impossible de lancer python-jobspy en mode isole"
    root = _project_root()
    script = root / "scripts" / "jobspy_fetch.py"
    if not script.exists():
        return [], f"script JobSpy absent: {script}"
    settings = dict(config.get("jobspy_direct", {}))
    if os.getenv("JOBRADAR_JOBSPY_LINKEDIN", "").lower() in {"1", "true", "yes"}:
        settings["include_linkedin"] = True
    max_queries = int(settings.get("max_queries", 8) or 8)
    timeout_seconds = _jobspy_timeout_seconds(settings)
    queries = select_query_items(config, limit=max_queries, early_career_min=3)
    payload = json.dumps({"queries": queries, "settings": settings}, ensure_ascii=False)
    command = [
        uv,
        "run",
        "--isolated",
        "--no-project",
        "--with",
        JOBSPY_PACKAGE,
        "--",
        "python",
        str(script),
    ]
    try:
        completed = _run_text_command(command, input_text=payload, cwd=root, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired:
        return [], f"JobSpy direct timeout apres {timeout_seconds}s"
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout).strip().splitlines()[-8:]
        return [], "JobSpy direct erreur: " + " | ".join(error)[:600]
    if completed.stdout is None:
        return [], "JobSpy direct sortie stdout vide"
    try:
        rows = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [], "JobSpy direct sortie JSON invalide: " + completed.stdout[:300]
    jobs: list[Job] = []
    for item in rows:
        location = _location_from_jobspy(item)
        jobs.append(
            Job(
                source="JobSpy Direct",
                source_type="scraper_api",
                title=normalize_space(item.get("title")),
                company=normalize_space(item.get("company")),
                url=item.get("job_url") or item.get("url") or "",
                apply_url=item.get("job_url") or item.get("url") or "",
                location=location,
                country=normalize_space((item.get("location") or {}).get("country") if isinstance(item.get("location"), dict) else ""),
                remote=bool(item.get("is_remote")),
                description=clean_html(item.get("description")),
                posted_at=item.get("date_posted") or "",
                salary=_jobspy_salary(item),
                employment_type=normalize_space(item.get("job_type")),
                raw_id=str(item.get("id") or item.get("job_url") or ""),
                tags=[normalize_space(item.get("site"))],
            )
        )
    return jobs, ""


def _jobspy_timeout_seconds(settings: dict[str, Any]) -> int:
    try:
        configured = int(settings.get("timeout_seconds", JOBSPY_DEFAULT_TIMEOUT_SECONDS) or JOBSPY_DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        configured = JOBSPY_DEFAULT_TIMEOUT_SECONDS
    return max(30, min(configured, 900))


def _run_text_command(
    command: list[str],
    *,
    input_text: str,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="jobradai-jobspy-") as temp_dir:
        stdout_path = Path(temp_dir) / "stdout.txt"
        stderr_path = Path(temp_dir) / "stderr.txt"
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file, stderr_path.open(
            "w", encoding="utf-8", errors="replace"
        ) as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
            )
            try:
                if process.stdin:
                    try:
                        process.stdin.write(input_text)
                    except BrokenPipeError:
                        pass
                    finally:
                        with contextlib.suppress(Exception):
                            process.stdin.close()
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                _terminate_process_tree(process.pid)
                with contextlib.suppress(Exception):
                    process.kill()
                with contextlib.suppress(Exception):
                    process.wait(timeout=5)
                stdout_file.flush()
                stderr_file.flush()
                exc.output = _read_text_file(stdout_path)
                exc.stderr = _read_text_file(stderr_path)
                raise
            stdout_file.flush()
            stderr_file.flush()
        return subprocess.CompletedProcess(
            command,
            returncode,
            _read_text_file(stdout_path),
            _read_text_file(stderr_path),
        )


def _read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    with contextlib.suppress(Exception):
        os.kill(pid, 9)


def fetch_france_travail(config: dict[str, Any], http: HttpClient) -> tuple[list[Job], str]:
    client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
    client_secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        return [], "missing_config: FRANCE_TRAVAIL_CLIENT_ID/SECRET absents"
    token_url = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "scope": "api_offresdemploiv2 o2dsoffre",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    token = http.fetch_json(token_url, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=body)
    access_token = token.get("access_token")
    if not access_token:
        return [], "auth_error: token France Travail absent"
    jobs: list[Job] = []
    settings = dict(config.get("france_travail", {}))
    terms = _france_travail_terms(config, max_queries=int(settings.get("max_queries", 22) or 22))
    for term in terms:
        text = http.fetch_text(
            "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search",
            {"motsCles": term, "range": "0-49", "sort": 1},
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if not text.strip():
            continue
        data = json.loads(text)
        for item in data.get("resultats", []):
            company = item.get("entreprise") or {}
            place = item.get("lieuTravail") or {}
            jobs.append(
                Job(
                    source="France Travail",
                    source_type="official_api",
                    title=normalize_space(item.get("intitule")),
                    company=normalize_space(company.get("nom")),
                    url=item.get("origineOffre", {}).get("urlOrigine") or "",
                    apply_url=item.get("contact", {}).get("urlPostulation") or item.get("origineOffre", {}).get("urlOrigine") or "",
                    location=normalize_space(place.get("libelle")),
                    country="France",
                    description=clean_html(item.get("description")),
                    posted_at=item.get("dateCreation") or "",
                    salary=normalize_space((item.get("salaire") or {}).get("libelle")),
                    employment_type=normalize_space((item.get("typeContrat") or "")),
                    raw_id=str(item.get("id") or ""),
                )
            )
    return jobs, ""


def _france_travail_terms(config: dict[str, Any], *, max_queries: int = 22) -> list[str]:
    base_limit = max(1, min(max_queries, 18))
    terms = select_query_terms(config, limit=base_limit, early_career_min=4)
    terms.extend(
        [
            "ingénieur data",
            "ingénieur IA",
            "architecte data",
            "MLOps",
            "LLM",
            "RAG",
            "ingénieur machine learning",
            "ingénieur ML",
            "ML engineer",
            "analytics engineer",
            "ingénieur recherche IA",
            "applied scientist",
            "interpretability",
            "explainability",
            "AI safety",
            "knowledge graph",
            "semantic web",
            "explicabilité IA",
            "interprétabilité IA",
            "sécurité IA",
            "graphe de connaissances",
            "web sémantique",
            "développeur IA",
            "analyste data",
            "consultant data",
            "business intelligence",
            "Power BI",
        ]
    )
    return _dedupe_terms(terms)[:max(1, max_queries)]


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for term in terms:
        cleaned = normalize_space(term)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def fetch_vdab_generic(config: dict[str, Any], http: HttpClient) -> tuple[list[Job], str]:
    endpoint = os.getenv("VDAB_SEARCH_URL")
    key = os.getenv("VDAB_API_KEY")
    if not endpoint or not key:
        return [], "missing_config: VDAB_SEARCH_URL/VDAB_API_KEY absents"
    jobs: list[Job] = []
    for query in select_query_items(config, limit=8, early_career_min=2):
        data = http.fetch_json(endpoint, {"q": query.get("term"), "limit": 50}, headers={"Ocp-Apim-Subscription-Key": key})
        rows = data.get("vacatures") or data.get("jobs") or data.get("results") or []
        for item in rows:
            jobs.append(
                Job(
                    source="VDAB",
                    source_type="official_api",
                    title=normalize_space(item.get("title") or item.get("titel")),
                    company=normalize_space(item.get("company") or item.get("bedrijf")),
                    url=item.get("url") or item.get("link") or "",
                    apply_url=item.get("apply_url") or item.get("url") or "",
                    location=normalize_space(item.get("location") or item.get("plaats")),
                    country="Belgium",
                    description=clean_html(item.get("description") or item.get("omschrijving")),
                    posted_at=item.get("posted_at") or item.get("datum") or "",
                    raw_id=str(item.get("id") or item.get("vacatureId") or ""),
                )
            )
    return jobs, ""


def _quick_health(base: str) -> bool:
    for suffix in ("/health", "/ping", "/docs"):
        try:
            request = urllib.request.Request(base + suffix, headers={"User-Agent": "JobRadarAI/0.1"})
            with urllib.request.urlopen(request, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False


def _project_root():
    return Path(__file__).resolve().parents[3]


def _location_from_jobspy(item: dict[str, Any]) -> str:
    raw = item.get("location")
    if isinstance(raw, dict):
        return normalize_space(", ".join(str(raw.get(k) or "") for k in ("city", "state", "country") if raw.get(k)))
    return normalize_space(raw or item.get("city") or "")


def _jobspy_salary(item: dict[str, Any]) -> str:
    minimum = item.get("min_amount")
    maximum = item.get("max_amount")
    currency = item.get("currency") or ""
    interval = item.get("interval") or ""
    if minimum and maximum:
        return f"{minimum}-{maximum} {currency} {interval}".strip()
    if minimum:
        return f"{minimum}+ {currency} {interval}".strip()
    if maximum:
        return f"up to {maximum} {currency} {interval}".strip()
    return ""


def _salary(item: dict[str, Any]) -> str:
    minimum = item.get("salary_min")
    maximum = item.get("salary_max")
    currency = item.get("salary_currency") or ""
    if minimum and maximum:
        return f"{minimum}-{maximum} {currency}".strip()
    if minimum:
        return f"{minimum}+ {currency}".strip()
    return ""
