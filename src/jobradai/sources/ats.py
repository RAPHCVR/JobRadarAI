from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from jobradai.http import HttpClient, HttpError
from jobradai.models import Job
from jobradai.text import clean_html, normalize_space, text_blob


def fetch_ats_feed(feed: dict[str, Any], http: HttpClient) -> list[Job]:
    http = _http_for_feed(feed, http)
    feed_type = str(feed.get("type", "")).lower()
    if feed_type == "greenhouse":
        return _greenhouse(feed, http)
    if feed_type == "lever":
        return _lever(feed, http)
    if feed_type == "ashby":
        return _ashby(feed, http)
    if feed_type == "smartrecruiters":
        return _smartrecruiters(feed, http)
    if feed_type == "workable":
        return _workable(feed, http)
    if feed_type == "recruitee":
        return _recruitee(feed, http)
    if feed_type == "personio_xml":
        return _personio_xml(feed, http)
    raise ValueError(f"Unsupported ATS feed type: {feed_type}")


def _http_for_feed(feed: dict[str, Any], http: HttpClient) -> HttpClient:
    base_timeout = int(getattr(http, "timeout", 25))
    base_retries = int(getattr(http, "retries", 2))
    timeout = _int_setting(feed.get("timeout"), base_timeout)
    retries = _int_setting(feed.get("retries"), base_retries)
    if timeout == base_timeout and retries == base_retries:
        return http
    scoped = HttpClient(timeout=timeout, retries=retries)
    scoped.user_agent = getattr(http, "user_agent", scoped.user_agent)
    return scoped


