from __future__ import annotations

import math
import re
from typing import Any, Sequence

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, safe_float, utc_now_iso


ARENA_DATASET_REPOSITORY = "lmarena-ai/leaderboard-dataset"
ARENA_DATASET_URL = f"https://huggingface.co/datasets/{ARENA_DATASET_REPOSITORY}"
ARENA_DATASET_API_URL = f"https://huggingface.co/api/datasets/{ARENA_DATASET_REPOSITORY}"
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")

# Keep the long-lived identifier as the style-controlled Text Overall score so
# existing use-case weights retain their meaning. New Arena surfaces are
# intentionally separate and have no default use-case weight.
ARENA_SELECTIONS: tuple[tuple[str, str, str, bool], ...] = (
    ("text", "overall", "chatbot_arena_text_raw", True),
    ("text_style_control", "overall", "chatbot_arena", True),
    ("text_style_control", "coding", "chatbot_arena_coding", False),
    ("text_style_control", "instruction_following", "chatbot_arena_instruction_following", False),
    ("text_style_control", "multi_turn", "chatbot_arena_multi_turn", False),
    ("text_style_control", "expert", "chatbot_arena_expert", False),
    (
        "text_style_control",
        "industry_business_and_management_and_financial_operations",
        "chatbot_arena_finance_business",
        False,
    ),
    (
        "text_style_control",
        "industry_legal_and_government",
        "chatbot_arena_legal_government",
        False,
    ),
    (
        "text_style_control",
        "industry_software_and_it_services",
        "chatbot_arena_software_it",
        False,
    ),
    ("webdev", "overall", "chatbot_arena_webdev", True),
    ("agent", "overall", "chatbot_arena_agent", True),
    ("vision_style_control", "overall", "chatbot_arena_vision", True),
    ("document_style_control", "overall", "chatbot_arena_document", True),
    ("search_style_control", "overall", "chatbot_arena_search", True),
)

RATING_COLUMNS = {
    "model_name",
    "organization",
    "license",
    "rating",
    "rating_lower",
    "rating_upper",
    "variance",
    "vote_count",
    "rank",
    "category",
    "leaderboard_publish_date",
}
AGENT_COLUMNS = {
    "model_name",
    "organization",
    "license",
    "score",
    "score_ci_lower",
    "score_ci_upper",
    "observation_count",
    "session_count",
    "rank",
    "category",
    "leaderboard_publish_date",
}
_SAFE_MODEL_NAME = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")


