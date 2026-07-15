"""Backend-only catalog export helpers."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable, Literal

from .update_engine import list_models

CatalogOutputFormat = Literal["json", "jsonl", "csv", "raw-csv"]

CSV_SIDECAR_SUFFIXES = {
    "scores": "scores",
    "suggested_use_cases": "suggested-use-cases",
    "use_case_approvals": "use-case-approvals",
    "inference_destinations": "inference-destinations",
    "pricing_offers": "pricing-offers",
    "provider_origin_countries": "provider-origin-countries",
    "source_freshness": "source-freshness",
    "source_listings": "source-listings",
}

MODEL_CSV_BASE_FIELDS = [
    "id",
    "name",
    "provider_id",
    "provider",
    "provider_country_code",
    "provider_country_name",
    "provider_country_flag",
    "provider_origin_basis",
    "provider_origin_source_url",
    "provider_origin_verified_at",
    "type",
    "catalog_status",
    "release_date",
    "release_date_precision",
    "release_date_confidence",
    "release_date_source_name",
    "release_date_source_url",
    "release_date_verified_at",
    "model_age_days",
    "model_age_basis",
    "model_age_confidence",
    "model_age_source_name",
    "model_age_source_url",
    "model_age_reference_date",
    "context_window",
    "context_window_tokens",
    "max_output_tokens",
    "parameter_count_b",
    "active_parameter_count_b",
    "model_size_class",
    "small_model_candidate",
    "model_size_source_name",
    "model_size_source_url",
    "model_size_verified_at",
    "price_input_per_mtok",
    "price_output_per_mtok",
    "openrouter_model_id",
    "openrouter_canonical_slug",
    "openrouter_added_at",
    "huggingface_repo_id",
    "huggingface_created_at",
    "huggingface_last_modified_at",
    "metadata_source_name",
    "metadata_source_url",
    "metadata_verified_at",
    "model_card_url",
    "model_card_source",
    "model_card_verified_at",
    "documentation_url",
    "repo_url",
    "paper_url",
    "license_id",
    "license_name",
    "license_url",
    "license_policy_class",
    "license_policy_label",
    "license_policy_note",
    "potential_legal_review",
    "commercial_use_blocked",
    "provenance_policy_class",
    "provenance_policy_label",
    "provenance_policy_note",
    "derivative_model",
    "potential_provenance_review",
    "production_provenance_blocked",
    "intended_use_short",
    "limitations_short",
    "training_data_summary",
    "training_cutoff",
    "openrouter_global_rank",
    "openrouter_global_total_tokens",
    "openrouter_global_share",
    "openrouter_global_change_ratio",
    "openrouter_global_request_count",
    "openrouter_programming_rank",
    "openrouter_programming_total_tokens",
    "openrouter_programming_volume",
    "openrouter_programming_request_count",
    "market_source_name",
    "market_source_url",
    "market_verified_at",
    "family_id",
    "family_name",
    "canonical_model_id",
    "canonical_model_name",
    "variant_label",
    "discovered_at",
    "discovered_update_log_id",
    "general_approved_for_use",
    "general_approval_notes",
    "general_approval_updated_at",
    "general_recommendation_status",
    "general_recommendation_notes",
    "general_recommendation_updated_at",
    "reasoning_effort_ceiling",
    "restricted_modes",
    "usage_policy_notes",
    "usage_policy_updated_at",
    "approved_for_use",
    "approval_use_case_count",
    "approval_notes",
    "approval_updated_at",
    "active",
]

MODEL_CSV_SUMMARY_FIELDS = [
    "model_roles",
    "provider_origin_country_codes",
    "provider_origin_country_names",
    "base_model_ids",
    "base_model_names",
    "supported_language_codes",
    "supported_language_names",
    "capability_ids",
    "capability_names",
    "provenance_gap_field_names",
    "inference_destination_count",
    "inference_platform_names",
    "inference_region_count",
    "inference_region_names",
    "inference_deployment_modes",
    "score_count",
    "verified_score_count",
    "benchmark_ids_with_scores",
    "comparable_score_count",
    "limited_score_count",
    "leading_score_count",
    "missing_relevant_benchmark_count",
    "suggested_use_case_count",
    "suggested_use_case_ids",
    "use_case_approval_count",
    "approved_use_case_ids",
    "recommended_use_case_ids",
    "not_recommended_use_case_ids",
    "discouraged_use_case_ids",
    "restricted_use_case_ids",
    "auto_not_recommended_use_case_ids",
    "source_freshness_source_count",
    "source_freshness_degraded_source_ids",
    "source_freshness_stale_source_ids",
    "source_freshness_missing_source_ids",
]

NESTED_MODEL_FIELDS = {
    "provider_origin_countries",
    "base_models",
    "supported_languages",
    "capabilities",
    "provenance_gap_fields",
    "use_case_approvals",
    "suggested_use_cases",
    "inference_destinations",
    "inference_summary",
    "scores",
    "score_configurations",
    "source_freshness",
    "source_listings",
}

SCORE_CSV_FIELDS = [
    "model_id",
    "model_name",
    "provider",
    "benchmark_id",
    "value",
    "raw_value",
    "collected_at",
    "source_url",
    "source_type",
    "verified",
    "notes",
    "confidence_lower",
    "confidence_upper",
    "variance",
    "vote_count",
    "observation_count",
    "session_count",
    "rank",
    "category",
    "publication_date",
    "methodology",
    "source_listing_status",
    "style_control",
    "preliminary",
    "source_metadata",
    "variant_model_id",
    "variant_model_name",
    "configuration_key",
    "configuration_value",
    "display_value",
    "display_formatted",
    "display_unit",
    "display_precision",
    "display_direction",
    "display_direction_label",
    "comparison_status",
    "strict_rank",
    "strict_tie_count",
    "strict_cohort_size",
    "strict_percentile",
    "strict_cohort_label",
    "strict_position_band",
    "strict_min",
    "strict_p10",
    "strict_p25",
    "strict_median",
    "strict_p75",
    "strict_p90",
    "strict_max",
    "broad_rank",
    "broad_tie_count",
    "broad_cohort_size",
    "broad_percentile",
    "broad_cohort_label",
    "broad_position_band",
    "broad_min",
    "broad_p10",
    "broad_p25",
    "broad_median",
    "broad_p75",
    "broad_p90",
    "broad_max",
    "coverage_scored_count",
    "coverage_eligible_count",
    "coverage_percent",
    "coverage_label",
    "evidence_count",
    "evidence_unit",
    "evidence_label",
    "comparison_warnings",
    "comparison_as_of",
    "contributor_model_id",
    "contributor_model_name",
]

SOURCE_LISTING_CSV_FIELDS = [
    "model_id",
    "model_name",
    "provider",
    "source_name",
    "benchmark_id",
    "raw_model_name",
    "raw_model_key",
    "listing_status",
    "source_revision",
    "publication_date",
    "first_seen_at",
    "last_seen_at",
    "metadata",
]

SUGGESTED_USE_CASE_CSV_FIELDS = [
    "model_id",
    "model_name",
    "provider",
    "use_case_id",
    "label",
    "description",
    "fit_score",
    "confidence",
    "reasons",
    "warnings",
    "required_controls",
    "policy_version",
    "computed_at",
]

USE_CASE_APPROVAL_CSV_FIELDS = [
    "model_id",
    "model_name",
    "provider",
    "use_case_id",
    "approved_for_use",
    "approval_notes",
    "approval_updated_at",
    "recommendation_status",
    "recommendation_notes",
    "recommendation_updated_at",
    "auto_recommendation_status",
    "auto_recommendation_notes",
    "auto_not_recommended_member_count",
    "approval_member_count",
    "approval_total_count",
    "recommended_member_count",
    "not_recommended_member_count",
    "discouraged_member_count",
    "restricted_member_count",
    "proposed_recommendation_status",
    "proposed_recommendation_score",
    "proposed_recommendation_confidence",
    "proposed_recommendation_blockers",
    "proposed_recommendation_warnings",
    "proposed_recommendation_reasons",
    "proposed_recommendation_required_controls",
    "proposed_recommendation_policy_version",
    "proposed_recommendation_computed_at",
    "inference_route_approval_count",
    "approved_inference_route_count",
]

INFERENCE_DESTINATION_CSV_FIELDS = [
    "model_id",
    "model_name",
    "provider",
    "destination_id",
    "destination_name",
    "hyperscaler",
    "availability_scope",
    "availability_note",
    "location_scope",
    "region_count",
    "regions",
    "deployment_modes",
    "pricing_label",
    "pricing_note",
    "sources",
]

PRICING_OFFER_CSV_FIELDS = [
    "model_id", "model_name", "provider", "destination_id", "destination_name",
    "offer_id", "provider_model_id", "service_tier", "region", "currency",
    "price_status", "constraints", "modality", "charge_type", "amount",
    "billing_unit", "unit_quantity", "conditions", "source_kind", "source_label",
    "source_url", "verified_at", "stale",
]

PROVIDER_ORIGIN_COUNTRY_CSV_FIELDS = [
    "model_id",
    "model_name",
    "provider_id",
    "provider",
    "country_code",
    "country_name",
    "provider_origin_basis",
    "provider_origin_source_url",
    "provider_origin_verified_at",
]

SOURCE_FRESHNESS_CSV_FIELDS = [
    "model_id",
    "model_name",
    "provider",
    "source_name",
    "source_label",
    "benchmark_ids",
    "model_benchmark_ids",
    "latest_source_status",
    "latest_attempted_at",
    "latest_success_at",
    "latest_failure_at",
    "latest_error",
    "latest_model_score_at",
    "latest_model_raw_record_at",
    "has_model_score",
    "has_model_raw_record",
    "model_evidence_status",
    "degraded",
    "stale",
    "missing_because_source_failed",
]


def build_model_metadata_list() -> list[dict[str, Any]]:
    """Return the active model catalog with all serialized metadata."""
    return list_models()


def render_model_metadata_list(
    models: list[dict[str, Any]],
    *,
    output_format: CatalogOutputFormat = "json",
) -> str:
    if output_format == "json":
        return json.dumps(models, indent=2, sort_keys=True, default=str) + "\n"

    if output_format == "jsonl":
        if not models:
            return ""
        return "\n".join(json.dumps(model, sort_keys=True, default=str) for model in models) + "\n"

    if output_format == "csv":
        return _render_clean_csv(models)

    if output_format == "raw-csv":
        return _render_raw_csv(models)

    raise ValueError(f"Unsupported model metadata output format: {output_format}")


def render_model_metadata_csv_bundle(models: list[dict[str, Any]]) -> dict[str, str]:
    """Return normalized sidecar CSV files for nested model metadata."""
    return {
        CSV_SIDECAR_SUFFIXES["scores"]: _render_csv_rows(SCORE_CSV_FIELDS, _score_rows(models)),
        CSV_SIDECAR_SUFFIXES["suggested_use_cases"]: _render_csv_rows(
            SUGGESTED_USE_CASE_CSV_FIELDS,
            _suggested_use_case_rows(models),
        ),
        CSV_SIDECAR_SUFFIXES["use_case_approvals"]: _render_csv_rows(
            USE_CASE_APPROVAL_CSV_FIELDS,
            _use_case_approval_rows(models),
        ),
        CSV_SIDECAR_SUFFIXES["inference_destinations"]: _render_csv_rows(
            INFERENCE_DESTINATION_CSV_FIELDS,
            _inference_destination_rows(models),
        ),
        CSV_SIDECAR_SUFFIXES["pricing_offers"]: _render_csv_rows(
            PRICING_OFFER_CSV_FIELDS,
            _pricing_offer_rows(models),
        ),
        CSV_SIDECAR_SUFFIXES["provider_origin_countries"]: _render_csv_rows(
            PROVIDER_ORIGIN_COUNTRY_CSV_FIELDS,
            _provider_origin_country_rows(models),
        ),
        CSV_SIDECAR_SUFFIXES["source_freshness"]: _render_csv_rows(
            SOURCE_FRESHNESS_CSV_FIELDS,
            _source_freshness_rows(models),
        ),
        CSV_SIDECAR_SUFFIXES["source_listings"]: _render_csv_rows(
            SOURCE_LISTING_CSV_FIELDS,
            _source_listing_rows(models),
        ),
    }


def _render_clean_csv(models: list[dict[str, Any]]) -> str:
    fieldnames = _clean_csv_fieldnames(models)
    rows = [_clean_model_csv_row(model, fieldnames) for model in models]
    return _render_csv_rows(fieldnames, rows)


def _render_raw_csv(models: list[dict[str, Any]]) -> str:
    if not models:
        return ""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_raw_csv_fieldnames(models), extrasaction="ignore")
    writer.writeheader()
    for model in models:
        writer.writerow({key: _raw_csv_value(value) for key, value in model.items()})
    return output.getvalue()


def _render_csv_rows(fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _clean_csv_value(row.get(field)) for field in fieldnames})
    return output.getvalue()


def _clean_csv_fieldnames(models: list[dict[str, Any]]) -> list[str]:
    fieldnames: list[str] = []
    seen: set[str] = set()

    for field in [*MODEL_CSV_BASE_FIELDS, *MODEL_CSV_SUMMARY_FIELDS]:
        _add_field(fieldnames, seen, field)

    for model in models:
        for key, value in model.items():
            if key in NESTED_MODEL_FIELDS or key in seen or not _is_scalar_value(value):
                continue
            _add_field(fieldnames, seen, key)

    return fieldnames


def _clean_model_csv_row(model: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    row = {field: model.get(field) for field in fieldnames}
    row.update(_model_summary_columns(model))
    return row


_DERIVED_SCORE_FIELDS = {
    "benchmark_id",
    "display",
    "evidence",
    "comparison",
    "variant_model_id",
    "variant_model_name",
}


def _score_observation_key(benchmark_id: str, score: dict[str, Any]) -> tuple[str, str]:
    """Identify one stored observation while ignoring its additive presentation."""
    source_payload = {
        key: value
        for key, value in score.items()
        if key not in _DERIVED_SCORE_FIELDS
    }
    return (
        benchmark_id,
        json.dumps(source_payload, ensure_ascii=True, sort_keys=True, default=str),
    )


def _deduplicated_score_entries(model: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return base and configured observations once, preserving distinct signatures."""
    entries: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    scores = model.get("scores") if isinstance(model.get("scores"), dict) else {}
    candidates: list[tuple[str, dict[str, Any]]] = [
        (str(benchmark_id), score)
        for benchmark_id, score in sorted(scores.items(), key=lambda item: str(item[0]))
        if isinstance(score, dict)
    ]
    candidates.extend(
        (str(score.get("benchmark_id") or ""), score)
        for score in _as_list(model.get("score_configurations"))
        if isinstance(score, dict) and str(score.get("benchmark_id") or "").strip()
    )
    for benchmark_id, score in candidates:
        key = _score_observation_key(benchmark_id, score)
        if key in seen:
            continue
        seen.add(key)
        entries.append((benchmark_id, score))
    return entries