def _int_setting(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _base_job(feed: dict[str, Any], title: str, url: str) -> Job:
    return Job(
        source=feed.get("name", "ATS"),
        source_type="ats",
        ats=feed.get("type", ""),
        title=normalize_space(title),
        company=feed.get("name", ""),
        url=url,
        apply_url=url,
    )


def _greenhouse(feed: dict[str, Any], http: HttpClient) -> list[Job]:
    data = http.fetch_json(feed["url"])
    jobs: list[Job] = []
    for item in data.get("jobs", []):
        job = _base_job(feed, item.get("title", ""), item.get("absolute_url", ""))
        job.raw_id = str(item.get("id", ""))
        job.location = _extract_location(item.get("location"))
        job.posted_at = item.get("updated_at") or ""
        job.description = clean_html(item.get("content", ""))
        job.employment_type = _department_text(item)
        jobs.append(job)
    return jobs


def _lever(feed: dict[str, Any], http: HttpClient) -> list[Job]:
    data = http.fetch_json(feed["url"])
    jobs: list[Job] = []
    for item in data if isinstance(data, list) else []:
        job = _base_job(feed, item.get("text", ""), item.get("hostedUrl", ""))
        job.raw_id = str(item.get("id", ""))
        categories = item.get("categories") or {}
        job.location = normalize_space(categories.get("location") or "")
        job.employment_type = normalize_space(categories.get("commitment") or "")
        job.posted_at = str(item.get("createdAt") or "")
        job.description = clean_html(
            text_blob(item.get("descriptionPlain"), item.get("additionalPlain"), item.get("description"))
        )
        jobs.append(job)
    return jobs


def _ashby(feed: dict[str, Any], http: HttpClient) -> list[Job]:
    data = http.fetch_json(feed["url"])
    rows = data.get("jobs") if isinstance(data, dict) else []
    jobs: list[Job] = []
    for item in rows or []:
        url = item.get("jobUrl") or item.get("applyUrl") or item.get("url") or ""
        job = _base_job(feed, item.get("title", ""), url)
        job.raw_id = str(item.get("id", ""))
        job.location = _ashby_location(item)
        job.remote = bool(item.get("isRemote")) or "remote" in str(item.get("workplaceType", "")).lower()
        job.employment_type = normalize_space(
            text_blob(item.get("employmentType"), item.get("workplaceType"), item.get("team"))
        )
        job.posted_at = item.get("publishedAt") or item.get("publishedDate") or item.get("createdAt") or ""
        job.description = clean_html(
            text_blob(item.get("descriptionPlain"), item.get("descriptionHtml"), item.get("description"))
        )
        job.salary = _ashby_compensation(item.get("compensation"))
        job.tags = [tag for tag in [normalize_space(item.get("department")), normalize_space(item.get("team"))] if tag]
        jobs.append(job)
    return jobs


def _smartrecruiters(feed: dict[str, Any], http: HttpClient) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    for params in _smartrecruiters_page_params(feed):
        data = http.fetch_json(feed["url"], params=params)
        rows = data.get("content") or data.get("postings") or []
        for item in rows:
            if not isinstance(item, dict):
                continue
            raw_id = str(item.get("id") or item.get("uuid") or "").strip()
            if raw_id and raw_id in seen:
                continue
            detail = _smartrecruiters_detail(item, http, enabled=bool(feed.get("fetch_details", True)))
            if _smartrecruiters_inactive(detail):
                continue
            if not _smartrecruiters_title_allowed(feed, item, detail):
                continue
            detail_id = str(detail.get("id") or detail.get("uuid") or "").strip()
            dedupe_id = detail_id or raw_id
            if dedupe_id and dedupe_id in seen:
                continue
            for candidate_id in (raw_id, detail_id):
                if candidate_id:
                    seen.add(candidate_id)
            jobs.append(_smartrecruiters_job(feed, item, detail))
    return jobs


def _smartrecruiters_page_params(feed: dict[str, Any]) -> list[dict[str, Any]]:
    page_size = _bounded_int(feed.get("page_size") or feed.get("limit"), default=100, minimum=1, maximum=100)
    max_pages = _bounded_int(feed.get("max_pages"), default=1, minimum=1, maximum=8)
    queries = [str(query).strip() for query in feed.get("queries", []) if str(query).strip()]
    if not queries:
        queries = [""]
    params: list[dict[str, Any]] = []
    for query in queries:
        for page in range(max_pages):
            item: dict[str, Any] = {"limit": page_size, "offset": page * page_size}
            if query:
                item["q"] = query
            params.append(item)
    return params


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _smartrecruiters_detail(item: dict[str, Any], http: HttpClient, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return item
    ref = str(item.get("ref") or "").strip()
    if not ref:
        return item
    try:
        data = http.fetch_json(ref)
    except HttpError:
        return item
    return data if isinstance(data, dict) else item


def _smartrecruiters_inactive(item: dict[str, Any]) -> bool:
    visibility = str(item.get("visibility") or "").upper()
    return item.get("active") is False or visibility == "INTERNAL"


def _smartrecruiters_title_allowed(feed: dict[str, Any], item: dict[str, Any], detail: dict[str, Any]) -> bool:
    title = _smartrecruiters_title(item, detail).lower()
    include = [str(term).strip().lower() for term in feed.get("include_title_keywords", []) if str(term).strip()]
    exclude = [str(term).strip().lower() for term in feed.get("exclude_title_keywords", []) if str(term).strip()]
    if include and not any(term in title for term in include):
        return False
    return not any(term in title for term in exclude)


def _smartrecruiters_title(item: dict[str, Any], detail: dict[str, Any]) -> str:
    return normalize_space(detail.get("name") or detail.get("title") or item.get("name") or item.get("title"))


def _smartrecruiters_job(feed: dict[str, Any], item: dict[str, Any], detail: dict[str, Any]) -> Job:
    url = detail.get("postingUrl") or detail.get("applyUrl") or item.get("url") or item.get("ref") or ""
    apply_url = detail.get("applyUrl") or url
    job = _base_job(feed, _smartrecruiters_title(item, detail), url)
    job.apply_url = apply_url
    job.raw_id = str(detail.get("id") or item.get("id") or item.get("uuid") or "")
    job.location = _extract_location(detail.get("location") or item.get("location"))
    location = detail.get("location") or item.get("location") or {}
    if isinstance(location, dict):
        job.remote = bool(location.get("remote") or location.get("hybrid"))
    job.posted_at = detail.get("releasedDate") or item.get("releasedDate") or item.get("createdOn") or ""
    job.description = _smartrecruiters_description(detail)
    job.employment_type = normalize_space(
        text_blob(
            _label(detail.get("typeOfEmployment") or item.get("typeOfEmployment")),
            _label(detail.get("experienceLevel") or item.get("experienceLevel")),
            _label(detail.get("function") or item.get("function")),
            _label(detail.get("department") or item.get("department")),
        )
    )
    job.tags = _smartrecruiters_tags(detail or item)
    return job


def _smartrecruiters_description(item: dict[str, Any]) -> str:
    sections = item.get("jobAd", {}).get("sections", {}) if isinstance(item.get("jobAd"), dict) else {}
    parts: list[str] = []
    if isinstance(sections, dict):
        for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
            section = sections.get(key)
            if isinstance(section, dict):
                parts.append(str(section.get("text") or ""))
    parts.extend(_smartrecruiters_tags(item))
    return clean_html(text_blob(*parts))


def _smartrecruiters_tags(item: dict[str, Any]) -> list[str]:
    tags = [
        _label(item.get("function")),
        _label(item.get("department")),
        _label(item.get("typeOfEmployment")),
        _label(item.get("experienceLevel")),
    ]
    for field in item.get("customField") or []:
        if isinstance(field, dict):
            tags.append(normalize_space(field.get("valueLabel")))
    return [tag for tag in tags if tag]


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return normalize_space(value.get("label") or value.get("name") or value.get("id"))
    return normalize_space(str(value or ""))


def _workable(feed: dict[str, Any], http: HttpClient) -> list[Job]:
    data = http.fetch_json(feed["url"])
    rows = data.get("jobs") or data.get("results") or []
    jobs: list[Job] = []
    for item in rows:
        url = item.get("url") or item.get("shortlink") or ""
        job = _base_job(feed, item.get("title") or item.get("full_title", ""), url)
        job.raw_id = str(item.get("id") or item.get("shortcode") or "")
        job.location = _extract_location(item.get("location"))
        job.posted_at = item.get("published_on") or item.get("created_at") or ""
        job.description = clean_html(text_blob(item.get("description"), item.get("requirements")))
        jobs.append(job)
    return jobs


def _recruitee(feed: dict[str, Any], http: HttpClient) -> list[Job]:
    data = http.fetch_json(feed["url"])
    rows = data.get("offers") or data.get("jobs") or []
    jobs: list[Job] = []
    for item in rows:
        url = item.get("careers_url") or item.get("url") or ""
        job = _base_job(feed, item.get("title", ""), url)
        job.raw_id = str(item.get("id", ""))
        job.location = _extract_location(item.get("location"))
        job.posted_at = item.get("created_at") or ""
        job.description = clean_html(item.get("description") or "")
        jobs.append(job)
    return jobs


def _personio_xml(feed: dict[str, Any], http: HttpClient) -> list[Job]:
    text = http.fetch_text(feed["url"])
    root = ET.fromstring(text)
    jobs: list[Job] = []
    for item in root.findall(".//position"):
        title = _node_text(item, "name")
        url = _node_text(item, "jobDescriptions/jobDescription/value") or feed.get("public_url", "")
        job = _base_job(feed, title, url)
        job.raw_id = _node_text(item, "id")
        job.location = _node_text(item, "office")
        job.employment_type = _node_text(item, "employmentType")
        job.posted_at = _node_text(item, "createdAt")
        job.description = clean_html(" ".join(node.text or "" for node in item.findall(".//jobDescription/value")))
        jobs.append(job)
    return jobs


def _extract_location(value: Any) -> str:
    if isinstance(value, str):
        return normalize_space(value)
    if isinstance(value, list):
        return normalize_space(", ".join(_extract_location(item) for item in value if item))
    if isinstance(value, dict):
        parts = [
            value.get("locationName"),
            value.get("address", {}).get("postalAddress", {}).get("addressLocality")
            if isinstance(value.get("address"), dict)
            else None,
            value.get("name"),
            value.get("city"),
            value.get("region"),
            value.get("country"),
            value.get("countryCode"),
        ]
        return normalize_space(", ".join(str(p) for p in parts if p))
    return ""


def _department_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("departments", "offices"):
        for entry in item.get(key) or []:
            if isinstance(entry, dict) and entry.get("name"):
                parts.append(entry["name"])
    return normalize_space(", ".join(parts))


def _ashby_location(item: dict[str, Any]) -> str:
    primary = item.get("locationName") or _extract_location(item.get("location"))
    secondary = _extract_location(item.get("secondaryLocations") or [])
    return normalize_space(", ".join(part for part in [primary, secondary] if part))


def _ashby_compensation(value: Any) -> str:
    if isinstance(value, str):
        return normalize_space(value)
    if not isinstance(value, dict):
        return ""
    for key in ("compensationTierSummary", "summary", "description"):
        if value.get(key):
            return normalize_space(value.get(key))
    tiers = value.get("compensationTiers")
    if isinstance(tiers, list):
        parts = []
        for tier in tiers:
            if not isinstance(tier, dict):
                continue
            summary = tier.get("summary") or tier.get("title")
            if summary:
                parts.append(str(summary))
        return normalize_space("; ".join(parts))
    return ""


def _node_text(root: ET.Element, path: str) -> str:
    node = root.find(path)
    return normalize_space(node.text if node is not None else "")
