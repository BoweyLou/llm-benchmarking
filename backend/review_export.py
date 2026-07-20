"""Readable, one-row-per-model AU-first review exports."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import json
import re
from typing import Any, Iterable, Mapping, Sequence
import unicodedata
import zipfile

from .inference_locations import get_inference_country_from_region
from .review_workbench import build_review_catalog


MODEL_FIELDS = [
    "Model",
    "Provider",
    "Roles",
    "Approval",
    "Recommendation",
    "Classification",
    "Last review update",
    "Suggested uses",
    "Australian inference and pricing",
    "Overseas inference and pricing",
    "Review notes and caveats",
    "Model ID",
]

INFERENCE_COST_FIELDS = [
    "model_group_id",
    "model_name",
    "source_record_id",
    "destination_id",
    "destination_name",
    "hyperscaler",
    "location_country",
    "location_region",
    "location_evidence",
    "availability_evidence_kind",
    "availability_catalog_model_id",
    "availability_synced_at",
    "availability_scope",
    "availability_note",
    "location_scope",
    "deployment_modes",
    "availability_source_urls",
    "offer_id",
    "provider_model_id",
    "service_tier",
    "currency",
    "price_status",
    "price_evidence_state",
    "pricing_is_stale",
    "constraints",
    "modality",
    "charge_type",
    "amount",
    "billing_unit",
    "unit_quantity",
    "conditions",
    "source_kind",
    "source_label",
    "source_url",
    "verified_at",
]

_ARCHIVE_MEMBERS = ("model-guide.csv", "README.txt")
_DANGEROUS_CELL_PREFIXES = frozenset("=+-@")

_STATUS_LABELS = {
    "approved": "Approved",
    "not_approved": "Not Approved",
    "unreviewed": "Not Reviewed",
    "recommended": "Recommended",
    "acceptable": "Acceptable",
    "legacy_supported": "Legacy Supported",
    "not_recommended": "Not Recommended",
    "unrated": "Not Assessed",
    "standard": "Standard",
    "restricted": "Restricted",
    "prohibited": "Prohibited",
    "unclassified": "Unclassified",
    "mixed": "Mixed",
}


@dataclass(frozen=True)
class ModelGuideArchive:
    """One deterministic ZIP archive and its export summary."""

    content: bytes
    filename: str
    model_count: int
    source_record_count: int
    inference_cost_row_count: int


def export_model_guide(
    *,
    model_ids: Sequence[str] | None = None,
    exported_at: str | None = None,
) -> ModelGuideArchive:
    """Build an archive from the current read-only review catalog."""

    return build_model_guide_archive(
        catalog=build_review_catalog(),
        model_ids=model_ids,
        exported_at=exported_at,
    )


def build_model_guide_archive(
    *,
    catalog: Mapping[str, Any],
    model_ids: Sequence[str] | None = None,
    exported_at: str | None = None,
) -> ModelGuideArchive:
    """Return a deterministic, spreadsheet-safe model-guide ZIP."""

    timestamp = _normalized_exported_at(exported_at)
    selected_models = _select_models(catalog.get("models"), model_ids)
    groups = _group_models(selected_models)
    cost_rows_by_group = {
        str(group["id"]): _inference_cost_rows(group)
        for group in groups
    }
    model_rows = [
        _model_row(group, cost_rows_by_group[str(group["id"])])
        for group in groups
    ]
    cost_rows = [
        row
        for group in groups
        for row in cost_rows_by_group[str(group["id"])]
    ]

    members = {
        "model-guide.csv": _render_csv(MODEL_FIELDS, model_rows),
        "README.txt": _render_readme(timestamp),
    }
    content = _render_zip(members, timestamp)
    return ModelGuideArchive(
        content=content,
        filename=f"llm-model-guide-{_filename_timestamp(timestamp)}.zip",
        model_count=len(groups),
        source_record_count=len(selected_models),
        inference_cost_row_count=len(cost_rows),
    )


def _select_models(value: Any, model_ids: Sequence[str] | None) -> list[dict[str, Any]]:
    models = [dict(model) for model in value or [] if isinstance(model, Mapping)]
    if model_ids is None:
        return models

    requested = {str(model_id).strip() for model_id in model_ids if str(model_id).strip()}
    if not requested:
        raise ValueError("At least one model id is required when model_ids is provided.")

    selected = [model for model in models if str(model.get("id") or "") in requested]
    found = {str(model.get("id") or "") for model in selected}
    unknown = sorted(requested - found)
    if unknown:
        raise ValueError(f"Model not found: {unknown[0]}")
    return selected


def _group_models(models: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        group_id = _review_entity_id(model)
        buckets.setdefault(group_id, []).append(model)

    groups = [
        {
            "id": group_id,
            "representative": members[0],
            "members": members,
        }
        for group_id, members in buckets.items()
    ]
    groups.sort(
        key=lambda group: (
            str(group["representative"].get("provider") or "").casefold(),
            str(group["representative"].get("name") or "").casefold(),
            str(group["id"]),
        )
    )
    return groups


def _review_entity_id(model: Mapping[str, Any]) -> str:
    existing = str(model.get("review_entity_id") or "").strip()
    if existing:
        return existing
    model_id = str(model.get("id") or "<unknown>").strip()
    raise ValueError(
        f"Model {model_id} is missing its server-owned review_entity_id."
    )


def _model_row(group: Mapping[str, Any], cost_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    representative = group["representative"]
    members = list(group["members"])
    providers = sorted(
        {
            str(member.get("provider") or "").strip()
            for member in members
            if str(member.get("provider") or "").strip()
        },
        key=str.casefold,
    )
    suggestions = _group_suggestions(members)
    approval = _unanimous_status(members, _approval_status, "unreviewed")
    recommendation = _unanimous_status(
        members,
        _recommendation_status,
        "unrated",
    )
    classification = _unanimous_status(
        members,
        _usage_classification,
        "unclassified",
    )
    return {
        "Model": representative.get("name") or representative.get("canonical_model_name"),
        "Provider": providers[0] if len(providers) == 1 else "Multiple providers",
        "Roles": _join_values(
            sorted(
                {
                    _human_label(role)
                    for member in members
                    for role in member.get("model_roles") or []
                    if str(role).strip()
                }
            )
        ),
        "Approval": _status_label(approval),
        "Recommendation": _status_label(recommendation),
        "Classification": _status_label(classification),
        "Last review update": _latest_review_update(members),
        "Suggested uses": _join_values(item.get("label") for item in suggestions),
        "Australian inference and pricing": _inference_and_pricing_summary(
            cost_rows,
            australia=True,
        ),
        "Overseas inference and pricing": _inference_and_pricing_summary(
            cost_rows,
            australia=False,
        ),
        "Review notes and caveats": _review_notes_and_caveats(members, cost_rows),
        "Model ID": group["id"],
    }


def _status_label(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    return _STATUS_LABELS.get(normalized, _human_label(normalized))


def _human_label(value: Any) -> str:
    text = str(value or "").strip().replace("_", " ")
    if not text:
        return ""
    words: list[str] = []
    for index, word in enumerate(text.split()):
        normalized = word.casefold()
        if normalized in {"api", "ocr"}:
            words.append(normalized.upper())
        elif index and normalized in {"and", "of", "to"}:
            words.append(normalized)
        else:
            words.append(word.title())
    return " ".join(words)


def _latest_review_update(models: Sequence[Mapping[str, Any]]) -> str:
    updates: list[tuple[str, str]] = []
    for model in models:
        for field, label in (
            ("general_approval_updated_at", "Approval"),
            ("general_recommendation_updated_at", "Recommendation"),
            ("usage_classification_updated_at", "Classification"),
        ):
            value = str(model.get(field) or "").strip()
            if value:
                updates.append((value, label))
    if not updates:
        return "Not reviewed"
    latest = max(value for value, _ in updates)
    labels = sorted({label for value, label in updates if value == latest})
    return f"{latest} ({', '.join(labels)})"


def _review_notes_and_caveats(
    models: Sequence[Mapping[str, Any]],
    cost_rows: Sequence[Mapping[str, Any]],
) -> str:
    parts: list[str] = []
    for field, label in (
        ("general_approval_notes", "Approval"),
        ("general_recommendation_notes", "Recommendation"),
        ("usage_classification_notes", "Classification"),
    ):
        notes = _join_values(model.get(field) for model in models)
        if notes:
            parts.append(f"{label}: {notes}")
    warning = _pricing_warning(cost_rows)
    if warning:
        parts.append(warning)
    return _join_values(parts)


def _approval_status(model: Mapping[str, Any]) -> str:
    explicit = str(model.get("general_approval_status") or "").strip().lower()
    if explicit:
        return explicit
    if bool(model.get("general_approved_for_use")):
        return "approved"
    if str(model.get("general_approval_updated_at") or "").strip():
        return "not_approved"
    return "unreviewed"


def _recommendation_status(model: Mapping[str, Any]) -> str:
    status = str(model.get("general_recommendation_status") or "unrated").strip().lower()
    return "not_recommended" if status == "discouraged" else status


def _usage_classification(model: Mapping[str, Any]) -> str:
    return str(model.get("usage_classification") or "unclassified").strip().lower()


def _unanimous_status(
    models: Sequence[Mapping[str, Any]],
    getter: Any,
    fallback: str,
) -> str:
    values = {getter(model) for model in models}
    return next(iter(values)) if len(values) == 1 else ("mixed" if values else fallback)


def _group_suggestions(models: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    suggestions: dict[str, dict[str, Any]] = {}
    for model in models:
        for raw in model.get("suggested_use_cases") or []:
            if not isinstance(raw, Mapping):
                continue
            item = dict(raw)
            key = str(item.get("use_case_id") or item.get("id") or item.get("label") or "").strip()
            if not key:
                continue
            current = suggestions.get(key)
            if current is None or _numeric(item.get("fit_score")) > _numeric(current.get("fit_score")):
                suggestions[key] = item
    return sorted(
        suggestions.values(),
        key=lambda item: (
            -_numeric(item.get("fit_score")),
            -_numeric(item.get("confidence")),
            str(item.get("label") or item.get("use_case_id") or "").casefold(),
        ),
    )


def _suggestion_evidence(item: Mapping[str, Any]) -> str:
    label = str(item.get("label") or item.get("use_case_id") or "Suggested use case")
    parts = [f"fit {_number_text(item.get('fit_score'))}"]
    if item.get("confidence") is not None:
        parts.append(f"confidence {_number_text(item.get('confidence'))}")
    if item.get("policy_version"):
        parts.append(f"policy {item['policy_version']}")
    if item.get("computed_at"):
        parts.append(f"computed {item['computed_at']}")
    return f"{label}: " + "; ".join(parts)


def _inference_cost_rows(group: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for member in group["members"]:
        for raw_destination in member.get("inference_destinations") or []:
            if isinstance(raw_destination, Mapping):
                rows.extend(_destination_cost_rows(group, member, raw_destination))

    if not rows:
        rows.append(_no_known_route_row(group))
    rows.sort(key=_cost_row_sort_key)
    return rows


def _destination_cost_rows(
    group: Mapping[str, Any],
    member: Mapping[str, Any],
    destination: Mapping[str, Any],
) -> list[dict[str, Any]]:
    destination_id = str(destination.get("id") or "").strip()
    pricing_only = (
        str(destination.get("availability_evidence_kind") or "").casefold()
        == "pricing_only"
    )
    regions = sorted(
        {
            str(region).strip()
            for region in destination.get("regions") or []
            if str(region).strip()
        },
        key=str.casefold,
    )
    offers = [
        dict(offer)
        for offer in destination.get("pricing_offers") or []
        if isinstance(offer, Mapping)
        and str(offer.get("destination_id") or "").strip() == destination_id
    ]
    consumed: set[int] = set()
    rows: list[dict[str, Any]] = []

    for region in regions:
        matching = [
            (index, offer)
            for index, offer in enumerate(offers)
            if str(offer.get("region") or "").strip().casefold() == region.casefold()
        ]
        if matching:
            for index, offer in matching:
                consumed.add(index)
                rows.extend(
                    _offer_cost_rows(
                        group,
                        member,
                        destination,
                        offer,
                        region=region,
                        country=_country_for_region(region),
                        location_evidence=(
                            "price_only" if pricing_only else "availability_and_price"
                        ),
                    )
                )
        else:
            rows.append(
                _availability_only_row(
                    group,
                    member,
                    destination,
                    region=region,
                    country=_country_for_region(region),
                    location_evidence=(
                        "price_only" if pricing_only else "availability_only"
                    ),
                )
            )

    for index, offer in enumerate(offers):
        if index in consumed:
            continue
        region = str(offer.get("region") or "").strip()
        rows.extend(
            _offer_cost_rows(
                group,
                member,
                destination,
                offer,
                region=region,
                country=_country_for_region(region),
                location_evidence="price_only",
            )
        )

    if not regions:
        location_scope = str(destination.get("location_scope") or "").strip()
        normalized_scope = location_scope.casefold()
        if normalized_scope == "provider managed":
            country = "Provider managed"
        elif normalized_scope == "provider routed":
            country = "Provider routed"
        else:
            country = "Unknown"
        if not pricing_only or not offers:
            rows.append(
                _availability_only_row(
                    group,
                    member,
                    destination,
                    region="",
                    country=country,
                    location_evidence=("price_only" if pricing_only else "availability_only"),
                )
            )
    return rows


def _offer_cost_rows(
    group: Mapping[str, Any],
    member: Mapping[str, Any],
    destination: Mapping[str, Any],
    offer: Mapping[str, Any],
    *,
    region: str,
    country: str,
    location_evidence: str,
) -> list[dict[str, Any]]:
    components = [
        dict(component)
        for component in offer.get("components") or []
        if isinstance(component, Mapping)
    ] or [{}]
    provenance = offer.get("provenance")
    if not isinstance(provenance, Mapping):
        provenance = {}
    state = _price_evidence_state(offer)
    base = _cost_row_base(group, member, destination, region=region, country=country)
    return [
        {
            **base,
            "location_evidence": location_evidence,
            "offer_id": offer.get("id"),
            "provider_model_id": offer.get("provider_model_id"),
            "service_tier": offer.get("service_tier"),
            "currency": offer.get("currency"),
            "price_status": offer.get("price_status"),
            "price_evidence_state": state,
            "pricing_is_stale": bool(provenance.get("stale")),
            "constraints": offer.get("constraints") or {},
            "modality": component.get("modality"),
            "charge_type": component.get("charge_type"),
            "amount": component.get("amount"),
            "billing_unit": component.get("billing_unit"),
            "unit_quantity": component.get("unit_quantity"),
            "conditions": component.get("conditions") or {},
            "source_kind": provenance.get("kind"),
            "source_label": provenance.get("label"),
            "source_url": provenance.get("url"),
            "verified_at": provenance.get("verified_at"),
        }
        for component in components
    ]


def _availability_only_row(
    group: Mapping[str, Any],
    member: Mapping[str, Any],
    destination: Mapping[str, Any],
    *,
    region: str,
    country: str,
    location_evidence: str = "availability_only",
) -> dict[str, Any]:
    return {
        **_cost_row_base(group, member, destination, region=region, country=country),
        "location_evidence": location_evidence,
        "offer_id": "",
        "provider_model_id": "",
        "service_tier": "",
        "currency": "",
        "price_status": "",
        "price_evidence_state": (
            "price_only" if location_evidence == "price_only" else "availability_only"
        ),
        "pricing_is_stale": "",
        "constraints": {},
        "modality": "",
        "charge_type": "",
        "amount": "",
        "billing_unit": "",
        "unit_quantity": "",
        "conditions": {},
        "source_kind": "",
        "source_label": "",
        "source_url": "",
        "verified_at": "",
    }


def _cost_row_base(
    group: Mapping[str, Any],
    member: Mapping[str, Any],
    destination: Mapping[str, Any],
    *,
    region: str,
    country: str,
) -> dict[str, Any]:
    representative = group["representative"]
    sources = destination.get("sources") or []
    source_urls = [
        _source_reference(source)
        for source in sources
        if isinstance(source, Mapping) and _source_reference(source)
    ]
    return {
        "model_group_id": group["id"],
        "model_name": representative.get("name") or representative.get("canonical_model_name"),
        "source_record_id": member.get("id"),
        "destination_id": destination.get("id"),
        "destination_name": destination.get("name"),
        "hyperscaler": destination.get("hyperscaler"),
        "location_country": country,
        "location_region": region,
        "location_evidence": "",
        "availability_evidence_kind": destination.get("availability_evidence_kind"),
        "availability_catalog_model_id": destination.get("catalog_model_id"),
        "availability_synced_at": destination.get("synced_at"),
        "availability_scope": destination.get("availability_scope"),
        "availability_note": destination.get("availability_note"),
        "location_scope": destination.get("location_scope"),
        "deployment_modes": _join_values(destination.get("deployment_modes") or []),
        "availability_source_urls": _join_values(source_urls),
    }


def _no_known_route_row(group: Mapping[str, Any]) -> dict[str, Any]:
    representative = group["representative"]
    member = group["members"][0]
    row = {field: "" for field in INFERENCE_COST_FIELDS}
    row.update(
        {
            "model_group_id": group["id"],
            "model_name": representative.get("name")
            or representative.get("canonical_model_name"),
            "source_record_id": member.get("id"),
            "location_country": "Unknown",
            "location_evidence": "no_known_route",
            "price_evidence_state": "no_known_route",
        }
    )
    return row


def _price_evidence_state(offer: Mapping[str, Any]) -> str:
    status = str(offer.get("price_status") or "").strip().casefold()
    if status in {"unavailable", "custom", "free"}:
        return status
    return "current"


def _country_for_region(region: str) -> str:
    return get_inference_country_from_region(region) or "Unknown"


def _source_reference(source: Mapping[str, Any]) -> str:
    label = str(source.get("label") or "").strip()
    url = str(source.get("url") or "").strip()
    if label and url:
        return f"{label}: {url}"
    return label or url


def _cost_row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    country = str(row.get("location_country") or "Unknown")
    special_rank = {
        "Australia": 0,
        "Global": 2,
        "Provider managed": 3,
        "Provider routed": 4,
        "Unknown": 5,
    }
    country_rank = special_rank.get(country, 1)
    state_rank = {
        "current": 0,
        "free": 1,
        "unavailable": 2,
        "custom": 3,
        "availability_only": 4,
        "price_only": 5,
        "no_known_route": 6,
    }.get(str(row.get("price_evidence_state") or ""), 8)
    return (
        country_rank,
        country.casefold(),
        str(row.get("destination_name") or "").casefold(),
        str(row.get("location_region") or "").casefold(),
        str(row.get("source_record_id") or ""),
        state_rank,
        _sortable_identifier(row.get("offer_id")),
        str(row.get("charge_type") or ""),
    )


def _sortable_identifier(value: Any) -> tuple[int, Any]:
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value or ""))


def _inference_and_pricing_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    australia: bool,
) -> str:
    scoped_rows = [
        row
        for row in rows
        if (str(row.get("location_country") or "Unknown") == "Australia") == australia
        and row.get("location_evidence") != "no_known_route"
    ]
    scope_label = "Australian" if australia else "overseas"
    if not scoped_rows:
        return f"No known {scope_label} inference route or price."

    availability: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in scoped_rows:
        if row.get("location_evidence") not in {"availability_only", "availability_and_price"}:
            continue
        destination_id = str(row.get("destination_id") or "")
        destination = str(row.get("destination_name") or destination_id or "Route")
        evidence_kind = str(row.get("availability_evidence_kind") or "").casefold()
        key = (destination_id, destination, evidence_kind)
        entry = availability.setdefault(key, {"locations": set(), "checked": set()})
        entry["locations"].add(_location_label(row, australia=australia))
        checked = str(row.get("availability_synced_at") or "").strip()
        if checked:
            entry["checked"].add(checked)

    component_pairs: dict[tuple[str, ...], dict[str, Mapping[str, Any]]] = {}
    for row in scoped_rows:
        if row.get("location_evidence") not in {"availability_and_price", "price_only"}:
            continue
        if bool(row.get("pricing_is_stale")):
            continue
        if row.get("price_evidence_state") not in {"current", "free"}:
            continue
        if str(row.get("service_tier") or "").casefold() != "standard":
            continue
        if str(row.get("modality") or "").casefold() != "text":
            continue
        charge_type = str(row.get("charge_type") or "").casefold()
        if charge_type not in {"input", "output"}:
            continue
        key = tuple(
            str(row.get(field) or "")
            for field in (
                "source_record_id",
                "destination_id",
                "location_country",
                "location_region",
                "offer_id",
                "currency",
                "billing_unit",
                "unit_quantity",
                "location_evidence",
                "availability_evidence_kind",
                "price_evidence_state",
            )
        )
        component_pairs.setdefault(key, {})[charge_type] = row

    price_groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for pair in component_pairs.values():
        if set(pair) != {"input", "output"}:
            continue
        input_row = pair["input"]
        output_row = pair["output"]
        destination_id = str(input_row.get("destination_id") or "")
        destination = str(input_row.get("destination_name") or destination_id or "Route")
        evidence_kind = str(input_row.get("availability_evidence_kind") or "").casefold()
        location_evidence = str(input_row.get("location_evidence") or "")
        key = (
            destination_id,
            destination,
            str(input_row.get("currency") or ""),
            str(input_row.get("billing_unit") or ""),
            str(input_row.get("unit_quantity") or ""),
            location_evidence,
            evidence_kind,
            str(input_row.get("price_evidence_state") or ""),
        )
        entry = price_groups.setdefault(
            key,
            {
                "locations": set(),
                "inputs": [],
                "outputs": [],
                "checked": set(),
                "quantity": input_row.get("unit_quantity"),
            },
        )
        entry["locations"].add(_location_label(input_row, australia=australia))
        entry["inputs"].append(input_row.get("amount"))
        entry["outputs"].append(output_row.get("amount"))
        for row in (input_row, output_row):
            checked = str(row.get("verified_at") or "").strip()
            if checked:
                entry["checked"].add(checked)

    summaries: list[str] = []
    priced_routes: set[tuple[str, str]] = set()
    for key, entry in price_groups.items():
        (
            destination_id,
            destination,
            currency,
            billing_unit,
            _quantity_key,
            location_evidence,
            evidence_kind,
            price_state,
        ) = key
        if location_evidence != "price_only":
            route = availability.get((destination_id, destination, evidence_kind))
            if route:
                entry["locations"].update(route["locations"])
                entry["checked"].update(route["checked"])
            priced_routes.add((destination_id, evidence_kind))
        prices = (
            f"{currency} {_number_range_text(entry['inputs'])} input / "
            f"{_number_range_text(entry['outputs'])} output per "
            f"{_quantity_text(entry['quantity'])} {_billing_unit_label(billing_unit, entry['quantity'])}"
        )
        if price_state == "free":
            prices = f"Free ({prices})"
        evidence = _readable_evidence(
            location_evidence=location_evidence,
            availability_evidence_kind=evidence_kind,
            checked_values=entry["checked"],
        )
        summaries.append(
            f"{destination} - {_summarize_locations(entry['locations'])} - {prices} [{evidence}]"
        )

    for (destination_id, destination, evidence_kind), entry in availability.items():
        if (destination_id, evidence_kind) in priced_routes:
            continue
        evidence = _readable_evidence(
            location_evidence="availability_only",
            availability_evidence_kind=evidence_kind,
            checked_values=entry["checked"],
        )
        summaries.append(
            f"{destination} - {_summarize_locations(entry['locations'])} - "
            f"Price not available [{evidence}]"
        )

    paired_destinations = {
        (key[0], key[2], key[5])
        for key in price_groups
    }
    generic_price_only: dict[tuple[str, str, str], set[str]] = {}
    for row in scoped_rows:
        if row.get("location_evidence") != "price_only":
            continue
        destination_id = str(row.get("destination_id") or "")
        currency = str(row.get("currency") or "")
        if (destination_id, currency, "price_only") in paired_destinations:
            continue
        destination = str(row.get("destination_name") or destination_id or "Route")
        generic_price_only.setdefault((destination_id, destination, currency), set()).add(
            _location_label(row, australia=australia)
        )
    for _destination_id, destination, currency in sorted(generic_price_only, key=lambda item: item[1].casefold()):
        locations = generic_price_only[(_destination_id, destination, currency)]
        currency_note = f" ({currency})" if currency else ""
        summaries.append(
            f"{destination} - {_summarize_locations(locations)} - Price details in catalog{currency_note} "
            "[price only; availability unconfirmed]"
        )

    if not summaries:
        return f"No known {scope_label} inference route or price."
    return " | ".join(sorted(set(summaries), key=str.casefold))


def _location_label(row: Mapping[str, Any], *, australia: bool) -> str:
    country = str(row.get("location_country") or "Unknown")
    region = str(row.get("location_region") or "").strip()
    if australia:
        return region or "Australia"
    return country if country != "Unknown" or not region else f"Unknown ({region})"


def _summarize_locations(values: Iterable[Any]) -> str:
    locations = sorted({str(value).strip() for value in values if str(value).strip()}, key=str.casefold)
    if not locations:
        return "Location unknown"
    if len(locations) <= 6:
        return ", ".join(locations)
    return ", ".join(locations[:5]) + f", +{len(locations) - 5} more"


def _readable_evidence(
    *,
    location_evidence: str,
    availability_evidence_kind: str,
    checked_values: Iterable[Any],
) -> str:
    if location_evidence == "price_only":
        label = "price only; availability unconfirmed"
    elif availability_evidence_kind == "synced":
        label = "confirmed route"
    elif availability_evidence_kind == "curated_fallback":
        label = "possible route; availability unconfirmed"
    else:
        label = "possible route; verify availability"
    checked = max((str(value) for value in checked_values if str(value)), default="")
    if checked:
        label += f"; checked {checked.split('T', 1)[0]}"
    return label


def _number_range_text(values: Iterable[Any]) -> str:
    numbers = sorted({float(value) for value in values})
    if not numbers:
        return ""
    if len(numbers) == 1:
        return _number_text(numbers[0])
    return f"{_number_text(numbers[0])}-{_number_text(numbers[-1])}"


def _billing_unit_label(value: Any, quantity: Any) -> str:
    label = str(value or "unit")
    try:
        plural = float(quantity) != 1
    except (TypeError, ValueError):
        plural = False
    if plural and not label.endswith("s"):
        label += "s"
    return label


def _pricing_warning(rows: Sequence[Mapping[str, Any]]) -> str:
    stale_offers = {
        (
            str(row.get("source_record_id") or ""),
            str(row.get("destination_id") or ""),
            str(row.get("offer_id") or ""),
        )
        for row in rows
        if bool(row.get("pricing_is_stale"))
    }
    count = len(stale_offers)
    if not count:
        return ""
    return f"{count} stale pricing offer{'s' if count != 1 else ''} excluded from current summaries."


def _join_values(values: Iterable[Any]) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _plain_text(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return "; ".join(result)


def _latest_text(values: Iterable[Any]) -> str:
    available = sorted(str(value).strip() for value in values if str(value or "").strip())
    return available[-1] if available else ""


def _numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _number_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    return str(int(number)) if number.is_integer() else format(number, ".12g")


def _quantity_text(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value or "")


def _normalized_exported_at(value: str | None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    else:
        text = str(value).strip()
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _filename_timestamp(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%SZ")


def _render_csv(fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(fields), lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                field: _spreadsheet_safe_text(_plain_text(row.get(field)))
                for field in fields
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return str(value)


def _spreadsheet_safe_text(value: str) -> str:
    parts = re.split(r"(\r\n|\r|\n)", value)
    for index in range(0, len(parts), 2):
        line = parts[index]
        prefix_end = 0
        while prefix_end < len(line):
            character = line[prefix_end]
            category = unicodedata.category(character)
            if not character.isspace() and category not in {"Cc", "Cf", "Zl", "Zp", "Zs"}:
                break
            prefix_end += 1
        if prefix_end < len(line) and line[prefix_end] in _DANGEROUS_CELL_PREFIXES:
            parts[index] = line[:prefix_end] + "'" + line[prefix_end:]
    return "".join(parts)


def _render_readme(timestamp: str) -> bytes:
    text = f"""LLM Model Guide export
