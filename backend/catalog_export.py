"""Backend-only catalog export helpers."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

from .update_engine import list_models

CatalogOutputFormat = Literal["json", "jsonl", "csv"]


def build_model_metadata_list() -> list[dict[str, Any]]:
    """Return the active model catalog with all serialized metadata."""
    return list_models()


def render_model_metadata_list(
    models: list[dict[str, Any]],
    *,
    output_format: CatalogOutputFormat = "json",
) -> str:
    if output_format == "json":
        return json.dumps(models, indent=2, sort_keys=True, default=str) + "\n"

    if output_format == "jsonl":
        if not models:
            return ""
        return "\n".join(json.dumps(model, sort_keys=True, default=str) for model in models) + "\n"

    if output_format == "csv":
        return _render_csv(models)

    raise ValueError(f"Unsupported model metadata output format: {output_format}")


def _render_csv(models: list[dict[str, Any]]) -> str:
    if not models:
        return ""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_csv_fieldnames(models), extrasaction="ignore")
    writer.writeheader()
    for model in models:
        writer.writerow({key: _csv_value(value) for key, value in model.items()})
    return output.getvalue()


def _csv_fieldnames(models: list[dict[str, Any]]) -> list[str]:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for model in models:
        for key in model:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    return fieldnames


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)
