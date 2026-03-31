from __future__ import annotations

import ast
import json
import re
from typing import Any, Sequence

import httpx
from bs4 import BeautifulSoup

from .base import (
    BaseSourceAdapter,
    RawSourceRecord,
    ScoreCandidate,
    first_non_empty,
    safe_float,
    utc_now_iso,
)


class ArtificialAnalysisAdapter(BaseSourceAdapter):
    source_id = "artificial_analysis"
    benchmark_ids = ("aa_intelligence", "aa_speed", "aa_cost")
    source_url = "https://artificialanalysis.ai/leaderboards/models"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0)
        response.raise_for_status()

        models = self._extract_models(response.text)
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in models:
            if row.get("deleted") or row.get("deprecated"):
                continue

            model_name = first_non_empty(
                row.get("shortName"),
                row.get("short_name"),
                row.get("name"),
                row.get("slug"),
            )
            if not model_name:
                continue

            metrics = self._extract_metrics(row)
            if not any(value is not None for value in metrics.values()):
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="aa_intelligence",
                    raw_model_name=model_name,
                    raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=first_non_empty(row.get("slug"), row.get("id"), model_name),
                    payload=row,
                    metadata={
                        "display_order": row.get("display_order"),
                        "deleted": bool(row.get("deleted")),
                        "deprecated": bool(row.get("deprecated")),
                        "model_family_slug": row.get("model_family_slug"),
                        "model_creator": first_non_empty(
                            (row.get("creator") or {}).get("name") if isinstance(row.get("creator"), dict) else None,
                            (row.get("model_creators") or {}).get("name")
                            if isinstance(row.get("model_creators"), dict)
                            else None,
                            row.get("modelCreatorName"),
                        ),
                        "metrics": metrics,
                    },
                )
            )

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            metrics = record.metadata.get("metrics") or {}
            if not isinstance(metrics, dict):
                continue

            for benchmark_id, metric_key, source_label in (
                ("aa_intelligence", "intelligence_index", "intelligence_index"),
                ("aa_speed", "median_output_speed", "timescaleData.median_output_speed"),
                ("aa_cost", "price_1m_blended_3_to_1", "price_1m_blended_3_to_1"),
            ):
                value = safe_float(metrics.get(metric_key))
                if value is None:
                    continue

                candidates.append(
                    ScoreCandidate(
                        source_id=self.source_id,
                        benchmark_id=benchmark_id,
                        raw_model_name=record.raw_model_name,
                        raw_model_key=record.raw_model_key or record.raw_model_name,
                        value=value,
                        raw_value=_format_value(value),
                        source_url=record.source_url,
                        collected_at=record.collected_at,
                        source_type="primary",
                        verified=True,
                        notes=f"Artificial Analysis field: {source_label}",
                        metadata={
                            **record.metadata,
                            "metric": metric_key,
                            "source_field": source_label,
                        },
                    )
                )

        return candidates

    def _extract_models(self, html: str) -> list[dict[str, Any]]:
        errors: list[str] = []

        for extractor in (self._extract_models_from_flight, self._extract_models_from_table):
            try:
                models = extractor(html)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if models:
                return models

        raise ValueError("; ".join(errors) or "Could not locate Artificial Analysis model payload.")

    def _extract_models_from_flight(self, html: str) -> list[dict[str, Any]]:
        needle = 'self.__next_f.push([1,'
        start = 0

        while True:
            chunk_start = html.find(needle, start)
            if chunk_start == -1:
                break

            chunk_end = html.find('])</script>', chunk_start)
            if chunk_end == -1:
                break

            fragment = html[chunk_start:chunk_end]
            encoded = fragment.split(needle, 1)[1]

            try:
                decoded = ast.literal_eval(encoded)
            except Exception:
                start = chunk_start + 1
                continue

            models_idx = decoded.find('"models":[')
            if models_idx == -1:
                start = chunk_start + 1
                continue

            if (
                "intelligenceIndex" not in decoded
                and "medianOutputTokensPerSecond" not in decoded
                and "price1m" not in decoded
            ):
                start = chunk_start + 1
                continue

            array_start = decoded.find("[", models_idx)
            models_json = _extract_balanced(decoded, array_start, "[", "]")
            payload = json.loads(models_json)
            if isinstance(payload, list):
                return [row for row in payload if isinstance(row, dict)]

            start = chunk_start + 1

        raise ValueError("Could not locate Artificial Analysis flight payload.")

    def _extract_models_from_table(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if table is None:
            raise ValueError("Could not locate Artificial Analysis leaderboard table.")

        header_row: list[str] | None = None
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if {
                "Model",
                "Creator",
                "Artificial Analysis Intelligence Index",
                "Blended USD/1M Tokens",
                "Median Tokens/s",
            }.issubset(set(cells)):
                header_row = cells
                break

        if header_row is None:
            raise ValueError("Could not locate Artificial Analysis table headers.")

        rows = table.select("tbody tr") or table.find_all("tr")
        payload: list[dict[str, Any]] = []

        for row in rows:
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
            if len(cells) < len(header_row):
                continue

            values = dict(zip(header_row, cells))
            model_name = first_non_empty(values.get("Model"))
            if not model_name or model_name == "Model":
                continue

            intelligence = _parse_numeric(values.get("Artificial Analysis Intelligence Index"))
            price = _parse_numeric(values.get("Blended USD/1M Tokens"))
            speed = _parse_numeric(values.get("Median Tokens/s"))
            if intelligence is None and price is None and speed is None:
                continue

            payload.append(
                {
                    "short_name": model_name,
                    "name": model_name,
                    "model_creators": {"name": values.get("Creator")},
                    "intelligence_index": intelligence,
                    "timescaleData": {"median_output_speed": speed},
                    "price_1m_blended_3_to_1": price,
                }
            )

        if not payload:
            raise ValueError("Could not parse any Artificial Analysis rows from table.")
        return payload

    def _extract_metrics(self, row: dict[str, Any]) -> dict[str, float | None]:
        timescale = row.get("timescaleData") or row.get("timescale_data") or {}
        if not isinstance(timescale, dict):
            timescale = {}

        return {
            "intelligence_index": safe_float(
                row.get("intelligenceIndex")
                or row.get("intelligence_index")
                or row.get("estimatedIntelligenceIndex")
                or row.get("estimated_intelligence_index")
            ),
            "median_output_speed": safe_float(
                timescale.get("medianOutputTokensPerSecond")
                or timescale.get("median_output_speed")
                or row.get("medianOutputTokensPerSecond")
                or row.get("median_output_speed")
            ),
            "price_1m_blended_3_to_1": safe_float(
                row.get("price1mBlended3To1")
                or row.get("price_1m_blended_3_to_1")
                or row.get("price_1m_blended")
                or row.get("blended_price_1m")
                or row.get("price")
            ),
        }


def _extract_balanced(text: str, start: int, open_char: str, close_char: str) -> str:
    if start < 0 or start >= len(text) or text[start] != open_char:
        raise ValueError("Balanced fragment start is invalid.")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("Could not extract balanced fragment.")


def _format_value(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _parse_numeric(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "N/A"}:
        return None

    cleaned = re.sub(r"[^0-9.+-]", "", text.replace(",", ""))
    if not cleaned:
        return None
    return safe_float(cleaned)
