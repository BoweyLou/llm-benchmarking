from __future__ import annotations

import re
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

        leaderboard = self._select_bash_only_leaderboard(payload)
        rows = leaderboard.get("results") or leaderboard.get("rows") or leaderboard.get("entries") or []
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in rows:
            version = str(row.get("mini-swe-agent_version") or row.get("mini_swe_agent_version") or "").strip()
            if not re.match(r"^2\.", version):
                continue

            model_name = self._extract_model_name(row)
            raw_score = row.get("resolved")
            if not model_name or raw_score is None:
                continue

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
                        "mini_swe_agent_version": version,
                        "verified": bool(row.get("verified", True)),
                        "tags": row.get("tags") or [],
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
                    source_type="primary",
                    verified=bool(record.metadata.get("verified", True)),
                    notes="Filtered from bash-only leaderboard with mini-SWE-agent v2 rows.",
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _select_bash_only_leaderboard(self, payload: dict[str, Any]) -> dict[str, Any]:
        leaderboards = payload.get("leaderboards") or []
        for item in leaderboards:
            if str(item.get("name", "")).strip() == "bash-only":
                return item
        raise ValueError("Could not find bash-only leaderboard in SWE-bench payload.")

    def _extract_model_name(self, row: dict[str, Any]) -> str:
        tags = row.get("tags") or []
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("Model: "):
                return tag.split("Model: ", 1)[1].strip()
        return str(row.get("name") or row.get("model") or row.get("model_name") or "").strip()
