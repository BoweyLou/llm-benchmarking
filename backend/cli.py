from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .banking_review import (
    DEFAULT_BANKING_REVIEW_OUTPUT,
    add_model_to_listing,
    deprecate_listings,
    export_banking_review_list,
    set_review_state,
)
from .catalog_export import (
    build_model_metadata_list,
    render_model_metadata_csv_bundle,
    render_model_metadata_list,
)
from .database import DEFAULT_DB_PATH, get_engine, init_db
from .inference_sync import sync_inference_catalog
from .model_card_audit import build_model_card_audit_summary, format_model_card_audit_summary
from .model_curation import MODEL_CURATION_BASELINE_PATH, export_model_curation_baseline
from .model_licenses import MODEL_LICENSE_BASELINE_PATH
from .recommendation_engine import (
    PROFILE_AUSTRALIAN_BANK,
    SUPPORTED_PROFILES,
    build_recommendation_audit,
    format_recommendation_audit_summary,
    sync_recommendation_proposals,
)
from .seed_data import PROVIDER_ORIGIN_BASELINE_PATH, export_provider_origin_baseline
from .update_engine import (
    bootstrap,
    get_update_log,
    refresh_model_discovery_metadata,
    refresh_model_card_metadata,
    refresh_model_license_metadata,
    run_update_now,
)

