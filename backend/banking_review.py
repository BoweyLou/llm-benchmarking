"""Local banking-review utilities for model-list export and curation."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from . import update_engine
from .catalog_export import (
    build_model_metadata_list,
    render_model_metadata_csv_bundle,
    render_model_metadata_list,
)
from .database import (
    fetch_all,
    fetch_one,
    get_connection,
    models as models_table,
    providers as providers_table,
)
from .model_taxonomy import infer_model_identity
from .recommendation_engine import PROFILE_AUSTRALIAN_BANK, sync_recommendation_proposals
from .seed_data import canonical_provider_name, provider_id_from_name

CATALOG_STATUS_TRACKED = "tracked"
CATALOG_STATUS_PROVISIONAL = "provisional"
CATALOG_STATUS_DEPRECATED = "deprecated"
VALID_CATALOG_STATUSES = {
    CATALOG_STATUS_TRACKED,
    CATALOG_STATUS_PROVISIONAL,
    CATALOG_STATUS_DEPRECATED,
}
VALID_MODEL_ROLES = {"generator", "embedding", "reranker", "multimodal_embedding", "speech_to_text", "text_to_speech"}
VALID_RECOMMENDATION_STATUSES = {"unrated", "recommended", "not_recommended", "discouraged", "restricted"}

DEFAULT_BANKING_REVIEW_OUTPUT = Path("output/banking-model-list-with-recommendations.csv")

REVIEW_LEADING_FIELDS = [
    "model_id",
    "model_name",
    "provider",
    "family_id",
    "family_name",
    "canonical_model_id",
    "canonical_model_name",
    "catalog_status",
    "active",
    "use_case_id",
    "approved_for_use",
    "recommendation_status",
    "proposed_recommendation_status",
    "proposed_recommendation_score",
    "proposed_recommendation_confidence",
    "proposed_recommendation_blockers",
    "proposed_recommendation_warnings",
    "proposed_recommendation_required_controls",
    "approval_notes",
    "recommendation_notes",
]


def export_banking_review_list(
    output_path: Path = DEFAULT_BANKING_REVIEW_OUTPUT,
    *,
    profile_id: str = PROFILE_AUSTRALIAN_BANK,
    sync_proposals: bool = True,
) -> dict[str, Any]:
    """Write a combined model x use-case CSV for banking review."""
    sync_summary: dict[str, Any] | None = None
    if sync_proposals:
        sync_summary = sync_recommendation_proposals(profile_id=profile_id)

    models = build_model_metadata_list()
    rendered = render_banking_review_csv(models)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    review_row_count = _csv_data_row_count(rendered)
    return {
        "profile_id": profile_id,
        "synced_proposals": bool(sync_proposals),
        "stored_proposal_count": int((sync_summary or {}).get("stored_count") or 0),
        "model_count": len(models),
        "review_row_count": review_row_count,
        "output_path": str(output_path),
    }


def render_banking_review_csv(models: list[dict[str, Any]]) -> str:
    """Return a combined model x use-case CSV using the normalized export contract."""
    model_reader = csv.DictReader(io.StringIO(render_model_metadata_list(models, output_format="csv")))
    model_rows = list(model_reader)
    approval_reader = csv.DictReader(
        io.StringIO(render_model_metadata_csv_bundle(models)["use-case-approvals"])
    )
    approval_rows = list(approval_reader)

    model_rows_by_id = {str(row.get("id") or ""): row for row in model_rows}
    rows: list[dict[str, str]] = []
    for approval in approval_rows:
        model_id = str(approval.get("model_id") or "")
        model_row = model_rows_by_id.get(model_id, {})
        rows.append(_combined_review_row(model_row, approval))

    if not rows:
        for model_row in model_rows:
            rows.append(_combined_review_row(model_row, {}))

    fieldnames = _review_fieldnames(
        model_reader.fieldnames or [],
        approval_reader.fieldnames or [],
        rows,
    )
    return _render_csv(fieldnames, rows)


def add_model_to_listing(
    *,
    name: str,
    provider: str,
    model_id: str | None = None,
    model_type: str = "proprietary",
    model_roles: Iterable[str] | None = None,
    catalog_status: str = CATALOG_STATUS_TRACKED,
    notes: str | None = None,
) -> dict[str, Any]:
    """Add a manually curated model row to the local listing."""
    update_engine.bootstrap()
    cleaned_name = _required_text(name, "name")
    cleaned_provider = canonical_provider_name(_required_text(provider, "provider"))
    normalized_status = _validate_catalog_status(catalog_status)
    normalized_roles = _normalise_model_roles(model_roles)
    normalized_model_id = _normalise_model_id(model_id) if model_id else _available_model_id(cleaned_name)
    provider_id = provider_id_from_name(cleaned_provider)
    identity = infer_model_identity(cleaned_name, cleaned_provider, normalized_model_id)

    with update_engine.ENGINE.begin() as conn:
        existing = fetch_one(conn, select(models_table.c.id).where(models_table.c.id == normalized_model_id))
        if existing is not None:
            raise ValueError(f"Model already exists: {normalized_model_id}")

        provider_stmt = sqlite_insert(providers_table).values(
            id=provider_id,
            name=cleaned_provider,
            active=1,
        )
        provider_stmt = provider_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"name": provider_stmt.excluded.name, "active": 1},
        )
        conn.execute(provider_stmt)

        conn.execute(
            models_table.insert().values(
                id=normalized_model_id,
                name=cleaned_name,
                provider_id=provider_id,
                provider=cleaned_provider,
                type=_clean_text(model_type) or "proprietary",
                model_roles_json=json.dumps(normalized_roles, ensure_ascii=True),
                catalog_status=normalized_status,
                family_id=identity.family_id,
                family_name=identity.family_name,
                canonical_model_id=identity.canonical_model_id,
                canonical_model_name=identity.canonical_model_name,
                variant_label=identity.variant_label,
                metadata_source_name="manual",
                intended_use_short=_clean_text(notes),
                active=1,
            )
        )

    model = _model_by_id(normalized_model_id)
    if model is None:
        raise ValueError(f"Added model could not be loaded: {normalized_model_id}")
    return {
        "model_id": normalized_model_id,
        "model_name": model.get("name"),
        "provider": model.get("provider"),
        "family_id": model.get("family_id"),
        "family_name": model.get("family_name"),
        "catalog_status": model.get("catalog_status"),
    }


def set_review_state(
    *,
    model_ids: Iterable[str] | None = None,
    family_ids: Iterable[str] | None = None,
    use_case_ids: Iterable[str] | None = None,
    all_use_cases: bool = False,
    approved_for_use: bool | None = None,
    recommendation_status: str | None = None,
    approval_notes: str | None = None,
    recommendation_notes: str | None = None,
) -> dict[str, Any]:
    """Set approval and/or manual recommendation state for models or families."""
    normalized_recommendation_status = (
        _validate_recommendation_status(recommendation_status)
        if recommendation_status is not None
        else None
    )
    if (
        approved_for_use is None
        and normalized_recommendation_status is None
        and approval_notes is None
        and recommendation_notes is None
    ):
        raise ValueError("Choose at least one review field to change.")

    target_model_ids = _resolve_target_model_ids(model_ids=model_ids, family_ids=family_ids)
    resolved_use_case_ids = _resolve_use_case_ids(use_case_ids, all_use_cases=all_use_cases)
    current_models = {str(model["id"]): model for model in build_model_metadata_list() if str(model.get("id")) in target_model_ids}

    updates: list[dict[str, Any]] = []
    for model_id in target_model_ids:
        model = current_models.get(model_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        approvals = model.get("use_case_approvals") if isinstance(model.get("use_case_approvals"), dict) else {}
        for use_case_id in resolved_use_case_ids:
            existing = approvals.get(use_case_id, {}) if isinstance(approvals.get(use_case_id), dict) else {}
            next_approved = bool(existing.get("approved_for_use")) if approved_for_use is None else bool(approved_for_use)
            next_approval_notes = (
                _clean_text(approval_notes)
                if approval_notes is not None
                else _clean_text(existing.get("approval_notes"))
            )
            display_recommendation_status = normalized_recommendation_status or str(
                existing.get("recommendation_status") or "unrated"
            )
            updated = update_engine.update_model_use_case_approval(
                model_id,
                use_case_id,
                next_approved,
                next_approval_notes,
                normalized_recommendation_status,
                _clean_text(recommendation_notes) if recommendation_notes is not None else None,
            )
            if updated is None:
                raise ValueError(f"Model not found: {model_id}")
            updates.append(
                {
                    "model_id": model_id,
                    "use_case_id": use_case_id,
                    "approved_for_use": next_approved,
                    "recommendation_status": display_recommendation_status,
                }
            )

    return {
        "target_model_count": len(target_model_ids),
        "use_case_count": len(resolved_use_case_ids),
        "updated_count": len(updates),
        "updated_model_ids": target_model_ids,
        "use_case_ids": resolved_use_case_ids,
    }


def deprecate_listings(
    *,
    model_ids: Iterable[str] | None = None,
    family_ids: Iterable[str] | None = None,
    notes: str | None = None,
    mark_not_recommended: bool = False,
    use_case_ids: Iterable[str] | None = None,
    all_use_cases: bool = False,
) -> dict[str, Any]:
    """Mark models or whole families as deprecated while keeping them in exports."""
    target_model_ids = _resolve_target_model_ids(model_ids=model_ids, family_ids=family_ids)
    cleaned_notes = _clean_text(notes)
    with update_engine.ENGINE.begin() as conn:
        conn.execute(
            update(models_table)
            .where(models_table.c.id.in_(target_model_ids))
            .values(catalog_status=CATALOG_STATUS_DEPRECATED, approval_notes=cleaned_notes)
        )

    recommendation_summary = None
    if mark_not_recommended:
        recommendation_summary = set_review_state(
            model_ids=target_model_ids,
            use_case_ids=use_case_ids,
            all_use_cases=all_use_cases or not list(use_case_ids or []),
            recommendation_status="not_recommended",
            recommendation_notes=cleaned_notes or "Deprecated listing.",
        )

    return {
        "deprecated_count": len(target_model_ids),
        "deprecated_model_ids": target_model_ids,
        "catalog_status": CATALOG_STATUS_DEPRECATED,
        "not_recommended_updates": recommendation_summary,
    }


def _combined_review_row(model_row: dict[str, str], approval_row: dict[str, str]) -> dict[str, str]:
    row = dict(model_row)
    row.update(approval_row)
    row.setdefault("model_id", model_row.get("id", ""))
    row.setdefault("model_name", model_row.get("name", ""))
    row.setdefault("provider", model_row.get("provider", ""))
    return row


def _review_fieldnames(
    model_fieldnames: list[str],
    approval_fieldnames: list[str],
    rows: list[dict[str, str]],
) -> list[str]:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for field in REVIEW_LEADING_FIELDS:
        _add_field(fieldnames, seen, field)
    for field in model_fieldnames:
        _add_field(fieldnames, seen, field)
    for field in approval_fieldnames:
        _add_field(fieldnames, seen, field)
    for row in rows:
        for field in row:
            _add_field(fieldnames, seen, field)
    return fieldnames


def _render_csv(fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})
    return output.getvalue()


def _csv_data_row_count(rendered: str) -> int:
    if not rendered.strip():
        return 0
    return sum(1 for _row in csv.DictReader(io.StringIO(rendered)))


def _resolve_target_model_ids(
    *,
    model_ids: Iterable[str] | None = None,
    family_ids: Iterable[str] | None = None,
) -> list[str]:
    update_engine.bootstrap()
    normalized_model_ids = _unique_clean(model_ids)
    normalized_family_ids = _unique_clean(family_ids)
    if bool(normalized_model_ids) == bool(normalized_family_ids):
        raise ValueError("Choose exactly one target: model ids or family ids.")

    with get_connection(update_engine.ENGINE) as conn:
        if normalized_model_ids:
            rows = fetch_all(
                conn,
                select(models_table.c.id)
                .where(models_table.c.active == 1)
                .where(models_table.c.id.in_(normalized_model_ids))
                .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
            )
            found_ids = [str(row["id"]) for row in rows]
            missing_ids = [model_id for model_id in normalized_model_ids if model_id not in found_ids]
            if missing_ids:
                raise ValueError(f"Model not found: {missing_ids[0]}")
            return found_ids

        rows = fetch_all(
            conn,
            select(models_table.c.id)
            .where(models_table.c.active == 1)
            .where(models_table.c.family_id.in_(normalized_family_ids))
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )
    found_ids = [str(row["id"]) for row in rows]
    if not found_ids:
        raise ValueError(f"Model family not found: {normalized_family_ids[0]}")
    return found_ids


def _resolve_use_case_ids(use_case_ids: Iterable[str] | None, *, all_use_cases: bool) -> list[str]:
    known_use_case_ids = [str(use_case["id"]) for use_case in update_engine.list_use_cases()]
    if all_use_cases:
        return known_use_case_ids

    normalized = _unique_clean(use_case_ids)
    if not normalized:
        raise ValueError("At least one use case is required, or pass --all-use-cases.")

    for use_case_id in normalized:
        if use_case_id not in known_use_case_ids:
            raise ValueError(f"Use case not found: {use_case_id}")
    return normalized


def _available_model_id(name: str) -> str:
    base_id = _normalise_model_id(name)
    candidate_id = base_id
    suffix = 2
    with get_connection(update_engine.ENGINE) as conn:
        while fetch_one(conn, select(models_table.c.id).where(models_table.c.id == candidate_id)) is not None:
            candidate_id = f"{base_id}-{suffix}"
            suffix += 1
    return candidate_id


def _model_by_id(model_id: str) -> dict[str, Any] | None:
    for model in build_model_metadata_list():
        if str(model.get("id") or "") == model_id:
            return model
    return None


def _normalise_model_id(value: str | None) -> str:
    return _slugify(_required_text(value, "model id"))


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "unknown-model"


def _normalise_model_roles(values: Iterable[str] | None) -> list[str]:
    roles = _unique_clean(values) or ["generator"]
    invalid = [role for role in roles if role not in VALID_MODEL_ROLES]
    if invalid:
        raise ValueError(f"Unsupported model role: {invalid[0]}")
    return roles


def _validate_catalog_status(value: str) -> str:
    normalized = _required_text(value, "catalog status").lower()
    if normalized not in VALID_CATALOG_STATUSES:
        raise ValueError(f"Unsupported catalog status: {value}")
    return normalized


def _validate_recommendation_status(value: str | None) -> str:
    normalized = _required_text(value, "recommendation status").lower()
    if normalized not in VALID_RECOMMENDATION_STATUSES:
        raise ValueError(f"Unsupported recommendation status: {value}")
    return normalized


def _unique_clean(values: Iterable[str] | None) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        text = _clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _required_text(value: Any, label: str) -> str:
    text = _clean_text(value)
    if text is None:
        raise ValueError(f"{label} is required.")
    return text


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _add_field(fieldnames: list[str], seen: set[str], field: str) -> None:
    if field not in seen:
        seen.add(field)
        fieldnames.append(field)


__all__ = [
    "DEFAULT_BANKING_REVIEW_OUTPUT",
    "add_model_to_listing",
    "deprecate_listings",
    "export_banking_review_list",
    "render_banking_review_csv",
    "set_review_state",
]
