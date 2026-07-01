from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, safe_float, utc_now_iso


LIVEBENCH_RELEASE = "2026-01-08"
LIVEBENCH_RELEASE_SLUG = LIVEBENCH_RELEASE.replace("-", "_")
LIVEBENCH_BASE_URL = "https://livebench.ai"
LIVEBENCH_LEADERBOARD_URL = f"{LIVEBENCH_BASE_URL}/table_{LIVEBENCH_RELEASE_SLUG}.csv"
LIVEBENCH_CATEGORIES_URL = f"{LIVEBENCH_BASE_URL}/categories_{LIVEBENCH_RELEASE_SLUG}.json"

LIVEBENCH_CATEGORY_BENCHMARKS: dict[str, tuple[str, str]] = {
    "Reasoning": ("livebench_reasoning", "Reasoning"),
    "Coding": ("livebench_coding", "Coding"),
    "Agentic Coding": ("livebench_agentic_coding", "Agentic Coding"),
    "Mathematics": ("livebench_math", "Mathematics"),
    "Data Analysis": ("livebench_data_analysis", "Data Analysis"),
    "Language": ("livebench_language", "Language"),
    "IF": ("livebench_instruction_following", "Instruction Following"),
}


class LiveBenchAdapter(BaseSourceAdapter):
    source_id = "livebench"
    benchmark_ids = (
        "livebench_overall",
        "livebench_reasoning",
        "livebench_coding",
        "livebench_agentic_coding",
        "livebench_math",
        "livebench_data_analysis",
        "livebench_language",
        "livebench_instruction_following",
    )
    source_url = "https://livebench.ai/"
    leaderboard_url = LIVEBENCH_LEADERBOARD_URL
    categories_url = LIVEBENCH_CATEGORIES_URL
    release = LIVEBENCH_RELEASE

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        table_response = await client.get(self.leaderboard_url, timeout=30.0)
        table_response.raise_for_status()
        categories_response = await client.get(self.categories_url, timeout=30.0)
        categories_response.raise_for_status()

        return self._build_raw_records(table_response.text, categories_response.text, collected_at=utc_now_iso())

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            category_scores = record.metadata.get("category_scores") or {}
            if not isinstance(category_scores, dict):
                category_scores = {}

            overall = safe_float(record.metadata.get("overall_score"))
            if overall is not None:
                candidates.append(
                    self._score_candidate(
                        record,
                        benchmark_id="livebench_overall",
                        value=overall,
                        metric_label="overall category average",
                    )
                )

            for category_name, score in category_scores.items():
                mapped = LIVEBENCH_CATEGORY_BENCHMARKS.get(str(category_name))
                if mapped is None:
                    continue
                benchmark_id, label = mapped
                value = safe_float(score)
                if value is None:
                    continue
                candidates.append(
                    self._score_candidate(
                        record,
                        benchmark_id=benchmark_id,
                        value=value,
                        metric_label=f"{label} category average",
                    )
                )

        return candidates

    def _score_candidate(
        self,
        record: RawSourceRecord,
        *,
        benchmark_id: str,
        value: float,
        metric_label: str,
    ) -> ScoreCandidate:
        return ScoreCandidate(
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
            notes=f"LiveBench {self.release} {metric_label}.",
            metadata={
                **record.metadata,
                        "metric": benchmark_id,
                        "metric_label": metric_label,
                        "source_policy": "category_average_from_official_static_table",
                    },
        )

    def _build_raw_records(
        self,
        table_csv: str,
        categories_json: str,
        *,
        collected_at: str,
    ) -> list[RawSourceRecord]:
        categories = self._parse_categories(categories_json)
        rows = csv.DictReader(StringIO(table_csv))
        expected_fields = set(rows.fieldnames or [])
        category_tasks = {task for tasks in categories.values() for task in tasks}
        missing_fields = sorted(category_tasks - expected_fields)
        if missing_fields:
            raise ValueError(f"LiveBench table is missing category task columns: {', '.join(missing_fields)}")

        table_sha256 = hashlib.sha256(table_csv.encode("utf-8")).hexdigest()
        raw_records: list[RawSourceRecord] = []

        for row in rows:
            if None in row:
                continue
            model_name = first_non_empty(row.get("model"))
            if not model_name:
                continue

            task_scores = _task_scores(row)
            if not category_tasks.issubset(task_scores):
                continue
            category_scores = _category_scores(task_scores, categories)
            overall_score = _mean(category_scores.values())
            if overall_score is None:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="livebench_overall",
                    raw_model_name=model_name,
                    raw_value=_format_value(overall_score),
                    source_url=self.leaderboard_url,
                    collected_at=collected_at,
                    raw_model_key=model_name,
                    payload=dict(row),
                    metadata={
                        "release": self.release,
                        "release_date": self.release,
                        "leaderboard_url": self.leaderboard_url,
                        "artifact_url": self.leaderboard_url,
                        "artifact_sha256": table_sha256,
                        "categories_url": self.categories_url,
                        "category_scores": category_scores,
                        "overall_score": overall_score,
                        "task_scores": task_scores,
                        "task_count": len(task_scores),
                        "source_policy": "category_average_from_official_static_table",
                    },
                )
            )

        return raw_records

    def _parse_categories(self, categories_json: str) -> dict[str, list[str]]:
        payload = json.loads(categories_json)
        if not isinstance(payload, dict):
            raise ValueError("LiveBench categories payload must be a JSON object.")

        categories: dict[str, list[str]] = {}
        for category_name, tasks in payload.items():
            if not isinstance(tasks, list):
                continue
            task_names = [str(task).strip() for task in tasks if str(task).strip()]
            if task_names:
                categories[str(category_name)] = task_names

        if not categories:
            raise ValueError("LiveBench categories payload did not contain any task lists.")
        return categories


def _task_scores(row: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for key, value in row.items():
        if key == "model":
            continue
        score = safe_float(value)
        if score is not None:
            scores[key] = score
    return scores


def _category_scores(task_scores: dict[str, float], categories: dict[str, list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for category_name, task_names in categories.items():
        values = [task_scores[task_name] for task_name in task_names if task_name in task_scores]
        category_score = _mean(values)
        if category_score is not None:
            scores[category_name] = category_score
    return scores


def _mean(values: Sequence[float] | Any) -> float | None:
    numeric_values = [score for value in values if (score := safe_float(value)) is not None]
    if not numeric_values:
        return None
    return sum(numeric_values) / len(numeric_values)


def _format_value(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
