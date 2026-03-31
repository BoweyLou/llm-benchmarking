from __future__ import annotations

import json
import re
from typing import Any, Sequence

import httpx
from bs4 import BeautifulSoup

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, percent_score, safe_float, utc_now_iso


class TerminalBenchAdapter(BaseSourceAdapter):
    source_id = "terminal_bench"
    benchmark_ids = ("terminal_bench",)
    source_url = "https://www.tbench.ai/leaderboard/terminal-bench/2.0"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0)
        response.raise_for_status()

        rows = self._extract_rows(response.text)
        fetched_at = utc_now_iso()
        raw_records: list[RawSourceRecord] = []

        for row in rows:
            raw_records.append(self._build_raw_record(row, fetched_at=fetched_at))

        if not raw_records:
            raise ValueError("Could not parse any Terminal-Bench leaderboard rows.")

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        best_by_model: dict[str, RawSourceRecord] = {}

        for record in raw_records:
            if not bool(record.metadata.get("single_model")):
                continue
            if not bool(record.metadata.get("verified")):
                continue

            value = safe_float(record.raw_value)
            if value is None:
                continue

            model_key = record.raw_model_key or record.raw_model_name
            best = best_by_model.get(model_key)
            if best is None or _is_better_submission(record, best):
                best_by_model[model_key] = record

        candidates: list[ScoreCandidate] = []
        for model_key, record in sorted(best_by_model.items(), key=lambda item: item[0].lower()):
            value = safe_float(record.raw_value)
            if value is None:
                continue

            candidates.append(
                ScoreCandidate(
                    source_id=self.source_id,
                    benchmark_id="terminal_bench",
                    raw_model_name=record.raw_model_name,
                    raw_model_key=model_key,
                    value=value,
                    raw_value=record.raw_value,
                    source_url=record.source_url,
                    collected_at=record.collected_at,
                    source_type="secondary",
                    verified=True,
                    notes=(
                        "Derived from the best verified single-model Terminal-Bench submission: "
                        f'{first_non_empty(record.metadata.get("agent"), record.metadata.get("agent_name"), "Unknown agent")} '
                        f'v{first_non_empty(record.metadata.get("agent_version"), "unknown")} '
                        f'on {first_non_empty(record.metadata.get("leaderboard_date"), "unknown date")} '
                        f'via {first_non_empty(record.metadata.get("integration_method"), "unknown integration")}.'
                    ),
                    metadata=dict(record.metadata),
                )
            )

        return candidates

    def _build_raw_record(self, row: dict[str, Any], *, fetched_at: str) -> RawSourceRecord:
        model_names = _string_list(row.get("modelNames"))
        model_providers = _string_list(row.get("modelProviders"))
        single_model = _is_single_model_submission(row)
        accuracy = percent_score(row.get("accuracy"))
        if accuracy is None:
            raise ValueError("Terminal-Bench row is missing an accuracy value.")

        raw_model_name = _raw_model_name(row, model_names, single_model)
        raw_model_key = _raw_model_key(row, model_names, raw_model_name, single_model)

        metadata = {
            "agent": row.get("agent"),
            "agent_name": row.get("agentName"),
            "agent_version": row.get("agentVersion"),
            "agent_organization": row.get("agentOrganization"),
            "model_organization": row.get("modelOrganization"),
            "model_names": model_names,
            "model_providers": model_providers,
            "integration_method": row.get("integrationMethod"),
            "leaderboard_date": row.get("date"),
            "rank": row.get("rank"),
            "stderr": row.get("stderr"),
            "verified": bool(row.get("verified")),
            "single_model": single_model,
            "aggregate_submission": not single_model,
            "self_reported": True,
            "source_policy": "best_verified_single_model",
        }

        return RawSourceRecord(
            source_id=self.source_id,
            benchmark_id="terminal_bench",
            raw_model_name=raw_model_name,
            raw_value=_format_value(accuracy),
            source_url=self.source_url,
            collected_at=fetched_at,
            raw_model_key=raw_model_key,
            payload=dict(row),
            metadata=metadata,
        )

    def _extract_rows(self, html_text: str) -> list[dict[str, Any]]:
        rows = self._extract_rows_from_script_payload(html_text)
        if rows:
            return rows

        rows = self._extract_rows_from_table(html_text)
        if rows:
            return rows

        raise ValueError("Could not locate Terminal-Bench leaderboard rows.")

    def _extract_rows_from_script_payload(self, html_text: str) -> list[dict[str, Any]]:
        marker = '\\"rows\\":'
        marker_pos = html_text.find(marker)
        if marker_pos == -1:
            return []

        rows_start = html_text.find("[", marker_pos)
        if rows_start == -1:
            return []

        payload_text = html_text[rows_start:].replace('\\"', '"')
        rows, _ = json.JSONDecoder().raw_decode(payload_text)
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _extract_rows_from_table(self, html_text: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html_text, "html.parser")
        table = soup.find("table")
        if table is None:
            return []

        rows: list[dict[str, Any]] = []
        for row in table.select("tbody tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
            if len(cells) < 8:
                continue

            rank = _parse_rank(cells[1])
            accuracy = _parse_accuracy(cells[7])
            if rank is None or accuracy is None:
                continue

            rows.append(
                {
                    "agent": cells[2],
                    "model": [cells[3]],
                    "agentOrganization": cells[5],
                    "modelOrganization": [cells[6]],
                    "date": cells[4],
                    "accuracy": accuracy / 100.0,
                    "stderr": _parse_stderr(cells[7]),
                    "integrationMethod": "HTML",
                    "agentUrl": self.source_url,
                    "verified": False,
                    "agentName": cells[2],
                    "agentVersion": "unknown",
                    "modelNames": [cells[3]],
                    "modelProviders": [cells[6]],
                    "key": f"{cells[2].lower()}__{cells[3].lower()}",
                    "rank": rank,
                }
            )

        return rows


def _is_single_model_submission(row: dict[str, Any]) -> bool:
    model_names = _string_list(row.get("modelNames"))
    if len(model_names) != 1:
        return False
    model_orgs = _string_list(row.get("modelOrganization"))
    if any(value.lower() == "multiple" for value in model_orgs):
        return False
    agent = str(row.get("agent") or "").strip().lower()
    agent_name = str(row.get("agentName") or "").strip().lower()
    return agent != "multiple" and agent_name != "multiple"


def _raw_model_name(row: dict[str, Any], model_names: list[str], single_model: bool) -> str:
    if single_model and model_names:
        model_labels = _string_list(row.get("model"))
        return first_non_empty(model_labels[0] if model_labels else None, model_names[0])

    agent = str(row.get("agent") or row.get("agentName") or "Terminal-Bench aggregate").strip()
    if not agent:
        agent = "Terminal-Bench aggregate"
    return f"{agent} (multiple models)"


def _raw_model_key(row: dict[str, Any], model_names: list[str], raw_model_name: str, single_model: bool) -> str:
    if single_model and model_names:
        return model_names[0]
    return str(row.get("key") or raw_model_name).strip() or raw_model_name


def _is_better_submission(candidate: RawSourceRecord, current: RawSourceRecord) -> bool:
    candidate_value = safe_float(candidate.raw_value)
    current_value = safe_float(current.raw_value)
    if candidate_value is None:
        return False
    if current_value is None:
        return True
    if candidate_value != current_value:
        return candidate_value > current_value

    candidate_date = str(candidate.metadata.get("leaderboard_date") or "")
    current_date = str(current.metadata.get("leaderboard_date") or "")
    if candidate_date != current_date:
        return candidate_date > current_date

    candidate_stderr = safe_float(candidate.metadata.get("stderr"))
    current_stderr = safe_float(current.metadata.get("stderr"))
    if candidate_stderr is not None and current_stderr is not None and candidate_stderr != current_stderr:
        return candidate_stderr < current_stderr

    candidate_rank = int(candidate.metadata.get("rank") or 10**9)
    current_rank = int(current.metadata.get("rank") or 10**9)
    return candidate_rank < current_rank


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_rank(value: str) -> int | None:
    match = re.search(r"(\d+)", value)
    if not match:
        return None
    return int(match.group(1))


def _parse_accuracy(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    if not match:
        return None
    return safe_float(match.group(1))


def _parse_stderr(value: str) -> float | None:
    match = re.search(r"±\s*(\d+(?:\.\d+)?)", value)
    if not match:
        return None
    return safe_float(match.group(1))


def _format_value(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")
