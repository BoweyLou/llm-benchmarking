"""Provider-specific inference pricing, provenance, and last-known-good refreshes."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import httpx
from sqlalchemy import delete, func, select, update

from .database import (
    fetch_all,
    fetch_one,
    get_connection,
    get_engine,
    model_pricing_components as components_table,
    model_pricing_offers as offers_table,
    models as models_table,
    raw_source_records as raw_source_records_table,
    source_runs as source_runs_table,
    utc_now_iso,
)
from .name_resolution import name_signatures, normalize_text

STALE_AFTER_DAYS = 30
MIN_REFRESH_COVERAGE = 0.70
ALIASES_PATH = Path(__file__).with_name("provider_pricing_aliases.json")

PROVIDER_SOURCES: dict[str, dict[str, str]] = {
    "openai": {
        "destination_id": "openai-direct",
        "label": "OpenAI API pricing",
        "url": "https://developers.openai.com/api/docs/pricing",
        "provider": "OpenAI",
    },
    "anthropic": {
        "destination_id": "anthropic-direct",
        "label": "Anthropic API pricing",
        "url": "https://docs.anthropic.com/en/docs/about-claude/pricing",
        "provider": "Anthropic",
    },
    "google": {
        "destination_id": "google-gemini-direct",
        "label": "Google Gemini API pricing",
        "url": "https://ai.google.dev/gemini-api/docs/pricing",
        "provider": "Google",
    },
    "mistral": {
        "destination_id": "mistral-direct",
        "label": "Mistral API pricing",
        "url": "https://mistral.ai/pricing/api/",
        "provider": "Mistral AI",
    },
    "cohere": {
        "destination_id": "cohere-direct",
        "label": "Cohere API pricing",
        "url": "https://cohere.com/pricing",
        "provider": "Cohere",
    },
    "xai": {
        "destination_id": "xai-direct",
        "label": "xAI API pricing",
        "url": "https://docs.x.ai/developers/pricing",
        "provider": "xAI",
    },
    "openrouter": {
        "destination_id": "openrouter",
        "label": "OpenRouter Models API",
        "url": "https://openrouter.ai/api/v1/models",
        "provider": "OpenRouter",
    },
}

_MONEY_RE = re.compile(r"(?:USD\s*)?\$\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_TIER_RE = re.compile(r"\b(standard|batch|priority|flex|realtime|cached)\b", re.IGNORECASE)


class PricingRefreshRejected(RuntimeError):
    """Raised when a source refresh fails a last-known-good coverage guard."""


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.row_tiers: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._next_table_tier = "standard"
        self._table_tier = "standard"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "astro-island":
            props = next((value for key, value in attrs if key == "props"), None) or ""
            tier_match = re.search(r'"tier"\s*:\s*\[0\s*,\s*"([^"]+)"\]', props)
            if tier_match:
                self._next_table_tier = tier_match.group(1).lower()
        elif tag == "table":
            self._table_tier = self._next_table_tier
        elif tag == "tr":
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._row is not None and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(unescape(value))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
                self.row_tiers.append(self._table_tier)
            self._row = None
            self._cell = None


def parse_official_pricing_html(provider_id: str, html: str) -> list[dict[str, Any]]:
    """Extract published pricing rows from semantic HTML tables.

    Provider pages are intentionally treated as fallible inputs. A zero-row
    parse is rejected by the refresh guard and cannot erase prior prices.
    """
    parser = _TableParser()
    parser.feed(html)
    offers: list[dict[str, Any]] = []
    headers: list[str] = []
    for cells, table_tier in zip(parser.rows, parser.row_tiers):
        lowered = [_pricing_header_text(cell) for cell in cells]
        if any("model" in cell.split() for cell in lowered) and any(
            token in " ".join(lowered) for token in ("input", "output", "price", "token")
        ):
            headers = lowered
            continue
        if len(cells) < 2:
            continue
        combined = " ".join(cells)
        tier_match = _TIER_RE.search(combined)
        default_tier = tier_match.group(1).lower() if tier_match else table_tier
        components = _components_from_cells(cells, headers, default_tier=default_tier)
        if not components and not any(normalize_text(cell) in {"free", "custom", "contact us"} for cell in cells[1:]):
            continue
        model_name = cells[0].strip()
        if not model_name or _pricing_header_text(model_name) in {"model", "models"}:
            continue
        components_by_tier: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for component in components:
            normalized_component = dict(component)
            component_tier = str(normalized_component.pop("_service_tier", default_tier) or "standard")
            components_by_tier[component_tier].append(normalized_component)
        if not components_by_tier:
            components_by_tier[default_tier or "standard"] = []
        for service_tier, tier_components in components_by_tier.items():
            price_status = "published"
            if tier_components and all(component.get("amount") == 0 for component in tier_components):
                price_status = "free"
            elif not tier_components:
                price_status = "custom" if "custom" in normalize_text(combined) or "contact us" in normalize_text(combined) else "unavailable"
            offers.append(
                {
                    "published_model_id": model_name,
                    "provider_model_id": model_name,
                    "service_tier": service_tier,
                    "currency": "USD",
                    "price_status": price_status,
                    "constraints": {},
                    "components": tier_components,
                    "raw": cells,
                }
            )
    if provider_id == "google":
        offers = _parse_google_pricing_sections(html)
    elif provider_id == "mistral":
        offers.extend(_parse_mistral_cards(html))
    elif provider_id == "cohere":
        offers.extend(_parse_cohere_embedded_models(html))
    elif provider_id == "xai":
        offers = _normalize_xai_offers(offers)
    return _dedupe_parsed_offers(offers)


def _parse_mistral_cards(html: str) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    for block in re.findall(r"<mistral-block-card-model\b.*?</mistral-block-card-model>", html, re.DOTALL | re.IGNORECASE):
        name_match = re.search(r'<p class="text-h5[^>]*>(.*?)</p>', block, re.DOTALL | re.IGNORECASE)
        if not name_match:
            continue
        model_name = " ".join(re.sub(r"<[^>]+>", " ", name_match.group(1)).split())
        components: list[dict[str, Any]] = []
        for label_text, attrs in re.findall(
            r"<p[^>]*>([^<]*(?:Input|Output)[^<]*)</p>\s*<mistral-atom-text-price\b([^>]*)>",
            block,
            re.DOTALL | re.IGNORECASE,
        ):
            prices_match = re.search(r'data-prices="([^"]+)"', attrs, re.IGNORECASE)
            if not prices_match:
                continue
            try:
                prices = json.loads(unescape(prices_match.group(1)))
                amount = float(prices["priceUsd"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            quantity, unit = _billing_unit(label_text, label_text)
            components.append(
                {
                    "modality": _modality_from_text(label_text),
                    "charge_type": "output" if "output" in normalize_text(label_text) else "input",
                    "amount": amount,
                    "billing_unit": unit,
                    "unit_quantity": quantity,
                    "conditions": {},
                }
            )
        if components:
            offers.append(
                {
                    "published_model_id": model_name, "provider_model_id": model_name,
                    "service_tier": "standard", "currency": "USD", "price_status": "published",
                    "constraints": {}, "components": components, "raw": {"model": model_name},
                }
            )
    return offers


def _parse_cohere_embedded_models(html: str) -> list[dict[str, Any]]:
    clean = unescape(html).replace('\\"', '"')
    pattern = re.compile(
        r'"modelName":"(?P<model>[^"]+)".*?"per":"(?P<per>[^"]+)".*?"pricings":\[(?P<pricing>.*?)\]',
        re.DOTALL,
    )
    offers: list[dict[str, Any]] = []
    for match in pattern.finditer(clean):
        price_block = match.group("pricing")
        input_match = re.search(r'"inputLabel":"([^"]+)"\s*,\s*"inputPrice":([0-9.]+)', price_block)
        output_match = re.search(r'"outputLabel":"([^"]+)"\s*,\s*(?:"overridePer":"([^"]+)"\s*,\s*)?"outputPrice":([0-9.]+)', price_block)
        override_per_match = re.search(r'"overridePer":"([^"]+)"', price_block)
        input_per = override_per_match.group(1) if override_per_match else match.group("per")
        quantity, unit = _billing_unit(
            input_per,
            f"{input_match.group(1) if input_match else ''} {input_per}",
        )
        components: list[dict[str, Any]] = []
        if input_match:
            label_text, amount = input_match.group(1), float(input_match.group(2))
            components.append(
                {
                    "modality": _modality_from_text(f"{match.group('model')} {label_text}"),
                    "charge_type": "input" if "input" in normalize_text(label_text) else "usage",
                    "amount": amount, "billing_unit": unit, "unit_quantity": quantity, "conditions": {},
                }
            )
        if output_match:
            label_text, override_per, amount_text = output_match.groups()
            output_per = override_per or match.group("per")
            out_quantity, out_unit = _billing_unit(output_per, f"{label_text} {output_per}")
            components.append(
                {
                    "modality": _modality_from_text(f"{match.group('model')} {label_text}"),
                    "charge_type": "output" if "output" in normalize_text(label_text) else "usage",
                    "amount": float(amount_text), "billing_unit": out_unit, "unit_quantity": out_quantity,
                    "conditions": {},
                }
            )
        if normalize_text(match.group("model")) == "transcribe":
            # Cohere describes unrestricted production Transcribe pricing as
            # contact-based Model Vault capacity. Do not present unrelated
            # token/image fields embedded in the page payload as direct rates.
            components = []
            offers.append(
                {
                    "published_model_id": match.group("model"), "provider_model_id": match.group("model"),
                    "service_tier": "standard", "currency": "USD", "price_status": "custom",
                    "constraints": {"availability": "contact Cohere for production Model Vault pricing"},
                    "components": [], "raw": {"model": match.group("model")},
                }
            )
            continue
        if components:
            offers.append(
                {
                    "published_model_id": match.group("model"), "provider_model_id": match.group("model"),
                    "service_tier": "standard", "currency": "USD",
                    "price_status": "free" if all(item["amount"] == 0 for item in components) else "published",
                    "constraints": {}, "components": components, "raw": {"model": match.group("model")},
                }
            )
    return offers


def _parse_google_pricing_sections(html: str) -> list[dict[str, Any]]:
    """Parse Google tables whose model identity lives in the preceding heading."""
    event_re = re.compile(r"<h([1-4])\b[^>]*>(.*?)</h\1>|(<table\b.*?</table>)", re.DOTALL | re.IGNORECASE)
    current_model: str | None = None
    current_tier = "standard"
    offers: list[dict[str, Any]] = []
    for event in event_re.finditer(html):
        if event.group(1):
            heading = " ".join(re.sub(r"<[^>]+>", " ", unescape(event.group(2))).split())
            normalized = normalize_text(heading)
            if normalized in {"standard", "batch", "flex", "priority"}:
                current_tier = normalized
            elif _is_google_model_heading(heading):
                current_model = heading
                current_tier = "standard"
            continue
        if not current_model:
            continue
        parser = _TableParser()
        parser.feed(event.group(3))
        components: list[dict[str, Any]] = []
        for row in parser.rows[1:]:
            if len(row) < 2:
                continue
            label_text = row[0]
            paid_cell = row[-1]
            money_matches = list(_MONEY_RE.finditer(paid_cell))
            for index, money_match in enumerate(money_matches):
                next_match = money_matches[index + 1] if index + 1 < len(money_matches) else None
                context_end = next_match.start() if next_match else len(paid_cell)
                context_text = paid_cell[money_match.end():context_end].strip(" ,;()")
                quantity, unit = _billing_unit(context_text, label_text)
                components.append(
                    {
                        "modality": _modality_from_text(f"{label_text} {context_text}"),
                        "charge_type": _google_charge_type(label_text, context_text),
                        "amount": float(money_match.group(1)),
                        "billing_unit": unit,
                        "unit_quantity": quantity,
                        "conditions": {"published_condition": context_text} if context_text else {},
                    }
                )
        components = _dedupe_components(components)
        if components:
            offers.append(
                {
                    "published_model_id": current_model,
                    "provider_model_id": current_model,
                    "service_tier": current_tier,
                    "currency": "USD",
                    "price_status": "free" if all(component["amount"] == 0 for component in components) else "published",
                    "constraints": {},
                    "components": components,
                    "raw": parser.rows,
                }
            )
    return offers


def _is_google_model_heading(value: str) -> bool:
    text = " ".join(value.split())
    return bool(
        re.match(r"^(?:Gemini|Imagen|Veo|Lyria)\s+(?:\d|Embedding|Live|Omni)", text, re.IGNORECASE)
        or re.match(r"^Gemini Embedding", text, re.IGNORECASE)
    )


def _google_charge_type(label_text: str, context_text: str) -> str:
    text = normalize_text(f"{label_text} {context_text}")
    if "context caching" in text and "storage" in text:
        return "cache_storage"
    if "context caching" in text:
        return "cached_input"
    if "output" in text:
        return "output"
    if "input" in text:
        return "input"
    if "search" in text or "grounding" in text:
        return "search"
    return "usage"


def _normalize_xai_offers(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for offer in offers:
        raw_name = str(offer.get("published_model_id") or "").strip()
        if re.fullmatch(r"(?:2K|720p|1080p)", raw_name, re.IGNORECASE):
            if current is not None:
                for component in offer.get("components") or []:
                    enriched = dict(component)
                    enriched["modality"] = "image" if raw_name.lower() == "2k" else "video"
                    enriched["charge_type"] = "output"
                    enriched["conditions"] = {**(component.get("conditions") or {}), "resolution": raw_name}
                    current["components"].append(enriched)
            continue
        if not raw_name.lower().startswith("grok-"):
            continue
        clean_name = re.sub(
            r"(?:Text|Image|Audio|Video)(?:\s*,\s*(?:Text|Image|Audio|Video))*\s*(?:→|->)\s*(?:Text|Image|Audio|Video).*$",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip()
        normalized = {**offer, "published_model_id": clean_name, "provider_model_id": clean_name}
        normalized["components"] = list(offer.get("components") or [])
        payload.append(normalized)
        current = normalized
    return _dedupe_parsed_offers(payload)


def _dedupe_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for component in components:
        key = json.dumps(
            {
                "modality": component.get("modality"), "charge_type": component.get("charge_type"),
                "amount": component.get("amount"), "billing_unit": component.get("billing_unit"),
                "unit_quantity": component.get("unit_quantity"), "conditions": component.get("conditions") or {},
            },
            sort_keys=True,
            default=str,
        )
        if key in seen:
            continue
        seen.add(key)
        payload.append(component)
    return payload


def _components_from_cells(
    cells: list[str], headers: list[str], *, default_tier: str = "standard"
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    price_cells = cells[1:]
    for index, cell in enumerate(price_cells, start=1):
        amount = _money_value(cell)
        if amount is None:
            continue
        header = headers[index] if index < len(headers) else ""
        charge_type = _charge_type(header, index - 1, len(price_cells))
        unit_quantity, billing_unit = _billing_unit(cell, header)
        modality = _modality_from_text(f"{header} {cell}")
        conditions: dict[str, Any] = {}
        header_text = _pricing_header_text(header)
        if "cache hits" in header_text and "refresh" in header_text:
            conditions["cache_operation"] = "hit_or_refresh"
        elif "cache write" in header_text:
            if "1h" in header_text or "1 h" in header_text:
                conditions["cache_duration"] = "1h"
            elif "5m" in header_text or "5 m" in header_text:
                conditions["cache_duration"] = "5m"
        if len(headers) == len(cells) and headers.count("input") >= 2 and len(price_cells) >= 8:
            conditions["context_band"] = "short" if index <= 4 else "long"
        components.append(
            {
                "modality": modality,
                "charge_type": charge_type,
                "amount": amount,
                "billing_unit": billing_unit,
                "unit_quantity": unit_quantity,
                "conditions": conditions,
                "_service_tier": _header_service_tier(header) or default_tier,
            }
        )
    return components


def _pricing_header_text(value: str) -> str:
    """Normalize pricing-table labels without model-name stopword removal."""
    return re.sub(r"[^0-9a-z]+", " ", unescape(value).casefold()).strip()


def _header_service_tier(value: str) -> str | None:
    match = re.search(r"\b(standard|batch|priority|flex|realtime)\b", _pricing_header_text(value), re.IGNORECASE)
    return match.group(1).lower() if match else None


def _money_value(value: str) -> float | None:
    if normalize_text(value) == "free":
        return 0.0
    match = _MONEY_RE.search(value)
    return float(match.group(1)) if match else None


def _charge_type(header: str, index: int, count: int) -> str:
    text = normalize_text(header)
    if "cache hits" in text or "refresh" in text:
        return "cached_input"
    if "cached" in text and "input" in text:
        return "cached_input"
    if "cache write" in text:
        return "cache_write"
    if "output" in text or "completion" in text:
        return "output"
    if "reason" in text:
        return "reasoning"
    if "request" in text:
        return "request"
    if "search" in text:
        return "search"
    if "input" in text or "prompt" in text:
        return "input"
    if count >= 3 and index == 1:
        return "cached_input"
    return "output" if index == count - 1 and count > 1 else "input"


def _billing_unit(cell: str, header: str) -> tuple[float, str]:
    raw_text = f"{cell} {header}"
    text = normalize_text(raw_text)
    if ("1,000" in raw_text or "1000" in text or "1k" in text) and ("search" in text or "request" in text):
        return 1_000.0, "search" if "search" in text else "request"
    if re.search(r"/\s*(?:min|minute)s?\b", raw_text, re.IGNORECASE):
        return 1.0, "minute"
    if re.search(r"/\s*(?:img|image)s?\b", raw_text, re.IGNORECASE):
        return 1.0, "image"
    if re.search(r"/\s*(?:sec|second)s?\b", raw_text, re.IGNORECASE):
        return 1.0, "second"
    if ("1,000,000" in raw_text or "1000000" in text or "1m" in text or "million" in text) and (
        "per hour" in text or re.search(r"/\s*(?:hr|hour)s?\b", raw_text, re.IGNORECASE)
    ):
        return 1_000_000.0, "token_hour"
    if "1,000,000" in raw_text or "1000000" in text or "1m" in text or "million" in text:
        return 1_000_000.0, "token"
    if "1k" in text or "thousand" in text:
        return 1_000.0, "token"
    for unit in ("request", "search", "image", "minute", "page", "character", "second", "hour", "frame"):
        if unit in text:
            return 1.0, unit
    return 1_000_000.0, "token"


def _modality_from_text(value: str) -> str:
    text = normalize_text(value)
    if "media input" in text or re.search(r"\bimgs?\b", text):
        return "image"
    for modality in ("audio", "image", "video", "embedding"):
        if modality in text:
            return modality
    return "text"


def _dedupe_parsed_offers(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for offer in offers:
        fingerprint = json.dumps(
            [offer.get("published_model_id"), offer.get("service_tier"), offer.get("components")],
            sort_keys=True,
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        payload.append(offer)
    return payload


def sync_pricing(
    *,
    provider_ids: Iterable[str] | None = None,
    engine=None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Refresh selected direct, router, or cloud pricing sources."""
    engine = engine or get_engine()
    selected = list(dict.fromkeys(provider_ids or PROVIDER_SOURCES.keys()))
    valid = {*PROVIDER_SOURCES, "aws-bedrock", "azure-ai-foundry", "google-vertex-ai"}
    invalid = sorted(set(selected) - valid)
    if invalid:
        raise ValueError(f"Unknown pricing providers: {', '.join(invalid)}")

    summary: dict[str, Any] = {"providers": {}, "offers_written": 0, "components_written": 0}
    owned_client = client is None
    active_client = client or httpx.Client(timeout=45.0, follow_redirects=True, headers={"User-Agent": "LLM-Model-Tool/0.8"})
    try:
        cloud_ids = [item for item in selected if item in {"aws-bedrock", "azure-ai-foundry", "google-vertex-ai"}]
        if cloud_ids:
            from .inference_sync import sync_inference_catalog

            cloud_summary = sync_inference_catalog(destination_ids=cloud_ids, engine=engine)
            for destination_id, result in cloud_summary.get("destinations", {}).items():
                summary["providers"][destination_id] = result
            summary["offers_written"] += int(cloud_summary.get("pricing_offers_written") or 0)
            summary["components_written"] += int(cloud_summary.get("pricing_components_written") or 0)

        for provider_id in selected:
            if provider_id in cloud_ids:
                continue
            try:
                if provider_id == "openrouter":
                    response = active_client.get(PROVIDER_SOURCES[provider_id]["url"], params={"output_modalities": "all"})
                    response.raise_for_status()
                    body = response.json()
                    items = body.get("data", []) if isinstance(body, dict) else []
                    result = sync_openrouter_items(items, engine=engine)
                else:
                    source = PROVIDER_SOURCES[provider_id]
                    response = active_client.get(source["url"])
                    response.raise_for_status()
                    parsed = parse_official_pricing_html(provider_id, response.text)
                    result = persist_parsed_source(provider_id, parsed, engine=engine)
                summary["providers"][provider_id] = {"status": "completed", **result}
                summary["offers_written"] += int(result.get("offer_count") or 0)
                summary["components_written"] += int(result.get("component_count") or 0)
            except Exception as exc:
                _record_failed_run(engine, f"pricing_{provider_id}", str(exc))
                summary["providers"][provider_id] = {"status": "failed", "reason": str(exc), "last_known_good_preserved": True}
    finally:
        if owned_client:
            active_client.close()
    return summary


