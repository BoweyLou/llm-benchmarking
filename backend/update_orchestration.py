from __future__ import annotations

from typing import Any, Iterable, Protocol


class UpdateAdapter(Protocol):
    source_id: str
    benchmark_ids: Iterable[str]


def humanize_source_name(source_name: str, label_overrides: dict[str, str]) -> str:
    if not source_name:
        return "Unknown source"
    if source_name in label_overrides:
        return label_overrides[source_name]
    return " ".join(part.upper() if len(part) <= 3 else part.capitalize() for part in source_name.split("_"))


def build_update_plan(
    adapters: Iterable[UpdateAdapter],
    *,
    post_phases: Iterable[dict[str, Any]],
    label_overrides: dict[str, str],
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for adapter in adapters:
        steps.append(
            {
                "key": f"source:{adapter.source_id}",
                "label": f"Ingest {humanize_source_name(adapter.source_id, label_overrides)}",
                "kind": "source",
                "source_name": adapter.source_id,
                "benchmark_id": ",".join(adapter.benchmark_ids),
            }
        )
    steps.extend(dict(step) for step in post_phases)
    return steps


def has_fatal_update_errors(errors: Iterable[dict[str, Any]]) -> bool:
    return any(not bool(error.get("nonfatal")) for error in errors)
