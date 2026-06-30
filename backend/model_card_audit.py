from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Connection, Engine

from .database import get_connection

FIELD_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("release_date", "Release date", "text"),
    ("context_window", "Context window", "text"),
    ("context_window_tokens", "Context window tokens", "text"),
    ("max_output_tokens", "Max output tokens", "text"),
    ("price_input_per_mtok", "Input price", "text"),
    ("price_output_per_mtok", "Output price", "text"),
    ("huggingface_repo_id", "Hugging Face repo id", "text"),
    ("metadata_source_name", "Metadata source", "text"),
    ("metadata_source_url", "Metadata source URL", "text"),
    ("metadata_verified_at", "Metadata verified at", "text"),
    ("model_card_url", "Model card URL", "text"),
    ("model_card_source", "Model card source", "text"),
    ("model_card_verified_at", "Model card verified at", "text"),
    ("documentation_url", "Documentation URL", "text"),
    ("repo_url", "Repository URL", "text"),
    ("paper_url", "Paper URL", "text"),
    ("license_id", "License id", "text"),
    ("license_name", "License name", "text"),
    ("license_url", "License URL", "text"),
    ("base_models_json", "Base models", "json_list"),
    ("supported_languages_json", "Supported languages", "json_list"),
    ("capabilities_json", "Capabilities", "json_list"),
    ("intended_use_short", "Intended use", "text"),
    ("limitations_short", "Limitations", "text"),
    ("training_data_summary", "Training data summary", "text"),
    ("training_cutoff", "Training cutoff", "text"),
)

GAP_DEFINITIONS: tuple[tuple[str, str], ...] = (
    (
        "models_without_license",
        "COALESCE(TRIM(license_id), '') = '' AND COALESCE(TRIM(license_name), '') = ''",
    ),
    (
        "proprietary_models_without_license",
        "type = 'proprietary' AND COALESCE(TRIM(license_id), '') = '' AND COALESCE(TRIM(license_name), '') = ''",
    ),
    (
        "open_weight_models_without_license",
        "type = 'open_weights' AND COALESCE(TRIM(license_id), '') = '' AND COALESCE(TRIM(license_name), '') = ''",
    ),
    (
        "models_with_generic_license_marker",
        "LOWER(COALESCE(TRIM(license_id), '')) IN ('other', 'unknown') AND COALESCE(TRIM(license_name), '') = ''",
    ),
    (
        "models_with_license_but_no_license_url",
        "(COALESCE(TRIM(license_id), '') != '' OR COALESCE(TRIM(license_name), '') != '') AND "
        "COALESCE(TRIM(license_url), '') = ''",
    ),
    (
        "models_without_any_model_metadata",
        "COALESCE(TRIM(metadata_source_name), '') = '' AND COALESCE(TRIM(model_card_url), '') = ''",
    ),
    (
        "huggingface_repo_without_model_card_url",
        "COALESCE(TRIM(huggingface_repo_id), '') != '' AND COALESCE(TRIM(model_card_url), '') = ''",
    ),
    (
        "model_card_without_rich_text_sections",
        "COALESCE(TRIM(model_card_url), '') != '' AND "
        "COALESCE(TRIM(intended_use_short), '') = '' AND "
        "COALESCE(TRIM(limitations_short), '') = '' AND "
        "COALESCE(TRIM(training_data_summary), '') = '' AND "
        "COALESCE(TRIM(training_cutoff), '') = ''",
    ),
    (
        "huggingface_repo_without_rich_text_sections",
        "COALESCE(TRIM(huggingface_repo_id), '') != '' AND "
        "COALESCE(TRIM(intended_use_short), '') = '' AND "
        "COALESCE(TRIM(limitations_short), '') = '' AND "
        "COALESCE(TRIM(training_data_summary), '') = '' AND "
        "COALESCE(TRIM(training_cutoff), '') = ''",
    ),
    (
        "model_card_without_license",
        "COALESCE(TRIM(model_card_url), '') != '' AND "
        "COALESCE(TRIM(license_id), '') = '' AND "
        "COALESCE(TRIM(license_name), '') = ''",
    ),
    (
        "model_card_without_external_links",
        "COALESCE(TRIM(model_card_url), '') != '' AND "
        "COALESCE(TRIM(documentation_url), '') = '' AND "
        "COALESCE(TRIM(repo_url), '') = '' AND "
        "COALESCE(TRIM(paper_url), '') = ''",
    ),
    (
        "model_card_without_base_models_or_languages",
        "COALESCE(TRIM(model_card_url), '') != '' AND "
        "COALESCE(base_models_json, '[]') = '[]' AND "
        "COALESCE(supported_languages_json, '[]') = '[]'",
    ),
)

