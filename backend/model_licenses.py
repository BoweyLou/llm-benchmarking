from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.engine import Connection, Engine

from .database import fetch_all, get_connection, models

MODEL_LICENSE_BASELINE_PATH = Path(__file__).with_name("model_license_baseline.json")
PROPRIETARY_LICENSE_ID = "proprietary"
PROPRIETARY_LICENSE_NAME = "Proprietary"
LICENSE_POLICY_COMMERCIAL_CLEAR = "commercial_clear"
LICENSE_POLICY_POTENTIAL_LEGAL_REVIEW = "potential_legal_review"
LICENSE_POLICY_COMMERCIAL_BLOCKED = "commercial_blocked"
LICENSE_POLICY_LABELS = {
    LICENSE_POLICY_COMMERCIAL_CLEAR: "Commercial clear",
    LICENSE_POLICY_POTENTIAL_LEGAL_REVIEW: "Potential legal review",
    LICENSE_POLICY_COMMERCIAL_BLOCKED: "Commercially restricted",
}
LICENSE_POLICY_NOTES = {
    LICENSE_POLICY_POTENTIAL_LEGAL_REVIEW: (
        "Potential legal review: this model may require legal/procurement review before production commercial use."
    ),
    LICENSE_POLICY_COMMERCIAL_BLOCKED: (
        "Commercially restricted license: this model is not recommended for production commercial use."
    ),
}


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _normalize_license_payload(item: Any, *, key_field: str | None = None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    if key_field is not None and _clean_optional_text(item.get(key_field)) is None:
        return None

    license_id = _clean_optional_text(item.get("license_id"))
    license_name = _clean_optional_text(item.get("license_name"))
    license_url = _clean_optional_text(item.get("license_url"))
    if not (license_id or license_name or license_url):
        return None

    payload: dict[str, Any] = {
        "license_id": license_id,
        "license_name": license_name,
        "license_url": license_url,
        "active": 1 if item.get("active", True) else 0,
    }
    if key_field is not None:
        payload[key_field] = _clean_optional_text(item.get(key_field))
    if "provider" in item:
        payload["provider"] = _clean_optional_text(item.get("provider"))
    if "type" in item:
        payload["type"] = _clean_optional_text(item.get("type"))
    return payload


def classify_license_policy(license_id: Any, license_name: Any) -> str:
    normalized_values = [
        value
        for value in (
            _clean_optional_text(license_id),
            _clean_optional_text(license_name),
        )
        if value
    ]
    lowered_values = [value.casefold() for value in normalized_values]

    if any(_is_commercially_blocked_license(value) for value in lowered_values):
        return LICENSE_POLICY_COMMERCIAL_BLOCKED
    if any(_is_commercial_clear_license(value) for value in lowered_values):
        return LICENSE_POLICY_COMMERCIAL_CLEAR
    return LICENSE_POLICY_POTENTIAL_LEGAL_REVIEW


def build_license_policy_payload(license_id: Any, license_name: Any) -> dict[str, Any]:
    policy_class = classify_license_policy(license_id, license_name)
    return {
        "license_policy_class": policy_class,
        "license_policy_label": LICENSE_POLICY_LABELS[policy_class],
        "license_policy_note": LICENSE_POLICY_NOTES.get(policy_class),
        "potential_legal_review": policy_class == LICENSE_POLICY_POTENTIAL_LEGAL_REVIEW,
        "commercial_use_blocked": policy_class == LICENSE_POLICY_COMMERCIAL_BLOCKED,
    }


def _is_commercial_clear_license(value: str) -> bool:
    return value in {"mit", "apache-2.0"}


def _is_commercially_blocked_license(value: str) -> bool:
    return (
        "cc-by-nc" in value
        or "non-commercial" in value
        or "noncommercial" in value
    )


def load_model_license_baseline(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    baseline_path = path or MODEL_LICENSE_BASELINE_PATH
    if not baseline_path.exists():
        return {
            "exact_overrides": [],
            "family_defaults": [],
            "provider_type_defaults": [],
        }

    raw_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError("Model license baseline must be a JSON object.")

    return {
        "exact_overrides": [
            normalized
            for normalized in (
                _normalize_license_payload(item, key_field="model_id")
                for item in raw_payload.get("exact_overrides", [])
            )
            if normalized is not None and normalized.get("active", 1)
        ],
        "family_defaults": [
            normalized
            for normalized in (
                _normalize_license_payload(item, key_field="family_id")
                for item in raw_payload.get("family_defaults", [])
            )
            if normalized is not None and normalized.get("active", 1)
        ],
        "provider_type_defaults": [
            normalized
            for normalized in (
                _normalize_license_payload(item)
                for item in raw_payload.get("provider_type_defaults", [])
            )
            if normalized is not None
            and normalized.get("active", 1)
            and normalized.get("provider")
            and normalized.get("type")
        ],
    }


def apply_model_license_baseline(target: Connection | Engine, path: Path | None = None) -> dict[str, int]:
    if isinstance(target, Engine):
        with get_connection(target) as conn:
            return apply_model_license_baseline(conn, path)

    rows = fetch_all(target, select(models).where(models.c.active == 1))
    row_by_id = {str(row["id"]): dict(row) for row in rows}
    summary = {
        "exact_overrides": 0,
        "family_defaults": 0,
        "provider_type_defaults": 0,
        "total_updates": 0,
    }

    baseline = load_model_license_baseline(path)

    for payload in baseline["exact_overrides"]:
        row = row_by_id.get(str(payload["model_id"]))
        if row is None:
            continue
        update_values = _build_license_update(row, payload, authoritative=True)
        if not update_values:
            continue
        _apply_model_update(target, row_by_id, str(row["id"]), update_values)
        summary["exact_overrides"] += 1
        summary["total_updates"] += 1

    for payload in baseline["family_defaults"]:
        family_id = str(payload["family_id"])
        for row in list(row_by_id.values()):
            if str(row.get("family_id") or "") != family_id:
                continue
            update_values = _build_license_update(row, payload, authoritative=False)
            if not update_values:
                continue
            _apply_model_update(target, row_by_id, str(row["id"]), update_values)
            summary["family_defaults"] += 1
            summary["total_updates"] += 1

    for payload in baseline["provider_type_defaults"]:
        provider = str(payload["provider"])
        model_type = str(payload["type"])
        for row in list(row_by_id.values()):
            if str(row.get("provider") or "") != provider or str(row.get("type") or "") != model_type:
                continue
            update_values = _build_license_update(row, payload, authoritative=False)
            if not update_values:
                continue
            _apply_model_update(target, row_by_id, str(row["id"]), update_values)
            summary["provider_type_defaults"] += 1
            summary["total_updates"] += 1

    return summary


def apply_inferred_model_licenses(target: Connection | Engine) -> dict[str, int]:
    if isinstance(target, Engine):
        with get_connection(target) as conn:
            return apply_inferred_model_licenses(conn)

    rows = fetch_all(
        target,
        select(
            models.c.id,
            models.c.provider,
            models.c.type,
            models.c.family_id,
            models.c.family_name,
            models.c.license_id,
            models.c.license_name,
            models.c.license_url,
        ).where(models.c.active == 1),
    )
    row_by_id = {str(row["id"]): dict(row) for row in rows}
    summary = {
        "family_id_propagation": 0,
        "family_name_propagation": 0,
        "family_name_non_proprietary_propagation": 0,
        "proprietary_defaults": 0,
        "total_updates": 0,
    }

    for model_id, payload in _build_unique_group_license_updates(list(row_by_id.values()), group_field="family_id").items():
        _apply_model_update(target, row_by_id, model_id, payload)
        summary["family_id_propagation"] += 1
        summary["total_updates"] += 1

    for model_id, payload in _build_unique_group_license_updates(list(row_by_id.values()), group_field="family_name").items():
        _apply_model_update(target, row_by_id, model_id, payload)
        summary["family_name_propagation"] += 1
        summary["total_updates"] += 1

    for model_id, payload in _build_unique_family_name_non_proprietary_updates(list(row_by_id.values())).items():
        _apply_model_update(target, row_by_id, model_id, payload)
        summary["family_name_non_proprietary_propagation"] += 1
        summary["total_updates"] += 1

    for row in list(row_by_id.values()):
        if str(row.get("type") or "") != "proprietary":
            continue
        if _has_license(row):
            continue
        payload = {
            "license_id": PROPRIETARY_LICENSE_ID,
            "license_name": PROPRIETARY_LICENSE_NAME,
        }
        _apply_model_update(target, row_by_id, str(row["id"]), payload)
        summary["proprietary_defaults"] += 1
        summary["total_updates"] += 1

    return summary


def _build_unique_group_license_updates(
    rows: list[dict[str, Any]],
    *,
    group_field: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("type") or "") != "open_weights":
            continue
        group_value = _clean_optional_text(row.get(group_field))
        if group_value:
            grouped[group_value].append(row)

    updates: dict[str, dict[str, Any]] = {}
    for group_rows in grouped.values():
        donors: dict[tuple[str, str], dict[str, Any]] = {}
        for row in group_rows:
            signature = _license_signature(row)
            if signature is None:
                continue
            current = donors.get(signature)
            if current is None or _license_completeness(row) > _license_completeness(current):
                donors[signature] = row
        if len(donors) != 1:
            continue
        donor = next(iter(donors.values()))
        donor_payload = {
            "license_id": _clean_optional_text(donor.get("license_id")),
            "license_name": _clean_optional_text(donor.get("license_name")),
            "license_url": _clean_optional_text(donor.get("license_url")),
        }
        for row in group_rows:
            if _has_license(row):
                continue
            updates[str(row["id"])] = donor_payload
    return updates


def _build_unique_family_name_non_proprietary_updates(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    missing_rows_by_family_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    donor_rows_by_family_name: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)

    for row in rows:
        family_name = _clean_optional_text(row.get("family_name"))
        if not family_name:
            continue

        if str(row.get("type") or "") == "open_weights" and not _has_license(row):
            missing_rows_by_family_name[family_name].append(row)
            continue

        signature = _license_signature(row)
        if signature is None or _is_proprietary_license(row):
            continue
        current = donor_rows_by_family_name[family_name].get(signature)
        if current is None or _license_completeness(row) > _license_completeness(current):
            donor_rows_by_family_name[family_name][signature] = row

    updates: dict[str, dict[str, Any]] = {}
    for family_name, missing_rows in missing_rows_by_family_name.items():
        donors = donor_rows_by_family_name.get(family_name, {})
        if len(donors) != 1:
            continue
        donor = next(iter(donors.values()))
        donor_payload = {
            "license_id": _clean_optional_text(donor.get("license_id")),
            "license_name": _clean_optional_text(donor.get("license_name")),
            "license_url": _clean_optional_text(donor.get("license_url")),
        }
        for row in missing_rows:
            updates[str(row["id"])] = donor_payload
    return updates


def _build_license_update(
    row: dict[str, Any],
    payload: dict[str, Any],
    *,
    authoritative: bool,
) -> dict[str, Any] | None:
    current_id = _clean_optional_text(row.get("license_id"))
    current_name = _clean_optional_text(row.get("license_name"))
    current_url = _clean_optional_text(row.get("license_url"))
    next_id = _clean_optional_text(payload.get("license_id"))
    next_name = _clean_optional_text(payload.get("license_name"))
    next_url = _clean_optional_text(payload.get("license_url"))

    update_values: dict[str, Any] = {}
    if authoritative:
        if current_id != next_id:
            update_values["license_id"] = next_id
        if current_name != next_name:
            update_values["license_name"] = next_name
        if current_url != next_url:
            update_values["license_url"] = next_url
        return update_values or None

    if not (current_id or current_name):
        if current_id != next_id:
            update_values["license_id"] = next_id
        if current_name != next_name:
            update_values["license_name"] = next_name
        if current_url != next_url and next_url:
            update_values["license_url"] = next_url
        return update_values or None

    current_signature = (current_id or "", current_name or "")
    next_signature = (next_id or "", next_name or "")
    if current_signature == next_signature and not current_url and next_url:
        update_values["license_url"] = next_url
    return update_values or None


def _apply_model_update(
    conn: Connection,
    row_by_id: dict[str, dict[str, Any]],
    model_id: str,
    update_values: dict[str, Any],
) -> None:
    conn.execute(update(models).where(models.c.id == model_id).values(**update_values))
    row_by_id[model_id] = {**row_by_id[model_id], **update_values}


def _has_license(row: dict[str, Any]) -> bool:
    return bool(_clean_optional_text(row.get("license_id")) or _clean_optional_text(row.get("license_name")))


def _license_signature(row: dict[str, Any]) -> tuple[str, str] | None:
    license_id = _clean_optional_text(row.get("license_id")) or ""
    license_name = _clean_optional_text(row.get("license_name")) or ""
    if not (license_id or license_name):
        return None
    return (license_id.casefold(), license_name.casefold())


def _license_completeness(row: dict[str, Any]) -> tuple[int, int, int]:
    license_id = int(bool(_clean_optional_text(row.get("license_id"))))
    license_name = int(bool(_clean_optional_text(row.get("license_name"))))
    license_url = int(bool(_clean_optional_text(row.get("license_url"))))
    return (license_id + license_name + license_url, license_url, license_name)


def _is_proprietary_license(row: dict[str, Any]) -> bool:
    license_id = (_clean_optional_text(row.get("license_id")) or "").casefold()
    license_name = (_clean_optional_text(row.get("license_name")) or "").casefold()
    return license_id == PROPRIETARY_LICENSE_ID or license_name == PROPRIETARY_LICENSE_NAME.casefold()


__all__ = [
    "LICENSE_POLICY_COMMERCIAL_BLOCKED",
    "LICENSE_POLICY_COMMERCIAL_CLEAR",
    "LICENSE_POLICY_LABELS",
    "LICENSE_POLICY_NOTES",
    "LICENSE_POLICY_POTENTIAL_LEGAL_REVIEW",
    "MODEL_LICENSE_BASELINE_PATH",
    "PROPRIETARY_LICENSE_ID",
    "PROPRIETARY_LICENSE_NAME",
    "apply_inferred_model_licenses",
    "apply_model_license_baseline",
    "build_license_policy_payload",
    "classify_license_policy",
    "load_model_license_baseline",
]
