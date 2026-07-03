from __future__ import annotations

import ast
import json
import re
from typing import Any, Sequence
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, safe_float, utc_now_iso


TTS_MODELS_URL = "https://artificialanalysis.ai/text-to-speech/models"
TTS_LEADERBOARD_URL = "https://artificialanalysis.ai/text-to-speech/leaderboard/selected-voice"
TTS_METHODOLOGY_URL = "https://artificialanalysis.ai/text-to-speech/methodology"
TTS_GENERATION_PROMPT_CHARS = 500.0


class ArtificialAnalysisTtsAdapter(BaseSourceAdapter):
    source_id = "artificial_analysis_tts"
    benchmark_ids = ("aa_tts_quality_elo", "aa_tts_generation_time", "aa_tts_price_per_1m_chars")
    source_url = TTS_MODELS_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(TTS_MODELS_URL, timeout=30.0, follow_redirects=True)
        response.raise_for_status()

        entries = self._entries_from_datasets(self._extract_datasets(response.text))

        try:
            leaderboard_response = await client.get(TTS_LEADERBOARD_URL, timeout=30.0, follow_redirects=True)
            leaderboard_response.raise_for_status()
            self._merge_leaderboard_rows(entries, self._extract_leaderboard_rows(leaderboard_response.text))
        except Exception:
            # The /models JSON-LD datasets carry the score data; the leaderboard adds richer metadata.
            pass

        raw_records = self._build_raw_records(entries, fetched_at=utc_now_iso())
        if not raw_records:
            raise ValueError("Could not parse any Artificial Analysis Text to Speech rows.")
        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []
        metric_specs = (
            ("aa_tts_quality_elo", "quality_elo", "Speech Arena Quality Elo"),
            ("aa_tts_generation_time", "generation_time_seconds", "500-character generation time seconds"),
            ("aa_tts_price_per_1m_chars", "price_per_1m_chars", "price per 1M characters"),
        )

        for record in raw_records:
            metrics = record.metadata.get("metrics") or {}
            if not isinstance(metrics, dict):
                continue

            for benchmark_id, metric_key, source_label in metric_specs:
                value = safe_float(metrics.get(metric_key))
                if value is None:
                    continue
                candidates.append(
                    ScoreCandidate(
                        source_id=self.source_id,
                        benchmark_id=benchmark_id,
                        raw_model_name=record.raw_model_name,
                        raw_model_key=record.raw_model_key or record.raw_model_name,
                        value=round(value, 6),
                        raw_value=_format_number(value),
                        source_url=_metric_source_url(record.metadata, metric_key) or record.source_url,
                        collected_at=record.collected_at,
                        source_type="primary",
                        verified=True,
                        notes=f"Artificial Analysis TTS field: {source_label}",
                        metadata={
                            **record.metadata,
                            "metric": metric_key,
                            "source_field": source_label,
                        },
                    )
                )

        return candidates

    def _extract_datasets(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        datasets: list[dict[str, Any]] = []
        for script in soup.find_all("script", type="application/ld+json"):
            text = script.string or script.get_text()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("@type") != "Dataset":
                continue
            name = str(payload.get("name") or "")
            rows = payload.get("data")
            if name not in {"Text to Speech Arena Quality Elo", "Price", "Characters Per Second"}:
                continue
            if isinstance(rows, list):
                datasets.append({"name": name, "data": rows, "description": payload.get("description")})

        if not datasets:
            raise ValueError("Could not locate Artificial Analysis Text to Speech JSON-LD datasets.")
        return datasets

    def _entries_from_datasets(self, datasets: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        for dataset in datasets:
            dataset_name = str(dataset.get("name") or "")
            rows = dataset.get("data")
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                model_name, representative_provider = _split_model_label(row.get("label"))
                if not model_name:
                    continue
                entry = entries.setdefault(
                    _identity_key(model_name),
                    {
                        "model_name": model_name,
                        "representative_provider": representative_provider,
                        "metrics": {},
                        "details_urls": {},
                        "datasets": [],
                    },
                )
                if representative_provider and not entry.get("representative_provider"):
                    entry["representative_provider"] = representative_provider
                entry.setdefault("datasets", []).append(dataset_name)
                details_url = _absolute_url(row.get("detailsUrl"))

                if dataset_name == "Text to Speech Arena Quality Elo":
                    value = safe_float(row.get("qualityElo"))
                    if value is not None:
                        entry["metrics"]["quality_elo"] = value
                        entry["details_urls"]["quality_elo"] = details_url
                elif dataset_name == "Price":
                    value = safe_float(row.get("pricePer1mCharacters"))
                    if value is not None:
                        entry["metrics"]["price_per_1m_chars"] = value
                        entry["details_urls"]["price_per_1m_chars"] = details_url
                elif dataset_name == "Characters Per Second":
                    value = safe_float(row.get("charactersPerSecond"))
                    if value is not None and value > 0:
                        entry["metrics"]["characters_per_second"] = value
                        entry["metrics"]["generation_time_seconds"] = TTS_GENERATION_PROMPT_CHARS / value
                        entry["details_urls"]["generation_time_seconds"] = details_url
        return entries

    def _extract_leaderboard_rows(self, html: str) -> list[dict[str, Any]]:
        rows_by_name: dict[str, dict[str, Any]] = {}
        needle = "self.__next_f.push([1,"
        start = 0

        while True:
            chunk_start = html.find(needle, start)
            if chunk_start == -1:
                break
            chunk_end = html.find("])</script>", chunk_start)
            if chunk_end == -1:
                break
            fragment = html[chunk_start:chunk_end]
            encoded = fragment.split(needle, 1)[1]
            start = chunk_start + 1

            try:
                decoded = ast.literal_eval(encoded)
            except Exception:
                continue
            if "pricePer1mCharacters" not in decoded or '"values"' not in decoded:
                continue

            try:
                payload = json.loads(decoded.split(":", 1)[1])
            except Exception:
                continue

            for row in _iter_leaderboard_value_rows(payload):
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                key = _identity_key(name)
                existing = rows_by_name.get(key)
                if existing is None or _leaderboard_rank(row) < _leaderboard_rank(existing):
                    rows_by_name[key] = row

        return list(rows_by_name.values())

    def _merge_leaderboard_rows(self, entries: dict[str, dict[str, Any]], rows: Sequence[dict[str, Any]]) -> None:
        for row in rows:
            model_name = str(row.get("name") or "").strip()
            if not model_name:
                continue
            entry = entries.setdefault(
                _identity_key(model_name),
                {
                    "model_name": model_name,
                    "metrics": {},
                    "details_urls": {},
                    "datasets": [],
                },
            )
            metrics = entry.setdefault("metrics", {})
            details_urls = entry.setdefault("details_urls", {})
            quality = safe_float(row.get("elo"))
            if quality is not None and "quality_elo" not in metrics:
                metrics["quality_elo"] = quality
                details_urls.setdefault("quality_elo", _absolute_url(row.get("url")))
            price = safe_float(row.get("pricePer1mCharacters"))
            if price is not None and "price_per_1m_chars" not in metrics:
                metrics["price_per_1m_chars"] = price
                details_urls.setdefault("price_per_1m_chars", _absolute_url(row.get("url")))

            creator = row.get("creator") if isinstance(row.get("creator"), dict) else {}
            entry["model_creator"] = first_non_empty(creator.get("name"), entry.get("model_creator"))
            entry["release_date"] = first_non_empty(row.get("released"), entry.get("release_date")) or None
            entry["details_url"] = _absolute_url(row.get("url")) or entry.get("details_url")
            entry["open_weights_url"] = _absolute_url(row.get("openWeightsUrl")) or entry.get("open_weights_url")
            entry["open_weights"] = bool(entry.get("open_weights_url"))
            entry["voice_count"] = safe_float(row.get("voiceCount"))
            entry["speech_arena_rank"] = _leaderboard_rank(row) + 1 if row.get("rank") is not None else None
            entry["speech_arena_appearances"] = safe_float(row.get("appearances"))
            entry["speech_arena_win_rate"] = safe_float(row.get("winRate"))
            entry["speech_arena_ci_lower"] = safe_float(row.get("ciLower"))
            entry["speech_arena_ci_upper"] = safe_float(row.get("ciUpper"))

    def _build_raw_records(self, entries: dict[str, dict[str, Any]], *, fetched_at: str) -> list[RawSourceRecord]:
        records: list[RawSourceRecord] = []
        for key, entry in sorted(entries.items(), key=lambda item: str(item[1].get("model_name") or "").lower()):
            metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
            if not any(value is not None for value in metrics.values()):
                continue
            model_name = str(entry.get("model_name") or "").strip()
            if not model_name:
                continue
            metadata = {
                "model_roles": ["text_to_speech"],
                "capabilities": ["text-to-speech", "speech-synthesis", "speech-output"],
                "input_modalities": ["text"],
                "output_modalities": ["speech"],
                "model_creator": first_non_empty(entry.get("model_creator"), entry.get("representative_provider")),
                "representative_provider": entry.get("representative_provider"),
                "release_date": entry.get("release_date"),
                "details_url": entry.get("details_url"),
                "source_url": TTS_MODELS_URL,
                "leaderboard_url": TTS_LEADERBOARD_URL,
                "methodology_url": TTS_METHODOLOGY_URL,
                "metrics": metrics,
                "metric_source_urls": entry.get("details_urls") or {},
                "datasets": sorted(set(str(value) for value in entry.get("datasets") or [] if str(value).strip())),
                "open_weights": bool(entry.get("open_weights")),
                "open_weights_url": entry.get("open_weights_url"),
                "voice_count": entry.get("voice_count"),
                "speech_arena_rank": entry.get("speech_arena_rank"),
                "speech_arena_appearances": entry.get("speech_arena_appearances"),
                "speech_arena_win_rate": entry.get("speech_arena_win_rate"),
                "speech_arena_ci_lower": entry.get("speech_arena_ci_lower"),
                "speech_arena_ci_upper": entry.get("speech_arena_ci_upper"),
            }
            records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="aa_tts_quality_elo",
                    raw_model_name=model_name,
                    raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
                    source_url=TTS_MODELS_URL,
                    collected_at=fetched_at,
                    raw_model_key=key,
                    payload=dict(entry),
                    metadata=metadata,
                )
            )
        return records


