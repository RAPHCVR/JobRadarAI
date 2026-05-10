from __future__ import annotations

import csv
import html
import json
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from jobradai.graduate import write_graduate_digest
from jobradai.models import Job, SourceRun
from jobradai.store import write_sqlite


def export_all(output_dir: Path, jobs: list[Job], source_runs: list[SourceRun], profile: dict[str, Any] | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_llm_outputs(output_dir)
    _write_json(output_dir / "jobs.json", jobs)
    _write_csv(output_dir / "jobs.csv", jobs)
    write_graduate_digest(output_dir, [job.as_dict() for job in jobs], profile or {})
    _write_markdown(output_dir / "report.md", jobs, source_runs)
    _write_html(output_dir / "dashboard.html", jobs, source_runs)
    _write_runs(output_dir / "sources.json", source_runs)
    write_sqlite(output_dir / "jobs.sqlite", jobs)


def _remove_stale_llm_outputs(output_dir: Path) -> None:
    for name in (
        "llm_shortlist.json",
        "llm_shortlist.md",
        "llm_payload_preview.json",
        "link_checks.json",
        "link_checks.md",
        "application_queue.json",
        "application_queue.md",
        "vie_priority_queue.json",
        "vie_priority_queue.md",
        "application_messages.json",
        "application_messages.md",
        "history_dashboard.json",
        "history_dashboard.md",
        "weekly_digest.json",
        "weekly_digest.md",
        "audit.json",
        "audit.md",
    ):
        path = output_dir / name
        if path.exists():
            path.unlink()


def _write_json(path: Path, jobs: list[Job]) -> None:
    path.write_text(json.dumps([job.as_dict() for job in jobs], ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, jobs: list[Job]) -> None:
    fields = [
        "score",
        "market",
        "title",
        "company",
        "location",
        "source",
        "source_type",
        "salary",
        "salary_normalized_annual_eur",
        "salary_currency",
        "deadline",
        "language_check",
        "remote_location_validity",
        "required_years",
        "experience_check",
        "experience_evidence",
        "posted_at",
        "url",
        "reasons",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for job in jobs:
            writer.writerow(
                {
                    "score": job.score,
                    "market": _csv_cell(job.market),
                    "title": _csv_cell(job.title),
                    "company": _csv_cell(job.company),
                    "location": _csv_cell(job.location),
                    "source": _csv_cell(job.source),
                    "source_type": _csv_cell(job.source_type),
                    "salary": _csv_cell(job.salary),
                    "salary_normalized_annual_eur": job.salary_normalized_annual_eur or "",
                    "salary_currency": _csv_cell(job.salary_currency),
                    "deadline": _csv_cell(job.deadline),
                    "language_check": _csv_cell(job.language_check),
                    "remote_location_validity": _csv_cell(job.remote_location_validity),
                    "required_years": job.required_years if job.required_years is not None else "",
                    "experience_check": _csv_cell(job.experience_check),
                    "experience_evidence": _csv_cell(job.experience_evidence),
                    "posted_at": _csv_cell(job.posted_at),
                    "url": _csv_cell(_safe_url(job.url)),
                    "reasons": _csv_cell(" | ".join(job.reasons)),
                }
            )


def _write_runs(path: Path, runs: list[SourceRun]) -> None:
    path.write_text(json.dumps([asdict(run) for run in runs], ensure_ascii=False, indent=2), encoding="utf-8")


def _write_markdown(path: Path, jobs: list[Job], runs: list[SourceRun]) -> None:
    by_market = Counter(job.market for job in jobs)
    by_source = Counter(job.source for job in jobs)
    lines = [
        "# JobRadarAI Report",
        "",
        f"- Offres retenues: **{len(jobs)}**",
        f"- Score minimum: **{min((job.score for job in jobs), default=0):.1f}**",
        f"- Score maximum: **{max((job.score for job in jobs), default=0):.1f}**",
        "",
        "## Sources",
        "",
    ]
    for run in runs:
        status = "ok" if run.ok else "erreur"
        if run.skipped:
            status = "ignore"
        suffix = f" - {run.reason}" if run.reason else ""
        lines.append(f"- `{run.name}`: {status}, {run.count} offres{suffix}")
    lines.extend(["", "## Marches", ""])
    for market, count in by_market.most_common():
        lines.append(f"- `{market}`: {count}")
    lines.extend(["", "## Sources principales", ""])
    for source, count in by_source.most_common(15):
        lines.append(f"- `{source}`: {count}")
    lines.extend(["", "## Top 30", ""])
    for idx, job in enumerate(jobs[:30], start=1):
        parts = ", ".join(f"{name}={value:.0f}" for name, value in job.score_parts.items())
        lines.extend(
            [
                f"### {idx}. {job.title} - {job.company} ({job.score:.1f})",
                f"- Marche: `{job.market}` | Source: `{job.source}` | Lieu: {job.location or 'n/a'}",
                f"- Deadline: {job.deadline or 'n/a'} | Langue: `{job.language_check}` | Remote/location: `{job.remote_location_validity}`",
                f"- Experience: `{job.experience_check}` | annees requises: `{job.required_years if job.required_years is not None else 'n/a'}`",
                f"- URL: {job.url}",
                f"- Sous-scores: {parts}",
                f"- Raisons: {'; '.join(job.reasons[:8])}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_html(path: Path, jobs: list[Job], runs: list[SourceRun]) -> None:
    grouped: dict[str, list[Job]] = defaultdict(list)
    for job in jobs:
        grouped[job.market].append(job)
    source_status = "".join(
        f"<li><span class='pill {html.escape('skip' if run.skipped else 'ok' if run.ok else 'err')}'>{html.escape(run.name)}</span> "
        f"{html.escape(str(run.count))} {html.escape(run.reason)}</li>"
        for run in runs
    )
    cards = []
    for market, rows in sorted(grouped.items(), key=lambda item: max(job.score for job in item[1]), reverse=True):
        cards.append(f"<section><h2>{html.escape(market)} <small>{len(rows)} offres</small></h2>")
        for job in rows[:25]:
            safe_url = _safe_url(job.url)
            title = html.escape(job.title)
            title_html = (
                f'<a href="{html.escape(safe_url)}" target="_blank" rel="noopener noreferrer">{title}</a>'
                if safe_url
                else title
            )
            reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in job.reasons[:6])
            parts = "".join(
                f"<span>{html.escape(name)} {value:.0f}</span>" for name, value in job.score_parts.items()
            )
            cards.append(
                f"""
                <article class="job">
                  <div class="score">{job.score:.0f}</div>
                  <div class="body">
                    <h3>{title_html}</h3>
                    <p class="meta">{html.escape(job.company)} · {html.escape(job.location or 'n/a')} · {html.escape(job.source)} · {html.escape(job.salary or 'salary n/a')}</p>
                    <p class="meta">deadline {html.escape(job.deadline or 'n/a')} · langue {html.escape(job.language_check)} · remote/location {html.escape(job.remote_location_validity)}</p>
                    <p class="meta">experience {html.escape(job.experience_check)} · required years {html.escape(str(job.required_years if job.required_years is not None else 'n/a'))}</p>
                    <div class="parts">{parts}</div>
                    <ul>{reasons}</ul>
                  </div>
                </article>
                """
            )
        cards.append("</section>")
    document = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JobRadarAI</title>
  <style>
    :root {{ color-scheme: light; --ink:#18212f; --muted:#647084; --line:#d9dee8; --bg:#f7f8fb; --card:#fff; --accent:#0f766e; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ padding:28px 36px; background:#102033; color:white; }}
    header h1 {{ margin:0 0 8px; font-size:30px; letter-spacing:0; }}
    header p {{ margin:0; color:#c8d3e2; }}
    main {{ max-width:1280px; margin:0 auto; padding:24px; }}
    .summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-bottom:18px; }}
    .panel, section {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .panel strong {{ display:block; font-size:28px; }}
    .panel span, small, .meta {{ color:var(--muted); }}
    section {{ margin:18px 0; }}
    h2 {{ margin:0 0 12px; font-size:22px; }}
    .job {{ display:grid; grid-template-columns:64px 1fr; gap:12px; padding:14px 0; border-top:1px solid var(--line); }}
    .job:first-of-type {{ border-top:0; }}
    .score {{ height:52px; border-radius:8px; display:grid; place-items:center; background:#e6f4f1; color:#075e57; font-size:24px; font-weight:700; }}
    h3 {{ margin:0 0 4px; font-size:18px; }}
    a {{ color:#0f5f96; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .parts {{ display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }}
    .parts span, .pill {{ border:1px solid var(--line); border-radius:999px; padding:4px 8px; color:var(--muted); font-size:12px; }}
    .pill.ok {{ color:#0f766e; border-color:#99d5cc; }}
    .pill.err {{ color:#b42318; border-color:#f1aaa4; }}
    .pill.skip {{ color:#806000; border-color:#e8d88c; }}
    ul {{ margin:8px 0 0; padding-left:18px; }}
    li {{ margin:3px 0; }}
  </style>
</head>
<body>
  <header>
    <h1>JobRadarAI</h1>
    <p>Radar offres data, IA, LLM orchestration, recherche appliquee et VIE international.</p>
  </header>
  <main>
    <div class="summary">
      <div class="panel"><strong>{len(jobs)}</strong><span>offres retenues</span></div>
      <div class="panel"><strong>{max((job.score for job in jobs), default=0):.0f}</strong><span>meilleur score</span></div>
      <div class="panel"><strong>{len(grouped)}</strong><span>marches detectes</span></div>
    </div>
    <details class="panel"><summary>Etat des sources</summary><ul>{source_status}</ul></details>
    {''.join(cards)}
  </main>
</body>
</html>"""
    path.write_text(document, encoding="utf-8")


def _csv_cell(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    if text[0] in ("=", "+", "-", "@", "\t", "\r", "\n"):
        return "'" + text
    return text


def _safe_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return text