SUSPICIOUS_VALUE_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("intended_use_contains_code_fence", "intended_use_short LIKE '%```%'"),
    ("intended_use_contains_markdown_rule", "intended_use_short LIKE '%---%'"),
    ("intended_use_mentions_hugging_face_badges", "intended_use_short LIKE '%Hugging Face%'"),
    (
        "intended_use_contains_raw_urls",
        "intended_use_short LIKE '%http://%' OR intended_use_short LIKE '%https://%'",
    ),
    ("training_data_contains_code_fence", "training_data_summary LIKE '%```%'"),
    (
        "repo_url_points_to_non_repo_asset",
        "repo_url LIKE '%.pdf%' OR "
        "repo_url LIKE '%raw=true%' OR "
        "repo_url LIKE '%.jpeg%' OR "
        "repo_url LIKE '%.jpg%' OR "
        "repo_url LIKE '%.png%'",
    ),
    (
        "documentation_url_points_to_code_file",
        "documentation_url LIKE '%Dockerfile%' OR "
        "documentation_url LIKE '%.py%' OR "
        "documentation_url LIKE '%.ipynb%'",
    ),
)

SUSPICIOUS_EXAMPLE_WHERE = (
    "repo_url LIKE '%.pdf%' OR "
    "repo_url LIKE '%raw=true%' OR "
    "repo_url LIKE '%.jpeg%' OR "
    "repo_url LIKE '%.jpg%' OR "
    "repo_url LIKE '%.png%' OR "
    "documentation_url LIKE '%Dockerfile%' OR "
    "documentation_url LIKE '%.py%' OR "
    "documentation_url LIKE '%.ipynb%' OR "
    "intended_use_short LIKE '%```%' OR "
    "intended_use_short LIKE '%---%' OR "
    "intended_use_short LIKE '%Hugging Face%' OR "
    "intended_use_short LIKE '%http://%' OR "
    "intended_use_short LIKE '%https://%' OR "
    "training_data_summary LIKE '%```%'"
)


def build_model_card_audit_summary(target: Connection | Engine) -> dict[str, Any]:
    if isinstance(target, Engine):
        with get_connection(target) as conn:
            return build_model_card_audit_summary(conn)

    active_model_count = _count_where(target, "1 = 1")
    summary = {
        "active_model_count": active_model_count,
        "field_coverage": _build_field_coverage(target, active_model_count),
        "metadata_source_counts": _count_by_value(target, "metadata_source_name"),
        "model_card_source_counts": _count_by_value(target, "model_card_source"),
        "coverage_by_type": _build_coverage_by_type(target),
        "gap_counts": {name: _count_where(target, clause) for name, clause in GAP_DEFINITIONS},
        "derivative_provenance": _build_derivative_provenance_summary(target),
        "suspicious_value_counts": {
            name: _count_where(target, clause) for name, clause in SUSPICIOUS_VALUE_DEFINITIONS
        },
        "suspicious_examples": _load_suspicious_examples(target),
    }
    return summary


def format_model_card_audit_summary(summary: dict[str, Any]) -> str:
    lines = [f"Active models: {int(summary.get('active_model_count') or 0)}", ""]

    lines.append("Field coverage:")
    for field in summary.get("field_coverage", []):
        lines.append(
            f"- {field['label']}: {field['filled_count']}/{field['total_count']} "
            f"({field['coverage_pct']:.1f}%)"
        )

    lines.append("")
    lines.append("Source coverage:")
    lines.extend(_format_count_map("Metadata source", summary.get("metadata_source_counts", {})))
    lines.extend(_format_count_map("Model card source", summary.get("model_card_source_counts", {})))

    lines.append("")
    lines.append("Coverage by type:")
    for entry in summary.get("coverage_by_type", []):
        lines.append(
            f"- {entry['type']}: total={entry['total']} hf_repo={entry['hf_repo']} "
            f"model_card={entry['model_card']} capabilities={entry['capabilities']} "
            f"intended_use={entry['intended_use']} limitations={entry['limitations']}"
        )

    lines.append("")
    lines.append("Gap counts:")
    for name, _clause in GAP_DEFINITIONS:
        lines.append(f"- {name}: {int(summary.get('gap_counts', {}).get(name) or 0)}")

    derivative_provenance = summary.get("derivative_provenance", {})
    lines.append("")
    lines.append("Derivative provenance:")
    lines.append(f"- derivative_models: {int(derivative_provenance.get('derivative_models') or 0)}")
    lines.append(f"- review_only: {int(derivative_provenance.get('review_only') or 0)}")
    lines.append(f"- production_blocked: {int(derivative_provenance.get('production_blocked') or 0)}")
    lines.append(f"- unknown_provider: {int(derivative_provenance.get('unknown_provider') or 0)}")
    lines.append(f"- missing_model_card: {int(derivative_provenance.get('missing_model_card') or 0)}")
    lines.append(f"- missing_training_data_summary: {int(derivative_provenance.get('missing_training_data_summary') or 0)}")

    lines.append("")
    lines.append("Suspicious value counts:")
    for name, _clause in SUSPICIOUS_VALUE_DEFINITIONS:
        lines.append(f"- {name}: {int(summary.get('suspicious_value_counts', {}).get(name) or 0)}")

    examples = summary.get("suspicious_examples", [])
    if examples:
        lines.append("")
        lines.append("Suspicious examples:")
        for example in examples:
            lines.append(
                f"- {example['name']} [{example['provider']}]: "
                f"documentation={example.get('documentation_url') or '-'} | "
                f"repo={example.get('repo_url') or '-'} | "
                f"paper={example.get('paper_url') or '-'}"
            )

    return "\n".join(lines)


