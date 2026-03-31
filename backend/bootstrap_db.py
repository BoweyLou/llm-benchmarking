from __future__ import annotations

import argparse
import json
from typing import Sequence

from .update_engine import bootstrap, run_update_sync


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
    if args.json:
        print(json.dumps({"log_id": log_id, "status": "completed"}, indent=2))
    else:
        print(f"Bootstrap complete: update_log_id={log_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