def _model_summary_columns(model: dict[str, Any]) -> dict[str, Any]:
    provider_origins = _as_list(model.get("provider_origin_countries"))
    base_models = _as_list(model.get("base_models"))
    supported_languages = _as_list(model.get("supported_languages"))
    capabilities = _as_list(model.get("capabilities"))
    provenance_gap_fields = _as_list(model.get("provenance_gap_fields"))
    inference_destinations = _as_list(model.get("inference_destinations"))
    inference_summary = model.get("inference_summary") if isinstance(model.get("inference_summary"), dict) else {}
    use_case_approvals = model.get("use_case_approvals") if isinstance(model.get("use_case_approvals"), dict) else {}
    suggested_use_cases = _as_list(model.get("suggested_use_cases"))
    source_freshness = _as_list(model.get("source_freshness"))

    score_entries = _deduplicated_score_entries(model)
    comparison_scores = [score for _, score in score_entries]
    comparison_statuses = [
        str((score.get("comparison") or {}).get("status") or "").strip().lower()
        for score in comparison_scores
        if isinstance(score.get("comparison"), dict)
    ]
    relevant_benchmark_ids = {
        str(benchmark_id)
        for benchmark_id in _as_list(model.get("relevant_benchmark_ids"))
        if str(benchmark_id).strip()
    }
    present_benchmark_ids = {benchmark_id for benchmark_id, _ in score_entries}

    return {
        "model_roles": _join_values(model.get("model_roles")),
        "provider_origin_country_codes": _join_values(_item_values(provider_origins, "code")),
        "provider_origin_country_names": _join_values(_item_values(provider_origins, "name")),
        "base_model_ids": _join_values(_item_values(base_models, "id", "model_id")),
        "base_model_names": _join_values(_item_values(base_models, "name", "model_name")),
        "supported_language_codes": _join_values(_item_values(supported_languages, "code", "id")),
        "supported_language_names": _join_values(_item_values(supported_languages, "name")),
        "capability_ids": _join_values(_item_values(capabilities, "id")),
        "capability_names": _join_values(_item_values(capabilities, "name", "label")),
        "provenance_gap_field_names": _join_values(provenance_gap_fields),
        "inference_destination_count": inference_summary.get("destination_count")
        if inference_summary
        else len(inference_destinations),
        "inference_platform_names": _join_values(
            inference_summary.get("platform_names")
            if inference_summary
            else _item_values(inference_destinations, "name")
        ),
        "inference_region_count": inference_summary.get("region_count") if inference_summary else _region_count(inference_destinations),
        "inference_region_names": _join_values(_flatten_item_values(inference_destinations, "regions")),
        "inference_deployment_modes": _join_values(
            inference_summary.get("deployment_modes")
            if inference_summary
            else _flatten_item_values(inference_destinations, "deployment_modes")
        ),
        "score_count": len(score_entries),
        "verified_score_count": sum(1 for score in comparison_scores if bool(score.get("verified"))),
        "benchmark_ids_with_scores": _join_values(sorted(present_benchmark_ids)),
        "comparable_score_count": comparison_statuses.count("comparable"),
        "limited_score_count": comparison_statuses.count("limited"),
        "leading_score_count": sum(
            1
            for score in comparison_scores
            if str(
                (((score.get("comparison") or {}).get("strict") or {}).get("band")
                or ((score.get("comparison") or {}).get("strict") or {}).get("position_band")
                or "")
            ).strip().lower()
            == "leading"
        ),
        "missing_relevant_benchmark_count": sum(
            1 for benchmark_id in relevant_benchmark_ids if benchmark_id not in present_benchmark_ids
        ),
        "suggested_use_case_count": len(suggested_use_cases),
        "suggested_use_case_ids": _join_values(
            [suggestion.get("use_case_id")
            for suggestion in suggested_use_cases
            if isinstance(suggestion, dict)]
        ),
        "use_case_approval_count": len(use_case_approvals),
        "approved_use_case_ids": _approval_ids(use_case_approvals, "approved_for_use", True),
        "recommended_use_case_ids": _approval_ids(use_case_approvals, "recommendation_status", "recommended"),
        "not_recommended_use_case_ids": _approval_ids(use_case_approvals, "recommendation_status", "not_recommended"),
        "discouraged_use_case_ids": _approval_ids(use_case_approvals, "recommendation_status", "discouraged"),
        "restricted_use_case_ids": _approval_ids(use_case_approvals, "recommendation_status", "restricted"),
        "auto_not_recommended_use_case_ids": _approval_ids(use_case_approvals, "auto_recommendation_status", "not_recommended"),
        "source_freshness_source_count": len(source_freshness),
        "source_freshness_degraded_source_ids": _source_freshness_ids(source_freshness, "degraded", True),
        "source_freshness_stale_source_ids": _source_freshness_ids(source_freshness, "stale", True),
        "source_freshness_missing_source_ids": _source_freshness_ids(
            source_freshness,
            "model_evidence_status",
            "missing",
        ),
    }