def persist_parsed_source(provider_id: str, parsed: list[dict[str, Any]], *, engine=None) -> dict[str, Any]:
    source = PROVIDER_SOURCES[provider_id]
    engine = engine or get_engine()
    with get_connection(engine) as conn:
        model_rows = fetch_all(conn, select(models_table).where(models_table.c.active == 1))
    aliases = _alias_config().get("aliases", {})
    matched, unmatched = _match_offers(parsed, model_rows, aliases.get(provider_id, {}), source["provider"])
    return _persist_source(
        engine=engine,
        source_name=f"pricing_{provider_id}",
        source_url=source["url"],
        source_label=source["label"],
        destination_id=source["destination_id"],
        matched=matched,
        unmatched=unmatched,
        canary=_alias_config().get("canaries", {}).get(provider_id),
    )


def sync_openrouter_items(items: Iterable[Mapping[str, Any]], *, engine=None) -> dict[str, Any]:
    engine = engine or get_engine()
    clean_items = [dict(item) for item in items if isinstance(item, Mapping)]
    with get_connection(engine) as conn:
        model_rows = fetch_all(conn, select(models_table).where(models_table.c.active == 1))
    by_openrouter_id: dict[str, str] = {}
    for row in model_rows:
        for key in (row.get("openrouter_model_id"), row.get("openrouter_canonical_slug")):
            if str(key or "").strip():
                by_openrouter_id[str(key)] = str(row["id"])
    name_index = _model_name_index(model_rows)
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for item in clean_items:
        provider_model_id = str(item.get("id") or item.get("canonical_slug") or "").strip()
        model_id = by_openrouter_id.get(provider_model_id) or by_openrouter_id.get(str(item.get("canonical_slug") or ""))
        if model_id is None:
            model_id = _resolve_model_id(str(item.get("name") or provider_model_id), name_index)
        raw_pricing = item.get("pricing")
        components = _openrouter_components(raw_pricing)
        if not model_id or not components:
            unmatched.append({"published_model_id": provider_model_id, "raw": item})
            continue
        base_offer = {
            "model_id": model_id,
            "published_model_id": provider_model_id,
            "provider_model_id": provider_model_id,
            "service_tier": "standard",
            "currency": "USD",
            "price_status": "free" if all(component["amount"] == 0 for component in components) else "published",
            "constraints": _openrouter_constraints(item),
            "components": components,
            "raw": item,
        }
        matched.append(base_offer)
        overrides = raw_pricing.get("overrides") if isinstance(raw_pricing, Mapping) else None
        if isinstance(overrides, list):
            for override_index, override in enumerate(overrides):
                if not isinstance(override, Mapping):
                    continue
                override_components = _openrouter_components(override)
                if not override_components:
                    continue
                override_constraints = {
                    **_openrouter_constraints(item),
                    "pricing_override": {
                        key: value
                        for key, value in override.items()
                        if key not in _OPENROUTER_PRICE_FIELDS
                    },
                }
                matched.append(
                    {
                        **base_offer,
                        "price_status": "free" if all(component["amount"] == 0 for component in override_components) else "published",
                        "constraints": override_constraints,
                        "components": override_components,
                        "_index": override_index,
                    }
                )
    source = PROVIDER_SOURCES["openrouter"]
    return _persist_source(
        engine=engine,
        source_name="pricing_openrouter",
        source_url=source["url"],
        source_label=source["label"],
        destination_id=source["destination_id"],
        matched=matched,
        unmatched=unmatched,
        canary=None,
    )


