from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterable

import httpx


def fetch_openrouter_models(
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    items = payload.get("data")
    if not isinstance(items, list):
        raise ValueError("OpenRouter models response did not include a 'data' list.")
    return [item for item in items if isinstance(item, dict)]


def fetch_openrouter_flight_payloads(
    *,
    url: str,
    headers: dict[str, str],
    next_flight_push_re: re.Pattern[str],
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        html = response.text

    payloads: list[dict[str, Any]] = []
    for match in next_flight_push_re.finditer(html):
        try:
            push_args = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(push_args, list) or len(push_args) < 2 or not isinstance(push_args[1], str):
            continue
        chunk = push_args[1]
        if ":" not in chunk:
            continue
        _, serialized = chunk.split(":", 1)
        try:
            parsed = json.loads(serialized)
        except json.JSONDecodeError:
            continue
        payloads.extend(iter_openrouter_payload_dicts(parsed))

    if not payloads:
        raise ValueError(f"OpenRouter page {url} did not expose any JSON payloads.")
    return payloads


def extract_global_rankings(payloads: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ranking_payload = find_openrouter_payload(
        payloads,
        lambda item: isinstance(item.get("rankingData"), list) and item["rankingData"],
    )
    if ranking_payload is None:
        raise ValueError("OpenRouter rankings page did not expose rankingData.")
    ranking_data = ranking_payload.get("rankingData")
    if not isinstance(ranking_data, list):
        raise ValueError("OpenRouter rankings page returned invalid rankingData.")
    return [item for item in ranking_data if isinstance(item, dict)]


def extract_programming_rankings(payloads: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    categories_payload = find_openrouter_payload(
        payloads,
        lambda item: isinstance(item.get("categories"), dict) and item["categories"],
    )
    if categories_payload is None:
        raise ValueError("OpenRouter programming collection did not expose categories.")

    categories = categories_payload.get("categories")
    if not isinstance(categories, dict):
        raise ValueError("OpenRouter programming collection returned invalid categories.")

    entries: list[dict[str, Any]] = []
    for model_slug, model_categories in categories.items():
        if not isinstance(model_categories, list):
            continue
        programming_entry = next(
            (
                entry
                for entry in model_categories
                if isinstance(entry, dict) and str(entry.get("category") or "") == "programming"
            ),
            None,
        )
        if programming_entry is None:
            continue
        enriched_entry = dict(programming_entry)
        enriched_entry["model_slug"] = str(model_slug)
        entries.append(enriched_entry)
    return entries


def iter_openrouter_payload_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_openrouter_payload_dicts(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from iter_openrouter_payload_dicts(child)


def find_openrouter_payload(
    payloads: Iterable[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
) -> dict[str, Any] | None:
    return next((payload for payload in payloads if predicate(payload)), None)