DEFAULT_CSV_OUTPUT_PATH = Path("output/model-list.csv")


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
        choices=("json", "jsonl", "csv", "raw-csv"),
        default="json",
        help="Output format. JSON prints one list; JSONL prints one model per line; CSV is spreadsheet-clean; raw-csv preserves nested JSON cells.",
    )
    list_models_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional file path. Omit to write to stdout.",
    )
    list_models_parser.add_argument(
        "--csv-output",
        type=Path,
        default=DEFAULT_CSV_OUTPUT_PATH,
        help=f"Also write a clean model CSV at this path unless --format csv or --no-csv is used. Defaults to {DEFAULT_CSV_OUTPUT_PATH}.",
    )
    list_models_parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Do not write the default CSV sidecar.",
    )
    list_models_parser.add_argument(
        "--no-csv-sidecars",
        action="store_true",
        help="Do not write normalized CSV companion files for scores, approvals, inference destinations, origins, and source freshness.",
    )
    list_models_parser.set_defaults(func=cmd_list_models)

    banking_review_parser = subparsers.add_parser(
        "banking-review",
        help="Export and curate the Australian-bank model review list.",
    )
    banking_review_subparsers = banking_review_parser.add_subparsers(dest="banking_review_command", required=True)

    banking_export_parser = banking_review_subparsers.add_parser(
        "export",
        help="Sync banking recommendation proposals and write a combined model x use-case CSV.",
    )
    banking_export_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_BANKING_REVIEW_OUTPUT,
        help=f"Output CSV path. Defaults to {DEFAULT_BANKING_REVIEW_OUTPUT}.",
    )
    banking_export_parser.add_argument(
        "--profile",
        default=PROFILE_AUSTRALIAN_BANK,
        choices=sorted(SUPPORTED_PROFILES),
        help=f"Recommendation profile. Defaults to {PROFILE_AUSTRALIAN_BANK}.",
    )
    banking_export_parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Do not regenerate recommendation proposals before exporting.",
    )
    banking_export_parser.add_argument(
        "--json",
        action="store_true",
        help="Print export summary as JSON.",
    )
    banking_export_parser.set_defaults(func=cmd_banking_review_export)

    banking_add_parser = banking_review_subparsers.add_parser(
        "add-model",
        help="Add a manually curated model row to the local listing.",
    )
    banking_add_parser.add_argument("--name", required=True, help="Display model name.")
    banking_add_parser.add_argument("--provider", required=True, help="Provider name.")
    banking_add_parser.add_argument("--model-id", help="Optional explicit model id. Defaults to a slug from the name.")
    banking_add_parser.add_argument("--type", default="proprietary", help="Model type. Defaults to proprietary.")
    banking_add_parser.add_argument(
        "--model-role",
        action="append",
        dest="model_roles",
        choices=("generator", "embedding", "reranker", "multimodal_embedding"),
        help="Model role. Repeat for multiple roles. Defaults to generator.",
    )
    banking_add_parser.add_argument(
        "--catalog-status",
        default="tracked",
        choices=("tracked", "provisional", "deprecated"),
        help="Initial listing status. Defaults to tracked.",
    )
    banking_add_parser.add_argument("--notes", help="Optional local curation note.")
    banking_add_parser.add_argument("--json", action="store_true", help="Print result as JSON.")
    banking_add_parser.set_defaults(func=cmd_banking_review_add_model)

    banking_set_parser = banking_review_subparsers.add_parser(
        "set",
        help="Set approval and/or manual recommendation state for models or families.",
    )
    banking_set_target = banking_set_parser.add_mutually_exclusive_group(required=True)
    banking_set_target.add_argument("--model-id", action="append", dest="model_ids", help="Target model id. Repeatable.")
    banking_set_target.add_argument("--family-id", action="append", dest="family_ids", help="Target family id. Repeatable.")
    banking_set_parser.add_argument("--use-case", action="append", dest="use_case_ids", help="Use-case id. Repeatable.")
    banking_set_parser.add_argument("--all-use-cases", action="store_true", help="Apply to every configured use case.")
    banking_set_parser.add_argument(
        "--approval",
        choices=("unchanged", "approved", "not_approved"),
        default="unchanged",
        help="Approval state to write. Defaults to unchanged.",
    )
    banking_set_parser.add_argument(
        "--recommendation",
        choices=("unchanged", "unrated", "recommended", "not_recommended", "discouraged"),
        default="unchanged",
        help="Manual recommendation rating to write. Defaults to unchanged.",
    )
    banking_set_parser.add_argument("--notes", help="Approval note. Existing notes are preserved when omitted.")
    banking_set_parser.add_argument(
        "--recommendation-notes",
        help="Recommendation note. Existing recommendation notes are preserved when omitted.",
    )
    banking_set_parser.add_argument("--json", action="store_true", help="Print result as JSON.")
    banking_set_parser.set_defaults(func=cmd_banking_review_set)

    banking_deprecate_parser = banking_review_subparsers.add_parser(
        "deprecate",
        help="Mark models or families deprecated while keeping them visible in exports.",
    )
    banking_deprecate_target = banking_deprecate_parser.add_mutually_exclusive_group(required=True)
    banking_deprecate_target.add_argument("--model-id", action="append", dest="model_ids", help="Target model id. Repeatable.")
    banking_deprecate_target.add_argument("--family-id", action="append", dest="family_ids", help="Target family id. Repeatable.")
    banking_deprecate_parser.add_argument("--notes", help="Optional deprecation note.")
    banking_deprecate_parser.add_argument(
        "--mark-not-recommended",
        action="store_true",
        help="Also mark selected use cases not_recommended. Defaults to all use cases when no --use-case is provided.",
    )
    banking_deprecate_parser.add_argument("--use-case", action="append", dest="use_case_ids", help="Use-case id for --mark-not-recommended.")
    banking_deprecate_parser.add_argument("--all-use-cases", action="store_true", help="Apply --mark-not-recommended to all use cases.")
    banking_deprecate_parser.add_argument("--json", action="store_true", help="Print result as JSON.")
    banking_deprecate_parser.set_defaults(func=cmd_banking_review_deprecate)

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
    update_parser.add_argument(
        "--refresh-model-discovery",
        action="store_true",
        help="Run curated metadata-only model discovery even when --benchmarks narrows the update.",
    )
    update_parser.set_defaults(func=cmd_update)

    model_discovery_parser = subparsers.add_parser(
        "model-discovery-sync",
        help="Refresh curated metadata-only model discovery from a configured source.",
    )
    model_discovery_parser.add_argument(
        "--source",
        default="configured",
        choices=("configured", "huggingface", "catalog"),
        help="Discovery source to refresh. Defaults to all configured discovery sources.",
    )
    model_discovery_parser.add_argument(
        "--family",
        help="Optional configured model family to refresh, for example gemma.",
    )
    model_discovery_parser.set_defaults(func=cmd_model_discovery_sync)

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

    recommendation_audit_parser = subparsers.add_parser(
        "recommendation-audit",
        help="Generate recommendation proposals without writing them to the database.",
    )
    recommendation_audit_parser.add_argument(
        "--profile",
        default=PROFILE_AUSTRALIAN_BANK,
        choices=sorted(SUPPORTED_PROFILES),
        help=f"Recommendation policy profile. Defaults to {PROFILE_AUSTRALIAN_BANK}.",
    )
    recommendation_audit_parser.add_argument(
        "--use-case",
        dest="use_cases",
        action="append",
        help="Limit the audit to one use-case id. Repeat for multiple use cases.",
    )
    recommendation_audit_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full proposal audit as JSON.",
    )
    recommendation_audit_parser.set_defaults(func=cmd_recommendation_audit)

    recommendation_sync_parser = subparsers.add_parser(
        "recommendation-sync",
        help="Generate and persist recommendation proposals for the current model catalog.",
    )
    recommendation_sync_parser.add_argument(
        "--profile",
        default=PROFILE_AUSTRALIAN_BANK,
        choices=sorted(SUPPORTED_PROFILES),
        help=f"Recommendation policy profile. Defaults to {PROFILE_AUSTRALIAN_BANK}.",
    )
    recommendation_sync_parser.add_argument(
        "--use-case",
        dest="use_cases",
        action="append",
        help="Limit the sync to one use-case id. Repeat for multiple use cases.",
    )
    recommendation_sync_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the persisted summary as JSON.",
    )
    recommendation_sync_parser.set_defaults(func=cmd_recommendation_sync)

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
    sidecar_paths: list[Path] = []

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Exported {len(models)} models to {args.output}")
    else:
        print(rendered, end="")

    if not args.no_csv and args.format != "csv":
        csv_output = Path(args.csv_output)
        csv_output.parent.mkdir(parents=True, exist_ok=True)
        csv_output.write_text(render_model_metadata_list(models, output_format="csv"), encoding="utf-8")
        if not args.no_csv_sidecars:
            sidecar_paths = _write_csv_sidecars(models, csv_output)
        if args.output:
            print(f"Exported CSV sidecar to {csv_output}")
    elif args.format == "csv" and args.output and not args.no_csv_sidecars:
        sidecar_paths = _write_csv_sidecars(models, Path(args.output))

    if args.output and sidecar_paths:
        print(f"Exported {len(sidecar_paths)} CSV companion files next to {sidecar_paths[0].parent}")

    return 0


