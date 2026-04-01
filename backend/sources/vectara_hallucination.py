from __future__ import annotations

from typing import Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, safe_float, utc_now_iso


VECTARA_README_URL = "https://raw.githubusercontent.com/vectara/hallucination-leaderboard/main/README.md"
VECTARA_PAGE_URL = "https://github.com/vectara/hallucination-leaderboard"
LEADERBOARD_MARKER = "<!-- LEADERBOARD_START -->"


class VectaraHallucinationAdapter(BaseSourceAdapter):
    source_id = "vectara_hallucination"
    benchmark_ids = ("rag_groundedness",)
    source_url = VECTARA_PAGE_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(VECTARA_README_URL, timeout=30.0)
        response.raise_for_status()

        rows = self._extract_table_rows(response.text)
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for rank, row in enumerate(rows, start=1):
            model_name = row["model_name"]
            factual_consistency = safe_float(row["factual_consistency_rate"].replace("%", ""))
            if not model_name or factual_consistency is None:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="rag_groundedness",
                    raw_model_name=model_name,
                    raw_value=f"{factual_consistency:.1f}",
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=model_name,
                    payload={"table_row": row["table_row"]},
                    metadata={
                        "rank": rank,
                        "hallucination_rate": safe_float(row["hallucination_rate"].replace("%", "")),
                        "factual_consistency_rate": factual_consistency,
                        "answer_rate": safe_float(row["answer_rate"].replace("%", "")),
                        "average_summary_length_words": safe_float(row["average_summary_length_words"]),
                    },
                )
            )

        if not raw_records:
            raise ValueError("Could not parse any Vectara leaderboard rows.")

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in sorted(raw_records, key=lambda item: int(item.metadata.get("rank", 10**9))):
            value = safe_float(record.raw_value)
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="rag_groundedness",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key or record.raw_model_name,
                    value=value,
                    raw_value=f"{value:.1f}",
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes="Vectara factual consistency to supplied source text. RAG-adjacent faithfulness signal, not retrieval relevance.",
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _extract_table_rows(self, text: str) -> list[dict[str, str]]:
        lines = [line.strip() for line in text.splitlines()]
        seen_marker = False
        rows: list[dict[str, str]] = []

        for line in lines:
            if line == LEADERBOARD_MARKER:
                seen_marker = True
                continue
            if not seen_marker or not line.startswith("|"):
                continue
            if "Factual Consistency Rate" in line or line.startswith("|----"):
                continue

            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 5:
                continue

            rows.append(
                {
                    "table_row": line,
                    "model_name": cells[0],
                    "hallucination_rate": cells[1],
                    "factual_consistency_rate": cells[2],
                    "answer_rate": cells[3],
                    "average_summary_length_words": cells[4],
                }
            )

        return rows
