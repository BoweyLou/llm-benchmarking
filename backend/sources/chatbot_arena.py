from __future__ import annotations

import ast
import html
import json
import re
from typing import Any, Sequence

import httpx

from .base import (
    BaseSourceAdapter,
    RawSourceRecord,
    ScoreCandidate,
    first_non_empty,
    safe_float,
    utc_now_iso,
)


class ChatbotArenaAdapter(BaseSourceAdapter):
    source_id = "chatbot_arena"
    benchmark_ids = ("chatbot_arena",)
    source_url = "https://arena.ai/leaderboard/text"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0)
        response.raise_for_status()

        entries = self._extract_entries(response.text)
        if not entries:
            entries = self._extract_entries_from_table(response.text)

        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for entry in entries:
            model_name = first_non_empty(entry.get("modelDisplayName"), entry.get("modelName"), entry.get("name"))
            if not model_name:
                continue

            rating = safe_float(entry.get("rating"))
            if rating is None:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="chatbot_arena",
                    raw_model_name=model_name,
                    raw_value=_format_value(rating),
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=model_name,
                    payload=entry,
                    metadata={
                        "rank": entry.get("rank"),
                        "rank_lower": entry.get("rankLower"),
                        "rank_upper": entry.get("rankUpper"),
                        "rating_lower": entry.get("ratingLower"),
                        "rating_upper": entry.get("ratingUpper"),
                        "votes": entry.get("votes"),
                        "organization": entry.get("modelOrganization"),
                        "model_url": entry.get("modelUrl"),
                        "license": entry.get("license"),
                        "input_price_per_million": entry.get("inputPricePerMillion"),
                        "output_price_per_million": entry.get("outputPricePerMillion"),
                        "context_length": entry.get("contextLength"),
                    },
                )
            )

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            value = safe_float(record.raw_value)
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="chatbot_arena",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=record.raw_model_key or record.raw_model_name,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="primary",
                    verified=True,
                    notes=f"Chatbot Arena votes: {record.metadata.get('votes')}",
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _extract_entries(self, html_text: str) -> list[dict[str, Any]]:
        pos = html_text.find('"modelDisplayName"')
        if pos == -1:
            pos = html_text.find('"leaderboard":{"arenaSlug":"text"')
        if pos == -1:
            return []

        start = html_text.rfind('self.__next_f.push([1,', 0, pos)
        end = html_text.find('])</script>', pos)
        if start == -1 or end == -1:
            return []

        fragment = html_text[start:end]
        encoded = fragment.split('self.__next_f.push([1,', 1)[1]
        decoded = ast.literal_eval(encoded)

        leaderboard_idx = decoded.find('"leaderboard":{')
        if leaderboard_idx == -1:
            return []

        object_start = decoded.find("{", leaderboard_idx)
        leaderboard_json = _extract_balanced(decoded, object_start, "{", "}")
        payload = json.loads(leaderboard_json)
        entries = payload.get("entries") or []
        return [entry for entry in entries if isinstance(entry, dict)]

    def _extract_entries_from_table(self, html_text: str) -> list[dict[str, Any]]:
        table_match = re.search(r"<table[^>]*>(.*?)</table>", html_text, re.S | re.I)
        if not table_match:
            return []

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.S | re.I)
        entries: list[dict[str, Any]] = []

        for row_html in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)
            if not cells:
                continue

            row_text = _strip_tags(row_html)
            model_name = _extract_anchor_text(row_html) or _extract_model_text(cells)
            rating = _extract_rating_from_text(row_text)
            if not model_name or rating is None:
                continue

            entries.append(
                {
                    "modelDisplayName": model_name,
                    "rating": rating,
                    "votes": _extract_votes_from_text(row_text),
                    "modelOrganization": _extract_org_from_text(row_text),
                    "modelUrl": _extract_model_url(row_html),
                    "license": _extract_license_from_text(row_text),
                    "contextLength": _extract_context_from_text(row_text),
                    "inputPricePerMillion": None,
                    "outputPricePerMillion": None,
                }
            )

        return entries


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


def _extract_anchor_text(row_html: str) -> str:
    match = re.search(r'<a[^>]*>(.*?)</a>', row_html, re.S | re.I)
    if not match:
        return ""
    return _strip_tags(match.group(1))


def _extract_model_text(cells: list[str]) -> str:
    for cell in cells:
        if "<a" in cell.lower():
            text = _strip_tags(cell)
            if text:
                return text
    for cell in cells:
        text = _strip_tags(cell)
        if text and not re.fullmatch(r"[\d,\s±]+", text):
            return text
    return ""


def _extract_rating_from_text(text: str) -> float | None:
    match = re.search(r"(\d{3,4}(?:\.\d+)?)\s*±\s*\d+", text)
    if not match:
        match = re.search(r"(\d{3,4}(?:\.\d+)?)", text)
    if not match:
        return None
    return safe_float(match.group(1))


def _extract_votes_from_text(text: str) -> str | None:
    matches = re.findall(r"\d{1,3}(?:,\d{3})+|\d+", text)
    if not matches:
        return None
    for token in matches:
        if "," in token:
            return token
    return matches[-1]


def _extract_org_from_text(text: str) -> str | None:
    for candidate in ("Anthropic", "Google", "OpenAI", "xAI", "Alibaba", "Baidu", "Moonshot", "Z.ai", "Zhipu"):
        if candidate.lower() in text.lower():
            return candidate
    return None


def _extract_license_from_text(text: str) -> str | None:
    for candidate in ("Proprietary", "Open Source", "MIT", "Apache 2.0", "Modified MIT"):
        if candidate.lower() in text.lower():
            return candidate
    return None


def _extract_context_from_text(text: str) -> str | None:
    match = re.search(r"(\d+(?:\.\d+)?\s*[KM]?)", text)
    return match.group(1) if match else None


def _extract_model_url(row_html: str) -> str | None:
    match = re.search(r'<a[^>]*href="([^"]+)"', row_html, re.I)
    if not match:
        return None
    return html.unescape(match.group(1))


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_value(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")