Exported at: {timestamp}

model-guide.csv contains one readable row per server-owned review entity.
Approval, Recommendation, and Classification remain independent. Mixed means
the grouped source records disagree. Not Assessed means no recommendation
decision has been recorded; Acceptable means suitable for normal use but not
preferred.

Last review update is the newest approval, recommendation, or classification
timestamp and names the decision axis updated at that time. Suggested uses are
read-only metric evidence, not approval decisions. Legacy per-use-case decisions
are not included.

Australian and overseas inference columns combine route and price evidence.
Fresh standard-tier text input/output components are paired, duplicate source
records and equivalent regional offers are consolidated, and regional price
differences appear as ranges. Prices remain in provider-native currencies and
billing units. The export does not convert currencies or claim a globally
cheapest provider. Additional tiers, modalities, constraints, component-level
provenance, and historical evidence remain available in the review catalog/API.

Evidence labels are material. Confirmed route means synced availability evidence
exists. Possible route means curated fallback evidence and still requires account
and regional verification. Price only means a published price exists without
matched availability; it must never be read as confirmed access or data
residency. Stale prices are excluded from current summaries and reported in the
caveats column. Always verify account access, quota, residency controls, and
provider terms before procurement or deployment.
"""
    return text.encode("utf-8")


def _render_zip(members: Mapping[str, bytes], timestamp: str) -> bytes:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    date_time = (
        parsed.year,
        parsed.month,
        parsed.day,
        parsed.hour,
        parsed.minute,
        parsed.second,
    )
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as bundle:
        for member_name in _ARCHIVE_MEMBERS:
            info = zipfile.ZipInfo(member_name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            bundle.writestr(info, members[member_name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


__all__ = [
    "MODEL_FIELDS",
    "ModelGuideArchive",
    "build_model_guide_archive",
    "export_model_guide",
]
