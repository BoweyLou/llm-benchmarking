from __future__ import annotations

import re
from typing import Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, safe_float, utc_now_iso


class VectaraHallucinationAdapter(BaseSourceAdapter):
    source_id = "vectara_hallucination"
    benchmark_ids = ("rag_groundedness",)
    source_url = "https://raw.githubusercontent.com/vectara/hallucination-leaderboard/main/README.md"
    leaderboard_url = "https://github.com/vectara/hallucination-leaderboard"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0)
        response.raise_for_status()

        last_updated = self._extract_last_updated(response.text)
        rows = self._extract_table_rows(response.text)
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in rows:
            model_name = first_non_empty(row.get("Model"), row.get("model"))
            factual_consistency = self._parse_percentage(row.get("Factual Consistency Rate"))
            hallucination_rate = self._parse_percentage(row.get("Hallucination Rate"))
            answer_rate = self._parse_percentage(row.get("Answer Rate"))
            summary_length = safe_float(row.get("Average Summary Length (Words)"))

            if not model_name or factual_consistency is None:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="rag_groundedness",
                    raw_model_name=model_name,
                    raw_value=self._format_percent(factual_consistency),
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=model_name,
                    payload=dict(row),
                    metadata={
                        "leaderboard": "Vectara Hallucination Leaderboard",
                        "leaderboard_url": self.leaderboard_url,
                        "leaderboard_last_updated": last_updated,
                        "hallucination_rate": hallucination_rate,
                        "factual_consistency_rate": factual_consistency,
                        "answer_rate": answer_rate,
                        "average_summary_length_words": summary_length,
                    },
                )
            )

        if not raw_records:
            raise ValueError("Could not parse any Vectara hallucination leaderboard rows.")

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            value = self._parse_percentage(record.raw_value)
            if value is None:
                continue

            notes = "Vectara factual consistency rate; RAG-adjacent faithfulness to supplied source text."
            leaderboard_last_updated = record.metadata.get("leaderboard_last_updated")
            if leaderboard_last_updated:
                notes = f"{notes} Last updated {leaderboard_last_updated}."

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
                    notes=notes,
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _extract_table_rows(self, text: str) -> list[dict[str, str]]:
        lines = [line.rstrip() for line in text.splitlines()]
        header_index = -1
        for index, line in enumerate(lines):
            if (
                line.startswith("|")
                and "Model" in line
                and "Hallucination Rate" in line
                and "Factual Consistency Rate" in line
            ):
                header_index = index
                break

        if header_index == -1 or header_index + 1 >= len(lines):
            return []

        headers = self._split_markdown_row(lines[header_index])
        if not headers:
            return []

        rows: list[dict[str, str]] = []
        for line in lines[header_index + 2 :]:
            if not line.startswith("|"):
                if rows:
                    break
                continue

            cells = self._split_markdown_row(line)
            if len(cells) < len(headers):
                continue

            row = {headers[i]: cells[i] for i in range(len(headers))}
            model = first_non_empty(row.get("Model"))
            factual = self._parse_percentage(row.get("Factual Consistency Rate"))
            if not model or factual is None:
                continue
            rows.append(row)

        return rows

    def _extract_last_updated(self, text: str) -> str | None:
        match = re.search(r"Last updated on ([^\n]+)", text, re.I)
        return match.group(1).strip() if match else None

    def _split_markdown_row(self, line: str) -> list[str]:
        stripped = line.strip().strip("|")
        return [cell.strip() for cell in stripped.split("|")]

    def _parse_percentage(self, value) -> float | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("%", "").strip()
        return safe_float(text)

    def _format_percent(self, value: float) -> str:
        return f"{value:.1f}"