def _score_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        for benchmark_id, score in _deduplicated_score_entries(model):
            score_row = {
                "model_id": model.get("id"),
                "model_name": model.get("name"),
                "provider": model.get("provider"),
                "benchmark_id": benchmark_id,
                **score,
                **_score_comparison_columns(score),
            }
            score_row["source_metadata"] = json.dumps(score.get("source_metadata") or {}, sort_keys=True)
            rows.append(score_row)
    return rows


def _score_comparison_columns(score: dict[str, Any]) -> dict[str, Any]:
    """Flatten the additive display/comparison contract for score sidecars."""
    display = score.get("display") if isinstance(score.get("display"), dict) else {}
    comparison = score.get("comparison") if isinstance(score.get("comparison"), dict) else {}
    strict = comparison.get("strict") if isinstance(comparison.get("strict"), dict) else {}
    broad = comparison.get("broad") if isinstance(comparison.get("broad"), dict) else {}
    coverage = comparison.get("coverage") if isinstance(comparison.get("coverage"), dict) else {}
    evidence = comparison.get("evidence") if isinstance(comparison.get("evidence"), dict) else {}
    if not evidence and isinstance(score.get("evidence"), dict):
        evidence = score["evidence"]

    scored_count = _first_present(coverage, "scored_count", "scored_model_count", "valid_scored_count")
    eligible_count = _first_present(coverage, "eligible_count", "eligible_model_count", "active_model_count")
    coverage_percent = _first_present(coverage, "percent", "coverage_percent")
    if coverage_percent is None and scored_count is not None and eligible_count:
        coverage_percent = round(float(scored_count) / float(eligible_count) * 100.0, 1)

    evidence_count = _first_present(evidence, "count", "observation_count")
    if evidence_count is None:
        evidence_count = score.get("observation_count")
    evidence_unit = _first_present(evidence, "unit", "count_unit")
    evidence_label = evidence.get("label")

    return {
        "display_value": display.get("value"),
        "display_formatted": display.get("formatted") or display.get("label"),
        "display_unit": display.get("unit"),
        "display_precision": display.get("precision"),
        "display_direction": display.get("direction"),
        "display_direction_label": display.get("direction_label"),
        "comparison_status": comparison.get("status"),
        **_position_columns("strict", strict),
        **_position_columns("broad", broad),
        "coverage_scored_count": scored_count,
        "coverage_eligible_count": eligible_count,
        "coverage_percent": coverage_percent,
        "coverage_label": coverage.get("label"),
        "evidence_count": evidence_count,
        "evidence_unit": evidence_unit,
        "evidence_label": evidence_label,
        "comparison_warnings": _join_values(comparison.get("warnings")),
        "comparison_as_of": comparison.get("as_of"),
        "contributor_model_id": comparison.get("contributor_model_id")
        or comparison.get("selected_contributor_model_id"),
        "contributor_model_name": comparison.get("contributor_model_name")
        or comparison.get("selected_contributor_model_name"),
    }


