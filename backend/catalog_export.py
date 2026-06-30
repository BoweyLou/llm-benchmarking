"""Backend-only catalog export helpers."""

from __future__ import annotations

import json
from typing import Any, Literal

from .update_engine import list_models

CatalogOutputFormat = Literal["json", "jsonl"]


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

    raise ValueError(f"Unsupported model metadata output format: {output_format}")
