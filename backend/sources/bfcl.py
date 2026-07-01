from __future__ import annotations

import csv
import json
import re
from io import StringIO
from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, safe_float, utc_now_iso


BFCL_LEADERBOARD_PAGE_URL = "https://gorilla.cs.berkeley.edu/leaderboard.html"
BFCL_OVERALL_CSV_URL = "https://gorilla.cs.berkeley.edu/data_overall.csv"
BFCL_PAGE_LAST_UPDATED = "2026-04-12"
BFCL_EVAL_COMMIT = "f7cf735"
BFCL_EVAL_VERSION = "2025.12.17"

PERCENT_FIELDS = (
    "Overall Acc",
    "Non-Live AST Acc",
    "Non-Live Simple AST",
    "Non-Live Multiple AST",
    "Non-Live Parallel AST",
    "Non-Live Parallel Multiple AST",
    "Live Acc",
    "Live Simple AST",
    "Live Multiple AST",
    "Live Parallel AST",
    "Live Parallel Multiple AST",
    "Multi Turn Acc",
    "Multi Turn Base",
    "Multi Turn Miss Func",
    "Multi Turn Miss Param",
    "Multi Turn Long Context",
    "Web Search Acc",
    "Web Search Base",
    "Web Search No Snippet",
    "Memory Acc",
    "Memory KV",
    "Memory Vector",
    "Memory Recursive Summarization",
    "Relevance Detection",
    "Irrelevance Detection",
)

NUMERIC_FIELDS = (
    "Rank",
    "Total Cost ($)",
    "Latency Mean (s)",
    "Latency Standard Deviation (s)",
    "Latency 95th Percentile (s)",
    "Format Sensitivity Max Delta",
    "Format Sensitivity Standard Deviation",
)


class BfclAdapter(BaseSourceAdapter):
    source_id = "bfcl"
    benchmark_ids = ("bfcl_overall",)
    source_url = BFCL_LEADERBOARD_PAGE_URL
    data_url = BFCL_OVERALL_CSV_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.data_url, timeout=30.0)
        response.raise_for_status()
        return self._build_raw_records(response.text, collected_at=utc_now_iso())

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            value = safe_float(record.metadata.get("overall_acc"))
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="bfcl_overall",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key or record.raw_model_name,
                    value=value,
                    raw_value=_format_value(value),
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes=(
                        "BFCL V4 overall function-calling accuracy from the official Berkeley "
                        f"leaderboard, updated {BFCL_PAGE_LAST_UPDATED}."
                    ),
                    metadata={
                        **record.metadata,
                        "metric": "overall_acc",
                    },
                )
            )

        return candidates

    def _build_raw_records(self, table_csv: str, *, collected_at: str) -> list[RawSourceRecord]:
        rows = csv.DictReader(StringIO(table_csv))
        required_fields = {"Model", "Overall Acc"}
        missing_fields = sorted(required_fields - set(rows.fieldnames or []))
        if missing_fields:
            raise ValueError(f"BFCL table is missing required columns: {', '.join(missing_fields)}")

        raw_records: list[RawSourceRecord] = []
        for row in rows:
            if None in row:
                continue

            original_model_name = first_non_empty(row.get("Model"))
            model_name, evaluation_mode = _split_evaluation_mode(original_model_name)
            overall_acc = _parse_percent(row.get("Overall Acc"))
            if not model_name or overall_acc is None:
                continue

            metadata = {
                "rank": safe_float(row.get("Rank")),
                "original_model_name": original_model_name,
                "evaluation_mode": evaluation_mode,
                "model_link": first_non_empty(row.get("Model Link")) or None,
                "organization": first_non_empty(row.get("Organization")) or None,
                "license": first_non_empty(row.get("License")) or None,
                "page_last_updated": BFCL_PAGE_LAST_UPDATED,
                "eval_commit": BFCL_EVAL_COMMIT,
                "bfcl_eval_version": BFCL_EVAL_VERSION,
                "leaderboard_url": self.source_url,
                "artifact_url": self.data_url,
                "overall_acc": overall_acc,
                "component_scores": _component_scores(row),
                "cost_usd": safe_float(row.get("Total Cost ($)")),
                "latency": {
                    "mean_seconds": safe_float(row.get("Latency Mean (s)")),
                    "stddev_seconds": safe_float(row.get("Latency Standard Deviation (s)")),
                    "p95_seconds": safe_float(row.get("Latency 95th Percentile (s)")),
                },
                "format_sensitivity": {
                    "max_delta": safe_float(row.get("Format Sensitivity Max Delta")),
                    "stddev": safe_float(row.get("Format Sensitivity Standard Deviation")),
                },
            }

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="bfcl_overall",
                    raw_model_name=model_name,
                    raw_value=_format_value(overall_acc),
                    source_url=self.data_url,
                    collected_at=collected_at,
                    raw_model_key=original_model_name or model_name,
                    payload=dict(row),
                    metadata=metadata,
                )
            )

        return raw_records


def _component_scores(row: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for field in PERCENT_FIELDS:
        if field == "Overall Acc":
            continue
        score = _parse_percent(row.get(field))
        if score is not None:
            scores[_field_key(field)] = score
    for field in NUMERIC_FIELDS:
        if field == "Rank":
            continue
        value = safe_float(row.get(field))
        if value is not None:
            scores[_field_key(field)] = value
    return scores


def _field_key(field: str) -> str:
    return (
        field.lower()
        .replace("($)", "usd")
        .replace("(s)", "seconds")
        .replace("%", "percent")
        .replace("-", " ")
        .replace("/", " ")
        .replace(" ", "_")
        .strip("_")
    )


def _parse_percent(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "N/A":
        return None
    if text.endswith("%"):
        text = text[:-1]
    return safe_float(text)


def _split_evaluation_mode(model_name: str) -> tuple[str, str | None]:
    text = first_non_empty(model_name)
    if not text:
        return "", None
    match = re.search(r"\s+\(([^()]+)\)\s*$", text)
    if not match:
        return text, None
    return text[: match.start()].strip(), match.group(1).strip() or None


def _format_value(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
