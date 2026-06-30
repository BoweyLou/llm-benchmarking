"""Hyperscaler inference directory helpers.

Curated destinations remain as the fallback layer, but the UI now prefers
destinations synced from official cloud APIs whenever a hyperscaler has been
successfully refreshed and cached in the database.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.engine import Connection

from .database import (
    fetch_all,
    inference_sync_status as inference_sync_status_table,
    model_inference_destinations as model_inference_destinations_table,
)

AWS_LIST_MODELS_URL = "https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModels.html"
AWS_AVAILABILITY_URL = "https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GetFoundationModelAvailability.html"
AWS_PRICING_URL = "https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html"

AZURE_MODELS_URL = (
    "https://learn.microsoft.com/en-us/rest/api/aifoundry/accountmanagement/models/list"
    "?view=rest-aifoundry-accountmanagement-2025-06-01"
)
AZURE_PRICING_URL = "https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices"

GCP_MODELS_URL = "https://docs.cloud.google.com/vertex-ai/docs/reference/rest/v1beta1/publishers.models/list"
GCP_ENDPOINTS_URL = "https://docs.cloud.google.com/vertex-ai/docs/reference/rest"
GCP_PRICING_URL = "https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.prices/list"

DESTINATIONS: dict[str, dict[str, Any]] = {
    "aws-bedrock": {
        "id": "aws-bedrock",
        "name": "AWS Bedrock",
        "hyperscaler": "AWS",
        "availability_scope": "Account + region scoped",
        "availability_note": (
            "Bedrock model listings and entitlements vary by AWS account and region."
        ),
        "location_scope": "Common Bedrock regions",
        "regions": [
            "us-east-1",
            "us-west-2",
            "eu-west-1",
            "eu-central-1",
            "ap-southeast-1",
            "ap-southeast-2",
            "ap-northeast-1",
        ],
        "deployment_modes": ["On-demand", "Provisioned"],
        "pricing_label": "AWS Price List API",
        "pricing_note": "Destination-specific rates are published per region and usage type.",
        "sources": [
            {"label": "Catalog API", "url": AWS_LIST_MODELS_URL},
            {"label": "Availability API", "url": AWS_AVAILABILITY_URL},
            {"label": "Pricing API", "url": AWS_PRICING_URL},
        ],
    },
    "azure-ai-foundry": {
        "id": "azure-ai-foundry",
        "name": "Azure AI Foundry",
        "hyperscaler": "Azure",
        "availability_scope": "Account + deployment scoped",
        "availability_note": (
            "Foundry model access depends on the Cognitive Services account, chosen SKU, and deployment."
        ),
        "location_scope": "Common Foundry regions",
        "regions": [
            "eastus2",
            "westus3",
            "swedencentral",
            "francecentral",
            "uksouth",
            "australiaeast",
        ],
        "deployment_modes": ["Serverless", "Provisioned"],
        "pricing_label": "Azure Retail Prices API",
        "pricing_note": "Retail pricing is exposed by meter ID and region.",
        "sources": [
            {"label": "Catalog API", "url": AZURE_MODELS_URL},
            {"label": "Pricing API", "url": AZURE_PRICING_URL},
        ],
    },
    "google-vertex-ai": {
        "id": "google-vertex-ai",
        "name": "Google Vertex AI",
        "hyperscaler": "Google Cloud",
        "availability_scope": "Project + region scoped",
        "availability_note": (
            "Publisher-model access depends on the GCP project, region, and quota envelope."
        ),
        "location_scope": "Published Vertex endpoints",
        "regions": [
            "global",
            "us-central1",
            "us-east5",
            "europe-west4",
            "asia-southeast1",
            "australia-southeast1",
        ],
        "deployment_modes": ["Publisher model endpoint", "Regional endpoint"],
        "pricing_label": "Cloud Billing Catalog API",
        "pricing_note": "Public or billing-account pricing is published as Cloud Billing SKUs.",
        "sources": [
            {"label": "Catalog API", "url": GCP_MODELS_URL},
            {"label": "Endpoint docs", "url": GCP_ENDPOINTS_URL},
            {"label": "Pricing API", "url": GCP_PRICING_URL},
        ],
    },
}

PROVIDER_DESTINATIONS: dict[str, list[str]] = {
    "ai21-labs": ["aws-bedrock"],
    "amazon": ["aws-bedrock"],
    "anthropic": ["aws-bedrock"],
    "cohere": ["aws-bedrock"],
    "google": ["google-vertex-ai"],
    "google-deepmind": ["google-vertex-ai"],
    "meta": ["aws-bedrock", "azure-ai-foundry", "google-vertex-ai"],
    "meta-ai": ["aws-bedrock", "azure-ai-foundry", "google-vertex-ai"],
    "mistral": ["aws-bedrock", "azure-ai-foundry", "google-vertex-ai"],
    "mistral-ai": ["aws-bedrock", "azure-ai-foundry", "google-vertex-ai"],
    "openai": ["azure-ai-foundry"],
}

FAMILY_DESTINATION_ADDITIONS: dict[str, list[str]] = {
    "anthropic::claude-3": ["google-vertex-ai"],
    "anthropic::claude-3-5": ["google-vertex-ai"],
    "anthropic::claude-3-7": ["google-vertex-ai"],
    "anthropic::claude-4": ["google-vertex-ai"],
    "anthropic::claude-4-1": ["google-vertex-ai"],
    "anthropic::claude-4-5": ["google-vertex-ai"],
    "anthropic::claude-4-6": ["google-vertex-ai"],
}


def attach_inference_catalog(
    model: Mapping[str, Any],
    *,
    synced_destinations: list[Mapping[str, Any]] | None = None,
    authoritative_destinations: set[str] | None = None,
) -> dict[str, Any]:
    payload = dict(model)
    destinations = list_inference_destinations(
        model,
        synced_destinations=synced_destinations,
        authoritative_destinations=authoritative_destinations,
    )
    payload["inference_destinations"] = destinations
    payload["inference_summary"] = _build_summary(destinations)
    return payload


def list_inference_destinations(
    model: Mapping[str, Any],
    *,
    synced_destinations: list[Mapping[str, Any]] | None = None,
    authoritative_destinations: set[str] | None = None,
) -> list[dict[str, Any]]:
    curated_destinations = {
        destination["id"]: destination for destination in list_curated_inference_destinations(model)
    }
    live_destinations = {
        str(destination.get("id") or ""): _normalize_destination(destination)
        for destination in synced_destinations or []
        if str(destination.get("id") or "").strip()
    }
    authoritative_ids = set(authoritative_destinations or set())

    ordered_ids: list[str] = []
    for destination_id in curated_destinations:
        if destination_id in live_destinations:
            ordered_ids.append(destination_id)
            continue
        if destination_id not in authoritative_ids:
            ordered_ids.append(destination_id)

    for destination_id in live_destinations:
        if destination_id not in ordered_ids:
            ordered_ids.append(destination_id)

    return [
        live_destinations.get(destination_id) or curated_destinations[destination_id]
        for destination_id in ordered_ids
        if destination_id in live_destinations or destination_id in curated_destinations
    ]


def list_curated_inference_destinations(model: Mapping[str, Any]) -> list[dict[str, Any]]:
    provider_key = _slugify(str(model.get("provider") or ""))
    family_id = str(model.get("family_id") or "")

    destination_ids = list(PROVIDER_DESTINATIONS.get(provider_key, []))
    for family_prefix, additions in FAMILY_DESTINATION_ADDITIONS.items():
        if family_id.startswith(family_prefix):
            destination_ids.extend(additions)

    unique_destination_ids = list(dict.fromkeys(destination_ids))
    return [_materialize_destination(destination_id) for destination_id in unique_destination_ids]


def load_synced_inference_catalog(
    conn: Connection,
    model_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    if not model_ids:
        return {}

    rows = fetch_all(
        conn,
        select(model_inference_destinations_table)
        .where(model_inference_destinations_table.c.model_id.in_(model_ids))
        .order_by(
            model_inference_destinations_table.c.model_id.asc(),
            model_inference_destinations_table.c.destination_id.asc(),
        ),
    )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["model_id"])].append(
            _normalize_destination(
                {
                    "id": row["destination_id"],
                    "name": row["name"],
                    "hyperscaler": row["hyperscaler"],
                    "availability_scope": row["availability_scope"],
                    "availability_note": row.get("availability_note"),
                    "location_scope": row["location_scope"],
                    "regions": _parse_json_list(row.get("regions_json")),
                    "region_count": row.get("region_count"),
                    "deployment_modes": _parse_json_list(row.get("deployment_modes_json")),
                    "pricing_label": row.get("pricing_label"),
                    "pricing_note": row.get("pricing_note"),
                    "sources": _parse_json_list(row.get("sources_json")),
                    "catalog_model_id": row.get("catalog_model_id"),
                    "synced_at": row.get("synced_at"),
                }
            )
        )

    return dict(grouped)


def load_authoritative_destination_ids(conn: Connection) -> set[str]:
    rows = fetch_all(
        conn,
        select(inference_sync_status_table).where(inference_sync_status_table.c.last_completed_at.is_not(None)),
    )
    return {str(row["destination_id"]) for row in rows if str(row.get("destination_id") or "").strip()}


def _materialize_destination(destination_id: str) -> dict[str, Any]:
    record = DESTINATIONS[destination_id]
    return _normalize_destination(record)


def _normalize_destination(record: Mapping[str, Any]) -> dict[str, Any]:
    regions = _string_list(record.get("regions"))
    deployment_modes = _string_list(record.get("deployment_modes"))
    sources = _source_list(record.get("sources"))
    return {
        "id": str(record.get("id") or ""),
        "name": str(record.get("name") or ""),
        "hyperscaler": str(record.get("hyperscaler") or ""),
        "availability_scope": str(record.get("availability_scope") or ""),
        "availability_note": _clean_optional_text(record.get("availability_note")),
        "location_scope": str(record.get("location_scope") or ""),
        "regions": regions,
        "region_count": int(record.get("region_count") or len(regions)),
        "deployment_modes": deployment_modes,
        "pricing_label": _clean_optional_text(record.get("pricing_label")),
        "pricing_note": _clean_optional_text(record.get("pricing_note")),
        "sources": sources,
    }


def _build_summary(destinations: list[dict[str, Any]]) -> dict[str, Any]:
    deployment_modes = sorted(
        {
            mode
            for destination in destinations
            for mode in destination.get("deployment_modes", [])
            if isinstance(mode, str) and mode.strip()
        }
    )
    platform_names = [str(destination.get("name") or "") for destination in destinations if destination.get("name")]
    region_count = sum(int(destination.get("region_count") or 0) for destination in destinations)
    return {
        "destination_count": len(destinations),
        "region_count": region_count,
        "platform_names": platform_names,
        "deployment_modes": deployment_modes,
    }


def _parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = []
    return [str(item).strip() for item in candidates if str(item).strip()]


def _source_list(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    payload: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "").strip()
        url = str(item.get("url") or "").strip()
        if label and url:
            payload.append({"label": label, "url": url})
    return payload


def _clean_optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized


__all__ = [
    "AWS_AVAILABILITY_URL",
    "AWS_LIST_MODELS_URL",
    "AWS_PRICING_URL",
    "AZURE_MODELS_URL",
    "AZURE_PRICING_URL",
    "GCP_ENDPOINTS_URL",
    "GCP_MODELS_URL",
    "GCP_PRICING_URL",
    "DESTINATIONS",
    "attach_inference_catalog",
    "list_curated_inference_destinations",
    "list_inference_destinations",
    "load_authoritative_destination_ids",
    "load_synced_inference_catalog",
]
