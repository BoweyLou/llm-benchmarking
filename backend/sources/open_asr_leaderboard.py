from __future__ import annotations

import csv
from collections import defaultdict
from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, compact_text, first_non_empty, safe_float, utc_now_iso


ENGLISH_SHORT_URL = (
    "https://huggingface.co/datasets/hf-audio/open-asr-leaderboard-results/resolve/main/english_short_latest.csv"
)
MULTILINGUAL_URL = "https://huggingface.co/datasets/Steveeeeeeen/multilingual_evals/resolve/main/multilingual_latest.csv"
LONGFORM_URL = "https://huggingface.co/datasets/Steveeeeeeen/leaderboard_longform/resolve/main/longform_latest.csv"

OPEN_ASR_FILES: tuple[dict[str, Any], ...] = (
    {
        "split": "english_short",
        "label": "English short-form",
        "benchmark_id": "asr_english_short_wer",
        "url": ENGLISH_SHORT_URL,
        "model_column": "model",
        "aggregate_columns": (),
        "metric_suffix": " WER",
    },
    {
        "split": "multilingual",
        "label": "Multilingual",
        "benchmark_id": "asr_multilingual_wer",
        "url": MULTILINGUAL_URL,
        "model_column": "model",
        "aggregate_columns": ("Avg",),
        "metric_suffix": "",
    },
    {
        "split": "longform",
        "label": "Long-form",
        "benchmark_id": "asr_longform_wer",
        "url": LONGFORM_URL,
        "model_column": "model_id",
        "aggregate_columns": ("Average",),
        "metric_suffix": "",
    },
)


class OpenAsrLeaderboardAdapter(BaseSourceAdapter):
    source_id = "open_asr_leaderboard"
    benchmark_ids = ("asr_english_short_wer", "asr_multilingual_wer", "asr_longform_wer", "asr_realtime_factor")
    source_url = "https://huggingface.co/spaces/hf-audio/open_asr_leaderboard"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []
        for source_file in OPEN_ASR_FILES:
            response = await client.get(source_file["url"], timeout=60.0)
            response.raise_for_status()
            raw_records.extend(_records_from_csv(response.text, source_file, fetched_at=fetched_at))

        if not raw_records:
            raise ValueError("Could not parse any Open ASR leaderboard rows.")
        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []
        records_by_model: dict[str, list[RawSourceRecord]] = defaultdict(list)

        for record in raw_records:
            model_key = record.raw_model_key or record.raw_model_name
            records_by_model[model_key].append(record)
            value = safe_float(record.raw_value)
            if value is None:
                continue
            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id=record.benchmark_id,
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key,
                    value=round(value, 6),
                    raw_value=_format_number(value),
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes=f"Open ASR Leaderboard {record.metadata.get('asr_split_label')} average WER. Lower is better.",
                    metadata=dict(record.metadata),
                )
            )

        for model_key, records in records_by_model.items():
            rtfx_records = [
                (safe_float(record.payload.get("RTFx")), record)
                for record in records
                if isinstance(record.payload, dict)
            ]
            rtfx_records = [(value, record) for value, record in rtfx_records if value is not None]
            if not rtfx_records:
                continue
            value, record = max(rtfx_records, key=lambda item: float(item[0] or 0.0))
            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="asr_realtime_factor",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=model_key,
                    value=round(float(value), 6),
                    raw_value=_format_number(value),
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes="Best reported Open ASR Leaderboard RTFx across imported splits. Higher is faster.",
                    metadata={**record.metadata, "score_policy": "best_reported_rtfx_across_open_asr_splits"},
                )
            )

        return candidates


def _records_from_csv(text: str, source_file: dict[str, Any], *, fetched_at: str) -> list[RawSourceRecord]:
    reader = csv.DictReader(text.splitlines())
    records: list[RawSourceRecord] = []
    for row in reader:
        record = _record_from_row(row, source_file, fetched_at=fetched_at)
        if record is not None:
            records.append(record)
    return records


def _record_from_row(row: dict[str, Any], source_file: dict[str, Any], *, fetched_at: str) -> RawSourceRecord | None:
    model_name = compact_text(row.get(source_file["model_column"]))
    if not model_name:
        return None
    value = _aggregate_wer_value(row, source_file)
    if value is None:
        return None
    provider = _provider_from_model_name(model_name)
    metadata = {
        "model_provider": provider,
        "raw_model_name": model_name,
        "model_roles": ["speech_to_text"],
        "capabilities": ["automatic-speech-recognition", "speech-to-text"],
        "asr_split": source_file["split"],
        "asr_split_label": source_file["label"],
        "source_policy": "open_asr_leaderboard_average_wer",
        "rtfx": safe_float(row.get("RTFx")),
        "license_name": compact_text(row.get("License")),
        "parameter_count_b": safe_float(row.get("Size (B)")),
        "language_count": safe_float(row.get("# Languages")),
    }
    return RawSourceRecord(
        source_id="open_asr_leaderboard",
        benchmark_id=source_file["benchmark_id"],
        raw_model_name=model_name,
        raw_model_key=model_name,
        raw_value=_format_number(value),
        source_url=source_file["url"],
        collected_at=fetched_at,
        payload=dict(row),
        metadata=metadata,
    )


def _aggregate_wer_value(row: dict[str, Any], source_file: dict[str, Any]) -> float | None:
    for column in source_file.get("aggregate_columns") or ():
        value = safe_float(row.get(column))
        if value is not None:
            return value

    values: list[float] = []
    metric_suffix = compact_text(source_file.get("metric_suffix"))
    ignored_columns = {
        compact_text(source_file.get("model_column")),
        "RTFx",
        "License",
        "Size (B)",
        "# Languages",
        "Encoder",
        "Decoder",
        "Avg",
        "Average",
        "Avg (without CORAAL)",
    }
    for column, raw_value in row.items():
        if column in ignored_columns:
            continue
        if metric_suffix and not str(column or "").endswith(metric_suffix):
            continue
        value = safe_float(raw_value)
        if value is not None:
            values.append(value)
    if not values:
        return None
    return sum(values) / len(values)


def _provider_from_model_name(model_name: str) -> str:
    owner = model_name.split("/", 1)[0].strip()
    provider_map = {
        "abr-ai": "Applied Brain Research",
        "assemblyai": "AssemblyAI",
        "AutoArk-AI": "AutoArk AI",
        "bosonai": "Boson AI",
        "CohereLabs": "Cohere",
        "facebook": "Meta",
        "google": "Google",
        "microsoft": "Microsoft",
        "mistralai": "Mistral AI",
        "nvidia": "NVIDIA",
        "openai": "OpenAI",
        "Qwen": "Alibaba",
    }
    return first_non_empty(provider_map.get(owner), owner, "Unknown")


def _format_number(value: Any) -> str:
    number = safe_float(value)
    if number is None:
        return compact_text(value)
    return f"{number:.6f}".rstrip("0").rstrip(".")