def _build_field_coverage(conn: Connection, total_count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field_name, label, field_kind in FIELD_DEFINITIONS:
        if field_kind == "json_list":
            clause = f"COALESCE({field_name}, '[]') != '[]'"
        else:
            clause = f"{field_name} IS NOT NULL AND TRIM(CAST({field_name} AS TEXT)) != ''"
        filled_count = _count_where(conn, clause)
        coverage_pct = (filled_count / total_count * 100.0) if total_count else 0.0
        rows.append(
            {
                "field": field_name,
                "label": label,
                "filled_count": filled_count,
                "missing_count": max(total_count - filled_count, 0),
                "total_count": total_count,
                "coverage_pct": round(coverage_pct, 1),
            }
        )
    return rows


def _build_coverage_by_type(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.exec_driver_sql(
        """
        SELECT
            type,
            COUNT(*) AS total,
            SUM(CASE WHEN COALESCE(TRIM(huggingface_repo_id), '') != '' THEN 1 ELSE 0 END) AS hf_repo,
            SUM(CASE WHEN COALESCE(TRIM(model_card_url), '') != '' THEN 1 ELSE 0 END) AS model_card,
            SUM(CASE WHEN COALESCE(capabilities_json, '[]') != '[]' THEN 1 ELSE 0 END) AS capabilities,
            SUM(CASE WHEN COALESCE(TRIM(intended_use_short), '') != '' THEN 1 ELSE 0 END) AS intended_use,
            SUM(CASE WHEN COALESCE(TRIM(limitations_short), '') != '' THEN 1 ELSE 0 END) AS limitations
        FROM models
        WHERE active = 1
        GROUP BY type
        ORDER BY total DESC, type ASC
        """
    ).mappings()
    return [dict(row) for row in rows]


def _build_derivative_provenance_summary(conn: Connection) -> dict[str, int]:
    derivative_where = "active = 1 AND COALESCE(base_models_json, '[]') != '[]'"
    unknown_provider_where = f"{derivative_where} AND COALESCE(TRIM(provider), '') = 'Unknown'"
    missing_model_card_where = f"{derivative_where} AND COALESCE(TRIM(model_card_url), '') = ''"
    missing_training_summary_where = f"{derivative_where} AND COALESCE(TRIM(training_data_summary), '') = ''"
    production_blocked_where = (
        f"{derivative_where} AND ("
        "COALESCE(TRIM(provider), '') = 'Unknown' OR "
        "COALESCE(TRIM(model_card_url), '') = '' OR "
        "COALESCE(TRIM(training_data_summary), '') = ''"
        ")"
    )
    derivative_models = _count_where(conn, derivative_where)
    production_blocked = _count_where(conn, production_blocked_where)
    return {
        "derivative_models": derivative_models,
        "review_only": max(derivative_models - production_blocked, 0),
        "production_blocked": production_blocked,
        "unknown_provider": _count_where(conn, unknown_provider_where),
        "missing_model_card": _count_where(conn, missing_model_card_where),
        "missing_training_data_summary": _count_where(conn, missing_training_summary_where),
    }


def _count_by_value(conn: Connection, column_name: str) -> dict[str, int]:
    rows = conn.exec_driver_sql(
        f"""
        SELECT COALESCE(NULLIF(TRIM({column_name}), ''), '<null>') AS value, COUNT(*) AS total
        FROM models
        WHERE active = 1
        GROUP BY 1
        ORDER BY total DESC, value ASC
        """
    ).mappings()
    return {str(row["value"]): int(row["total"]) for row in rows}


def _load_suspicious_examples(conn: Connection, *, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.exec_driver_sql(
        f"""
        SELECT
            name,
            provider,
            documentation_url,
            repo_url,
            paper_url
        FROM models
        WHERE active = 1
          AND ({SUSPICIOUS_EXAMPLE_WHERE})
        ORDER BY name ASC
        LIMIT :limit
        """,
        {"limit": limit},
    ).mappings()
    return [dict(row) for row in rows]


def _count_where(conn: Connection, clause: str) -> int:
    row = conn.exec_driver_sql(
        f"SELECT COUNT(*) AS total FROM models WHERE active = 1 AND ({clause})"
    ).mappings().first()
    return int(row["total"]) if row is not None else 0


def _format_count_map(label: str, values: dict[str, int]) -> list[str]:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    if not ordered:
        return [f"- {label}: <none>"]
    return [f"- {label} `{name}`: {count}" for name, count in ordered]


__all__ = [
    "build_model_card_audit_summary",
    "format_model_card_audit_summary",
]
