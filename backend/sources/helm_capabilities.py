from __future__ import annotations

import json
from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, percent_score, utc_now_iso


RELEASE = "v1.15.0"
BASE_URL = f"https://storage.googleapis.com/crfm-helm-public/capabilities/benchmark_output/releases/{RELEASE}"
GROUP_NAME = "core_scenarios"
GROUP_URL = f"{BASE_URL}/groups/{GROUP_NAME}.json"
SCHEMA_URL = f"{BASE_URL}/schema.json"
SUMMARY_URL = f"{BASE_URL}/summary.json"

METRICS = {
    "Mean score": ("helm_capabilities_mean", "Mean accuracy score"),
    "MMLU-Pro - COT correct": ("helm_capabilities_mmlu_pro", "MMLU-Pro COT correct"),
    "GPQA - COT correct": ("helm_capabilities_gpqa", "GPQA COT correct"),
    "IFEval - IFEval Strict Acc": ("helm_capabilities_ifeval", "IFEval strict accuracy"),
    "WildBench - WB Score": ("helm_capabilities_wildbench", "WildBench score"),
    "Omni-MATH - Acc": ("helm_capabilities_omni_math", "Omni-MATH accuracy"),
}


class HelmCapabilitiesAdapter(BaseSourceAdapter):
    source_id = "helm_capabilities"
    benchmark_ids = tuple(benchmark_id for benchmark_id, _ in METRICS.values())
    source_url = "https://crfm.stanford.edu/helm/capabilities/latest/"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        summary_response = await client.get(SUMMARY_URL, timeout=30.0)
        summary_response.raise_for_status()
        summary = summary_response.json()

        schema_response = await client.get(SCHEMA_URL, timeout=30.0)
        schema_response.raise_for_status()
        schema = schema_response.json()
        model_lookup = _build_model_lookup(schema)

        group_response = await client.get(GROUP_URL, timeout=30.0)
        group_response.raise_for_status()
        group_tables = group_response.json()
        if not isinstance(group_tables, list):
            raise ValueError("HELM capabilities group payload was not a JSON array.")

        accuracy_table = _select_accuracy_table(group_tables)
        header_values = [str(cell.get("value") or "") for cell in accuracy_table.get("header") or []]
        rows = accuracy_table.get("rows") or []
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                continue

            model_cell = row[0] if isinstance(row[0], dict) else {}
            model_display_name = str(model_cell.get("value") or "").strip()
            if not model_display_name:
                continue

            model_info = model_lookup.get(model_display_name, {})
            metrics: dict[str, dict[str, Any]] = {}
            for index, header in enumerate(header_values):
                if header not in METRICS or index >= len(row):
                    continue
                cell = row[index] if isinstance(row[index], dict) else {}
                value = cell.get("value")
                if value is None:
                    continue
                benchmark_id, metric_label = METRICS[header]
                metrics[benchmark_id] = {
                    "header": header,
                    "label": metric_label,
                    "value": value,
                    "description": cell.get("description"),
                    "run_spec_names": cell.get("run_spec_names") or [],
                }

            if not metrics:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="helm_capabilities_mean",
                    raw_model_name=model_display_name,
                    raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
                    source_url=GROUP_URL,
                    collected_at=fetched_at,
                    raw_model_key=first_non_empty(model_info.get("name"), model_display_name),
                    payload={"row": row},
                    metadata={
                        "project": "capabilities",
                        "release": summary.get("release") or RELEASE,
                        "release_date": summary.get("date"),
                        "group_name": GROUP_NAME,
                        "table_title": accuracy_table.get("title"),
                        "model": model_info,
                        "metrics": metrics,
                        "source_policy": "official_helm_capabilities_core_scenarios_accuracy",
                    },
                )
            )

        if not raw_records:
            raise ValueError("Could not parse any HELM Capabilities core scenario rows.")
        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            metrics = record.metadata.get("metrics")
            if not isinstance(metrics, dict):
                try:
                    parsed = json.loads(record.raw_value)
                except json.JSONDecodeError:
                    continue
                metrics = parsed if isinstance(parsed, dict) else {}

            for benchmark_id, metric in metrics.items():
                if not isinstance(metric, dict):
                    continue
                value = percent_score(metric.get("value"))
                if value is None:
                    continue

                candidates.append(
                    ScoreCandidate(
                        source_id=self.source_id,
                        benchmark_id=benchmark_id,
                        raw_model_name=record.raw_model_name,
                        raw_model_key=record.raw_model_key or record.raw_model_name,
                        value=value,
                        raw_value=_format_value(value),
                        source_url=record.source_url,
                        collected_at=record.collected_at,
                        source_type="primary",
                        verified=True,
                        notes=(
                            f"Official HELM Capabilities {record.metadata.get('release') or RELEASE} "
                            f"{metric.get('label') or benchmark_id} score."
                        ),
                        metadata={
                            **record.metadata,
                            "metric": metric,
                            "benchmark_id": benchmark_id,
                        },
                    )
                )

        return candidates


def _select_accuracy_table(group_tables: list[Any]) -> dict[str, Any]:
    for table in group_tables:
        if isinstance(table, dict) and str(table.get("title") or "").strip() == "Accuracy":
            return table
    raise ValueError("Could not find HELM Capabilities Accuracy table.")


def _build_model_lookup(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in schema.get("models") or []:
        if not isinstance(item, dict):
            continue
        normalized = {
            "name": item.get("name"),
            "display_name": item.get("display_name"),
            "short_display_name": item.get("short_display_name"),
            "creator_organization": item.get("creator_organization"),
            "access": item.get("access"),
            "release_date": item.get("release_date"),
        }
        for key in (item.get("display_name"), item.get("short_display_name"), item.get("name")):
            key_text = str(key or "").strip()
            if key_text:
                lookup.setdefault(key_text, normalized)
    return lookup


def _format_value(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