def _write_csv_sidecars(models: list[dict[str, object]], csv_output: Path) -> list[Path]:
    paths: list[Path] = []
    for suffix, content in render_model_metadata_csv_bundle(models).items():
        sidecar_path = csv_output.with_name(f"{csv_output.stem}-{suffix}{csv_output.suffix}")
        sidecar_path.write_text(content, encoding="utf-8")
        paths.append(sidecar_path)
    return paths


def cmd_banking_review_export(args: argparse.Namespace) -> int:
    summary = export_banking_review_list(
        args.output,
        profile_id=args.profile,
        sync_proposals=not bool(args.skip_sync),
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    else:
        print(
            "Exported banking review CSV:",
            f"models={summary['model_count']}",
            f"rows={summary['review_row_count']}",
            f"path={summary['output_path']}",
        )
        if summary["synced_proposals"]:
            print(f"Stored proposal rows: {summary['stored_proposal_count']}")
    return 0


def cmd_banking_review_add_model(args: argparse.Namespace) -> int:
    result = add_model_to_listing(
        name=args.name,
        provider=args.provider,
        model_id=args.model_id,
        model_type=args.type,
        model_roles=args.model_roles,
        catalog_status=args.catalog_status,
        notes=args.notes,
    )
    _print_banking_review_result(result, json_output=bool(args.json))
    return 0


def cmd_banking_review_set(args: argparse.Namespace) -> int:
    result = set_review_state(
        model_ids=args.model_ids,
        family_ids=args.family_ids,
        use_case_ids=args.use_case_ids,
        all_use_cases=bool(args.all_use_cases),
        approved_for_use=_approval_choice_to_bool(args.approval),
        recommendation_status=None if args.recommendation == "unchanged" else args.recommendation,
        approval_notes=args.notes,
        recommendation_notes=args.recommendation_notes,
    )
    _print_banking_review_result(result, json_output=bool(args.json))
    return 0


def cmd_banking_review_deprecate(args: argparse.Namespace) -> int:
    result = deprecate_listings(
        model_ids=args.model_ids,
        family_ids=args.family_ids,
        notes=args.notes,
        mark_not_recommended=bool(args.mark_not_recommended),
        use_case_ids=args.use_case_ids,
        all_use_cases=bool(args.all_use_cases),
    )
    _print_banking_review_result(result, json_output=bool(args.json))
    return 0


def _approval_choice_to_bool(value: str) -> bool | None:
    if value == "approved":
        return True
    if value == "not_approved":
        return False
    return None


def _print_banking_review_result(result: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


def cmd_update(args: argparse.Namespace) -> int:
    log = run_update_now(
        benchmarks=args.benchmarks,
        triggered_by=args.triggered_by,
        refresh_model_discovery=True if args.refresh_model_discovery else None,
    )
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


def cmd_model_discovery_sync(args: argparse.Namespace) -> int:
    summary = refresh_model_discovery_metadata(source=args.source, family=args.family)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


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


def cmd_recommendation_audit(args: argparse.Namespace) -> int:
    summary = build_recommendation_audit(profile_id=args.profile, use_case_ids=args.use_cases)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    else:
        print(format_recommendation_audit_summary(summary), end="")
    return 0


def cmd_recommendation_sync(args: argparse.Namespace) -> int:
    summary = sync_recommendation_proposals(profile_id=args.profile, use_case_ids=args.use_cases)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    else:
        print(format_recommendation_audit_summary(summary), end="")
        print(f"Stored proposal rows: {summary.get('stored_count', 0)}")
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
