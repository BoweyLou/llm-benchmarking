from __future__ import annotations

from typing import Any, Sequence

import httpx

from .base import (
    BaseSourceAdapter,
    RawSourceRecord,
    ScoreCandidate,
    first_non_empty,
    percent_score,
    utc_now_iso,
)


class MmmuAdapter(BaseSourceAdapter):
    source_id = "mmmu"
    benchmark_ids = ("mmmu", "mmmu_test", "mmmu_pro")
    source_url = "https://mmmu-benchmark.github.io/leaderboard_data.json"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0)
        response.raise_for_status()

        payload = response.json()
        rows = self._extract_rows(payload)
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in rows:
            info = row.get("info") or {}
            if info.get("type") in {"human_expert", "random_frequent"}:
                continue

            model_name = first_non_empty(info.get("name"), info.get("display_name"), info.get("title"))
            if not model_name:
                continue

            validation = row.get("validation") or {}
            test = row.get("test") or {}
            pro = row.get("pro") or {}
            raw_score = first_non_empty(validation.get("overall"), test.get("overall"), pro.get("overall"))
            if not raw_score:
                continue
            benchmark_id = "mmmu"
            if percent_score(validation.get("overall")) is None:
                benchmark_id = "mmmu_test" if percent_score(test.get("overall")) is not None else "mmmu_pro"

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id=benchmark_id,
                    raw_model_name=model_name,
                    raw_value=str(raw_score),
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=model_name,
                    payload=row,
                    metadata={
                        "info_type": info.get("type"),
                        "model_url": info.get("link"),
                        "validation_source": validation.get("source"),
                        "validation_overall": validation.get("overall"),
                        "test_overall": test.get("overall"),
                        "test_source": test.get("source"),
                        "pro_overall": pro.get("overall"),
                        "pro_source": pro.get("source"),
                        "pro_vision": pro.get("vision"),
                        "pro_original": pro.get("original"),
                        "date": info.get("date"),
                        "size": info.get("size"),
                    },
                )
            )

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            metrics = [
                (
                    "mmmu",
                    record.metadata.get("validation_overall", record.raw_value),
                    "MMMU validation overall score.",
                    record.metadata.get("validation_source"),
                ),
                (
                    "mmmu_test",
                    record.metadata.get("test_overall"),
                    "MMMU test overall score.",
                    record.metadata.get("test_source"),
                ),
                (
                    "mmmu_pro",
                    record.metadata.get("pro_overall"),
                    "MMMU-Pro overall score.",
                    record.metadata.get("pro_source"),
                ),
            ]

            for benchmark_id, raw_value, note_prefix, source in metrics:
                value = percent_score(raw_value)
                if value is None:
                    continue
                notes = first_non_empty(
                    f"{note_prefix} MMMU info type: {record.metadata.get('info_type')}",
                    f"Source: {source}",
                )
                candidates.append(
                    ScoreCandidate(
                        source_id=self.source_id,
                        benchmark_id=benchmark_id,
                        raw_model_name=record.raw_model_name,
                        raw_model_key=record.raw_model_key or record.raw_model_name,
                        value=value,
                        raw_value=str(raw_value),
                        source_url=record.source_url,
                        collected_at=record.collected_at,
                        source_type="primary",
                        verified=True,
                        notes=notes or None,
                        metadata=dict(record.metadata),
                    )
                )

        return candidates

    def _extract_rows(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("leaderboardData", "data", "rows", "models"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
        return []
