from __future__ import annotations

import re
from typing import Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, safe_float, utc_now_iso


FAITHJUDGE_README_URL = "https://raw.githubusercontent.com/vectara/FaithJudge/main/README.md"
FAITHJUDGE_PAGE_URL = "https://github.com/vectara/FaithJudge#leaderboard"
MODEL_LINK_RE = re.compile(r"\[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\)")


class FaithJudgeAdapter(BaseSourceAdapter):
    source_id = "faithjudge"
    benchmark_ids = ("rag_task_faithfulness",)
    source_url = FAITHJUDGE_PAGE_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(FAITHJUDGE_README_URL, timeout=30.0)
        response.raise_for_status()

        rows = self._extract_table_rows(response.text)
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in rows:
            model_name = row["model_name"]
            overall_rate = safe_float(row["overall_hallucination_rate"].replace("%", ""))
            if not model_name or overall_rate is None:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="rag_task_faithfulness",
                    raw_model_name=model_name,
                    raw_value=f"{overall_rate:.2f}",
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=model_name,
                    payload={"table_row": row["table_row"]},
                    metadata={
                        "rank": row["rank"],
                        "organization": row["organization"],
                        "parameters": row["parameters"],
                        "model_url": row["model_url"],
                        "overall_hallucination_rate": overall_rate,
                        "faithbench_summarization": row["faithbench_summarization"],
                        "ragtruth_summarization": row["ragtruth_summarization"],
                        "ragtruth_question_answering": row["ragtruth_question_answering"],
                        "ragtruth_data_to_text": row["ragtruth_data_to_text"],
                    },
                )
            )

        if not raw_records:
            raise ValueError("Could not parse any FaithJudge leaderboard rows.")

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in sorted(raw_records, key=lambda item: self._rank_value(item.metadata.get("rank"))):
            value = safe_float(record.raw_value)
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="rag_task_faithfulness",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key or record.raw_model_name,
                    value=value,
                    raw_value=f"{value:.2f}",
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes="FaithJudge overall hallucination rate across FaithBench and RagTruth RAG tasks. Lower is better.",
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _extract_table_rows(self, text: str) -> list[dict[str, str]]:
        lines = [line.strip() for line in text.splitlines()]
        rows: list[dict[str, str]] = []

        for line in lines:
            if not line.startswith("|"):
                continue
            if "Overall Hallucination Rate" in line or line.startswith("|---"):
                continue

            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 9:
                continue

            rank = cells[0]
            if safe_float(rank) is None:
                continue

            model_match = MODEL_LINK_RE.search(cells[1])
            model_name = model_match.group("name").strip() if model_match else cells[1]
            model_url = model_match.group("url").strip() if model_match else self.source_url
            if not model_name:
                continue

            rows.append(
                {
                    "table_row": line,
                    "rank": rank,
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
            )

        return rows

    def _rank_value(self, value: object) -> int:
        rank = safe_float(value)
        return int(rank) if rank is not None else 10**9
