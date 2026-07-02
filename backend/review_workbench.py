"""Interactive review workbench helpers for banking model decisions."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from . import update_engine
from .banking_review import (
    CATALOG_STATUS_DEPRECATED,
    CATALOG_STATUS_PROVISIONAL,
    CATALOG_STATUS_TRACKED,
    VALID_CATALOG_STATUSES,
    VALID_MODEL_ROLES,
    VALID_RECOMMENDATION_STATUSES,
    add_model_to_listing,
    set_review_state,
)
from .catalog_export import build_model_metadata_list
from .database import (
    fetch_all,
    fetch_one,
    get_connection,
    model_use_case_approvals as model_use_case_approvals_table,
    models as models_table,
    utc_now_iso,
)

SNAPSHOT_SCHEMA_VERSION = 1


def build_review_catalog() -> dict[str, Any]:
    """Return the model catalog plus review-oriented facets for the workbench."""
    models = build_model_metadata_list()
    use_cases = update_engine.list_use_cases()
    providers = update_engine.list_providers()
    families = _build_family_summaries(models)
    facets = _build_facets(models, providers, families)
    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "models": models,
        "use_cases": use_cases,
        "providers": providers,
        "families": families,
        "facets": facets,
        "summary": {
            "model_count": len(models),
            "provider_count": len(providers),
            "family_count": len(families),
            "deprecated_count": sum(1 for model in models if model.get("catalog_status") == CATALOG_STATUS_DEPRECATED),
            "needs_decision_count": sum(1 for model in models if _model_needs_decision(model)),
        },
    }


def apply_review_decisions(
    *,
    model_ids: Iterable[str],
    use_case_ids: Iterable[str] | None = None,
    approved_for_use: bool | None = None,
    recommendation_status: str | None = None,
    approval_notes: str | None = None,
    recommendation_notes: str | None = None,
    catalog_status: str | None = None,
) -> dict[str, Any]:
    """Save explicit review decisions to durable SQLite rows."""
    normalized_model_ids = _unique_clean(model_ids)
    if not normalized_model_ids:
        raise ValueError("At least one model id is required.")
    _ensure_models_exist(normalized_model_ids)

    normalized_catalog_status = _validate_catalog_status(catalog_status) if catalog_status is not None else None
    normalized_recommendation_status = (
        _validate_recommendation_status(recommendation_status)
        if recommendation_status is not None
        else None
    )
    should_write_use_case_rows = any(
        value is not None
        for value in (approved_for_use, normalized_recommendation_status, approval_notes, recommendation_notes)
    )

    review_summary: dict[str, Any] | None = None
    if should_write_use_case_rows:
        normalized_use_case_ids = _validate_use_case_ids(use_case_ids)
        review_summary = set_review_state(
            model_ids=normalized_model_ids,
            use_case_ids=normalized_use_case_ids,
            approved_for_use=approved_for_use,
            recommendation_status=normalized_recommendation_status,
            approval_notes=approval_notes,
            recommendation_notes=recommendation_notes,
        )
    else:
        normalized_use_case_ids = _unique_clean(use_case_ids)

    catalog_status_updated_count = 0
    if normalized_catalog_status is not None:
        catalog_status_updated_count = _set_catalog_status(normalized_model_ids, normalized_catalog_status, approval_notes)

    return {
        "model_ids": normalized_model_ids,
        "use_case_ids": normalized_use_case_ids,
        "updated_count": int((review_summary or {}).get("updated_count") or 0),
        "catalog_status_updated_count": catalog_status_updated_count,
        "catalog_status": normalized_catalog_status,
        "review": review_summary,
        "saved_at": utc_now_iso(),
    }


def apply_model_approvals(
    *,
    model_ids: Iterable[str],
    approved_for_use: bool,
    approval_notes: str | None = None,
) -> dict[str, Any]:
    """Save model-level general approval without touching use-case decisions."""
    normalized_model_ids = _unique_clean(model_ids)
    if not normalized_model_ids:
        raise ValueError("At least one model id is required.")
    _ensure_models_exist(normalized_model_ids)

    cleaned_notes = _clean_text(approval_notes)
    updated_at = utc_now_iso()
    with update_engine.ENGINE.begin() as conn:
        result = conn.execute(
            update(models_table)
            .where(models_table.c.active == 1)
            .where(models_table.c.id.in_(normalized_model_ids))
            .values(
                general_approved_for_use=1 if approved_for_use else 0,
                general_approval_notes=cleaned_notes,
                general_approval_updated_at=updated_at,
            )
        )

    return {
        "model_ids": normalized_model_ids,
        "updated_count": int(result.rowcount or 0),
        "approved_for_use": bool(approved_for_use),
        "saved_at": updated_at,
    }


def add_review_model(
    *,
    name: str,
    provider: str,
    model_id: str | None = None,
    model_type: str = "proprietary",
    model_roles: Iterable[str] | None = None,
    catalog_status: str = CATALOG_STATUS_TRACKED,
    notes: str | None = None,
) -> dict[str, Any]:
    """Add a manually curated model listing for review."""
    return add_model_to_listing(
        name=name,
        provider=provider,
        model_id=model_id,
        model_type=model_type,
        model_roles=model_roles,
        catalog_status=catalog_status,
        notes=notes,
    )


def export_review_snapshot() -> dict[str, Any]:
    """Export review decisions and manual listings for DB rebuild resilience."""
    update_engine.bootstrap()
    with get_connection(update_engine.ENGINE) as conn:
        decision_rows = fetch_all(
            conn,
            select(model_use_case_approvals_table).order_by(
                model_use_case_approvals_table.c.model_id.asc(),
                model_use_case_approvals_table.c.use_case_id.asc(),
            ),
        )
        catalog_status_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.catalog_status,
                models_table.c.approval_notes,
                models_table.c.approval_updated_at,
            )
            .where(models_table.c.active == 1)
            .where(models_table.c.catalog_status != CATALOG_STATUS_TRACKED)
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )
        model_approval_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.general_approved_for_use,
                models_table.c.general_approval_notes,
                models_table.c.general_approval_updated_at,
            )
            .where(models_table.c.active == 1)
            .where(
                or_(
                    models_table.c.general_approved_for_use != 0,
                    models_table.c.general_approval_notes.is_not(None),
                    models_table.c.general_approval_updated_at.is_not(None),
                )
            )
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )
        manual_model_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.provider,
                models_table.c.type,
                models_table.c.model_roles_json,
                models_table.c.catalog_status,
                models_table.c.intended_use_short,
            )
            .where(models_table.c.active == 1)
            .where(models_table.c.metadata_source_name == "manual")
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "exported_at": utc_now_iso(),
        "catalog_statuses": [_row_to_dict(row) for row in catalog_status_rows],
        "model_approvals": [_row_to_dict(row) for row in model_approval_rows],
        "manual_models": [_row_to_dict(row) for row in manual_model_rows],
        "decisions": [_row_to_dict(row) for row in decision_rows],
    }


def import_review_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Import a review snapshot into the current SQLite database."""
    update_engine.bootstrap()
    if int(snapshot.get("schema_version") or 0) != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported review snapshot schema version: {snapshot.get('schema_version')}")

    created_manual_models = 0
    skipped_manual_models = 0
    for model in snapshot.get("manual_models") or []:
        if not isinstance(model, dict):
            continue
        model_id = _clean_text(model.get("id"))
        if not model_id:
            continue
        if _model_exists(model_id):
            skipped_manual_models += 1
            continue
        add_review_model(
            name=_clean_text(model.get("name")) or model_id,
            provider=_clean_text(model.get("provider")) or "Manual Provider",
            model_id=model_id,
            model_type=_clean_text(model.get("type")) or "proprietary",
            model_roles=_decode_model_roles(model.get("model_roles_json")),
            catalog_status=_clean_text(model.get("catalog_status")) or CATALOG_STATUS_TRACKED,
            notes=_clean_text(model.get("intended_use_short")),
        )
        created_manual_models += 1

    catalog_status_updated_count = _import_catalog_statuses(snapshot.get("catalog_statuses") or [])
    decision_summary = _import_decisions(snapshot.get("decisions") or [])
    model_approval_updated_count = _import_model_approvals(snapshot.get("model_approvals") or [])
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "created_manual_model_count": created_manual_models,
        "skipped_manual_model_count": skipped_manual_models,
        "catalog_status_updated_count": catalog_status_updated_count,
        "model_approval_updated_count": model_approval_updated_count,
        "decision_import_count": decision_summary["imported_count"],
        "decision_skipped_count": decision_summary["skipped_count"],
        "imported_at": utc_now_iso(),
    }