def _position_columns(prefix: str, position: dict[str, Any]) -> dict[str, Any]:
    distribution = position.get("distribution") if isinstance(position.get("distribution"), dict) else {}
    return {
        f"{prefix}_rank": position.get("rank"),
        f"{prefix}_tie_count": position.get("tie_count"),
        f"{prefix}_cohort_size": position.get("cohort_size"),
        f"{prefix}_percentile": position.get("percentile"),
        f"{prefix}_cohort_label": position.get("cohort_label") or position.get("label"),
        f"{prefix}_position_band": position.get("position_band") or position.get("band"),
        **{
            f"{prefix}_{quantile}": _first_present(distribution, quantile, f"{quantile}_value")
            for quantile in ("min", "p10", "p25", "median", "p75", "p90", "max")
        },
    }


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _suggested_use_case_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        for suggestion in _as_list(model.get("suggested_use_cases")):
            if not isinstance(suggestion, dict):
                continue
            rows.append(
                {
                    "model_id": model.get("id"),
                    "model_name": model.get("name"),
                    "provider": model.get("provider"),
                    **suggestion,
                    "reasons": _join_values(suggestion.get("reasons")),
                    "warnings": _join_values(suggestion.get("warnings")),
                    "required_controls": _join_values(suggestion.get("required_controls")),
                }
            )
    return rows