def _split_model_label(value: Any) -> tuple[str, str | None]:
    text = str(value or "").strip()
    if not text:
        return "", None
    if "," not in text:
        return text, None
    model_name, provider = [part.strip() for part in text.rsplit(",", 1)]
    return model_name or text, provider or None


def _identity_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _absolute_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return urljoin("https://artificialanalysis.ai", text)


def _iter_leaderboard_value_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        row_values = value.get("values")
        if isinstance(row_values, dict) and row_values.get("name") and row_values.get("elo") is not None:
            rows.append(row_values)
        for nested in value.values():
            rows.extend(_iter_leaderboard_value_rows(nested))
    elif isinstance(value, list):
        for nested in value:
            rows.extend(_iter_leaderboard_value_rows(nested))
    return rows


def _leaderboard_rank(row: dict[str, Any]) -> int:
    rank = safe_float(row.get("rank"))
    return int(rank) if rank is not None else 999_999


def _metric_source_url(metadata: dict[str, Any], metric_key: str) -> str | None:
    urls = metadata.get("metric_source_urls")
    if not isinstance(urls, dict):
        return None
    return _absolute_url(urls.get(metric_key))


def _format_number(value: Any) -> str:
    number = safe_float(value)
    if number is None:
        return str(value or "").strip()
    return f"{number:.6f}".rstrip("0").rstrip(".")