def _build_family_summaries(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    families_by_id: dict[str, dict[str, Any]] = {}
    for model in models:
        family_id = _clean_text(model.get("family_id")) or str(model.get("id") or "")
        family = families_by_id.setdefault(
            family_id,
            {
                "family_id": family_id,
                "family_name": _clean_text(model.get("family_name")) or _clean_text(model.get("name")) or family_id,
                "provider": _clean_text(model.get("provider")),
                "model_count": 0,
                "deprecated_count": 0,
                "needs_decision_count": 0,
                "model_ids": [],
            },
        )
        family["model_count"] += 1
        family["model_ids"].append(str(model.get("id") or ""))
        if model.get("catalog_status") == CATALOG_STATUS_DEPRECATED:
            family["deprecated_count"] += 1
        if _model_needs_decision(model):
            family["needs_decision_count"] += 1
    return sorted(families_by_id.values(), key=lambda item: (str(item.get("provider") or ""), str(item["family_name"])))


def _build_facets(
    models: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    families: list[dict[str, Any]],
) -> dict[str, Any]:
    provider_counts = _count_values(model.get("provider") for model in models)
    catalog_counts = _count_values(model.get("catalog_status") for model in models)
    role_counts: dict[str, int] = {}
    recommendation_counts: dict[str, int] = {}
    general_approval_counts = {"approved": 0, "not_approved": 0}
    approval_counts = {"approved": 0, "not_approved": 0}
    for model in models:
        if model.get("general_approved_for_use"):
            general_approval_counts["approved"] += 1
        else:
            general_approval_counts["not_approved"] += 1
        for role in model.get("model_roles") or []:
            role_counts[str(role)] = role_counts.get(str(role), 0) + 1
        approvals = model.get("use_case_approvals")
        if not isinstance(approvals, dict):
            continue
        for approval in approvals.values():
            if not isinstance(approval, dict):
                continue
            status = str(approval.get("effective_recommendation_status") or "unrated")
            recommendation_counts[status] = recommendation_counts.get(status, 0) + 1
            if approval.get("approved_for_use"):
                approval_counts["approved"] += 1
            else:
                approval_counts["not_approved"] += 1

    return {
        "providers": [
            {"id": provider.get("id"), "name": provider.get("name"), "count": provider_counts.get(str(provider.get("name")), 0)}
            for provider in providers
        ],
        "families": [
            {"id": family["family_id"], "name": family["family_name"], "count": family["model_count"]}
            for family in families
        ],
        "catalog_statuses": _counts_to_list(catalog_counts),
        "model_roles": _counts_to_list(role_counts),
        "general_approvals": _counts_to_list(general_approval_counts),
        "recommendations": _counts_to_list(recommendation_counts),
        "approvals": _counts_to_list(approval_counts),
    }


def _model_needs_decision(model: dict[str, Any]) -> bool:
    approvals = model.get("use_case_approvals")
    if not isinstance(approvals, dict):
        return False
    for approval in approvals.values():
        if not isinstance(approval, dict):
            continue
        manual_status = str(approval.get("recommendation_status") or "unrated")
        proposed_status = str(approval.get("proposed_recommendation_status") or "unrated")
        if manual_status == "unrated" and proposed_status != "unrated":
            return True
    return False


def _set_catalog_status(model_ids: list[str], catalog_status: str, notes: str | None = None) -> int:
    cleaned_notes = _clean_text(notes)
    updated_at = utc_now_iso()
    with update_engine.ENGINE.begin() as conn:
        result = conn.execute(
            update(models_table)
            .where(models_table.c.id.in_(model_ids))
            .values(
                catalog_status=catalog_status,
                approval_notes=cleaned_notes,
                approval_updated_at=updated_at,
            )
        )
    return int(result.rowcount or 0)


def _import_catalog_statuses(rows: Iterable[Any]) -> int:
    updated = 0
    with update_engine.ENGINE.begin() as conn:
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = _clean_text(row.get("id"))
            if not model_id or not _model_exists(model_id, conn=conn):
                continue
            catalog_status = _validate_catalog_status(_clean_text(row.get("catalog_status")) or CATALOG_STATUS_TRACKED)
            result = conn.execute(
                update(models_table)
                .where(models_table.c.id == model_id)
                .values(
                    catalog_status=catalog_status,
                    approval_notes=_clean_text(row.get("approval_notes")),
                    approval_updated_at=_clean_text(row.get("approval_updated_at")) or utc_now_iso(),
                )
            )
            updated += int(result.rowcount or 0)
    return updated


def _import_model_approvals(rows: Iterable[Any]) -> int:
    updated = 0
    with update_engine.ENGINE.begin() as conn:
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = _clean_text(row.get("id"))
            if not model_id or not _model_exists(model_id, conn=conn):
                continue
            result = conn.execute(
                update(models_table)
                .where(models_table.c.id == model_id)
                .values(
                    general_approved_for_use=1 if bool(row.get("general_approved_for_use")) else 0,
                    general_approval_notes=_clean_text(row.get("general_approval_notes")),
                    general_approval_updated_at=_clean_text(row.get("general_approval_updated_at")) or utc_now_iso(),
                )
            )
            updated += int(result.rowcount or 0)
    return updated


def _import_decisions(rows: Iterable[Any]) -> dict[str, int]:
    use_case_ids = set(_all_use_case_ids())
    imported_count = 0
    skipped_count = 0
    changed_model_ids: set[str] = set()
    with update_engine.ENGINE.begin() as conn:
        for row in rows:
            if not isinstance(row, dict):
                skipped_count += 1
                continue
            model_id = _clean_text(row.get("model_id"))
            use_case_id = _clean_text(row.get("use_case_id"))
            if not model_id or not use_case_id or use_case_id not in use_case_ids or not _model_exists(model_id, conn=conn):
                skipped_count += 1
                continue
            stmt = sqlite_insert(model_use_case_approvals_table).values(
                model_id=model_id,
                use_case_id=use_case_id,
                approved_for_use=1 if bool(row.get("approved_for_use")) else 0,
                approval_notes=_clean_text(row.get("approval_notes")),
                approval_updated_at=_clean_text(row.get("approval_updated_at")) or utc_now_iso(),
                recommendation_status=_validate_recommendation_status(
                    _clean_text(row.get("recommendation_status")) or "unrated"
                ),
                recommendation_notes=_clean_text(row.get("recommendation_notes")),
                recommendation_updated_at=_clean_text(row.get("recommendation_updated_at")) or utc_now_iso(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["model_id", "use_case_id"],
                set_={
                    "approved_for_use": stmt.excluded.approved_for_use,
                    "approval_notes": stmt.excluded.approval_notes,
                    "approval_updated_at": stmt.excluded.approval_updated_at,
                    "recommendation_status": stmt.excluded.recommendation_status,
                    "recommendation_notes": stmt.excluded.recommendation_notes,
                    "recommendation_updated_at": stmt.excluded.recommendation_updated_at,
                },
            )
            conn.execute(stmt)
            imported_count += 1
            changed_model_ids.add(model_id)
        for model_id in sorted(changed_model_ids):
            update_engine._sync_legacy_model_approval_columns(conn, model_id)  # type: ignore[attr-defined]
    return {"imported_count": imported_count, "skipped_count": skipped_count}


def _ensure_models_exist(model_ids: list[str]) -> None:
    update_engine.bootstrap()
    with get_connection(update_engine.ENGINE) as conn:
        found = {
            str(row["id"])
            for row in fetch_all(
                conn,
                select(models_table.c.id)
                .where(models_table.c.active == 1)
                .where(models_table.c.id.in_(model_ids)),
            )
        }
    missing = [model_id for model_id in model_ids if model_id not in found]
    if missing:
        raise ValueError(f"Model not found: {missing[0]}")


def _model_exists(model_id: str, *, conn: Any | None = None) -> bool:
    if conn is not None:
        return fetch_one(conn, select(models_table.c.id).where(models_table.c.id == model_id)) is not None
    with get_connection(update_engine.ENGINE) as active_conn:
        return fetch_one(active_conn, select(models_table.c.id).where(models_table.c.id == model_id)) is not None


def _validate_use_case_ids(use_case_ids: Iterable[str] | None) -> list[str]:
    known_use_case_ids = _all_use_case_ids()
    normalized = _unique_clean(use_case_ids)
    if not normalized:
        raise ValueError("At least one use case is required for approval or recommendation changes.")
    for use_case_id in normalized:
        if use_case_id not in known_use_case_ids:
            raise ValueError(f"Use case not found: {use_case_id}")
    return normalized


def _all_use_case_ids() -> list[str]:
    return [str(use_case["id"]) for use_case in update_engine.list_use_cases()]


def _validate_catalog_status(value: str | None) -> str:
    normalized = _required_text(value, "catalog status").lower()
    if normalized not in VALID_CATALOG_STATUSES:
        raise ValueError(f"Unsupported catalog status: {value}")
    return normalized


def _validate_recommendation_status(value: str | None) -> str:
    normalized = _required_text(value, "recommendation status").lower()
    if normalized not in VALID_RECOMMENDATION_STATUSES:
        raise ValueError(f"Unsupported recommendation status: {value}")
    return normalized


def _decode_model_roles(value: Any) -> list[str]:
    if isinstance(value, list):
        roles = [str(role) for role in value]
    else:
        import json

        try:
            decoded = json.loads(str(value or "[]"))
        except json.JSONDecodeError:
            decoded = []
        roles = [str(role) for role in decoded] if isinstance(decoded, list) else []
    return [role for role in roles if role in VALID_MODEL_ROLES] or ["generator"]


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
    return counts


def _counts_to_list(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [{"id": key, "name": key, "count": value} for key, value in sorted(counts.items())]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


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


__all__ = [
    "CATALOG_STATUS_DEPRECATED",
    "CATALOG_STATUS_PROVISIONAL",
    "CATALOG_STATUS_TRACKED",
    "SNAPSHOT_SCHEMA_VERSION",
    "add_review_model",
    "apply_model_approvals",
    "apply_review_decisions",
    "build_review_catalog",
    "export_review_snapshot",
    "import_review_snapshot",
]