def _source_listing_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        for listing in _as_list(model.get("source_listings")):
            if not isinstance(listing, dict):
                continue
            rows.append(
                {
                    "model_id": model.get("id"),
                    "model_name": model.get("name"),
                    "provider": model.get("provider"),
                    **listing,
                    "metadata": json.dumps(listing.get("metadata") or {}, sort_keys=True),
                }
            )
    return rows


def _use_case_approval_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        approvals = model.get("use_case_approvals") if isinstance(model.get("use_case_approvals"), dict) else {}
        for use_case_id, approval in sorted(approvals.items(), key=lambda item: str(item[0])):
            if not isinstance(approval, dict):
                continue
            route_approvals = [
                entry
                for entry in _as_list(approval.get("inference_route_approvals"))
                if isinstance(entry, dict)
            ]
            rows.append(
                {
                    "model_id": model.get("id"),
                    "model_name": model.get("name"),
                    "provider": model.get("provider"),
                    "use_case_id": approval.get("use_case_id") or use_case_id,
                    **approval,
                    "proposed_recommendation_blockers": _join_values(approval.get("proposed_recommendation_blockers")),
                    "proposed_recommendation_warnings": _join_values(approval.get("proposed_recommendation_warnings")),
                    "proposed_recommendation_reasons": _join_values(approval.get("proposed_recommendation_reasons")),
                    "proposed_recommendation_required_controls": _join_values(
                        approval.get("proposed_recommendation_required_controls")
                    ),
                    "inference_route_approval_count": len(route_approvals),
                    "approved_inference_route_count": sum(
                        1 for entry in route_approvals if bool(entry.get("approved_for_use"))
                    ),
                }
            )
    return rows


