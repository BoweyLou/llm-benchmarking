from __future__ import annotations

import math
from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, safe_float, utc_now_iso


SPLIT_CONFIGS = (
    {
        "leaderboard_name": "Verified",
        "display_name": "Verified",
        "benchmark_id": "swebench_verified",
        "page_url": "https://www.swebench.com/#verified",
    },
    {
        "leaderboard_name": "Test",
        "display_name": "Full",
        "benchmark_id": "swebench_full",
        "page_url": "https://www.swebench.com/#full",
    },
    {
        "leaderboard_name": "Lite",
        "display_name": "Lite",
        "benchmark_id": "swebench_lite",
        "page_url": "https://www.swebench.com/#lite",
    },
    {
        "leaderboard_name": "Multilingual",
        "display_name": "Multilingual",
        "benchmark_id": "swebench_multilingual",
        "page_url": "https://www.swebench.com/#multilingual",
    },
    {
        "leaderboard_name": "Multimodal",
        "display_name": "Multimodal",
        "benchmark_id": "swebench_multimodal",
        "page_url": "https://www.swebench.com/#multimodal",
    },
)


class SwebenchAdapter(BaseSourceAdapter):
    source_id = "swebench"
    benchmark_ids = tuple(str(config["benchmark_id"]) for config in SPLIT_CONFIGS)
    source_url = "https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json"
    page_url = "https://www.swebench.com/#verified"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0)
        response.raise_for_status()
        payload = response.json()

        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for config in SPLIT_CONFIGS:
            leaderboard = self._select_leaderboard(payload, str(config["leaderboard_name"]))
            rows = leaderboard.get("results") or leaderboard.get("rows") or leaderboard.get("entries") or []
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
                        benchmark_id=str(config["benchmark_id"]),
                        raw_model_name=model_name,
                        raw_value=str(raw_score),
                        source_url=str(config["page_url"]),
                        collected_at=fetched_at,
                        raw_model_key=model_name,
                        payload=row,
                        metadata={
                            "leaderboard_name": str(config["display_name"]),
                            "source_leaderboard_name": str(config["leaderboard_name"]),
                            "leaderboard_date": row.get("date"),
                            "submission_name": row.get("name"),
                            "submission_organization": organization,
                            "system_attempts": system_attempts,
                            "os_model": bool(row.get("os_model")),
                            "os_system": bool(row.get("os_system")),
                            "verified": True,
                            "single_model_submission": True,
                            "benchmark_id": str(config["benchmark_id"]),
                            "tags": tags,
                        },
                    )
                )

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        best_by_model_and_benchmark: dict[tuple[str, str], RawSourceRecord] = {}

        for record in raw_records:
            model_key = record.raw_model_key or record.raw_model_name
            current_value = _resolved_percentage_points(record.raw_value)
            if current_value is None:
                continue

            candidate_key = (model_key, record.benchmark_id)
            best = best_by_model_and_benchmark.get(candidate_key)
            best_value = _resolved_percentage_points(best.raw_value) if best else None
            if best is None or best_value is None or current_value > best_value:
                best_by_model_and_benchmark[candidate_key] = record

        candidates: list[ScoreCandidate] = []
        for (model_key, benchmark_id), record in sorted(
            best_by_model_and_benchmark.items(),
            key=lambda item: (item[0][0].lower(), item[0][1]),
        ):
            value = _resolved_percentage_points(record.raw_value)
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id=benchmark_id,
                    raw_model_name=record.raw_model_name,
                    raw_model_key=model_key,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="secondary",
                    verified=bool(record.metadata.get("verified", True)),
                    notes=(
                        "Best single-model submission from the official "
                        f'SWE-bench {record.metadata.get("leaderboard_name") or "unknown"} board: '
                        f'{record.metadata.get("submission_name") or "Unknown submission"} '
                        f'on {record.metadata.get("leaderboard_date") or "unknown date"}.'
                    ),
                    source_metadata=_comparison_source_metadata(record),
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _select_leaderboard(self, payload: dict[str, Any], name: str) -> dict[str, Any]:
        leaderboards = payload.get("leaderboards") or []
        for item in leaderboards:
            if str(item.get("name", "")).strip() == name:
                return item
        raise ValueError(f"Could not find {name} leaderboard in SWE-bench payload.")

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


def _resolved_percentage_points(value: Any) -> float | None:
    """Return an official SWE-bench resolved percentage without fraction rescaling."""
    score = safe_float(value)
    if score is None or not math.isfinite(score) or score < 0.0 or score > 100.0:
        return None
    return score


def _comparison_source_metadata(record: RawSourceRecord) -> dict[str, Any]:
    metadata = record.metadata
    payload = {
        "split": metadata.get("leaderboard_name"),
        "submission_name": metadata.get("submission_name"),
        "submission_organization": metadata.get("submission_organization"),
        "system_attempts": metadata.get("system_attempts"),
        "os_model": metadata.get("os_model"),
        "os_system": metadata.get("os_system"),
        "single_model_submission": metadata.get("single_model_submission"),
    }
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value != ""
    }
