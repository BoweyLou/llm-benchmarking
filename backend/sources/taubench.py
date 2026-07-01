from __future__ import annotations

import asyncio
import json
from typing import Any, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, first_non_empty, safe_float, utc_now_iso


BASE_URL = "https://sierra-tau-bench-public.s3.amazonaws.com/submissions"
MANIFEST_URL = f"{BASE_URL}/manifest.json"
PAGE_URL = "https://taubench.com/"

TEXT_DOMAINS = {
    "airline": ("taubench_text_airline", "Airline"),
    "retail": ("taubench_text_retail", "Retail"),
    "telecom": ("taubench_text_telecom", "Telecom"),
    "banking_knowledge": ("taubench_text_banking_knowledge", "Banking knowledge"),
}
VOICE_DOMAINS = {
    "airline": ("taubench_voice_airline", "Voice airline"),
    "retail": ("taubench_voice_retail", "Voice retail"),
    "telecom": ("taubench_voice_telecom", "Voice telecom"),
}
MEAN_BENCHMARKS = {
    "text": ("taubench_text_mean", "Text mean"),
    "voice": ("taubench_voice_mean", "Voice mean"),
}


class TaubenchAdapter(BaseSourceAdapter):
    source_id = "taubench"
    benchmark_ids = (
        "taubench_text_mean",
        "taubench_text_airline",
        "taubench_text_retail",
        "taubench_text_telecom",
        "taubench_text_banking_knowledge",
        "taubench_voice_mean",
        "taubench_voice_airline",
        "taubench_voice_retail",
        "taubench_voice_telecom",
    )
    source_url = PAGE_URL

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        manifest_response = await client.get(MANIFEST_URL, timeout=30.0)
        manifest_response.raise_for_status()
        manifest = manifest_response.json()
        if not isinstance(manifest, dict):
            raise ValueError("tau-bench manifest payload was not a JSON object.")

        fetched_at = utc_now_iso()
        submission_specs = [
            ("submissions", "text", submission_id)
            for submission_id in _string_list(manifest.get("submissions"))
        ] + [
            ("voice_submissions", "voice", submission_id)
            for submission_id in _string_list(manifest.get("voice_submissions"))
        ]
        submissions = await asyncio.gather(
            *[
                self._fetch_submission(client, manifest_bucket, default_modality, submission_id)
                for manifest_bucket, default_modality, submission_id in submission_specs
            ]
        )

        raw_records = [
            self._build_raw_record(
                submission_id=submission_id,
                manifest_bucket=manifest_bucket,
                default_modality=default_modality,
                payload=payload,
                fetched_at=fetched_at,
            )
            for manifest_bucket, default_modality, submission_id, payload in submissions
        ]
        raw_records = [record for record in raw_records if record is not None]
        if not raw_records:
            raise ValueError("Could not parse any tau-bench leaderboard submissions.")
        return raw_records

    async def _fetch_submission(
        self,
        client: httpx.AsyncClient,
        manifest_bucket: str,
        default_modality: str,
        submission_id: str,
    ) -> tuple[str, str, str, dict[str, Any]]:
        response = await client.get(_submission_url(submission_id), timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"tau-bench submission {submission_id} was not a JSON object.")
        return manifest_bucket, default_modality, submission_id, payload

    def _build_raw_record(
        self,
        *,
        submission_id: str,
        manifest_bucket: str,
        default_modality: str,
        payload: dict[str, Any],
        fetched_at: str,
    ) -> RawSourceRecord | None:
        modality = _modality(payload, default_modality)
        domain_map = VOICE_DOMAINS if modality == "voice" else TEXT_DOMAINS
        domain_metrics = _domain_metrics(payload.get("results"), domain_map)
        if not domain_metrics:
            return None

        expected_domain_count = len(domain_map)
        complete_domain_set = len(domain_metrics) == expected_domain_count
        single_model = _is_single_model_submission(payload)
        submission_type = str(payload.get("submission_type") or "standard").strip().lower() or "standard"
        model_name = first_non_empty(payload.get("model_name"), submission_id)
        model_organization = first_non_empty(payload.get("model_organization"))
        voice_config = payload.get("voice_config") if isinstance(payload.get("voice_config"), dict) else {}
        methodology = payload.get("methodology") if isinstance(payload.get("methodology"), dict) else {}
        verification = methodology.get("verification") if isinstance(methodology.get("verification"), dict) else {}
        mean_benchmark_id, _ = MEAN_BENCHMARKS[modality]
        first_benchmark_id = next(iter(domain_metrics.values()))["benchmark_id"]

        metadata = {
            "submission_id": submission_id,
            "submission_url": _submission_url(submission_id),
            "manifest_url": MANIFEST_URL,
            "manifest_bucket": manifest_bucket,
            "modality": modality,
            "submission_type": submission_type,
            "model_organization": model_organization,
            "submitting_organization": payload.get("submitting_organization"),
            "submission_date": payload.get("submission_date"),
            "evaluation_date": methodology.get("evaluation_date"),
            "tau2_bench_version": methodology.get("tau2_bench_version"),
            "user_simulator": methodology.get("user_simulator"),
            "reasoning_effort": payload.get("reasoning_effort"),
            "voice_config": voice_config,
            "model_release": payload.get("model_release"),
            "references": payload.get("references") or [],
            "trajectories_available": bool(payload.get("trajectories_available")),
            "trajectory_files": payload.get("trajectory_files") or {},
            "verification": verification,
            "verified": _is_verified(payload),
            "single_model_submission": single_model,
            "aggregate_submission": not single_model,
            "self_reported": True,
            "agent_system_evidence": True,
            "complete_domain_set": complete_domain_set,
            "available_domain_count": len(domain_metrics),
            "expected_domain_count": expected_domain_count,
            "domain_metrics": domain_metrics,
            "source_policy": "current_standard_single_model_pass_1",
        }

        raw_model_key = _raw_model_key(model_name, model_organization, voice_config, single_model)
        raw_value = json.dumps(domain_metrics, ensure_ascii=True, sort_keys=True)
        return RawSourceRecord(
            source_id=self.source_id,
            benchmark_id=mean_benchmark_id if complete_domain_set else first_benchmark_id,
            raw_model_name=model_name,
            raw_value=raw_value,
            source_url=_submission_url(submission_id),
            collected_at=fetched_at,
            raw_model_key=raw_model_key,
            payload=payload,
            metadata=metadata,
        )

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []

        for record in raw_records:
            if not bool(record.metadata.get("single_model_submission")):
                continue

            modality = str(record.metadata.get("modality") or "text")
            domain_metrics = record.metadata.get("domain_metrics")
            if not isinstance(domain_metrics, dict):
                try:
                    parsed = json.loads(record.raw_value)
                except json.JSONDecodeError:
                    continue
                domain_metrics = parsed if isinstance(parsed, dict) else {}

            candidates.extend(self._domain_candidates(record, domain_metrics))
            if bool(record.metadata.get("complete_domain_set")):
                mean_candidate = self._mean_candidate(record, domain_metrics, modality)
                if mean_candidate is not None:
                    candidates.append(mean_candidate)

        return candidates

    def _domain_candidates(self, record: RawSourceRecord, domain_metrics: dict[str, Any]) -> list[ScoreCandidate]:
        candidates: list[ScoreCandidate] = []
        for metric in domain_metrics.values():
            if not isinstance(metric, dict):
                continue
            value = safe_float(metric.get("pass_1"))
            benchmark_id = str(metric.get("benchmark_id") or "").strip()
            if value is None or not benchmark_id:
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
                    source_type="secondary",
                    verified=bool(record.metadata.get("verified")),
                    notes=(
                        f"Official tau-bench {record.metadata.get('modality')} "
                        f"{metric.get('label') or metric.get('domain')} pass^1 score from "
                        f"{record.metadata.get('submission_id')}."
                    ),
                    metadata={
                        **record.metadata,
                        "benchmark_id": benchmark_id,
                        "metric": metric,
                    },
                )
            )
        return candidates

    def _mean_candidate(
        self,
        record: RawSourceRecord,
        domain_metrics: dict[str, Any],
        modality: str,
    ) -> ScoreCandidate | None:
        domain_map = VOICE_DOMAINS if modality == "voice" else TEXT_DOMAINS
        values: list[float] = []
        for domain in domain_map:
            metric = domain_metrics.get(domain)
            if not isinstance(metric, dict):
                return None
            value = safe_float(metric.get("pass_1"))
            if value is None:
                return None
            values.append(value)

        mean_value = sum(values) / len(values)
        benchmark_id, label = MEAN_BENCHMARKS[modality]
        return ScoreCandidate(
            source_id=self.source_id,
            benchmark_id=benchmark_id,
            raw_model_name=record.raw_model_name,
            raw_model_key=record.raw_model_key or record.raw_model_name,
            value=mean_value,
            raw_value=_format_value(mean_value),
            source_url=record.source_url,
            collected_at=record.collected_at,
            source_type="secondary",
            verified=bool(record.metadata.get("verified")),
            notes=(
                f"Official tau-bench {label.lower()} pass^1 score across the complete "
                f"{modality} domain set from {record.metadata.get('submission_id')}."
            ),
            metadata={
                **record.metadata,
                "benchmark_id": benchmark_id,
                "metric": {
                    "label": label,
                    "domains": list(domain_map),
                    "pass_1": mean_value,
                },
            },
        )


