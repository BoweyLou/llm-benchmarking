from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .catalog_export import build_model_metadata_list, render_model_metadata_list
from .database import DEFAULT_DB_PATH, get_engine, init_db
from .inference_sync import sync_inference_catalog
from .model_card_audit import build_model_card_audit_summary, format_model_card_audit_summary
from .model_curation import MODEL_CURATION_BASELINE_PATH, export_model_curation_baseline
from .model_licenses import MODEL_LICENSE_BASELINE_PATH
from .seed_data import PROVIDER_ORIGIN_BASELINE_PATH, export_provider_origin_baseline
from .update_engine import (
    bootstrap,
    get_update_log,
    refresh_model_card_metadata,
    refresh_model_license_metadata,
    run_update_now,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM Benchmarking backend utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Create schema and seed reference data.")
    bootstrap_parser.set_defaults(func=cmd_bootstrap)

    list_models_parser = subparsers.add_parser(
        "list-models",
        help="Print or export the active model list with all serialized metadata.",
    )
    list_models_parser.add_argument(
        "--format",
        choices=("json", "jsonl"),
        default="json",
        help="Output format. JSON prints one list; JSONL prints one model per line.",
    )
    list_models_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional file path. Omit to write to stdout.",
    )
    list_models_parser.set_defaults(func=cmd_list_models)

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

    model_card_parser = subparsers.add_parser(
        "model-card-sync",
        help="Refresh Hugging Face-backed model card metadata for models that have a linked repo id.",
    )
    model_card_parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh even recently verified model-card rows.",
    )
    model_card_parser.set_defaults(func=cmd_model_card_sync)

    model_card_audit_parser = subparsers.add_parser(
        "model-card-audit",
        help="Summarize model-card coverage gaps, derivative provenance blockers, and extraction-quality issues.",
    )
    model_card_audit_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the audit summary as JSON.",
    )
    model_card_audit_parser.set_defaults(func=cmd_model_card_audit)

    model_license_parser = subparsers.add_parser(
        "model-license-sync",
        help="Refresh model license metadata using inferred rules, tracked overrides, and optional model-card refresh.",
    )
    model_license_parser.add_argument(
        "--refresh-model-cards",
        action="store_true",
        help="Refresh Hugging Face-backed model cards before applying license inference and overrides.",
    )
    model_license_parser.add_argument(
        "--force-model-cards",
        action="store_true",
        help="Force-refresh model cards when --refresh-model-cards is set.",
    )
    model_license_parser.set_defaults(func=cmd_model_license_sync)

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

    model_curation_parser = subparsers.add_parser(
        "model-curation-export",
        help="Export current model curation overrides into the tracked repo baseline.",
    )
    model_curation_parser.add_argument(
        "--path",
        default=str(MODEL_CURATION_BASELINE_PATH),
        help="Optional output path. Defaults to the canonical baseline JSON in backend/.",
    )
    model_curation_parser.set_defaults(func=cmd_model_curation_export)

    return parser


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    bootstrap()
    print(f"Bootstrapped database schema and seed data at {DEFAULT_DB_PATH}")
    return 0


def cmd_list_models(args: argparse.Namespace) -> int:
    models = build_model_metadata_list()
    rendered = render_model_metadata_list(models, output_format=args.format)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Exported {len(models)} models to {args.output}")
        return 0

    print(rendered, end="")
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


def cmd_model_card_sync(args: argparse.Namespace) -> int:
    refresh_model_card_metadata(force=bool(args.force))
    print("Refreshed model-card metadata")
    return 0


def cmd_model_card_audit(args: argparse.Namespace) -> int:
    engine = init_db(get_engine())
    summary = build_model_card_audit_summary(engine)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(format_model_card_audit_summary(summary))
    return 0


def cmd_model_license_sync(args: argparse.Namespace) -> int:
    summary = refresh_model_license_metadata(
        refresh_model_cards=bool(args.refresh_model_cards),
        force_model_cards=bool(args.force_model_cards),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Tracked license baseline: {MODEL_LICENSE_BASELINE_PATH}")
    return 0


def cmd_provider_origin_export(args: argparse.Namespace) -> int:
    bootstrap()
    output_path = export_provider_origin_baseline(get_engine(), Path(args.path))
    print(f"Exported provider-origin baseline to {output_path}")
    return 0


def cmd_model_curation_export(args: argparse.Namespace) -> int:
    bootstrap()
    output_path = export_model_curation_baseline(get_engine(), Path(args.path))
    print(f"Exported model curation baseline to {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
