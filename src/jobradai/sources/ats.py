from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from jobradai.http import HttpClient
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
    data = http.fetch_json(feed["url"])
    rows = data.get("content") or data.get("postings") or []
    jobs: list[Job] = []
    for item in rows:
        url = item.get("ref") or item.get("applyUrl") or item.get("url") or ""
        job = _base_job(feed, item.get("name") or item.get("title", ""), url)
        job.raw_id = str(item.get("id", ""))
        job.location = _extract_location(item.get("location"))
        job.posted_at = item.get("releasedDate") or item.get("createdOn") or ""
        job.description = clean_html(item.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""))
        jobs.append(job)
    return jobs


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
