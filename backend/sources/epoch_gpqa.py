from __future__ import annotations

import csv
from io import StringIO
from typing import Sequence

import httpx

from .base import (
    BaseSourceAdapter,
    RawSourceRecord,
    ScoreCandidate,
    first_non_empty,
    percent_score,
    safe_float,
    utc_now_iso,
)


class EpochGpqaAdapter(BaseSourceAdapter):
    source_id = "epoch_ai"
    benchmark_ids = ("gpqa_diamond",)
    source_url = "https://epoch.ai/data/benchmarks.csv"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0)
        response.raise_for_status()

        reader = csv.DictReader(StringIO(response.text))
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in reader:
            task = first_non_empty(row.get("task"), row.get("Task"))
            if not task.lower().startswith("gpqa diamond"):
                continue

            model_name = first_non_empty(
                row.get("Unique display name"),
                row.get("Display name"),
                row.get("Model"),
                row.get("id_model_version"),
            )
            model_key = first_non_empty(row.get("id_model_version"), model_name)
            raw_score = first_non_empty(row.get("mean_score"), row.get("Mean score"))
            if not model_name or not raw_score:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="gpqa_diamond",
                    raw_model_name=model_name,
                    raw_value=raw_score,
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=model_key,
                    payload=row,
                    metadata={
                        "task": task,
                        "task_version": first_non_empty(row.get("task version"), row.get("task_version")),
                        "organization": first_non_empty(row.get("Organization"), row.get("organization")),
                        "stderr": safe_float(first_non_empty(row.get("stderr"), row.get("StdErr"))),
                        "status": first_non_empty(row.get("Status"), row.get("status")),
                    },
                )
            )

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        best_by_model: dict[str, RawSourceRecord] = {}

        for record in raw_records:
            model_key = record.raw_model_key or record.raw_model_name
            current_value = percent_score(record.raw_value)
            if current_value is None:
                continue

            best = best_by_model.get(model_key)
            best_value = percent_score(best.raw_value) if best else None
            if best is None or best_value is None or current_value > best_value:
                best_by_model[model_key] = record

        candidates: list[ScoreCandidate] = []
        for model_key, record in sorted(best_by_model.items(), key=lambda item: item[1].raw_model_name.lower()):
            value = percent_score(record.raw_value)
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="gpqa_diamond",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=model_key,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes=first_non_empty(
                        f"GPQA task: {record.metadata.get('task')}",
                        f"Task version: {record.metadata.get('task_version')}",
                    )
                    or None,
                    metadata={
                        **record.metadata,
                        "source_row_count": sum(
                            1 for item in raw_records if (item.raw_model_key or item.raw_model_name) == model_key
                        ),
                    },
                )
            )

        return candidates
