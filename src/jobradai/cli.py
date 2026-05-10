from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jobradai.config import PROJECT_ROOT, load_config
from jobradai.audit import write_audit
from jobradai.exporters import export_all
from jobradai.graduate import write_graduate_digest
from jobradai.history import sync_history
from jobradai.link_check import verify_links
from jobradai.llm_judge import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
    DEFAULT_MAX_FALLBACK_RATIO,
    LLMJudgeError,
    LLMSettings,
    judge_jobs,
)
from jobradai.pipeline import run_pipeline
from jobradai.snapshot import write_snapshot
from jobradai.webapp import run_web_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobradai", description="Radar emplois data/IA/LLM.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Ingere, score et exporte les offres.")
    run.add_argument("--root", type=Path, default=PROJECT_ROOT)
    run.add_argument("--output", type=Path, default=None)
    run.add_argument("--max-per-source", type=int, default=None)

    sub.add_parser("sources", help="Liste les sources configurees.")

    audit = sub.add_parser("audit", help="Genere un audit local marches/langues/VIE/salaire/remote.")
    audit.add_argument("--root", type=Path, default=PROJECT_ROOT)
    audit.add_argument("--output", type=Path, default=None)

    judge = sub.add_parser("judge", help="Passe un judge LLM sur le top N deja exporte.")
    judge.add_argument("--root", type=Path, default=PROJECT_ROOT)
    judge.add_argument("--input", type=Path, default=None)
    judge.add_argument("--output", type=Path, default=None)
    judge.add_argument("--limit", type=int, default=30)
    judge.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    judge.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    judge.add_argument("--selection-mode", choices=["top", "balanced", "wide", "vie", "all"], default="wide")
    judge.add_argument("--base-url", default=None)
    judge.add_argument("--model", default=None)
    judge.add_argument("--effort", choices=["none", "minimal", "low", "medium", "high", "xhigh"], default=None)
    judge.add_argument("--transport", choices=["auto", "sdk", "raw"], default=None)
    judge.add_argument("--timeout", type=int, default=None)
    judge.add_argument("--max-fallback-ratio", type=float, default=DEFAULT_MAX_FALLBACK_RATIO)
    judge.add_argument("--dry-run", action="store_true")

    links = sub.add_parser("verify-links", help="Verifie les liens/apply du corpus exporte.")
    links.add_argument("--root", type=Path, default=PROJECT_ROOT)
    links.add_argument("--input", type=Path, default=None)
    links.add_argument("--shortlist", type=Path, default=None)
    links.add_argument("--output", type=Path, default=None)
    links.add_argument("--limit", type=int, default=160)
    links.add_argument("--timeout", type=int, default=10)
    links.add_argument("--workers", type=int, default=12)

    snapshot = sub.add_parser("snapshot", help="Archive le snapshot courant dans runs/history.")
    snapshot.add_argument("--root", type=Path, default=PROJECT_ROOT)
    snapshot.add_argument("--output", type=Path, default=None)
    snapshot.add_argument("--history", type=Path, default=None)
    snapshot.add_argument("--name", default=None)

    history = sub.add_parser("sync-history", help="Met a jour le registre multi-run et la queue de candidature.")
    history.add_argument("--root", type=Path, default=PROJECT_ROOT)
    history.add_argument("--output", type=Path, default=None)
    history.add_argument("--history-db", type=Path, default=None)
    history.add_argument("--run-name", default=None)
    history.add_argument("--recheck-stale-limit", type=int, default=40)
    history.add_argument("--timeout", type=int, default=10)
    history.add_argument("--workers", type=int, default=8)

    graduate = sub.add_parser("graduate-digest", help="Genere le digest graduate/early-career/doctoral depuis jobs.json.")
    graduate.add_argument("--root", type=Path, default=PROJECT_ROOT)
    graduate.add_argument("--input", type=Path, default=None)
    graduate.add_argument("--output", type=Path, default=None)

    web = sub.add_parser("web", help="Expose l'interface web locale ou Kubernetes.")
    web.add_argument("--root", type=Path, default=PROJECT_ROOT)
    web.add_argument("--output", type=Path, default=None)
    web.add_argument("--state-path", type=Path, default=None)
    web.add_argument("--static-dir", type=Path, default=None)
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    if args.command == "sources":
        config = load_config(PROJECT_ROOT)
        print(json.dumps(_sources_summary(config.sources), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        config = load_config(args.root)
        result = run_pipeline(config, max_per_source=args.max_per_source)
        output = args.output.resolve() if args.output else config.output_dir
        export_all(output, result.jobs, result.source_runs, profile=config.profile)
        print(f"offres={len(result.jobs)} output={output}")
        print(f"dashboard={output / 'dashboard.html'}")
        print(f"report={output / 'report.md'}")
        print(f"graduate={output / 'graduate_programs.md'}")
        return 0
    if args.command == "audit":
        config = load_config(args.root)
        output = (args.output or config.output_dir).resolve()
        report = write_audit(output, config)
        print(f"audit={output / 'audit.md'}")
        print(f"offres={report['total_jobs']} sources_ok={report['source_status']['ok']} erreurs={len(report['source_status']['errors'])}")
        return 0
    if args.command == "judge":
        config = load_config(args.root)
        input_path = (args.input or (config.output_dir / "jobs.json")).resolve()
        output = (args.output or config.output_dir).resolve()
        settings = None
        if not args.dry_run:
            settings = LLMSettings.from_env(
                base_url=args.base_url,
                model=args.model,
                reasoning_effort=args.effort,
                timeout_seconds=args.timeout,
                transport=args.transport,
            )
        try:
            result = judge_jobs(
                input_path=input_path,
                output_dir=output,
                profile=config.profile,
                limit=args.limit,
                batch_size=args.batch_size,
                concurrency=args.concurrency,
                selection_mode=args.selection_mode,
                settings=settings,
                dry_run=args.dry_run,
                progress=not args.dry_run,
                max_fallback_ratio=args.max_fallback_ratio,
            )
        except LLMJudgeError as exc:
            print(f"erreur_llm={exc}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(
                f"dry_run=1 offres={len(result['jobs'])} concurrency={result.get('concurrency', 1)} "
                f"output={output / 'llm_payload_preview.json'}"
            )
        else:
            print(f"offres_judgees={result['count']} output={output}")
            print(f"batches={len(result.get('batches', []))}")
            print(f"concurrency={result.get('concurrency', 1)}")
            print(f"transport={result.get('transport', '')} endpoint={result.get('endpoint', '')}")
            print(f"fallback={result.get('fallback_items', 0)}/{result.get('count', 0)} ratio={result.get('fallback_ratio', 0):.3f}")
            print(f"shortlist={output / 'llm_shortlist.md'}")
            print(f"json={output / 'llm_shortlist.json'}")
        return 0
    if args.command == "verify-links":
        config = load_config(args.root)
        input_path = (args.input or (config.output_dir / "jobs.json")).resolve()
        output = (args.output or config.output_dir).resolve()
        shortlist_path = (args.shortlist or (output / "llm_shortlist.json")).resolve()
        result = verify_links(
            input_path=input_path,
            output_dir=output,
            shortlist_path=shortlist_path,
            limit=args.limit,
            timeout_seconds=args.timeout,
            workers=args.workers,
        )
        print(f"liens_verifies={result['checked_count']} output={output}")
        print(f"statuts={json.dumps(result['status_counts'], ensure_ascii=False, sort_keys=True)}")
        print(f"markdown={output / 'link_checks.md'}")
        print(f"json={output / 'link_checks.json'}")
        return 0
    if args.command == "snapshot":
        config = load_config(args.root)
        output = (args.output or config.output_dir).resolve()
        history = (args.history or (config.root / "runs" / "history")).resolve()
        manifest = write_snapshot(output_dir=output, history_dir=history, name=args.name)
        print(f"snapshot={manifest['snapshot_dir']}")
        print(f"fichiers={len(manifest['files'])}")
        print(f"resume={json.dumps(manifest['summary'], ensure_ascii=False, sort_keys=True)}")
        return 0
    if args.command == "sync-history":
        config = load_config(args.root)
        output = (args.output or config.output_dir).resolve()
        history_db = (args.history_db or (config.root / "runs" / "history" / "job_history.sqlite")).resolve()
        result = sync_history(
            output_dir=output,
            history_db=history_db,
            run_name=args.run_name,
            recheck_stale_limit=args.recheck_stale_limit,
            timeout_seconds=args.timeout,
            workers=args.workers,
            profile=config.profile,
        )
        print(f"history_db={result['history_db']}")
        print(f"queue={output / 'application_queue.md'}")
        print(f"messages={output / 'application_messages.md'}")
        print(f"dashboard={output / 'history_dashboard.md'}")
        print(f"digest={output / 'weekly_digest.md'}")
        print(
            "resume="
            + json.dumps(
                {
                    "current_jobs": result["current_jobs"],
                    "known_jobs": result["known_jobs"],
                    "new_jobs": result["new_jobs"],
                    "returned_jobs": result["returned_jobs"],
                    "missing_this_run": result["missing_this_run"],
                    "rechecked_stale": result["rechecked_stale"],
                    "queue_count": result["queue_count"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "graduate-digest":
        config = load_config(args.root)
        input_path = (args.input or (config.output_dir / "jobs.json")).resolve()
        output = (args.output or config.output_dir).resolve()
        jobs = _read_jobs(input_path)
        result = write_graduate_digest(output, jobs, config.profile)
        print(f"graduate={output / 'graduate_programs.md'}")
        print(f"json={output / 'graduate_programs.json'}")
        print(
            "resume="
            + json.dumps(
                {
                    "count": result["count"],
                    "target_count": result["target_count"],
                    "fit_counts": result["fit_counts"],
                    "start_date_counts": result["start_date_counts"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "web":
        config = load_config(args.root, load_env=False)
        run_web_app(
            root=args.root,
            output_dir=(args.output or config.output_dir),
            state_path=args.state_path,
            static_dir=args.static_dir,
            host=args.host,
            port=args.port,
        )
        return 0
    return 2


def _sources_summary(config: dict) -> dict:
    return {
        "public_sources": config.get("public_sources", {}),
        "optional_sources": config.get("optional_sources", {}),
        "ats_feeds": [
            {"name": feed.get("name"), "type": feed.get("type"), "url": feed.get("url")}
            for feed in config.get("ats_feeds", [])
        ],
        "queries": [query.get("term") for query in config.get("queries", [])],
    }


def _read_jobs(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Format jobs invalide dans {path}: liste attendue.")
    return [item for item in data if isinstance(item, dict)]


if __name__ == "__main__":
    sys.exit(main())
