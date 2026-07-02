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
    percent_score,
    safe_float,
    utc_now_iso,
)


AA_METRIC_SPECS: tuple[dict[str, Any], ...] = (
    {
        "benchmark_id": "aa_intelligence",
        "metric_key": "intelligence_index",
        "source_label": "intelligenceIndex",
        "paths": ("intelligenceIndex", "intelligence_index", "estimatedIntelligenceIndex", "estimated_intelligence_index"),
    },
    {
        "benchmark_id": "aa_coding_index",
        "metric_key": "coding_index",
        "source_label": "codingIndex",
        "paths": ("codingIndex", "coding_index"),
    },
    {
        "benchmark_id": "aa_agentic_index",
        "metric_key": "agentic_index",
        "source_label": "agenticIndex",
        "paths": ("agenticIndex", "agentic_index"),
    },
    {
        "benchmark_id": "aa_tau2_telecom",
        "metric_key": "tau2_telecom",
        "source_label": "tau2",
        "paths": ("tau2", "tau2_telecom"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_tau_banking",
        "metric_key": "tau_banking",
        "source_label": "tauBanking",
        "paths": ("tauBanking", "tau_banking"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_terminalbench_hard",
        "metric_key": "terminalbench_hard",
        "source_label": "terminalbenchHard",
        "paths": ("terminalbenchHard", "terminalbench_hard"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_terminalbench_v2_1",
        "metric_key": "terminalbench_v2_1",
        "source_label": "terminalbenchV21",
        "paths": ("terminalbenchV21", "terminalbench_v2_1"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_scicode",
        "metric_key": "scicode",
        "source_label": "scicode",
        "paths": ("scicode",),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_lcr",
        "metric_key": "lcr",
        "source_label": "lcr",
        "paths": ("lcr", "aa_lcr"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_omniscience_index",
        "metric_key": "omniscience_index",
        "source_label": "omniscience",
        "paths": ("omniscience", "aa_omniscience_index"),
    },
    {
        "benchmark_id": "aa_omniscience_accuracy",
        "metric_key": "omniscience_accuracy",
        "source_label": "omniscienceAccuracy",
        "paths": ("omniscienceAccuracy", "aa_omniscience_accuracy"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_omniscience_non_hallucination",
        "metric_key": "omniscience_non_hallucination",
        "source_label": "omniscienceNonHallucination",
        "paths": ("omniscienceNonHallucination", "aa_omniscience_non_hallucination_rate"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_ifbench",
        "metric_key": "ifbench",
        "source_label": "ifbench",
        "paths": ("ifbench",),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_hle",
        "metric_key": "hle",
        "source_label": "hle",
        "paths": ("hle",),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_gpqa_diamond",
        "metric_key": "gpqa_diamond",
        "source_label": "gpqa",
        "paths": ("gpqa", "gpqa_diamond"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_critpt",
        "metric_key": "critpt",
        "source_label": "critpt",
        "paths": ("critpt",),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_gdpval_normalized",
        "metric_key": "gdpval_normalized",
        "source_label": "gdpvalNormalized",
        "paths": ("gdpvalNormalized", "gdpval_aa_normalized"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_mmmu_pro",
        "metric_key": "mmmu_pro",
        "source_label": "mmmuPro",
        "paths": ("mmmuPro", "mmmu_pro"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_apex_agents",
        "metric_key": "apex_agents",
        "source_label": "apexAgents",
        "paths": ("apexAgents", "apex_agents"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_itbench_sre",
        "metric_key": "itbench_sre",
        "source_label": "itbenchSre",
        "paths": ("itbenchSre", "itbench_sre"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_openness_index",
        "metric_key": "openness_index",
        "source_label": "opennessBreakdown.opennessIndex",
        "paths": ("opennessBreakdown.opennessIndex", "artificial_analysis_openness_index"),
    },
    {
        "benchmark_id": "aa_multilingual_index",
        "metric_key": "multilingual_index",
        "source_label": "multilingualBreakdown.index",
        "paths": ("multilingualBreakdown.index", "artificial_analysis_multilingual_index"),
        "scale": "percent",
    },
    {
        "benchmark_id": "aa_cost",
        "metric_key": "price_1m_blended_3_to_1",
        "source_label": "price1mBlended0To3To1",
        "paths": ("price1mBlended0To3To1", "price1mBlended3To1", "price_1m_blended_3_to_1", "price_1m_blended", "blended_price_1m", "price"),
    },
    {
        "benchmark_id": "aa_cost_blended_7_2_1",
        "metric_key": "price_1m_blended_7_to_2_to_1",
        "source_label": "price1mBlended7To2To1",
        "paths": ("price1mBlended7To2To1", "price_1m_blended_7_to_2_to_1"),
    },
    {
        "benchmark_id": "aa_cost_blended_1_1",
        "metric_key": "price_1m_blended_1_to_1",
        "source_label": "price1mBlended0To1To1",
        "paths": ("price1mBlended0To1To1", "price_1m_blended_1_to_1"),
    },
    {
        "benchmark_id": "aa_cost_blended_100_1",
        "metric_key": "price_1m_blended_100_to_1",
        "source_label": "price1mBlended100To1To1",
        "paths": ("price1mBlended100To1To1", "price_1m_blended_100_to_1"),
    },
    {
        "benchmark_id": "aa_cost_blended_output_heavy",
        "metric_key": "price_1m_blended_output_heavy",
        "source_label": "price1mBlended0To100To1",
        "paths": ("price1mBlended0To100To1", "price_1m_blended_0_to_100_to_1"),
    },
    {
        "benchmark_id": "aa_price_input",
        "metric_key": "price_1m_input_tokens",
        "source_label": "price1mInputTokens",
        "paths": ("price1mInputTokens", "price_1m_input_tokens"),
    },
    {
        "benchmark_id": "aa_price_output",
        "metric_key": "price_1m_output_tokens",
        "source_label": "price1mOutputTokens",
        "paths": ("price1mOutputTokens", "price_1m_output_tokens"),
    },
    {
        "benchmark_id": "aa_price_cache_hit",
        "metric_key": "price_1m_cache_hit_tokens",
        "source_label": "cacheHitPrice",
        "paths": ("cacheHitPrice", "price_1m_cache_hit_tokens"),
    },
    {
        "benchmark_id": "aa_price_cache_write",
        "metric_key": "price_1m_cache_write_tokens",
        "source_label": "cacheWritePrice",
        "paths": ("cacheWritePrice", "price_1m_cache_write_tokens"),
    },
    {
        "benchmark_id": "aa_speed",
        "metric_key": "median_output_speed",
        "source_label": "medianOutputTokensPerSecond",
        "paths": ("timescaleData.medianOutputTokensPerSecond", "timescaleData.median_output_speed", "medianOutputTokensPerSecond", "median_output_speed"),
    },
    {
        "benchmark_id": "aa_answer_speed",
        "metric_key": "median_answer_output_speed",
        "source_label": "medianCanonicalAnswerOutputSpeed",
        "paths": ("medianCanonicalAnswerOutputSpeed", "median_canonical_answer_output_speed"),
    },
    {
        "benchmark_id": "aa_time_to_first_token",
        "metric_key": "median_time_to_first_token_seconds",
        "source_label": "medianTimeToFirstTokenSeconds",
        "paths": ("medianTimeToFirstTokenSeconds", "median_time_to_first_token_seconds"),
    },
    {
        "benchmark_id": "aa_time_to_first_answer_token",
        "metric_key": "median_time_to_first_answer_token_seconds",
        "source_label": "medianTimeToFirstAnswerTokenSeconds",
        "paths": ("medianTimeToFirstAnswerTokenSeconds", "median_time_to_first_answer_token_seconds"),
    },
    {
        "benchmark_id": "aa_end_to_end_response_time",
        "metric_key": "median_end_to_end_response_time_seconds",
        "source_label": "medianEndToEndResponseTimeSeconds",
        "paths": ("medianEndToEndResponseTimeSeconds", "median_end_to_end_response_time_seconds"),
    },
    {
        "benchmark_id": "aa_reasoning_time",
        "metric_key": "median_reasoning_time_seconds",
        "source_label": "medianReasoningTimeSeconds",
        "paths": ("medianReasoningTimeSeconds", "median_reasoning_time_seconds"),
    },
    {
        "benchmark_id": "aa_speed_p05",
        "metric_key": "percentile_05_output_speed",
        "source_label": "percentile05OutputTokensPerSecond",
        "paths": ("percentile05OutputTokensPerSecond", "percentile_05_output_tokens_per_second"),
    },
    {
        "benchmark_id": "aa_speed_q25",
        "metric_key": "quartile_25_output_speed",
        "source_label": "quartile25OutputTokensPerSecond",
        "paths": ("quartile25OutputTokensPerSecond", "quartile_25_output_tokens_per_second"),
    },
    {
        "benchmark_id": "aa_speed_q75",
        "metric_key": "quartile_75_output_speed",
        "source_label": "quartile75OutputTokensPerSecond",
        "paths": ("quartile75OutputTokensPerSecond", "quartile_75_output_tokens_per_second"),
    },
    {
        "benchmark_id": "aa_speed_p95",
        "metric_key": "percentile_95_output_speed",
        "source_label": "percentile95OutputTokensPerSecond",
        "paths": ("percentile95OutputTokensPerSecond", "percentile_95_output_tokens_per_second"),
    },
    {
        "benchmark_id": "aa_ttft_p05",
        "metric_key": "percentile_05_time_to_first_token",
        "source_label": "percentile05TimeToFirstTokenSeconds",
        "paths": ("percentile05TimeToFirstTokenSeconds", "percentile_05_time_to_first_token_seconds"),
    },
    {
        "benchmark_id": "aa_ttft_q25",
        "metric_key": "quartile_25_time_to_first_token",
        "source_label": "quartile25TimeToFirstTokenSeconds",
        "paths": ("quartile25TimeToFirstTokenSeconds", "quartile_25_time_to_first_token_seconds"),
    },
    {
        "benchmark_id": "aa_ttft_q75",
        "metric_key": "quartile_75_time_to_first_token",
        "source_label": "quartile75TimeToFirstTokenSeconds",
        "paths": ("quartile75TimeToFirstTokenSeconds", "quartile_75_time_to_first_token_seconds"),
    },
    {
        "benchmark_id": "aa_ttft_p95",
        "metric_key": "percentile_95_time_to_first_token",
        "source_label": "percentile95TimeToFirstTokenSeconds",
        "paths": ("percentile95TimeToFirstTokenSeconds", "percentile_95_time_to_first_token_seconds"),
    },
    {
        "benchmark_id": "aa_intelligence_cost_total",
        "metric_key": "intelligence_index_cost_total",
        "source_label": "intelligenceIndexCostTotal",
        "paths": ("intelligenceIndexCostTotal", "artificial_analysis_intelligence_index_cost.total_cost"),
    },
    {
        "benchmark_id": "aa_intelligence_cost_per_task",
        "metric_key": "intelligence_index_cost_per_task",
        "source_label": "intelligenceIndexCostPerTask.cost.total",
        "paths": ("intelligenceIndexCostPerTask.cost.total", "artificial_analysis_intelligence_index_cost.cost_per_task.total_cost"),
    },
    {
        "benchmark_id": "aa_intelligence_input_cost",
        "metric_key": "intelligence_index_input_cost",
        "source_label": "intelligenceIndexCostInput",
        "paths": ("intelligenceIndexCostInput", "artificial_analysis_intelligence_index_cost.input_cost"),
    },
    {
        "benchmark_id": "aa_intelligence_output_cost",
        "metric_key": "intelligence_index_output_cost",
        "source_label": "intelligenceIndexCostOutput",
        "paths": ("intelligenceIndexCostOutput", "artificial_analysis_intelligence_index_cost.output_cost"),
    },
    {
        "benchmark_id": "aa_intelligence_reasoning_cost",
        "metric_key": "intelligence_index_reasoning_cost",
        "source_label": "intelligenceIndexCostReasoning",
        "paths": ("intelligenceIndexCostReasoning", "artificial_analysis_intelligence_index_cost.reasoning_cost"),
    },
    {
        "benchmark_id": "aa_intelligence_answer_cost",
        "metric_key": "intelligence_index_answer_cost",
        "source_label": "intelligenceIndexCostAnswer",
        "paths": ("intelligenceIndexCostAnswer", "artificial_analysis_intelligence_index_cost.answer_cost"),
    },
    {
        "benchmark_id": "aa_intelligence_time_per_task",
        "metric_key": "intelligence_index_time_per_task",
        "source_label": "intelligenceIndexTimePerTask",
        "paths": ("intelligenceIndexTimePerTask", "artificial_analysis_intelligence_index_time_per_task"),
    },
)


class ArtificialAnalysisAdapter(BaseSourceAdapter):
    source_id = "artificial_analysis"
    benchmark_ids = tuple(str(spec["benchmark_id"]) for spec in AA_METRIC_SPECS)
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

            raw_records.append(self._build_raw_record(row, model_name=model_name, metrics=metrics, fetched_at=fetched_at))

        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            metrics = record.metadata.get("metrics") or {}
            if not isinstance(metrics, dict):
                continue

            for spec in AA_METRIC_SPECS:
                metric_key = str(spec["metric_key"])
                value = _score_value(metrics.get(metric_key), scale=str(spec.get("scale") or "number"))
                if value is None:
                    continue

                candidates.append(
                    ScoreCandidate(
                        source_id=self.source_id,
                        benchmark_id=str(spec["benchmark_id"]),
                        raw_model_name=record.raw_model_name,
                        raw_model_key=record.raw_model_key or record.raw_model_name,
                        value=value,
                        raw_value=_format_value(value),
                        source_url=record.source_url,
                        collected_at=record.collected_at,
                        source_type="primary",
                        verified=True,
                        notes=f"Artificial Analysis field: {spec['source_label']}",
                        metadata={
                            **record.metadata,
                            "metric": metric_key,
                            "source_field": spec["source_label"],
                            "scale": spec.get("scale") or "number",
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
        return {
            str(spec["metric_key"]): _first_numeric(row, *[str(path) for path in spec["paths"]])
            for spec in AA_METRIC_SPECS
        }

    def _extract_metadata(self, row: dict[str, Any]) -> dict[str, Any]:
        return _drop_empty(
            {
                "display_order": row.get("display_order"),
                "deleted": bool(row.get("deleted")),
                "deprecated": bool(row.get("deprecated")),
                "model_family_slug": row.get("model_family_slug"),
                "model_creator": first_non_empty(
                    (row.get("creator") or {}).get("name") if isinstance(row.get("creator"), dict) else None,
                    (row.get("model_creators") or {}).get("name") if isinstance(row.get("model_creators"), dict) else None,
                    row.get("modelCreatorName"),
                ),
                "model_creator_slug": row.get("modelCreatorSlug"),
                "model_creator_country": row.get("modelCreatorCountry"),
                "release_date": row.get("releaseDate"),
                "reasoning_model": row.get("reasoningModel"),
                "context_window_tokens": row.get("contextWindowTokens"),
                "total_parameters": row.get("totalParameters"),
                "active_parameters": row.get("activeParameters"),
                "size_class": row.get("sizeClass"),
                "param_class": row.get("paramClass"),
                "price_class": row.get("priceClass"),
                "input_modalities": {
                    "text": row.get("inputModalityText"),
                    "image": row.get("inputModalityImage"),
                    "video": row.get("inputModalityVideo"),
                    "speech": row.get("inputModalitySpeech"),
                },
                "output_modalities": {
                    "text": row.get("outputModalityText"),
                    "image": row.get("outputModalityImage"),
                    "video": row.get("outputModalityVideo"),
                    "speech": row.get("outputModalitySpeech"),
                },
                "is_open_weights": row.get("isOpenWeights"),
                "commercial_allowed": row.get("commercialAllowed"),
                "license_name": row.get("licenseName"),
                "license_url": row.get("licenseUrl"),
                "huggingface_url": row.get("huggingfaceUrl"),
                "openrouter_api_id": row.get("openrouterApiId"),
                "training_tokens_trillions": row.get("trainingTokensTrillions"),
                "eval_token_counts": row.get("evalTokenCounts"),
                "intelligence_index_token_counts": row.get("intelligenceIndexTokenCounts"),
                "intelligence_index_output_tokens_per_task": row.get("intelligenceIndexOutputTokensPerTask"),
                "intelligence_index_cost_per_task": row.get("intelligenceIndexCostPerTask"),
                "gdpval_breakdown": row.get("gdpvalBreakdown"),
                "omniscience_breakdown": row.get("omniscienceBreakdown"),
                "multilingual_breakdown": row.get("multilingualBreakdown"),
                "openness_breakdown": row.get("opennessBreakdown"),
            }
        )

    def _build_raw_record(
        self,
        row: dict[str, Any],
        *,
        model_name: str | None = None,
        metrics: dict[str, float | None] | None = None,
        fetched_at: str,
    ) -> RawSourceRecord:
        raw_model_name = model_name or first_non_empty(
            row.get("shortName"),
            row.get("short_name"),
            row.get("name"),
            row.get("slug"),
        )
        metric_values = metrics or self._extract_metrics(row)
        metadata = self._extract_metadata(row)
        metadata["metrics"] = metric_values
        return RawSourceRecord(
            source_id=self.source_id,
            benchmark_id="aa_intelligence",
            raw_model_name=raw_model_name,
            raw_value=json.dumps(metric_values, ensure_ascii=True, sort_keys=True),
            source_url=self.source_url,
            collected_at=fetched_at,
            raw_model_key=first_non_empty(row.get("slug"), row.get("id"), raw_model_name),
            payload=row,
            metadata=metadata,
        )


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


def _score_value(value: Any, *, scale: str) -> float | None:
    if scale == "percent":
        return percent_score(value)
    return safe_float(value)


def _first_numeric(row: dict[str, Any], *paths: str) -> float | None:
    for path in paths:
        value = _path_value(row, path)
        number = safe_float(_clean_undefined(value))
        if number is not None:
            return number
    return None


def _path_value(row: dict[str, Any], path: str) -> Any:
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _drop_empty(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        normalized = _clean_undefined(value)
        if normalized is None:
            continue
        if isinstance(normalized, dict) and not normalized:
            continue
        cleaned[key] = normalized
    return cleaned


def _clean_undefined(value: Any) -> Any:
    if value == "$undefined":
        return None
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _clean_undefined(item)) is not None
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _clean_undefined(item)) is not None]
    return value


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
