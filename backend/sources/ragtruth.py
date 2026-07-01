from __future__ import annotations

from collections import defaultdict
import json
from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, safe_float, utc_now_iso


REPO_URL = "https://github.com/ParticleMedia/RAGTruth"
RESPONSE_URL = "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/response.jsonl"
SOURCE_INFO_URL = "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/source_info.jsonl"
DATASET_VERSION = "2024-02"
EVALUATION_SPLIT = "test"

TASK_BENCHMARKS = {
    "Summary": ("ragtruth_summary_hallucination_rate", "Summarization"),
    "QA": ("ragtruth_qa_hallucination_rate", "Question answering"),
    "Data2txt": ("ragtruth_data_to_text_hallucination_rate", "Data-to-text"),
}
OVERALL_BENCHMARK_ID = "ragtruth_hallucination_rate"


class RagtruthAdapter(BaseSourceAdapter):
    source_id = "ragtruth"
    benchmark_ids = (
        OVERALL_BENCHMARK_ID,
        "ragtruth_summary_hallucination_rate",
        "ragtruth_qa_hallucination_rate",
        "ragtruth_data_to_text_hallucination_rate",
    )
    source_url = REPO_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        source_response = await client.get(SOURCE_INFO_URL, timeout=60.0)
        source_response.raise_for_status()
        source_tasks = _source_task_lookup(source_response.text)

        response = await client.get(RESPONSE_URL, timeout=60.0)
        response.raise_for_status()

        aggregates = _aggregate_response_rows(response.text, source_tasks)
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for model_name, aggregate in sorted(aggregates.items(), key=lambda item: item[0].lower()):
            metrics = _build_metrics(aggregate)
            if not metrics:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id=OVERALL_BENCHMARK_ID,
                    raw_model_name=model_name,
                    raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
                    source_url=RESPONSE_URL,
                    collected_at=fetched_at,
                    raw_model_key=model_name,
                    payload={
                        "model": model_name,
                        "split": EVALUATION_SPLIT,
                        "metrics": metrics,
                    },
                    metadata={
                        "dataset_version": DATASET_VERSION,
                        "split": EVALUATION_SPLIT,
                        "response_url": RESPONSE_URL,
                        "source_info_url": SOURCE_INFO_URL,
                        "metrics": metrics,
                        "source_policy": "official_ragtruth_test_split_response_hallucination_rate",
                    },
                )
            )

        if not raw_records:
            raise ValueError("Could not parse any RAGTruth test-split aggregates.")
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
                value = safe_float(metric.get("hallucination_rate"))
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
                            f"Official RAGTruth {record.metadata.get('split')} split "
                            f"{metric.get('label') or benchmark_id} response-level hallucination rate. "
                            "Lower is better; this is historical corpus evidence."
                        ),
                        metadata={
                            **record.metadata,
                            "benchmark_id": benchmark_id,
                            "metric": metric,
                        },
                    )
                )

        return candidates


def _source_task_lookup(text: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        source_id = str(item.get("source_id") or "").strip()
        task_type = str(item.get("task_type") or "").strip()
        if source_id and task_type:
            lookup[source_id] = task_type
    return lookup


def _aggregate_response_rows(text: str, source_tasks: dict[str, str]) -> dict[str, dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = defaultdict(_empty_aggregate)
    for line in text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if str(item.get("split") or "").strip() != EVALUATION_SPLIT:
            continue

        model = str(item.get("model") or "").strip()
        if not model:
            continue
        task_type = source_tasks.get(str(item.get("source_id") or "").strip(), "unknown")
        labels = item.get("labels") if isinstance(item.get("labels"), list) else []
        hallucinated = bool(labels)

        aggregate = aggregates[model]
        _add_example(aggregate["overall"], hallucinated, labels)
        if task_type in TASK_BENCHMARKS:
            _add_example(aggregate["tasks"][task_type], hallucinated, labels)

    return dict(aggregates)


def _empty_aggregate() -> dict[str, Any]:
    return {
        "overall": {"responses": 0, "hallucinated_responses": 0, "hallucination_spans": 0},
        "tasks": defaultdict(lambda: {"responses": 0, "hallucinated_responses": 0, "hallucination_spans": 0}),
    }


def _add_example(target: dict[str, int], hallucinated: bool, labels: list[Any]) -> None:
    target["responses"] += 1
    target["hallucinated_responses"] += 1 if hallucinated else 0
    target["hallucination_spans"] += len(labels)


def _build_metrics(aggregate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    overall = _metric_payload("Overall", aggregate.get("overall") or {})
    if overall is not None:
        metrics[OVERALL_BENCHMARK_ID] = overall

    tasks = aggregate.get("tasks") or {}
    for task_type, (benchmark_id, label) in TASK_BENCHMARKS.items():
        metric = _metric_payload(label, tasks.get(task_type) or {})
        if metric is not None:
            metric["task_type"] = task_type
            metrics[benchmark_id] = metric

    return metrics


def _metric_payload(label: str, stats: dict[str, Any]) -> dict[str, Any] | None:
    responses = int(stats.get("responses") or 0)
    if responses <= 0:
        return None
    hallucinated = int(stats.get("hallucinated_responses") or 0)
    spans = int(stats.get("hallucination_spans") or 0)
    return {
        "label": label,
        "responses": responses,
        "hallucinated_responses": hallucinated,
        "hallucination_spans": spans,
        "hallucination_rate": hallucinated * 100.0 / responses,
    }


def _format_value(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
