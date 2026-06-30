"""Tracked baseline and helpers for manual model identity curation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine

from .database import model_duplicate_overrides, model_identity_overrides
from .name_resolution import normalize_text

MODEL_CURATION_BASELINE_PATH = Path(__file__).with_name("model_curation_baseline.json")


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def build_model_curation_match_key(provider: Any, name: Any) -> str | None:
    normalized_name = normalize_text(name or "")
    if not normalized_name:
        return None
    normalized_provider = normalize_text(provider or "")
    return f"{normalized_provider}::{normalized_name}"


def _normalize_identity_override(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    source_model_id = _clean_optional_text(item.get("source_model_id"))
    match_provider = _clean_optional_text(item.get("match_provider"))
    match_name = _clean_optional_text(item.get("match_name"))
    match_key = build_model_curation_match_key(match_provider, match_name)
    family_id = _clean_optional_text(item.get("family_id"))
    family_name = _clean_optional_text(item.get("family_name"))
    canonical_model_id = _clean_optional_text(item.get("canonical_model_id"))
    canonical_model_name = _clean_optional_text(item.get("canonical_model_name"))

    if not all((source_model_id, match_provider, match_name, match_key, family_id, family_name, canonical_model_id, canonical_model_name)):
        return None

    return {
        "source_model_id": source_model_id,
        "match_provider": match_provider,
        "match_name": match_name,
        "match_key": match_key,
        "family_id": family_id,
        "family_name": family_name,
        "canonical_model_id": canonical_model_id,
        "canonical_model_name": canonical_model_name,
        "variant_label": _clean_optional_text(item.get("variant_label")),
        "notes": _clean_optional_text(item.get("notes")),
        "updated_at": _clean_optional_text(item.get("updated_at")),
        "active": 1 if item.get("active", True) else 0,
    }


def _normalize_duplicate_override(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    source_model_id = _clean_optional_text(item.get("source_model_id"))
    match_provider = _clean_optional_text(item.get("match_provider"))
    match_name = _clean_optional_text(item.get("match_name"))
    match_key = build_model_curation_match_key(match_provider, match_name)
    target_model_id = _clean_optional_text(item.get("target_model_id"))

    if not all((source_model_id, match_provider, match_name, match_key, target_model_id)):
        return None

    return {
        "source_model_id": source_model_id,
        "match_provider": match_provider,
        "match_name": match_name,
        "match_key": match_key,
        "target_model_id": target_model_id,
        "notes": _clean_optional_text(item.get("notes")),
        "updated_at": _clean_optional_text(item.get("updated_at")),
        "active": 1 if item.get("active", True) else 0,
    }


def load_model_curation_baseline(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    baseline_path = path or MODEL_CURATION_BASELINE_PATH
    if not baseline_path.exists():
        return {"identity_overrides": [], "duplicate_overrides": []}

    raw_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError("Model curation baseline must be a JSON object.")

    identity_rows = [
        normalized
        for normalized in (
            _normalize_identity_override(item) for item in raw_payload.get("identity_overrides", [])
        )
        if normalized is not None
    ]
    duplicate_rows = [
        normalized
        for normalized in (
            _normalize_duplicate_override(item) for item in raw_payload.get("duplicate_overrides", [])
        )
        if normalized is not None
    ]
    return {
        "identity_overrides": identity_rows,
        "duplicate_overrides": duplicate_rows,
    }


def apply_model_curation_baseline(target: Connection | Engine) -> dict[str, int]:
    if isinstance(target, Engine):
        with target.begin() as conn:
            return apply_model_curation_baseline(conn)

    payload = load_model_curation_baseline()
    identity_rows = payload["identity_overrides"]
    duplicate_rows = payload["duplicate_overrides"]

    if identity_rows:
        stmt = sqlite_insert(model_identity_overrides).values(identity_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_model_id"],
            set_={
                "match_provider": stmt.excluded.match_provider,
                "match_name": stmt.excluded.match_name,
                "match_key": stmt.excluded.match_key,
                "family_id": stmt.excluded.family_id,
                "family_name": stmt.excluded.family_name,
                "canonical_model_id": stmt.excluded.canonical_model_id,
                "canonical_model_name": stmt.excluded.canonical_model_name,
                "variant_label": stmt.excluded.variant_label,
                "notes": stmt.excluded.notes,
                "updated_at": stmt.excluded.updated_at,
                "active": stmt.excluded.active,
            },
        )
        target.execute(stmt)

    if duplicate_rows:
        stmt = sqlite_insert(model_duplicate_overrides).values(duplicate_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_model_id"],
            set_={
                "match_provider": stmt.excluded.match_provider,
                "match_name": stmt.excluded.match_name,
                "match_key": stmt.excluded.match_key,
                "target_model_id": stmt.excluded.target_model_id,
                "notes": stmt.excluded.notes,
                "updated_at": stmt.excluded.updated_at,
                "active": stmt.excluded.active,
            },
        )
        target.execute(stmt)

    return {
        "identity_overrides": len(identity_rows),
        "duplicate_overrides": len(duplicate_rows),
    }


def export_model_curation_baseline(target: Connection | Engine, path: Path | None = None) -> Path:
    baseline_path = path or MODEL_CURATION_BASELINE_PATH
    if isinstance(target, Engine):
        with target.begin() as conn:
            return export_model_curation_baseline(conn, baseline_path)

    identity_rows = (
        target.execute(
            select(model_identity_overrides)
            .where(model_identity_overrides.c.active == 1)
            .order_by(model_identity_overrides.c.source_model_id.asc())
        )
        .mappings()
        .all()
    )
    duplicate_rows = (
        target.execute(
            select(model_duplicate_overrides)
            .where(model_duplicate_overrides.c.active == 1)
            .order_by(model_duplicate_overrides.c.source_model_id.asc())
        )
        .mappings()
        .all()
    )

    payload = {
        "identity_overrides": [
            {
                "source_model_id": str(row["source_model_id"]),
                "match_provider": str(row["match_provider"]),
                "match_name": str(row["match_name"]),
                "family_id": str(row["family_id"]),
                "family_name": str(row["family_name"]),
                "canonical_model_id": str(row["canonical_model_id"]),
                "canonical_model_name": str(row["canonical_model_name"]),
                "variant_label": _clean_optional_text(row.get("variant_label")),
                "notes": _clean_optional_text(row.get("notes")),
                "updated_at": _clean_optional_text(row.get("updated_at")),
                "active": bool(row.get("active", 1)),
            }
            for row in identity_rows
        ],
        "duplicate_overrides": [
            {
                "source_model_id": str(row["source_model_id"]),
                "match_provider": str(row["match_provider"]),
                "match_name": str(row["match_name"]),
                "target_model_id": str(row["target_model_id"]),
                "notes": _clean_optional_text(row.get("notes")),
                "updated_at": _clean_optional_text(row.get("updated_at")),
                "active": bool(row.get("active", 1)),
            }
            for row in duplicate_rows
        ],
    }
    baseline_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return baseline_path


__all__ = [
    "MODEL_CURATION_BASELINE_PATH",
    "apply_model_curation_baseline",
    "build_model_curation_match_key",
    "export_model_curation_baseline",
    "load_model_curation_baseline",
]