def _inference_destination_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        for destination in _as_list(model.get("inference_destinations")):
            if not isinstance(destination, dict):
                continue
            rows.append(
                {
                    "model_id": model.get("id"),
                    "model_name": model.get("name"),
                    "provider": model.get("provider"),
                    "destination_id": destination.get("id"),
                    "destination_name": destination.get("name"),
                    "hyperscaler": destination.get("hyperscaler"),
                    "availability_scope": destination.get("availability_scope"),
                    "availability_note": destination.get("availability_note"),
                    "location_scope": destination.get("location_scope"),
                    "region_count": destination.get("region_count"),
                    "regions": _join_values(destination.get("regions")),
                    "deployment_modes": _join_values(destination.get("deployment_modes")),
                    "pricing_label": destination.get("pricing_label"),
                    "pricing_note": destination.get("pricing_note"),
                    "sources": _join_values(_source_labels(destination.get("sources"))),
                }
            )
    return rows


def _pricing_offer_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        for destination in _as_list(model.get("inference_destinations")):
            if not isinstance(destination, dict):
                continue
            for offer in _as_list(destination.get("pricing_offers")):
                if not isinstance(offer, dict):
                    continue
                provenance = offer.get("provenance") if isinstance(offer.get("provenance"), dict) else {}
                components = [item for item in _as_list(offer.get("components")) if isinstance(item, dict)] or [{}]
                for component in components:
                    rows.append(
                        {
                            "model_id": model.get("id"), "model_name": model.get("name"), "provider": model.get("provider"),
                            "destination_id": destination.get("id"), "destination_name": destination.get("name"),
                            "offer_id": offer.get("id"), "provider_model_id": offer.get("provider_model_id"),
                            "service_tier": offer.get("service_tier"), "region": offer.get("region"),
                            "currency": offer.get("currency"), "price_status": offer.get("price_status"),
                            "constraints": offer.get("constraints"), "modality": component.get("modality"),
                            "charge_type": component.get("charge_type"), "amount": component.get("amount"),
                            "billing_unit": component.get("billing_unit"), "unit_quantity": component.get("unit_quantity"),
                            "conditions": component.get("conditions"), "source_kind": provenance.get("kind"),
                            "source_label": provenance.get("label"), "source_url": provenance.get("url"),
                            "verified_at": provenance.get("verified_at"), "stale": provenance.get("stale"),
                        }
                    )
    return rows


