"""Sync cached hyperscaler inference destinations from official cloud APIs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
from typing import Any, Iterable
from urllib.parse import quote, urlsplit

import httpx
from sqlalchemy import delete, select

from .database import (
    fetch_all,
    fetch_one,
    get_connection,
    get_engine,
    inference_sync_status as inference_sync_status_table,
    model_inference_destinations as model_inference_destinations_table,
    models as models_table,
    utc_now_iso,
)
from .inference_catalog import (
    AWS_AVAILABILITY_URL,
    AWS_LIST_MODELS_URL,
    AWS_PRICING_URL,
    AZURE_MODELS_URL,
    AZURE_PRICING_URL,
    DESTINATIONS,
    GCP_ENDPOINTS_URL,
    GCP_MODELS_URL,
    GCP_PRICING_URL,
    list_curated_inference_destinations,
)
from .model_taxonomy import infer_model_identity
from .name_resolution import name_signatures, normalize_text

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LLMBenchmarkingBot/0.1; +https://localhost)",
    "Accept": "application/json",
}
AWS_PRICING_INDEX_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/region_index.json"
AWS_PRICING_REGION_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/{region}/index.json"
AWS_DEFAULT_REGIONS = tuple(DESTINATIONS["aws-bedrock"]["regions"])
AZURE_RETAIL_PRICES_URL = "https://prices.azure.com/api/retail/prices"
GCP_BILLING_SERVICES_URL = "https://cloudbilling.googleapis.com/v1/services"
GCP_BILLING_SERVICE_SKUS_URL = "https://cloudbilling.googleapis.com/v1/services/{service_id}/skus"
GCP_DEFAULT_REGIONS = tuple(DESTINATIONS["google-vertex-ai"]["regions"])
GCP_PUBLISHER_MAP = {
    "anthropic": "anthropic",
    "cohere": "cohere",
    "google": "google",
    "googledeepmind": "google",
    "meta": "meta",
    "metaai": "meta",
    "mistral": "mistralai",
    "mistralai": "mistralai",
}
PROVIDER_EQUIVALENTS = {
    "googledeepmind": {"google", "googledeepmind", "deepmind"},
    "metaai": {"meta", "metaai"},
    "mistralai": {"mistral", "mistralai"},
}


class MissingConfiguration(RuntimeError):
    """Raised when a cloud sync cannot run without user-supplied credentials."""


@dataclass
class SyncOutcome:
    destination_id: str
    records: list[dict[str, Any]]
    detail: dict[str, Any]


def sync_inference_catalog(
    *,
    destination_ids: Iterable[str] | None = None,
    engine=None,
) -> dict[str, Any]:
    engine = engine or get_engine()
    selected = list(dict.fromkeys(destination_ids or DESTINATIONS.keys()))
    invalid = [destination_id for destination_id in selected if destination_id not in DESTINATIONS]
    if invalid:
        raise ValueError(f"Unknown inference destinations: {', '.join(sorted(invalid))}")

    with get_connection(engine) as conn:
        models = fetch_all(
            conn,
            select(models_table)
            .where(models_table.c.active == 1)
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )

    summary: dict[str, Any] = {"destinations": {}, "records_written": 0}
    with httpx.Client(timeout=45.0, headers=HTTP_HEADERS, follow_redirects=True) as client:
        for destination_id in selected:
            try:
                outcome = _sync_destination(destination_id, models, client)
            except MissingConfiguration as exc:
                summary["destinations"][destination_id] = {
                    "status": "skipped",
                    "reason": str(exc),
                }
                continue
            except Exception as exc:
                with engine.begin() as conn:
                    _write_sync_status(
                        conn,
                        destination_id,
                        status="failed",
                        detail={"error": str(exc)},
                        completed=False,
                    )
                summary["destinations"][destination_id] = {
                    "status": "failed",
                    "reason": str(exc),
                }
                continue

            with engine.begin() as conn:
                _replace_destination_records(conn, outcome.destination_id, outcome.records)
                _write_sync_status(
                    conn,
                    outcome.destination_id,
                    status="completed",
                    detail=outcome.detail,
                    completed=True,
                )

            summary["records_written"] += len(outcome.records)
            summary["destinations"][destination_id] = {
                "status": "completed",
                **outcome.detail,
            }

    return summary


def _sync_destination(
    destination_id: str,
    models: list[dict[str, Any]],
    client: httpx.Client,
) -> SyncOutcome:
    if destination_id == "aws-bedrock":
        return _sync_aws_bedrock(models, client)
    if destination_id == "azure-ai-foundry":
        return _sync_azure_foundry(models, client)
    if destination_id == "google-vertex-ai":
        return _sync_google_vertex_ai(models, client)
    raise ValueError(f"Unsupported inference destination: {destination_id}")


def _sync_aws_bedrock(models: list[dict[str, Any]], client: httpx.Client) -> SyncOutcome:
    pricing_index = _request_json(client, AWS_PRICING_INDEX_URL)
    published_regions = sorted(pricing_index.get("regions", {}).keys())
    configured_regions = _configured_regions("AWS_BEDROCK_REGIONS", published_regions or AWS_DEFAULT_REGIONS)

    price_entries: list[dict[str, Any]] = []
    publication_dates: list[str] = []
    for region in configured_regions:
        try:
            region_payload = _request_json(client, AWS_PRICING_REGION_URL.format(region=region))
        except httpx.HTTPError:
            continue
        publication_date = str(region_payload.get("publicationDate") or "").strip()
        if publication_date:
            publication_dates.append(publication_date)
        price_entries.extend(_parse_aws_price_entries(region_payload, region))

    credentials = _aws_credentials_from_env()
    catalog_entries: list[dict[str, Any]] = []
    catalog_regions_scanned = 0
    if credentials is not None:
        for region in configured_regions:
            try:
                catalog_entries.extend(_aws_list_foundation_models(client, region, credentials))
                catalog_regions_scanned += 1
            except httpx.HTTPError:
                continue

    records: list[dict[str, Any]] = []
    for model in models:
        matched_prices = [
            entry
            for entry in price_entries
            if _catalog_entry_matches_model(
                model,
                entry.get("provider"),
                entry.get("model_name"),
                entry.get("catalog_model_id"),
            )
        ]
        matched_catalog = [
            entry
            for entry in catalog_entries
            if _catalog_entry_matches_model(
                model,
                entry.get("provider"),
                entry.get("model_name"),
                entry.get("catalog_model_id"),
            )
        ]
        if not matched_prices and not matched_catalog:
            continue

        records.append(
            _build_destination_record(
                model_id=str(model["id"]),
                destination_id="aws-bedrock",
                name=DESTINATIONS["aws-bedrock"]["name"],
                hyperscaler=DESTINATIONS["aws-bedrock"]["hyperscaler"],
                availability_scope=(
                    "Account + region scoped" if matched_catalog else "Region scoped via live pricing"
                ),
                availability_note=_aws_availability_note(
                    matched_catalog=matched_catalog,
                    matched_prices=matched_prices,
                    publication_dates=publication_dates,
                    used_account_catalog=bool(credentials),
                ),
                location_scope="Live Bedrock regions" if matched_catalog else "Live Bedrock pricing regions",
                regions=_unique_sorted(
                    entry.get("region")
                    for entry in (matched_catalog or matched_prices)
                    if entry.get("region")
                ),
                deployment_modes=_aws_deployment_modes(matched_prices, matched_catalog),
                pricing_label=_pricing_label(
                    input_prices=[entry["price_per_mtok"] for entry in matched_prices if entry.get("price_kind") == "input"],
                    output_prices=[entry["price_per_mtok"] for entry in matched_prices if entry.get("price_kind") == "output"],
                    currency_code="USD",
                ),
                pricing_note=_aws_pricing_note(matched_prices, publication_dates),
                sources=[
                    {"label": "Catalog API", "url": AWS_LIST_MODELS_URL},
                    {"label": "Availability API", "url": AWS_AVAILABILITY_URL},
                    {"label": "Pricing API", "url": AWS_PRICING_URL},
                ],
                catalog_model_id=_first_non_empty(
                    entry.get("catalog_model_id") for entry in (matched_catalog or matched_prices)
                ),
            )
        )

    return SyncOutcome(
        destination_id="aws-bedrock",
        records=records,
        detail={
            "status": "completed",
            "mode": "account-catalog+pricing" if credentials is not None else "pricing-only",
            "model_count": len(records),
            "regions_scanned": len(configured_regions),
            "catalog_regions_scanned": catalog_regions_scanned,
        },
    )


def _sync_azure_foundry(models: list[dict[str, Any]], client: httpx.Client) -> SyncOutcome:
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    resource_group = os.getenv("AZURE_RESOURCE_GROUP")
    account_name = os.getenv("AZURE_AI_FOUNDRY_ACCOUNT") or os.getenv("AZURE_COGSERVICES_ACCOUNT")
    if not subscription_id or not resource_group or not account_name:
        return _sync_azure_foundry_public_pricing(models, client)

    try:
        token = _azure_access_token(client)
    except MissingConfiguration:
        return _sync_azure_foundry_public_pricing(models, client)
    azure_headers = {"Authorization": f"Bearer {token}"}
    models_url = (
        "https://management.azure.com/subscriptions/"
        f"{subscription_id}/resourceGroups/{resource_group}/providers/"
        f"Microsoft.CognitiveServices/accounts/{account_name}/models"
    )
    try:
        payload = _request_json(
            client,
            models_url,
            headers=azure_headers,
            params={"api-version": "2025-06-01"},
        )
    except httpx.HTTPError:
        return _sync_azure_foundry_public_pricing(models, client)
    account_models = list(_iterate_collection(payload, client, headers=azure_headers))

    meter_ids = sorted(
        {
            meter_id
            for entry in account_models
            for sku in _azure_model_skus(entry)
            for meter_id in _azure_sku_meter_ids(sku)
        }
    )
    price_index = _azure_price_index(client, meter_ids)

    records: list[dict[str, Any]] = []
    for model in models:
        matched_models = [
            entry
            for entry in account_models
            if _catalog_entry_matches_model(
                model,
                _azure_model_provider(entry),
                _azure_model_name(entry),
                _azure_model_resource_name(entry),
            )
        ]
        if not matched_models:
            continue

        matched_prices = [
            price
            for entry in matched_models
            for sku in _azure_model_skus(entry)
            for meter_id in _azure_sku_meter_ids(sku)
            for price in price_index.get(meter_id, [])
        ]
        deployment_modes = _azure_deployment_modes(matched_models)
        regions = _unique_sorted(
            price.get("armRegionName") or _azure_model_location(entry)
            for entry in matched_models
            for price in (matched_prices or [{}])
        )
        records.append(
            _build_destination_record(
                model_id=str(model["id"]),
                destination_id="azure-ai-foundry",
                name=DESTINATIONS["azure-ai-foundry"]["name"],
                hyperscaler=DESTINATIONS["azure-ai-foundry"]["hyperscaler"],
                availability_scope="Configured account + deployment scoped",
                availability_note=(
                    f"Live from Azure account {account_name}; SKU capacity and rate limits are account-scoped."
                ),
                location_scope="Configured Foundry account regions",
                regions=regions,
                deployment_modes=deployment_modes,
                pricing_label=_pricing_label(
                    input_prices=[
                        price["price_per_mtok"] for price in matched_prices if price.get("price_kind") == "input"
                    ],
                    output_prices=[
                        price["price_per_mtok"] for price in matched_prices if price.get("price_kind") == "output"
                    ],
                    currency_code="USD",
                ),
                pricing_note=_azure_pricing_note(matched_prices),
                sources=[
                    {"label": "Catalog API", "url": AZURE_MODELS_URL},
                    {"label": "Pricing API", "url": AZURE_PRICING_URL},
                ],
                catalog_model_id=_first_non_empty(_azure_model_resource_name(entry) for entry in matched_models),
            )
        )

    return SyncOutcome(
        destination_id="azure-ai-foundry",
        records=records,
        detail={
            "status": "completed",
            "mode": "account-catalog+pricing",
            "model_count": len(records),
            "account_name": account_name,
            "meter_count": len(meter_ids),
        },
    )


def _sync_azure_foundry_public_pricing(
    models: list[dict[str, Any]],
    client: httpx.Client,
) -> SyncOutcome:
    query_cache: dict[str, list[dict[str, Any]]] = {}
    records: list[dict[str, Any]] = []
    query_count = 0

    for model in models:
        if not _model_has_curated_destination(model, "azure-ai-foundry"):
            continue

        matched_prices: list[dict[str, Any]] = []
        for filter_expr in _azure_public_filters_for_model(model):
            if filter_expr not in query_cache:
                query_cache[filter_expr] = _azure_public_price_entries(client, filter_expr)
                query_count += 1
            matched_prices.extend(query_cache[filter_expr])

        matched_prices = [
            entry
            for entry in matched_prices
            if _catalog_entry_matches_model(
                model,
                entry.get("provider"),
                entry.get("product_name"),
                entry.get("sku_name"),
                entry.get("meter_name"),
                entry.get("derived_model_name"),
            )
        ]
        matched_prices = _dedupe_azure_public_entries(matched_prices)
        if not matched_prices:
            continue

        records.append(
            _build_destination_record(
                model_id=str(model["id"]),
                destination_id="azure-ai-foundry",
                name=DESTINATIONS["azure-ai-foundry"]["name"],
                hyperscaler=DESTINATIONS["azure-ai-foundry"]["hyperscaler"],
                availability_scope="Public retail pricing footprint",
                availability_note=(
                    "Derived from the public Azure Retail Prices API; not account-scoped and "
                    "does not confirm deployment entitlements."
                ),
                location_scope="Live Azure retail pricing regions",
                regions=_unique_sorted(
                    entry.get("armRegionName") for entry in matched_prices if entry.get("armRegionName")
                ),
                deployment_modes=_azure_public_deployment_modes(matched_prices),
                pricing_label=_pricing_label(
                    input_prices=[
                        entry["price_per_mtok"] for entry in matched_prices if entry.get("price_kind") == "input"
                    ],
                    output_prices=[
                        entry["price_per_mtok"] for entry in matched_prices if entry.get("price_kind") == "output"
                    ],
                    currency_code="USD",
                ),
                pricing_note=_azure_pricing_note(matched_prices, public_only=True),
                sources=[
                    {"label": "Catalog API", "url": AZURE_MODELS_URL},
                    {"label": "Pricing API", "url": AZURE_PRICING_URL},
                ],
                catalog_model_id=_first_non_empty(
                    entry.get("derived_model_name") or entry.get("meter_name") for entry in matched_prices
                ),
            )
        )

    return SyncOutcome(
        destination_id="azure-ai-foundry",
        records=records,
        detail={
            "status": "completed",
            "mode": "public-pricing-only",
            "model_count": len(records),
            "query_count": query_count,
        },
    )


def _sync_google_vertex_ai(models: list[dict[str, Any]], client: httpx.Client) -> SyncOutcome:
    token = os.getenv("GOOGLE_CLOUD_ACCESS_TOKEN") or os.getenv("GCP_ACCESS_TOKEN")
    if not token:
        return _sync_google_vertex_public_endpoints(models)

    gcp_headers = {"Authorization": f"Bearer {token}"}
    publishers = _vertex_publishers_for_models(models)
    regions = _configured_regions("GOOGLE_VERTEX_REGIONS", GCP_DEFAULT_REGIONS)
    publisher_models: list[dict[str, Any]] = []
    for region in regions:
        endpoint = _google_vertex_endpoint(region)
        for publisher in publishers:
            url = f"{endpoint}/v1beta1/publishers/{publisher}/models"
            try:
                payload = _request_json(client, url, headers=gcp_headers)
            except httpx.HTTPError:
                continue
            for entry in _extract_google_publisher_models(payload):
                entry["region"] = region
                entry["publisher"] = publisher
                publisher_models.append(entry)

    service_id = _google_vertex_service_id(client, gcp_headers)
    sku_entries = _google_vertex_skus(client, gcp_headers, service_id) if service_id else []

    records: list[dict[str, Any]] = []
    for model in models:
        matched_catalog = [
            entry
            for entry in publisher_models
            if _catalog_entry_matches_model(
                model,
                entry.get("provider"),
                entry.get("display_name"),
                entry.get("catalog_model_id"),
                entry.get("name"),
            )
        ]
        if not matched_catalog:
            continue

        matched_skus = [
            sku
            for sku in sku_entries
            if _catalog_entry_matches_model(
                model,
                sku.get("provider"),
                sku.get("display_name"),
                sku.get("description"),
                sku.get("catalog_model_id"),
            )
        ]
        records.append(
            _build_destination_record(
                model_id=str(model["id"]),
                destination_id="google-vertex-ai",
                name=DESTINATIONS["google-vertex-ai"]["name"],
                hyperscaler=DESTINATIONS["google-vertex-ai"]["hyperscaler"],
                availability_scope="Project + region scoped",
                availability_note="Live publisher-model catalog by probed Vertex AI endpoint region.",
                location_scope="Probed Vertex endpoints",
                regions=_unique_sorted(entry.get("region") for entry in matched_catalog if entry.get("region")),
                deployment_modes=_google_deployment_modes(matched_catalog),
                pricing_label=_pricing_label(
                    input_prices=[entry["price_per_mtok"] for entry in matched_skus if entry.get("price_kind") == "input"],
                    output_prices=[entry["price_per_mtok"] for entry in matched_skus if entry.get("price_kind") == "output"],
                    currency_code="USD",
                ),
                pricing_note=_google_pricing_note(matched_skus),
                sources=[
                    {"label": "Catalog API", "url": GCP_MODELS_URL},
                    {"label": "Endpoint docs", "url": GCP_ENDPOINTS_URL},
                    {"label": "Pricing API", "url": GCP_PRICING_URL},
                ],
                catalog_model_id=_first_non_empty(entry.get("catalog_model_id") for entry in matched_catalog),
            )
        )

    return SyncOutcome(
        destination_id="google-vertex-ai",
        records=records,
        detail={
            "status": "completed",
            "mode": "project-catalog+pricing",
            "model_count": len(records),
            "publisher_count": len(publishers),
            "regions_scanned": len(regions),
        },
    )


def _sync_google_vertex_public_endpoints(models: list[dict[str, Any]]) -> SyncOutcome:
    regions = _configured_regions("GOOGLE_VERTEX_REGIONS", GCP_DEFAULT_REGIONS)
    deployment_modes = _google_public_deployment_modes(regions)
    records: list[dict[str, Any]] = []

    for model in models:
        if not _model_has_curated_destination(model, "google-vertex-ai"):
            continue
        records.append(
            _build_destination_record(
                model_id=str(model["id"]),
                destination_id="google-vertex-ai",
                name=DESTINATIONS["google-vertex-ai"]["name"],
                hyperscaler=DESTINATIONS["google-vertex-ai"]["hyperscaler"],
                availability_scope="Published endpoint footprint",
                availability_note=(
                    "Derived from published Vertex AI endpoint regions plus curated provider/model routing; "
                    "does not confirm project access, quotas, or model enablement."
                ),
                location_scope="Published Vertex endpoints",
                regions=regions,
                deployment_modes=deployment_modes,
                pricing_label=None,
                pricing_note="Cloud Billing pricing and model availability require authenticated Google APIs.",
                sources=[
                    {"label": "Catalog API", "url": GCP_MODELS_URL},
                    {"label": "Endpoint docs", "url": GCP_ENDPOINTS_URL},
                    {"label": "Pricing API", "url": GCP_PRICING_URL},
                ],
                catalog_model_id=str(model.get("canonical_model_id") or model.get("family_id") or model["id"]),
            )
        )

    return SyncOutcome(
        destination_id="google-vertex-ai",
        records=records,
        detail={
            "status": "completed",
            "mode": "published-endpoints-only",
            "model_count": len(records),
            "regions_scanned": len(regions),
        },
    )


def _replace_destination_records(conn, destination_id: str, records: list[dict[str, Any]]) -> None:
    conn.execute(
        delete(model_inference_destinations_table).where(
            model_inference_destinations_table.c.destination_id == destination_id
        )
    )
    if not records:
        return
    conn.execute(model_inference_destinations_table.insert(), records)


def _write_sync_status(
    conn,
    destination_id: str,
    *,
    status: str,
    detail: dict[str, Any],
    completed: bool,
) -> None:
    existing = fetch_one(
        conn,
        select(inference_sync_status_table).where(inference_sync_status_table.c.destination_id == destination_id),
    )
    now = utc_now_iso()
    conn.execute(
        delete(inference_sync_status_table).where(inference_sync_status_table.c.destination_id == destination_id)
    )
    conn.execute(
        inference_sync_status_table.insert(),
        [
            {
                "destination_id": destination_id,
                "last_status": status,
                "last_attempted_at": now,
                "last_completed_at": now if completed else (existing or {}).get("last_completed_at"),
                "detail_json": json.dumps(detail, sort_keys=True),
            }
        ],
    )


def _build_destination_record(
    *,
    model_id: str,
    destination_id: str,
    name: str,
    hyperscaler: str,
    availability_scope: str,
    availability_note: str | None,
    location_scope: str,
    regions: list[str],
    deployment_modes: list[str],
    pricing_label: str | None,
    pricing_note: str | None,
    sources: list[dict[str, str]],
    catalog_model_id: str | None,
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "destination_id": destination_id,
        "name": name,
        "hyperscaler": hyperscaler,
        "availability_scope": availability_scope,
        "availability_note": availability_note,
        "location_scope": location_scope,
        "regions_json": json.dumps(regions),
        "region_count": len(regions),
        "deployment_modes_json": json.dumps(deployment_modes),
        "pricing_label": pricing_label,
        "pricing_note": pricing_note,
        "sources_json": json.dumps(sources),
        "catalog_model_id": catalog_model_id,
        "synced_at": utc_now_iso(),
    }


def _request_json(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.request(method, url, headers=headers, params=params, data=data)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _iterate_collection(
    payload: dict[str, Any],
    client: httpx.Client,
    *,
    headers: dict[str, str] | None = None,
) -> Iterable[dict[str, Any]]:
    current = payload
    while True:
        for key in ("value", "items", "Items", "models", "publisherModels", "services", "skus"):
            if isinstance(current.get(key), list):
                for item in current[key]:
                    if isinstance(item, dict):
                        yield item
                break
        next_link = current.get("nextLink") or current.get("NextPageLink") or current.get("nextPageToken")
        if not next_link:
            return
        if isinstance(next_link, str) and next_link.startswith("http"):
            current = _request_json(client, next_link, headers=headers)
            continue
        return


def _model_has_curated_destination(model: dict[str, Any], destination_id: str) -> bool:
    return any(
        destination.get("id") == destination_id
        for destination in list_curated_inference_destinations(model)
    )


def _configured_regions(env_name: str, default_regions: Iterable[str]) -> list[str]:
    raw = os.getenv(env_name, "")
    if not raw.strip():
        return list(dict.fromkeys(region.strip() for region in default_regions if region.strip()))
    regions = [region.strip() for region in raw.split(",") if region.strip()]
    return list(dict.fromkeys(regions))


def _aws_credentials_from_env() -> dict[str, str] | None:
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        return None
    return {
        "access_key": access_key,
        "secret_key": secret_key,
        "session_token": os.getenv("AWS_SESSION_TOKEN", ""),
    }


def _aws_list_foundation_models(
    client: httpx.Client,
    region: str,
    credentials: dict[str, str],
) -> list[dict[str, Any]]:
    url = f"https://bedrock.{region}.amazonaws.com/foundation-models"
    headers = _aws_sigv4_headers(
        method="GET",
        url=url,
        region=region,
        service="bedrock",
        access_key=credentials["access_key"],
        secret_key=credentials["secret_key"],
        session_token=credentials.get("session_token") or None,
    )
    payload = _request_json(client, url, headers=headers)
    records: list[dict[str, Any]] = []
    for item in payload.get("modelSummaries", []):
        if not isinstance(item, dict):
            continue
        records.append(
            {
                "region": region,
                "provider": item.get("providerName"),
                "model_name": item.get("modelName"),
                "catalog_model_id": item.get("modelId"),
                "deployment_modes": list(item.get("inferenceTypesSupported") or []),
            }
        )
    return records


def _aws_sigv4_headers(
    *,
    method: str,
    url: str,
    region: str,
    service: str,
    access_key: str,
    secret_key: str,
    session_token: str | None = None,
) -> dict[str, str]:
    payload_hash = hashlib.sha256(b"").hexdigest()
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    parsed = urlsplit(url)
    host = parsed.netloc
    canonical_uri = parsed.path or "/"
    canonical_querystring = parsed.query
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    headers = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if session_token:
        headers["x-amz-security-token"] = session_token
        canonical_headers += f"x-amz-security-token:{session_token}\n"
        signed_headers += ";x-amz-security-token"

    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _aws_signing_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return headers


def _aws_signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = hmac.new(f"AWS4{secret_key}".encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def _parse_aws_price_entries(payload: dict[str, Any], region: str) -> list[dict[str, Any]]:
    price_dimensions_by_sku = _aws_price_dimensions(payload)
    entries: list[dict[str, Any]] = []
    for sku, product in payload.get("products", {}).items():
        if not isinstance(product, dict):
            continue
        attrs = product.get("attributes", {}) or {}
        model_name = str(attrs.get("model") or "").strip()
        if not model_name:
            continue
        price_dimension = price_dimensions_by_sku.get(str(sku))
        if price_dimension is None:
            continue
        price_per_unit = _first_usd_price(price_dimension)
        if price_per_unit is None:
            continue
        unit = str(price_dimension.get("unit") or "").strip()
        price_per_mtok = _price_per_mtok(price_per_unit, unit)
        catalog_model_id = _clean_optional_text(attrs.get("modelId"))
        provider = _clean_optional_text(attrs.get("provider")) or _provider_from_model_name(model_name)
        entries.append(
            {
                "region": str(attrs.get("regionCode") or region),
                "provider": provider,
                "model_name": model_name,
                "catalog_model_id": catalog_model_id,
                "deployment_mode": _aws_inference_type_label(attrs.get("inferenceType")),
                "price_kind": _price_kind_from_text(
                    str(attrs.get("usagetype") or ""),
                    str(price_dimension.get("description") or ""),
                ),
                "price_per_mtok": price_per_mtok,
                "unit": unit,
            }
        )
    return entries


def _aws_price_dimensions(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    dimensions: dict[str, dict[str, Any]] = {}
    for term_name in ("OnDemand", "Reserved"):
        term_collection = payload.get("terms", {}).get(term_name, {})
        if not isinstance(term_collection, dict):
            continue
        for sku, offers in term_collection.items():
            if not isinstance(offers, dict):
                continue
            for offer in offers.values():
                if not isinstance(offer, dict):
                    continue
                price_dimensions = offer.get("priceDimensions", {}) or {}
                first_dimension = next(
                    (dimension for dimension in price_dimensions.values() if isinstance(dimension, dict)),
                    None,
                )
                if first_dimension is not None:
                    dimensions[str(sku)] = first_dimension
                    break
    return dimensions


def _azure_access_token(client: httpx.Client) -> str:
    inline_token = os.getenv("AZURE_ACCESS_TOKEN")
    if inline_token:
        return inline_token

    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    if not tenant_id or not client_id or not client_secret:
        raise MissingConfiguration(
            "Set AZURE_ACCESS_TOKEN or the AZURE_TENANT_ID/AZURE_CLIENT_ID/AZURE_CLIENT_SECRET trio."
        )
    payload = _request_json(
        client,
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        method="POST",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://management.azure.com/.default",
        },
    )
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise MissingConfiguration("Failed to obtain Azure access token.")
    return token


def _azure_model_name(entry: dict[str, Any]) -> str | None:
    model = entry.get("model")
    if isinstance(model, dict):
        return _clean_optional_text(model.get("name"))
    properties = entry.get("properties")
    if isinstance(properties, dict):
        inner_model = properties.get("model")
        if isinstance(inner_model, dict):
            return _clean_optional_text(inner_model.get("name"))
    return _clean_optional_text(entry.get("name"))


def _azure_model_provider(entry: dict[str, Any]) -> str | None:
    model = entry.get("model")
    if isinstance(model, dict):
        return _clean_optional_text(model.get("publisher") or model.get("provider"))
    properties = entry.get("properties")
    if isinstance(properties, dict):
        inner_model = properties.get("model")
        if isinstance(inner_model, dict):
            return _clean_optional_text(inner_model.get("publisher") or inner_model.get("provider"))
    return _clean_optional_text(entry.get("publisher"))


def _azure_model_resource_name(entry: dict[str, Any]) -> str | None:
    return _clean_optional_text(entry.get("id") or entry.get("name"))


def _azure_model_location(entry: dict[str, Any]) -> str | None:
    return _clean_optional_text(entry.get("location"))


def _azure_model_skus(entry: dict[str, Any]) -> list[dict[str, Any]]:
    for container in (entry, entry.get("properties") if isinstance(entry.get("properties"), dict) else None):
        if isinstance(container, dict) and isinstance(container.get("skus"), list):
            return [sku for sku in container["skus"] if isinstance(sku, dict)]
    return []


def _azure_sku_meter_ids(sku: dict[str, Any]) -> list[str]:
    cost = sku.get("cost")
    if not isinstance(cost, list):
        return []
    meter_ids = []
    for item in cost:
        if not isinstance(item, dict):
            continue
        meter_id = _clean_optional_text(item.get("meterId"))
        if meter_id:
            meter_ids.append(meter_id)
    return meter_ids


def _azure_price_index(client: httpx.Client, meter_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for meter_id in meter_ids:
        payload = _request_json(
            client,
            AZURE_RETAIL_PRICES_URL,
            params={
                "api-version": "2023-01-01-preview",
                "$filter": f"meterId eq '{meter_id}' and priceType eq 'Consumption'",
            },
        )
        items = payload.get("Items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            unit_price = _to_float(item.get("unitPrice"))
            if unit_price is None:
                continue
            unit = _clean_optional_text(item.get("unitOfMeasure")) or ""
            index[meter_id].append(
                {
                    "meterId": meter_id,
                    "meterName": item.get("meterName"),
                    "armRegionName": item.get("armRegionName"),
                    "price_kind": _price_kind_from_text(
                        str(item.get("meterName") or ""),
                        str(item.get("productName") or ""),
                        str(item.get("skuName") or ""),
                    ),
                    "price_per_mtok": _price_per_mtok(unit_price, unit),
                    "unit": unit,
                }
            )
    return index


def _azure_public_filters_for_model(model: dict[str, Any]) -> list[str]:
    provider_slug = _provider_slug(model.get("provider"))
    product_filter: str | None = None
    search_terms: list[str] = []

    if provider_slug == "openai":
        product_filter = "Azure OpenAI"
        search_terms.extend(_azure_openai_search_terms(model))
    elif provider_slug in {"meta", "metaai"}:
        product_filter = "Llama"
        search_terms.extend(_azure_generic_model_terms(model))
    elif provider_slug in {"mistral", "mistralai"}:
        product_filter = "Mistral"
        search_terms.extend(_azure_generic_model_terms(model))
    else:
        product_filter = None

    clauses = ["serviceName eq 'Foundry Models'"]
    if product_filter:
        clauses.append(f"contains(productName, '{product_filter}')")

    filters: list[str] = []
    if not search_terms:
        filters.append(" and ".join(clauses))
    for term in search_terms:
        filters.append(" and ".join([*clauses, f"contains(meterName, '{term}')"]))
    return list(dict.fromkeys(filters))


def _azure_openai_search_terms(model: dict[str, Any]) -> list[str]:
    raw_values = " ".join(
        str(model.get(key) or "")
        for key in ("name", "canonical_model_name", "family_name", "id", "family_id", "canonical_model_id")
    )
    normalized = normalize_text(raw_values)
    terms: list[str] = []
    version_match = _azure_openai_version(raw_values)
    if version_match:
        terms.append(version_match)
    if "codex" in normalized:
        terms.append("codex")
    if "mini" in normalized:
        terms.append("mini")
    if "nano" in normalized:
        terms.append("nano")
    if "pro" in normalized:
        terms.append("pro")
    return list(dict.fromkeys(terms))


def _azure_openai_version(value: str) -> str | None:
    lowered = value.lower()
    for pattern in (
        r"gpt[-\s]?(\d+(?:[.-]\d+)?o?)",
        r"\b(\d+(?:[.-]\d+)?o?)\b",
    ):
        match = re.search(pattern, lowered)
        if not match:
            continue
        token = match.group(1).replace("-", ".")
        if token in {"5", "5.1", "5.4", "4", "4.1", "4o"}:
            return token
    return None


def _azure_generic_model_terms(model: dict[str, Any]) -> list[str]:
    values = [
        str(model.get("canonical_model_name") or ""),
        str(model.get("family_name") or ""),
        str(model.get("name") or ""),
    ]
    normalized = normalize_text(" ".join(values))
    terms: list[str] = []
    for token in normalized.split():
        if token in {"llama", "mistral", "models", "model", "azure"}:
            continue
        if token and (any(char.isdigit() for char in token) or len(token) > 4):
            terms.append(token.upper() if token.endswith("b") else token)
    return list(dict.fromkeys(terms))


def _azure_public_price_entries(client: httpx.Client, filter_expr: str) -> list[dict[str, Any]]:
    payload = _request_json(
        client,
        AZURE_RETAIL_PRICES_URL,
        params={
            "api-version": "2023-01-01-preview",
            "$filter": filter_expr,
        },
    )
    items = list(_iterate_collection(payload, client))
    entries: list[dict[str, Any]] = []
    for item in items:
        unit_price = _to_float(item.get("unitPrice"))
        if unit_price is None:
            continue
        product_name = _clean_optional_text(item.get("productName"))
        sku_name = _clean_optional_text(item.get("skuName"))
        meter_name = _clean_optional_text(item.get("meterName"))
        unit = _clean_optional_text(item.get("unitOfMeasure")) or ""
        entries.append(
            {
                "provider": _azure_public_provider_name(item),
                "product_name": product_name,
                "sku_name": sku_name,
                "meter_name": meter_name,
                "armRegionName": _clean_optional_text(item.get("armRegionName")),
                "price_kind": _price_kind_from_text(product_name or "", sku_name or "", meter_name or ""),
                "price_per_mtok": _price_per_mtok(unit_price, unit),
                "unit": unit,
                "derived_model_name": _azure_public_model_name(item),
            }
        )
    return entries


def _azure_public_provider_name(item: dict[str, Any]) -> str | None:
    product_name = normalize_text(str(item.get("productName") or ""))
    if "openai" in product_name:
        return "OpenAI"
    if "llama" in product_name:
        return "Meta"
    if "mistral" in product_name or "ministral" in product_name or "codestral" in product_name:
        return "Mistral AI"
    return None


def _azure_public_model_name(item: dict[str, Any]) -> str | None:
    product_name = normalize_text(str(item.get("productName") or ""))
    meter_name = normalize_text(str(item.get("meterName") or ""))
    sku_name = normalize_text(str(item.get("skuName") or ""))
    combined = " ".join(part for part in (meter_name, sku_name, product_name) if part)

    if "openai" in product_name:
        if "4o" in combined:
            return "GPT 4o"
        for version in ("5.4", "5.1", "5", "4.1", "4"):
            if version in combined:
                suffix: list[str] = []
                if "codex" in combined:
                    suffix.append("Codex")
                elif "mini" in combined:
                    suffix.append("Mini")
                elif "nano" in combined:
                    suffix.append("Nano")
                elif "pro" in combined:
                    suffix.append("Pro")
                label = f"GPT {version}"
                if suffix:
                    label += " " + " ".join(suffix)
                return label

    if "llama" in product_name:
        for token in ("4 scout", "4 maverick", "3.3 70b", "3.2", "3.1", "3"):
            if token in combined:
                return f"Llama {token.replace('b', 'B').title()}"
        return "Llama"

    if "mistral" in product_name:
        for token in ("codestral", "ministral", "large 3", "large", "small", "pixtral"):
            if token in combined:
                return token.title()
        return "Mistral"

    return None


def _dedupe_azure_public_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    payload: list[dict[str, Any]] = []
    for entry in entries:
        key = (
            str(entry.get("meter_name") or ""),
            str(entry.get("armRegionName") or ""),
            str(entry.get("price_kind") or ""),
            str(entry.get("unit") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        payload.append(entry)
    return payload


def _azure_deployment_modes(entries: list[dict[str, Any]]) -> list[str]:
    modes: set[str] = set()
    for entry in entries:
        for sku in _azure_model_skus(entry):
            sku_name = normalize_text(str(sku.get("name") or ""))
            if "provisioned" in sku_name:
                modes.add("Provisioned")
            else:
                modes.add("Serverless")
    return sorted(modes)


def _azure_public_deployment_modes(entries: list[dict[str, Any]]) -> list[str]:
    modes: set[str] = set()
    for entry in entries:
        combined = normalize_text(
            " ".join(
                str(entry.get(key) or "")
                for key in ("product_name", "sku_name", "meter_name", "unit")
            )
        )
        if "batch" in combined:
            modes.add("Batch")
        if any(token in combined for token in ("provisioned", "managed", "hosting", "1 hour", "hour")):
            modes.add("Provisioned")
        if not any(token in combined for token in ("provisioned", "managed", "hosting", "1 hour", "hour")):
            modes.add("Serverless")
    return sorted(modes)


def _google_vertex_endpoint(region: str) -> str:
    if region == "global":
        return "https://aiplatform.googleapis.com"
    return f"https://{region}-aiplatform.googleapis.com"


def _vertex_publishers_for_models(models: list[dict[str, Any]]) -> list[str]:
    publishers: list[str] = []
    for model in models:
        provider_slug = _provider_slug(model.get("provider"))
        publisher = GCP_PUBLISHER_MAP.get(provider_slug)
        if publisher:
            publishers.append(publisher)
    if "google" not in publishers:
        publishers.append("google")
    return list(dict.fromkeys(publishers))


def _extract_google_publisher_models(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for key in ("publisherModels", "models", "items"):
        raw_items = payload.get(key)
        if isinstance(raw_items, list):
            items = raw_items
            break
    records: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _clean_optional_text(item.get("name"))
        display_name = _clean_optional_text(item.get("displayName")) or _resource_tail(name)
        records.append(
            {
                "name": name,
                "display_name": display_name,
                "catalog_model_id": _resource_tail(name),
                "provider": _publisher_provider_name(_google_publisher_from_resource_name(name) or item.get("publisher")),
            }
        )
    return records


def _google_vertex_service_id(client: httpx.Client, headers: dict[str, str]) -> str | None:
    payload = _request_json(client, GCP_BILLING_SERVICES_URL, headers=headers)
    for service in payload.get("services", []):
        if not isinstance(service, dict):
            continue
        display_name = str(service.get("displayName") or "")
        if "Vertex AI" in display_name:
            return _resource_tail(service.get("name"))
    return None


def _google_vertex_skus(
    client: httpx.Client,
    headers: dict[str, str],
    service_id: str,
) -> list[dict[str, Any]]:
    skus: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params = {"pageSize": 500}
        if page_token:
            params["pageToken"] = page_token
        payload = _request_json(
            client,
            GCP_BILLING_SERVICE_SKUS_URL.format(service_id=service_id),
            headers=headers,
            params=params,
        )
        for item in payload.get("skus", []):
            if not isinstance(item, dict):
                continue
            description = _clean_optional_text(item.get("description"))
            display_name = _clean_optional_text(item.get("displayName")) or description
            latest_pricing = _latest_google_pricing(item.get("pricingInfo"))
            price_per_unit = _google_unit_price(latest_pricing)
            unit = _google_pricing_unit(latest_pricing)
            skus.append(
                {
                    "catalog_model_id": _resource_tail(item.get("name")),
                    "description": description,
                    "display_name": display_name,
                    "provider": _provider_from_text(description or display_name or ""),
                    "regions": item.get("serviceRegions") or [],
                    "price_kind": _price_kind_from_text(description or "", display_name or ""),
                    "price_per_mtok": _price_per_mtok(price_per_unit, unit) if price_per_unit is not None else None,
                    "unit": unit,
                }
            )
        page_token = str(payload.get("nextPageToken") or "").strip()
        if not page_token:
            break
    return skus


def _latest_google_pricing(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list) or not value:
        return None
    items = [item for item in value if isinstance(item, dict)]
    if not items:
        return None
    items.sort(key=lambda item: str(item.get("effectiveTime") or ""))
    return items[-1]


def _google_unit_price(pricing_info: dict[str, Any] | None) -> float | None:
    if not isinstance(pricing_info, dict):
        return None
    expression = pricing_info.get("pricingExpression")
    if not isinstance(expression, dict):
        return None
    tiered_rates = expression.get("tieredRates")
    if not isinstance(tiered_rates, list) or not tiered_rates:
        return None
    first_rate = tiered_rates[0]
    if not isinstance(first_rate, dict):
        return None
    money = first_rate.get("unitPrice")
    if not isinstance(money, dict):
        return None
    units = _to_float(money.get("units")) or 0.0
    nanos = _to_float(money.get("nanos")) or 0.0
    return units + nanos / 1_000_000_000.0


def _google_pricing_unit(pricing_info: dict[str, Any] | None) -> str:
    if not isinstance(pricing_info, dict):
        return ""
    expression = pricing_info.get("pricingExpression")
    if not isinstance(expression, dict):
        return ""
    return str(
        expression.get("displayQuantity") and expression.get("usageUnitDescription")
        or expression.get("usageUnitDescription")
        or expression.get("baseUnitDescription")
        or ""
    ).strip()


def _catalog_entry_matches_model(
    model: dict[str, Any],
    provider: Any,
    *candidate_values: Any,
) -> bool:
    provider_aliases = _provider_aliases(provider)
    model_provider_aliases = _provider_aliases(model.get("provider"))
    if provider_aliases and model_provider_aliases and not provider_aliases.intersection(model_provider_aliases):
        return False

    local_aliases = _model_aliases(model)
    local_signatures = _model_signatures(model)
    local_identity_ids = {
        str(model.get("family_id") or "").strip(),
        str(model.get("canonical_model_id") or "").strip(),
    }
    local_identity_ids.discard("")

    remote_aliases: set[str] = set()
    remote_signatures: set[str] = set()
    remote_identity_ids: set[str] = set()
    for value in candidate_values:
        if not value:
            continue
        for variant in _value_variants(value):
            remote_aliases.add(variant)
        for signature in name_signatures(str(value)):
            remote_signatures.add(signature)
        identity = infer_model_identity(str(value), _provider_display_name(provider), str(value))
        remote_identity_ids.update({identity.family_id, identity.canonical_model_id})

    if local_identity_ids.intersection(remote_identity_ids):
        return True
    if local_aliases.intersection(remote_aliases):
        return True
    if local_signatures.intersection(remote_signatures):
        return True
    return False


def _model_aliases(model: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for key in (
        "name",
        "canonical_model_name",
        "family_name",
        "openrouter_model_id",
        "openrouter_canonical_slug",
        "id",
    ):
        value = model.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        aliases.update(_value_variants(value))
    return aliases


def _model_signatures(model: dict[str, Any]) -> set[str]:
    signatures: set[str] = set()
    for key in (
        "name",
        "canonical_model_name",
        "family_name",
        "openrouter_model_id",
        "openrouter_canonical_slug",
        "id",
    ):
        value = model.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        signatures.update(name_signatures(value))
    return signatures


def _value_variants(value: Any) -> set[str]:
    text = str(value).strip()
    if not text:
        return set()
    normalized = normalize_text(text)
    compact = normalized.replace(" ", "")
    tail = _resource_tail(text)
    variants = {item for item in (normalized, compact) if item}
    if tail:
        tail_normalized = normalize_text(tail)
        if tail_normalized:
            variants.add(tail_normalized)
            variants.add(tail_normalized.replace(" ", ""))
    return variants


def _provider_aliases(value: Any) -> set[str]:
    slug = _provider_slug(value)
    if not slug:
        return set()
    return set(PROVIDER_EQUIVALENTS.get(slug, {slug}))


def _provider_slug(value: Any) -> str:
    normalized = normalize_text(str(value or ""))
    return "".join(ch for ch in normalized if ch.isalnum())


def _provider_display_name(value: Any) -> str:
    text = str(value or "").strip()
    return text or "Unknown"


def _provider_from_text(value: str) -> str | None:
    normalized = normalize_text(value)
    for provider in ("anthropic", "cohere", "google", "meta", "mistral", "openai"):
        if provider in normalized:
            return provider.title() if provider != "openai" else "OpenAI"
    return None


def _provider_from_model_name(model_name: str) -> str | None:
    normalized = normalize_text(model_name)
    if normalized.startswith("claude"):
        return "Anthropic"
    if normalized.startswith("nova"):
        return "Amazon"
    if normalized.startswith("gemini") or normalized.startswith("gemma"):
        return "Google"
    if normalized.startswith("llama"):
        return "Meta"
    if normalized.startswith("ministral") or normalized.startswith("mistral"):
        return "Mistral AI"
    if normalized.startswith("gpt") or normalized.startswith("o1") or normalized.startswith("o3") or normalized.startswith("o4"):
        return "OpenAI"
    return None


def _publisher_provider_name(value: Any) -> str | None:
    slug = _provider_slug(value)
    mapping = {
        "anthropic": "Anthropic",
        "cohere": "Cohere",
        "google": "Google",
        "meta": "Meta",
        "mistralai": "Mistral AI",
    }
    return mapping.get(slug)


def _price_kind_from_text(*values: str) -> str | None:
    combined = normalize_text(" ".join(values))
    tokens = set(combined.split())
    has_input = bool(tokens.intersection({"input", "inp", "inpt", "in"}))
    has_output = bool(tokens.intersection({"output", "outp", "outpt", "opt", "out"}))
    has_tokens = "token" in tokens or "tokens" in tokens
    if has_input and has_tokens:
        return "input"
    if has_output and has_tokens:
        return "output"
    return None


def _price_per_mtok(price_per_unit: float | None, unit: str) -> float | None:
    if price_per_unit is None:
        return None
    normalized = normalize_text(unit)
    if not normalized:
        return None
    if normalized in {"1m", "1 m"}:
        return price_per_unit
    if normalized in {"1k", "1 k"}:
        return price_per_unit * 1000.0
    if normalized.startswith("1k token") or normalized.startswith("1 k token"):
        return price_per_unit * 1000.0
    if normalized.startswith("1m token") or normalized.startswith("1 m token"):
        return price_per_unit
    if normalized.startswith("1 token"):
        return price_per_unit * 1_000_000.0
    if normalized.endswith("token") and normalized.startswith("1"):
        return price_per_unit
    return None


def _first_usd_price(price_dimension: dict[str, Any]) -> float | None:
    price_per_unit = price_dimension.get("pricePerUnit")
    if not isinstance(price_per_unit, dict):
        return None
    return _to_float(price_per_unit.get("USD"))


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _aws_inference_type_label(value: Any) -> str | None:
    normalized = normalize_text(str(value or ""))
    if normalized == "on demand":
        return "On-demand"
    if normalized == "provisioned":
        return "Provisioned"
    if normalized == "batch":
        return "Batch"
    return _clean_optional_text(value)


def _aws_deployment_modes(
    matched_prices: list[dict[str, Any]],
    matched_catalog: list[dict[str, Any]],
) -> list[str]:
    modes = {
        _clean_optional_text(entry.get("deployment_mode"))
        for entry in matched_prices
        if _clean_optional_text(entry.get("deployment_mode"))
    }
    for entry in matched_catalog:
        for mode in entry.get("deployment_modes", []):
            label = _aws_inference_type_label(mode)
            if label:
                modes.add(label)
    return sorted(mode for mode in modes if mode)


def _aws_availability_note(
    *,
    matched_catalog: list[dict[str, Any]],
    matched_prices: list[dict[str, Any]],
    publication_dates: list[str],
    used_account_catalog: bool,
) -> str | None:
    latest_publication = max(publication_dates) if publication_dates else None
    if matched_catalog and used_account_catalog:
        return (
            f"Live Bedrock catalog regions for this AWS account. "
            f"Pricing fallback publication date: {latest_publication}."
            if latest_publication
            else "Live Bedrock catalog regions for this AWS account."
        )
    if matched_prices:
        return (
            "Derived from the public Amazon Bedrock price list; "
            "account entitlement checks are unavailable without AWS credentials."
        )
    return None


def _aws_pricing_note(matched_prices: list[dict[str, Any]], publication_dates: list[str]) -> str | None:
    latest_publication = max(publication_dates) if publication_dates else None
    regions = _unique_sorted(entry.get("region") for entry in matched_prices if entry.get("region"))
    if not matched_prices:
        return None
    note = f"Live AWS pricing matched in {len(regions)} region(s)."
    if latest_publication:
        note += f" Offer publication date: {latest_publication}."
    return note


def _azure_pricing_note(matched_prices: list[dict[str, Any]], *, public_only: bool = False) -> str | None:
    if not matched_prices:
        if public_only:
            return "Public Azure retail prices matched the model family, but no token-priced meters were resolved."
        return "Live Azure model SKUs were matched, but no retail meter prices resolved for the returned meter IDs."
    regions = _unique_sorted(price.get("armRegionName") for price in matched_prices if price.get("armRegionName"))
    if public_only:
        return (
            f"Public Azure retail prices resolved for {len(matched_prices)} meter row(s) "
            f"across {len(regions)} region(s); this does not confirm account entitlements."
        )
    return f"Live Azure retail prices resolved for {len(matched_prices)} meter row(s) across {len(regions)} region(s)."


def _google_deployment_modes(matched_catalog: list[dict[str, Any]]) -> list[str]:
    if not matched_catalog:
        return []
    modes = set()
    for entry in matched_catalog:
        if entry.get("region") == "global":
            modes.add("Publisher model endpoint")
        else:
            modes.add("Regional endpoint")
    return sorted(modes)


def _google_public_deployment_modes(regions: list[str]) -> list[str]:
    modes = {"Regional endpoint"}
    if "global" in regions:
        modes.add("Publisher model endpoint")
    return sorted(modes)


def _google_pricing_note(matched_skus: list[dict[str, Any]]) -> str | None:
    if not matched_skus:
        return "Live Vertex model regions were synced; Cloud Billing SKU pricing did not match this model."
    return f"Live Cloud Billing SKUs matched: {len(matched_skus)}."


def _pricing_label(
    *,
    input_prices: list[float | None],
    output_prices: list[float | None],
    currency_code: str,
) -> str | None:
    clean_inputs = [price for price in input_prices if price is not None]
    clean_outputs = [price for price in output_prices if price is not None]
    parts: list[str] = []
    if clean_inputs:
        parts.append(f"Input {_format_price_range(clean_inputs, currency_code)}")
    if clean_outputs:
        parts.append(f"Output {_format_price_range(clean_outputs, currency_code)}")
    if parts:
        return " / ".join(parts) + " per 1M tokens"
    return None


def _format_price_range(values: list[float], currency_code: str) -> str:
    if not values:
        return ""
    minimum = min(values)
    maximum = max(values)
    if abs(maximum - minimum) < 1e-12:
        return f"{currency_code} {_format_price_number(minimum)}"
    return f"{currency_code} {_format_price_number(minimum)}-{_format_price_number(maximum)}"


def _format_price_number(value: float) -> str:
    if value >= 1:
        return f"${value:.2f}"
    if value >= 0.01:
        return f"${value:.4f}".rstrip("0").rstrip(".")
    return f"${value:.6f}".rstrip("0").rstrip(".")


def _resource_tail(value: Any) -> str | None:
    text = _clean_optional_text(value)
    if not text:
        return None
    return text.split("/")[-1]


def _resource_parent_tail(value: Any) -> str | None:
    text = _clean_optional_text(value)
    if not text or "/" not in text:
        return None
    return text.split("/")[-2]


def _google_publisher_from_resource_name(value: Any) -> str | None:
    text = _clean_optional_text(value)
    if not text:
        return None
    parts = [part for part in text.split("/") if part]
    if len(parts) >= 4 and parts[-4] == "publishers":
        return parts[-3]
    if len(parts) >= 2 and parts[0] == "publishers":
        return parts[1]
    return None


def _unique_sorted(values: Iterable[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _first_non_empty(values: Iterable[Any]) -> str | None:
    for value in values:
        text = _clean_optional_text(value)
        if text:
            return text
    return None


def _clean_optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


__all__ = ["MissingConfiguration", "sync_inference_catalog"]
