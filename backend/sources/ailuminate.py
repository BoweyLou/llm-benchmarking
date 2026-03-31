from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..seed_data import AILUMINATE_GRADE_TO_SCORE

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, utc_now_iso


AILUMINATE_PAGES = (
    "https://ailuminate.mlcommons.org/benchmarks/general_purpose_ai_chat/1.0-en_us-official-ensemble",
    "https://ailuminate.mlcommons.org/benchmarks/general_purpose_ai_chat/1.0-fr_fr-official-ensemble",
)

GRADE_TO_SCORE = dict(AILUMINATE_GRADE_TO_SCORE)
GRADE_TO_SCORE.setdefault("Very Good", 75.0)
GRADE_TO_SCORE.setdefault("Good", 50.0)
GRADE_TO_SCORE.setdefault("Fair", 25.0)
GRADE_TO_SCORE.setdefault("Poor", 0.0)


@dataclass(slots=True)
class _RowCandidate:
    raw_record: RawSourceRecord
    score: float
    system_priority: int
    locale_priority: int


class AILuminateAdapter(BaseSourceAdapter):
    source_id = "ailuminate"
    benchmark_ids = ("ailuminate",)
    source_url = AILUMINATE_PAGES[0]

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        raw_records: list[RawSourceRecord] = []

        for page_url in AILUMINATE_PAGES:
            response = await client.get(page_url, timeout=30.0)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            locale = self._extract_locale(page_url)
            benchmark_version = self._extract_benchmark_version(page_url)
            fetched_at = utc_now_iso()

            for table in soup.find_all("table"):
                system_class = self._table_system_class(table)
                for row in table.select("tbody tr"):
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue

                    model_name = cells[0].get_text(" ", strip=True)
                    grade_cell = cells[1]
                    grade_div = grade_cell.find(attrs={"data-risk": True})
                    grade_label = first_non_empty(
                        grade_cell.get_text(" ", strip=True),
                        grade_div.get_text(" ", strip=True) if grade_div else "",
                    )
                    if not model_name or not grade_label:
                        continue

                    risk_value = None
                    if grade_div is not None:
                        raw_risk = grade_div.get("data-risk")
                        try:
                            risk_value = int(float(raw_risk)) if raw_risk is not None else None
                        except (TypeError, ValueError):
                            risk_value = None

                    detail_link = cells[2].find("a")
                    detail_url = urljoin(page_url, detail_link.get("href")) if detail_link and detail_link.get("href") else page_url

                    raw_records.append(
                        RawSourceRecord(
                            source_id=self.source_id,
                            benchmark_id="ailuminate",
                            raw_model_name=model_name,
                            raw_value=grade_label,
                            source_url=page_url,
                            collected_at=fetched_at,
                            raw_model_key=model_name,
                            payload={
                                "page_url": page_url,
                                "locale": locale,
                                "benchmark_version": benchmark_version,
                                "system_class": system_class,
                                "detail_url": detail_url,
                                "grade_label": grade_label,
                                "risk_ordinal": risk_value,
                            },
                            metadata={
                                "page_url": page_url,
                                "locale": locale,
                                "benchmark_version": benchmark_version,
                                "system_class": system_class,
                                "detail_url": detail_url,
                                "risk_ordinal": risk_value,
                            },
                        )
                    )

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        best_by_model: dict[str, _RowCandidate] = {}

        for record in raw_records:
            score = GRADE_TO_SCORE.get(record.raw_value)
            if score is None:
                continue

            model_key = record.raw_model_key or record.raw_model_name
            current = _RowCandidate(
                raw_record=record,
                score=score,
                system_priority=1 if record.metadata.get("system_class") == "AI Systems" else 0,
                locale_priority=1 if record.metadata.get("locale") == "en_us" else 0,
            )
            previous = best_by_model.get(model_key)
            if previous is None or self._candidate_sort_key(current) > self._candidate_sort_key(previous):
                best_by_model[model_key] = current

        candidates: list[ScoreCandidate] = []
        for model_key, entry in sorted(best_by_model.items(), key=lambda item: item[0].lower()):
            record = entry.raw_record
            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="ailuminate",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=model_key,
                    value=entry.score,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes="; ".join(
                        part
                        for part in (
                            f"Locale: {record.metadata.get('locale')}",
                            f"System class: {record.metadata.get('system_class')}",
                            f"Detail: {record.metadata.get('detail_url')}",
                        )
                        if part
                    ),
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _candidate_sort_key(self, candidate: _RowCandidate) -> tuple[float, int, int]:
        return (candidate.score, candidate.system_priority, candidate.locale_priority)

    def _extract_locale(self, page_url: str) -> str:
        if "fr_fr" in page_url:
            return "fr_fr"
        if "en_us" in page_url:
            return "en_us"
        return "unknown"

    def _extract_benchmark_version(self, page_url: str) -> str:
        match = re.search(r"/general_purpose_ai_chat/([^/]+)$", page_url)
        return match.group(1) if match else "unknown"

    def _table_system_class(self, table) -> str:
        heading = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        if heading_text:
            return heading_text
        return "Unknown"