def _provider_origin_country_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        for country in _as_list(model.get("provider_origin_countries")):
            if isinstance(country, dict):
                country_code = country.get("code")
                country_name = country.get("name")
            else:
                country_code = None
                country_name = country
            rows.append(
                {
                    "model_id": model.get("id"),
                    "model_name": model.get("name"),
                    "provider_id": model.get("provider_id"),
                    "provider": model.get("provider"),
                    "country_code": country_code,
                    "country_name": country_name,
                    "provider_origin_basis": model.get("provider_origin_basis"),
                    "provider_origin_source_url": model.get("provider_origin_source_url"),
                    "provider_origin_verified_at": model.get("provider_origin_verified_at"),
                }
            )
    return rows


def _source_freshness_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        for source in _as_list(model.get("source_freshness")):
            if not isinstance(source, dict):
                continue
            rows.append(
                {
                    "model_id": model.get("id"),
                    "model_name": model.get("name"),
                    "provider": model.get("provider"),
                    "source_name": source.get("source_name"),
                    "source_label": source.get("source_label"),
                    "benchmark_ids": _join_values(source.get("benchmark_ids")),
                    "model_benchmark_ids": _join_values(source.get("model_benchmark_ids")),
                    "latest_source_status": source.get("latest_source_status"),
                    "latest_attempted_at": source.get("latest_attempted_at"),
                    "latest_success_at": source.get("latest_success_at"),
                    "latest_failure_at": source.get("latest_failure_at"),
                    "latest_error": source.get("latest_error"),
                    "latest_model_score_at": source.get("latest_model_score_at"),
                    "latest_model_raw_record_at": source.get("latest_model_raw_record_at"),
                    "has_model_score": source.get("has_model_score"),
                    "has_model_raw_record": source.get("has_model_raw_record"),
                    "model_evidence_status": source.get("model_evidence_status"),
                    "degraded": source.get("degraded"),
                    "stale": source.get("stale"),
                    "missing_because_source_failed": source.get("missing_because_source_failed"),
                }
            )
    return rows


