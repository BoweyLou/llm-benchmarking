from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

import httpx


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compact_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = compact_text(value)
        if text:
            return text
    return ""


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", "")
            if not value:
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def percent_score(value: Any) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    return number * 100.0 if abs(number) <= 1.5 else number


@dataclass(slots=True)
class RawSourceRecord:
    source_id: str
    benchmark_id: str
    raw_model_name: str
    raw_value: str
    source_url: str
    collected_at: str
    raw_model_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    configuration_key: str | None = None
    configuration_value: str | None = None


@dataclass(slots=True)
class ScoreCandidate:
    source_id: str
    benchmark_id: str
    raw_model_name: str
    value: float
    raw_value: str
    source_url: str
    collected_at: str
    raw_model_key: str | None = None
    source_type: str = "primary"
    verified: bool = True
    notes: str | None = None
    confidence_lower: float | None = None
    confidence_upper: float | None = None
    variance: float | None = None
    vote_count: int | None = None
    observation_count: int | None = None
    session_count: int | None = None
    rank: int | None = None
    category: str | None = None
    publication_date: str | None = None
    methodology: str | None = None
    source_listing_status: str | None = None
    style_control: bool | None = None
    preliminary: bool | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    configuration_key: str | None = None
    configuration_value: str | None = None


@dataclass(slots=True)
class SourceFetchResult:
    source_id: str
    source_url: str
    fetched_at: str
    raw_records: list[RawSourceRecord]
    candidates: list[ScoreCandidate]
    listing_benchmark_ids: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


class BaseSourceAdapter(ABC):
    source_id: str
    benchmark_ids: tuple[str, ...]
    source_url: str

    @abstractmethod
    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        raise NotImplementedError

    def _set_fetch_details(self, details: dict[str, Any] | None) -> None:
        """Store JSON-shaped details for the current fetch without sharing caller state."""
        self._latest_fetch_details = deepcopy(details) if isinstance(details, dict) else {}

    def _fetch_details_snapshot(self) -> dict[str, Any]:
        details = getattr(self, "_latest_fetch_details", None)
        return deepcopy(details) if isinstance(details, dict) else {}

    async def collect(self, client: httpx.AsyncClient) -> SourceFetchResult:
        self._set_fetch_details({})
        fetched_at = utc_now_iso()
        raw_records = await self.fetch_raw(client)
        candidates = self.normalize(raw_records)
        return SourceFetchResult(
            source_id=self.source_id,
            source_url=self.source_url,
            fetched_at=fetched_at,
            raw_records=raw_records,
            candidates=candidates,
            listing_benchmark_ids=self.benchmark_ids,
            details=self._fetch_details_snapshot(),
        )
