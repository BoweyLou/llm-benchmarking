"""Curated model-discovery helpers for metadata-only catalog expansion."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
from typing import Any, Iterable

import httpx


MODEL_DISCOVERY_BASELINE_PATH = Path(__file__).with_name("model_discovery_baseline.json")
HUGGINGFACE_MODELS_API_URL = "https://huggingface.co/api/models"
SMALL_MODEL_ACTIVE_PARAMETER_THRESHOLD_B = 15.0
SMALL_MODEL_TOTAL_PARAMETER_THRESHOLD_B = 15.0

_ACTIVE_PARAMETER_RE = re.compile(r"(?<![A-Za-z0-9])(?:A|E)(\d+(?:\.\d+)?)\s*B(?![A-Za-z0-9])", re.IGNORECASE)
_TOTAL_PARAMETER_B_RE = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*B(?![A-Za-z0-9])", re.IGNORECASE)
_TOTAL_PARAMETER_M_RE = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*M(?![A-Za-z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class ModelSizeMetadata:
    parameter_count_b: float | None
    active_parameter_count_b: float | None
    model_size_class: str | None
    small_model_candidate: bool


def load_model_discovery_baseline(path: Path | None = None) -> dict[str, Any]:
    baseline_path = path or MODEL_DISCOVERY_BASELINE_PATH
    if not baseline_path.exists():
        return {"version": 1, "sources": []}
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Model discovery baseline must be a JSON object.")
    sources = payload.get("sources")
    if sources is None:
        payload["sources"] = []
    elif not isinstance(sources, list):
        raise ValueError("Model discovery baseline sources must be a list.")
    return payload


def huggingface_discovery_entries(*, family: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    baseline = load_model_discovery_baseline(path)
    family_filter = _clean_text(family).lower()
    entries: list[dict[str, Any]] = []
    for item in baseline.get("sources", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("source") or "").strip().lower() != "huggingface":
            continue
        if family_filter and str(item.get("family") or "").strip().lower() != family_filter:
            continue
        entries.append(dict(item))
    return entries


def fetch_huggingface_discovery_items(
    client: httpx.Client,
    entry: dict[str, Any],
    *,
    api_url: str = HUGGINGFACE_MODELS_API_URL,
) -> list[dict[str, Any]]:
    author = _clean_text(entry.get("author"))
    queries = _string_list(entry.get("queries")) or [""]
    limit = _positive_int(entry.get("limit"), default=100)
    items_by_id: dict[str, dict[str, Any]] = {}

    for query in queries:
        params: dict[str, Any] = {"limit": limit, "full": "true"}
        if author:
            params["author"] = author
        if query:
            params["search"] = query
        response = client.get(api_url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Hugging Face model discovery response must be a list.")
        for item in payload:
            if not isinstance(item, dict):
                continue
            repo_id = _repo_id_from_item(item)
            if repo_id:
                items_by_id[repo_id] = item

    return [items_by_id[repo_id] for repo_id in sorted(items_by_id)]


def filter_huggingface_discovery_items(items: Iterable[dict[str, Any]], entry: dict[str, Any]) -> list[dict[str, Any]]:
    include_patterns = _string_list(entry.get("include_patterns"))
    exclude_patterns = _string_list(entry.get("exclude_patterns"))
    trusted_mirrors = _string_list(entry.get("trusted_mirrors"))
    allowed_authors = {
        str(author).strip().lower()
        for author in [entry.get("author"), *trusted_mirrors]
        if str(author or "").strip()
    }

    filtered: list[dict[str, Any]] = []
    for item in items:
        repo_id = _repo_id_from_item(item)
        if not repo_id:
            continue
        author = repo_id.split("/", 1)[0].lower() if "/" in repo_id else ""
        if allowed_authors and author not in allowed_authors:
            continue
        if include_patterns and not any(fnmatchcase(repo_id, pattern) for pattern in include_patterns):
            continue
        if exclude_patterns and any(fnmatchcase(repo_id, pattern) for pattern in exclude_patterns):
            continue
        filtered.append(item)
    return filtered


def repo_id_from_huggingface_item(item: dict[str, Any]) -> str | None:
    return _repo_id_from_item(item)


def infer_model_size_metadata(*values: Any) -> ModelSizeMetadata:
    texts = [text for value in values for text in _text_values(value)]
    active_values: list[float] = []
    total_values_b: list[float] = []

    for text in texts:
        active_values.extend(float(match.group(1)) for match in _ACTIVE_PARAMETER_RE.finditer(text))
        total_values_b.extend(float(match.group(1)) for match in _TOTAL_PARAMETER_B_RE.finditer(text))
        total_values_b.extend(float(match.group(1)) / 1000.0 for match in _TOTAL_PARAMETER_M_RE.finditer(text))

    active_parameter_count_b = _min_or_none(active_values)
    parameter_count_b = _min_or_none(total_values_b)
    size_basis = active_parameter_count_b if active_parameter_count_b is not None else parameter_count_b
    model_size_class = _size_class(size_basis)
    small_model_candidate = False
    if active_parameter_count_b is not None:
        small_model_candidate = active_parameter_count_b <= SMALL_MODEL_ACTIVE_PARAMETER_THRESHOLD_B
    elif parameter_count_b is not None:
        small_model_candidate = parameter_count_b <= SMALL_MODEL_TOTAL_PARAMETER_THRESHOLD_B

    return ModelSizeMetadata(
        parameter_count_b=parameter_count_b,
        active_parameter_count_b=active_parameter_count_b,
        model_size_class=model_size_class,
        small_model_candidate=small_model_candidate,
    )


def model_size_values_from_metadata(metadata: ModelSizeMetadata, *, source_name: str, source_url: str, verified_at: str) -> dict[str, Any]:
    values: dict[str, Any] = {
        "small_model_candidate": 1 if metadata.small_model_candidate else 0,
    }
    if metadata.parameter_count_b is not None:
        values["parameter_count_b"] = metadata.parameter_count_b
    if metadata.active_parameter_count_b is not None:
        values["active_parameter_count_b"] = metadata.active_parameter_count_b
    if metadata.model_size_class:
        values["model_size_class"] = metadata.model_size_class
    if any(key in values for key in ("parameter_count_b", "active_parameter_count_b", "model_size_class")):
        values.update(
            model_size_source_name=source_name,
            model_size_source_url=source_url,
            model_size_verified_at=verified_at,
        )
    return values


def _repo_id_from_item(item: dict[str, Any]) -> str | None:
    for key in ("modelId", "id"):
        value = _clean_text(item.get(key))
        if value and "/" in value:
            return value
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable) and not isinstance(value, dict):
        values = value
    else:
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        return [
            text
            for item in value.values()
            for text in _text_values(item)
        ]
    if isinstance(value, Iterable):
        return [
            text
            for item in value
            for text in _text_values(item)
        ]
    text = str(value or "").strip()
    return [text] if text else []


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _min_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return min(values)


def _size_class(value_b: float | None) -> str | None:
    if value_b is None:
        return None
    if value_b <= 15.0:
        return "small"
    if value_b <= 40.0:
        return "medium"
    return "large"


__all__ = [
    "HUGGINGFACE_MODELS_API_URL",
    "MODEL_DISCOVERY_BASELINE_PATH",
    "ModelSizeMetadata",
    "fetch_huggingface_discovery_items",
    "filter_huggingface_discovery_items",
    "huggingface_discovery_entries",
    "infer_model_size_metadata",
    "load_model_discovery_baseline",
    "model_size_values_from_metadata",
    "repo_id_from_huggingface_item",
]