_OPENROUTER_FIELD_MAP: dict[str, tuple[str, str, str, float, dict[str, Any]]] = {
    "prompt": ("text", "input", "token", 1_000_000.0, {}),
    "completion": ("text", "output", "token", 1_000_000.0, {}),
    "input_cache_read": ("text", "cached_input", "token", 1_000_000.0, {}),
    "input_cache_write": ("text", "cache_write", "token", 1_000_000.0, {}),
    "input_cache_write_1h": ("text", "cache_write", "token", 1_000_000.0, {"cache_duration": "1h"}),
    "internal_reasoning": ("text", "reasoning", "token", 1_000_000.0, {}),
    "image": ("image", "input", "token", 1_000_000.0, {}),
    "image_token": ("image", "output", "token", 1_000_000.0, {"source_field": "image_token"}),
    "image_output": ("image", "output", "token", 1_000_000.0, {"source_field": "image_output"}),
    "audio": ("audio", "input", "token", 1_000_000.0, {}),
    "input_audio_cache": ("audio", "cached_input", "token", 1_000_000.0, {}),
    "audio_output": ("audio", "output", "token", 1_000_000.0, {}),
    "request": ("text", "request", "request", 1.0, {}),
    "web_search": ("text", "search", "search", 1.0, {}),
}
_OPENROUTER_PRICE_FIELDS = frozenset(_OPENROUTER_FIELD_MAP)


