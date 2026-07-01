from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable, Mapping, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, safe_float, utc_now_iso


LIVECODEBENCH_PAGE_URL = "https://livecodebench.github.io/leaderboard.html"
LIVECODEBENCH_DATA_URL = "https://livecodebench.github.io/performances_generation.json"
LIVECODEBENCH_BENCHMARK_ID = "livecodebench_codegen"


class LiveCodeBenchAdapter(BaseSourceAdapter):
    source_id = "livecodebench"
    benchmark_ids = (LIVECODEBENCH_BENCHMARK_ID,)
    source_url = LIVECODEBENCH_PAGE_URL
    data_url = LIVECODEBENCH_DATA_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.data_url, timeout=30.0)
        response.raise_for_status()
        content = response.content
        payload = response.json()
        metadata = {
            "artifact_url": self.data_url,
            "artifact_sha256": sha256(content).hexdigest(),
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
        }
        return self._records_from_payload(payload, fetched_at=utc_now_iso(), artifact_metadata=metadata)

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in sorted(raw_records, key=lambda item: item.raw_model_name.lower()):
            value = safe_float(record.raw_value)
            if value is None:
                continue

            contaminated = bool(record.metadata.get("contaminated_by_window"))
            notes = (
                "LiveCodeBench code-generation pass@1 from the official default date window; "
                f"{record.metadata.get('problem_count', 0)} problems from "
                f"{record.metadata.get('window_start_date')} through {record.metadata.get('window_end_date')}."
            )
            if contaminated:
                notes += " The site marks this model as potentially contaminated for the selected window."

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id=LIVECODEBENCH_BENCHMARK_ID,
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

    def _records_from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        fetched_at: str,
        artifact_metadata: Mapping[str, Any] | None = None,
    ) -> list[RawSourceRecord]:
        date_marks = _sorted_date_marks(payload.get("date_marks"))
        if not date_marks:
            raise ValueError("LiveCodeBench payload is missing date_marks.")

        performances = payload.get("performances")
        if not isinstance(performances, list):
            raise ValueError("LiveCodeBench payload is missing performances.")

        models = _model_rows(payload.get("models"))
        if not models:
            raise ValueError("LiveCodeBench payload is missing models.")

        start_index = 15 if len(date_marks) > 12 else min(4, len(date_marks) - 1)
        window_start = date_marks[start_index]
        window_end = date_marks[-1]
        performances_by_model = _group_performances_by_model(performances, window_start=window_start, window_end=window_end)

        raw_records: list[RawSourceRecord] = []
        for model in models:
            release_date = _int_value(model.get("release_date"))
            if release_date is None:
                continue

            model_repr = first_non_empty(model.get("model_repr"), model.get("model_name"))
            if not model_repr:
                continue

            rows = performances_by_model.get(model_repr, [])
            if not rows:
                continue

            aggregate = _aggregate_rows(rows)
            if aggregate["average_pass"] is None:
                continue

            metadata = {
                "model_name": first_non_empty(model.get("model_name"), model_repr),
                "model_repr": model_repr,
                "model_style": model.get("model_style"),
                "model_link": model.get("link"),
                "release_date_ms": release_date,
                "release_date": _date_from_ms(release_date),
                "window_start_ms": window_start,
                "window_end_ms": window_end,
                "window_start_date": _date_from_ms(window_start),
                "window_end_date": _date_from_ms(window_end),
                "date_mark_count": len(date_marks),
                "default_start_index": start_index,
                "contaminated_by_window": release_date >= window_start,
                "problem_count": aggregate["problem_count"],
                "difficulty_counts": aggregate["difficulty_counts"],
                "difficulty_scores": aggregate["difficulty_scores"],
                "platform_counts": aggregate["platform_counts"],
                "source_page_url": self.source_url,
                "source_data_url": self.data_url,
            }
            metadata.update({key: value for key, value in (artifact_metadata or {}).items() if value is not None})

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id=LIVECODEBENCH_BENCHMARK_ID,
                    raw_model_name=model_repr,
                    raw_value=_format_score(float(aggregate["average_pass"])),
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=first_non_empty(model.get("model_name"), model_repr),
                    payload={
                        "model": dict(model),
                        "aggregate": aggregate,
                    },
                    metadata=metadata,
                )
            )

        if not raw_records:
            raise ValueError("Could not derive any LiveCodeBench model scores.")

        return raw_records


def _sorted_date_marks(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    marks = [_int_value(item) for item in value]
    return sorted(item for item in marks if item is not None)


def _model_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [item for item in value.values() if isinstance(item, Mapping)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _group_performances_by_model(
    rows: Iterable[Any],
    *,
    window_start: int,
    window_end: int,
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        model = first_non_empty(row.get("model"))
        row_date = _int_value(row.get("date"))
        pass_at_1 = safe_float(row.get("pass@1"))
        if not model or row_date is None or pass_at_1 is None:
            continue
        if row_date < window_start or row_date > window_end:
            continue
        grouped.setdefault(model, []).append(row)
    return grouped


def _aggregate_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pass_values = [_pass_at_1(row) for row in rows]
    pass_values = [value for value in pass_values if value is not None]
    difficulty_scores: dict[str, float] = {}
    difficulty_counts: Counter[str] = Counter()
    platform_counts: Counter[str] = Counter()

    for row in rows:
        difficulty = first_non_empty(row.get("difficulty"), "unknown").lower()
        platform = first_non_empty(row.get("platform"), "unknown").lower()
        if _pass_at_1(row) is not None:
            difficulty_counts[difficulty] += 1
            platform_counts[platform] += 1

    for difficulty in sorted(difficulty_counts):
        values = [
            value
            for row in rows
            if first_non_empty(row.get("difficulty"), "unknown").lower() == difficulty
            for value in [_pass_at_1(row)]
            if value is not None
        ]
        if values:
            difficulty_scores[difficulty] = _round_one_decimal(sum(values) / len(values))

    return {
        "average_pass": _round_one_decimal(sum(pass_values) / len(pass_values)) if pass_values else None,
        "problem_count": len(pass_values),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "difficulty_scores": difficulty_scores,
        "platform_counts": dict(sorted(platform_counts.items())),
    }


def _pass_at_1(row: Mapping[str, Any]) -> float | None:
    return safe_float(row.get("pass@1"))


def _round_one_decimal(value: float) -> float:
    return round(float(value), 1)


def _format_score(value: float) -> str:
    return f"{_round_one_decimal(value):.1f}"


def _int_value(value: Any) -> int | None:
    number = safe_float(value)
    if number is None:
        return None
    return int(number)


def _date_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
