from __future__ import annotations

import contextlib
import json
import sys
from typing import Any

from jobspy import scrape_jobs


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    payload = json.loads(sys.stdin.read())
    queries = [str(item.get("term", "")).strip() for item in payload.get("queries", []) if item.get("term")]
    settings = payload.get("settings", {})
    max_queries = int(settings.get("max_queries", 6))
    results_wanted = int(settings.get("results_wanted", 12))
    hours_old = int(settings.get("hours_old", 336))
    sites = list(settings.get("sites", ["indeed", "glassdoor"]))
    if settings.get("include_linkedin") and "linkedin" not in sites:
        sites.append("linkedin")
    locations = settings.get("locations", [])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries[:max_queries]:
        search_term = _jobspy_query(query)
        for location in locations:
            label = location.get("label", "")
            country = location.get("country_indeed", "")
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    df = scrape_jobs(
                        site_name=sites,
                        search_term=search_term,
                        location=label,
                        results_wanted=results_wanted,
                        hours_old=hours_old,
                        country_indeed=country,
                        description_format="markdown",
                        verbose=0,
                        linkedin_fetch_description=False,
                    )
            except Exception as exc:  # noqa: BLE001 - one location must not kill the batch
                print(f"[jobspy] {query} / {label}: {type(exc).__name__}: {exc}", file=sys.stderr)
                continue
            for item in json.loads(df.to_json(orient="records", date_format="iso")):
                key = "|".join(
                    str(item.get(part, "")).lower().strip()
                    for part in ("site", "company", "title", "job_url")
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(item)
    print(json.dumps(rows, ensure_ascii=False))
    return 0


def _jobspy_query(query: str) -> str:
    lower = query.lower()
    if "graduate" in lower or "new grad" in lower or "early career" in lower or "campus" in lower:
        return (
            '("graduate" OR "new grad" OR "early careers" OR campus OR "entry level") '
            '("data engineer" OR "AI engineer" OR "machine learning" OR "software engineer" OR analytics OR LLM OR GenAI) '
            '-intern -apprentice -alternance'
        )
    if "trainee" in lower or "junior" in lower:
        return (
            '("junior" OR trainee OR "entry level") '
            '("data engineer" OR "AI engineer" OR "machine learning" OR "software engineer" OR analytics OR LLM OR GenAI) '
            '-intern -apprentice -alternance'
        )
    if "data engineer" in lower:
        return '"data engineer" (python OR sql OR spark OR databricks OR snowflake OR dbt OR airflow OR dagster OR rag OR llm) -intern -apprentice'
    if "ingénieur data" in lower or "ingenieur data" in lower:
        return '("ingénieur data" OR "ingenieur data" OR "data engineer") (python OR sql OR spark OR databricks OR cloud OR rag OR llm) -alternance'
    if "ingénieur ia" in lower or "ingenieur ia" in lower:
        return '("ingénieur IA" OR "ingenieur IA" OR "AI engineer" OR GenAI OR LLM OR RAG) (python OR mlops OR cloud OR evaluation) -alternance'
    if "machine learning engineer" in lower:
        return '("machine learning engineer" OR "ML engineer") (python OR mlops OR production OR platform OR evaluation) -intern -apprentice'
    if "data scientist" in lower:
        return '"data scientist" (python OR machine learning OR LLM OR GenAI OR NLP OR time series) -intern -apprentice'
    if "llm" in lower or "genai" in lower:
        return '(LLM OR "large language model" OR GenAI OR RAG) (engineer OR platform OR orchestration OR evaluation) -intern -apprentice'
    if "mlops" in lower or "platform" in lower:
        return '(MLOps OR LLMOps OR "ML platform" OR "AI platform") (engineer OR platform) -intern -apprentice'
    if "research" in lower or "nlp" in lower:
        return '("research engineer" OR NLP OR "applied scientist") (LLM OR AI OR retrieval OR machine learning) -intern'
    return f'"{query}" -intern -apprentice -alternance'


if __name__ == "__main__":
    raise SystemExit(main())
