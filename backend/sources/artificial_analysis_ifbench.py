from __future__ import annotations

import json
from typing import Any, Sequence
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, percent_score, safe_float, utc_now_iso


IFBENCH_URL = "https://artificialanalysis.ai/evaluations/ifbench"
IFBENCH_SCORE_KEY = "IFBench Benchmark Leaderboard"
IFBENCH_TIME_KEY = "IFBench Benchmark Leaderboard time per task"


class ArtificialAnalysisIfbenchAdapter(BaseSourceAdapter):
    source_id = "artificial_analysis_ifbench"
    benchmark_ids = (
        "aa_ifbench",
        "aa_ifbench_output_tokens",
        "aa_ifbench_cost",
        "aa_ifbench_time",
    )
    source_url = IFBENCH_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        response = await client.get(self.source_url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()

        records = self._build_raw_records(self._extract_datasets(response.text), fetched_at=utc_now_iso())
        if not records:
            raise ValueError("Could not parse any Artificial Analysis IFBench rows.")
        return records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        metric_specs = (
            ("aa_ifbench", "score_percent", "IFBench score %", "score"),
            ("aa_ifbench_output_tokens", "output_tokens_per_task", "output tokens per task", "token_usage"),
            ("aa_ifbench_cost", "cost_per_task_usd", "cost per task USD", "cost"),
            ("aa_ifbench_time", "time_per_task_minutes", "time per task minutes", "time"),
        )

        for record in raw_records:
            metrics = record.metadata.get("metrics") or {}
            if not isinstance(metrics, dict):
                continue

            for benchmark_id, metric_key, source_label, metric_group in metric_specs:
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
                        notes=f"Artificial Analysis IFBench field: {source_label}",
                        metadata={
                            **record.metadata,
                            "metric": metric_key,
                            "metric_group": metric_group,
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
            name = str(payload.get("name") or "")
            rows = payload.get("data")
            if payload.get("@type") != "Dataset" or not name.startswith("IFBench Benchmark Leaderboard"):
                continue
            if isinstance(rows, list):
                datasets.append({"name": name, "description": payload.get("description"), "data": rows})

        if not datasets:
            raise ValueError("Could not locate Artificial Analysis IFBench JSON-LD datasets.")
        return datasets

    def _build_raw_records(self, datasets: Sequence[dict[str, Any]], *, fetched_at: str) -> list[RawSourceRecord]:
        rows_by_identity: dict[str, dict[str, Any]] = {}
        dataset_names: list[str] = []

        for dataset in datasets:
            dataset_name = str(dataset.get("name") or "")
            rows = dataset.get("data")
            if not isinstance(rows, list):
                continue
            dataset_names.append(dataset_name)
            section = _dataset_section(dataset_name)

            for row in rows:
                if not isinstance(row, dict):
                    continue
                identity = _row_identity(row)
                label = str(row.get("label") or "").strip()
                if not identity or not label:
                    continue
                entry = rows_by_identity.setdefault(
                    identity,
                    {
                        "label": label,
                        "details_url": _absolute_details_url(row.get("detailsUrl")),
                        "sections": {},
                    },
                )
                entry["sections"][section] = dict(row)

        raw_records: list[RawSourceRecord] = []
        for identity, entry in sorted(rows_by_identity.items(), key=lambda item: str(item[1].get("label") or "").lower()):
            metrics = _metrics_from_sections(entry.get("sections") or {})
            if metrics["score_percent"] is None:
                continue

            raw_records.append(
                RawSourceRecord(
                    source_id=self.source_id,
                    benchmark_id="aa_ifbench",
                    raw_model_name=str(entry["label"]),
                    raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
                    source_url=self.source_url,
                    collected_at=fetched_at,
                    raw_model_key=_details_slug(entry.get("details_url")) or str(entry["label"]),
                    payload={
                        "page_url": self.source_url,
                        "details_url": entry.get("details_url"),
                        "sections": entry.get("sections") or {},
                    },
                    metadata={
                        "evaluation": "IFBench",
                        "page_url": self.source_url,
                        "details_url": entry.get("details_url"),
                        "dataset_names": dataset_names,
                        "metrics": metrics,
                        "row_identity": identity,
                    },
                )
            )

        return raw_records


def _dataset_section(dataset_name: str) -> str:
    if dataset_name.endswith(": Score"):
        return "score"
    if dataset_name.endswith(": Output Tokens per Task"):
        return "output_tokens"
    if dataset_name.endswith(": Cost per Task"):
        return "cost"
    if dataset_name.endswith(": Time per Task"):
        return "time"
    return dataset_name


def _row_identity(row: dict[str, Any]) -> str:
    return str(row.get("detailsUrl") or row.get("label") or "").strip()


def _metrics_from_sections(sections: dict[str, dict[str, Any]]) -> dict[str, float | None]:
    score_fraction = safe_float((sections.get("score") or {}).get(IFBENCH_SCORE_KEY))
    answer_tokens = safe_float((sections.get("output_tokens") or {}).get("answer"))
    reasoning_tokens = safe_float((sections.get("output_tokens") or {}).get("reasoning"))
    output_tokens = _sum_present(answer_tokens, reasoning_tokens)

    cost_row = sections.get("cost") or {}
    answer_cost = safe_float(cost_row.get("answer"))
    reasoning_cost = safe_float(cost_row.get("reasoning"))
    cache_write_cost = safe_float(cost_row.get("cacheWrite"))
    cache_hit_cost = safe_float(cost_row.get("cacheHit"))
    input_cost = safe_float(cost_row.get("input"))
    cost_per_task = _sum_present(answer_cost, reasoning_cost, cache_write_cost, cache_hit_cost, input_cost)

    time_minutes = safe_float((sections.get("time") or {}).get(IFBENCH_TIME_KEY))

    return {
        "score_fraction": score_fraction,
        "score_percent": percent_score(score_fraction),
        "answer_tokens_per_task": answer_tokens,
        "reasoning_tokens_per_task": reasoning_tokens,
        "output_tokens_per_task": output_tokens,
        "answer_cost_usd": answer_cost,
        "reasoning_cost_usd": reasoning_cost,
        "cache_write_cost_usd": cache_write_cost,
        "cache_hit_cost_usd": cache_hit_cost,
        "input_cost_usd": input_cost,
        "cost_per_task_usd": cost_per_task,
        "time_per_task_minutes": time_minutes,
    }


def _sum_present(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _absolute_details_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return urljoin("https://artificialanalysis.ai", text)


def _details_slug(details_url: Any) -> str | None:
    text = str(details_url or "").strip().rstrip("/")
    if not text:
        return None
    marker = "/models/"
    if marker not in text:
        return None
    return text.rsplit(marker, 1)[1] or None


def _format_value(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")