def _submission_url(submission_id: str) -> str:
    return f"{BASE_URL}/{submission_id}/submission.json"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _modality(payload: dict[str, Any], default_modality: str) -> str:
    modality = str(payload.get("modality") or default_modality or "text").strip().lower()
    return "voice" if modality == "voice" else "text"


def _domain_metrics(results: Any, domain_map: dict[str, tuple[str, str]]) -> dict[str, dict[str, Any]]:
    if not isinstance(results, dict):
        return {}

    metrics: dict[str, dict[str, Any]] = {}
    for domain, (benchmark_id, label) in domain_map.items():
        result = results.get(domain)
        if not isinstance(result, dict):
            continue
        pass_1 = safe_float(result.get("pass_1"))
        if pass_1 is None:
            continue

        metrics[domain] = {
            "domain": domain,
            "benchmark_id": benchmark_id,
            "label": label,
            "pass_1": pass_1,
            "pass_2": safe_float(result.get("pass_2")),
            "pass_3": safe_float(result.get("pass_3")),
            "pass_4": safe_float(result.get("pass_4")),
            "cost": safe_float(result.get("cost")),
            "retrieval_config": result.get("retrieval_config"),
        }
    return metrics


def _is_single_model_submission(payload: dict[str, Any]) -> bool:
    submission_type = str(payload.get("submission_type") or "standard").strip().lower()
    if submission_type != "standard":
        return False
    model_organization = str(payload.get("model_organization") or "").strip().lower()
    if model_organization in {"multiple providers", "multiple"}:
        return False
    voice_config = payload.get("voice_config") if isinstance(payload.get("voice_config"), dict) else {}
    provider = str(voice_config.get("provider") or "").strip().lower()
    model = str(voice_config.get("model") or "").strip().lower()
    if provider == "cascaded" or model == "stt-llm-tts":
        return False
    return bool(str(payload.get("model_name") or "").strip())


def _is_verified(payload: dict[str, Any]) -> bool:
    methodology = payload.get("methodology") if isinstance(payload.get("methodology"), dict) else {}
    verification = methodology.get("verification") if isinstance(methodology.get("verification"), dict) else {}
    return (
        bool(payload.get("trajectories_available"))
        and verification.get("modified_prompts") is False
        and verification.get("omitted_questions") is False
    )


def _raw_model_key(
    model_name: str,
    model_organization: str,
    voice_config: dict[str, Any],
    single_model: bool,
) -> str:
    if not single_model:
        return model_name
    voice_model = first_non_empty(voice_config.get("model"))
    if voice_model:
        return voice_model
    return first_non_empty(model_name, f"{model_organization}/{model_name}")


def _format_value(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
