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
    benchmark_ids = ("mmmu",)
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
            raw_score = validation.get("overall")
            if raw_score in (None, "", "-"):
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="mmmu",
                    raw_model_name=model_name,
                    raw_value=str(raw_score),
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=model_name,
                    payload=row,
                    metadata={
                        "info_type": info.get("type"),
                        "validation_source": validation.get("source"),
                        "test_overall": (row.get("test") or {}).get("overall"),
                        "pro_overall": (row.get("pro") or {}).get("overall"),
                        "date": info.get("date"),
                        "size": info.get("size"),
                    },
                )
            )

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            value = percent_score(record.raw_value)
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="mmmu",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key or record.raw_model_name,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes=first_non_empty(
                        f"MMMU info type: {record.metadata.get('info_type')}",
                        f"Validation source: {record.metadata.get('validation_source')}",
                    )
                    or None,
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
