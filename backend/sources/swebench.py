from __future__ import annotations

from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, percent_score, utc_now_iso


class SwebenchAdapter(BaseSourceAdapter):
    source_id = "swebench"
    benchmark_ids = ("swebench_verified",)
    source_url = "https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json"
    page_url = "https://www.swebench.com/#verified"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0)
        response.raise_for_status()
        payload = response.json()

        leaderboard = self._select_verified_leaderboard(payload)
        rows = leaderboard.get("results") or leaderboard.get("rows") or leaderboard.get("entries") or []
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in rows:
            model_name = self._extract_model_name(row)
            if not model_name:
                continue

            raw_score = row.get("resolved")
            if not model_name or raw_score is None:
                continue

            tags = row.get("tags") or []
            organization = self._extract_tag_value(tags, "Org: ")
            system_attempts = self._extract_tag_value(tags, "System: ")

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="swebench_verified",
                    raw_model_name=model_name,
                    raw_value=str(raw_score),
                    source_url=self.page_url,
                    collected_at=fetched_at,
                    raw_model_key=model_name,
                    payload=row,
                    metadata={
                        "leaderboard_name": "Verified",
                        "leaderboard_date": row.get("date"),
                        "submission_name": row.get("name"),
                        "submission_organization": organization,
                        "system_attempts": system_attempts,
                        "os_model": bool(row.get("os_model")),
                        "os_system": bool(row.get("os_system")),
                        "verified": True,
                        "single_model_submission": True,
                        "tags": tags,
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
        for model_key, record in sorted(best_by_model.items(), key=lambda item: item[0].lower()):
            value = percent_score(record.raw_value)
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="swebench_verified",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=model_key,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="secondary",
                    verified=bool(record.metadata.get("verified", True)),
                    notes=(
                        "Best single-model submission from the official SWE-bench Verified board: "
                        f'{record.metadata.get("submission_name") or "Unknown submission"} '
                        f'on {record.metadata.get("leaderboard_date") or "unknown date"}.'
                    ),
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _select_verified_leaderboard(self, payload: dict[str, Any]) -> dict[str, Any]:
        leaderboards = payload.get("leaderboards") or []
        for item in leaderboards:
            if str(item.get("name", "")).strip() == "Verified":
                return item
        raise ValueError("Could not find Verified leaderboard in SWE-bench payload.")

    def _extract_model_name(self, row: dict[str, Any]) -> str:
        model_tags = self._extract_model_tags(row.get("tags") or [])
        if len(model_tags) != 1:
            return ""
        return model_tags[0]

    def _extract_model_tags(self, tags: list[Any]) -> list[str]:
        values: list[str] = []
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("Model: "):
                value = tag.split("Model: ", 1)[1].strip()
                if value:
                    values.append(value)
        return values

    def _extract_tag_value(self, tags: list[Any], prefix: str) -> str:
        for tag in tags:
            if isinstance(tag, str) and tag.startswith(prefix):
                return tag.split(prefix, 1)[1].strip()
        return ""
