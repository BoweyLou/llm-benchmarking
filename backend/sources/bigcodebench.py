from __future__ import annotations

import json
from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, safe_float, utc_now_iso


DATASETS = (
    {
        "name": "Full",
        "result_url": "https://bigcode-bench.github.io/results.json",
        "benchmark_prefix": "bigcodebench_full",
    },
    {
        "name": "Hard",
        "result_url": "https://bigcode-bench.github.io/results-hard.json",
        "benchmark_prefix": "bigcodebench_hard",
    },
)

METRICS = (
    ("", "average", "Average Pass@1"),
    ("_instruct", "instruct", "Instruct Pass@1"),
    ("_complete", "complete", "Complete Pass@1"),
)


class BigCodeBenchAdapter(BaseSourceAdapter):
    source_id = "bigcodebench"
    benchmark_ids = tuple(
        f"{dataset['benchmark_prefix']}{metric_suffix}" for dataset in DATASETS for metric_suffix, _, _ in METRICS
    )
    source_url = "https://bigcode-bench.github.io/"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for dataset in DATASETS:
            result_url = str(dataset["result_url"])
            response = await client.get(result_url, timeout=30.0)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"BigCodeBench payload at {result_url} was not a JSON object.")

            for model_name, row in payload.items():
                if not isinstance(row, dict):
                    continue

                pass_at_1 = row.get("pass@1")
                if not isinstance(pass_at_1, dict):
                    continue
                if not any(safe_float(pass_at_1.get(metric_key)) is not None for _, metric_key, _ in METRICS):
                    continue

                model_name_text = str(model_name).strip()
                if not model_name_text:
                    continue

                metadata = {
                    "dataset": dataset["name"],
                    "result_url": result_url,
                    "model_link": row.get("link"),
                    "open_data": row.get("open-data"),
                    "prompted": row.get("prompted"),
                    "moe": row.get("moe"),
                    "size_b": row.get("size"),
                    "active_parameters_b": row.get("act_param"),
                    "leaderboard_date": row.get("date"),
                    "prefill": row.get("prefill"),
                    "pass_at_1": dict(pass_at_1),
                    "source_policy": "official_leaderboard_pass_at_1_greedy",
                }

                raw_records.append(
                    RawSourceRecord(
                        source_id=self.source_id,
                        benchmark_id=str(dataset["benchmark_prefix"]),
                        raw_model_name=model_name_text,
                        raw_value=json.dumps(pass_at_1, ensure_ascii=True, sort_keys=True),
                        source_url=result_url,
                        collected_at=fetched_at,
                        raw_model_key=model_name_text,
                        payload=dict(row),
                        metadata=metadata,
                    )
                )

        if not raw_records:
            raise ValueError("Could not parse any BigCodeBench leaderboard rows.")
        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            pass_at_1 = record.metadata.get("pass_at_1")
            if not isinstance(pass_at_1, dict):
                try:
                    parsed = json.loads(record.raw_value)
                except json.JSONDecodeError:
                    continue
                pass_at_1 = parsed if isinstance(parsed, dict) else {}

            for metric_suffix, metric_key, metric_label in METRICS:
                value = _metric_value(pass_at_1, metric_key)
                if value is None:
                    continue

                benchmark_id = f"{record.benchmark_id}{metric_suffix}"
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
                            f"Official BigCodeBench {record.metadata.get('dataset') or 'unknown'} "
                            f"{metric_label} leaderboard score."
                        ),
                        metadata={
                            **record.metadata,
                            "metric": metric_key,
                            "metric_label": metric_label,
                            "benchmark_id": benchmark_id,
                            "model_link": first_non_empty(record.metadata.get("model_link")),
                        },
                    )
                )

        return candidates


def _metric_value(pass_at_1: dict[str, Any], metric_key: str) -> float | None:
    if metric_key == "average":
        instruct = safe_float(pass_at_1.get("instruct"))
        complete = safe_float(pass_at_1.get("complete"))
        if instruct is None or complete is None:
            return None
        return round((instruct + complete) / 2.0, 1)
    return safe_float(pass_at_1.get(metric_key))


def _format_value(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")
