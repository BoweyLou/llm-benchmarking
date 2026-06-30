from __future__ import annotations

from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, percent_score, utc_now_iso


IFEVAL_PAGE_URL = "https://llm-stats.com/benchmarks/ifeval"
IFEVAL_DETAILS_URLS = (
    "https://api.llm-stats.com/leaderboard/benchmarks/ifeval/details",
    "https://api.zeroeval.com/leaderboard/benchmarks/ifeval/details",
)


class IfevalAdapter(BaseSourceAdapter):
    source_id = "ifeval"
    benchmark_ids = ("ifeval",)
    source_url = IFEVAL_PAGE_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        payload, details_url = await self._fetch_details_payload(client)
        models = payload.get("models") or []
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in models:
            if not isinstance(row, dict):
                continue

            model_name = first_non_empty(row.get("model_name"), row.get("model_id"))
            if not model_name:
                continue

            raw_score = row.get("score")
            if raw_score is None:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="ifeval",
                    raw_model_name=model_name,
                    raw_value=str(raw_score),
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=first_non_empty(row.get("model_id"), model_name),
                    payload=row,
                    metadata={
                        "details_url": details_url,
                        "rank": row.get("rank"),
                        "organization_name": row.get("organization_name"),
                        "organization_id": row.get("organization_id"),
                        "verified": bool(row.get("verified")),
                        "self_reported": bool(row.get("self_reported")),
                        "self_reported_source": row.get("self_reported_source"),
                        "analysis_method": row.get("analysis_method"),
                        "verification_date": row.get("verification_date"),
                        "provider_id": row.get("provider_id"),
                        "input_cost_per_million": row.get("input_cost_per_million"),
                        "output_cost_per_million": row.get("output_cost_per_million"),
                        "context_window": row.get("context_window"),
                        "announcement_date": row.get("announcement_date"),
                        "param_count": row.get("param_count"),
                        "is_open_source": row.get("is_open_source"),
                        "is_new": row.get("is_new"),
                        "best_latency": row.get("best_latency"),
                        "latency_provider": row.get("latency_provider"),
                        "best_throughput": row.get("best_throughput"),
                        "throughput_provider": row.get("throughput_provider"),
                        "context_provider": row.get("context_provider"),
                        "model_id": row.get("model_id"),
                    },
                )
            )

        return raw_records

    async def _fetch_details_payload(self, client: httpx.AsyncClient) -> tuple[dict[str, Any], str]:
        errors: list[str] = []

        for details_url in IFEVAL_DETAILS_URLS:
            try:
                response = await client.get(details_url, timeout=30.0)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                errors.append(f"{details_url}: {exc}")
                continue

            payload = response.json()
            models = payload.get("models") or []
            if isinstance(models, list) and models:
                return payload, details_url
            errors.append(f"{details_url}: returned 0 models")

        raise ValueError("; ".join(errors) if errors else "IFEval details endpoint returned no models.")

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in sorted(raw_records, key=lambda item: item.metadata.get("rank") or 10**9):
            value = percent_score(record.raw_value)
            if value is None:
                continue

            verified = bool(record.metadata.get("verified"))
            self_reported = bool(record.metadata.get("self_reported"))
            source_type = "primary" if verified and not self_reported else "secondary"
            source_bits = []
            if record.metadata.get("organization_name"):
                source_bits.append(str(record.metadata["organization_name"]))
            if self_reported:
                source_bits.append("self-reported")
            elif verified:
                source_bits.append("verified")
            else:
                source_bits.append("unverified")

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="ifeval",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key or record.raw_model_name,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type=source_type,
                    verified=verified,
                    notes="; ".join(source_bits)
                    if source_bits
                    else "IFEval benchmark score from the LLM Stats / ZeroEval details endpoint.",
                    metadata=dict(record.metadata),
                )
            )

        return candidates
