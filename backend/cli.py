from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .database import DEFAULT_DB_PATH, get_engine
from .inference_sync import sync_inference_catalog
from .seed_data import PROVIDER_ORIGIN_BASELINE_PATH, export_provider_origin_baseline
from .update_engine import bootstrap, get_update_log, run_update_now


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM Benchmarking backend utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Create schema and seed reference data.")
    bootstrap_parser.set_defaults(func=cmd_bootstrap)

    update_parser = subparsers.add_parser("update", help="Run a synchronous benchmark update.")
    update_parser.add_argument(
        "--benchmarks",
        nargs="+",
        help="Optional benchmark ids to update. Example: gpqa_diamond mmmu terminal_bench",
    )
    update_parser.add_argument(
        "--triggered-by",
        default="cli",
        choices=("manual", "api", "scheduled", "bootstrap", "cli"),
        help="Write a source label into update_log.triggered_by.",
    )
    update_parser.set_defaults(func=cmd_update)

    inference_parser = subparsers.add_parser(
        "inference-sync",
        help="Sync hyperscaler inference destinations from official cloud APIs.",
    )
    inference_parser.add_argument(
        "--destinations",
        nargs="+",
        choices=("aws-bedrock", "azure-ai-foundry", "google-vertex-ai"),
        help="Optional subset of hyperscaler destinations to sync.",
    )
    inference_parser.set_defaults(func=cmd_inference_sync)

    provider_origin_parser = subparsers.add_parser(
        "provider-origin-export",
        help="Export current provider-origin metadata into the tracked repo baseline.",
    )
    provider_origin_parser.add_argument(
        "--path",
        default=str(PROVIDER_ORIGIN_BASELINE_PATH),
        help="Optional output path. Defaults to the canonical baseline JSON in backend/.",
    )
    provider_origin_parser.set_defaults(func=cmd_provider_origin_export)

    return parser


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    bootstrap()
    print(f"Bootstrapped database schema and seed data at {DEFAULT_DB_PATH}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    log = run_update_now(benchmarks=args.benchmarks, triggered_by=args.triggered_by)
    audit = log.get("audit_summary") or {}
    errors = log.get("errors") or []

    print(
        "Update complete:",
        f"log_id={log['id']}",
        f"status={log['status']}",
        f"scores_added={log['scores_added']}",
        f"scores_updated={log['scores_updated']}",
        f"audit={audit.get('status', 'missing')}",
    )
    if errors:
        print("Errors:")
        for error in errors:
            print(f"- {error}")

    return 0 if log["status"] == "completed" else 1


def cmd_inference_sync(args: argparse.Namespace) -> int:
    bootstrap()
    summary = sync_inference_catalog(destination_ids=args.destinations)
    print(json.dumps(summary, indent=2, sort_keys=True))
    statuses = [item.get("status") for item in summary.get("destinations", {}).values()]
    return 0 if statuses and all(status != "failed" for status in statuses) else 1


def cmd_provider_origin_export(args: argparse.Namespace) -> int:
    bootstrap()
    output_path = export_provider_origin_baseline(get_engine(), Path(args.path))
    print(f"Exported provider-origin baseline to {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
