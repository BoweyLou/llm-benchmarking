from __future__ import annotations

import argparse
import json
from typing import Sequence

from .update_engine import bootstrap, get_update_log, run_update_sync


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap the benchmark database and run a full ingest.",
    )
    parser.add_argument(
        "--benchmark",
        dest="benchmarks",
        action="append",
        help="Limit ingestion to a benchmark id. May be repeated.",
    )
    parser.add_argument(
        "--triggered-by",
        default="bootstrap",
        help="Value stored in update_log.triggered_by.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the resulting update log as JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bootstrap()
    log_id = run_update_sync(benchmarks=args.benchmarks, triggered_by=args.triggered_by)
    log = get_update_log(log_id)
    if log is None:
        raise RuntimeError(f"Unable to load update log {log_id} after bootstrap")

    if args.json:
        print(json.dumps(log, indent=2, default=str))
    else:
        print(
            "Bootstrap "
            f'{log["status"]}: '
            f'update_log_id={log_id}, '
            f'scores_added={log["scores_added"]}, '
            f'scores_updated={log["scores_updated"]}'
        )
        audit = log.get("audit_summary")
        if audit:
            print(
                "Audit "
                f'{audit["status"]}: '
                f'blockers={audit["blocker_count"]}, '
                f'warnings={audit["warning_count"]}, '
                f'info={audit["info_count"]}'
            )
    return 1 if log["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