def _openrouter_components(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    components: list[dict[str, Any]] = []
    for field, raw_amount in value.items():
        definition = _OPENROUTER_FIELD_MAP.get(str(field))
        if definition is None:
            continue
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError):
            continue
        modality, charge_type, billing_unit, quantity, conditions = definition
        components.append(
            {
                "modality": modality,
                "charge_type": charge_type,
                "amount": amount * quantity if billing_unit == "token" else amount,
                "billing_unit": billing_unit,
                "unit_quantity": quantity,
                "conditions": conditions,
            }
        )
    return components


def _openrouter_constraints(item: Mapping[str, Any]) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for key in ("per_request_limits", "supported_parameters"):
        if item.get(key) not in (None, [], {}):
            constraints[key] = item[key]
    return constraints


def _persist_source(
    *,
    engine,
    source_name: str,
    source_url: str,
    source_label: str,
    destination_id: str,
    matched: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
    canary: str | None,
) -> dict[str, Any]:
    verified_at = utc_now_iso()
    for item in matched:
        item["components"] = _dedupe_components(list(item.get("components") or []))
    component_count = sum(len(item.get("components") or []) for item in matched)
    if not matched or component_count == 0:
        raise PricingRefreshRejected(f"{source_label} returned no matched numeric pricing offers")
    with get_connection(engine) as conn:
        previous_components = int(
            conn.execute(
                select(func.count(components_table.c.id))
                .select_from(components_table.join(offers_table, components_table.c.offer_id == offers_table.c.id))
                .where(offers_table.c.source_name == source_name, offers_table.c.active == 1)
            ).scalar_one()
        )
    if previous_components and component_count < previous_components * MIN_REFRESH_COVERAGE:
        raise PricingRefreshRejected(
            f"{source_label} coverage fell from {previous_components} to {component_count} components"
        )
    source_records = [*matched, *unmatched]
    if canary and not any(_normal(item.get("published_model_id")).startswith(_normal(canary)) for item in source_records):
        raise PricingRefreshRejected(f"{source_label} did not contain configured canary {canary}")

    with engine.begin() as conn:
        source_run_id = int(
            conn.execute(
                source_runs_table.insert().values(
                    update_log_id=None,
                    source_name=source_name,
                    benchmark_id=None,
                    started_at=verified_at,
                    completed_at=verified_at,
                    status="completed",
                    records_found=len(matched) + len(unmatched),
                    error_message=None,
                    details_json=json.dumps(
                        {
                            "destination_id": destination_id,
                            "matched_offer_count": len(matched),
                            "unmatched_count": len(unmatched),
                            "component_count": component_count,
                            "source_url": source_url,
                        },
                        sort_keys=True,
                    ),
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            update(offers_table)
            .where(offers_table.c.source_name == source_name, offers_table.c.active == 1)
            .values(active=0, superseded_at=verified_at)
        )
        for item in matched:
            offer_key = _offer_key(item)
            offer_id = int(
                conn.execute(
                    offers_table.insert().values(
                        model_id=item["model_id"],
                        destination_id=destination_id,
                        offer_key=offer_key,
                        provider_model_id=item.get("provider_model_id") or item.get("published_model_id"),
                        service_tier=item.get("service_tier") or "standard",
                        region=item.get("region"),
                        currency=item.get("currency") or "USD",
                        constraints_json=json.dumps(item.get("constraints") or {}, sort_keys=True),
                        price_status=item.get("price_status") or "published",
                        source_name=source_name,
                        source_url=source_url,
                        source_type="official",
                        source_run_id=source_run_id,
                        effective_at=item.get("effective_at"),
                        verified_at=verified_at,
                        created_at=verified_at,
                        superseded_at=None,
                        active=1,
                    )
                ).inserted_primary_key[0]
            )
            component_rows = _dedupe_components([
                    {
                        "offer_id": offer_id,
                        "modality": component.get("modality") or "text",
                        "charge_type": component["charge_type"],
                        "amount": component.get("amount"),
                        "billing_unit": component["billing_unit"],
                        "unit_quantity": float(component.get("unit_quantity") or 1),
                        "conditions_json": json.dumps(component.get("conditions") or {}, sort_keys=True),
                    }
                    for component in item.get("components") or []
                ])
            if component_rows:
                conn.execute(components_table.insert(), component_rows)
            _write_raw_record(conn, source_run_id, item, source_url, normalized_model_id=item["model_id"])
        for item in unmatched:
            _write_raw_record(conn, source_run_id, item, source_url, normalized_model_id=None)
        _update_legacy_scalar_prices(conn, destination_id, matched)
    return {
        "source_run_id": source_run_id,
        "offer_count": len(matched),
        "component_count": component_count,
        "unmatched_count": len(unmatched),
        "verified_at": verified_at,
    }


def persist_cloud_pricing(
    *,
    engine,
    destination_id: str,
    source_url: str,
    source_label: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for record in records:
        for entry in record.get("_pricing_entries") or []:
            amount = entry.get("amount", entry.get("price_per_mtok"))
            if amount is None:
                continue
            provider_model_id = str(entry.get("catalog_model_id") or record.get("catalog_model_id") or record["model_id"])
            tier = str(entry.get("service_tier") or _tier_from_entry(entry))
            region = str(entry.get("region") or entry.get("armRegionName") or "")
            constraints = {
                key: entry[key]
                for key in ("unit", "start_usage_amount", "end_usage_amount", "effective_time")
                if entry.get(key) not in (None, "")
            }
            key = (str(record["model_id"]), provider_model_id, tier, region, json.dumps(constraints, sort_keys=True))
            offer = grouped.setdefault(
                key,
                {
                    "model_id": record["model_id"], "published_model_id": provider_model_id,
                    "provider_model_id": provider_model_id, "service_tier": tier,
                    "region": region or None, "currency": "USD", "price_status": "free" if float(amount) == 0 else "published",
                    "constraints": constraints, "components": [], "raw": [],
                },
            )
            offer["components"].append(
                {
                    "modality": _modality_from_text(json.dumps(entry)),
                    "charge_type": entry.get("price_kind") or "usage",
                    "amount": float(amount),
                    "billing_unit": entry.get("billing_unit") or "token",
                    "unit_quantity": float(entry.get("unit_quantity") or 1_000_000.0),
                    "conditions": {
                        key: entry[key]
                        for key in ("start_usage_amount", "end_usage_amount")
                        if entry.get(key) not in (None, "")
                    },
                }
            )
            offer["raw"].append(entry)
            if float(amount) != 0:
                offer["price_status"] = "published"
    matched = list(grouped.values())
    if not matched:
        raise PricingRefreshRejected(f"{source_label} returned no matched numeric pricing offers")
    return _persist_source(
        engine=engine,
        source_name=f"pricing_{destination_id}",
        source_url=source_url,
        source_label=source_label,
        destination_id=destination_id,
        matched=matched,
        unmatched=[],
        canary=None,
    )


def _update_legacy_scalar_prices(conn, destination_id: str, matched: list[dict[str, Any]]) -> None:
    if destination_id != "openrouter" and not destination_id.endswith("-direct"):
        return
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in matched:
        if str(item.get("service_tier") or "standard") == "standard":
            by_model[str(item["model_id"])].append(item)
    for model_id, items in by_model.items():
        if destination_id == "openrouter":
            has_direct = fetch_one(
                conn,
                select(offers_table.c.id).where(
                    offers_table.c.model_id == model_id,
                    offers_table.c.destination_id.like("%-direct"),
                    offers_table.c.active == 1,
                ).limit(1),
            )
            if has_direct:
                continue
        input_price: float | None = None
        output_price: float | None = None
        for component in (component for item in items for component in item.get("components") or []):
            if component.get("modality") != "text" or component.get("billing_unit") != "token":
                continue
            quantity = float(component.get("unit_quantity") or 1)
            normalized_amount = float(component.get("amount") or 0) * 1_000_000.0 / quantity
            if component.get("charge_type") == "input" and input_price is None:
                input_price = normalized_amount
            if component.get("charge_type") == "output" and output_price is None:
                output_price = normalized_amount
        values: dict[str, Any] = {}
        if input_price is not None:
            values["price_input_per_mtok"] = input_price
        if output_price is not None:
            values["price_output_per_mtok"] = output_price
        if values:
            conn.execute(update(models_table).where(models_table.c.id == model_id).values(**values))


def _tier_from_entry(entry: Mapping[str, Any]) -> str:
    text = normalize_text(" ".join(str(value) for value in entry.values()))
    for tier in ("batch", "priority", "provisioned", "serverless"):
        if tier in text:
            return tier
    return "standard"


def load_pricing_offers(conn, model_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not model_ids:
        return {}
    rows = fetch_all(
        conn,
        select(offers_table).where(offers_table.c.model_id.in_(model_ids), offers_table.c.active == 1)
        .order_by(offers_table.c.destination_id, offers_table.c.service_tier, offers_table.c.region),
    )
    offer_ids = [int(row["id"]) for row in rows]
    component_rows = (
        fetch_all(conn, select(components_table).where(components_table.c.offer_id.in_(offer_ids)).order_by(components_table.c.id))
        if offer_ids else []
    )
    components_by_offer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for component in component_rows:
        components_by_offer[int(component["offer_id"])].append(
            {
                "modality": component["modality"],
                "charge_type": component["charge_type"],
                "amount": component.get("amount"),
                "billing_unit": component["billing_unit"],
                "unit_quantity": component["unit_quantity"],
                "conditions": _json_object(component.get("conditions_json")),
            }
        )
    now = datetime.now(timezone.utc)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        stale = _is_stale(row.get("verified_at"), now=now)
        grouped[str(row["model_id"])].append(
            {
                "id": int(row["id"]),
                "destination_id": row["destination_id"],
                "provider_model_id": row.get("provider_model_id"),
                "service_tier": row.get("service_tier") or "standard",
                "region": row.get("region"),
                "currency": row.get("currency") or "USD",
                "constraints": _json_object(row.get("constraints_json")),
                "price_status": row.get("price_status") or "published",
                "components": components_by_offer.get(int(row["id"]), []),
                "provenance": {
                    "kind": row.get("source_type") or "official",
                    "label": _source_label(str(row.get("source_name") or "")),
                    "url": row.get("source_url"),
                    "verified_at": row.get("verified_at"),
                    "stale": stale,
                },
            }
        )
    return dict(grouped)


def attach_pricing(model: dict[str, Any], offers: list[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(model)
    by_destination: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for offer in offers:
        by_destination[str(offer.get("destination_id") or "")].append(offer)
    destinations = [dict(destination) for destination in payload.get("inference_destinations") or []]
    known = {str(destination.get("id") or "") for destination in destinations}
    from .inference_catalog import materialize_destination

    for destination_id in by_destination:
        if destination_id and destination_id not in known:
            destinations.append(materialize_destination(destination_id))
    for destination in destinations:
        destination["pricing_offers"] = by_destination.get(str(destination.get("id") or ""), [])
    payload["inference_destinations"] = destinations
    fresh = [offer for offer in offers if not bool((offer.get("provenance") or {}).get("stale"))]
    payload["pricing_summary"] = {
        "priced_route_count": len({str(offer.get("destination_id") or "") for offer in fresh}),
        "offer_count": len(fresh),
        "currencies": sorted({str(offer.get("currency") or "") for offer in fresh if offer.get("currency")}),
        "stale_offer_count": len(offers) - len(fresh),
    }
    return payload


def merge_model_pricing(conn, duplicate_id: str, canonical_id: str) -> None:
    duplicate_rows = fetch_all(conn, select(offers_table).where(offers_table.c.model_id == duplicate_id))
    for row in duplicate_rows:
        collision = None
        if row.get("active"):
            canonical_active = fetch_all(
                conn,
                select(offers_table).where(
                    offers_table.c.model_id == canonical_id,
                    offers_table.c.destination_id == row["destination_id"],
                    offers_table.c.active == 1,
                ),
            )
            collision = next(
                (candidate for candidate in canonical_active if _merge_offer_identity(candidate) == _merge_offer_identity(row)),
                None,
            )
        if collision:
            keep_duplicate = str(row.get("verified_at") or "") > str(collision.get("verified_at") or "")
            losing_id = int(collision["id"] if keep_duplicate else row["id"])
            conn.execute(update(offers_table).where(offers_table.c.id == losing_id).values(active=0, superseded_at=utc_now_iso()))
        conn.execute(update(offers_table).where(offers_table.c.id == row["id"]).values(model_id=canonical_id))


def _merge_offer_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Identify the same published route independently of changing rate values."""
    return (
        row.get("destination_id"), row.get("provider_model_id"), row.get("service_tier") or "standard",
        row.get("region"), row.get("currency") or "USD", row.get("constraints_json") or "{}",
        row.get("source_name"),
    )


def _match_offers(
    parsed: list[dict[str, Any]],
    model_rows: list[dict[str, Any]],
    aliases: Mapping[str, str],
    provider_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    provider_rows = [row for row in model_rows if _provider_matches(row.get("provider"), provider_name)]
    index = _model_name_index(provider_rows)
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for item in parsed:
        published_id = str(item.get("published_model_id") or "")
        target = aliases.get(published_id) or aliases.get(_normal(published_id))
        model_id = target if target and any(str(row["id"]) == target for row in provider_rows) else _resolve_model_id(published_id, index)
        if model_id is None:
            model_id = _resolve_model_id(_TIER_RE.sub("", published_id).strip(" -–—()"), index)
        if not model_id:
            unmatched.append(item)
            continue
        matched.append({**item, "model_id": model_id})
    return matched, unmatched


def _model_name_index(rows: list[dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for row in rows:
        model_id = str(row["id"])
        for value in (
            row.get("id"), row.get("name"), row.get("canonical_model_id"), row.get("canonical_model_name"),
            row.get("openrouter_model_id"), row.get("openrouter_canonical_slug"),
        ):
            text = str(value or "").strip()
            if not text:
                continue
            index.setdefault(_normal(text), model_id)
            for signature in name_signatures(text):
                index.setdefault(f"sig:{signature}", model_id)
    return index


def _resolve_model_id(value: str, index: Mapping[str, str]) -> str | None:
    direct = index.get(_normal(value))
    if direct:
        return direct
    for signature in name_signatures(value):
        if f"sig:{signature}" in index:
            return index[f"sig:{signature}"]
    return None


def _offer_key(item: Mapping[str, Any]) -> str:
    raw = json.dumps(
        {
            "provider_model_id": item.get("provider_model_id") or item.get("published_model_id"),
            "service_tier": item.get("service_tier") or "standard",
            "region": item.get("region"),
            "constraints": item.get("constraints") or {},
            "components": item.get("components") or [],
            "index": item.get("_index"),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _write_raw_record(conn, source_run_id: int, item: Mapping[str, Any], source_url: str, *, normalized_model_id: str | None) -> None:
    raw_name = str(item.get("published_model_id") or item.get("provider_model_id") or "Unknown")
    conn.execute(
        raw_source_records_table.insert().values(
            source_run_id=source_run_id,
            benchmark_id=None,
            raw_model_name=raw_name,
            normalized_model_id=normalized_model_id,
            raw_key=raw_name,
            raw_value=None,
            payload_json=json.dumps(item.get("raw") or item, sort_keys=True, default=str),
            source_url=source_url,
            source_type="primary",
            collected_at=utc_now_iso(),
            resolution_status="resolved" if normalized_model_id else "unresolved",
        )
    )


def _record_failed_run(engine, source_name: str, error: str) -> None:
    now = utc_now_iso()
    with engine.begin() as conn:
        conn.execute(
            source_runs_table.insert().values(
                update_log_id=None,
                source_name=source_name,
                benchmark_id=None,
                started_at=now,
                completed_at=now,
                status="failed",
                records_found=0,
                error_message=error,
                details_json=json.dumps({"last_known_good_preserved": True}, sort_keys=True),
            )
        )


def record_failed_pricing_run(source_name: str, error: str, *, engine=None) -> None:
    """Record a rejected source parse without modifying active pricing rows."""
    _record_failed_run(engine or get_engine(), source_name, error)


def _source_label(source_name: str) -> str:
    key = source_name.removeprefix("pricing_")
    if key in PROVIDER_SOURCES:
        return PROVIDER_SOURCES[key]["label"]
    return key.replace("-", " ").replace("_", " ").title() + " pricing"


def _is_stale(value: Any, *, now: datetime) -> bool:
    try:
        verified = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if verified.tzinfo is None:
            verified = verified.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return verified < now - timedelta(days=STALE_AFTER_DAYS)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normal(value: Any) -> str:
    return normalize_text(str(value or "")).replace(" ", "")


def _provider_matches(actual: Any, expected: str) -> bool:
    actual_key = _normal(actual)
    expected_key = _normal(expected)
    if expected_key == "google":
        return actual_key.startswith("google")
    return actual_key == expected_key


def _alias_config() -> dict[str, Any]:
    try:
        payload = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"aliases": {}, "canaries": {}}
    return payload if isinstance(payload, dict) else {"aliases": {}, "canaries": {}}


__all__ = [
    "MIN_REFRESH_COVERAGE",
    "PROVIDER_SOURCES",
    "PricingRefreshRejected",
    "STALE_AFTER_DAYS",
    "attach_pricing",
    "load_pricing_offers",
    "merge_model_pricing",
    "parse_official_pricing_html",
    "persist_cloud_pricing",
    "persist_parsed_source",
    "record_failed_pricing_run",
    "sync_openrouter_items",
    "sync_pricing",
]