class ChatbotArenaAdapter(BaseSourceAdapter):
    source_id = "chatbot_arena"
    benchmark_ids = tuple(benchmark_id for _split, _category, benchmark_id, _required in ARENA_SELECTIONS)
    source_url = ARENA_DATASET_URL

    def __init__(self, *, revision: str | None = None) -> None:
        if revision is not None and not _REVISION_RE.fullmatch(revision):
            raise ValueError("Arena dataset revision must be a 40-character lowercase Git SHA.")
        self.revision = revision

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        fetched_at = utc_now_iso()
        revision = self.revision or await self._resolve_revision(client)
        records: list[RawSourceRecord] = []
        selections_by_split: dict[str, list[tuple[str, str, bool]]] = {}
        for split, category, benchmark_id, required in ARENA_SELECTIONS:
            selections_by_split.setdefault(split, []).append((category, benchmark_id, required))
        for split, selections in selections_by_split.items():
            parquet_url = self._parquet_url(split, revision)
            response = await client.get(parquet_url, timeout=60.0, follow_redirects=True)
            response.raise_for_status()
            if not response.content:
                raise ValueError(f"Arena dataset returned an empty Parquet payload for {split}.")
            records.extend(
                self._records_from_parquet(
                    response.content,
                    split=split,
                    selections=selections,
                    parquet_url=parquet_url,
                    fetched_at=fetched_at,
                    revision=revision,
                )
            )
        if not records:
            raise ValueError("Arena dataset produced no records.")
        return records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []
        for record in raw_records:
            value = safe_float(record.raw_value)
            if value is None or not math.isfinite(value):
                raise ValueError(f"Arena score is invalid for {record.raw_model_name!r}.")
            metadata = dict(record.metadata)
            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id=record.benchmark_id,
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key or record.raw_model_name,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes="Official revision-pinned Arena leaderboard dataset.",
                    confidence_lower=safe_float(metadata.get("confidence_lower")),
                    confidence_upper=safe_float(metadata.get("confidence_upper")),
                    variance=safe_float(metadata.get("variance")),
                    vote_count=_safe_int(metadata.get("vote_count")),
                    observation_count=_safe_int(metadata.get("observation_count")),
                    session_count=_safe_int(metadata.get("session_count")),
                    rank=_safe_int(metadata.get("rank")),
                    category=str(metadata.get("category") or "overall"),
                    publication_date=str(metadata.get("leaderboard_publish_date") or "") or None,
                    methodology=str(metadata.get("methodology") or "") or None,
                    source_listing_status="listed",
                    style_control=bool(metadata.get("style_control")),
                    preliminary=None,
                    source_metadata={
                        "dataset_revision": metadata.get("dataset_revision"),
                        "dataset_split": metadata.get("dataset_split"),
                        "organization": metadata.get("organization"),
                        "license": metadata.get("license"),
                    },
                    metadata=metadata,
                )
            )
        return candidates

    async def _resolve_revision(self, client: httpx.AsyncClient) -> str:
        response = await client.get(ARENA_DATASET_API_URL, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        try:
            revision = str(response.json()["sha"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Arena dataset metadata did not contain a revision SHA.") from exc
        if not _REVISION_RE.fullmatch(revision):
            raise ValueError("Arena dataset metadata returned an invalid revision SHA.")
        return revision

    @staticmethod
    def _parquet_url(split: str, revision: str) -> str:
        return (
            f"https://huggingface.co/datasets/{ARENA_DATASET_REPOSITORY}/resolve/"
            f"{revision}/{split}/latest-00000-of-00001.parquet"
        )

    def _records_from_parquet(
        self,
        content: bytes,
        *,
        split: str,
        selections: list[tuple[str, str, bool]],
        parquet_url: str,
        fetched_at: str,
        revision: str,
    ) -> list[RawSourceRecord]:
        try:
            table = pq.read_table(pa.BufferReader(content))
        except Exception as exc:
            raise ValueError(f"Arena {split} payload is not valid Parquet: {exc}") from exc

        required = AGENT_COLUMNS if split == "agent" else RATING_COLUMNS
        missing = sorted(required.difference(table.schema.names))
        if missing:
            raise ValueError(f"Arena {split} schema is missing required columns: {', '.join(missing)}")

        rows = table.select(sorted(required)).to_pylist()
        publish_dates = [str(row.get("leaderboard_publish_date") or "") for row in rows]
        latest_publish_date = max((value for value in publish_dates if value), default="")
        if not latest_publish_date:
            raise ValueError(f"Arena {split} has no leaderboard publication date.")

        records: list[RawSourceRecord] = []
        for category, benchmark_id, required in selections:
            selected = [
                row
                for row in rows
                if str(row.get("leaderboard_publish_date") or "") == latest_publish_date
                and str(row.get("category") or "").strip().lower() == category
            ]
            if not selected:
                if required:
                    raise ValueError(
                        f"Arena {split} has no required {category} rows for {latest_publish_date}."
                    )
                continue
            records.extend(
                self._records_from_rows(
                    selected,
                    split=split,
                    category=category,
                    benchmark_id=benchmark_id,
                    parquet_url=parquet_url,
                    latest_publish_date=latest_publish_date,
                    revision=revision,
                )
            )
        return records

    def _records_from_rows(
        self,
        selected: list[dict[str, Any]],
        *,
        split: str,
        category: str,
        benchmark_id: str,
        parquet_url: str,
        latest_publish_date: str,
        revision: str,
    ) -> list[RawSourceRecord]:
        deduplicated: dict[str, dict[str, Any]] = {}
        duplicate_counts: dict[str, int] = {}
        for row in selected:
            identity_key = str(row.get("model_name") or "").strip().casefold()
            duplicate_counts[identity_key] = duplicate_counts.get(identity_key, 0) + 1
            current = deduplicated.get(identity_key)
            if current is None or _evidence_count(row) > _evidence_count(current):
                deduplicated[identity_key] = row
        records: list[RawSourceRecord] = []
        for identity_key, row in deduplicated.items():
            model_name = str(row.get("model_name") or "").strip()
            organization = str(row.get("organization") or "").strip()
            license_name = str(row.get("license") or "").strip()
            if not model_name or not _SAFE_MODEL_NAME.fullmatch(model_name):
                raise ValueError(f"Arena {split} contains an unsafe or empty model identity.")

            value_key = "score" if split == "agent" else "rating"
            value = safe_float(row.get(value_key))
            if value is None or not math.isfinite(value):
                raise ValueError(f"Arena {split} identity {model_name!r} has an invalid score.")
            lower_key = "score_ci_lower" if split == "agent" else "rating_lower"
            upper_key = "score_ci_upper" if split == "agent" else "rating_upper"
            lower = safe_float(row.get(lower_key))
            upper = safe_float(row.get(upper_key))
            if lower is None or upper is None or lower > value or value > upper:
                raise ValueError(f"Arena {split} identity {model_name!r} has invalid confidence bounds.")

            payload = dict(row)
            metadata = {
                "organization": organization,
                "license": license_name,
                "confidence_lower": lower,
                "confidence_upper": upper,
                "variance": row.get("variance"),
                "vote_count": row.get("vote_count"),
                "observation_count": row.get("observation_count"),
                "session_count": row.get("session_count"),
                "rank": row.get("rank"),
                "category": category,
                "leaderboard_publish_date": latest_publish_date,
                "methodology": "inverse_propensity_scored_agent_success" if split == "agent" else "bradley_terry_style_controlled" if "style_control" in split else "bradley_terry",
                "style_control": "style_control" in split,
                "dataset_revision": revision,
                "dataset_split": split,
                # Arena listing is evidence, not global model availability. It
                # must never create or reactivate a catalog model.
                "existing_models_only": True,
                "source_listing_status": "listed",
                "duplicate_display_name_rows": duplicate_counts[identity_key],
            }
            records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id=benchmark_id,
                    raw_model_name=model_name,
                    raw_model_key=model_name,
                    raw_value=_format_value(value),
                    source_url=parquet_url,
                    collected_at=f"{latest_publish_date}T00:00:00Z",
                    payload=payload,
                    metadata=metadata,
                )
            )
        return records


def _safe_int(value: Any) -> int | None:
    number = safe_float(value)
    if number is None or not math.isfinite(number):
        return None
    return int(number)


def _evidence_count(row: dict[str, Any]) -> float:
    return max(
        safe_float(row.get("vote_count")) or 0.0,
        safe_float(row.get("session_count")) or 0.0,
        safe_float(row.get("observation_count")) or 0.0,
    )


def _format_value(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.10f}".rstrip("0").rstrip(".")
