"""Benchmark-owned score presentation and within-catalog comparison context.

This module deliberately keeps benchmark semantics out of the browser.  The
registry is exhaustive for active seed benchmarks and the comparison index is
built in one pass over already-loaded models, avoiding per-score database work.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import threading
from typing import Any, Iterable, Mapping, Sequence

from .seed_data import BENCHMARKS, INTERNAL_VIEW_BENCHMARK_ID

ALL_MODEL_ROLES = (
    "generator",
    "embedding",
    "reranker",
    "multimodal_embedding",
    "speech_to_text",
    "text_to_speech",
)
GENERATOR_ROLES = ("generator",)
ROLE_DEFAULT_BENCHMARKS: dict[str, tuple[str, ...]] = {
    "embedding": ("mteb_retrieval", "mteb_retrieval_reranking", "rteb_finance"),
    "reranker": ("mteb_reranking", "mteb_retrieval_reranking"),
    "speech_to_text": (
        "asr_english_short_wer",
        "asr_multilingual_wer",
        "asr_longform_wer",
        "asr_realtime_factor",
    ),
    "text_to_speech": (
        "aa_tts_quality_elo",
        "aa_tts_generation_time",
        "aa_tts_price_per_1m_chars",
    ),
    "multimodal_embedding": (),
}


@dataclass(frozen=True, slots=True)
class BenchmarkPolicy:
    value_kind: str
    unit: str | None
    precision: int
    higher_is_better: bool
    valid_min: float | None
    valid_max: float | None
    roles: tuple[str, ...]
    evidence_unit: str
    evidence_field: str = "observation_count"
    comparison_dimensions: tuple[str, ...] = ()
    strict_requires_metadata: bool = False
    allow_comparison: bool = True
    display_scale: float = 1.0
    system_effect_warning: str | None = None

    def presentation(self) -> dict[str, Any]:
        return {
            "value_kind": self.value_kind,
            "unit": self.unit,
            "precision": self.precision,
            "direction": "higher" if self.higher_is_better else "lower",
            "direction_label": "Higher is better" if self.higher_is_better else "Lower is better",
            "valid_min": self.valid_min,
            "valid_max": self.valid_max,
            "roles": list(self.roles),
            "evidence_unit": self.evidence_unit,
            "comparison_dimensions": list(self.comparison_dimensions),
            "comparison_enabled": self.allow_comparison,
        }


def _build_policy_registry() -> dict[str, BenchmarkPolicy]:
    policies: dict[str, BenchmarkPolicy] = {}

    def register(ids: Sequence[str], **kwargs: Any) -> None:
        policy = BenchmarkPolicy(**kwargs)
        for benchmark_id in ids:
            if benchmark_id in policies:
                raise ValueError(f"Duplicate benchmark presentation policy: {benchmark_id}")
            policies[benchmark_id] = policy

    register(
        [INTERNAL_VIEW_BENCHMARK_ID],
        value_kind="score",
        unit="points",
        precision=1,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=ALL_MODEL_ROLES,
        evidence_unit="assessment",
        allow_comparison=False,
    )
    register(
        ["aa_intelligence"],
        value_kind="index",
        unit="points",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="observation",
    )

    percent_high = [
        "aa_ifbench",
        "gpqa_diamond",
        "mmmu",
        "mmmu_test",
        "mmmu_pro",
        "livecodebench_codegen",
        "ifeval",
        "rag_groundedness",
        "rag_answer_rate",
    ]
    register(
        percent_high,
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="observation",
    )

    register(
        [
            "swebench_verified",
            "swebench_full",
            "swebench_lite",
            "swebench_multilingual",
            "swebench_multimodal",
        ],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="issue",
        comparison_dimensions=(
            "source_metadata.split",
            "source_metadata.system_attempts",
            "source_metadata.os_model",
            "source_metadata.os_system",
            "source_metadata.single_model_submission",
        ),
        strict_requires_metadata=True,
        system_effect_warning="This benchmark includes system or scaffold effects; treat it as model-plus-system evidence.",
    )
    register(
        ["terminal_bench"],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="task",
        comparison_dimensions=(
            "source_metadata.agent",
            "source_metadata.agent_name",
            "source_metadata.agent_version",
            "source_metadata.integration_method",
            "source_metadata.leaderboard_date",
        ),
        strict_requires_metadata=True,
        system_effect_warning="This benchmark includes system or scaffold effects; treat it as model-plus-system evidence.",
    )
    register(
        [
            "livebench_overall",
            "livebench_reasoning",
            "livebench_coding",
            "livebench_agentic_coding",
            "livebench_math",
            "livebench_data_analysis",
            "livebench_language",
            "livebench_instruction_following",
        ],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="task",
        comparison_dimensions=("source_metadata.release", "source_metadata.release_date"),
        strict_requires_metadata=True,
    )
    register(
        ["bfcl_overall"],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="test case",
    )
    register(
        [
            "bigcodebench_full",
            "bigcodebench_full_instruct",
            "bigcodebench_full_complete",
            "bigcodebench_hard",
            "bigcodebench_hard_instruct",
            "bigcodebench_hard_complete",
        ],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="problem",
        comparison_dimensions=("source_metadata.version", "source_metadata.dataset_revision"),
        strict_requires_metadata=True,
    )
    register(
        [
            "helm_capabilities_mean",
            "helm_capabilities_mmlu_pro",
            "helm_capabilities_gpqa",
            "helm_capabilities_ifeval",
            "helm_capabilities_wildbench",
            "helm_capabilities_omni_math",
        ],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="run",
        comparison_dimensions=("source_metadata.release", "source_metadata.dataset_revision"),
        strict_requires_metadata=True,
    )
    register(
        [
            "taubench_text_mean",
            "taubench_text_airline",
            "taubench_text_retail",
            "taubench_text_telecom",
            "taubench_text_banking_knowledge",
            "taubench_voice_mean",
            "taubench_voice_airline",
            "taubench_voice_retail",
            "taubench_voice_telecom",
        ],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="task",
        comparison_dimensions=(
            "source_metadata.benchmark_version",
            "source_metadata.agent",
            "source_metadata.environment",
        ),
        strict_requires_metadata=True,
        system_effect_warning="This benchmark includes agent-system effects; treat it as model-plus-system evidence.",
    )

    register(
        [
            "rag_hallucination_rate",
            "rag_task_faithfulness",
            "faithjudge_faithbench_summarization",
            "faithjudge_ragtruth_summarization",
            "faithjudge_ragtruth_question_answering",
            "faithjudge_ragtruth_data_to_text",
            "ragtruth_hallucination_rate",
            "ragtruth_summary_hallucination_rate",
            "ragtruth_qa_hallucination_rate",
            "ragtruth_data_to_text_hallucination_rate",
        ],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=False,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="example",
    )

    mteb_dimensions = (
        "source_metadata.task_category",
        "source_metadata.task_categories",
        "source_metadata.task_names",
        "source_metadata.languages",
        "source_metadata.revision",
        "source_metadata.dataset_revision",
        "source_metadata.mteb_version",
        "source_metadata.splits",
        "source_metadata.subsets",
    )
    register(
        ["mteb_retrieval"],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=("embedding",),
        evidence_unit="task result",
        comparison_dimensions=mteb_dimensions,
        strict_requires_metadata=True,
    )
    register(
        ["mteb_reranking"],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=("reranker",),
        evidence_unit="task result",
        comparison_dimensions=mteb_dimensions,
        strict_requires_metadata=True,
    )
    register(
        ["mteb_retrieval_reranking"],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=("embedding", "reranker"),
        evidence_unit="task result",
        comparison_dimensions=mteb_dimensions,
        strict_requires_metadata=True,
    )
    register(
        ["rteb_finance"],
        value_kind="percentage",
        unit="%",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=("embedding",),
        evidence_unit="task result",
        comparison_dimensions=mteb_dimensions,
        strict_requires_metadata=True,
    )

    register(
        ["asr_english_short_wer", "asr_multilingual_wer", "asr_longform_wer"],
        value_kind="word_error_rate",
        unit="%",
        precision=2,
        higher_is_better=False,
        valid_min=0.0,
        valid_max=None,
        roles=("speech_to_text",),
        evidence_unit="dataset",
    )
    register(
        ["asr_realtime_factor"],
        value_kind="realtime_factor",
        unit="× real time",
        precision=2,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=None,
        roles=("speech_to_text",),
        evidence_unit="dataset",
    )
    register(
        ["aa_tts_quality_elo"],
        value_kind="elo",
        unit="Elo",
        precision=0,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=None,
        roles=("text_to_speech",),
        evidence_unit="vote",
        evidence_field="vote_count",
    )
    register(
        ["aa_tts_generation_time"],
        value_kind="duration",
        unit="s / ~500 characters",
        precision=2,
        higher_is_better=False,
        valid_min=0.0,
        valid_max=None,
        roles=("text_to_speech",),
        evidence_unit="observation",
    )
    register(
        ["aa_tts_price_per_1m_chars"],
        value_kind="currency",
        unit="USD / 1M characters",
        precision=4,
        higher_is_better=False,
        valid_min=0.0,
        valid_max=None,
        roles=("text_to_speech",),
        evidence_unit="endpoint",
    )

    register(
        ["ailuminate", "ailuminate_en_us", "ailuminate_fr_fr", "ailuminate_ai_systems", "ailuminate_bare_models"],
        value_kind="grade",
        unit="points",
        precision=1,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=100.0,
        roles=GENERATOR_ROLES,
        evidence_unit="assessment",
    )
    register(
        ["aa_ifbench_output_tokens"],
        value_kind="count",
        unit="tokens / task",
        precision=0,
        higher_is_better=False,
        valid_min=0.0,
        valid_max=None,
        roles=GENERATOR_ROLES,
        evidence_unit="task",
    )
    register(
        ["aa_ifbench_cost"],
        value_kind="currency",
        unit="USD / task",
        precision=4,
        higher_is_better=False,
        valid_min=0.0,
        valid_max=None,
        roles=GENERATOR_ROLES,
        evidence_unit="task",
    )
    register(
        ["aa_ifbench_time"],
        value_kind="duration",
        unit="min / task",
        precision=2,
        higher_is_better=False,
        valid_min=0.0,
        valid_max=None,
        roles=GENERATOR_ROLES,
        evidence_unit="task",
    )
    register(
        ["aa_speed"],
        value_kind="throughput",
        unit="tokens / sec",
        precision=1,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=None,
        roles=GENERATOR_ROLES,
        evidence_unit="endpoint",
    )
    register(
        ["aa_cost"],
        value_kind="currency",
        unit="USD / 1M tokens",
        precision=4,
        higher_is_better=False,
        valid_min=0.0,
        valid_max=None,
        roles=GENERATOR_ROLES,
        evidence_unit="endpoint",
    )

    arena_dimensions = (
        "category",
        "style_control",
        "methodology",
        "source_metadata.dataset_revision",
        "source_metadata.dataset_split",
    )
    register(
        [
            "chatbot_arena",
            "chatbot_arena_text_raw",
            "chatbot_arena_coding",
            "chatbot_arena_instruction_following",
            "chatbot_arena_multi_turn",
            "chatbot_arena_expert",
            "chatbot_arena_finance_business",
            "chatbot_arena_legal_government",
            "chatbot_arena_software_it",
            "chatbot_arena_webdev",
            "chatbot_arena_vision",
            "chatbot_arena_document",
            "chatbot_arena_search",
        ],
        value_kind="elo",
        unit="Arena score",
        precision=0,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=None,
        roles=GENERATOR_ROLES,
        evidence_unit="vote",
        evidence_field="vote_count",
        comparison_dimensions=arena_dimensions,
        strict_requires_metadata=True,
    )
    register(
        ["chatbot_arena_agent"],
        value_kind="fraction",
        unit="%",
        precision=1,
        higher_is_better=True,
        valid_min=0.0,
        valid_max=1.0,
        roles=GENERATOR_ROLES,
        evidence_unit="session",
        evidence_field="session_count",
        comparison_dimensions=arena_dimensions,
        strict_requires_metadata=True,
        display_scale=100.0,
        system_effect_warning="This benchmark includes agent-system effects; treat it as model-plus-system evidence.",
    )
    return policies


BENCHMARK_POLICIES = _build_policy_registry()


def validate_policy_registry(benchmarks: Iterable[Mapping[str, Any]]) -> None:
    active = {str(item["id"]): item for item in benchmarks if item.get("active", 1)}
    missing = sorted(set(active) - set(BENCHMARK_POLICIES))
    extra = sorted(set(BENCHMARK_POLICIES) - set(active))
    if missing or extra:
        raise ValueError(f"Benchmark policy registry mismatch; missing={missing}, extra={extra}")
    for benchmark_id, benchmark in active.items():
        policy = BENCHMARK_POLICIES[benchmark_id]
        if policy.higher_is_better != bool(benchmark.get("higher_is_better", 1)):
            raise ValueError(f"Benchmark direction mismatch for {benchmark_id}")
        if not policy.roles:
            raise ValueError(f"Benchmark policy has no applicable roles: {benchmark_id}")


validate_policy_registry(BENCHMARKS)


def format_score_display(
    policy: BenchmarkPolicy,
    raw_value: float,
    raw_label: Any = None,
) -> dict[str, Any]:
    value = float(raw_value) * policy.display_scale
    number = f"{value:,.{policy.precision}f}"
    if policy.value_kind == "grade" and _non_numeric_label(raw_label) is not None:
        formatted = str(_non_numeric_label(raw_label))
    elif policy.value_kind in {"percentage", "fraction", "word_error_rate"}:
        formatted = f"{number}%"
    elif policy.value_kind == "currency":
        basis = (policy.unit or "USD").removeprefix("USD").strip()
        formatted = f"${number}{f' {basis}' if basis else ''}"
    elif policy.value_kind == "realtime_factor":
        formatted = f"{number}×"
    elif policy.value_kind in {"duration", "throughput", "count"}:
        formatted = f"{number} {policy.unit}" if policy.unit else number
    else:
        formatted = number
    return {
        "value": round(value, max(policy.precision, 4)) if policy.precision else float(round(value)),
        "formatted": formatted,
        "unit": policy.unit,
        "precision": policy.precision,
        "direction": "higher" if policy.higher_is_better else "lower",
        "direction_label": "Higher is better" if policy.higher_is_better else "Lower is better",
    }


def _non_numeric_label(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        float(text.replace(",", ""))
    except ValueError:
        return text
    return None


def _roles(value: Any) -> set[str]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            decoded = [value]
        value = decoded
    if not isinstance(value, Iterable) or isinstance(value, (bytes, Mapping)):
        return {"generator"}
    roles = {str(item).strip() for item in value if str(item).strip()}
    return roles or {"generator"}


def _score_value(score: Mapping[str, Any]) -> float | None:
    try:
        value = float(score.get("value"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _valid_score(policy: BenchmarkPolicy, score: Mapping[str, Any]) -> bool:
    if _transport_sanitized_invalid_score(score):
        return False
    value = _score_value(score)
    if value is None:
        return False
    if policy.valid_min is not None and value < policy.valid_min:
        return False
    if policy.valid_max is not None and value > policy.valid_max:
        return False
    return True


def _transport_sanitized_invalid_score(score: Mapping[str, Any]) -> bool:
    display = score.get("display")
    comparison = score.get("comparison")
    return (
        score.get("value") is None
        and isinstance(display, Mapping)
        and display.get("formatted") == "Data check needed"
        and isinstance(comparison, Mapping)
        and comparison.get("status") == "invalid"
    )


def _evidence_count(score: Mapping[str, Any], policy: BenchmarkPolicy) -> int | None:
    fields = (policy.evidence_field, "observation_count", "vote_count", "session_count")
    for field in dict.fromkeys(fields):
        value = score.get(field)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return None


def _evidence(score: Mapping[str, Any], policy: BenchmarkPolicy) -> dict[str, Any]:
    count = _evidence_count(score, policy)
    if count is None:
        label = "Evidence count unavailable"
    else:
        unit = policy.evidence_unit if count == 1 else _pluralize(policy.evidence_unit)
        label = f"{count:,} {unit}"
    return {"count": count, "unit": policy.evidence_unit, "label": label}


def _pluralize(unit: str) -> str:
    if unit.endswith("case"):
        return f"{unit}s"
    if unit.endswith("result"):
        return f"{unit}s"
    if unit.endswith("y") and not unit.endswith(("ay", "ey")):
        return f"{unit[:-1]}ies"
    return unit if unit.endswith("s") else f"{unit}s"


def _path_value(score: Mapping[str, Any], path: str) -> Any:
    current: Any = score
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _signature_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _signature_value(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple, set)):
        normalized = [_signature_value(item) for item in value]
        return tuple(sorted((item for item in normalized if item is not None), key=repr))
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return str(value).strip() or None


def _evaluation_signature(score: Mapping[str, Any], policy: BenchmarkPolicy) -> tuple[tuple[str, Any], ...]:
    values: list[tuple[str, Any]] = []
    for dimension in policy.comparison_dimensions:
        value = _signature_value(_path_value(score, dimension))
        if value is not None and value != ():
            values.append((dimension, value))
    return tuple(values)


def evaluation_signature(
    benchmark_id: str,
    score: Mapping[str, Any],
) -> tuple[tuple[str, Any], ...]:
    """Return the policy-owned, hashable evaluation signature for a score."""
    policy = BENCHMARK_POLICIES.get(str(benchmark_id))
    return _evaluation_signature(score, policy) if policy is not None else ()


def _configuration(score: Mapping[str, Any]) -> tuple[str | None, str | None]:
    key = str(score.get("configuration_key") or "").strip() or None
    value = str(score.get("configuration_value") or "").strip() or None
    return key, value


def _timestamp(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def prefer_score_candidate(
    candidate: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    candidate_model_id: str = "",
    current_model_id: str = "",
) -> bool:
    """Return whether candidate wins provenance-first canonical arbitration."""
    candidate_verified = bool(candidate.get("verified", False))
    current_verified = bool(current.get("verified", False))
    if candidate_verified != current_verified:
        return candidate_verified
    if candidate_verified:
        source_rank = {"primary": 0, "secondary": 1, "manual": 2}
        candidate_source = source_rank.get(str(candidate.get("source_type") or "primary"), 3)
        current_source = source_rank.get(str(current.get("source_type") or "primary"), 3)
        if candidate_source != current_source:
            return candidate_source < current_source
    candidate_time = _timestamp(candidate.get("collected_at"))
    current_time = _timestamp(current.get("collected_at"))
    if candidate_time != current_time:
        return candidate_time > current_time
    candidate_evidence = max(
        int(candidate.get(field) or 0) for field in ("observation_count", "vote_count", "session_count")
    )
    current_evidence = max(
        int(current.get(field) or 0) for field in ("observation_count", "vote_count", "session_count")
    )
    if candidate_evidence != current_evidence:
        return candidate_evidence > current_evidence
    return str(candidate_model_id) < str(current_model_id)


@dataclass(slots=True)
class _Observation:
    model_id: str
    model_name: str
    canonical_id: str
    benchmark_id: str
    roles: frozenset[str]
    score: dict[str, Any]
    configuration: tuple[str | None, str | None]
    signature: tuple[tuple[str, Any], ...]
    primary_score: bool

    @property
    def value(self) -> float:
        return float(self.score["value"])


@dataclass(frozen=True, slots=True)
class _CohortStats:
    sorted_values: tuple[float, ...]
    distribution: dict[str, float]


class BenchmarkComparisonIndex:
    def __init__(self, models: list[dict[str, Any]], benchmarks: Mapping[str, Mapping[str, Any]]) -> None:
        self.benchmarks = benchmarks
        self.observations: list[_Observation] = []
        self.eligible: dict[str, dict[str, set[str]]] = {
            benchmark_id: {} for benchmark_id in BENCHMARK_POLICIES
        }
        self._by_benchmark: dict[str, list[_Observation]] = {}
        self._by_strict: dict[
            tuple[str, tuple[str | None, str | None], tuple[tuple[str, Any], ...]],
            list[_Observation],
        ] = {}
        self._summary: dict[str, dict[str, _Observation]] = {}
        self._cohort_groups: dict[tuple[Any, ...], dict[str, _Observation]] = {}
        self._cohort_stats: dict[tuple[Any, ...], _CohortStats] = {}
        self._position_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._mixed_signature_cache: dict[tuple[str, tuple[str, ...]], bool] = {}
        self._conflicts: set[tuple[str, str]] = set()
        self._build(models)

    def _build(self, models: list[dict[str, Any]]) -> None:
        seen_observations: set[tuple[Any, ...]] = set()
        for model in models:
            if not bool(model.get("active", True)):
                continue
            model_id = str(model.get("id") or "")
            if not model_id:
                continue
            canonical_id = str(model.get("canonical_model_id") or model_id)
            model_roles = frozenset(_roles(model.get("model_roles", model.get("model_roles_json"))))
            for benchmark_id, policy in BENCHMARK_POLICIES.items():
                if model_roles.intersection(policy.roles):
                    self.eligible[benchmark_id].setdefault(canonical_id, set()).update(model_roles)

            entries: list[tuple[str, dict[str, Any], bool]] = []
            for benchmark_id, score in (model.get("scores") or {}).items():
                if isinstance(score, dict):
                    entries.append((str(benchmark_id), score, True))
            for score in model.get("score_configurations") or []:
                if isinstance(score, dict) and score.get("benchmark_id"):
                    entries.append((str(score["benchmark_id"]), score, False))

            for benchmark_id, score, primary_score in entries:
                policy = BENCHMARK_POLICIES.get(benchmark_id)
                if policy is None or not model_roles.intersection(policy.roles) or not _valid_score(policy, score):
                    continue
                observation_key = (
                    model_id,
                    benchmark_id,
                    _configuration(score),
                    str(score.get("collected_at") or ""),
                    float(score["value"]),
                    str(score.get("raw_value") or ""),
                    str(score.get("source_type") or ""),
                    bool(score.get("verified", False)),
                    score.get("observation_count"),
                    score.get("vote_count"),
                    score.get("session_count"),
                    json.dumps(score.get("source_metadata") or {}, sort_keys=True, default=str),
                )
                if observation_key in seen_observations:
                    continue
                seen_observations.add(observation_key)
                observation = _Observation(
                    model_id=model_id,
                    model_name=str(model.get("name") or model_id),
                    canonical_id=canonical_id,
                    benchmark_id=benchmark_id,
                    roles=model_roles,
                    score=score,
                    configuration=_configuration(score),
                    signature=_evaluation_signature(score, policy),
                    primary_score=primary_score,
                )
                self.observations.append(observation)
                self._by_benchmark.setdefault(benchmark_id, []).append(observation)
                self._by_strict.setdefault(
                    (benchmark_id, observation.configuration, observation.signature), []
                ).append(observation)
                if primary_score:
                    self._add_winner(self._summary.setdefault(benchmark_id, {}), observation)

    def _add_winner(
        self,
        group: dict[str, _Observation],
        candidate: _Observation,
        *,
        record_conflict: bool = False,
    ) -> None:
        current = group.get(candidate.canonical_id)
        if current is None:
            group[candidate.canonical_id] = candidate
            return
        if record_conflict and (
            candidate.model_id != current.model_id
            and candidate.configuration == current.configuration
            and candidate.signature == current.signature
            and not math.isclose(candidate.value, current.value, rel_tol=0.0, abs_tol=1e-12)
        ):
            self._conflicts.add((candidate.benchmark_id, candidate.canonical_id))
        if prefer_score_candidate(
            candidate.score,
            current.score,
            candidate_model_id=candidate.model_id,
            current_model_id=current.model_id,
        ):
            group[candidate.canonical_id] = candidate

    @staticmethod
    def _compatible_roles(model_roles: frozenset[str], policy: BenchmarkPolicy) -> tuple[str, ...]:
        return tuple(sorted(model_roles.intersection(policy.roles)))

    def _cohort_group(
        self,
        *,
        benchmark_id: str,
        compatible_roles: tuple[str, ...],
        configuration: tuple[str | None, str | None] | None = None,
        signature: tuple[tuple[str, Any], ...] | None = None,
    ) -> tuple[tuple[Any, ...], dict[str, _Observation]]:
        kind = "broad" if configuration is None or signature is None else "strict"
        key: tuple[Any, ...] = (
            kind,
            benchmark_id,
            compatible_roles,
            configuration if kind == "strict" else None,
            signature if kind == "strict" else None,
        )
        cached = self._cohort_groups.get(key)
        if cached is not None:
            return key, cached
        role_set = set(compatible_roles)
        source = (
            self._by_benchmark.get(benchmark_id, [])
            if kind == "broad"
            else self._by_strict.get((benchmark_id, configuration, signature), [])
        )
        group: dict[str, _Observation] = {}
        for observation in source:
            if not role_set.intersection(observation.roles):
                continue
            self._add_winner(group, observation, record_conflict=kind == "strict")
        self._cohort_groups[key] = group
        return key, group

    def presentation(self, benchmark_id: str) -> dict[str, Any]:
        return BENCHMARK_POLICIES[benchmark_id].presentation()

    def relevant_benchmark_ids(self, model: Mapping[str, Any]) -> list[str]:
        model_roles = _roles(model.get("model_roles", model.get("model_roles_json")))
        relevant: set[str] = set()
        if "generator" in model_roles:
            relevant.update(
                benchmark_id
                for benchmark_id, policy in BENCHMARK_POLICIES.items()
                if policy.allow_comparison
                and "generator" in policy.roles
                and int((self.benchmarks.get(benchmark_id) or {}).get("tier") or 9) == 1
            )
        for role in model_roles:
            relevant.update(ROLE_DEFAULT_BENCHMARKS.get(role, ()))
        return sorted(
            benchmark_id
            for benchmark_id in relevant
            if benchmark_id in self.benchmarks
            and BENCHMARK_POLICIES[benchmark_id].allow_comparison
        )

    def comparison_for(
        self,
        model: Mapping[str, Any],
        benchmark_id: str,
        score: dict[str, Any],
    ) -> dict[str, Any]:
        policy = BENCHMARK_POLICIES[benchmark_id]
        model_id = str(model.get("id") or "")
        canonical_id = str(model.get("canonical_model_id") or model_id)
        model_roles = frozenset(_roles(model.get("model_roles", model.get("model_roles_json"))))
        compatible_roles = self._compatible_roles(model_roles, policy)
        warnings: list[str] = []
        coverage = self._coverage(benchmark_id, compatible_roles)
        base = {
            "status": "unavailable",
            "strict": None,
            "broad": None,
            "coverage": coverage,
            "warnings": warnings,
            "as_of": str(score.get("collected_at") or "") or None,
            "contributor_model_id": model_id or None,
            "contributor_model_name": str(model.get("name") or model_id) or None,
            "selected_for_entity": True,
        }
        if not policy.allow_comparison:
            warnings.append("Comparison is disabled for internal assessment scores")
            return base
        if not compatible_roles:
            warnings.append("Benchmark is not applicable to this model role")
            return base
        if not _valid_score(policy, score):
            base["status"] = "invalid"
            if _score_value(score) is None or _transport_sanitized_invalid_score(score):
                warnings.append("Data check needed: score is missing, non-numeric, or non-finite")
            else:
                warnings.append("Data check needed: score falls outside this benchmark's valid range")
            return base

        target = _Observation(
            model_id=model_id,
            model_name=str(model.get("name") or model_id),
            canonical_id=canonical_id,
            benchmark_id=benchmark_id,
            roles=model_roles,
            score=score,
            configuration=_configuration(score),
            signature=_evaluation_signature(score, policy),
            primary_score=True,
        )
        strict_group_key, selected_group = self._cohort_group(
            benchmark_id=benchmark_id,
            compatible_roles=compatible_roles,
            configuration=target.configuration,
            signature=target.signature,
        )
        selected = selected_group.get(canonical_id, target)
        selected_for_entity = self._same_observation(selected, target)
        base["selected_for_entity"] = selected_for_entity
        base["contributor_model_id"] = selected.model_id
        base["contributor_model_name"] = selected.model_name
        if not selected_for_entity:
            warnings.append("Another canonical alias is the provenance-selected contribution")

        broad_group_key, broad_group = self._cohort_group(
            benchmark_id=benchmark_id,
            compatible_roles=compatible_roles,
        )
        broad_cohort = self._cohort_with_target(broad_group, selected)
        broad_winner = broad_group.get(canonical_id)
        broad_stats_key = (
            broad_group_key
            if broad_winner is not None and self._same_observation(broad_winner, selected)
            else (*broad_group_key, self._observation_identity(selected))
        )
        base["broad"] = self._position(
            broad_cohort,
            selected,
            policy,
            self._broad_label(policy, compatible_roles),
            broad_stats_key,
        )

        has_strict_metadata = bool(target.signature)
        strict_available = not policy.strict_requires_metadata or has_strict_metadata
        if strict_available:
            strict_cohort = self._cohort_with_target(selected_group, selected)
            base["strict"] = self._position(
                strict_cohort,
                selected,
                policy,
                "Comparable models",
                strict_group_key,
            )
        else:
            warnings.append("Comparable cohort unavailable because evaluation metadata is incomplete")

        if self._mixed_signatures(benchmark_id, compatible_roles):
            warnings.append("Broad cohort mixes evaluation configurations")
        if (benchmark_id, canonical_id) in self._conflicts:
            warnings.append("Canonical aliases report different values; provenance-first result selected")
        if policy.system_effect_warning:
            warnings.append(policy.system_effect_warning)
        if coverage["percent"] is not None and float(coverage["percent"]) < 50.0:
            warnings.append("Low database coverage")

        strict_position = base["strict"]
        if strict_position is not None and int(strict_position["cohort_size"]) >= 5:
            base["status"] = "comparable"
        else:
            base["status"] = "limited"
        cohort_size = int(strict_position["cohort_size"]) if strict_position is not None else len(broad_cohort)
        if cohort_size == 1:
            warnings.append("Only scored comparable model")
        elif 2 <= cohort_size <= 4:
            warnings.append("Very small cohort")
        elif 5 <= cohort_size <= 19:
            warnings.append("Small cohort")
        base["as_of"] = max(
            (str(item.score.get("collected_at") or "") for item in broad_cohort),
            default=str(score.get("collected_at") or ""),
        ) or None
        return base

    def _coverage(self, benchmark_id: str, compatible_roles: tuple[str, ...]) -> dict[str, Any]:
        role_set = set(compatible_roles)
        eligible_count = sum(
            1
            for roles in self.eligible.get(benchmark_id, {}).values()
            if role_set.intersection(roles)
        )
        _key, broad_group = self._cohort_group(
            benchmark_id=benchmark_id,
            compatible_roles=compatible_roles,
        )
        scored_count = len(broad_group)
        percent = round(scored_count / eligible_count * 100.0, 2) if eligible_count else None
        return {
            "scored_count": scored_count,
            "eligible_count": eligible_count,
            "percent": percent,
            "label": f"{scored_count:,} of {eligible_count:,} compatible models scored",
        }

    @staticmethod
    def _cohort_with_target(group: Mapping[str, _Observation], target: _Observation) -> list[_Observation]:
        cohort = [item for canonical_id, item in group.items() if canonical_id != target.canonical_id]
        cohort.append(target)
        return cohort

    @staticmethod
    def _same_observation(left: _Observation, right: _Observation) -> bool:
        return (
            left.model_id == right.model_id
            and left.configuration == right.configuration
            and left.signature == right.signature
            and str(left.score.get("collected_at") or "") == str(right.score.get("collected_at") or "")
            and math.isclose(left.value, right.value, rel_tol=0.0, abs_tol=1e-12)
        )

    @staticmethod
    def _observation_identity(observation: _Observation) -> tuple[Any, ...]:
        return (
            observation.model_id,
            observation.configuration,
            observation.signature,
            str(observation.score.get("collected_at") or ""),
            observation.value,
        )

    def _mixed_signatures(self, benchmark_id: str, compatible_roles: tuple[str, ...]) -> bool:
        cache_key = (benchmark_id, compatible_roles)
        if cache_key in self._mixed_signature_cache:
            return self._mixed_signature_cache[cache_key]
        role_set = set(compatible_roles)
        signatures = {
            (observation.configuration, observation.signature)
            for observation in self._by_benchmark.get(benchmark_id, [])
            if role_set.intersection(observation.roles)
        }
        result = len(signatures) > 1
        self._mixed_signature_cache[cache_key] = result
        return result

    @staticmethod
    def _broad_label(policy: BenchmarkPolicy, compatible_roles: tuple[str, ...]) -> str:
        if len(compatible_roles) == 1:
            labels = {
                "generator": "generative models",
                "embedding": "embeddings",
                "reranker": "rerankers",
                "speech_to_text": "speech-to-text models",
                "text_to_speech": "text-to-speech models",
                "multimodal_embedding": "multimodal embeddings",
            }
            return f"All scored {labels.get(compatible_roles[0], 'compatible models')}"
        return "All scored compatible models"

    def _position(
        self,
        cohort: list[_Observation],
        target: _Observation,
        policy: BenchmarkPolicy,
        cohort_label: str,
        stats_key: tuple[Any, ...],
    ) -> dict[str, Any]:
        cache_key = (stats_key, target.value, policy.higher_is_better, cohort_label)
        cached = self._position_cache.get(cache_key)
        if cached is not None:
            return cached
        stats = self._cohort_stats.get(stats_key)
        if stats is None:
            ordered = tuple(sorted(item.value for item in cohort))
            stats = _CohortStats(
                sorted_values=ordered,
                distribution=_distribution(ordered),
            )
            self._cohort_stats[stats_key] = stats
        values = stats.sorted_values
        target_value = target.value
        left = bisect_left(values, target_value)
        right = bisect_right(values, target_value)
        cohort_size = len(values)
        tied = right - left
        if policy.higher_is_better:
            better = cohort_size - right
            worse = left
        else:
            better = left
            worse = cohort_size - right
        percentile: float | None = None
        if cohort_size >= 5:
            if tied == cohort_size:
                percentile = 50.0
            elif better == 0:
                percentile = 100.0
            elif worse == 0:
                percentile = 0.0
            else:
                percentile = round(100.0 * worse / (better + worse), 2)
        position_band = _position_band(percentile) if cohort_size >= 20 and percentile is not None else None
        result = {
            "rank": better + 1,
            "tie_count": tied,
            "cohort_size": cohort_size,
            "percentile": percentile,
            "distribution": stats.distribution,
            "cohort_label": cohort_label,
            "position_band": position_band,
        }
        self._position_cache[cache_key] = result
        return result

    def benchmark_summary(self, benchmark_id: str) -> dict[str, Any]:
        policy = BENCHMARK_POLICIES[benchmark_id]
        winners = list(self._summary.get(benchmark_id, {}).values())
        values = [item.value for item in winners]
        eligible_count = len(self.eligible.get(benchmark_id, {}))
        scored_count = len(winners)
        coverage_percent = round(scored_count / eligible_count * 100.0, 2) if eligible_count else None
        warnings: list[str] = []
        configurations = {item.configuration for item in winners}
        if len(configurations) > 1:
            warnings.append("Summary mixes configured score variants")
        if not policy.allow_comparison:
            warnings.append("Comparison is disabled for internal assessment scores")
        return {
            "status": "available" if values and policy.allow_comparison else "unavailable",
            "scored_count": scored_count,
            "eligible_count": eligible_count,
            "coverage_percent": coverage_percent,
            "distribution": _distribution(values) if values else None,
            "as_of": max((str(item.score.get("collected_at") or "") for item in winners), default="") or None,
            "warnings": warnings,
        }


def _quantile(sorted_values: list[float], fraction: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _distribution(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(float(value) for value in values)
    return {
        "min": round(ordered[0], 4),
        "p10": round(_quantile(ordered, 0.10), 4),
        "p25": round(_quantile(ordered, 0.25), 4),
        "median": round(_quantile(ordered, 0.50), 4),
        "p75": round(_quantile(ordered, 0.75), 4),
        "p90": round(_quantile(ordered, 0.90), 4),
        "max": round(ordered[-1], 4),
    }


def _position_band(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    if percentile >= 90.0:
        return "Leading"
    if percentile >= 75.0:
        return "Strong"
    if percentile >= 25.0:
        return "Mid-pack"
    if percentile >= 10.0:
        return "Below most"
    return "Trailing"


_CACHE_LOCK = threading.Lock()
_CACHE_FINGERPRINT: str | None = None
_CACHE_INDEX: BenchmarkComparisonIndex | None = None
_CACHE_BUILDS = 0


def _fingerprint(models: list[dict[str, Any]], benchmarks: Mapping[str, Mapping[str, Any]]) -> str:
    payload: list[Any] = []
    for model in sorted(
        models,
        key=lambda item: (str(item.get("id") or ""), str(item.get("name") or "")),
    ):
        model_payload: list[Any] = [
            model.get("id"),
            model.get("name"),
            model.get("canonical_model_id"),
            sorted(_roles(model.get("model_roles", model.get("model_roles_json")))),
            bool(model.get("active", True)),
        ]
        score_rows: list[Any] = []
        for benchmark_id, score in sorted((model.get("scores") or {}).items()):
            if isinstance(score, Mapping):
                score_rows.append(_fingerprint_score(str(benchmark_id), score))
        for score in model.get("score_configurations") or []:
            if isinstance(score, Mapping):
                score_rows.append(_fingerprint_score(str(score.get("benchmark_id") or ""), score))
        model_payload.append(
            sorted(
                score_rows,
                key=lambda item: json.dumps(item, sort_keys=True, default=str, separators=(",", ":")),
            )
        )
        payload.append(model_payload)
    benchmark_payload = sorted(
        (
            benchmark_id,
            bool(item.get("active", True)),
            bool(item.get("higher_is_better", True)),
            item.get("name"),
            item.get("metric"),
            {
                **BENCHMARK_POLICIES[benchmark_id].presentation(),
                "display_scale": BENCHMARK_POLICIES[benchmark_id].display_scale,
                "strict_requires_metadata": BENCHMARK_POLICIES[benchmark_id].strict_requires_metadata,
                "system_effect_warning": BENCHMARK_POLICIES[benchmark_id].system_effect_warning,
            }
            if benchmark_id in BENCHMARK_POLICIES
            else None,
        )
        for benchmark_id, item in benchmarks.items()
    )
    encoded = json.dumps([payload, benchmark_payload], sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint_score(benchmark_id: str, score: Mapping[str, Any]) -> list[Any]:
    return [
        benchmark_id,
        score.get("value"),
        score.get("raw_value"),
        score.get("collected_at"),
        score.get("source_type"),
        bool(score.get("verified", False)),
        score.get("observation_count"),
        score.get("vote_count"),
        score.get("session_count"),
        score.get("configuration_key"),
        score.get("configuration_value"),
        score.get("category"),
        score.get("style_control"),
        score.get("methodology"),
        score.get("source_metadata") or {},
    ]


def get_comparison_index(
    models: list[dict[str, Any]],
    benchmarks: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
) -> BenchmarkComparisonIndex:
    global _CACHE_BUILDS, _CACHE_FINGERPRINT, _CACHE_INDEX
    benchmarks_by_id = (
        {str(item["id"]): item for item in benchmarks}
        if not isinstance(benchmarks, Mapping)
        else benchmarks
    )
    fingerprint = _fingerprint(models, benchmarks_by_id)
    with _CACHE_LOCK:
        if _CACHE_INDEX is not None and _CACHE_FINGERPRINT == fingerprint:
            return _CACHE_INDEX
        _CACHE_INDEX = BenchmarkComparisonIndex(models, benchmarks_by_id)
        _CACHE_FINGERPRINT = fingerprint
        _CACHE_BUILDS += 1
        return _CACHE_INDEX


def enrich_models(
    models: list[dict[str, Any]],
    benchmarks: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    index = get_comparison_index(models, benchmarks)
    for model in models:
        model["review_entity_id"] = str(model.get("canonical_model_id") or model.get("id") or "")
        model["relevant_benchmark_ids"] = index.relevant_benchmark_ids(model)
        for benchmark_id, score in (model.get("scores") or {}).items():
            if not isinstance(score, dict) or benchmark_id not in BENCHMARK_POLICIES:
                continue
            policy = BENCHMARK_POLICIES[benchmark_id]
            value = _score_value(score)
            already_sanitized = _transport_sanitized_invalid_score(score)
            if value is not None and not already_sanitized:
                score["display"] = format_score_display(policy, value, score.get("raw_value"))
            score["evidence"] = _evidence(score, policy)
            score["comparison"] = index.comparison_for(model, benchmark_id, score)
            _sanitize_invalid_score_for_transport(score, policy, force=already_sanitized)
        for score in model.get("score_configurations") or []:
            if not isinstance(score, dict):
                continue
            benchmark_id = str(score.get("benchmark_id") or "")
            if benchmark_id not in BENCHMARK_POLICIES:
                continue
            policy = BENCHMARK_POLICIES[benchmark_id]
            value = _score_value(score)
            already_sanitized = _transport_sanitized_invalid_score(score)
            if value is not None and not already_sanitized:
                score["display"] = format_score_display(policy, value, score.get("raw_value"))
            score["evidence"] = _evidence(score, policy)
            score["comparison"] = index.comparison_for(model, benchmark_id, score)
            _sanitize_invalid_score_for_transport(score, policy, force=already_sanitized)
    return models


def _sanitize_invalid_score_for_transport(
    score: dict[str, Any],
    policy: BenchmarkPolicy,
    *,
    force: bool = False,
) -> None:
    """Keep invalid evidence visible without emitting non-JSON numeric values."""
    raw_value = score.get("value")
    try:
        numeric_value = float(raw_value)
    except (TypeError, ValueError):
        numeric_value = math.nan
    if math.isfinite(numeric_value) and not force:
        comparison = score.get("comparison")
        display = score.get("display")
        if (
            isinstance(comparison, Mapping)
            and comparison.get("status") == "invalid"
            and isinstance(display, dict)
        ):
            display["formatted"] = "Data check needed"
        return

    if not str(score.get("raw_value") or "").strip():
        if math.isnan(numeric_value):
            score["raw_value"] = "NaN"
        elif numeric_value > 0:
            score["raw_value"] = "Infinity"
        else:
            score["raw_value"] = "-Infinity"

    # Non-finite IEEE values cannot be represented in strict JSON. Preserve
    # the source text in raw_value and expose a null measurement explicitly.
    score["value"] = None
    score["display"] = {
        "value": None,
        "formatted": "Data check needed",
        "unit": policy.unit,
        "precision": policy.precision,
        "direction": "higher" if policy.higher_is_better else "lower",
        "direction_label": "Higher is better" if policy.higher_is_better else "Lower is better",
    }
    comparison = score.get("comparison")
    if isinstance(comparison, dict):
        comparison["status"] = "invalid"
        warnings = comparison.setdefault("warnings", [])
        warning = "Stored score is non-numeric or non-finite; value was sanitized for JSON transport"
        if warning not in warnings:
            warnings.append(warning)


def invalidate_comparison_cache() -> None:
    global _CACHE_FINGERPRINT, _CACHE_INDEX
    with _CACHE_LOCK:
        _CACHE_FINGERPRINT = None
        _CACHE_INDEX = None


def comparison_cache_info() -> dict[str, Any]:
    with _CACHE_LOCK:
        return {
            "cached": _CACHE_INDEX is not None,
            "builds": _CACHE_BUILDS,
            "cohort_stats": len(_CACHE_INDEX._cohort_stats) if _CACHE_INDEX is not None else 0,
            "positions": len(_CACHE_INDEX._position_cache) if _CACHE_INDEX is not None else 0,
        }


__all__ = [
    "BENCHMARK_POLICIES",
    "BenchmarkComparisonIndex",
    "BenchmarkPolicy",
    "comparison_cache_info",
    "enrich_models",
    "evaluation_signature",
    "format_score_display",
    "get_comparison_index",
    "invalidate_comparison_cache",
    "prefer_score_candidate",
    "validate_policy_registry",
]
