"""Server entry point and explicit, operator-run collection commands."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

REPORTS_KEPT = 30


def serve() -> None:
    parser = argparse.ArgumentParser(prog="claude-academy-api")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(os.getenv("CLAUDE_ACADEMY_SNAPSHOT_PATH", "data/snapshot.json")),
    )
    parser.add_argument("--frontend-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    import uvicorn

    from .app import create_app

    uvicorn.run(
        create_app(args.snapshot, args.frontend_dir),
        host=args.host,
        port=args.port,
        log_level="info",
        server_header=False,
        proxy_headers=False,
    )


def _write_report(state_dir: Path, report: dict) -> Path:
    from .storage import atomic_json

    runs = state_dir / "runs"
    path = runs / f"{report['startedAt'].replace(':', '').replace('-', '')}.json"
    atomic_json(path, report)
    for old in sorted(runs.glob("*.json"))[:-REPORTS_KEPT]:
        old.unlink(missing_ok=True)
    return path


def _run(args, parser) -> int:
    import fcntl

    from .collector import collect
    from .edge import PurgeError, purge_from_environment
    from .fetch import USER_AGENT, Fetcher
    from .models import CollectionArtifact
    from .storage import SnapshotStore, SnapshotUnavailable, now

    purge = purge_from_environment()  # Checked before any request is sent.
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (args.state_dir / "collector.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.exit(1, "Another collection run is in progress\n")
    store = SnapshotStore(args.snapshot)
    try:
        previous = store.read()
    except SnapshotUnavailable:
        previous = None
    fetcher = Fetcher(interval=args.interval, max_requests=args.max_requests)
    report: dict = {
        "startedAt": now().isoformat().replace("+00:00", "Z"),
        "userAgent": USER_AGENT,
        "previousSnapshotId": previous.snapshot_id if previous else None,
    }

    def fail(exc: Exception) -> None:
        report.update(state="failed", error=f"{type(exc).__name__}: {exc}"[:2000])
        report["receipts"] = [r.as_dict() for r in fetcher.receipts]
        path = _write_report(args.state_dir, report)
        parser.exit(1, f"Collection failed; snapshot unchanged. Report: {path}\n")

    try:
        outcome = collect(fetcher, previous, max_resources=args.max_resources)
        artifact = CollectionArtifact.model_validate_json(json.dumps(outcome.artifact))
    except Exception as exc:
        store.record_attempt(success=False, code="collection-failed")
        fail(exc)
    try:
        snapshot = store.publish_artifact(artifact, method="crawler", merge=False)
    except Exception as exc:  # Publication records its own failed attempt.
        fail(exc)
    edge = None
    if purge is not None and snapshot.snapshot_id != report["previousSnapshotId"]:
        try:
            edge = {"hostname": purge.hostname, "state": "accepted", "purgeId": purge()}
        except PurgeError as exc:
            edge = {"hostname": purge.hostname, "state": "failed", "error": str(exc)}
    summary = {
        "state": "published",
        "snapshotId": snapshot.snapshot_id,
        "resources": len(snapshot.resources),
        "byKind": dict(sorted(Counter(r.kind for r in snapshot.resources).items())),
        "pagesRead": len(outcome.pages),
        "retained": len(outcome.retained),
        "failed": len(outcome.failed),
        "skippedByRobots": len(outcome.skipped),
        "requests": fetcher.requests,
        "edgePurge": edge,
    }
    report.update(
        summary,
        finishedAt=now().isoformat().replace("+00:00", "Z"),
        failedPages=outcome.failed,
        skippedPages=outcome.skipped,
        retainedPages=outcome.retained,
        warnings=outcome.warnings,
        receipts=[r.as_dict() for r in fetcher.receipts],
    )
    summary["report"] = str(_write_report(args.state_dir, report))
    print(json.dumps(summary, indent=2))
    if edge and edge["state"] == "failed":
        parser.exit(
            3,
            "Snapshot published, but the Cloudflare cache purge failed. Retry only the purge "
            "with: claude-academy-collector purge-cache --live\n",
        )
    return 0


def collect() -> None:
    parser = argparse.ArgumentParser(prog="claude-academy-collector")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(os.getenv("CLAUDE_ACADEMY_SNAPSHOT_PATH", "data/snapshot.json")),
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.getenv("CLAUDE_ACADEMY_COLLECTOR_STATE", "data/collector")),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Read the public site once and publish a snapshot")
    run.add_argument("--live", action="store_true", required=True)
    run.add_argument("--interval", type=float, default=1.1, help="Seconds between requests")
    run.add_argument("--max-requests", type=int, default=1000)
    run.add_argument("--max-resources", type=int, default=2000)
    discover = commands.add_parser("discover", help="Read robots.txt and the sitemap only")
    discover.add_argument("--live", action="store_true", required=True)
    parse = commands.add_parser("parse", help="Parse one saved page offline")
    parse.add_argument("html", type=Path)
    parse.add_argument("--url", required=True)
    purge_cache = commands.add_parser("purge-cache")
    purge_cache.add_argument("--live", action="store_true", required=True)
    for name in ("validate", "validate-snapshot", "import"):
        cmd = commands.add_parser(name)
        cmd.add_argument("artifact", type=Path)
        if name == "import":
            cmd.add_argument("--method", choices=["manual", "fixture"], default="manual")
    args = parser.parse_args()

    from .models import CollectionArtifact, Snapshot
    from .storage import SnapshotStore, bounded_json

    try:
        if args.command == "run":
            if args.interval < 1.0:
                raise ValueError("--interval must be at least 1 second")
            _run(args, parser)
        elif args.command == "discover":
            from .collector import SITEMAP_URL, resource_queue, sitemap_urls
            from .fetch import USER_AGENT, Fetcher
            from .security import resource_kind

            fetcher = Fetcher()
            fetcher.load_robots()
            urls = sitemap_urls(fetcher.get(SITEMAP_URL).body)
            queue = resource_queue(urls)
            blocked = [u for u in queue if not fetcher.allowed(u)]
            print(
                json.dumps(
                    {
                        "userAgent": USER_AGENT,
                        "sitemapUrls": len(urls),
                        "resourcePages": dict(Counter(resource_kind(u) for u in queue)),
                        "disallowedByRobots": blocked,
                        "requests": fetcher.requests,
                    },
                    indent=2,
                )
            )
        elif args.command == "parse":
            from dataclasses import asdict

            from .parse import parse_page

            page = parse_page(args.url, bounded_json(args.html).decode("utf-8", "replace"))
            print(json.dumps(asdict(page) | {"tags": page.tags}, indent=2, ensure_ascii=False))
        elif args.command == "purge-cache":
            from .edge import PurgeError, purge_from_environment

            purge = purge_from_environment()
            if purge is None:
                raise ValueError("Cloudflare purge settings are missing from the environment")
            try:
                purge_id = purge()
            except PurgeError as exc:
                parser.exit(1, f"Cache purge failed: {exc}\n")
            print(
                json.dumps(
                    {"hostname": purge.hostname, "state": "accepted", "purgeId": purge_id},
                    indent=2,
                )
            )
        elif args.command == "validate-snapshot":
            snapshot = Snapshot.model_validate_json(bounded_json(args.artifact))
            print(
                json.dumps(
                    {
                        "valid": True,
                        "resources": len(snapshot.resources),
                        "snapshotId": snapshot.snapshot_id,
                    }
                )
            )
        elif args.command == "validate":
            artifact = CollectionArtifact.model_validate_json(bounded_json(args.artifact))
            print(json.dumps({"valid": True, "resources": len(artifact.resources)}))
        else:
            result = SnapshotStore(args.snapshot).publish(args.artifact, method=args.method)
            print(
                json.dumps({"snapshotId": result.snapshot_id, "resources": len(result.resources)})
            )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Collection failed: {exc}\n")