def _raw_csv_fieldnames(models: list[dict[str, Any]]) -> list[str]:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for model in models:
        for key in model:
            _add_field(fieldnames, seen, key)
    return fieldnames


def _add_field(fieldnames: list[str], seen: set[str], field: str) -> None:
    if field not in seen:
        seen.add(field)
        fieldnames.append(field)


def _is_scalar_value(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _clean_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return _join_values(value)
    if isinstance(value, dict):
        return ""
    return str(value)


def _raw_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value, key=str)
    return [value]


def _join_values(values: Any) -> str:
    items: list[str] = []
    for value in _as_list(values):
        if value is None:
            continue
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, dict):
            text = _first_text_value(value, ("name", "label", "id", "code", "url"))
        else:
            text = str(value)
        text = text.strip()
        if text and text not in items:
            items.append(text)
    return "; ".join(items)


def _item_values(items: Iterable[Any], *keys: str) -> list[Any]:
    values: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            values.append(_first_text_value(item, keys))
        else:
            values.append(item)
    return [value for value in values if value not in (None, "")]


def _flatten_item_values(items: Iterable[Any], key: str) -> list[Any]:
    values: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            values.extend(_as_list(item.get(key)))
    return values


def _first_text_value(item: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _region_count(destinations: list[Any]) -> int:
    regions = {
        str(region)
        for region in _flatten_item_values(destinations, "regions")
        if str(region).strip()
    }
    return len(regions)


def _approval_ids(approvals: dict[str, Any], field: str, expected: Any) -> str:
    ids = [
        str(use_case_id)
        for use_case_id, approval in approvals.items()
        if isinstance(approval, dict) and approval.get(field) == expected
    ]
    return _join_values(sorted(ids))


def _source_freshness_ids(entries: list[Any], field: str, expected: Any) -> str:
    ids = [
        str(entry.get("source_name"))
        for entry in entries
        if isinstance(entry, dict) and entry.get(field) == expected and entry.get("source_name")
    ]
    return _join_values(sorted(ids))


def _source_labels(sources: Any) -> list[str]:
    labels: list[str] = []
    for source in _as_list(sources):
        if isinstance(source, dict):
            label = str(source.get("label") or "").strip()
            url = str(source.get("url") or "").strip()
            if label and url:
                labels.append(f"{label}: {url}")
            elif label:
                labels.append(label)
            elif url:
                labels.append(url)
        elif source is not None:
            labels.append(str(source))
    return labels
