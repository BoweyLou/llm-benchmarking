from __future__ import annotations

import argparse
import sys

from .database import DEFAULT_DB_PATH
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
