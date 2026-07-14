"""Interactive review workbench helpers for banking model decisions."""

from __future__ import annotations

import json
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
    sqlite_database_updated_at,
    update_log as update_log_table,
    utc_now_iso,
)
from .model_evidence import enrich_models_with_selection_evidence

SNAPSHOT_SCHEMA_VERSION = 3
GENERAL_RECOMMENDATION_STATUSES = ("unrated", "recommended", "restricted", "not_recommended")


def build_review_catalog() -> dict[str, Any]:
    """Return the model catalog plus review-oriented facets for the workbench."""
    models = build_model_metadata_list()
    for model in models:
        model["general_approval_status"] = _general_approval_status(model)
        model["general_recommendation_status"] = _normalize_general_recommendation_status(
            model.get("general_recommendation_status")
        )
    use_cases = update_engine.list_use_cases()
    benchmarks = update_engine.list_benchmarks()
    enrich_models_with_selection_evidence(models, use_cases=use_cases, benchmarks=benchmarks)
    providers = update_engine.list_providers()
    families = _build_family_summaries(models)
    facets = _build_facets(models, providers, families)
    sync_metadata = _latest_sync_metadata()
    return {
        "schema_version": 3,
        "generated_at": utc_now_iso(),
        "database_updated_at": sqlite_database_updated_at(update_engine.ENGINE),
        **sync_metadata,
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


def _latest_sync_metadata() -> dict[str, Any]:
    """Return the latest persisted update run without changing database state."""
    with get_connection(update_engine.ENGINE) as conn:
        row = fetch_one(
            conn,
            select(
                update_log_table.c.id,
                update_log_table.c.started_at,
                update_log_table.c.completed_at,
                update_log_table.c.status,
            )
            .order_by(update_log_table.c.started_at.desc(), update_log_table.c.id.desc())
            .limit(1),
        )
    if row is None:
        return {"last_sync_at": None, "last_sync_status": None, "last_sync_log_id": None}

    payload = dict(row)
    status = payload.get("status")
    sync_at = payload.get("started_at") if status == "running" else payload.get("completed_at")
    return {
        "last_sync_at": sync_at or payload.get("started_at"),
        "last_sync_status": status,
        "last_sync_log_id": int(payload["id"]),
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
    approval_status: str | None = None,
    approval_notes: str | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for callers that only update general approval."""
    normalized_status = _normalize_general_approval_status(approval_status, approved_for_use=approved_for_use)
    return apply_model_decisions(
        model_ids=model_ids,
        approval_status=normalized_status,
        approval_notes=approval_notes,
    )


def apply_model_decisions(
    *,
    model_ids: Iterable[str],
    approval_status: str | None = None,
    approval_notes: str | None = None,
    recommendation_status: str | None = None,
    recommendation_notes: str | None = None,
    reasoning_effort_ceiling: str | None = None,
    reasoning_effort_ceiling_set: bool = False,
    restricted_modes: Iterable[str] | None = None,
    usage_policy_notes: str | None = None,
) -> dict[str, Any]:
    """Save general model decisions without creating use-case decision rows."""
    normalized_model_ids = _unique_clean(model_ids)
    if not normalized_model_ids:
        raise ValueError("At least one model id is required.")
    _ensure_models_exist(normalized_model_ids)

    if approval_status is None and recommendation_status is None and not reasoning_effort_ceiling_set and restricted_modes is None:
        raise ValueError("At least one general decision or usage policy field is required.")

    values: dict[str, Any] = {}
    saved_at = utc_now_iso()
    normalized_approval_status: str | None = None
    normalized_recommendation_status: str | None = None
    if approval_status is not None:
        normalized_approval_status = _normalize_general_approval_status(
            approval_status,
            approved_for_use=str(approval_status).strip().lower() == "approved",
        )
        values.update(
            general_approved_for_use=1 if normalized_approval_status == "approved" else 0,
            general_approval_notes=None
            if normalized_approval_status == "unreviewed"
            else _clean_text(approval_notes),
            general_approval_updated_at=None
            if normalized_approval_status == "unreviewed"
            else saved_at,
        )
    if recommendation_status is not None:
        normalized_recommendation_status = _normalize_general_recommendation_status(recommendation_status)
        values.update(
            general_recommendation_status=normalized_recommendation_status,
            general_recommendation_notes=None
            if normalized_recommendation_status == "unrated"
            else _clean_text(recommendation_notes),
            general_recommendation_updated_at=None
            if normalized_recommendation_status == "unrated"
            else saved_at,
        )
    normalized_restricted_modes: list[str] | None = None
    if reasoning_effort_ceiling_set:
        if reasoning_effort_ceiling not in {None, "none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Unknown reasoning effort ceiling.")
        values["reasoning_effort_ceiling"] = reasoning_effort_ceiling
        values["usage_policy_updated_at"] = saved_at
    if restricted_modes is not None:
        normalized_restricted_modes = sorted(dict.fromkeys(str(mode).strip().lower() for mode in restricted_modes))
        if any(mode not in {"pro", "ultra"} for mode in normalized_restricted_modes):
            raise ValueError("Restricted modes must contain only pro or ultra.")
        values["restricted_modes_json"] = json.dumps(normalized_restricted_modes)
        values["usage_policy_updated_at"] = saved_at
    if reasoning_effort_ceiling_set or restricted_modes is not None:
        values["usage_policy_notes"] = _clean_text(usage_policy_notes)

    with update_engine.ENGINE.begin() as conn:
        result = conn.execute(
            update(models_table)
            .where(models_table.c.active == 1)
            .where(models_table.c.id.in_(normalized_model_ids))
            .values(**values)
        )

    return {
        "model_ids": normalized_model_ids,
        "updated_count": int(result.rowcount or 0),
        "approved_for_use": normalized_approval_status == "approved" if normalized_approval_status else None,
        "approval_status": normalized_approval_status,
        "recommendation_status": normalized_recommendation_status,
        "reasoning_effort_ceiling": reasoning_effort_ceiling if reasoning_effort_ceiling_set else None,
        "restricted_modes": normalized_restricted_modes,
        "saved_at": saved_at,
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
                models_table.c.general_recommendation_status,
                models_table.c.general_recommendation_notes,
                models_table.c.general_recommendation_updated_at,
                models_table.c.reasoning_effort_ceiling,
                models_table.c.restricted_modes_json,
                models_table.c.usage_policy_notes,
                models_table.c.usage_policy_updated_at,
            )
            .where(models_table.c.active == 1)
            .where(
                or_(
                    models_table.c.general_approved_for_use != 0,
                    models_table.c.general_approval_notes.is_not(None),
                    models_table.c.general_approval_updated_at.is_not(None),
                    models_table.c.general_recommendation_status != "unrated",
                    models_table.c.general_recommendation_notes.is_not(None),
                    models_table.c.general_recommendation_updated_at.is_not(None),
                    models_table.c.reasoning_effort_ceiling.is_not(None),
                    models_table.c.restricted_modes_json != "[]",
                    models_table.c.usage_policy_notes.is_not(None),
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

    model_approvals = [_row_to_dict(row) for row in model_approval_rows]
    for row in model_approvals:
        row["general_recommendation_status"] = _normalize_general_recommendation_status(
            row.get("general_recommendation_status")
        )

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "exported_at": utc_now_iso(),
        "catalog_statuses": [_row_to_dict(row) for row in catalog_status_rows],
        "model_approvals": [
            {**row, "approval_status": _general_approval_status(row)}
            for row in model_approvals
        ],
        "manual_models": [_row_to_dict(row) for row in manual_model_rows],
        "decisions": [_row_to_dict(row) for row in decision_rows],
    }


def import_review_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Import a review snapshot into the current SQLite database."""
    update_engine.bootstrap()
    if int(snapshot.get("schema_version") or 0) not in {1, 2, SNAPSHOT_SCHEMA_VERSION}:
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
    country_counts: dict[str, int] = {}
    country_names: dict[str, str] = {}
    hyperscaler_counts: dict[str, int] = {}
    hyperscaler_model_count = 0
    no_hyperscaler_model_count = 0
    role_counts: dict[str, int] = {}
    capability_counts: dict[str, int] = {}
    general_approval_counts = {"approved": 0, "not_approved": 0, "unreviewed": 0}
    general_recommendation_counts = {status: 0 for status in GENERAL_RECOMMENDATION_STATUSES}
    approval_counts = {"approved": 0, "not_approved": 0}
    for model in models:
        general_approval_counts[_general_approval_status(model)] += 1
        general_recommendation_counts[
            _normalize_general_recommendation_status(model.get("general_recommendation_status"))
        ] += 1
        for country in _model_country_entries(model):
            country_id = country["id"]
            country_counts[country_id] = country_counts.get(country_id, 0) + 1
            country_names.setdefault(country_id, country["name"])
        hyperscaler_entries = _model_hyperscaler_entries(model)
        if hyperscaler_entries:
            hyperscaler_model_count += 1
            for hyperscaler in hyperscaler_entries:
                hyperscaler_counts[hyperscaler] = hyperscaler_counts.get(hyperscaler, 0) + 1
        else:
            no_hyperscaler_model_count += 1
        for role in model.get("model_roles") or []:
            role_counts[str(role)] = role_counts.get(str(role), 0) + 1
        for capability in model.get("capabilities") or []:
            capability_text = str(capability).strip()
            if capability_text:
                capability_counts[capability_text] = capability_counts.get(capability_text, 0) + 1
        approvals = model.get("use_case_approvals")
        if not isinstance(approvals, dict):
            continue
        for approval in approvals.values():
            if not isinstance(approval, dict):
                continue
            if approval.get("approved_for_use"):
                approval_counts["approved"] += 1
            else:
                approval_counts["not_approved"] += 1

    return {
        "providers": [
            {"id": provider.get("id"), "name": provider.get("name"), "count": provider_counts.get(str(provider.get("name")), 0)}
            for provider in providers
        ],
        "countries": [
            {"id": country_id, "name": country_names.get(country_id, country_id), "count": count}
            for country_id, count in sorted(
                country_counts.items(),
                key=lambda item: (country_names.get(item[0], item[0]), item[0]),
            )
        ],
        "hyperscalers": [
            {"id": "__any__", "name": "Any hyperscaler", "count": hyperscaler_model_count},
            *[
                {"id": name, "name": name, "count": count}
                for name, count in sorted(hyperscaler_counts.items(), key=lambda item: item[0])
            ],
            {"id": "__none__", "name": "No hyperscaler route", "count": no_hyperscaler_model_count},
        ],
        "families": [
            {"id": family["family_id"], "name": family["family_name"], "count": family["model_count"]}
            for family in families
        ],
        "catalog_statuses": _counts_to_list(catalog_counts),
        "model_roles": _counts_to_list(role_counts),
        "capabilities": _counts_to_list(capability_counts),
        "general_approvals": _counts_to_list(general_approval_counts),
        "general_recommendations": _counts_to_list(general_recommendation_counts),
        "approvals": _counts_to_list(approval_counts),
    }


def _model_country_entries(model: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    origins = model.get("provider_origin_countries") or []
    if isinstance(origins, list):
        for origin in origins:
            if not isinstance(origin, dict):
                continue
            code = _clean_text(origin.get("code"))
            name = _clean_text(origin.get("name"))
            if code or name:
                entries.append({"id": code or name or "", "name": name or code or ""})

    if not entries:
        code = _clean_text(model.get("provider_country_code"))
        name = _clean_text(model.get("provider_country_name"))
        if code or name:
            entries.append({"id": code or name or "", "name": name or code or ""})

    unique: dict[str, str] = {}
    for entry in entries:
        country_id = _clean_text(entry.get("id"))
        name = _clean_text(entry.get("name"))
        if country_id and name:
            unique.setdefault(country_id, name)
    return [{"id": country_id, "name": name} for country_id, name in unique.items()]


def _model_hyperscaler_entries(model: dict[str, Any]) -> list[str]:
    summary = model.get("inference_summary") if isinstance(model.get("inference_summary"), dict) else {}
    platform_names = summary.get("platform_names") if isinstance(summary, dict) else []
    if not isinstance(platform_names, list):
        return []

    unique: dict[str, None] = {}
    for value in platform_names:
        name = _clean_text(value)
        if name:
            unique.setdefault(name, None)
    return list(unique)


def _model_needs_decision(model: dict[str, Any]) -> bool:
    return (
        _general_approval_status(model) == "unreviewed"
        or _normalize_general_recommendation_status(model.get("general_recommendation_status")) == "unrated"
    )


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
            approval_status = _normalize_general_approval_status(
                row.get("approval_status"),
                approved_for_use=bool(row.get("general_approved_for_use")),
                updated_at=_clean_text(row.get("general_approval_updated_at")),
                unreviewed_when_missing=True,
            )
            result = conn.execute(
                update(models_table)
                .where(models_table.c.id == model_id)
                .values(
                    general_approved_for_use=1 if approval_status == "approved" else 0,
                    general_approval_notes=None
                    if approval_status == "unreviewed"
                    else _clean_text(row.get("general_approval_notes")),
                    general_approval_updated_at=None
                    if approval_status == "unreviewed"
                    else (_clean_text(row.get("general_approval_updated_at")) or utc_now_iso()),
                    general_recommendation_status=_normalize_general_recommendation_status(
                        _clean_text(row.get("general_recommendation_status")) or "unrated"
                    ),
                    general_recommendation_notes=_clean_text(row.get("general_recommendation_notes")),
                    general_recommendation_updated_at=_clean_text(
                        row.get("general_recommendation_updated_at")
                    ),
                    reasoning_effort_ceiling=_clean_text(row.get("reasoning_effort_ceiling")),
                    restricted_modes_json=_clean_text(row.get("restricted_modes_json")) or "[]",
                    usage_policy_notes=_clean_text(row.get("usage_policy_notes")),
                    usage_policy_updated_at=_clean_text(row.get("usage_policy_updated_at")),
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


def _normalize_general_recommendation_status(value: Any) -> str:
    normalized = _validate_recommendation_status(_clean_text(value) or "unrated")
    return "not_recommended" if normalized == "discouraged" else normalized


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


def _general_approval_status(model: dict[str, Any]) -> str:
    if model.get("general_approved_for_use"):
        return "approved"
    if _clean_text(model.get("general_approval_updated_at")):
        return "not_approved"
    return "unreviewed"


def _normalize_general_approval_status(
    status: Any,
    *,
    approved_for_use: bool,
    updated_at: str | None = None,
    unreviewed_when_missing: bool = False,
) -> str:
    normalized = _clean_text(status)
    if normalized is None:
        if approved_for_use:
            return "approved"
        if unreviewed_when_missing and not updated_at:
            return "unreviewed"
        return "not_approved"
    normalized = normalized.lower()
    if normalized not in {"approved", "not_approved", "unreviewed"}:
        raise ValueError(f"Unsupported general approval status: {status}")
    return normalized


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
