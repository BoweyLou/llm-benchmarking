from __future__ import annotations

import re
from typing import Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, safe_float, utc_now_iso


FAITHJUDGE_README_URL = "https://raw.githubusercontent.com/vectara/FaithJudge/main/README.md"
FAITHJUDGE_PAGE_URL = "https://github.com/vectara/FaithJudge#leaderboard"
TABLE_START_MARKER = "<!-- TABLE START -->"
TABLE_END_MARKER = "<!-- TABLE END -->"
MODEL_LINK_RE = re.compile(r"\[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\)")


class FaithJudgeAdapter(BaseSourceAdapter):
    source_id = "faithjudge"
    benchmark_ids = ("rag_groundedness",)
    source_url = FAITHJUDGE_PAGE_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(FAITHJUDGE_README_URL, timeout=30.0)
        response.raise_for_status()

        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []
        for line in self._extract_table_lines(response.text):
            parsed = self._parse_table_row(line)
            if parsed is None:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="rag_groundedness",
                    raw_model_name=parsed["model_name"],
                    raw_value=parsed["overall_hallucination_rate"],
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=parsed["model_name"],
                    payload={"table_row": line},
                    metadata={
                        "rank": parsed["rank"],
                        "organization": parsed["organization"],
                        "parameters": parsed["parameters"],
                        "model_url": parsed["model_url"],
                        "faithbench_summarization": parsed["faithbench_summarization"],
                        "ragtruth_summarization": parsed["ragtruth_summarization"],
                        "ragtruth_question_answering": parsed["ragtruth_question_answering"],
                        "ragtruth_data_to_text": parsed["ragtruth_data_to_text"],
                    },
                )
            )

        if not raw_records:
            raise ValueError("Could not parse any FaithJudge leaderboard rows.")

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in sorted(raw_records, key=lambda item: self._rank_value(item.metadata.get("rank"))):
            value = safe_float(str(record.raw_value).replace("%", ""))
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="rag_groundedness",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key or record.raw_model_name,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes="FaithJudge overall hallucination rate across FaithBench and RagTruth RAG tasks. Lower is better.",
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _extract_table_lines(self, text: str) -> list[str]:
        lines = text.splitlines()
        collecting = False
        table_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped == TABLE_START_MARKER:
                collecting = True
                continue
            if stripped == TABLE_END_MARKER:
                break
            if collecting:
                table_lines.append(stripped)

        return [
            line
            for line in table_lines
            if line.startswith("|")
            and "Overall Hallucination Rate" not in line
            and not line.startswith("|-------")
        ]

    def _parse_table_row(self, line: str) -> dict[str, str] | None:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            return None

        model_match = MODEL_LINK_RE.search(cells[1])
        model_name = model_match.group("name").strip() if model_match else cells[1]
        model_url = model_match.group("url").strip() if model_match else self.source_url
        if not model_name:
            return None

        return {
            "rank": cells[0],
            "model_name": model_name,
            "model_url": model_url,
            "organization": cells[2],
            "parameters": cells[3],
            "overall_hallucination_rate": cells[4],
            "faithbench_summarization": cells[5],
            "ragtruth_summarization": cells[6],
            "ragtruth_question_answering": cells[7],
            "ragtruth_data_to_text": cells[8],
        }

    def _rank_value(self, value: object) -> int:
        rank = safe_float(value)
        return int(rank) if rank is not None else 10**9


# Compatibility alias while the source file name still reflects the older implementation.
VectaraHallucinationAdapter = FaithJudgeAdapter
