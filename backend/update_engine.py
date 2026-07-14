"""Update orchestration and API-facing read helpers for Phase 1 ingestion."""

from __future__ import annotations

import asyncio
import json
import re
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import httpx
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .database import (
    benchmarks as benchmarks_table,
    fetch_all,
    fetch_one,
    get_connection,
    get_engine,
    init_db,
    model_duplicate_overrides as model_duplicate_overrides_table,
    model_inference_destinations as model_inference_destinations_table,
    model_identity_overrides as model_identity_overrides_table,
    model_market_snapshots as model_market_snapshots_table,
    model_source_listings as model_source_listings_table,
    model_use_case_inference_approvals as model_use_case_inference_approvals_table,
    model_use_case_approvals as model_use_case_approvals_table,
    model_use_case_recommendation_proposals as model_use_case_recommendation_proposals_table,
    models as models_table,
    providers as providers_table,
    raw_source_records as raw_source_records_table,
    scores as scores_table,
    source_runs as source_runs_table,
    update_log as update_log_table,
    use_case_benchmark_weights as use_case_benchmark_weights_table,
    utc_now_iso,
)
from . import model_card_refresh, model_discovery, openrouter_metadata, provider_catalogs, ranking_views, update_orchestration
from .audit_engine import get_audit_run, get_audit_summary, run_audit
from .inference_catalog import (
    attach_inference_catalog,
    load_authoritative_destination_ids,
    load_synced_inference_catalog,
)
from .inference_locations import get_inference_country_from_region, inference_location_key, sort_inference_countries
from .model_curation import (
    apply_model_curation_baseline,
    build_model_curation_match_key,
    export_model_curation_baseline,
)
from .model_licenses import (
    LICENSE_POLICY_COMMERCIAL_BLOCKED,
    apply_inferred_model_licenses,
    apply_model_license_baseline,
    build_license_policy_payload,
)
from .model_provenance import (
    PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED,
    build_provenance_policy_payload,
)
from .model_taxonomy import ModelIdentity, infer_model_identity
from .name_resolution import build_model_lookup, name_signatures, normalize_text, resolve_model_name
from .seed_data import (
    INTERNAL_VIEW_BENCHMARK_ID,
    USE_CASES,
    apply_provider_origin_baseline,
    canonical_provider_name,
    derive_provider_origin_fields,
    export_provider_origin_baseline,
    normalize_origin_countries,
    provider_id_from_name,
    seed_reference_data,
)
from .sources import get_source_adapters
from .sources.base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, SourceFetchResult

ENGINE = get_engine()
UPDATE_LOCK = threading.Lock()
UPDATE_SCHEDULE_LOCK = threading.Lock()
UPDATE_CHANGE_ITEM_LIMIT = 50
UPDATE_MODEL_CHANGE_FIELD_LABELS = {
    "name": "Name",
    "provider": "Provider",
    "catalog_status": "Catalog status",
    "model_roles": "Model roles",
    "capabilities": "Capabilities",
    "release_date": "Release date",
    "context_window_tokens": "Context window",
    "max_output_tokens": "Max output",
    "parameter_count_b": "Parameters",
    "active_parameter_count_b": "Active parameters",
    "model_size_class": "Size class",
    "small_model_candidate": "Small model flag",
    "price_input_per_mtok": "Input price",
    "price_output_per_mtok": "Output price",
    "openrouter_canonical_slug": "OpenRouter slug",
    "openrouter_global_rank": "OpenRouter rank",
    "openrouter_programming_rank": "Programming rank",
    "huggingface_repo_id": "Hugging Face repo",
    "metadata_source_name": "Metadata source",
    "metadata_source_url": "Metadata source URL",
    "model_card_url": "Model card",
    "license_name": "License",
    "base_models": "Base models",
    "family_id": "Family",
    "canonical_model_id": "Canonical model",
}
BOOTSTRAP_LOCK = threading.Lock()
BOOTSTRAPPED = False
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LLMBenchmarkingBot/0.1; +https://localhost)",
    "Accept": "application/json,text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
}
MIN_RANKING_COVERAGE = 0.5
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_RANKINGS_URL = "https://openrouter.ai/rankings"
OPENROUTER_PROGRAMMING_COLLECTION_URL = "https://openrouter.ai/collections/programming"
OPENROUTER_MARKET_SOURCE_NAME = "openrouter"
OPENROUTER_NEW_RELEASE_LOOKBACK_DAYS = 60
HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME = "huggingface_model_discovery"
CATALOG_MODEL_DISCOVERY_SOURCE_NAME = "catalog_model_discovery"
PROVIDER_API_MODEL_DISCOVERY_SOURCE_NAME = "provider_api_model_discovery"
HUGGINGFACE_MODEL_API_URL_TEMPLATE = "https://huggingface.co/api/models/{repo_id}"
HUGGINGFACE_RAW_README_URL_TEMPLATE = "https://huggingface.co/{repo_id}/raw/main/README.md"
MODEL_CARD_REFRESH_STALE_DAYS = 30
INTERNAL_VIEW_NOTE = (
    "Optional internal assessment overlay entered in Admin. Missing internal scores do not block ranking eligibility."
)
INTERNAL_VIEW_COVERAGE_EXEMPT_BENCHMARK_IDS = {INTERNAL_VIEW_BENCHMARK_ID}
RECOMMENDATION_STATUS_UNRATED = "unrated"
RECOMMENDATION_STATUS_RECOMMENDED = "recommended"
RECOMMENDATION_STATUS_NOT_RECOMMENDED = "not_recommended"
RECOMMENDATION_STATUS_DISCOURAGED = "discouraged"
RECOMMENDATION_STATUS_RESTRICTED = "restricted"
RECOMMENDATION_STATUS_MIXED = "mixed"
DEFAULT_RECOMMENDATION_PROFILE_ID = "australian_bank"
VALID_RECOMMENDATION_STATUSES = {
    RECOMMENDATION_STATUS_UNRATED,
    RECOMMENDATION_STATUS_RECOMMENDED,
    RECOMMENDATION_STATUS_NOT_RECOMMENDED,
    RECOMMENDATION_STATUS_DISCOURAGED,
    RECOMMENDATION_STATUS_RESTRICTED,
}
SOURCE_METADATA_PROMOTION_LABELS = {
    "artificial_analysis": "Artificial Analysis",
    "artificial_analysis_tts": "Artificial Analysis Text to Speech",
    "chatbot_arena": "Chatbot Arena",
    "ifeval": "IFEval",
}
MODEL_ROLE_GENERATOR = "generator"
MODEL_ROLE_SPEECH_TO_TEXT = "speech_to_text"
MODEL_ROLE_TEXT_TO_SPEECH = "text_to_speech"
VALID_MODEL_ROLES = {
    "generator",
    "embedding",
    "reranker",
    "multimodal_embedding",
    MODEL_ROLE_SPEECH_TO_TEXT,
    MODEL_ROLE_TEXT_TO_SPEECH,
}
SPEECH_TO_TEXT_CAPABILITY_MARKERS = {
    "automatic-speech-recognition",
    "speech-to-text",
    "voice-to-text",
    "transcription-output",
    "transcription",
    "audio-transcription",
    "asr",
}
SPEECH_TO_TEXT_NAME_RE = re.compile(
    r"(?<![a-z0-9])(?:asr|whisper|transcribe|transcription|parakeet|mai-transcribe|(?:chirp|voxtral).*(?:asr|stt|transcri))(?![a-z0-9])",
    re.IGNORECASE,
)
TEXT_TO_SPEECH_CAPABILITY_MARKERS = {
    "text-to-speech",
    "speech-synthesis",
    "text->speech",
    "speech-output",
    "tts",
}
TEXT_GENERATION_CAPABILITY_MARKERS = {
    "text-output",
    "text->text",
    "chat-completion",
    "completion",
    "structured-output",
    "reasoning",
    "tool-use",
    "tool-choice",
}
TEXT_TO_SPEECH_NAME_RE = re.compile(
    r"(?<![a-z0-9])(?:tts|text-to-speech|speech-synthesis|gpt-4o-mini-tts|tts-1(?:-hd)?|sonic(?:[-\s]\d(?:\.\d)?)?|kokoro|orpheus|zonos|chatterbox|aura|polly|playdialog|play3|chirp(?:[-\s]*3)?[-:\s]*hd|grok-voice-tts|gemini.*tts|voxtral.*tts|mai-voice|eleven(?:labs)?|multilingual-v2|flash-v2-5|speech-\d+(?:\.\d+)?(?:[-\s](?:hd|turbo))?)(?![a-z0-9])",
    re.IGNORECASE,
)


class OptionalSourceUnavailable(RuntimeError):
    """Raised when an optional enrichment source is unavailable or has changed shape."""


SOURCE_STEP_LABEL_OVERRIDES = {
    "ailuminate": "AiLuminate",
    "artificial_analysis_tts": "Artificial Analysis Text to Speech",
    "chatbot_arena": "Chatbot Arena",
    "epoch_ai": "Epoch AI",
    "faithjudge": "FaithJudge",
    "ifeval": "IFEval",
    "mmmu": "MMMU",
    "mteb": "MTEB",
    "open_asr_leaderboard": "Open ASR Leaderboard",
    "swebench": "SWE-bench Verified",
    "terminal_bench": "Terminal-Bench",
    "vectara_hallucination": "Vectara Hallucination",
    HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME: "Hugging Face model discovery",
    PROVIDER_API_MODEL_DISCOVERY_SOURCE_NAME: "Provider API model discovery",
}
UPDATE_POST_PHASES = [
    {"key": "phase:identity-refresh-initial", "label": "Refresh model identity metadata", "kind": "phase"},
    {"key": "phase:catalog-canonicalization", "label": "Canonicalize model catalog", "kind": "phase"},
    {"key": "phase:identity-refresh-final", "label": "Refresh model identity metadata again", "kind": "phase"},
    {"key": "phase:provider-origin-baseline", "label": "Apply provider origin baseline", "kind": "phase"},
    {"key": "phase:openrouter-models", "label": "Refresh OpenRouter model metadata", "kind": "phase"},
    {"key": "phase:model-discovery", "label": "Refresh model discovery metadata", "kind": "phase"},
    {"key": "phase:model-card-metadata", "label": "Refresh model card metadata", "kind": "phase"},
    {"key": "phase:openrouter-market", "label": "Refresh OpenRouter market signals", "kind": "phase"},
    {"key": "phase:audit", "label": "Run post-update audit", "kind": "phase"},
    {"key": "phase:finalize", "label": "Finalize update", "kind": "phase"},
]
CATALOG_STATUS_TRACKED = "tracked"
CATALOG_STATUS_PROVISIONAL = "provisional"
_DISPLAY_PROVIDER_PREFIX_RE = re.compile(r"^[a-z0-9_.-]+/", re.IGNORECASE)
_DISPLAY_TRAILING_ISO_DATE_RE = re.compile(r"[-_]?20\d{2}[-_]\d{2}[-_]\d{2}$", re.IGNORECASE)
_DISPLAY_TRAILING_COMPACT_DATE_RE = re.compile(r"[-_]?20\d{6}$", re.IGNORECASE)
_DISPLAY_TRAILING_THINKING_RE = re.compile(r"-(?:\d+k-)?thinking(?:-\d+k)?$", re.IGNORECASE)
_DISPLAY_TRAILING_NON_REASONING_RE = re.compile(r"-non-reasoning(?:-low-effort)?$", re.IGNORECASE)
_DISPLAY_TRAILING_PAREN_VARIANT_RE = re.compile(r"\s*\([^)]*\)\s*$", re.IGNORECASE)
_OPENROUTER_TRAILING_ALIAS_RE = re.compile(
    r"(?:[\s:_-]+(?:it|instruct|chat|preview|latest|reasoning|thinking|free|fast|turbo))+$",
    re.IGNORECASE,
)
_OPENROUTER_TRAILING_VERSION_RE = re.compile(
    r"(?:[\s:_-]+v\d+(?:\.\d+)?(?::\d+)?)$",
    re.IGNORECASE,
)
_NEXT_FLIGHT_PUSH_RE = re.compile(r"<script>self\.__next_f\.push\((\[.*?\])\)</script>", re.S)
_VERSION_TOKEN_RE = re.compile(r"^(?:[a-z]?\d+(?:\.\d+)?|\d+(?:\.\d+)?[a-z]?)$", re.IGNORECASE)
_PROVIDER_PREFIX_HINTS = (
    ("openai/", "OpenAI"),
    ("anthropic/", "Anthropic"),
    ("google/", "Google"),
    ("meta-llama/", "Meta"),
    ("microsoft/", "Microsoft"),
    ("mistralai/", "Mistral"),
    ("qwen/", "Alibaba"),
    ("deepseek-ai/", "DeepSeek"),
    ("deepseek/", "DeepSeek"),
    ("xai-org/", "xAI"),
    ("moonshotai/", "Moonshot AI"),
    ("coherelabs/", "Cohere"),
    ("amazon/", "Amazon"),
    ("ibm-granite/", "IBM"),
)
_PROVIDER_NAME_HINTS = (
    ("qwen", "Alibaba"),
    ("deepseek", "DeepSeek"),
    ("gpt", "OpenAI"),
    ("o1", "OpenAI"),
    ("o3", "OpenAI"),
    ("o4", "OpenAI"),
    ("claude", "Anthropic"),
    ("gemini", "Google"),
    ("gemma", "Google"),
    ("phi", "Microsoft"),
)
_DISPLAY_TOKEN_MAP = {
    "claude": "Claude",
    "codex": "Codex",
    "deepseek": "DeepSeek",
    "flash": "Flash",
    "gemini": "Gemini",
    "gemma": "Gemma",
    "glm": "GLM",
    "gpt": "GPT",
    "grok": "Grok",
    "haiku": "Haiku",
    "high": "High",
    "instruct": "Instruct",
    "kimi": "Kimi",
    "lite": "Lite",
    "llama": "Llama",
    "low": "Low",
    "mistral": "Mistral",
    "minimax": "MiniMax",
    "nano": "Nano",
    "nova": "Nova",
    "o1": "o1",
    "o3": "o3",
    "o4": "o4",
    "opus": "Opus",
    "phi": "Phi",
    "preview": "Preview",
    "qwen": "Qwen",
    "reasoning": "Reasoning",
    "sonnet": "Sonnet",
    "turbo": "Turbo",
    "xhigh": "xhigh",
}


def bootstrap() -> None:
    """Initialize and repair local database state without network refreshes."""
    global BOOTSTRAPPED
    if BOOTSTRAPPED:
        return

    with BOOTSTRAP_LOCK:
        if BOOTSTRAPPED:
            return
        init_db(ENGINE)
        with ENGINE.begin() as conn:
            seed_reference_data(conn)
        _recover_interrupted_updates()
        _repair_score_trust_labels()
        _sync_provider_directory()
        apply_provider_origin_baseline(ENGINE)
        _canonicalize_provider_aliases()
        apply_model_curation_baseline(ENGINE)
        apply_model_license_baseline(ENGINE)
        _migrate_legacy_model_approvals()
        _refresh_model_identity_metadata()
        _canonicalize_model_catalog()
        _refresh_model_identity_metadata()
        BOOTSTRAPPED = True


def refresh_model_card_metadata(*, force: bool = False) -> None:
    bootstrap()
    _refresh_model_card_metadata(force=force)
    _refresh_model_license_metadata()


def refresh_model_license_metadata(*, refresh_model_cards: bool = False, force_model_cards: bool = False) -> dict[str, int]:
    bootstrap()
    if refresh_model_cards:
        _refresh_model_card_metadata(force=force_model_cards)
    return _refresh_model_license_metadata()


def refresh_model_discovery_metadata(*, source: str = "configured", family: str | None = None) -> dict[str, Any]:
    bootstrap()
    normalized_source = str(source or "").strip().lower()
    if normalized_source == "provider_api":
        normalized_source = "provider-api"
    if normalized_source not in {"configured", "huggingface", "catalog", "provider-api"}:
        raise ValueError(f"Unsupported model discovery source: {source}")

    step_plan = [
        {"key": "phase:model-discovery", "label": "Refresh model discovery metadata", "kind": "phase"},
        {"key": "phase:finalize", "label": "Finalize update", "kind": "phase"},
    ]
    log_id = _create_update_log("cli", step_plan)
    total_steps = len(step_plan)
    errors: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    try:
        _set_update_progress(log_id, step_plan[0], 1, total_steps)
        summary = _refresh_configured_model_discovery(log_id=log_id, source=normalized_source, family=family)
        _refresh_model_identity_metadata()
        _canonicalize_model_catalog()
        _refresh_model_identity_metadata()
        _set_update_progress(log_id, step_plan[1], 2, total_steps)
    except Exception as exc:
        errors.append(
            {
                "benchmark_id": "",
                "source_id": "model_discovery",
                "error_message": str(exc),
            }
        )
        _finalize_update_log(
            log_id,
            status="failed",
            scores_added=0,
            scores_updated=0,
            errors=errors,
            audit_result=None,
            step=step_plan[-1],
            step_index=total_steps,
            total_steps=total_steps,
        )
        raise

    _finalize_update_log(
        log_id,
        status="completed",
        scores_added=0,
        scores_updated=0,
        errors=errors,
        audit_result=None,
        step=step_plan[-1],
        step_index=total_steps,
        total_steps=total_steps,
    )
    return {"log_id": log_id, "source": normalized_source, **summary}


def _recover_interrupted_updates() -> None:
    with ENGINE.begin() as conn:
        rows = fetch_all(
            conn,
            select(update_log_table).where(update_log_table.c.status == "running"),
        )
        for row in rows:
            existing_errors = _decode_json_list(row.get("errors"))
            existing_errors.append(
                {
                    "benchmark_id": "",
                    "source_id": "update",
                    "error_message": "Update interrupted before completion. The server restarted or the worker crashed.",
                }
            )
            conn.execute(
                update(update_log_table)
                .where(update_log_table.c.id == row["id"])
                .values(
                    status="failed",
                    completed_at=utc_now_iso(),
                    errors=json.dumps(existing_errors),
                )
            )


def _repair_score_trust_labels() -> None:
    with ENGINE.begin() as conn:
        conn.execute(
            update(scores_table)
            .where(scores_table.c.benchmark_id == "swebench_verified")
            .where(scores_table.c.source_type != "secondary")
            .values(source_type="secondary")
        )
        conn.execute(
            update(scores_table)
            .where(scores_table.c.benchmark_id == "ifeval")
            .where(
                (scores_table.c.source_type != "secondary")
                | (scores_table.c.verified != 0)
            )
            .values(source_type="secondary", verified=0)
        )


def _decode_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _decode_json_string_list(value: Any) -> list[str]:
    return [
        str(item).strip()
        for item in _decode_json_list(value)
        if str(item).strip()
    ]


def _normalise_model_roles(value: Any, *, default: Iterable[str] = (MODEL_ROLE_GENERATOR,)) -> list[str]:
    roles = [
        role
        for role in _decode_json_string_list(value if not isinstance(value, str) else value)
        if role in VALID_MODEL_ROLES
    ]
    if roles:
        return sorted(dict.fromkeys(roles))
    return sorted(dict.fromkeys(role for role in default if role in VALID_MODEL_ROLES))


def _model_roles_from_metadata(metadata: dict[str, Any]) -> list[str]:
    raw_roles = metadata.get("model_roles")
    if raw_roles is None and metadata.get("model_role") is not None:
        raw_roles = [metadata.get("model_role")]
    roles = _normalise_model_roles(raw_roles, default=())
    if _metadata_indicates_speech_to_text(metadata):
        roles.append(MODEL_ROLE_SPEECH_TO_TEXT)
    if _metadata_indicates_text_to_speech(metadata):
        roles.append(MODEL_ROLE_TEXT_TO_SPEECH)
    return sorted(dict.fromkeys(roles))


def _metadata_indicates_speech_to_text(metadata: dict[str, Any]) -> bool:
    if _metadata_indicates_text_to_speech(metadata):
        explicit_stt_values = _metadata_audio_indicator_values(metadata, include_names=False)
        if not _values_indicate_speech_to_text(*explicit_stt_values):
            return False
    return _values_indicate_speech_to_text(
        *_metadata_audio_indicator_values(metadata),
    )


def _metadata_indicates_text_to_speech(metadata: dict[str, Any]) -> bool:
    return _values_indicate_text_to_speech(
        *_metadata_audio_indicator_values(metadata),
    )


def _metadata_audio_indicator_values(metadata: dict[str, Any], *, include_names: bool = True) -> list[Any]:
    capability_values = _decode_json_string_list(metadata.get("capabilities"))
    capability_values.extend(_decode_json_string_list(metadata.get("capabilities_json")))
    for key in (
        "pipeline_tag",
        "task",
        "modality",
        "input_modality",
        "output_modality",
        "input_modalities",
        "output_modalities",
    ):
        raw_value = metadata.get(key)
        if isinstance(raw_value, list):
            capability_values.extend(_decode_json_string_list(raw_value))
            continue
        value = _clean_text(raw_value)
        if value:
            capability_values.append(value)
    if include_names:
        capability_values.extend(
            [
                metadata.get("raw_model_name"),
                metadata.get("model_name"),
                metadata.get("name"),
                metadata.get("huggingface_repo_id"),
                metadata.get("openrouter_model_id"),
            ]
        )
    return capability_values


def _values_indicate_speech_to_text(*values: Any) -> bool:
    for value in values:
        for text in _iter_text_values(value):
            normalized = text.strip().lower().replace("_", "-")
            if normalized in SPEECH_TO_TEXT_CAPABILITY_MARKERS:
                return True
            if normalized.endswith("-output") and "transcription" in normalized:
                return True
            if SPEECH_TO_TEXT_NAME_RE.search(normalized):
                return True
    return False


def _values_indicate_text_to_speech(*values: Any) -> bool:
    for value in values:
        for text in _iter_text_values(value):
            normalized = text.strip().lower().replace("_", "-")
            if normalized in TEXT_TO_SPEECH_CAPABILITY_MARKERS:
                return True
            if normalized.endswith("-output") and "speech" in normalized:
                return True
            if TEXT_TO_SPEECH_NAME_RE.search(normalized):
                return True
    return False


def _values_indicate_text_generation(*values: Any) -> bool:
    for value in values:
        for text in _iter_text_values(value):
            normalized = text.strip().lower().replace("_", "-")
            if normalized in TEXT_GENERATION_CAPABILITY_MARKERS:
                return True
            if normalized.endswith("->text") and not any(
                marker in normalized for marker in ("audio", "speech", "transcription")
            ):
                return True
    return False


def _iter_text_values(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _iter_text_values(item)]
    if isinstance(value, Iterable):
        return [text for item in value for text in _iter_text_values(item)]
    return [str(value)]


def _merge_inferred_speech_to_text_role(
    current_roles_value: Any,
    *,
    capabilities: Iterable[str] | None = None,
    names: Iterable[Any] = (),
) -> list[str]:
    return _merge_inferred_audio_roles(
        current_roles_value,
        capabilities=capabilities,
        names=names,
    )


def _merge_inferred_audio_roles(
    current_roles_value: Any,
    *,
    capabilities: Iterable[str] | None = None,
    names: Iterable[Any] = (),
) -> list[str]:
    roles = _normalise_model_roles(current_roles_value, default=(MODEL_ROLE_GENERATOR,))
    capability_values = list(capabilities or [])
    tts_detected = _values_indicate_text_to_speech(*capability_values, *names)
    explicit_stt_detected = _values_indicate_speech_to_text(*capability_values)
    stt_detected = explicit_stt_detected or (not tts_detected and _values_indicate_speech_to_text(*names))
    if (stt_detected or tts_detected) and set(roles) == {MODEL_ROLE_GENERATOR}:
        if not _values_indicate_text_generation(*capability_values):
            roles = []
    if stt_detected:
        roles.append(MODEL_ROLE_SPEECH_TO_TEXT)
    if tts_detected:
        roles.append(MODEL_ROLE_TEXT_TO_SPEECH)
    return sorted(dict.fromkeys(roles))


def _humanize_source_name(source_name: str) -> str:
    return update_orchestration.humanize_source_name(source_name, SOURCE_STEP_LABEL_OVERRIDES)


def _build_update_plan(
    adapters: list[BaseSourceAdapter],
    *,
    include_model_discovery: bool = True,
) -> list[dict[str, Any]]:
    post_phases = [
        phase
        for phase in UPDATE_POST_PHASES
        if include_model_discovery or phase.get("key") != "phase:model-discovery"
    ]
    return update_orchestration.build_update_plan(
        adapters,
        post_phases=post_phases,
        label_overrides=SOURCE_STEP_LABEL_OVERRIDES,
    )


def _set_update_progress(log_id: int, step: dict[str, Any], step_index: int, total_steps: int) -> None:
    with ENGINE.begin() as conn:
        conn.execute(
            update(update_log_table)
            .where(update_log_table.c.id == log_id)
            .values(
                current_step_key=step.get("key"),
                current_step_label=step.get("label"),
                current_step_started_at=utc_now_iso(),
                current_step_index=step_index,
                total_steps=total_steps,
            )
        )


def list_benchmarks() -> list[dict[str, Any]]:
    bootstrap()
    benchmark_stats = _benchmark_stats(_load_latest_scores())
    with get_connection(ENGINE) as conn:
        rows = fetch_all(
            conn,
            select(benchmarks_table)
            .where(benchmarks_table.c.active == 1)
            .order_by(benchmarks_table.c.tier.asc(), benchmarks_table.c.name.asc()),
        )
    payload: list[dict[str, Any]] = []
    for row in rows:
        benchmark = _serialize_benchmark(row)
        benchmark.update(benchmark_stats.get(benchmark["id"], {}))
        payload.append(benchmark)
    return payload


def list_use_cases() -> list[dict[str, Any]]:
    bootstrap()
    with get_connection(ENGINE) as conn:
        weight_overrides_by_use_case = _load_use_case_weight_overrides(conn)
    return [_resolve_use_case_definition(use_case, weight_overrides_by_use_case) for use_case in USE_CASES]


def _load_use_case_weight_overrides(conn) -> dict[str, dict[str, float]]:
    rows = fetch_all(conn, select(use_case_benchmark_weights_table))
    payload: dict[str, dict[str, float]] = {}
    for row in rows:
        use_case_id = str(row.get("use_case_id") or "").strip()
        benchmark_id = str(row.get("benchmark_id") or "").strip()
        if not use_case_id or not benchmark_id:
            continue
        payload.setdefault(use_case_id, {})[benchmark_id] = float(row.get("weight") or 0.0)
    return payload


def _resolve_use_case_definition(
    use_case: dict[str, Any],
    weight_overrides_by_use_case: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    resolved = {
        "id": use_case["id"],
        "label": use_case["label"],
        "icon": use_case["icon"],
        "description": use_case["description"],
        "segment": use_case.get("segment", "core"),
        "status": use_case.get("status", "ready"),
        "model_roles": _normalise_model_roles(use_case.get("model_roles"), default=(MODEL_ROLE_GENERATOR,)),
        "production_commercial": bool(
            use_case.get("production_commercial", use_case.get("segment", "core") == "enterprise")
        ),
        "min_coverage": float(use_case.get("min_coverage", MIN_RANKING_COVERAGE)),
        "required_benchmarks": list(use_case.get("required_benchmarks", [])),
        "benchmark_notes": dict(use_case.get("benchmark_notes", {})),
        "weights": dict(use_case["weights"]),
    }

    override_weights = (weight_overrides_by_use_case or {}).get(resolved["id"], {})
    internal_view_weight = max(0.0, min(1.0, float(override_weights.get(INTERNAL_VIEW_BENCHMARK_ID, 0.0) or 0.0)))
    resolved["internal_view_weight"] = internal_view_weight

    if internal_view_weight > 0:
        scaled_base_weights = {
            benchmark_id: float(weight) * (1.0 - internal_view_weight)
            for benchmark_id, weight in resolved["weights"].items()
        }
        scaled_base_weights[INTERNAL_VIEW_BENCHMARK_ID] = internal_view_weight
        resolved["weights"] = scaled_base_weights
        resolved["benchmark_notes"].setdefault(INTERNAL_VIEW_BENCHMARK_ID, INTERNAL_VIEW_NOTE)

    return resolved


def _all_use_case_ids() -> list[str]:
    return [str(use_case["id"]) for use_case in USE_CASES if str(use_case.get("id") or "").strip()]


def _normalize_recommendation_status(value: Any, *, allow_mixed: bool = False) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_RECOMMENDATION_STATUSES:
        return normalized
    if allow_mixed and normalized == RECOMMENDATION_STATUS_MIXED:
        return normalized
    return RECOMMENDATION_STATUS_UNRATED


def _serialize_use_case_approval(row: dict[str, Any]) -> dict[str, Any]:
    recommendation_status = _normalize_recommendation_status(row.get("recommendation_status"))
    auto_recommendation_status = _normalize_recommendation_status(row.get("auto_recommendation_status"))
    return {
        "use_case_id": str(row.get("use_case_id") or ""),
        "approved_for_use": bool(row.get("approved_for_use", 0)),
        "approval_notes": _clean_text(row.get("approval_notes")),
        "approval_updated_at": row.get("approval_updated_at"),
        "recommendation_status": recommendation_status,
        "recommendation_notes": _clean_text(row.get("recommendation_notes")),
        "recommendation_updated_at": row.get("recommendation_updated_at"),
        "auto_recommendation_status": auto_recommendation_status,
        "auto_recommendation_notes": _clean_text(row.get("auto_recommendation_notes")),
        "auto_not_recommended_member_count": int(
            row.get("auto_not_recommended_member_count")
            or (1 if auto_recommendation_status == RECOMMENDATION_STATUS_NOT_RECOMMENDED else 0)
        ),
        "approval_member_count": int(row.get("approval_member_count") or (1 if row.get("approved_for_use") else 0)),
        "approval_total_count": int(row.get("approval_total_count") or 1),
        "recommended_member_count": int(
            row.get("recommended_member_count") or (1 if recommendation_status == RECOMMENDATION_STATUS_RECOMMENDED else 0)
        ),
        "not_recommended_member_count": int(
            row.get("not_recommended_member_count") or (1 if recommendation_status == RECOMMENDATION_STATUS_NOT_RECOMMENDED else 0)
        ),
        "discouraged_member_count": int(
            row.get("discouraged_member_count") or (1 if recommendation_status == RECOMMENDATION_STATUS_DISCOURAGED else 0)
        ),
        "restricted_member_count": int(
            row.get("restricted_member_count") or (1 if recommendation_status == RECOMMENDATION_STATUS_RESTRICTED else 0)
        ),
        "proposed_recommendation_status": _normalize_recommendation_status(row.get("proposed_recommendation_status")),
        "proposed_recommendation_score": row.get("proposed_recommendation_score"),
        "proposed_recommendation_confidence": row.get("proposed_recommendation_confidence"),
        "proposed_recommendation_blockers": _decode_json_string_list(row.get("proposed_recommendation_blockers_json")),
        "proposed_recommendation_warnings": _decode_json_string_list(row.get("proposed_recommendation_warnings_json")),
        "proposed_recommendation_reasons": _decode_json_string_list(row.get("proposed_recommendation_reasons_json")),
        "proposed_recommendation_required_controls": _decode_json_string_list(
            row.get("proposed_recommendation_required_controls_json")
        ),
        "proposed_recommendation_policy_version": _clean_text(row.get("proposed_recommendation_policy_version")),
        "proposed_recommendation_computed_at": row.get("proposed_recommendation_computed_at"),
        "effective_recommendation_status": _normalize_recommendation_status(
            row.get("effective_recommendation_status"),
            allow_mixed=True,
        ),
        "inference_route_approvals": [],
    }


def _default_use_case_approval_payload(use_case_id: str) -> dict[str, Any]:
    return {
        "use_case_id": use_case_id,
        "approved_for_use": False,
        "approval_notes": None,
        "approval_updated_at": None,
        "recommendation_status": RECOMMENDATION_STATUS_UNRATED,
        "recommendation_notes": None,
        "recommendation_updated_at": None,
        "auto_recommendation_status": RECOMMENDATION_STATUS_UNRATED,
        "auto_recommendation_notes": None,
        "auto_not_recommended_member_count": 0,
        "approval_member_count": 0,
        "approval_total_count": 1,
        "recommended_member_count": 0,
        "not_recommended_member_count": 0,
        "discouraged_member_count": 0,
        "restricted_member_count": 0,
        "proposed_recommendation_status": RECOMMENDATION_STATUS_UNRATED,
        "proposed_recommendation_score": None,
        "proposed_recommendation_confidence": None,
        "proposed_recommendation_blockers": [],
        "proposed_recommendation_warnings": [],
        "proposed_recommendation_reasons": [],
        "proposed_recommendation_required_controls": [],
        "proposed_recommendation_policy_version": None,
        "proposed_recommendation_computed_at": None,
        "effective_recommendation_status": RECOMMENDATION_STATUS_UNRATED,
    }


def _is_production_commercial_use_case(use_case: dict[str, Any] | None) -> bool:
    if use_case is None:
        return False
    return bool(use_case.get("production_commercial", use_case.get("segment", "core") == "enterprise"))


def _attach_license_policy_use_case_overlays(model: dict[str, Any]) -> None:
    use_case_approvals = model.get("use_case_approvals")
    if not isinstance(use_case_approvals, dict):
        return

    if model.get("license_policy_class") != LICENSE_POLICY_COMMERCIAL_BLOCKED:
        return

    auto_note = _clean_text(model.get("license_policy_note"))
    for use_case in USE_CASES:
        if not _is_production_commercial_use_case(use_case):
            continue
        use_case_id = str(use_case.get("id") or "").strip()
        if not use_case_id:
            continue
        approval = use_case_approvals.setdefault(use_case_id, _default_use_case_approval_payload(use_case_id))
        _set_auto_not_recommended_overlay(approval, auto_note)


def _attach_provenance_policy_use_case_overlays(model: dict[str, Any]) -> None:
    use_case_approvals = model.get("use_case_approvals")
    if not isinstance(use_case_approvals, dict):
        return

    if model.get("provenance_policy_class") != PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED:
        return

    auto_note = _clean_text(model.get("provenance_policy_note"))
    for use_case in USE_CASES:
        if not _is_production_commercial_use_case(use_case):
            continue
        use_case_id = str(use_case.get("id") or "").strip()
        if not use_case_id:
            continue
        approval = use_case_approvals.setdefault(use_case_id, _default_use_case_approval_payload(use_case_id))
        _set_auto_not_recommended_overlay(approval, auto_note)


def _attach_recommendation_proposals(
    model: dict[str, Any],
    proposals_by_use_case: dict[str, dict[str, Any]] | None,
) -> None:
    use_case_approvals = model.get("use_case_approvals")
    if not isinstance(use_case_approvals, dict):
        return

    for use_case_id, proposal in (proposals_by_use_case or {}).items():
        approval = use_case_approvals.setdefault(use_case_id, _default_use_case_approval_payload(use_case_id))
        approval["proposed_recommendation_status"] = _normalize_recommendation_status(proposal.get("proposed_status"))
        approval["proposed_recommendation_score"] = proposal.get("score")
        approval["proposed_recommendation_confidence"] = proposal.get("confidence")
        approval["proposed_recommendation_blockers"] = _decode_json_string_list(proposal.get("blockers"))
        approval["proposed_recommendation_warnings"] = _decode_json_string_list(proposal.get("warnings"))
        approval["proposed_recommendation_reasons"] = _decode_json_string_list(proposal.get("reasons"))
        approval["proposed_recommendation_required_controls"] = _decode_json_string_list(proposal.get("required_controls"))
        approval["proposed_recommendation_policy_version"] = _clean_text(proposal.get("policy_version"))
        approval["proposed_recommendation_computed_at"] = proposal.get("computed_at")

    _attach_effective_recommendation_statuses(use_case_approvals)


def _build_suggested_use_cases(
    proposals_by_use_case: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return positive metric-derived use-case fits without creating decision state."""
    use_case_lookup = {
        str(use_case.get("id") or ""): use_case
        for use_case in USE_CASES
        if str(use_case.get("id") or "").strip()
    }
    suggestions: list[dict[str, Any]] = []
    for use_case_id, proposal in (proposals_by_use_case or {}).items():
        proposed_status = _normalize_recommendation_status(proposal.get("proposed_status"))
        score = proposal.get("score")
        if proposed_status not in {RECOMMENDATION_STATUS_RECOMMENDED, RECOMMENDATION_STATUS_RESTRICTED}:
            continue
        if score is None:
            continue
        use_case = use_case_lookup.get(str(use_case_id), {})
        suggestions.append(
            {
                "use_case_id": str(use_case_id),
                "label": str(use_case.get("label") or use_case_id),
                "description": _clean_text(use_case.get("description")),
                "fit_score": float(score),
                "confidence": proposal.get("confidence"),
                "reasons": _decode_json_string_list(proposal.get("reasons")),
                "warnings": _decode_json_string_list(proposal.get("warnings")),
                "required_controls": _decode_json_string_list(proposal.get("required_controls")),
                "policy_version": _clean_text(proposal.get("policy_version")),
                "computed_at": proposal.get("computed_at"),
            }
        )
    return sorted(
        suggestions,
        key=lambda suggestion: (
            -float(suggestion.get("fit_score") or 0.0),
            -float(suggestion.get("confidence") or 0.0),
            str(suggestion.get("label") or ""),
        ),
    )


def _attach_effective_recommendation_statuses(use_case_approvals: dict[str, dict[str, Any]]) -> None:
    for approval in use_case_approvals.values():
        manual_status = _normalize_recommendation_status(
            approval.get("recommendation_status"),
            allow_mixed=True,
        )
        auto_status = _normalize_recommendation_status(
            approval.get("auto_recommendation_status"),
            allow_mixed=True,
        )
        proposed_status = _normalize_recommendation_status(approval.get("proposed_recommendation_status"))
        if manual_status != RECOMMENDATION_STATUS_UNRATED:
            effective_status = manual_status
        elif auto_status == RECOMMENDATION_STATUS_NOT_RECOMMENDED:
            effective_status = RECOMMENDATION_STATUS_NOT_RECOMMENDED
        elif proposed_status != RECOMMENDATION_STATUS_UNRATED:
            effective_status = proposed_status
        else:
            effective_status = RECOMMENDATION_STATUS_UNRATED
        approval["effective_recommendation_status"] = effective_status


def _set_auto_not_recommended_overlay(approval: dict[str, Any], note: str | None) -> None:
    approval["auto_recommendation_status"] = RECOMMENDATION_STATUS_NOT_RECOMMENDED
    approval["auto_not_recommended_member_count"] = max(
        1,
        int(approval.get("auto_not_recommended_member_count") or 0),
    )
    approval["auto_recommendation_notes"] = _merge_overlay_notes(
        approval.get("auto_recommendation_notes"),
        note,
    )


def _merge_overlay_notes(*values: Any) -> str | None:
    normalized: list[str] = []
    for value in values:
        text_value = _clean_text(value)
        if text_value is not None and text_value not in normalized:
            normalized.append(text_value)
    if not normalized:
        return None
    return " ".join(normalized)


def _load_model_use_case_approvals(
    conn,
    model_ids: Iterable[str] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    statement = select(model_use_case_approvals_table)
    normalized_model_ids = [str(model_id) for model_id in (model_ids or []) if str(model_id).strip()]
    if normalized_model_ids:
        statement = statement.where(model_use_case_approvals_table.c.model_id.in_(normalized_model_ids))
    rows = fetch_all(conn, statement)
    payload: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        model_id = str(row.get("model_id") or "").strip()
        use_case_id = str(row.get("use_case_id") or "").strip()
        if not model_id or not use_case_id:
            continue
        payload.setdefault(model_id, {})[use_case_id] = _serialize_use_case_approval(row)
    return payload


def _serialize_recommendation_proposal(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": str(row.get("profile_id") or ""),
        "model_id": str(row.get("model_id") or ""),
        "use_case_id": str(row.get("use_case_id") or ""),
        "proposed_status": _normalize_recommendation_status(row.get("proposed_status")),
        "score": row.get("score"),
        "confidence": row.get("confidence"),
        "blockers": _decode_json_string_list(row.get("blockers_json")),
        "warnings": _decode_json_string_list(row.get("warnings_json")),
        "reasons": _decode_json_string_list(row.get("reasons_json")),
        "required_controls": _decode_json_string_list(row.get("required_controls_json")),
        "policy_version": _clean_text(row.get("policy_version")),
        "computed_at": row.get("computed_at"),
        "source_profile": _decode_json_object(row.get("source_profile_json")),
    }


def _load_model_use_case_recommendation_proposals(
    conn,
    model_ids: Iterable[str] | None = None,
    *,
    profile_id: str = DEFAULT_RECOMMENDATION_PROFILE_ID,
) -> dict[str, dict[str, dict[str, Any]]]:
    statement = select(model_use_case_recommendation_proposals_table).where(
        model_use_case_recommendation_proposals_table.c.profile_id == profile_id
    )
    normalized_model_ids = [str(model_id) for model_id in (model_ids or []) if str(model_id).strip()]
    if normalized_model_ids:
        statement = statement.where(model_use_case_recommendation_proposals_table.c.model_id.in_(normalized_model_ids))
    rows = fetch_all(conn, statement)
    payload: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        model_id = str(row.get("model_id") or "").strip()
        use_case_id = str(row.get("use_case_id") or "").strip()
        if not model_id or not use_case_id:
            continue
        payload.setdefault(model_id, {})[use_case_id] = _serialize_recommendation_proposal(row)
    return payload


def _serialize_inference_route_approval(
    row: dict[str, Any],
    destination_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    destination = (destination_lookup or {}).get(str(row.get("destination_id") or ""))
    return {
        "use_case_id": str(row.get("use_case_id") or ""),
        "destination_id": str(row.get("destination_id") or ""),
        "destination_name": destination.get("name") if destination is not None else None,
        "hyperscaler": destination.get("hyperscaler") if destination is not None else None,
        "location_key": str(row.get("location_key") or ""),
        "location_label": str(row.get("location_label") or ""),
        "approved_for_use": bool(row.get("approved_for_use", 0)),
        "approval_notes": _clean_text(row.get("approval_notes")),
        "approval_updated_at": row.get("approval_updated_at"),
    }


def _load_model_use_case_inference_approvals(
    conn,
    model_ids: Iterable[str] | None = None,
    destinations_by_model_id: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    statement = select(model_use_case_inference_approvals_table)
    normalized_model_ids = [str(model_id) for model_id in (model_ids or []) if str(model_id).strip()]
    if normalized_model_ids:
        statement = statement.where(model_use_case_inference_approvals_table.c.model_id.in_(normalized_model_ids))
    rows = fetch_all(conn, statement)
    payload: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        model_id = str(row.get("model_id") or "").strip()
        use_case_id = str(row.get("use_case_id") or "").strip()
        if not model_id or not use_case_id:
            continue
        destination_lookup = {
            str(destination.get("id") or ""): destination
            for destination in (destinations_by_model_id or {}).get(model_id, [])
            if str(destination.get("id") or "").strip()
        }
        payload.setdefault(model_id, {}).setdefault(use_case_id, []).append(
            _serialize_inference_route_approval(row, destination_lookup)
        )

    for approvals_by_use_case in payload.values():
        for use_case_id, approvals in approvals_by_use_case.items():
            approvals_by_use_case[use_case_id] = sorted(
                approvals,
                key=lambda item: (
                    str(item.get("destination_name") or ""),
                    str(item.get("location_label") or ""),
                ),
            )
    return payload


def _approval_summary_from_use_case_approvals(use_case_approvals: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    approvals = use_case_approvals or {}
    latest_entry: dict[str, Any] | None = None
    for approval in approvals.values():
        if latest_entry is None or str(approval.get("approval_updated_at") or "") > str(latest_entry.get("approval_updated_at") or ""):
            latest_entry = approval

    approved_entries = [approval for approval in approvals.values() if approval.get("approved_for_use")]
    return {
        "approved_for_use": bool(approved_entries),
        "approval_use_case_count": len(approved_entries),
        "approval_notes": latest_entry.get("approval_notes") if latest_entry is not None else None,
        "approval_updated_at": latest_entry.get("approval_updated_at") if latest_entry is not None else None,
    }


def list_models(*, include_recommendation_proposals: bool = True) -> list[dict[str, Any]]:
    bootstrap()
    benchmarks = list_benchmarks()
    benchmark_ids = [benchmark["id"] for benchmark in benchmarks]
    benchmark_source_ids = _benchmark_source_ids(benchmarks)
    latest_scores = _load_latest_scores()
    score_configurations = _load_latest_score_configurations()

    with get_connection(ENGINE) as conn:
        provider_rows = fetch_all(
            conn,
            select(providers_table).where(providers_table.c.active == 1),
        )
        model_rows = fetch_all(
            conn,
            select(models_table)
            .where(models_table.c.active == 1)
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )
        model_ids = [str(row["id"]) for row in model_rows]
        approvals_by_model_id = _load_model_use_case_approvals(conn, model_ids)
        recommendation_proposals_by_model_id = (
            _load_model_use_case_recommendation_proposals(conn, model_ids)
            if include_recommendation_proposals
            else {}
        )
        inference_approvals_by_model_id = _load_model_use_case_inference_approvals(conn, model_ids)
        inference_rows_by_model = load_synced_inference_catalog(conn, model_ids)
        authoritative_destination_ids = load_authoritative_destination_ids(conn)
        source_freshness_by_model_id = _load_source_freshness_by_model_id(
            conn,
            model_ids,
            benchmark_source_ids=benchmark_source_ids,
            latest_scores=latest_scores,
        )
        source_listings_by_model_id: dict[str, list[dict[str, Any]]] = {}
        if model_ids:
            listing_rows = fetch_all(
                conn,
                select(model_source_listings_table)
                .where(model_source_listings_table.c.model_id.in_(model_ids))
                .order_by(
                    model_source_listings_table.c.source_name.asc(),
                    model_source_listings_table.c.benchmark_id.asc(),
                ),
            )
            for listing in listing_rows:
                listing["metadata"] = _decode_json_object(listing.pop("metadata_json", None))
                source_listings_by_model_id.setdefault(str(listing["model_id"]), []).append(listing)

    providers_by_id = {str(row["id"]): _serialize_provider(row) for row in provider_rows}
    providers_by_name = {
        normalize_text(str(row["name"])): _serialize_provider(row)
        for row in provider_rows
        if str(row.get("name") or "").strip()
    }

    payload: list[dict[str, Any]] = []
    for row in model_rows:
        model = _serialize_model(
            row,
            provider_metadata=_resolve_provider_metadata(row, providers_by_id, providers_by_name),
            use_case_approvals=approvals_by_model_id.get(str(row["id"]), {}),
            recommendation_proposals=recommendation_proposals_by_model_id.get(str(row["id"]), {}),
            inference_route_approvals=inference_approvals_by_model_id.get(str(row["id"]), {}),
        )
        model["source_freshness"] = source_freshness_by_model_id.get(str(row["id"]), [])
        model["source_listings"] = source_listings_by_model_id.get(str(row["id"]), [])
        model = attach_inference_catalog(
            model,
            synced_destinations=inference_rows_by_model.get(model["id"]),
            authoritative_destinations=authoritative_destination_ids,
        )
        _attach_inference_route_destination_metadata(model)
        model["scores"] = {
            benchmark_id: _serialize_score(latest_scores[(model["id"], benchmark_id)])
            if (model["id"], benchmark_id) in latest_scores
            else None
            for benchmark_id in benchmark_ids
        }
        model["score_configurations"] = [
            {"benchmark_id": benchmark_id, **_serialize_score(score)}
            for (configuration_model_id, benchmark_id, _key, _value), score in score_configurations.items()
            if configuration_model_id == model["id"]
        ]
        payload.append(model)
    return payload


def _benchmark_source_ids(benchmarks: list[dict[str, Any]]) -> dict[str, str]:
    source_id_by_scraper = {
        adapter.__class__.__name__: adapter.source_id
        for adapter in get_source_adapters(include_phase_two=True)
    }
    payload: dict[str, str] = {}
    for benchmark in benchmarks:
        benchmark_id = str(benchmark.get("id") or "").strip()
        scraper_id = str(benchmark.get("scraper_id") or "").strip()
        source_id = source_id_by_scraper.get(scraper_id)
        if benchmark_id and source_id:
            payload[benchmark_id] = source_id
    return payload


def _load_source_freshness_by_model_id(
    conn,
    model_ids: list[str],
    *,
    benchmark_source_ids: dict[str, str],
    latest_scores: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    if not model_ids:
        return {}

    source_benchmark_ids: dict[str, set[str]] = {}
    for benchmark_id, source_name in benchmark_source_ids.items():
        source_benchmark_ids.setdefault(source_name, set()).add(benchmark_id)
    source_names = sorted(source_benchmark_ids)

    source_runs = fetch_all(
        conn,
        select(source_runs_table).where(source_runs_table.c.source_name.in_(source_names)),
    ) if source_names else []
    latest_attempt_by_source: dict[str, dict[str, Any]] = {}
    latest_success_by_source: dict[str, dict[str, Any]] = {}
    latest_failure_by_source: dict[str, dict[str, Any]] = {}
    for row in source_runs:
        source_name = str(row.get("source_name") or "").strip()
        if not source_name:
            continue
        if _source_run_is_newer(row, latest_attempt_by_source.get(source_name)):
            latest_attempt_by_source[source_name] = row
        status = str(row.get("status") or "").strip()
        if status == "completed" and _source_run_is_newer(row, latest_success_by_source.get(source_name)):
            latest_success_by_source[source_name] = row
        if status == "failed" and _source_run_is_newer(row, latest_failure_by_source.get(source_name)):
            latest_failure_by_source[source_name] = row

    score_data: dict[str, dict[str, dict[str, Any]]] = {model_id: {} for model_id in model_ids}
    for (model_id, benchmark_id), score in latest_scores.items():
        model_id = str(model_id)
        source_name = benchmark_source_ids.get(str(benchmark_id))
        if model_id not in score_data or source_name is None:
            continue
        current = score_data[model_id].setdefault(
            source_name,
            {"benchmark_ids": set(), "latest_model_score_at": None},
        )
        current["benchmark_ids"].add(str(benchmark_id))
        collected_at = str(score.get("collected_at") or "")
        if collected_at and collected_at > str(current.get("latest_model_score_at") or ""):
            current["latest_model_score_at"] = collected_at

    raw_data: dict[str, dict[str, dict[str, Any]]] = {model_id: {} for model_id in model_ids}
    raw_join = raw_source_records_table.join(
        source_runs_table,
        raw_source_records_table.c.source_run_id == source_runs_table.c.id,
    )
    raw_rows = fetch_all(
        conn,
        select(
            raw_source_records_table.c.normalized_model_id,
            raw_source_records_table.c.benchmark_id,
            raw_source_records_table.c.collected_at,
            source_runs_table.c.source_name,
        )
        .select_from(raw_join)
        .where(raw_source_records_table.c.normalized_model_id.in_(model_ids)),
    )
    for row in raw_rows:
        model_id = str(row.get("normalized_model_id") or "").strip()
        source_name = str(row.get("source_name") or "").strip()
        benchmark_id = str(row.get("benchmark_id") or "").strip()
        if model_id not in raw_data or source_name not in source_benchmark_ids:
            continue
        current = raw_data[model_id].setdefault(
            source_name,
            {"benchmark_ids": set(), "latest_model_raw_record_at": None},
        )
        if benchmark_id:
            current["benchmark_ids"].add(benchmark_id)
        collected_at = str(row.get("collected_at") or "")
        if collected_at and collected_at > str(current.get("latest_model_raw_record_at") or ""):
            current["latest_model_raw_record_at"] = collected_at

    payload: dict[str, list[dict[str, Any]]] = {}
    for model_id in model_ids:
        entries = []
        for source_name in source_names:
            entries.append(
                _source_freshness_entry(
                    source_name,
                    benchmark_ids=sorted(source_benchmark_ids.get(source_name, set())),
                    latest_attempt=latest_attempt_by_source.get(source_name),
                    latest_success=latest_success_by_source.get(source_name),
                    latest_failure=latest_failure_by_source.get(source_name),
                    score_data=score_data.get(model_id, {}).get(source_name, {}),
                    raw_data=raw_data.get(model_id, {}).get(source_name, {}),
                )
            )
        payload[model_id] = entries
    return payload


def _source_freshness_entry(
    source_name: str,
    *,
    benchmark_ids: list[str],
    latest_attempt: dict[str, Any] | None,
    latest_success: dict[str, Any] | None,
    latest_failure: dict[str, Any] | None,
    score_data: dict[str, Any],
    raw_data: dict[str, Any],
) -> dict[str, Any]:
    latest_source_status = str(latest_attempt.get("status") or "") if latest_attempt is not None else None
    latest_attempted_at = _source_run_timestamp(latest_attempt)
    latest_success_at = _source_run_timestamp(latest_success)
    latest_failure_at = _source_run_timestamp(latest_failure)
    latest_model_score_at = score_data.get("latest_model_score_at")
    latest_model_raw_record_at = raw_data.get("latest_model_raw_record_at")
    has_model_score = bool(score_data.get("benchmark_ids"))
    has_model_raw_record = bool(raw_data.get("benchmark_ids"))
    has_model_evidence = has_model_score or has_model_raw_record
    degraded = latest_source_status == "failed"

    if degraded and has_model_evidence:
        model_evidence_status = "stale"
    elif degraded:
        model_evidence_status = "missing_source_failed"
    elif latest_source_status == "running" and has_model_evidence:
        model_evidence_status = "refreshing"
    elif has_model_evidence:
        model_evidence_status = "current"
    elif latest_source_status == "completed":
        model_evidence_status = "missing"
    else:
        model_evidence_status = "unknown"

    return {
        "source_name": source_name,
        "source_label": _humanize_source_name(source_name),
        "benchmark_ids": benchmark_ids,
        "model_benchmark_ids": sorted(
            set(score_data.get("benchmark_ids") or set())
            | set(raw_data.get("benchmark_ids") or set())
        ),
        "latest_source_status": latest_source_status,
        "latest_attempted_at": latest_attempted_at,
        "latest_success_at": latest_success_at,
        "latest_failure_at": latest_failure_at,
        "latest_error": latest_failure.get("error_message") if latest_failure is not None else None,
        "latest_model_score_at": latest_model_score_at,
        "latest_model_raw_record_at": latest_model_raw_record_at,
        "has_model_score": has_model_score,
        "has_model_raw_record": has_model_raw_record,
        "model_evidence_status": model_evidence_status,
        "degraded": degraded,
        "stale": model_evidence_status == "stale",
        "missing_because_source_failed": model_evidence_status == "missing_source_failed",
    }


def _source_run_timestamp(row: dict[str, Any] | None) -> str | None:
    if row is None:
        return None
    return str(row.get("completed_at") or row.get("started_at") or "") or None


def _source_run_is_newer(row: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if current is None:
        return True
    return (
        str(row.get("completed_at") or row.get("started_at") or ""),
        int(row.get("id") or 0),
    ) > (
        str(current.get("completed_at") or current.get("started_at") or ""),
        int(current.get("id") or 0),
    )


def list_providers() -> list[dict[str, Any]]:
    bootstrap()
    with get_connection(ENGINE) as conn:
        rows = fetch_all(
            conn,
            select(providers_table)
            .where(providers_table.c.active == 1)
            .order_by(providers_table.c.name.asc()),
        )
    return [_serialize_provider(row) for row in rows]


def _load_origin_countries(value: Any, fallback_country_code: str | None = None, fallback_country_name: str | None = None) -> list[dict[str, str | None]]:
    raw_value = value
    if isinstance(raw_value, str):
        try:
            raw_value = json.loads(raw_value)
        except json.JSONDecodeError:
            raw_value = []
    if raw_value is None:
        raw_value = []
    if not isinstance(raw_value, list):
        raise ValueError("origin_countries must be a list.")
    return normalize_origin_countries(raw_value, fallback_country_code, fallback_country_name)


def update_provider_origin(provider_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    bootstrap()
    normalized_values: dict[str, Any] = {}
    for field in ("country_code", "country_name", "origin_basis", "source_url", "verified_at"):
        if field not in payload:
            continue
        normalized_values[field] = _clean_text(payload.get(field))

    if "country_code" in normalized_values and normalized_values["country_code"] is not None:
        normalized_values["country_code"] = normalized_values["country_code"].upper()
        if len(normalized_values["country_code"]) != 2 or not normalized_values["country_code"].isalpha():
            raise ValueError("country_code must be a 2-letter ISO country code.")

    if "origin_countries" in payload:
        origin_countries = _load_origin_countries(
            payload.get("origin_countries"),
            normalized_values.get("country_code"),
            normalized_values.get("country_name"),
        )
        country_code, country_name = derive_provider_origin_fields(origin_countries)
        normalized_values["origin_countries_json"] = json.dumps(origin_countries, separators=(",", ":"))
        normalized_values["country_code"] = country_code
        normalized_values["country_name"] = country_name
    elif "country_code" in normalized_values or "country_name" in normalized_values:
        origin_countries = normalize_origin_countries(
            [],
            normalized_values.get("country_code"),
            normalized_values.get("country_name"),
        )
        country_code, country_name = derive_provider_origin_fields(origin_countries)
        normalized_values["origin_countries_json"] = json.dumps(origin_countries, separators=(",", ":"))
        normalized_values["country_code"] = country_code
        normalized_values["country_name"] = country_name

    with ENGINE.begin() as conn:
        existing = fetch_one(
            conn,
            select(providers_table).where(providers_table.c.id == provider_id),
        )
        if existing is None:
            return None

        if normalized_values:
            conn.execute(
                update(providers_table)
                .where(providers_table.c.id == provider_id)
                .values(**normalized_values)
            )
        updated = fetch_one(
            conn,
            select(providers_table).where(providers_table.c.id == provider_id),
        )

    export_provider_origin_baseline(ENGINE)
    return _serialize_provider(updated) if updated is not None else None


def _sync_legacy_model_approval_columns(conn, model_id: str) -> dict[str, Any] | None:
    approval_rows = fetch_all(
        conn,
        select(model_use_case_approvals_table).where(model_use_case_approvals_table.c.model_id == model_id),
    )
    approvals = {
        str(row["use_case_id"]): _serialize_use_case_approval(row)
        for row in approval_rows
        if str(row.get("use_case_id") or "").strip()
    }
    summary = _approval_summary_from_use_case_approvals(approvals)
    conn.execute(
        update(models_table)
        .where(models_table.c.id == model_id)
        .values(
            approved_for_use=1 if summary["approved_for_use"] else 0,
            approval_notes=summary["approval_notes"],
            approval_updated_at=summary["approval_updated_at"],
        )
    )
    return fetch_one(conn, select(models_table).where(models_table.c.id == model_id))


def _migrate_legacy_model_approvals() -> None:
    use_case_ids = _all_use_case_ids()
    if not use_case_ids:
        return

    with ENGINE.begin() as conn:
        legacy_rows = fetch_all(
            conn,
            select(models_table.c.id, models_table.c.approved_for_use, models_table.c.approval_notes, models_table.c.approval_updated_at)
            .where(models_table.c.active == 1)
            .where(models_table.c.approved_for_use == 1),
        )
        pending_rows: list[dict[str, Any]] = []
        for row in legacy_rows:
            model_id = str(row.get("id") or "").strip()
            if not model_id:
                continue
            existing_count = conn.execute(
                select(func.count())
                .select_from(model_use_case_approvals_table)
                .where(model_use_case_approvals_table.c.model_id == model_id)
            ).scalar_one()
            if int(existing_count or 0) > 0:
                continue
            for use_case_id in use_case_ids:
                pending_rows.append(
                    {
                        "model_id": model_id,
                        "use_case_id": use_case_id,
                        "approved_for_use": 1,
                        "approval_notes": _clean_text(row.get("approval_notes")),
                        "approval_updated_at": row.get("approval_updated_at") or utc_now_iso(),
                    }
                )

        if pending_rows:
            stmt = sqlite_insert(model_use_case_approvals_table).values(pending_rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["model_id", "use_case_id"])
            conn.execute(stmt)


def _load_model_update_context(conn, model_ids: list[str]) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, dict[str, Any]]],
    dict[str, dict[str, dict[str, Any]]],
    dict[str, dict[str, list[dict[str, Any]]]],
    dict[str, list[dict[str, Any]]],
    set[str],
]:
    provider_rows = fetch_all(conn, select(providers_table).where(providers_table.c.active == 1))
    providers_by_id = {str(row["id"]): _serialize_provider(row) for row in provider_rows}
    providers_by_name = {
        normalize_text(str(row["name"])): _serialize_provider(row)
        for row in provider_rows
        if str(row.get("name") or "").strip()
    }
    approvals_by_model_id = _load_model_use_case_approvals(conn, model_ids)
    recommendation_proposals_by_model_id = _load_model_use_case_recommendation_proposals(conn, model_ids)
    inference_approvals_by_model_id = _load_model_use_case_inference_approvals(conn, model_ids)
    inference_rows_by_model = load_synced_inference_catalog(conn, model_ids)
    authoritative_destination_ids = load_authoritative_destination_ids(conn)
    return (
        providers_by_id,
        providers_by_name,
        approvals_by_model_id,
        recommendation_proposals_by_model_id,
        inference_approvals_by_model_id,
        inference_rows_by_model,
        authoritative_destination_ids,
    )


def _load_serialized_model_for_response(conn, model_id: str) -> dict[str, Any] | None:
    existing = fetch_one(conn, select(models_table).where(models_table.c.id == model_id))
    if existing is None:
        return None
    (
        providers_by_id,
        providers_by_name,
        approvals_by_model_id,
        recommendation_proposals_by_model_id,
        inference_approvals_by_model_id,
        inference_rows_by_model,
        authoritative_destination_ids,
    ) = _load_model_update_context(conn, [model_id])
    model = _serialize_model(
        existing,
        provider_metadata=_resolve_provider_metadata(existing, providers_by_id, providers_by_name),
        use_case_approvals=approvals_by_model_id.get(model_id, {}),
        recommendation_proposals=recommendation_proposals_by_model_id.get(model_id, {}),
        inference_route_approvals=inference_approvals_by_model_id.get(model_id, {}),
    )
    model = attach_inference_catalog(
        model,
        synced_destinations=inference_rows_by_model.get(model_id),
        authoritative_destinations=authoritative_destination_ids,
    )
    _attach_inference_route_destination_metadata(model)
    return model


def update_model_use_case_approval(
    model_id: str,
    use_case_id: str,
    approved_for_use: bool,
    approval_notes: str | None,
    recommendation_status: str | None = None,
    recommendation_notes: str | None = None,
) -> dict[str, Any] | None:
    bootstrap()
    if _get_base_use_case(use_case_id) is None:
        raise ValueError("Use case not found")

    cleaned_notes = _clean_text(approval_notes)
    updated_at = utc_now_iso()

    with ENGINE.begin() as conn:
        existing = fetch_one(conn, select(models_table).where(models_table.c.id == model_id))
        if existing is None:
            return None
        existing_approval = fetch_one(
            conn,
            select(model_use_case_approvals_table).where(
                model_use_case_approvals_table.c.model_id == model_id,
                model_use_case_approvals_table.c.use_case_id == use_case_id,
            ),
        )
        normalized_recommendation_status = _normalize_recommendation_status(
            recommendation_status if recommendation_status is not None else (existing_approval or {}).get("recommendation_status")
        )
        cleaned_recommendation_notes = _clean_text(
            recommendation_notes if recommendation_notes is not None else (existing_approval or {}).get("recommendation_notes")
        )
        recommendation_updated_at = (
            updated_at
            if recommendation_status is not None or recommendation_notes is not None
            else (existing_approval or {}).get("recommendation_updated_at")
        )

        stmt = sqlite_insert(model_use_case_approvals_table).values(
            model_id=model_id,
            use_case_id=use_case_id,
            approved_for_use=1 if approved_for_use else 0,
            approval_notes=cleaned_notes,
            approval_updated_at=updated_at,
            recommendation_status=normalized_recommendation_status,
            recommendation_notes=cleaned_recommendation_notes,
            recommendation_updated_at=recommendation_updated_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["model_id", "use_case_id"],
            set_={
                "approved_for_use": stmt.excluded.approved_for_use,
                "approval_notes": stmt.excluded.approval_notes,
                "approval_updated_at": stmt.excluded.approval_updated_at,
                "recommendation_status": stmt.excluded.recommendation_status,
                "recommendation_notes": stmt.excluded.recommendation_notes,
                "recommendation_updated_at": stmt.excluded.recommendation_updated_at,
            },
        )
        conn.execute(stmt)
        updated = _sync_legacy_model_approval_columns(conn, model_id)
        (
            providers_by_id,
            providers_by_name,
            approvals_by_model_id,
            recommendation_proposals_by_model_id,
            inference_approvals_by_model_id,
            inference_rows_by_model,
            authoritative_destination_ids,
        ) = _load_model_update_context(conn, [model_id])

    if updated is None:
        return None

    model = _serialize_model(
        updated,
        provider_metadata=_resolve_provider_metadata(updated, providers_by_id, providers_by_name),
        use_case_approvals=approvals_by_model_id.get(model_id, {}),
        recommendation_proposals=recommendation_proposals_by_model_id.get(model_id, {}),
        inference_route_approvals=inference_approvals_by_model_id.get(model_id, {}),
    )
    model = attach_inference_catalog(
        model,
        synced_destinations=inference_rows_by_model.get(model_id),
        authoritative_destinations=authoritative_destination_ids,
    )
    _attach_inference_route_destination_metadata(model)
    return _model_summary(model)


def curate_model_identity(
    model_id: str,
    target_model_id: str,
    *,
    variant_label: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    bootstrap()
    normalized_model_id = str(model_id or "").strip()
    normalized_target_model_id = str(target_model_id or "").strip()
    if not normalized_model_id or not normalized_target_model_id:
        raise ValueError("Both source and target model ids are required.")
    if normalized_model_id == normalized_target_model_id:
        raise ValueError("Choose a different model to copy family identity from.")

    cleaned_variant_label = _clean_text(variant_label)
    cleaned_notes = _clean_text(notes)
    updated_at = utc_now_iso()

    with ENGINE.begin() as conn:
        source = fetch_one(conn, select(models_table).where(models_table.c.id == normalized_model_id))
        target = fetch_one(conn, select(models_table).where(models_table.c.id == normalized_target_model_id))
        if source is None:
            return None
        if target is None:
            raise ValueError("Target model not found.")
        if not all(
            (
                str(target.get("family_id") or "").strip(),
                str(target.get("family_name") or "").strip(),
                str(target.get("canonical_model_id") or "").strip(),
                str(target.get("canonical_model_name") or "").strip(),
            )
        ):
            raise ValueError("Target model is missing family/canonical identity metadata.")

        match_provider = str(source.get("provider") or "").strip() or "Unknown"
        match_name = str(source.get("name") or "").strip()
        if not match_name:
            raise ValueError("Source model is missing a name.")
        match_key = build_model_curation_match_key(match_provider, match_name)
        if not match_key:
            raise ValueError("Could not derive a durable match key for this model.")

        override_values = {
            "source_model_id": normalized_model_id,
            "match_provider": match_provider,
            "match_name": match_name,
            "match_key": match_key,
            "family_id": str(target["family_id"]),
            "family_name": str(target["family_name"]),
            "canonical_model_id": str(target["canonical_model_id"]),
            "canonical_model_name": str(target["canonical_model_name"]),
            "variant_label": cleaned_variant_label if variant_label is not None else _clean_text(source.get("variant_label")),
            "notes": cleaned_notes,
            "updated_at": updated_at,
            "active": 1,
        }
        stmt = sqlite_insert(model_identity_overrides_table).values(**override_values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_model_id"],
            set_={
                "match_provider": stmt.excluded.match_provider,
                "match_name": stmt.excluded.match_name,
                "match_key": stmt.excluded.match_key,
                "family_id": stmt.excluded.family_id,
                "family_name": stmt.excluded.family_name,
                "canonical_model_id": stmt.excluded.canonical_model_id,
                "canonical_model_name": stmt.excluded.canonical_model_name,
                "variant_label": stmt.excluded.variant_label,
                "notes": stmt.excluded.notes,
                "updated_at": stmt.excluded.updated_at,
                "active": stmt.excluded.active,
            },
        )
        conn.execute(stmt)
        conn.execute(
            update(model_duplicate_overrides_table)
            .where(model_duplicate_overrides_table.c.source_model_id == normalized_model_id)
            .values(active=0)
        )
        conn.execute(
            update(models_table)
            .where(models_table.c.id == normalized_model_id)
            .values(
                family_id=override_values["family_id"],
                family_name=override_values["family_name"],
                canonical_model_id=override_values["canonical_model_id"],
                canonical_model_name=override_values["canonical_model_name"],
                variant_label=override_values["variant_label"],
            )
        )
        model = _load_serialized_model_for_response(conn, normalized_model_id)

    export_model_curation_baseline(ENGINE)
    return _model_summary(model) if model is not None else None


def merge_model_duplicate(
    model_id: str,
    target_model_id: str,
    *,
    notes: str | None = None,
) -> dict[str, Any] | None:
    bootstrap()
    normalized_model_id = str(model_id or "").strip()
    normalized_target_model_id = str(target_model_id or "").strip()
    if not normalized_model_id or not normalized_target_model_id:
        raise ValueError("Both source and target model ids are required.")
    if normalized_model_id == normalized_target_model_id:
        raise ValueError("Choose a different model to merge into.")

    cleaned_notes = _clean_text(notes)
    updated_at = utc_now_iso()

    with ENGINE.begin() as conn:
        source = fetch_one(conn, select(models_table).where(models_table.c.id == normalized_model_id))
        target = fetch_one(conn, select(models_table).where(models_table.c.id == normalized_target_model_id))
        if source is None:
            return None
        if target is None:
            raise ValueError("Target model not found.")
        match_provider = str(source.get("provider") or "").strip() or "Unknown"
        match_name = str(source.get("name") or "").strip()
        if not match_name:
            raise ValueError("Source model is missing a name.")
        match_key = build_model_curation_match_key(match_provider, match_name)
        if not match_key:
            raise ValueError("Could not derive a durable match key for this model.")

        stmt = sqlite_insert(model_duplicate_overrides_table).values(
            source_model_id=normalized_model_id,
            match_provider=match_provider,
            match_name=match_name,
            match_key=match_key,
            target_model_id=normalized_target_model_id,
            notes=cleaned_notes,
            updated_at=updated_at,
            active=1,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_model_id"],
            set_={
                "match_provider": stmt.excluded.match_provider,
                "match_name": stmt.excluded.match_name,
                "match_key": stmt.excluded.match_key,
                "target_model_id": stmt.excluded.target_model_id,
                "notes": stmt.excluded.notes,
                "updated_at": stmt.excluded.updated_at,
                "active": stmt.excluded.active,
            },
        )
        conn.execute(stmt)
        _deactivate_source_identity_override(conn, normalized_model_id)
        merged = _merge_model_into_target(conn, normalized_model_id, normalized_target_model_id)
        if not merged:
            raise ValueError("Could not merge duplicate into the selected target.")
        model = _load_serialized_model_for_response(conn, normalized_target_model_id)

    export_model_curation_baseline(ENGINE)
    return _model_summary(model) if model is not None else None


def _destination_location_entries(destination: dict[str, Any]) -> list[dict[str, str]]:
    labels = sort_inference_countries(
        [
            get_inference_country_from_region(region)
            for region in (destination.get("regions") or [])
        ]
    )
    if not labels and "global" in str(destination.get("location_scope") or "").lower():
        labels = ["Global"]
    return [
        {
            "location_key": inference_location_key(label),
            "location_label": label,
        }
        for label in labels
        if inference_location_key(label)
    ]


def _resolve_inference_route_target(
    destinations: list[dict[str, Any]],
    destination_id: str,
    location_label: str,
    location_key: str | None = None,
) -> dict[str, Any] | None:
    normalized_destination_id = str(destination_id or "").strip()
    normalized_location_label = str(location_label or "").strip()
    normalized_location_key = str(location_key or "").strip() or inference_location_key(normalized_location_label)
    if not normalized_destination_id or not normalized_location_key:
        return None

    for destination in destinations:
        if str(destination.get("id") or "").strip() != normalized_destination_id:
            continue
        for location in _destination_location_entries(destination):
            if location["location_key"] != normalized_location_key:
                continue
            return {
                "destination_id": normalized_destination_id,
                "destination_name": destination.get("name"),
                "hyperscaler": destination.get("hyperscaler"),
                "location_key": location["location_key"],
                "location_label": location["location_label"],
            }
    return None


def update_model_use_case_inference_approval(
    model_id: str,
    use_case_id: str,
    destination_id: str,
    location_label: str,
    approved_for_use: bool,
    approval_notes: str | None,
    *,
    location_key: str | None = None,
) -> dict[str, Any] | None:
    bootstrap()
    if _get_base_use_case(use_case_id) is None:
        raise ValueError("Use case not found")

    cleaned_notes = _clean_text(approval_notes)
    updated_at = utc_now_iso()

    with ENGINE.begin() as conn:
        existing = fetch_one(conn, select(models_table).where(models_table.c.id == model_id))
        if existing is None:
            return None

        (
            providers_by_id,
            providers_by_name,
            approvals_by_model_id,
            recommendation_proposals_by_model_id,
            inference_approvals_by_model_id,
            inference_rows_by_model,
            authoritative_destination_ids,
        ) = _load_model_update_context(conn, [model_id])

        model = _serialize_model(
            existing,
            provider_metadata=_resolve_provider_metadata(existing, providers_by_id, providers_by_name),
            use_case_approvals=approvals_by_model_id.get(model_id, {}),
            recommendation_proposals=recommendation_proposals_by_model_id.get(model_id, {}),
            inference_route_approvals=inference_approvals_by_model_id.get(model_id, {}),
        )
        model = attach_inference_catalog(
            model,
            synced_destinations=inference_rows_by_model.get(model_id),
            authoritative_destinations=authoritative_destination_ids,
        )
        _attach_inference_route_destination_metadata(model)

        route_target = _resolve_inference_route_target(
            model.get("inference_destinations") or [],
            destination_id,
            location_label,
            location_key,
        )
        if route_target is None:
            raise ValueError("Inference provider/location not found for this model")

        stmt = sqlite_insert(model_use_case_inference_approvals_table).values(
            model_id=model_id,
            use_case_id=use_case_id,
            destination_id=route_target["destination_id"],
            location_key=route_target["location_key"],
            location_label=route_target["location_label"],
            approved_for_use=1 if approved_for_use else 0,
            approval_notes=cleaned_notes,
            approval_updated_at=updated_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["model_id", "use_case_id", "destination_id", "location_key"],
            set_={
                "location_label": stmt.excluded.location_label,
                "approved_for_use": stmt.excluded.approved_for_use,
                "approval_notes": stmt.excluded.approval_notes,
                "approval_updated_at": stmt.excluded.approval_updated_at,
            },
        )
        conn.execute(stmt)

        base_approval = approvals_by_model_id.get(model_id, {}).get(use_case_id)
        if approved_for_use and not (base_approval or {}).get("approved_for_use"):
            base_note = _clean_text((base_approval or {}).get("approval_notes")) or (
                f"Approved via inference route approval for {route_target['destination_name']} in {route_target['location_label']}."
            )
            base_stmt = sqlite_insert(model_use_case_approvals_table).values(
                model_id=model_id,
                use_case_id=use_case_id,
                approved_for_use=1,
                approval_notes=base_note,
                approval_updated_at=updated_at,
                recommendation_status=_normalize_recommendation_status((base_approval or {}).get("recommendation_status")),
                recommendation_notes=_clean_text((base_approval or {}).get("recommendation_notes")),
                recommendation_updated_at=(base_approval or {}).get("recommendation_updated_at"),
            )
            base_stmt = base_stmt.on_conflict_do_update(
                index_elements=["model_id", "use_case_id"],
                set_={
                    "approved_for_use": 1,
                    "approval_notes": base_stmt.excluded.approval_notes,
                    "approval_updated_at": base_stmt.excluded.approval_updated_at,
                },
            )
            conn.execute(base_stmt)

        updated = _sync_legacy_model_approval_columns(conn, model_id)
        (
            providers_by_id,
            providers_by_name,
            approvals_by_model_id,
            recommendation_proposals_by_model_id,
            inference_approvals_by_model_id,
            inference_rows_by_model,
            authoritative_destination_ids,
        ) = _load_model_update_context(conn, [model_id])

    if updated is None:
        return None

    model = _serialize_model(
        updated,
        provider_metadata=_resolve_provider_metadata(updated, providers_by_id, providers_by_name),
        use_case_approvals=approvals_by_model_id.get(model_id, {}),
        recommendation_proposals=recommendation_proposals_by_model_id.get(model_id, {}),
        inference_route_approvals=inference_approvals_by_model_id.get(model_id, {}),
    )
    model = attach_inference_catalog(
        model,
        synced_destinations=inference_rows_by_model.get(model_id),
        authoritative_destinations=authoritative_destination_ids,
    )
    _attach_inference_route_destination_metadata(model)
    return _model_summary(model)


def apply_model_inference_route_approval_bulk(
    model_ids: Iterable[str],
    use_case_id: str,
    destination_id: str,
    location_label: str,
    approved_for_use: bool,
    approval_notes: str | None = None,
    *,
    location_key: str | None = None,
) -> dict[str, Any]:
    bootstrap()
    if _get_base_use_case(use_case_id) is None:
        raise ValueError("Use case not found")

    normalized_model_ids = []
    seen_model_ids = set()
    for model_id in model_ids:
        normalized_model_id = str(model_id or "").strip()
        if not normalized_model_id or normalized_model_id in seen_model_ids:
            continue
        seen_model_ids.add(normalized_model_id)
        normalized_model_ids.append(normalized_model_id)
    if not normalized_model_ids:
        raise ValueError("At least one model id is required")

    cleaned_notes = _clean_text(approval_notes)
    applied_at = utc_now_iso()

    with ENGINE.begin() as conn:
        model_rows = fetch_all(
            conn,
            select(models_table)
            .where(models_table.c.active == 1)
            .where(models_table.c.id.in_(normalized_model_ids))
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )
        if not model_rows:
            raise ValueError("No active models matched the requested ids")

        (
            providers_by_id,
            providers_by_name,
            approvals_by_model_id,
            recommendation_proposals_by_model_id,
            inference_approvals_by_model_id,
            inference_rows_by_model,
            authoritative_destination_ids,
        ) = _load_model_update_context(conn, [str(row["id"]) for row in model_rows])

        pending_rows: list[dict[str, Any]] = []
        base_rows: list[dict[str, Any]] = []
        updated_model_ids: list[str] = []
        route_target_summary: dict[str, Any] | None = None

        for row in model_rows:
            model_id = str(row["id"])
            model = _serialize_model(
                row,
                provider_metadata=_resolve_provider_metadata(row, providers_by_id, providers_by_name),
                use_case_approvals=approvals_by_model_id.get(model_id, {}),
                recommendation_proposals=recommendation_proposals_by_model_id.get(model_id, {}),
                inference_route_approvals=inference_approvals_by_model_id.get(model_id, {}),
            )
            model = attach_inference_catalog(
                model,
                synced_destinations=inference_rows_by_model.get(model_id),
                authoritative_destinations=authoritative_destination_ids,
            )
            _attach_inference_route_destination_metadata(model)

            route_target = _resolve_inference_route_target(
                model.get("inference_destinations") or [],
                destination_id,
                location_label,
                location_key,
            )
            if route_target is None:
                continue

            route_target_summary = route_target
            pending_rows.append(
                {
                    "model_id": model_id,
                    "use_case_id": use_case_id,
                    "destination_id": route_target["destination_id"],
                    "location_key": route_target["location_key"],
                    "location_label": route_target["location_label"],
                    "approved_for_use": 1 if approved_for_use else 0,
                    "approval_notes": cleaned_notes,
                    "approval_updated_at": applied_at,
                }
            )
            updated_model_ids.append(model_id)

            base_approval = approvals_by_model_id.get(model_id, {}).get(use_case_id)
            if approved_for_use and not (base_approval or {}).get("approved_for_use"):
                base_note = _clean_text((base_approval or {}).get("approval_notes")) or (
                    f"Approved via inference route approval for {route_target['destination_name']} in {route_target['location_label']}."
                )
                base_rows.append(
                    {
                        "model_id": model_id,
                        "use_case_id": use_case_id,
                        "approved_for_use": 1,
                        "approval_notes": base_note,
                        "approval_updated_at": applied_at,
                        "recommendation_status": _normalize_recommendation_status((base_approval or {}).get("recommendation_status")),
                        "recommendation_notes": _clean_text((base_approval or {}).get("recommendation_notes")),
                        "recommendation_updated_at": (base_approval or {}).get("recommendation_updated_at"),
                    }
                )

        if pending_rows:
            stmt = sqlite_insert(model_use_case_inference_approvals_table).values(pending_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["model_id", "use_case_id", "destination_id", "location_key"],
                set_={
                    "location_label": stmt.excluded.location_label,
                    "approved_for_use": stmt.excluded.approved_for_use,
                    "approval_notes": stmt.excluded.approval_notes,
                    "approval_updated_at": stmt.excluded.approval_updated_at,
                },
            )
            conn.execute(stmt)

        if base_rows:
            base_stmt = sqlite_insert(model_use_case_approvals_table).values(base_rows)
            base_stmt = base_stmt.on_conflict_do_update(
                index_elements=["model_id", "use_case_id"],
                set_={
                    "approved_for_use": 1,
                    "approval_notes": base_stmt.excluded.approval_notes,
                    "approval_updated_at": base_stmt.excluded.approval_updated_at,
                },
            )
            conn.execute(base_stmt)

        for model_id in updated_model_ids:
            _sync_legacy_model_approval_columns(conn, model_id)

    route_target_summary = route_target_summary or {
        "destination_id": str(destination_id or "").strip(),
        "destination_name": None,
        "hyperscaler": None,
        "location_key": str(location_key or "").strip() or inference_location_key(location_label),
        "location_label": str(location_label or "").strip(),
    }

    return {
        "use_case_id": use_case_id,
        "destination_id": route_target_summary["destination_id"],
        "destination_name": route_target_summary.get("destination_name"),
        "hyperscaler": route_target_summary.get("hyperscaler"),
        "location_key": route_target_summary["location_key"],
        "location_label": route_target_summary["location_label"],
        "approved_for_use": bool(approved_for_use),
        "approval_notes": cleaned_notes,
        "updated_count": len(updated_model_ids),
        "updated_model_ids": updated_model_ids,
        "applied_at": applied_at,
    }


def update_model_approval(model_id: str, approved_for_use: bool, approval_notes: str | None) -> dict[str, Any] | None:
    use_case_ids = _all_use_case_ids()
    if not use_case_ids:
        return None
    result = None
    for use_case_id in use_case_ids:
        result = update_model_use_case_approval(model_id, use_case_id, approved_for_use, approval_notes)
    return result


def _normalize_use_case_ids(use_case_ids: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    for use_case_id in (use_case_ids or []):
        candidate = str(use_case_id or "").strip()
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def apply_model_family_approval_bulk(
    family_id: str,
    use_case_ids: Iterable[str],
    approval_notes: str | None = None,
    *,
    scope: str = "family",
) -> dict[str, Any] | None:
    bootstrap()

    normalized_family_id = str(family_id or "").strip()
    if not normalized_family_id:
        raise ValueError("Family id is required")

    normalized_use_case_ids = _normalize_use_case_ids(use_case_ids)
    if not normalized_use_case_ids:
        raise ValueError("At least one use case is required")
    invalid_use_case_ids = [use_case_id for use_case_id in normalized_use_case_ids if _get_base_use_case(use_case_id) is None]
    if invalid_use_case_ids:
        raise ValueError(f"Unknown use case: {invalid_use_case_ids[0]}")

    normalized_scope = str(scope or "family").strip().lower()
    if normalized_scope not in {"family", "delta"}:
        raise ValueError("Scope must be either 'family' or 'delta'.")

    cleaned_notes = _clean_text(approval_notes)
    applied_at = utc_now_iso()

    with ENGINE.begin() as conn:
        family_rows = fetch_all(
            conn,
            select(models_table)
            .where(models_table.c.active == 1)
            .where(models_table.c.family_id == normalized_family_id)
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )
        if not family_rows:
            return None

        family_name = str(family_rows[0].get("family_name") or "") or None
        model_ids = [str(row["id"]) for row in family_rows]
        approvals_by_model_id = _load_model_use_case_approvals(conn, model_ids)
        changed_model_ids: set[str] = set()
        results: list[dict[str, Any]] = []

        for use_case_id in normalized_use_case_ids:
            reference_approved_ids = sorted(
                model_id
                for model_id in model_ids
                if approvals_by_model_id.get(model_id, {}).get(use_case_id, {}).get("approved_for_use")
            )

            if normalized_scope == "delta":
                if not reference_approved_ids:
                    results.append(
                        {
                            "use_case_id": use_case_id,
                            "updated_count": 0,
                            "candidate_count": 0,
                            "reference_approved_count": 0,
                            "updated_model_ids": [],
                            "skipped_reason": "No approved reference models exist in this family for the selected use case.",
                        }
                    )
                    continue
                candidate_rows = [
                    row
                    for row in family_rows
                    if row.get("discovered_update_log_id") is not None
                    and approvals_by_model_id.get(str(row["id"]), {}).get(use_case_id) is None
                ]
                applied_notes = cleaned_notes or (
                    f"Approved via family delta for {family_name or normalized_family_id} based on existing approved family members."
                )
                if candidate_rows:
                    pending_rows = [
                        {
                            "model_id": str(row["id"]),
                            "use_case_id": use_case_id,
                            "approved_for_use": 1,
                            "approval_notes": applied_notes,
                            "approval_updated_at": applied_at,
                        }
                        for row in candidate_rows
                    ]
                    stmt = sqlite_insert(model_use_case_approvals_table).values(pending_rows)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["model_id", "use_case_id"])
                    conn.execute(stmt)
                    for row in candidate_rows:
                        model_id = str(row["id"])
                        approvals_by_model_id.setdefault(model_id, {})[use_case_id] = {
                            "use_case_id": use_case_id,
                            "approved_for_use": True,
                            "approval_notes": applied_notes,
                            "approval_updated_at": applied_at,
                        }
                        changed_model_ids.add(model_id)
                results.append(
                    {
                        "use_case_id": use_case_id,
                        "updated_count": len(candidate_rows),
                        "candidate_count": len(candidate_rows),
                        "reference_approved_count": len(reference_approved_ids),
                        "updated_model_ids": [str(row["id"]) for row in candidate_rows],
                        "skipped_reason": None,
                    }
                )
                continue

            candidate_rows = [
                row
                for row in family_rows
                if not approvals_by_model_id.get(str(row["id"]), {}).get(use_case_id, {}).get("approved_for_use")
            ]
            applied_notes = cleaned_notes or (
                f"Approved across the full {family_name or normalized_family_id} family."
            )
            if candidate_rows:
                pending_rows = [
                    {
                        "model_id": str(row["id"]),
                        "use_case_id": use_case_id,
                        "approved_for_use": 1,
                        "approval_notes": applied_notes,
                        "approval_updated_at": applied_at,
                    }
                    for row in candidate_rows
                ]
                stmt = sqlite_insert(model_use_case_approvals_table).values(pending_rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["model_id", "use_case_id"],
                    set_={
                        "approved_for_use": stmt.excluded.approved_for_use,
                        "approval_notes": stmt.excluded.approval_notes,
                        "approval_updated_at": stmt.excluded.approval_updated_at,
                    },
                )
                conn.execute(stmt)
                for row in candidate_rows:
                    model_id = str(row["id"])
                    approvals_by_model_id.setdefault(model_id, {})[use_case_id] = {
                        "use_case_id": use_case_id,
                        "approved_for_use": True,
                        "approval_notes": applied_notes,
                        "approval_updated_at": applied_at,
                    }
                    changed_model_ids.add(model_id)
            results.append(
                {
                    "use_case_id": use_case_id,
                    "updated_count": len(candidate_rows),
                    "candidate_count": len(candidate_rows),
                    "reference_approved_count": len(reference_approved_ids),
                    "updated_model_ids": [str(row["id"]) for row in candidate_rows],
                    "skipped_reason": None,
                }
            )

        for model_id in sorted(changed_model_ids):
            _sync_legacy_model_approval_columns(conn, model_id)

    return {
        "family_id": normalized_family_id,
        "family_name": family_name,
        "scope": normalized_scope,
        "use_case_ids": normalized_use_case_ids,
        "total_updated_count": sum(int(result.get("updated_count") or 0) for result in results),
        "results": results,
        "approval_notes": cleaned_notes,
        "applied_at": applied_at,
    }


def apply_model_family_approval_delta(
    family_id: str,
    use_case_id: str,
    approval_notes: str | None = None,
) -> dict[str, Any] | None:
    result = apply_model_family_approval_bulk(
        family_id,
        [use_case_id],
        approval_notes,
        scope="delta",
    )
    if result is None:
        return None
    use_case_result = (result.get("results") or [{}])[0]
    skipped_reason = _clean_text(use_case_result.get("skipped_reason"))
    if skipped_reason:
        raise ValueError(skipped_reason)
    return {
        "family_id": result["family_id"],
        "family_name": result.get("family_name"),
        "use_case_id": use_case_id,
        "updated_count": int(use_case_result.get("updated_count") or 0),
        "candidate_count": int(use_case_result.get("candidate_count") or 0),
        "reference_approved_count": int(use_case_result.get("reference_approved_count") or 0),
        "updated_model_ids": list(use_case_result.get("updated_model_ids") or []),
        "approval_notes": result.get("approval_notes"),
        "applied_at": result.get("applied_at"),
    }


def update_use_case_internal_weight(use_case_id: str, weight: float) -> dict[str, Any] | None:
    bootstrap()
    if _get_base_use_case(use_case_id) is None:
        return None

    normalized_weight = max(0.0, min(1.0, float(weight)))
    with ENGINE.begin() as conn:
        if normalized_weight <= 0:
            conn.execute(
                delete(use_case_benchmark_weights_table).where(
                    use_case_benchmark_weights_table.c.use_case_id == use_case_id,
                    use_case_benchmark_weights_table.c.benchmark_id == INTERNAL_VIEW_BENCHMARK_ID,
                )
            )
        else:
            stmt = sqlite_insert(use_case_benchmark_weights_table).values(
                use_case_id=use_case_id,
                benchmark_id=INTERNAL_VIEW_BENCHMARK_ID,
                weight=normalized_weight,
                updated_at=utc_now_iso(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["use_case_id", "benchmark_id"],
                set_={"weight": stmt.excluded.weight, "updated_at": stmt.excluded.updated_at},
            )
            conn.execute(stmt)

    return _get_use_case(use_case_id)


def update_manual_benchmark_score(
    model_id: str,
    benchmark_id: str,
    *,
    value: float | None,
    raw_value: str | None = None,
    notes: str | None = None,
    source_url: str | None = None,
    verified: bool = False,
) -> dict[str, Any] | None:
    bootstrap()
    with ENGINE.begin() as conn:
        model_row = fetch_one(conn, select(models_table).where(models_table.c.id == model_id))
        if model_row is None:
            return None

        benchmark_row = fetch_one(conn, select(benchmarks_table).where(benchmarks_table.c.id == benchmark_id))
        if benchmark_row is None:
            return None

        if str(benchmark_row.get("source") or "").strip().lower() != "internal":
            raise ValueError("Only internal manual benchmarks can be edited from Admin.")

        conn.execute(
            delete(scores_table).where(
                scores_table.c.model_id == model_id,
                scores_table.c.benchmark_id == benchmark_id,
                scores_table.c.source_type == "manual",
            )
        )

        score_payload = None
        if value is not None:
            collected_at = utc_now_iso()
            cleaned_notes = _clean_text(notes)
            cleaned_source_url = _clean_text(source_url)
            cleaned_raw_value = _clean_text(raw_value) or str(value)
            conn.execute(
                insert(scores_table).values(
                    model_id=model_id,
                    benchmark_id=benchmark_id,
                    value=float(value),
                    raw_value=cleaned_raw_value,
                    collected_at=collected_at,
                    source_url=cleaned_source_url,
                    source_type="manual",
                    verified=1 if verified else 0,
                    notes=cleaned_notes,
                )
            )
            score_payload = {
                "value": float(value),
                "raw_value": cleaned_raw_value,
                "collected_at": collected_at,
                "source_url": cleaned_source_url,
                "source_type": "manual",
                "verified": bool(verified),
                "notes": cleaned_notes,
                "variant_model_id": None,
                "variant_model_name": None,
            }

    return {
        "model_id": model_id,
        "benchmark_id": benchmark_id,
        "score": score_payload,
    }


def _build_canonical_models(
    models: list[dict[str, Any]],
    benchmarks_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for model in models:
        canonical_id = str(model.get("canonical_model_id") or model["id"])
        group = groups.setdefault(
            canonical_id,
            {
                "canonical_id": canonical_id,
                "canonical_name": model.get("canonical_model_name") or model["name"],
                "family_id": model.get("family_id"),
                "family_name": model.get("family_name"),
                "provider": model["provider"],
                "members": [],
            },
        )
        group["members"].append(model)
        if not group["family_id"] and model.get("family_id"):
            group["family_id"] = model["family_id"]
        if not group["family_name"] and model.get("family_name"):
            group["family_name"] = model["family_name"]
        if (
            model.get("canonical_model_name")
            and _readable_name_score(str(model["canonical_model_name"])) > _readable_name_score(str(group["canonical_name"]))
        ):
            group["canonical_name"] = model["canonical_model_name"]

    payload: list[dict[str, Any]] = []
    for group in groups.values():
        representative = _choose_group_representative(group["members"], str(group["canonical_name"]))
        aggregated_use_case_approvals = _aggregate_use_case_approvals(group["members"])
        approval_summary = _approval_summary_from_use_case_approvals(aggregated_use_case_approvals)
        benchmark_ids = {
            benchmark_id
            for member in group["members"]
            for benchmark_id in (member.get("scores") or {}).keys()
        }
        scores: dict[str, dict[str, Any] | None] = {}
        for benchmark_id in benchmark_ids:
            benchmark = benchmarks_by_id.get(benchmark_id)
            best_entry: tuple[dict[str, Any], dict[str, Any]] | None = None
            for member in group["members"]:
                score = (member.get("scores") or {}).get(benchmark_id)
                if not score or score.get("value") is None:
                    continue
                if best_entry is None or _is_better_benchmark_score(score, best_entry[1], benchmark):
                    best_entry = (member, score)

            if best_entry is None:
                scores[benchmark_id] = None
                continue

            member, score = best_entry
            aggregated = dict(score)
            aggregated["variant_model_id"] = member["id"]
            aggregated["variant_model_name"] = member["name"]
            scores[benchmark_id] = aggregated

        canonical_model = {
            **representative,
            "id": group["canonical_id"],
            "name": group["canonical_name"] or representative["name"],
            "family_id": group["family_id"] or representative.get("family_id"),
            "family_name": group["family_name"] or representative.get("family_name"),
            "canonical_model_id": group["canonical_id"],
            "canonical_model_name": group["canonical_name"] or representative["name"],
            "approved_for_use": approval_summary["approved_for_use"],
            "approval_use_case_count": approval_summary["approval_use_case_count"],
            "use_case_approvals": aggregated_use_case_approvals,
            "approval_notes": approval_summary["approval_notes"],
            "approval_updated_at": approval_summary["approval_updated_at"],
            "scores": scores,
        }
        payload.append(canonical_model)

    payload.sort(
        key=lambda item: (
            str(item.get("provider") or ""),
            str(item.get("canonical_model_name") or item["name"]).lower(),
            str(item["id"]),
        )
    )
    return payload


def _aggregate_use_case_approvals(members: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    approval_keys = {
        str(use_case_id)
        for member in members
        for use_case_id in (member.get("use_case_approvals") or {}).keys()
    }
    aggregated: dict[str, dict[str, Any]] = {}
    for use_case_id in sorted(approval_keys):
        entries = [
            member.get("use_case_approvals", {}).get(use_case_id)
            for member in members
            if member.get("use_case_approvals", {}).get(use_case_id) is not None
        ]
        if not entries:
            continue
        latest_entry = max(entries, key=lambda item: str(item.get("approval_updated_at") or ""))
        latest_recommendation_entry = max(entries, key=lambda item: str(item.get("recommendation_updated_at") or ""))
        approved_member_count = sum(1 for entry in entries if entry.get("approved_for_use"))
        recommended_member_count = sum(
            1 for entry in entries if _normalize_recommendation_status(entry.get("recommendation_status")) == RECOMMENDATION_STATUS_RECOMMENDED
        )
        not_recommended_member_count = sum(
            1 for entry in entries if _normalize_recommendation_status(entry.get("recommendation_status")) == RECOMMENDATION_STATUS_NOT_RECOMMENDED
        )
        discouraged_member_count = sum(
            1 for entry in entries if _normalize_recommendation_status(entry.get("recommendation_status")) == RECOMMENDATION_STATUS_DISCOURAGED
        )
        restricted_member_count = sum(
            1 for entry in entries if _normalize_recommendation_status(entry.get("recommendation_status")) == RECOMMENDATION_STATUS_RESTRICTED
        )
        auto_not_recommended_member_count = sum(
            1 for entry in entries if _normalize_recommendation_status(entry.get("auto_recommendation_status")) == RECOMMENDATION_STATUS_NOT_RECOMMENDED
        )
        distinct_proposed_recommendation_statuses = {
            _normalize_recommendation_status(entry.get("proposed_recommendation_status"))
            for entry in entries
            if _normalize_recommendation_status(entry.get("proposed_recommendation_status")) != RECOMMENDATION_STATUS_UNRATED
        }
        distinct_effective_recommendation_statuses = {
            _normalize_recommendation_status(entry.get("effective_recommendation_status"), allow_mixed=True)
            for entry in entries
            if _normalize_recommendation_status(entry.get("effective_recommendation_status"), allow_mixed=True)
            != RECOMMENDATION_STATUS_UNRATED
        }
        distinct_recommendation_statuses = {
            status
            for status in (
                RECOMMENDATION_STATUS_RECOMMENDED if recommended_member_count else "",
                RECOMMENDATION_STATUS_NOT_RECOMMENDED if not_recommended_member_count else "",
                RECOMMENDATION_STATUS_DISCOURAGED if discouraged_member_count else "",
                RECOMMENDATION_STATUS_RESTRICTED if restricted_member_count else "",
            )
            if status
        }
        aggregated_recommendation_status = (
            RECOMMENDATION_STATUS_MIXED
            if len(distinct_recommendation_statuses) > 1
            else next(iter(distinct_recommendation_statuses), RECOMMENDATION_STATUS_UNRATED)
        )
        aggregated_proposed_recommendation_status = (
            RECOMMENDATION_STATUS_MIXED
            if len(distinct_proposed_recommendation_statuses) > 1
            else next(iter(distinct_proposed_recommendation_statuses), RECOMMENDATION_STATUS_UNRATED)
        )
        aggregated_effective_recommendation_status = (
            RECOMMENDATION_STATUS_MIXED
            if len(distinct_effective_recommendation_statuses) > 1
            else next(iter(distinct_effective_recommendation_statuses), RECOMMENDATION_STATUS_UNRATED)
        )
        aggregated[use_case_id] = {
            "use_case_id": use_case_id,
            "approved_for_use": approved_member_count > 0,
            "approval_notes": latest_entry.get("approval_notes"),
            "approval_updated_at": latest_entry.get("approval_updated_at"),
            "recommendation_status": aggregated_recommendation_status,
            "recommendation_notes": latest_recommendation_entry.get("recommendation_notes"),
            "recommendation_updated_at": latest_recommendation_entry.get("recommendation_updated_at"),
            "auto_recommendation_status": (
                RECOMMENDATION_STATUS_NOT_RECOMMENDED
                if auto_not_recommended_member_count
                else RECOMMENDATION_STATUS_UNRATED
            ),
            "auto_recommendation_notes": _merge_overlay_notes(*(entry.get("auto_recommendation_notes") for entry in entries)),
            "auto_not_recommended_member_count": auto_not_recommended_member_count,
            "approval_member_count": approved_member_count,
            "approval_total_count": len(members),
            "recommended_member_count": recommended_member_count,
            "not_recommended_member_count": not_recommended_member_count,
            "discouraged_member_count": discouraged_member_count,
            "restricted_member_count": restricted_member_count,
            "proposed_recommendation_status": aggregated_proposed_recommendation_status,
            "proposed_recommendation_score": _average_numeric(
                entry.get("proposed_recommendation_score") for entry in entries
            ),
            "proposed_recommendation_confidence": _average_numeric(
                entry.get("proposed_recommendation_confidence") for entry in entries
            ),
            "proposed_recommendation_blockers": _merge_serialized_string_lists(
                *(entry.get("proposed_recommendation_blockers") for entry in entries)
            ),
            "proposed_recommendation_warnings": _merge_serialized_string_lists(
                *(entry.get("proposed_recommendation_warnings") for entry in entries)
            ),
            "proposed_recommendation_reasons": _merge_serialized_string_lists(
                *(entry.get("proposed_recommendation_reasons") for entry in entries)
            ),
            "proposed_recommendation_required_controls": _merge_serialized_string_lists(
                *(entry.get("proposed_recommendation_required_controls") for entry in entries)
            ),
            "proposed_recommendation_policy_version": _merge_overlay_notes(
                *(entry.get("proposed_recommendation_policy_version") for entry in entries)
            ),
            "proposed_recommendation_computed_at": max(
                str(entry.get("proposed_recommendation_computed_at") or "") for entry in entries
            )
            or None,
            "effective_recommendation_status": aggregated_effective_recommendation_status,
        }
    return aggregated


def _merge_serialized_string_lists(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _decode_json_string_list(value):
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return merged


def _average_numeric(values: Iterable[Any]) -> float | None:
    numeric_values: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not numeric_values:
        return None
    return sum(numeric_values) / len(numeric_values)


def _choose_group_representative(members: list[dict[str, Any]], display_name: str) -> dict[str, Any]:
    def sort_key(model: dict[str, Any]) -> tuple[Any, ...]:
        name = str(model.get("name") or model.get("id") or "")
        direct_name_match = int(name == display_name)
        metadata_fields = int(bool(model.get("release_date"))) + int(bool(model.get("context_window")))
        score_coverage = sum(
            1
            for score in (model.get("scores") or {}).values()
            if score is not None and score.get("value") is not None
        )
        return (
            -direct_name_match,
            -metadata_fields,
            -_readable_name_score(name),
            -score_coverage,
            len(name),
            str(model["id"]),
        )

    return sorted(members, key=sort_key)[0]


def _is_better_benchmark_score(
    candidate: dict[str, Any],
    current_best: dict[str, Any],
    benchmark: dict[str, Any] | None,
) -> bool:
    candidate_value = float(candidate["value"])
    current_value = float(current_best["value"])
    higher_is_better = bool(benchmark["higher_is_better"]) if benchmark is not None else True
    if candidate_value != current_value:
        return candidate_value > current_value if higher_is_better else candidate_value < current_value
    return str(candidate.get("collected_at") or "") > str(current_best.get("collected_at") or "")


def _should_refresh_model_discovery(
    selected_benchmarks: set[str],
    *,
    refresh_model_discovery: bool | None,
) -> bool:
    if refresh_model_discovery is not None:
        return bool(refresh_model_discovery)
    return not selected_benchmarks


def _update_model_change_snapshot() -> dict[str, dict[str, Any]]:
    with get_connection(ENGINE) as conn:
        rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.provider,
                models_table.c.catalog_status,
                models_table.c.model_roles_json,
                models_table.c.metadata_source_name,
                models_table.c.capabilities_json,
                models_table.c.release_date,
                models_table.c.context_window_tokens,
                models_table.c.max_output_tokens,
                models_table.c.parameter_count_b,
                models_table.c.active_parameter_count_b,
                models_table.c.model_size_class,
                models_table.c.small_model_candidate,
                models_table.c.price_input_per_mtok,
                models_table.c.price_output_per_mtok,
                models_table.c.openrouter_canonical_slug,
                models_table.c.openrouter_global_rank,
                models_table.c.openrouter_programming_rank,
                models_table.c.huggingface_repo_id,
                models_table.c.metadata_source_name,
                models_table.c.metadata_source_url,
                models_table.c.model_card_url,
                models_table.c.license_name,
                models_table.c.base_models_json,
                models_table.c.family_id,
                models_table.c.canonical_model_id,
                models_table.c.discovered_at,
            ).where(models_table.c.active == 1),
        )
    return {
        str(row["id"]): _normalize_update_model_snapshot(row)
        for row in rows
        if str(row.get("id") or "").strip()
    }


def _normalize_update_model_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "name": _clean_text(row.get("name")),
        "provider": _clean_text(row.get("provider")),
        "catalog_status": _clean_text(row.get("catalog_status")),
        "model_roles": sorted(dict.fromkeys(_decode_json_string_list(row.get("model_roles_json")))),
        "capabilities": sorted(dict.fromkeys(_decode_json_string_list(row.get("capabilities_json")))),
        "release_date": _clean_text(row.get("release_date")),
        "context_window_tokens": _optional_int(row.get("context_window_tokens")),
        "max_output_tokens": _optional_int(row.get("max_output_tokens")),
        "parameter_count_b": _optional_float(row.get("parameter_count_b")),
        "active_parameter_count_b": _optional_float(row.get("active_parameter_count_b")),
        "model_size_class": _clean_text(row.get("model_size_class")),
        "small_model_candidate": bool(row.get("small_model_candidate")),
        "price_input_per_mtok": _optional_float(row.get("price_input_per_mtok")),
        "price_output_per_mtok": _optional_float(row.get("price_output_per_mtok")),
        "openrouter_canonical_slug": _clean_text(row.get("openrouter_canonical_slug")),
        "openrouter_global_rank": _optional_int(row.get("openrouter_global_rank")),
        "openrouter_programming_rank": _optional_int(row.get("openrouter_programming_rank")),
        "huggingface_repo_id": _clean_text(row.get("huggingface_repo_id")),
        "metadata_source_name": _clean_text(row.get("metadata_source_name")),
        "metadata_source_url": _clean_text(row.get("metadata_source_url")),
        "model_card_url": _clean_text(row.get("model_card_url")),
        "license_name": _clean_text(row.get("license_name")),
        "base_models": sorted(dict.fromkeys(_decode_json_string_list(row.get("base_models_json")))),
        "family_id": _clean_text(row.get("family_id")),
        "canonical_model_id": _clean_text(row.get("canonical_model_id")),
        "discovered_at": _clean_text(row.get("discovered_at")),
    }


def _safe_update_change_summary(
    *,
    log_id: int,
    before: dict[str, dict[str, Any]] | None,
    snapshot_error: str | None = None,
) -> dict[str, Any]:
    if snapshot_error:
        try:
            model_count_after = len(_update_model_change_snapshot())
        except Exception:
            model_count_after = 0
        return {
            "generated_at": utc_now_iso(),
            "model_count_before": len(before or {}),
            "model_count_after": model_count_after,
            "model_count_delta": 0,
            "new_model_count": 0,
            "changed_model_count": 0,
            "removed_model_count": 0,
            "unchanged_model_count": 0,
            "source_record_count": 0,
            "source_failure_count": 0,
            "new_models": [],
            "changed_models": [],
            "removed_models": [],
            "truncated": {},
            "error": f"Initial catalog snapshot failed: {snapshot_error}",
        }
    try:
        after = _update_model_change_snapshot()
        return _build_update_change_summary(
            before or {},
            after,
            log_id=log_id,
        )
    except Exception as exc:
        return {
            "generated_at": utc_now_iso(),
            "model_count_before": len(before or {}),
            "model_count_after": 0,
            "model_count_delta": 0,
            "new_model_count": 0,
            "changed_model_count": 0,
            "removed_model_count": 0,
            "unchanged_model_count": 0,
            "source_record_count": 0,
            "source_failure_count": 0,
            "new_models": [],
            "changed_models": [],
            "removed_models": [],
            "truncated": {},
            "error": str(exc),
        }


def _build_update_change_summary(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    *,
    log_id: int,
) -> dict[str, Any]:
    before_ids = set(before)
    after_ids = set(after)
    new_ids = sorted(after_ids - before_ids, key=lambda model_id: _model_sort_key(after[model_id]))
    removed_ids = sorted(before_ids - after_ids, key=lambda model_id: _model_sort_key(before[model_id]))

    changed: list[tuple[str, list[dict[str, Any]]]] = []
    for model_id in sorted(before_ids & after_ids, key=lambda item: _model_sort_key(after[item])):
        field_changes = _model_field_changes(before[model_id], after[model_id])
        if field_changes:
            changed.append((model_id, field_changes))

    source_runs = list_source_runs(log_id)
    source_record_count = sum(int(source_run.get("records_found") or 0) for source_run in source_runs)
    source_failure_count = sum(1 for source_run in source_runs if source_run.get("status") == "failed")

    new_models = [_update_model_change_item(after[model_id]) for model_id in new_ids]
    changed_models = [
        _update_model_change_item(after[model_id], field_changes=field_changes)
        for model_id, field_changes in changed
    ]
    removed_models = [_update_model_change_item(before[model_id]) for model_id in removed_ids]

    return {
        "generated_at": utc_now_iso(),
        "model_count_before": len(before),
        "model_count_after": len(after),
        "model_count_delta": len(after) - len(before),
        "new_model_count": len(new_models),
        "changed_model_count": len(changed_models),
        "removed_model_count": len(removed_models),
        "unchanged_model_count": len(before_ids & after_ids) - len(changed_models),
        "source_record_count": source_record_count,
        "source_failure_count": source_failure_count,
        "new_models": new_models[:UPDATE_CHANGE_ITEM_LIMIT],
        "changed_models": changed_models[:UPDATE_CHANGE_ITEM_LIMIT],
        "removed_models": removed_models[:UPDATE_CHANGE_ITEM_LIMIT],
        "truncated": {
            "new_models": max(0, len(new_models) - UPDATE_CHANGE_ITEM_LIMIT),
            "changed_models": max(0, len(changed_models) - UPDATE_CHANGE_ITEM_LIMIT),
            "removed_models": max(0, len(removed_models) - UPDATE_CHANGE_ITEM_LIMIT),
        },
        "error": None,
    }


def _model_field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for field, label in UPDATE_MODEL_CHANGE_FIELD_LABELS.items():
        if before.get(field) == after.get(field):
            continue
        changes.append(
            {
                "field": field,
                "label": label,
                "before": before.get(field),
                "after": after.get(field),
            }
        )
    return changes


def _update_model_change_item(
    model: dict[str, Any],
    *,
    field_changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    changes = field_changes or []
    return {
        "id": model["id"],
        "name": model.get("name"),
        "provider": model.get("provider"),
        "catalog_status": model.get("catalog_status"),
        "model_roles": model.get("model_roles") or [],
        "metadata_source_name": model.get("metadata_source_name"),
        "metadata_source_url": model.get("metadata_source_url"),
        "discovered_at": model.get("discovered_at"),
        "changed_fields": [str(change.get("label") or change.get("field") or "") for change in changes],
        "field_changes": changes,
    }


def _model_sort_key(model: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(model.get("provider") or "").lower(),
        str(model.get("name") or "").lower(),
        str(model.get("id") or "").lower(),
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def schedule_update(
    benchmarks: Iterable[str] | None = None,
    triggered_by: str = "manual",
    *,
    refresh_model_discovery: bool | None = None,
) -> int:
    bootstrap()
    selected_benchmarks = {benchmark_id for benchmark_id in (benchmarks or [])}
    adapters = _selected_adapters(selected_benchmarks or None)
    include_model_discovery = _should_refresh_model_discovery(
        selected_benchmarks,
        refresh_model_discovery=refresh_model_discovery,
    )
    step_plan = _build_update_plan(adapters, include_model_discovery=include_model_discovery)

    with UPDATE_SCHEDULE_LOCK:
        active_log_id = _find_running_update_log_id()
        if active_log_id is not None:
            return active_log_id

        log_id = _create_update_log(triggered_by, step_plan)

        worker = threading.Thread(
            target=_run_update_job,
            args=(log_id, adapters, step_plan, triggered_by),
            kwargs={"refresh_model_discovery": include_model_discovery},
            daemon=True,
        )
        worker.start()
    return log_id


def run_update_sync(
    benchmarks: Iterable[str] | None = None,
    triggered_by: str = "manual",
    *,
    refresh_model_discovery: bool | None = None,
) -> int:
    bootstrap()
    selected_benchmarks = {benchmark_id for benchmark_id in (benchmarks or [])}
    adapters = _selected_adapters(selected_benchmarks or None)
    include_model_discovery = _should_refresh_model_discovery(
        selected_benchmarks,
        refresh_model_discovery=refresh_model_discovery,
    )
    step_plan = _build_update_plan(adapters, include_model_discovery=include_model_discovery)

    with UPDATE_SCHEDULE_LOCK:
        active_log_id = _find_running_update_log_id()
        if active_log_id is not None:
            return active_log_id

        log_id = _create_update_log(triggered_by, step_plan)

    _run_update_job(
        log_id,
        adapters,
        step_plan,
        triggered_by,
        refresh_model_discovery=include_model_discovery,
    )
    return log_id


def run_update_now(
    benchmarks: Iterable[str] | None = None,
    triggered_by: str = "bootstrap",
    *,
    refresh_model_discovery: bool | None = None,
) -> dict[str, Any]:
    log_id = run_update_sync(
        benchmarks=benchmarks,
        triggered_by=triggered_by,
        refresh_model_discovery=refresh_model_discovery,
    )
    log = get_update_log(log_id)
    if log is None:
        raise RuntimeError(f"Update log {log_id} was not found after sync update.")
    return log


def get_update_log(log_id: int) -> dict[str, Any] | None:
    bootstrap()
    with get_connection(ENGINE) as conn:
        row = fetch_one(
            conn,
            select(update_log_table).where(update_log_table.c.id == log_id),
        )
    if row is None:
        return None
    return _serialize_update_log(
        row,
        source_runs=list_source_runs(int(row["id"])),
        audit_summary=get_audit_summary(ENGINE, int(row["id"])),
    )


def list_update_logs() -> list[dict[str, Any]]:
    bootstrap()
    with get_connection(ENGINE) as conn:
        rows = fetch_all(
            conn,
            select(update_log_table)
            .order_by(update_log_table.c.started_at.desc(), update_log_table.c.id.desc()),
        )
    source_runs_by_log_id = _load_source_runs_by_log_id([int(row["id"]) for row in rows])
    return [
        _serialize_update_log(
            row,
            source_runs=source_runs_by_log_id.get(int(row["id"]), []),
            audit_summary=get_audit_summary(ENGINE, int(row["id"])),
        )
        for row in rows
    ]


def list_source_runs(log_id: int) -> list[dict[str, Any]]:
    bootstrap()
    with get_connection(ENGINE) as conn:
        rows = fetch_all(
            conn,
            select(source_runs_table)
            .where(source_runs_table.c.update_log_id == log_id)
            .order_by(source_runs_table.c.started_at.asc(), source_runs_table.c.id.asc()),
        )
    return [_serialize_source_run(row) for row in rows]


def list_market_snapshots(
    *,
    scope: str | None = None,
    category_slug: str | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    bootstrap()
    normalized_limit = max(1, min(int(limit), 1000))
    with get_connection(ENGINE) as conn:
        statement = (
            select(
                model_market_snapshots_table,
                models_table.c.name.label("model_name"),
                models_table.c.provider.label("provider"),
            )
            .select_from(
                model_market_snapshots_table.join(
                    models_table,
                    model_market_snapshots_table.c.model_id == models_table.c.id,
                )
            )
            .where(models_table.c.active == 1)
            .order_by(
                model_market_snapshots_table.c.snapshot_date.desc(),
                model_market_snapshots_table.c.scope.asc(),
                model_market_snapshots_table.c.category_slug.asc(),
                model_market_snapshots_table.c.rank.asc(),
                model_market_snapshots_table.c.id.asc(),
            )
            .limit(normalized_limit)
        )

        if scope:
            statement = statement.where(model_market_snapshots_table.c.scope == scope)
        if category_slug is not None:
            statement = statement.where(model_market_snapshots_table.c.category_slug == category_slug)

        rows = fetch_all(conn, statement)
    return [_serialize_market_snapshot(row) for row in rows]


def list_raw_source_records(source_run_id: int) -> list[dict[str, Any]]:
    bootstrap()
    with get_connection(ENGINE) as conn:
        rows = fetch_all(
            conn,
            select(raw_source_records_table)
            .where(raw_source_records_table.c.source_run_id == source_run_id)
            .order_by(raw_source_records_table.c.id.asc()),
        )
    return [dict(row) for row in rows]


def get_rankings(use_case_id: str) -> dict[str, Any] | None:
    bootstrap()
    use_case = _get_use_case(use_case_id)
    if use_case is None:
        return None

    benchmarks = {row["id"]: row for row in list_benchmarks()}
    models = _build_canonical_models(list_models(), benchmarks)
    return ranking_views.build_rankings_response(
        use_case=use_case,
        models=models,
        benchmarks=benchmarks,
        model_summary=_model_summary,
        min_ranking_coverage=MIN_RANKING_COVERAGE,
        coverage_exempt_benchmark_ids=INTERNAL_VIEW_COVERAGE_EXEMPT_BENCHMARK_IDS,
    )


def _run_update_job(
    log_id: int,
    adapters: list[BaseSourceAdapter],
    step_plan: list[dict[str, Any]],
    triggered_by: str,
    *,
    refresh_model_discovery: bool = True,
) -> None:
    bootstrap()
    errors: list[dict[str, Any]] = []
    scores_added = 0
    scores_updated = 0
    audit_result: dict[str, Any] | None = None
    total_steps = len(step_plan)
    current_step_index = 0
    snapshot_error: str | None = None
    try:
        model_snapshot_before = _update_model_change_snapshot()
    except Exception as exc:
        model_snapshot_before = {}
        snapshot_error = str(exc)

    try:
        with UPDATE_LOCK:
            for current_step_index, adapter in enumerate(adapters, start=1):
                step = step_plan[current_step_index - 1]
                _set_update_progress(log_id, step, current_step_index, total_steps)
                source_run_id = _start_source_run(log_id, adapter)
                try:
                    result = asyncio.run(_collect_adapter(adapter))
                    added, updated = _persist_source_result(source_run_id, result, discovered_update_log_id=log_id)
                    scores_added += added
                    scores_updated += updated
                    _finish_source_run(source_run_id, status="completed", records_found=len(result.raw_records), error_message=None)
                except Exception as exc:
                    errors.append(
                        {
                            "benchmark_id": ",".join(adapter.benchmark_ids),
                            "source_id": adapter.source_id,
                            "error_message": str(exc),
                        }
                    )
                    _finish_source_run(source_run_id, status="failed", records_found=0, error_message=str(exc))

            current_step_index = len(adapters)

            def advance_phase(expected_key: str) -> dict[str, Any]:
                nonlocal current_step_index
                current_step_index += 1
                step = step_plan[current_step_index - 1]
                actual_key = str(step.get("key") or "")
                if actual_key != expected_key:
                    raise RuntimeError(f"Expected update phase {expected_key}, found {actual_key or 'unknown'}.")
                _set_update_progress(log_id, step, current_step_index, total_steps)
                return step

            advance_phase("phase:identity-refresh-initial")
            _refresh_model_identity_metadata()

            advance_phase("phase:catalog-canonicalization")
            _canonicalize_model_catalog()

            advance_phase("phase:identity-refresh-final")
            _refresh_model_identity_metadata()

            advance_phase("phase:provider-origin-baseline")
            apply_provider_origin_baseline(ENGINE)
            _canonicalize_provider_aliases()

            advance_phase("phase:openrouter-models")
            try:
                _refresh_openrouter_model_metadata()
                if _repair_submitter_provider_leaks() > 0:
                    _refresh_model_identity_metadata()
                    _canonicalize_model_catalog()
                    _refresh_model_identity_metadata()
            except Exception as exc:
                errors.append(
                    {
                        "benchmark_id": "",
                        "source_id": "openrouter_models",
                        "error_message": str(exc),
                    }
                )

            if refresh_model_discovery:
                advance_phase("phase:model-discovery")
                try:
                    _refresh_configured_model_discovery(log_id=log_id)
                    _refresh_model_identity_metadata()
                    _canonicalize_model_catalog()
                    _refresh_model_identity_metadata()
                except Exception as exc:
                    errors.append(
                        {
                            "benchmark_id": "",
                            "source_id": HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME,
                            "error_message": str(exc),
                        }
                    )

            advance_phase("phase:model-card-metadata")
            try:
                _refresh_model_card_metadata()
                _refresh_model_license_metadata()
            except Exception as exc:
                errors.append(
                    {
                        "benchmark_id": "",
                        "source_id": "model_card_metadata",
                        "error_message": str(exc),
                    }
                )

            advance_phase("phase:openrouter-market")
            try:
                _refresh_openrouter_market_signals()
            except OptionalSourceUnavailable as exc:
                errors.append(
                    {
                        "benchmark_id": "",
                        "source_id": "openrouter_market",
                        "error_message": str(exc),
                        "severity": "warning",
                        "nonfatal": True,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "benchmark_id": "",
                        "source_id": "openrouter_market",
                        "error_message": str(exc),
                    }
                )

            advance_phase("phase:audit")
            try:
                audit_result = run_audit(ENGINE, log_id)
            except Exception as exc:
                audit_result = {
                    "status": "failed",
                    "findings": [],
                    "blocker_count": 1,
                    "warning_count": 0,
                    "info_count": 0,
                }
                errors.append(
                    {
                        "benchmark_id": "",
                        "source_id": "audit",
                        "error_message": str(exc),
                    }
                )

            advance_phase("phase:finalize")
    except Exception as exc:
        errors.append(
            {
                "benchmark_id": "",
                "source_id": "update",
                "error_message": str(exc),
            }
        )
        _finalize_update_log(
            log_id,
            status="failed",
            scores_added=scores_added,
            scores_updated=scores_updated,
            errors=errors,
            audit_result=audit_result,
            change_summary=_safe_update_change_summary(
                log_id=log_id,
                before=model_snapshot_before,
                snapshot_error=snapshot_error,
            ),
        )
        return

    final_status = "completed"
    if _has_fatal_update_errors(errors) or (audit_result is not None and audit_result.get("status") == "failed"):
        final_status = "failed"
    _finalize_update_log(
        log_id,
        status=final_status,
        scores_added=scores_added,
        scores_updated=scores_updated,
        errors=errors,
        audit_result=audit_result,
        change_summary=_safe_update_change_summary(
            log_id=log_id,
            before=model_snapshot_before,
            snapshot_error=snapshot_error,
        ),
        step=step_plan[-1] if step_plan else None,
        step_index=total_steps,
        total_steps=total_steps,
    )


def _finalize_update_log(
    log_id: int,
    *,
    status: str,
    scores_added: int,
    scores_updated: int,
    errors: list[dict[str, Any]],
    audit_result: dict[str, Any] | None,
    change_summary: dict[str, Any] | None = None,
    step: dict[str, Any] | None = None,
    step_index: int | None = None,
    total_steps: int | None = None,
) -> None:
    values: dict[str, Any] = {
        "completed_at": utc_now_iso(),
        "status": status,
        "scores_added": scores_added,
        "scores_updated": scores_updated,
        "errors": json.dumps(errors + (_audit_errors(audit_result) if audit_result else [])),
        "change_summary_json": json.dumps(change_summary or {}, ensure_ascii=True),
    }
    if step is not None:
        values.update(
            current_step_key=step.get("key"),
            current_step_label=step.get("label"),
            current_step_started_at=utc_now_iso(),
            current_step_index=step_index or 0,
            total_steps=total_steps or 0,
        )

    with ENGINE.begin() as conn:
        conn.execute(
            update(update_log_table)
            .where(update_log_table.c.id == log_id)
            .values(**values)
        )


def _has_fatal_update_errors(errors: Iterable[dict[str, Any]]) -> bool:
    return update_orchestration.has_fatal_update_errors(errors)


def _create_update_log(triggered_by: str, step_plan: list[dict[str, Any]] | None = None) -> int:
    resolved_step_plan = list(step_plan or [])
    with ENGINE.begin() as conn:
        result = conn.execute(
            insert(update_log_table).values(
                started_at=utc_now_iso(),
                completed_at=None,
                triggered_by=triggered_by,
                status="running",
                scores_added=0,
                scores_updated=0,
                errors=json.dumps([]),
                current_step_key=None,
                current_step_label=None,
                current_step_started_at=None,
                current_step_index=0,
                total_steps=len(resolved_step_plan),
                steps_json=json.dumps(resolved_step_plan),
                change_summary_json=json.dumps({}, ensure_ascii=True),
            )
        )
        return int(result.inserted_primary_key[0])


def _find_running_update_log_id() -> int | None:
    with get_connection(ENGINE) as conn:
        row = fetch_one(
            conn,
            select(update_log_table.c.id)
            .where(update_log_table.c.status == "running")
            .order_by(update_log_table.c.started_at.desc(), update_log_table.c.id.desc())
            .limit(1),
        )
    return int(row["id"]) if row is not None else None


async def _collect_adapter(adapter: BaseSourceAdapter) -> SourceFetchResult:
    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True, timeout=30.0) as client:
        return await adapter.collect(client)


def _selected_adapters(selected_benchmarks: set[str] | None) -> list[BaseSourceAdapter]:
    include_phase_two = selected_benchmarks is None or "terminal_bench" in selected_benchmarks
    adapters = get_source_adapters(include_phase_two=include_phase_two)
    if not selected_benchmarks:
        return adapters
    return [
        adapter
        for adapter in adapters
        if selected_benchmarks.intersection(adapter.benchmark_ids)
    ]


def _refresh_huggingface_model_discovery(
    *,
    log_id: int,
    family: str | None = None,
) -> dict[str, Any]:
    entries = model_discovery.huggingface_discovery_entries(family=family)
    summary = {
        "family": _clean_text(family),
        "entries": len(entries),
        "records_found": 0,
        "models_created": 0,
        "models_updated": 0,
        "models_unchanged": 0,
    }
    if not entries:
        return summary

    verified_at = utc_now_iso()
    source_run_id = _start_metadata_source_run(
        log_id,
        source_name=HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME,
        benchmark_id=_model_discovery_benchmark_id(family),
    )
    records_found = 0
    try:
        with httpx.Client(headers=HTTP_HEADERS, follow_redirects=True, timeout=30.0) as client:
            for entry in entries:
                model_roles = _normalise_model_roles(entry.get("model_roles"), default=(MODEL_ROLE_GENERATOR,))
                fetched_items = model_discovery.fetch_huggingface_discovery_items(client, entry)
                items = model_discovery.filter_huggingface_discovery_items(fetched_items, entry)
                for item in items:
                    repo_id = model_discovery.repo_id_from_huggingface_item(item)
                    if not repo_id:
                        continue
                    display_name = _suggest_display_name(repo_id.split("/", 1)[1]) or repo_id
                    provider = canonical_provider_name(
                        _clean_text(entry.get("provider")) or _provider_hint_from_name(repo_id) or "Unknown"
                    )
                    source_url = f"https://huggingface.co/{repo_id}"
                    size_metadata = model_discovery.infer_model_size_metadata(
                        repo_id,
                        display_name,
                        item.get("pipeline_tag"),
                        item.get("tags"),
                        item.get("cardData"),
                    )
                    size_values = model_discovery.model_size_values_from_metadata(
                        size_metadata,
                        source_name=HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME,
                        source_url=source_url,
                        verified_at=verified_at,
                    )
                    size_values = _apply_huggingface_discovery_size_defaults(
                        size_values,
                        entry,
                        source_url=source_url,
                        verified_at=verified_at,
                    )
                    timestamp_values = model_discovery.huggingface_timestamp_values_from_item(item)
                    model_id, outcome = _ensure_discovered_huggingface_model(
                        repo_id=repo_id,
                        display_name=display_name,
                        provider=provider,
                        source_url=source_url,
                        verified_at=verified_at,
                        discovered_update_log_id=log_id,
                        model_roles=model_roles,
                        size_values=size_values,
                        timestamp_values=timestamp_values,
                    )
                    raw_record = RawSourceRecord(
                        source_id=HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME,
                        benchmark_id=_model_discovery_benchmark_id(entry.get("family") or family),
                        raw_model_name=display_name,
                        raw_value=repo_id,
                        source_url=source_url,
                        collected_at=verified_at,
                        raw_model_key=repo_id,
                        payload=item,
                        metadata={
                            "source": "huggingface",
                            "family": _clean_text(entry.get("family")),
                            "provider": provider,
                            "huggingface_repo_id": repo_id,
                            "model_roles": model_roles,
                            **timestamp_values,
                            **size_values,
                        },
                    )
                    _insert_raw_source_record(
                        source_run_id,
                        raw_record,
                        normalized_model_id=model_id,
                        source_type="primary",
                        verified=True,
                        resolution_status="resolved",
                    )
                    records_found += 1
                    if outcome == "created":
                        summary["models_created"] += 1
                    elif outcome == "updated":
                        summary["models_updated"] += 1
                    else:
                        summary["models_unchanged"] += 1
    except Exception as exc:
        _finish_source_run(source_run_id, status="failed", records_found=records_found, error_message=str(exc))
        raise

    summary["records_found"] = records_found
    _finish_source_run(source_run_id, status="completed", records_found=records_found, error_message=None)
    return summary


def _apply_huggingface_discovery_size_defaults(
    size_values: dict[str, Any],
    entry: dict[str, Any],
    *,
    source_url: str,
    verified_at: str,
) -> dict[str, Any]:
    if not bool(entry.get("small_model_candidate_if_unknown")):
        return size_values
    if size_values.get("parameter_count_b") is not None or size_values.get("active_parameter_count_b") is not None:
        return size_values

    updated = dict(size_values)
    updated["small_model_candidate"] = 1
    updated.setdefault("model_size_class", "small")
    updated.setdefault("model_size_source_name", HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME)
    updated.setdefault("model_size_source_url", source_url)
    updated.setdefault("model_size_verified_at", verified_at)
    return updated


def _refresh_configured_model_discovery(
    *,
    log_id: int,
    source: str = "configured",
    family: str | None = None,
) -> dict[str, Any]:
    normalized_source = str(source or "").strip().lower()
    summaries: dict[str, dict[str, Any]] = {}
    if normalized_source in {"configured", "catalog"}:
        summaries["catalog"] = _refresh_catalog_model_discovery(log_id=log_id, family=family)
    if normalized_source in {"configured", "huggingface"}:
        summaries["huggingface"] = _refresh_huggingface_model_discovery(log_id=log_id, family=family)
    if normalized_source in {"configured", "provider-api"}:
        summaries["provider_api"] = _refresh_provider_api_model_discovery(log_id=log_id, family=family)

    totals = {
        "entries": sum(int(summary.get("entries") or 0) for summary in summaries.values()),
        "records_found": sum(int(summary.get("records_found") or 0) for summary in summaries.values()),
        "models_created": sum(int(summary.get("models_created") or 0) for summary in summaries.values()),
        "models_updated": sum(int(summary.get("models_updated") or 0) for summary in summaries.values()),
        "models_unchanged": sum(int(summary.get("models_unchanged") or 0) for summary in summaries.values()),
        "sources_skipped": sum(int(summary.get("sources_skipped") or 0) for summary in summaries.values()),
        "sources_failed": sum(int(summary.get("sources_failed") or 0) for summary in summaries.values()),
    }
    return {
        "family": _clean_text(family),
        "sources": summaries,
        **totals,
    }


def _refresh_provider_api_model_discovery(
    *,
    log_id: int,
    family: str | None = None,
) -> dict[str, Any]:
    catalogs = provider_catalogs.provider_api_catalogs(family=family)
    summary: dict[str, Any] = {
        "family": _clean_text(family),
        "entries": len(catalogs),
        "records_found": 0,
        "models_created": 0,
        "models_updated": 0,
        "models_unchanged": 0,
        "sources_skipped": 0,
        "sources_failed": 0,
        "providers": {},
        "errors": [],
    }
    if not catalogs:
        return summary

    verified_at = utc_now_iso()
    with httpx.Client(headers=HTTP_HEADERS, follow_redirects=True, timeout=30.0) as client:
        for catalog in catalogs:
            catalog_id = _clean_text(_provider_catalog_value(catalog, "id")) or "provider-api"
            provider = canonical_provider_name(_clean_text(_provider_catalog_value(catalog, "provider")) or "Unknown")
            catalog_family = _clean_text(_provider_catalog_value(catalog, "family")) or catalog_id
            benchmark_id = _model_discovery_benchmark_id(catalog_family)
            source_run_id = _start_metadata_source_run(
                log_id,
                source_name=PROVIDER_API_MODEL_DISCOVERY_SOURCE_NAME,
                benchmark_id=benchmark_id,
            )
            provider_summary: dict[str, Any] = {
                "provider": provider,
                "records_found": 0,
                "models_created": 0,
                "models_updated": 0,
                "models_unchanged": 0,
                "status": "running",
            }
            try:
                items = provider_catalogs.fetch_provider_api_catalog_models(client, catalog)
                entry_roles = _normalise_model_roles(
                    _provider_catalog_value(catalog, "model_roles"),
                    default=(MODEL_ROLE_GENERATOR,),
                )
                entry = {
                    "family": catalog_family,
                    "provider": provider,
                    "model_roles": entry_roles,
                    "model_type": _clean_text(_provider_catalog_value(catalog, "model_type")) or "proprietary",
                }
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item = dict(item)
                    if _clean_text(item.get("catalog_status")) != "deprecated":
                        item["catalog_status"] = CATALOG_STATUS_PROVISIONAL
                    name = _clean_text(item.get("name"))
                    if not name:
                        continue
                    item_provider = canonical_provider_name(_clean_text(item.get("provider")) or provider)
                    item_source_url = (
                        _clean_text(item.get("source_url"))
                        or _clean_text(item.get("documentation_url"))
                        or _clean_text(_provider_catalog_value(catalog, "source_url"))
                        or _clean_text(_provider_catalog_value(catalog, "documentation_url"))
                        or ""
                    )
                    model_id, outcome = _ensure_discovered_catalog_model(
                        item=item,
                        entry=entry,
                        provider=item_provider,
                        source_url=item_source_url,
                        verified_at=verified_at,
                        discovered_update_log_id=log_id,
                        entry_roles=entry_roles,
                    )
                    model_roles = _normalise_model_roles(item.get("model_roles"), default=entry_roles)
                    raw_record = RawSourceRecord(
                        source_id=PROVIDER_API_MODEL_DISCOVERY_SOURCE_NAME,
                        benchmark_id=benchmark_id,
                        raw_model_name=name,
                        raw_value=_clean_text(item.get("catalog_model_id")) or _clean_text(item.get("id")) or name,
                        source_url=item_source_url,
                        collected_at=verified_at,
                        raw_model_key=_clean_text(item.get("catalog_model_id")) or _clean_text(item.get("id")),
                        payload=item,
                        metadata={
                            "source": "provider_api",
                            "family": catalog_family,
                            "provider": item_provider,
                            "provider_catalog": catalog_id,
                            "model_roles": model_roles,
                        },
                    )
                    _insert_raw_source_record(
                        source_run_id,
                        raw_record,
                        normalized_model_id=model_id,
                        source_type="primary",
                        verified=True,
                        resolution_status="resolved",
                    )
                    provider_summary["records_found"] += 1
                    summary["records_found"] += 1
                    if outcome == "created":
                        provider_summary["models_created"] += 1
                        summary["models_created"] += 1
                    elif outcome == "updated":
                        provider_summary["models_updated"] += 1
                        summary["models_updated"] += 1
                    else:
                        provider_summary["models_unchanged"] += 1
                        summary["models_unchanged"] += 1
            except provider_catalogs.ProviderCatalogNotConfigured as exc:
                provider_summary["status"] = "skipped"
                provider_summary["error"] = str(exc)
                summary["sources_skipped"] += 1
                _finish_source_run(source_run_id, status="skipped", records_found=0, error_message=str(exc))
            except Exception as exc:
                safe_error = provider_catalogs.safe_provider_catalog_error(exc, catalog)
                provider_summary["status"] = "failed"
                provider_summary["error"] = safe_error
                summary["sources_failed"] += 1
                summary["errors"].append(
                    {
                        "provider": provider,
                        "provider_catalog": catalog_id,
                        "error_message": safe_error,
                    }
                )
                _finish_source_run(
                    source_run_id,
                    status="failed",
                    records_found=int(provider_summary["records_found"]),
                    error_message=safe_error,
                )
            else:
                provider_summary["status"] = "completed"
                _finish_source_run(
                    source_run_id,
                    status="completed",
                    records_found=int(provider_summary["records_found"]),
                    error_message=None,
                )
            summary["providers"][catalog_id] = provider_summary
    return summary


def _provider_catalog_value(catalog: Any, key: str) -> Any:
    if isinstance(catalog, dict):
        return catalog.get(key)
    return getattr(catalog, key, None)


def _refresh_catalog_model_discovery(
    *,
    log_id: int,
    family: str | None = None,
) -> dict[str, Any]:
    entries = model_discovery.catalog_discovery_entries(family=family)
    summary = {
        "family": _clean_text(family),
        "entries": len(entries),
        "records_found": 0,
        "models_created": 0,
        "models_updated": 0,
        "models_unchanged": 0,
    }
    if not entries:
        return summary

    verified_at = utc_now_iso()
    source_run_id = _start_metadata_source_run(
        log_id,
        source_name=CATALOG_MODEL_DISCOVERY_SOURCE_NAME,
        benchmark_id=_model_discovery_benchmark_id(family),
    )
    records_found = 0
    try:
        for entry in entries:
            provider = canonical_provider_name(_clean_text(entry.get("provider")) or "Unknown")
            entry_source_url = _clean_text(entry.get("source_url"))
            entry_roles = _normalise_model_roles(entry.get("model_roles"), default=(MODEL_ROLE_GENERATOR,))
            for item in model_discovery.catalog_discovery_models(entry):
                name = _clean_text(item.get("name"))
                if not name:
                    continue
                item_source_url = _clean_text(item.get("source_url")) or entry_source_url or ""
                model_id, outcome = _ensure_discovered_catalog_model(
                    item=item,
                    entry=entry,
                    provider=provider,
                    source_url=item_source_url,
                    verified_at=verified_at,
                    discovered_update_log_id=log_id,
                    entry_roles=entry_roles,
                )
                raw_record = RawSourceRecord(
                    source_id=CATALOG_MODEL_DISCOVERY_SOURCE_NAME,
                    benchmark_id=_model_discovery_benchmark_id(entry.get("family") or family),
                    raw_model_name=name,
                    raw_value=_clean_text(item.get("catalog_model_id")) or _clean_text(item.get("id")) or name,
                    source_url=item_source_url,
                    collected_at=verified_at,
                    raw_model_key=_clean_text(item.get("catalog_model_id")) or _clean_text(item.get("id")),
                    payload=item,
                    metadata={
                        "source": "catalog",
                        "family": _clean_text(entry.get("family")),
                        "provider": provider,
                        "model_roles": _normalise_model_roles(item.get("model_roles"), default=entry_roles),
                    },
                )
                _insert_raw_source_record(
                    source_run_id,
                    raw_record,
                    normalized_model_id=model_id,
                    source_type="primary",
                    verified=True,
                    resolution_status="resolved",
                )
                records_found += 1
                if outcome == "created":
                    summary["models_created"] += 1
                elif outcome == "updated":
                    summary["models_updated"] += 1
                else:
                    summary["models_unchanged"] += 1
    except Exception as exc:
        _finish_source_run(source_run_id, status="failed", records_found=records_found, error_message=str(exc))
        raise

    summary["records_found"] = records_found
    _finish_source_run(source_run_id, status="completed", records_found=records_found, error_message=None)
    return summary


def _model_discovery_benchmark_id(family: Any) -> str:
    family_text = _clean_text(family)
    return f"model_discovery:{family_text}" if family_text else "model_discovery"


def _start_metadata_source_run(log_id: int, *, source_name: str, benchmark_id: str) -> int:
    with ENGINE.begin() as conn:
        result = conn.execute(
            insert(source_runs_table).values(
                update_log_id=log_id,
                source_name=source_name,
                benchmark_id=benchmark_id,
                started_at=utc_now_iso(),
                completed_at=None,
                status="running",
                records_found=0,
                error_message=None,
                details_json=None,
            )
        )
        return int(result.inserted_primary_key[0])


def _start_source_run(log_id: int, adapter: BaseSourceAdapter) -> int:
    with ENGINE.begin() as conn:
        result = conn.execute(
            insert(source_runs_table).values(
                update_log_id=log_id,
                source_name=adapter.source_id,
                benchmark_id=",".join(adapter.benchmark_ids),
                started_at=utc_now_iso(),
                completed_at=None,
                status="running",
                records_found=0,
                error_message=None,
                details_json=None,
            )
        )
        return int(result.inserted_primary_key[0])


def _finish_source_run(source_run_id: int, *, status: str, records_found: int, error_message: str | None) -> None:
    with ENGINE.begin() as conn:
        conn.execute(
            update(source_runs_table)
            .where(source_runs_table.c.id == source_run_id)
            .values(
                completed_at=utc_now_iso(),
                status=status,
                records_found=records_found,
                error_message=error_message,
            )
        )


def _persist_source_result(
    source_run_id: int,
    result: SourceFetchResult,
    *,
    discovered_update_log_id: int | None = None,
) -> tuple[int, int]:
    scores_added = 0
    scores_updated = 0
    model_ids_by_identity: dict[str, str] = {}
    source_meta_by_identity: dict[str, tuple[str, bool]] = {}
    benchmark_ids = sorted({candidate.benchmark_id for candidate in result.candidates})
    with get_connection(ENGINE) as conn:
        benchmarks_by_id = {
            str(row["id"]): dict(row)
            for row in fetch_all(
                conn,
                select(
                    benchmarks_table.c.id,
                    benchmarks_table.c.higher_is_better,
                ).where(benchmarks_table.c.id.in_(benchmark_ids)),
            )
        }

    resolved_candidates: dict[tuple[str, str, str, str], tuple[str, ScoreCandidate]] = {}
    for candidate in result.candidates:
        gpt56 = _gpt56_identity_and_configuration(candidate.raw_model_name)
        if gpt56 is not None:
            model_id, candidate.configuration_key, candidate.configuration_value = gpt56
            _ensure_gpt56_base_model(model_id)
        else:
            model_id = None
        existing_models_only = bool(candidate.metadata.get("existing_models_only"))
        if model_id is None and existing_models_only:
            model_id = _resolve_model_id(candidate.raw_model_name)
        if model_id is None and existing_models_only:
            source_meta_by_identity[_record_identity(candidate.raw_model_name, candidate.raw_model_key)] = (
                candidate.source_type,
                candidate.verified,
            )
            continue
        if model_id is None:
            model_id = _ensure_model(
                candidate.raw_model_name,
                candidate.metadata,
                candidate.raw_model_key,
                discovered_update_log_id=discovered_update_log_id,
            )
        _merge_model_roles(model_id, candidate.metadata)
        identity = _record_identity(candidate.raw_model_name, candidate.raw_model_key)
        model_ids_by_identity[identity] = model_id
        source_meta_by_identity[identity] = (candidate.source_type, candidate.verified)

        candidate_key = (
            model_id,
            candidate.benchmark_id,
            candidate.configuration_key or "",
            candidate.configuration_value or "",
        )
        current_best = resolved_candidates.get(candidate_key)
        if current_best is not None:
            benchmark = benchmarks_by_id.get(candidate.benchmark_id)
            if not _is_better_benchmark_score(
                {"value": candidate.value, "collected_at": candidate.collected_at},
                {"value": current_best[1].value, "collected_at": current_best[1].collected_at},
                benchmark,
            ):
                continue
        resolved_candidates[candidate_key] = (model_id, candidate)

    for model_id, candidate in resolved_candidates.values():
        _promote_score_candidate_metadata(model_id, candidate)
        _, outcome = _persist_score_candidate(candidate, resolved_model_id=model_id)
        if outcome == "added":
            scores_added += 1
        elif outcome == "updated":
            scores_updated += 1

    for raw_record in result.raw_records:
        identity = _record_identity(raw_record.raw_model_name, raw_record.raw_model_key)
        normalized_model_id = model_ids_by_identity.get(identity)
        skipped_resolution = _should_skip_raw_model_resolution(raw_record)
        if normalized_model_id is None and not skipped_resolution:
            normalized_model_id = _ensure_model(
                raw_record.raw_model_name,
                raw_record.metadata,
                raw_record.raw_model_key,
                discovered_update_log_id=discovered_update_log_id,
            )
            _merge_model_roles(normalized_model_id, raw_record.metadata)
            model_ids_by_identity[identity] = normalized_model_id
        elif normalized_model_id is None and raw_record.metadata.get("existing_models_only"):
            normalized_model_id = _resolve_model_id(raw_record.raw_model_name)
            if normalized_model_id is not None:
                model_ids_by_identity[identity] = normalized_model_id
        resolution_status = _resolution_status_for_raw_record(
            raw_record,
            normalized_model_id=normalized_model_id,
            skipped_resolution=skipped_resolution,
        )

        source_type, verified = source_meta_by_identity.get(
            identity,
            (
                "secondary" if raw_record.metadata.get("self_reported") else "primary",
                bool(raw_record.metadata.get("verified")),
            ),
        )
        _insert_raw_source_record(
            source_run_id,
            raw_record,
            normalized_model_id=normalized_model_id,
            source_type=source_type,
            verified=verified,
            resolution_status=resolution_status,
        )
        _upsert_source_listing(raw_record, normalized_model_id=normalized_model_id)

    _mark_missing_source_listings(result)

    return scores_added, scores_updated


def _promote_score_candidate_metadata(model_id: str, candidate: ScoreCandidate) -> bool:
    source_id = str(candidate.source_id or "").strip()
    if source_id not in SOURCE_METADATA_PROMOTION_LABELS:
        return False

    trust_level = _source_metadata_trust_level(
        source_id,
        candidate.metadata,
        source_type=candidate.source_type,
        verified=candidate.verified,
    )
    if trust_level is None:
        return False

    with ENGINE.begin() as conn:
        row = fetch_one(conn, select(models_table).where(models_table.c.id == model_id))
        if row is None:
            return False

        values: dict[str, Any] = {}
        provider_name = _source_metadata_provider(source_id, candidate.metadata)
        if provider_name and trust_level != "self_reported":
            current_provider = str(row.get("provider") or "").strip()
            current_provider_unknown = not current_provider or current_provider.lower() == "unknown"
            current_provider_id = str(row.get("provider_id") or "").strip()
            if current_provider_unknown or (
                not current_provider_id and normalize_text(current_provider) == normalize_text(provider_name)
            ):
                values["provider"] = provider_name
                values["provider_id"] = _ensure_provider_row(provider_name, conn=conn)

        context_tokens = _source_metadata_context_tokens(source_id, candidate.metadata)
        if context_tokens is not None and row.get("context_window_tokens") is None:
            values["context_window_tokens"] = context_tokens
            if _model_field_missing(row, "context_window"):
                values["context_window"] = _format_context_window_tokens(context_tokens)

        input_price = _source_metadata_price_per_mtok(source_id, candidate.metadata, input_price=True)
        if input_price is not None and row.get("price_input_per_mtok") is None:
            values["price_input_per_mtok"] = input_price

        output_price = _source_metadata_price_per_mtok(source_id, candidate.metadata, input_price=False)
        if output_price is not None and row.get("price_output_per_mtok") is None:
            values["price_output_per_mtok"] = output_price

        license_name = _source_metadata_license_name(source_id, candidate.metadata)
        if license_name and trust_level != "self_reported" and _model_field_missing(row, "license_id") and _model_field_missing(row, "license_name"):
            values["license_name"] = license_name

        documentation_url = _source_metadata_documentation_url(source_id, candidate.metadata)
        if documentation_url and _model_field_missing(row, "documentation_url"):
            values["documentation_url"] = documentation_url

        release_date_values = _source_metadata_release_date_values(
            source_id,
            candidate.metadata,
            trust_level=trust_level,
            source_url=_source_metadata_source_url(source_id, candidate.metadata, candidate.source_url),
            verified_at=candidate.collected_at,
        )
        if release_date_values and _should_update_release_date(row, release_date_values):
            values.update(release_date_values)

        if values and _model_field_missing(row, "metadata_source_name"):
            values["metadata_source_name"] = SOURCE_METADATA_PROMOTION_LABELS[source_id]
            values["metadata_source_url"] = _source_metadata_source_url(source_id, candidate.metadata, candidate.source_url)
            values["metadata_verified_at"] = candidate.collected_at

        if not values:
            return False

        conn.execute(
            update(models_table)
            .where(models_table.c.id == model_id)
            .values(**values)
        )
        return True


def _source_metadata_trust_level(
    source_id: str,
    metadata: dict[str, Any],
    *,
    source_type: str,
    verified: bool,
) -> str | None:
    if source_id in {"artificial_analysis", "artificial_analysis_tts"}:
        if verified and source_type == "primary":
            return "verified"
        return None

    if source_id == "chatbot_arena":
        return "verified"

    if source_id != "ifeval":
        return None

    self_reported = bool(metadata.get("self_reported"))
    if verified and not self_reported:
        return "verified"
    if self_reported and _clean_text(metadata.get("self_reported_source")):
        return "self_reported"
    if source_type == "primary" and verified:
        return "verified"
    return None


def _source_metadata_release_date_values(
    source_id: str,
    metadata: dict[str, Any],
    *,
    trust_level: str,
    source_url: str | None,
    verified_at: str,
) -> dict[str, Any]:
    if source_id in {"artificial_analysis", "artificial_analysis_tts"}:
        release_date = _clean_release_date(metadata.get("release_date"))
        confidence = "high"
    elif source_id == "ifeval":
        release_date = _clean_release_date(metadata.get("announcement_date"))
        confidence = "medium" if trust_level == "verified" else "low"
    else:
        release_date = None
        confidence = "low"

    if not release_date:
        return {}

    precision = _release_date_precision(release_date)
    if precision is None:
        return {}

    return {
        "release_date": release_date,
        "release_date_precision": precision,
        "release_date_confidence": confidence,
        "release_date_source_name": SOURCE_METADATA_PROMOTION_LABELS[source_id],
        "release_date_source_url": source_url,
        "release_date_verified_at": verified_at,
    }


def _should_update_release_date(row: dict[str, Any], values: dict[str, Any]) -> bool:
    next_release_date = _clean_text(values.get("release_date"))
    if not next_release_date:
        return False

    current_release_date = _clean_text(row.get("release_date"))
    if not current_release_date:
        return True

    current_precision = _clean_text(row.get("release_date_precision")) or _release_date_precision(current_release_date)
    next_precision = _clean_text(values.get("release_date_precision")) or _release_date_precision(next_release_date)
    current_confidence = _clean_text(row.get("release_date_confidence"))
    next_confidence = _clean_text(values.get("release_date_confidence"))

    if current_release_date == next_release_date:
        return any(
            _model_field_missing(row, field_name)
            for field_name in (
                "release_date_precision",
                "release_date_confidence",
                "release_date_source_name",
                "release_date_source_url",
                "release_date_verified_at",
            )
        )

    current_precision_rank = _release_precision_rank(current_precision)
    next_precision_rank = _release_precision_rank(next_precision)
    current_confidence_rank = _release_confidence_rank(current_confidence)
    next_confidence_rank = _release_confidence_rank(next_confidence)
    if next_precision_rank > current_precision_rank and next_confidence_rank >= current_confidence_rank:
        return True
    if next_confidence_rank > current_confidence_rank and next_precision_rank >= current_precision_rank:
        return True
    return False


def _source_metadata_provider(source_id: str, metadata: dict[str, Any]) -> str | None:
    provider_name: str | None = None
    if source_id == "chatbot_arena":
        provider_name = _clean_text(metadata.get("organization") or metadata.get("modelOrganization"))
    elif source_id == "artificial_analysis_tts":
        provider_name = _clean_text(metadata.get("model_creator"))
    elif source_id == "ifeval":
        provider_name = _clean_text(metadata.get("organization_name"))
    return canonical_provider_name(provider_name) if provider_name else None


def _source_metadata_context_tokens(source_id: str, metadata: dict[str, Any]) -> int | None:
    if source_id == "chatbot_arena":
        return _context_window_tokens_from_source(metadata.get("context_length"))
    if source_id == "ifeval":
        return _context_window_tokens_from_source(metadata.get("context_window"))
    return None


def _source_metadata_price_per_mtok(source_id: str, metadata: dict[str, Any], *, input_price: bool) -> float | None:
    if source_id == "chatbot_arena":
        key = "input_price_per_million" if input_price else "output_price_per_million"
    elif source_id == "ifeval":
        key = "input_cost_per_million" if input_price else "output_cost_per_million"
    else:
        return None
    return _safe_float(metadata.get(key))


def _source_metadata_license_name(source_id: str, metadata: dict[str, Any]) -> str | None:
    if source_id == "chatbot_arena":
        return _clean_text(metadata.get("license"))
    if source_id == "ifeval":
        return _clean_text(metadata.get("license") or metadata.get("license_name"))
    return None


def _source_metadata_documentation_url(source_id: str, metadata: dict[str, Any]) -> str | None:
    if source_id == "chatbot_arena":
        return _clean_url(metadata.get("model_url") or metadata.get("modelUrl"))
    if source_id == "artificial_analysis_tts":
        return _clean_url(metadata.get("details_url") or metadata.get("leaderboard_url"))
    return None


def _source_metadata_source_url(source_id: str, metadata: dict[str, Any], fallback_url: str) -> str | None:
    if source_id == "ifeval":
        return _clean_url(metadata.get("details_url")) or _clean_url(fallback_url)
    if source_id == "artificial_analysis_tts":
        return _clean_url(metadata.get("details_url")) or _clean_url(fallback_url)
    return _clean_url(fallback_url)


def _context_window_tokens_from_source(value: Any) -> int | None:
    direct_value = _safe_int(value)
    if direct_value is not None:
        return direct_value if direct_value > 0 else None

    text_value = str(value or "").strip().replace(",", "")
    if not text_value:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:tokens?|ctx|context)?", text_value)
    if not match:
        return None
    number = _safe_float(match.group(1))
    if number is None or number <= 0:
        return None
    suffix = match.group(2).lower()
    if suffix == "m":
        number *= 1_000_000
    elif suffix == "k":
        number *= 1_000
    return int(number)


def _model_field_missing(row: dict[str, Any], field_name: str) -> bool:
    value = row.get(field_name)
    return value is None or value == ""


def _clean_url(value: Any) -> str | None:
    url = _clean_text(value)
    if not url:
        return None
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return None
    return url


def _insert_raw_source_record(
    source_run_id: int,
    raw_record: RawSourceRecord,
    *,
    normalized_model_id: str | None,
    source_type: str,
    verified: bool,
    resolution_status: str,
) -> None:
    with ENGINE.begin() as conn:
        conn.execute(
            insert(raw_source_records_table).values(
                source_run_id=source_run_id,
                benchmark_id=raw_record.benchmark_id,
                raw_model_name=raw_record.raw_model_name,
                normalized_model_id=normalized_model_id,
                raw_key=raw_record.raw_model_key,
                raw_value=raw_record.raw_value,
                payload_json=json.dumps(raw_record.payload, ensure_ascii=True),
                source_url=raw_record.source_url,
                source_type=source_type,
                verified=1 if verified else 0,
                resolution_status=resolution_status,
                collected_at=raw_record.collected_at,
                notes=_stringify(raw_record.metadata) if raw_record.metadata else None,
            )
        )


def _upsert_source_listing(raw_record: RawSourceRecord, *, normalized_model_id: str | None) -> None:
    listing_status = _clean_text(raw_record.metadata.get("source_listing_status"))
    if not listing_status:
        return
    raw_key = _clean_text(raw_record.raw_model_key) or raw_record.raw_model_name
    source_revision = _clean_text(raw_record.metadata.get("dataset_revision")) or None
    publication_date = _clean_text(raw_record.metadata.get("leaderboard_publish_date")) or None
    observed_at = raw_record.collected_at
    metadata_json = json.dumps(raw_record.metadata, ensure_ascii=True, sort_keys=True)
    statement = sqlite_insert(model_source_listings_table).values(
        source_name=raw_record.source_id,
        benchmark_id=raw_record.benchmark_id,
        raw_model_name=raw_record.raw_model_name,
        raw_model_key=raw_key,
        model_id=normalized_model_id,
        listing_status=listing_status,
        source_revision=source_revision,
        publication_date=publication_date,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        metadata_json=metadata_json,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["source_name", "benchmark_id", "raw_model_key"],
        set_={
            "raw_model_name": raw_record.raw_model_name,
            "model_id": normalized_model_id,
            "listing_status": listing_status,
            "source_revision": source_revision,
            "publication_date": publication_date,
            "last_seen_at": observed_at,
            "metadata_json": metadata_json,
        },
    )
    with ENGINE.begin() as conn:
        conn.execute(statement)


def _mark_missing_source_listings(result: SourceFetchResult) -> None:
    keys_by_benchmark: dict[str, set[str]] = {
        benchmark_id: set() for benchmark_id in result.listing_benchmark_ids
    }
    has_listing_evidence = False
    for raw_record in result.raw_records:
        if not _clean_text(raw_record.metadata.get("source_listing_status")):
            continue
        has_listing_evidence = True
        keys_by_benchmark.setdefault(raw_record.benchmark_id, set()).add(
            _clean_text(raw_record.raw_model_key) or raw_record.raw_model_name
        )
    if not has_listing_evidence:
        return
    with ENGINE.begin() as conn:
        for benchmark_id, current_keys in keys_by_benchmark.items():
            statement = (
                update(model_source_listings_table)
                .where(model_source_listings_table.c.source_name == result.source_id)
                .where(model_source_listings_table.c.benchmark_id == benchmark_id)
                .where(model_source_listings_table.c.listing_status == "listed")
            )
            if current_keys:
                statement = statement.where(
                    model_source_listings_table.c.raw_model_key.not_in(sorted(current_keys))
                )
            conn.execute(statement.values(listing_status="no_longer_listed"))


def _persist_score_candidate(
    candidate: ScoreCandidate,
    resolved_model_id: str | None = None,
    *,
    discovered_update_log_id: int | None = None,
) -> tuple[str, str]:
    model_id = resolved_model_id or _ensure_model(
        candidate.raw_model_name,
        candidate.metadata,
        candidate.raw_model_key,
        discovered_update_log_id=discovered_update_log_id,
    )

    with ENGINE.begin() as conn:
        latest = fetch_one(
            conn,
            select(
                scores_table.c.id,
                scores_table.c.value,
                scores_table.c.collected_at,
                scores_table.c.source_type,
                scores_table.c.verified,
                scores_table.c.source_listing_status,
                scores_table.c.source_metadata_json,
            )
            .where(scores_table.c.model_id == model_id)
            .where(scores_table.c.benchmark_id == candidate.benchmark_id)
            .where(
                scores_table.c.configuration_key.is_(None)
                if candidate.configuration_key is None
                else scores_table.c.configuration_key == candidate.configuration_key
            )
            .where(
                scores_table.c.configuration_value.is_(None)
                if candidate.configuration_value is None
                else scores_table.c.configuration_value == candidate.configuration_value
            )
            .order_by(scores_table.c.collected_at.desc(), scores_table.c.id.desc())
            .limit(1),
        )

        if latest is not None and str(latest.get("collected_at") or "") == candidate.collected_at:
            benchmark = fetch_one(
                conn,
                select(
                    benchmarks_table.c.id,
                    benchmarks_table.c.higher_is_better,
                ).where(benchmarks_table.c.id == candidate.benchmark_id),
            )
            latest_score = {
                "value": float(latest["value"]),
                "collected_at": str(latest.get("collected_at") or ""),
            }
            candidate_score = {
                "value": float(candidate.value),
                "collected_at": candidate.collected_at,
            }
            latest_source_revision = _score_source_revision(
                _decode_json_object(latest.get("source_metadata_json"))
            )
            candidate_source_revision = _score_source_revision(candidate.source_metadata)
            source_revision_changed = bool(
                latest_source_revision
                and candidate_source_revision
                and latest_source_revision != candidate_source_revision
            )
            if source_revision_changed or _is_better_benchmark_score(candidate_score, latest_score, benchmark) or (
                candidate.source_listing_status
                and not latest.get("source_listing_status")
            ):
                conn.execute(
                    update(scores_table)
                    .where(scores_table.c.id == latest["id"])
                    .values(
                        value=candidate.value,
                        raw_value=candidate.raw_value,
                        collected_at=candidate.collected_at,
                        source_url=candidate.source_url,
                        source_type=candidate.source_type,
                        verified=1 if candidate.verified else 0,
                        notes=candidate.notes,
                        confidence_lower=candidate.confidence_lower,
                        confidence_upper=candidate.confidence_upper,
                        variance=candidate.variance,
                        vote_count=candidate.vote_count,
                        observation_count=candidate.observation_count,
                        session_count=candidate.session_count,
                        rank=candidate.rank,
                        category=candidate.category,
                        publication_date=candidate.publication_date,
                        methodology=candidate.methodology,
                        source_listing_status=candidate.source_listing_status,
                        style_control=None if candidate.style_control is None else (1 if candidate.style_control else 0),
                        preliminary=None if candidate.preliminary is None else (1 if candidate.preliminary else 0),
                        source_metadata_json=json.dumps(candidate.source_metadata, ensure_ascii=True, sort_keys=True),
                        configuration_key=candidate.configuration_key,
                        configuration_value=candidate.configuration_value,
                    )
                )
                return model_id, "updated"
            return model_id, "skipped"

        if (
            latest is not None
            and abs(float(latest["value"]) - candidate.value) <= 0.1
            and not candidate.source_listing_status
        ):
            return model_id, "skipped"

        conn.execute(
            insert(scores_table).values(
                model_id=model_id,
                benchmark_id=candidate.benchmark_id,
                value=candidate.value,
                raw_value=candidate.raw_value,
                collected_at=candidate.collected_at,
                source_url=candidate.source_url,
                source_type=candidate.source_type,
                verified=1 if candidate.verified else 0,
                notes=candidate.notes,
                confidence_lower=candidate.confidence_lower,
                confidence_upper=candidate.confidence_upper,
                variance=candidate.variance,
                vote_count=candidate.vote_count,
                observation_count=candidate.observation_count,
                session_count=candidate.session_count,
                rank=candidate.rank,
                category=candidate.category,
                publication_date=candidate.publication_date,
                methodology=candidate.methodology,
                source_listing_status=candidate.source_listing_status,
                style_control=None if candidate.style_control is None else (1 if candidate.style_control else 0),
                preliminary=None if candidate.preliminary is None else (1 if candidate.preliminary else 0),
                source_metadata_json=json.dumps(candidate.source_metadata, ensure_ascii=True, sort_keys=True),
                configuration_key=candidate.configuration_key,
                configuration_value=candidate.configuration_value,
            )
        )

    return model_id, "updated" if latest is not None else "added"


def _score_source_revision(source_metadata: dict[str, Any]) -> str | None:
    for key in ("dataset_revision", "source_revision", "revision"):
        revision = _clean_text(source_metadata.get(key))
        if revision:
            return revision
    return None


def _merge_model_roles(model_id: str, metadata: dict[str, Any]) -> bool:
    roles = _model_roles_from_metadata(metadata)
    if not roles:
        return False

    with ENGINE.begin() as conn:
        row = fetch_one(
            conn,
            select(models_table.c.model_roles_json).where(models_table.c.id == model_id),
        )
        if row is None:
            return False

        current_roles = _normalise_model_roles(row.get("model_roles_json"), default=())
        merged_roles = sorted(dict.fromkeys([*current_roles, *roles]))
        if merged_roles == current_roles:
            return False

        conn.execute(
            update(models_table)
            .where(models_table.c.id == model_id)
            .values(model_roles_json=json.dumps(merged_roles, ensure_ascii=True))
        )
        return True


def _load_identity_override_indexes(
    conn,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = fetch_all(
        conn,
        select(model_identity_overrides_table).where(model_identity_overrides_table.c.active == 1),
    )
    by_model_id: dict[str, dict[str, Any]] = {}
    by_match_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_model_id = str(row.get("source_model_id") or "").strip()
        match_key = str(row.get("match_key") or "").strip()
        if source_model_id:
            by_model_id[source_model_id] = row
        if match_key:
            by_match_key[match_key] = row
    return by_model_id, by_match_key


def _load_duplicate_override_indexes(
    conn,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = fetch_all(
        conn,
        select(model_duplicate_overrides_table).where(model_duplicate_overrides_table.c.active == 1),
    )
    by_model_id: dict[str, dict[str, Any]] = {}
    by_match_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_model_id = str(row.get("source_model_id") or "").strip()
        match_key = str(row.get("match_key") or "").strip()
        if source_model_id:
            by_model_id[source_model_id] = row
        if match_key:
            by_match_key[match_key] = row
    return by_model_id, by_match_key


def _find_identity_override(
    conn,
    *,
    model_id: str | None = None,
    provider: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    by_model_id, by_match_key = _load_identity_override_indexes(conn)
    normalized_model_id = str(model_id or "").strip()
    if normalized_model_id and normalized_model_id in by_model_id:
        return by_model_id[normalized_model_id]
    match_key = build_model_curation_match_key(provider, name)
    if match_key:
        return by_match_key.get(match_key)
    return None


def _find_duplicate_override(
    conn,
    *,
    model_id: str | None = None,
    provider: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    by_model_id, by_match_key = _load_duplicate_override_indexes(conn)
    normalized_model_id = str(model_id or "").strip()
    if normalized_model_id and normalized_model_id in by_model_id:
        return by_model_id[normalized_model_id]
    match_key = build_model_curation_match_key(provider, name)
    if match_key:
        return by_match_key.get(match_key)
    return None


def _resolve_active_duplicate_target(conn, override: dict[str, Any] | None) -> str | None:
    if override is None:
        return None
    target_model_id = str(override.get("target_model_id") or "").strip()
    if not target_model_id:
        return None
    existing = fetch_one(
        conn,
        select(models_table.c.id).where(
            models_table.c.id == target_model_id,
            models_table.c.active == 1,
        ),
    )
    return target_model_id if existing is not None else None


def _identity_from_override(override: dict[str, Any] | None) -> ModelIdentity | None:
    if override is None:
        return None
    family_id = str(override.get("family_id") or "").strip()
    family_name = str(override.get("family_name") or "").strip()
    canonical_model_id = str(override.get("canonical_model_id") or "").strip()
    canonical_model_name = str(override.get("canonical_model_name") or "").strip()
    if not all((family_id, family_name, canonical_model_id, canonical_model_name)):
        return None
    return ModelIdentity(
        family_id=family_id,
        family_name=family_name,
        canonical_model_id=canonical_model_id,
        canonical_model_name=canonical_model_name,
        variant_label=_clean_text(override.get("variant_label")),
    )


def _ensure_model(
    raw_model_name: str,
    metadata: dict[str, Any],
    raw_model_key: str | None = None,
    *,
    discovered_update_log_id: int | None = None,
) -> str:
    gpt56 = _gpt56_identity_and_configuration(raw_model_name)
    if gpt56 is not None:
        return _ensure_gpt56_base_model(gpt56[0])
    resolved = _resolve_model_id(raw_model_name)
    if resolved:
        return resolved

    candidate_model_id = _choose_model_id(raw_model_name, raw_model_key)
    provider = canonical_provider_name(_infer_provider(metadata, raw_model_name) or "Unknown")
    discovered_at = utc_now_iso()
    with ENGINE.begin() as conn:
        provider_id = _ensure_provider_row(provider, conn=conn)
        duplicate_override = _find_duplicate_override(
            conn,
            model_id=candidate_model_id,
            provider=provider,
            name=raw_model_name,
        )
        duplicate_target_id = _resolve_active_duplicate_target(conn, duplicate_override)
        if duplicate_target_id:
            return duplicate_target_id

        identity_override = _find_identity_override(
            conn,
            model_id=candidate_model_id,
            provider=provider,
            name=raw_model_name,
        )
        model_id = str(identity_override.get("source_model_id") or candidate_model_id) if identity_override else candidate_model_id
        identity = _identity_from_override(identity_override) or infer_model_identity(raw_model_name, provider, model_id)
        stmt = sqlite_insert(models_table).values(
            id=model_id,
            name=raw_model_name,
            provider_id=provider_id,
            provider=provider,
            type="proprietary" if provider != "Unknown" else "open_weights",
            model_roles_json=json.dumps(
                _model_roles_from_metadata(metadata) or [MODEL_ROLE_GENERATOR],
                ensure_ascii=True,
            ),
            catalog_status=CATALOG_STATUS_TRACKED,
            release_date=None,
            release_date_precision=None,
            release_date_confidence=None,
            release_date_source_name=None,
            release_date_source_url=None,
            release_date_verified_at=None,
            context_window=None,
            family_id=identity.family_id,
            family_name=identity.family_name,
            canonical_model_id=identity.canonical_model_id,
            canonical_model_name=identity.canonical_model_name,
            variant_label=identity.variant_label,
            discovered_at=discovered_at,
            discovered_update_log_id=discovered_update_log_id,
            active=1,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        conn.execute(stmt)
    return model_id


def _ensure_discovered_catalog_model(
    *,
    item: dict[str, Any],
    entry: dict[str, Any],
    provider: str,
    source_url: str,
    verified_at: str,
    discovered_update_log_id: int | None,
    entry_roles: list[str],
) -> tuple[str, str]:
    name = _clean_text(item.get("name"))
    if not name:
        raise ValueError("Catalog discovery item is missing a name.")

    provider = canonical_provider_name(provider)
    model_id = _clean_text(item.get("id")) or _choose_model_id(name, _clean_text(item.get("catalog_model_id")))
    roles = _normalise_model_roles(item.get("model_roles"), default=entry_roles or (MODEL_ROLE_GENERATOR,))
    model_type = _clean_text(item.get("model_type")) or _clean_text(entry.get("model_type")) or "proprietary"
    catalog_status = _clean_text(item.get("catalog_status")) or CATALOG_STATUS_TRACKED
    if catalog_status not in {CATALOG_STATUS_TRACKED, CATALOG_STATUS_PROVISIONAL, "deprecated"}:
        catalog_status = CATALOG_STATUS_TRACKED
    source_name = _clean_text(item.get("metadata_source_name")) or CATALOG_MODEL_DISCOVERY_SOURCE_NAME
    documentation_url = _clean_text(item.get("documentation_url"))
    model_card_url = _clean_text(item.get("model_card_url")) or documentation_url
    repo_url = _clean_text(item.get("repo_url"))
    paper_url = _clean_text(item.get("paper_url"))
    license_id = _clean_text(item.get("license_id"))
    license_name = _clean_text(item.get("license_name"))
    license_url = _clean_text(item.get("license_url"))
    capabilities = _decode_json_string_list(item.get("capabilities"))
    intended_use = _clean_text(item.get("intended_use_short")) or _clean_text(item.get("description"))
    context_window_tokens = _safe_int(item.get("context_window_tokens"))
    max_output_tokens = _safe_int(item.get("max_output_tokens"))
    price_input_per_mtok = _safe_float(item.get("price_input_per_mtok"))
    price_output_per_mtok = _safe_float(item.get("price_output_per_mtok"))
    release_date = _clean_text(item.get("release_date"))
    release_date_precision = _clean_text(item.get("release_date_precision")) or None
    release_date_confidence = _clean_text(item.get("release_date_confidence")) or None
    parameter_count_b = _safe_float(item.get("parameter_count_b"))
    active_parameter_count_b = _safe_float(item.get("active_parameter_count_b"))
    model_size_class = _clean_text(item.get("model_size_class"))
    small_model_candidate = item.get("small_model_candidate")
    if small_model_candidate is None and parameter_count_b is not None:
        small_model_candidate = parameter_count_b <= 15.0
    huggingface_repo_id = _clean_text(item.get("huggingface_repo_id"))
    identity = infer_model_identity(name, provider, model_id)

    with ENGINE.begin() as conn:
        provider_id = _ensure_provider_row(provider, conn=conn)
        existing = fetch_one(conn, select(models_table).where(models_table.c.id == model_id))
        if existing is None:
            resolved = _resolve_model_id(name)
            if resolved:
                existing = fetch_one(conn, select(models_table).where(models_table.c.id == resolved))
                if existing is not None:
                    model_id = str(existing["id"])

        if existing is not None:
            values: dict[str, Any] = {}
            current_provider = _clean_text(existing.get("provider"))
            if not current_provider or current_provider.lower() == "unknown" or normalize_text(current_provider) == normalize_text(provider):
                values["provider"] = provider
                values["provider_id"] = provider_id

            current_roles = _normalise_model_roles(existing.get("model_roles_json"), default=())
            merged_roles = sorted(dict.fromkeys([*current_roles, *roles]))
            if merged_roles and merged_roles != current_roles:
                values["model_roles_json"] = json.dumps(merged_roles, ensure_ascii=True)

            if catalog_status == CATALOG_STATUS_TRACKED and existing.get("catalog_status") == CATALOG_STATUS_PROVISIONAL:
                values["catalog_status"] = catalog_status
            if _model_field_missing(existing, "metadata_source_name") or existing.get("metadata_source_name") == CATALOG_MODEL_DISCOVERY_SOURCE_NAME:
                values["metadata_source_name"] = source_name
                values["metadata_source_url"] = source_url
                values["metadata_verified_at"] = verified_at
            if huggingface_repo_id and _model_field_missing(existing, "huggingface_repo_id"):
                values["huggingface_repo_id"] = huggingface_repo_id
            if model_card_url and _model_field_missing(existing, "model_card_url"):
                values["model_card_url"] = model_card_url
                values["model_card_source"] = source_name
                values["model_card_verified_at"] = verified_at
            if documentation_url and _model_field_missing(existing, "documentation_url"):
                values["documentation_url"] = documentation_url
            if repo_url and _model_field_missing(existing, "repo_url"):
                values["repo_url"] = repo_url
            if paper_url and _model_field_missing(existing, "paper_url"):
                values["paper_url"] = paper_url
            if license_id and _model_field_missing(existing, "license_id"):
                values["license_id"] = license_id
                values["license_name"] = license_name
                values["license_url"] = license_url
            if context_window_tokens and _model_field_missing(existing, "context_window_tokens"):
                values["context_window_tokens"] = context_window_tokens
            if max_output_tokens and _model_field_missing(existing, "max_output_tokens"):
                values["max_output_tokens"] = max_output_tokens
            if price_input_per_mtok is not None and _model_field_missing(existing, "price_input_per_mtok"):
                values["price_input_per_mtok"] = price_input_per_mtok
            if price_output_per_mtok is not None and _model_field_missing(existing, "price_output_per_mtok"):
                values["price_output_per_mtok"] = price_output_per_mtok
            if release_date and _model_field_missing(existing, "release_date"):
                values["release_date"] = release_date
                values["release_date_precision"] = release_date_precision or "day"
                values["release_date_confidence"] = release_date_confidence or "medium"
                values["release_date_source_name"] = source_name
                values["release_date_source_url"] = source_url
                values["release_date_verified_at"] = verified_at
            if parameter_count_b is not None and _model_field_missing(existing, "parameter_count_b"):
                values["parameter_count_b"] = parameter_count_b
            if active_parameter_count_b is not None and _model_field_missing(existing, "active_parameter_count_b"):
                values["active_parameter_count_b"] = active_parameter_count_b
            if model_size_class and _model_field_missing(existing, "model_size_class"):
                values["model_size_class"] = model_size_class
            if small_model_candidate is not None and not existing.get("small_model_candidate"):
                values["small_model_candidate"] = 1 if bool(small_model_candidate) else 0
            if values.keys() & {"parameter_count_b", "active_parameter_count_b", "model_size_class", "small_model_candidate"}:
                values["model_size_source_name"] = source_name
                values["model_size_source_url"] = source_url
                values["model_size_verified_at"] = verified_at
            if capabilities:
                current_capabilities = _decode_json_string_list(existing.get("capabilities_json"))
                merged_capabilities = sorted(dict.fromkeys([*current_capabilities, *capabilities]))
                if merged_capabilities != current_capabilities:
                    values["capabilities_json"] = json.dumps(merged_capabilities, ensure_ascii=True)
            if intended_use and _model_field_missing(existing, "intended_use_short"):
                values["intended_use_short"] = intended_use
            if _model_field_missing(existing, "discovered_at"):
                values["discovered_at"] = verified_at
            if _model_field_missing(existing, "discovered_update_log_id"):
                values["discovered_update_log_id"] = discovered_update_log_id

            if not values:
                return model_id, "unchanged"
            conn.execute(update(models_table).where(models_table.c.id == model_id).values(**values))
            return model_id, "updated"

        values = {
            "id": model_id,
            "name": name,
            "provider_id": provider_id,
            "provider": provider,
            "type": model_type,
            "model_roles_json": json.dumps(roles or [MODEL_ROLE_GENERATOR], ensure_ascii=True),
            "catalog_status": catalog_status,
            "family_id": identity.family_id,
            "family_name": identity.family_name,
            "canonical_model_id": identity.canonical_model_id,
            "canonical_model_name": identity.canonical_model_name,
            "variant_label": identity.variant_label,
            "discovered_at": verified_at,
            "discovered_update_log_id": discovered_update_log_id,
            "metadata_source_name": source_name,
            "metadata_source_url": source_url,
            "metadata_verified_at": verified_at,
            "model_card_url": model_card_url,
            "model_card_source": source_name if model_card_url else None,
            "model_card_verified_at": verified_at if model_card_url else None,
            "documentation_url": documentation_url,
            "repo_url": repo_url,
            "paper_url": paper_url,
            "license_id": license_id,
            "license_name": license_name,
            "license_url": license_url,
            "context_window_tokens": context_window_tokens,
            "max_output_tokens": max_output_tokens,
            "price_input_per_mtok": price_input_per_mtok,
            "price_output_per_mtok": price_output_per_mtok,
            "release_date": release_date,
            "release_date_precision": release_date_precision,
            "release_date_confidence": release_date_confidence,
            "release_date_source_name": source_name if release_date else None,
            "release_date_source_url": source_url if release_date else None,
            "release_date_verified_at": verified_at if release_date else None,
            "parameter_count_b": parameter_count_b,
            "active_parameter_count_b": active_parameter_count_b,
            "model_size_class": model_size_class,
            "small_model_candidate": 1 if bool(small_model_candidate) else 0,
            "model_size_source_name": source_name if any(
                value is not None for value in (parameter_count_b, active_parameter_count_b, model_size_class, small_model_candidate)
            ) else None,
            "model_size_source_url": source_url if any(
                value is not None for value in (parameter_count_b, active_parameter_count_b, model_size_class, small_model_candidate)
            ) else None,
            "model_size_verified_at": verified_at if any(
                value is not None for value in (parameter_count_b, active_parameter_count_b, model_size_class, small_model_candidate)
            ) else None,
            "huggingface_repo_id": huggingface_repo_id,
            "capabilities_json": json.dumps(capabilities, ensure_ascii=True),
            "intended_use_short": intended_use,
            "active": 1,
        }
        stmt = sqlite_insert(models_table).values(**values)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        result = conn.execute(stmt)
        if result.rowcount:
            return model_id, "created"

    return model_id, "unchanged"


def _ensure_discovered_huggingface_model(
    *,
    repo_id: str,
    display_name: str,
    provider: str,
    source_url: str,
    verified_at: str,
    discovered_update_log_id: int | None,
    model_roles: list[str],
    size_values: dict[str, Any],
    timestamp_values: dict[str, Any],
) -> tuple[str, str]:
    provider = canonical_provider_name(provider)
    existing_model_id = _resolve_huggingface_model_id(repo_id, display_name, provider)
    if existing_model_id:
        with ENGINE.begin() as conn:
            row = fetch_one(conn, select(models_table).where(models_table.c.id == existing_model_id))
            if row is None:
                return existing_model_id, "unchanged"
            values = _huggingface_discovery_existing_model_values(
                row,
                repo_id=repo_id,
                provider=provider,
                source_url=source_url,
                verified_at=verified_at,
                discovered_update_log_id=discovered_update_log_id,
                model_roles=model_roles,
                size_values=size_values,
                timestamp_values=timestamp_values,
                conn=conn,
            )
            if not values:
                return existing_model_id, "unchanged"
            conn.execute(
                update(models_table)
                .where(models_table.c.id == existing_model_id)
                .values(**values)
            )
            return existing_model_id, "updated"

    model_id = _choose_model_id(display_name, repo_id)
    identity = infer_model_identity(display_name, provider, repo_id)
    discovered_at = verified_at
    with ENGINE.begin() as conn:
        provider_id = _ensure_provider_row(provider, conn=conn)
        values = {
            "id": model_id,
            "name": display_name,
            "provider_id": provider_id,
            "provider": provider,
            "type": "open_weights",
            "model_roles_json": json.dumps(model_roles or [MODEL_ROLE_GENERATOR], ensure_ascii=True),
            "catalog_status": CATALOG_STATUS_PROVISIONAL,
            "release_date": None,
            "release_date_precision": None,
            "release_date_confidence": None,
            "release_date_source_name": None,
            "release_date_source_url": None,
            "release_date_verified_at": None,
            "context_window": None,
            "family_id": identity.family_id,
            "family_name": identity.family_name,
            "canonical_model_id": identity.canonical_model_id,
            "canonical_model_name": identity.canonical_model_name,
            "variant_label": identity.variant_label,
            "discovered_at": discovered_at,
            "discovered_update_log_id": discovered_update_log_id,
            "active": 1,
            "huggingface_repo_id": repo_id,
            "metadata_source_name": HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME,
            "metadata_source_url": source_url,
            "metadata_verified_at": verified_at,
            **timestamp_values,
            **size_values,
        }
        stmt = sqlite_insert(models_table).values(**values)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        result = conn.execute(stmt)
        if result.rowcount:
            return model_id, "created"
        conflict_row = fetch_one(conn, select(models_table).where(models_table.c.id == model_id))
        if conflict_row is not None:
            return str(conflict_row["id"]), "unchanged"

    return model_id, "unchanged"


def _resolve_huggingface_model_id(repo_id: str, display_name: str, provider: str) -> str | None:
    candidate_model_id = _choose_model_id(display_name, repo_id)
    display_names = {
        normalize_text(display_name),
        normalize_text(repo_id),
        normalize_text(repo_id.split("/", 1)[1] if "/" in repo_id else repo_id),
    }
    repo_id_norm = normalize_text(repo_id)
    with get_connection(ENGINE) as conn:
        repo_match = fetch_one(
            conn,
            select(models_table.c.id)
            .where(
                models_table.c.active == 1,
                models_table.c.huggingface_repo_id == repo_id,
            )
            .limit(1),
        )
        if repo_match is not None:
            return str(repo_match["id"])

        exact_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.canonical_model_name,
                models_table.c.openrouter_model_id,
            ).where(models_table.c.active == 1),
        )
    for row in exact_rows:
        if str(row.get("id") or "") == candidate_model_id:
            return str(row["id"])
        if normalize_text(str(row.get("openrouter_model_id") or "")) == repo_id_norm:
            return str(row["id"])
        row_names = {
            normalize_text(str(row.get("name") or "")),
            normalize_text(str(row.get("canonical_model_name") or "")),
        }
        if any(name and name in display_names for name in row_names):
            return str(row["id"])

    return None


def _huggingface_discovery_existing_model_values(
    row: dict[str, Any],
    *,
    repo_id: str,
    provider: str,
    source_url: str,
    verified_at: str,
    discovered_update_log_id: int | None,
    model_roles: list[str],
    size_values: dict[str, Any],
    timestamp_values: dict[str, Any],
    conn: Any,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if _model_field_missing(row, "huggingface_repo_id"):
        values["huggingface_repo_id"] = repo_id

    current_provider = _clean_text(row.get("provider"))
    if not current_provider or current_provider.lower() == "unknown":
        values["provider"] = provider
        values["provider_id"] = _ensure_provider_row(provider, conn=conn)

    current_roles = _normalise_model_roles(row.get("model_roles_json"), default=())
    merged_roles = sorted(dict.fromkeys([*current_roles, *model_roles]))
    if merged_roles and merged_roles != current_roles:
        values["model_roles_json"] = json.dumps(merged_roles, ensure_ascii=True)

    if _model_field_missing(row, "metadata_source_name"):
        values["metadata_source_name"] = HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME
        values["metadata_source_url"] = source_url
        values["metadata_verified_at"] = verified_at

    current_size_source = _clean_text(row.get("model_size_source_name"))
    if not current_size_source or current_size_source == HUGGINGFACE_MODEL_DISCOVERY_SOURCE_NAME:
        values.update(size_values)

    if timestamp_values.get("huggingface_created_at") and _model_field_missing(row, "huggingface_created_at"):
        values["huggingface_created_at"] = timestamp_values["huggingface_created_at"]
    if timestamp_values.get("huggingface_last_modified_at"):
        values["huggingface_last_modified_at"] = timestamp_values["huggingface_last_modified_at"]

    if _model_field_missing(row, "discovered_at"):
        values["discovered_at"] = verified_at
    if _model_field_missing(row, "discovered_update_log_id"):
        values["discovered_update_log_id"] = discovered_update_log_id

    return values


def _sync_provider_directory() -> None:
    with ENGINE.begin() as conn:
        provider_rows = fetch_all(conn, select(providers_table))
        providers_by_name = {
            normalize_text(str(row["name"])): str(row["id"])
            for row in provider_rows
            if str(row.get("name") or "").strip()
        }
        model_rows = fetch_all(
            conn,
            select(models_table.c.id, models_table.c.provider, models_table.c.provider_id),
        )

        pending_provider_rows: list[dict[str, Any]] = []
        pending_model_updates: list[tuple[str, str, str]] = []
        for row in model_rows:
            raw_provider_name = str(row.get("provider") or "").strip()
            provider_name = canonical_provider_name(raw_provider_name)
            if not provider_name or provider_name == "Unknown":
                continue

            provider_key = normalize_text(provider_name)
            provider_id = providers_by_name.get(provider_key)
            if provider_id is None:
                provider_id = provider_id_from_name(provider_name)
                providers_by_name[provider_key] = provider_id
                pending_provider_rows.append(
                    {
                        "id": provider_id,
                        "name": provider_name,
                        "country_code": None,
                        "country_name": None,
                        "origin_countries_json": "[]",
                        "origin_basis": None,
                        "source_url": None,
                        "verified_at": None,
                        "active": 1,
                    }
                )

            if str(row.get("provider_id") or "").strip() != provider_id or raw_provider_name != provider_name:
                pending_model_updates.append((str(row["id"]), provider_id, provider_name))

        if pending_provider_rows:
            stmt = sqlite_insert(providers_table).values(pending_provider_rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
            conn.execute(stmt)

        for model_id, provider_id, provider_name in pending_model_updates:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == model_id)
                .values(provider_id=provider_id, provider=provider_name)
            )


def _canonicalize_provider_aliases() -> None:
    with ENGINE.begin() as conn:
        provider_rows = fetch_all(conn, select(providers_table))
        for row in provider_rows:
            current_id = str(row.get("id") or "").strip()
            current_name = str(row.get("name") or "").strip()
            canonical_name = canonical_provider_name(current_name)
            if not current_id or not canonical_name:
                continue

            canonical_id = provider_id_from_name(canonical_name)
            if canonical_name == current_name and current_id == canonical_id:
                continue

            canonical_row = fetch_one(conn, select(providers_table).where(providers_table.c.id == canonical_id))
            if canonical_row is None:
                payload = {key: row.get(key) for key in row.keys()}
                payload.update(id=canonical_id, name=canonical_name, active=1)
                stmt = sqlite_insert(providers_table).values(payload)
                stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
                conn.execute(stmt)

            if current_id != canonical_id:
                conn.execute(
                    update(providers_table)
                    .where(providers_table.c.id == current_id)
                    .values(active=0)
                )
            else:
                conn.execute(
                    update(providers_table)
                    .where(providers_table.c.id == current_id)
                    .values(name=canonical_name, active=1)
                )


def _ensure_provider_row(provider_name: str | None, *, conn: Any | None = None) -> str | None:
    cleaned = canonical_provider_name(str(provider_name or "").strip())
    if not cleaned or cleaned == "Unknown":
        return None

    provider_id = provider_id_from_name(cleaned)
    stmt = sqlite_insert(providers_table).values(
        id=provider_id,
        name=cleaned,
        country_code=None,
        country_name=None,
        origin_countries_json="[]",
        origin_basis=None,
        source_url=None,
        verified_at=None,
        active=1,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
    if conn is not None:
        conn.execute(stmt)
    else:
        with ENGINE.begin() as local_conn:
            local_conn.execute(stmt)
    return provider_id


def _refresh_model_identity_metadata() -> None:
    with ENGINE.begin() as conn:
        identity_overrides_by_model_id, identity_overrides_by_match_key = _load_identity_override_indexes(conn)
        rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.provider,
                models_table.c.family_id,
                models_table.c.family_name,
                models_table.c.canonical_model_id,
                models_table.c.canonical_model_name,
                models_table.c.variant_label,
            ).where(models_table.c.active == 1),
        )
        for row in rows:
            override = identity_overrides_by_model_id.get(str(row["id"])) or identity_overrides_by_match_key.get(
                str(build_model_curation_match_key(row.get("provider"), row.get("name")) or "")
            )
            identity = _identity_from_override(override) or infer_model_identity(
                str(row["name"]),
                str(row.get("provider") or "Unknown"),
                str(row["id"]),
            )
            desired_values = {
                "family_id": identity.family_id,
                "family_name": identity.family_name,
                "canonical_model_id": identity.canonical_model_id,
                "canonical_model_name": identity.canonical_model_name,
                "variant_label": identity.variant_label,
            }
            current_values = {
                "family_id": row.get("family_id"),
                "family_name": row.get("family_name"),
                "canonical_model_id": row.get("canonical_model_id"),
                "canonical_model_name": row.get("canonical_model_name"),
                "variant_label": row.get("variant_label"),
            }
            if current_values == desired_values:
                continue
            conn.execute(
                update(models_table)
                .where(models_table.c.id == row["id"])
                .values(**desired_values)
            )


def _merge_duplicate_use_case_approvals(conn, duplicate_id: str, canonical_id: str) -> None:
    duplicate_rows = fetch_all(
        conn,
        select(model_use_case_approvals_table).where(
            model_use_case_approvals_table.c.model_id == duplicate_id
        ),
    )
    if not duplicate_rows:
        return

    stmt = sqlite_insert(model_use_case_approvals_table).values(
        [{**row, "model_id": canonical_id} for row in duplicate_rows]
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["model_id", "use_case_id"])
    conn.execute(stmt)
    conn.execute(
        delete(model_use_case_approvals_table).where(
            model_use_case_approvals_table.c.model_id == duplicate_id
        )
    )


def _merge_duplicate_recommendation_proposals(conn, duplicate_id: str, canonical_id: str) -> None:
    duplicate_rows = fetch_all(
        conn,
        select(model_use_case_recommendation_proposals_table).where(
            model_use_case_recommendation_proposals_table.c.model_id == duplicate_id
        ),
    )
    if not duplicate_rows:
        return

    stmt = sqlite_insert(model_use_case_recommendation_proposals_table).values(
        [{**row, "model_id": canonical_id} for row in duplicate_rows]
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["profile_id", "model_id", "use_case_id"])
    conn.execute(stmt)
    conn.execute(
        delete(model_use_case_recommendation_proposals_table).where(
            model_use_case_recommendation_proposals_table.c.model_id == duplicate_id
        )
    )


def _merge_duplicate_inference_destinations(conn, duplicate_id: str, canonical_id: str) -> None:
    duplicate_rows = fetch_all(
        conn,
        select(model_inference_destinations_table).where(
            model_inference_destinations_table.c.model_id == duplicate_id
        ),
    )
    if not duplicate_rows:
        return

    payload_rows: list[dict[str, Any]] = []
    for row in duplicate_rows:
        payload = {key: value for key, value in row.items() if key != "id"}
        payload["model_id"] = canonical_id
        payload_rows.append(payload)
    stmt = sqlite_insert(model_inference_destinations_table).values(payload_rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["model_id", "destination_id"])
    conn.execute(stmt)
    conn.execute(
        delete(model_inference_destinations_table).where(
            model_inference_destinations_table.c.model_id == duplicate_id
        )
    )


def _deactivate_source_identity_override(conn, source_model_id: str) -> None:
    conn.execute(
        update(model_identity_overrides_table)
        .where(model_identity_overrides_table.c.source_model_id == source_model_id)
        .values(active=0)
    )


def _merge_model_into_target(conn, duplicate_id: str, canonical_id: str) -> bool:
    normalized_duplicate_id = str(duplicate_id or "").strip()
    normalized_canonical_id = str(canonical_id or "").strip()
    if not normalized_duplicate_id or not normalized_canonical_id or normalized_duplicate_id == normalized_canonical_id:
        return False

    duplicate = fetch_one(
        conn,
        select(models_table).where(
            models_table.c.id == normalized_duplicate_id,
            models_table.c.active == 1,
        ),
    )
    canonical = fetch_one(
        conn,
        select(models_table).where(
            models_table.c.id == normalized_canonical_id,
            models_table.c.active == 1,
        ),
    )
    if duplicate is None or canonical is None:
        return False

    enrichment = _canonical_model_enrichment([duplicate, canonical], canonical)
    if enrichment:
        conn.execute(
            update(models_table)
            .where(models_table.c.id == normalized_canonical_id)
            .values(**enrichment)
        )

    conn.execute(
        update(scores_table)
        .where(scores_table.c.model_id == normalized_duplicate_id)
        .values(model_id=normalized_canonical_id)
    )
    _merge_duplicate_use_case_approvals(conn, normalized_duplicate_id, normalized_canonical_id)
    _merge_duplicate_recommendation_proposals(conn, normalized_duplicate_id, normalized_canonical_id)
    _merge_duplicate_inference_destinations(conn, normalized_duplicate_id, normalized_canonical_id)
    _merge_duplicate_inference_route_approvals(conn, normalized_duplicate_id, normalized_canonical_id)
    _merge_duplicate_market_snapshots(conn, normalized_duplicate_id, normalized_canonical_id)
    conn.execute(
        update(raw_source_records_table)
        .where(raw_source_records_table.c.normalized_model_id == normalized_duplicate_id)
        .values(normalized_model_id=normalized_canonical_id)
    )
    _deactivate_source_identity_override(conn, normalized_duplicate_id)
    conn.execute(
        models_table.delete().where(models_table.c.id == normalized_duplicate_id)
    )
    _sync_legacy_model_approval_columns(conn, normalized_canonical_id)
    return True


def _canonicalize_model_catalog() -> None:
    with ENGINE.begin() as conn:
        duplicate_override_rows = fetch_all(
            conn,
            select(model_duplicate_overrides_table)
            .where(model_duplicate_overrides_table.c.active == 1)
            .order_by(model_duplicate_overrides_table.c.updated_at.asc(), model_duplicate_overrides_table.c.id.asc()),
        )
        for override in duplicate_override_rows:
            _merge_model_into_target(
                conn,
                str(override.get("source_model_id") or ""),
                str(override.get("target_model_id") or ""),
            )

    with get_connection(ENGINE) as conn:
        model_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.provider,
                models_table.c.type,
                models_table.c.catalog_status,
                models_table.c.release_date,
                models_table.c.release_date_precision,
                models_table.c.release_date_confidence,
                models_table.c.release_date_source_name,
                models_table.c.release_date_source_url,
                models_table.c.release_date_verified_at,
                models_table.c.context_window,
                models_table.c.context_window_tokens,
                models_table.c.max_output_tokens,
                models_table.c.parameter_count_b,
                models_table.c.active_parameter_count_b,
                models_table.c.model_size_class,
                models_table.c.small_model_candidate,
                models_table.c.model_size_source_name,
                models_table.c.model_size_source_url,
                models_table.c.model_size_verified_at,
                models_table.c.openrouter_model_id,
                models_table.c.openrouter_canonical_slug,
                models_table.c.openrouter_added_at,
                models_table.c.huggingface_repo_id,
                models_table.c.huggingface_created_at,
                models_table.c.huggingface_last_modified_at,
                models_table.c.metadata_source_name,
                models_table.c.metadata_source_url,
                models_table.c.metadata_verified_at,
                models_table.c.model_card_url,
                models_table.c.model_card_source,
                models_table.c.model_card_verified_at,
                models_table.c.documentation_url,
                models_table.c.repo_url,
                models_table.c.paper_url,
                models_table.c.license_id,
                models_table.c.license_name,
                models_table.c.license_url,
                models_table.c.base_models_json,
                models_table.c.supported_languages_json,
                models_table.c.capabilities_json,
                models_table.c.intended_use_short,
                models_table.c.limitations_short,
                models_table.c.training_data_summary,
                models_table.c.training_cutoff,
                models_table.c.active,
            ).where(models_table.c.active == 1),
        )
        score_counts = {
            str(row["model_id"]): int(row["score_count"])
            for row in fetch_all(
                conn,
                select(
                    scores_table.c.model_id,
                    func.count().label("score_count"),
                ).group_by(scores_table.c.model_id),
            )
        }

    groups: dict[str, list[dict[str, Any]]] = {}
    for model_row in model_rows:
        signature = _preferred_model_signature(model_row)
        if not signature:
            continue
        groups.setdefault(signature, []).append(model_row)

    with ENGINE.begin() as conn:
        for group in groups.values():
            if len(group) < 2 or _has_provider_conflict(group):
                continue

            merge_group = [
                row for row in group
                if not _is_openrouter_exact_identity_row(row)
            ]
            if len(merge_group) < 2:
                continue

            canonical = _choose_canonical_model(merge_group, score_counts)
            canonical_id = str(canonical["id"])
            enrichment = _canonical_model_enrichment(merge_group, canonical)
            if enrichment:
                conn.execute(
                    update(models_table)
                    .where(models_table.c.id == canonical_id)
                    .values(**enrichment)
                )

            for duplicate in merge_group:
                duplicate_id = str(duplicate["id"])
                if duplicate_id == canonical_id:
                    continue
                _merge_model_into_target(conn, duplicate_id, canonical_id)

        active_rows = fetch_all(
            conn,
            select(models_table.c.id, models_table.c.name).where(models_table.c.active == 1),
        )
        for row in active_rows:
            current_name = str(row.get("name") or row.get("id") or "")
            suggested_name = _suggest_display_name(current_name)
            if suggested_name and _readable_name_score(suggested_name) > _readable_name_score(current_name):
                conn.execute(
                    update(models_table)
                    .where(models_table.c.id == row["id"])
                    .values(name=suggested_name)
                )


def _merge_duplicate_market_snapshots(conn, duplicate_id: str, canonical_id: str) -> None:
    canonical_rows = fetch_all(
        conn,
        select(
            model_market_snapshots_table.c.id,
            model_market_snapshots_table.c.source_name,
            model_market_snapshots_table.c.scope,
            model_market_snapshots_table.c.category_slug,
            model_market_snapshots_table.c.snapshot_date,
        ).where(model_market_snapshots_table.c.model_id == canonical_id),
    )
    canonical_keys = {
        (
            str(row.get("source_name") or ""),
            str(row.get("scope") or ""),
            str(row.get("category_slug") or ""),
            str(row.get("snapshot_date") or ""),
        )
        for row in canonical_rows
    }
    duplicate_rows = fetch_all(
        conn,
        select(
            model_market_snapshots_table.c.id,
            model_market_snapshots_table.c.source_name,
            model_market_snapshots_table.c.scope,
            model_market_snapshots_table.c.category_slug,
            model_market_snapshots_table.c.snapshot_date,
        ).where(model_market_snapshots_table.c.model_id == duplicate_id),
    )

    duplicate_snapshot_ids_to_delete: list[int] = []
    duplicate_snapshot_ids_to_update: list[int] = []
    for row in duplicate_rows:
        snapshot_key = (
            str(row.get("source_name") or ""),
            str(row.get("scope") or ""),
            str(row.get("category_slug") or ""),
            str(row.get("snapshot_date") or ""),
        )
        if snapshot_key in canonical_keys:
            duplicate_snapshot_ids_to_delete.append(int(row["id"]))
        else:
            duplicate_snapshot_ids_to_update.append(int(row["id"]))
            canonical_keys.add(snapshot_key)

    if duplicate_snapshot_ids_to_delete:
        conn.execute(
            delete(model_market_snapshots_table).where(
                model_market_snapshots_table.c.id.in_(duplicate_snapshot_ids_to_delete)
            )
        )
    if duplicate_snapshot_ids_to_update:
        conn.execute(
            update(model_market_snapshots_table)
            .where(model_market_snapshots_table.c.id.in_(duplicate_snapshot_ids_to_update))
            .values(model_id=canonical_id)
        )


def _merge_duplicate_inference_route_approvals(conn, duplicate_id: str, canonical_id: str) -> None:
    duplicate_rows = fetch_all(
        conn,
        select(model_use_case_inference_approvals_table).where(
            model_use_case_inference_approvals_table.c.model_id == duplicate_id
        ),
    )
    if not duplicate_rows:
        return

    stmt = sqlite_insert(model_use_case_inference_approvals_table).values(
        [{**row, "model_id": canonical_id} for row in duplicate_rows]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["model_id", "use_case_id", "destination_id", "location_key"],
        set_={
            "location_label": stmt.excluded.location_label,
            "approved_for_use": stmt.excluded.approved_for_use,
            "approval_notes": stmt.excluded.approval_notes,
            "approval_updated_at": stmt.excluded.approval_updated_at,
        },
    )
    conn.execute(stmt)
    conn.execute(
        delete(model_use_case_inference_approvals_table).where(
            model_use_case_inference_approvals_table.c.model_id == duplicate_id
        )
    )


def _refresh_openrouter_model_metadata() -> None:
    with get_connection(ENGINE) as conn:
        model_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.provider,
                models_table.c.catalog_status,
                models_table.c.family_name,
                models_table.c.canonical_model_id,
                models_table.c.canonical_model_name,
                models_table.c.variant_label,
                models_table.c.model_roles_json,
                models_table.c.metadata_source_name,
                models_table.c.openrouter_model_id,
                models_table.c.openrouter_canonical_slug,
            ).where(models_table.c.active == 1),
        )

    if not model_rows:
        return

    canonical_id_lookup = {
        str(row["canonical_model_id"]): str(row["id"])
        for row in model_rows
        if row.get("canonical_model_id")
    }
    canonical_name_lookup = {
        normalize_text(str(row.get("canonical_model_name") or row.get("name") or "")): str(row["id"])
        for row in model_rows
        if normalize_text(str(row.get("canonical_model_name") or row.get("name") or ""))
    }
    resolution_indexes = _build_name_resolution_indexes(model_rows)
    model_rows_by_id = {str(row["id"]): row for row in model_rows}
    model_rows_by_canonical_id = {
        str(row["canonical_model_id"]): row
        for row in model_rows
        if str(row.get("canonical_model_id") or "").strip()
    }
    existing_canonical_model_ids = {
        str(row["canonical_model_id"])
        for row in model_rows
        if str(row.get("canonical_model_id") or "").strip()
    }
    represented_openrouter_keys = {
        key
        for row in model_rows
        for key in (
            str(row.get("openrouter_model_id") or "").strip(),
            str(row.get("openrouter_canonical_slug") or "").strip(),
        )
        if key
    }

    items = _fetch_openrouter_models()
    verified_at = utc_now_iso()
    best_item_by_model_id: dict[str, dict[str, Any]] = {}
    unmatched_best_items: dict[str, dict[str, Any]] = {}
    exact_release_items: dict[str, dict[str, Any]] = {}

    for item in items:
        model_id = _resolve_openrouter_model_id(
            item,
            resolution_indexes=resolution_indexes,
            canonical_id_lookup=canonical_id_lookup,
            canonical_name_lookup=canonical_name_lookup,
        )
        import_as_exact_release = _should_import_openrouter_exact_release(
            item,
            represented_openrouter_keys=represented_openrouter_keys,
            existing_canonical_model_ids=existing_canonical_model_ids,
            model_rows_by_canonical_id=model_rows_by_canonical_id,
            resolved_model_row=model_rows_by_id.get(model_id) if model_id else None,
            resolved_model_id=model_id,
            require_release_alias=True,
            verified_at=verified_at,
        )
        if import_as_exact_release:
            exact_key = _openrouter_exact_release_import_key(item)
            if exact_key:
                current_exact = exact_release_items.get(exact_key)
                if current_exact is None or _openrouter_item_rank(item) > _openrouter_item_rank(current_exact):
                    exact_release_items[exact_key] = item
            if model_id:
                continue

        if not model_id:
            if import_as_exact_release:
                continue
            unresolved_key = str(item.get("canonical_slug") or item.get("id") or "").strip()
            if unresolved_key:
                current_unmatched = unmatched_best_items.get(unresolved_key)
                if current_unmatched is None or _openrouter_item_rank(item) > _openrouter_item_rank(current_unmatched):
                    unmatched_best_items[unresolved_key] = item
            continue
        current = best_item_by_model_id.get(model_id)
        if current is None or _openrouter_item_rank(item) > _openrouter_item_rank(current):
            best_item_by_model_id[model_id] = item

    represented_after_updates = set(represented_openrouter_keys)
    for item in best_item_by_model_id.values():
        represented_after_updates.update(_openrouter_identity_keys(item))
    for item in exact_release_items.values():
        represented_after_updates.update(_openrouter_identity_keys(item))

    for item in items:
        model_id = _resolve_openrouter_model_id(
            item,
            resolution_indexes=resolution_indexes,
            canonical_id_lookup=canonical_id_lookup,
            canonical_name_lookup=canonical_name_lookup,
        )
        if not _should_import_openrouter_exact_release(
            item,
            represented_openrouter_keys=represented_after_updates,
            existing_canonical_model_ids=existing_canonical_model_ids,
            model_rows_by_canonical_id=model_rows_by_canonical_id,
            resolved_model_row=model_rows_by_id.get(model_id) if model_id else None,
            resolved_model_id=model_id,
            require_release_alias=False,
            verified_at=verified_at,
        ):
            continue
        exact_key = _openrouter_exact_release_import_key(item)
        if not exact_key:
            continue
        current_exact = exact_release_items.get(exact_key)
        if current_exact is None or _openrouter_item_rank(item) > _openrouter_item_rank(current_exact):
            exact_release_items[exact_key] = item
        represented_after_updates.update(_openrouter_identity_keys(item))

    with ENGINE.begin() as conn:
        for model_id, item in best_item_by_model_id.items():
            values = _openrouter_model_values(
                item,
                verified_at=verified_at,
                current_model_roles=model_rows_by_id.get(model_id, {}).get("model_roles_json"),
                current_metadata_source_name=model_rows_by_id.get(model_id, {}).get("metadata_source_name"),
                current_catalog_status=model_rows_by_id.get(model_id, {}).get("catalog_status"),
            )
            if not values:
                continue
            conn.execute(
                update(models_table)
                .where(models_table.c.id == model_id)
                .values(**values)
            )
        _import_openrouter_provisional_models(
            conn,
            unmatched_items=list(unmatched_best_items.values()),
            existing_canonical_model_ids=existing_canonical_model_ids,
            verified_at=verified_at,
        )
        _import_openrouter_provisional_models(
            conn,
            unmatched_items=list(exact_release_items.values()),
            existing_canonical_model_ids=existing_canonical_model_ids,
            verified_at=verified_at,
            allow_existing_canonical_model_ids=True,
        )


def _refresh_openrouter_market_signals() -> None:
    with get_connection(ENGINE) as conn:
        model_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.provider,
                models_table.c.family_name,
                models_table.c.canonical_model_id,
                models_table.c.canonical_model_name,
                models_table.c.variant_label,
            ).where(models_table.c.active == 1),
        )

    if not model_rows:
        return

    canonical_id_lookup = {
        str(row["canonical_model_id"]): str(row["id"])
        for row in model_rows
        if row.get("canonical_model_id")
    }
    canonical_name_lookup = {
        normalize_text(str(row.get("canonical_model_name") or row.get("name") or "")): str(row["id"])
        for row in model_rows
        if normalize_text(str(row.get("canonical_model_name") or row.get("name") or ""))
    }
    resolution_indexes = _build_name_resolution_indexes(model_rows)

    global_entries = _fetch_openrouter_global_rankings()
    programming_entries = _fetch_openrouter_programming_rankings()
    verified_at = utc_now_iso()

    global_signals, global_snapshots = _build_openrouter_global_signals(
        global_entries,
        verified_at=verified_at,
        resolution_indexes=resolution_indexes,
        canonical_id_lookup=canonical_id_lookup,
        canonical_name_lookup=canonical_name_lookup,
    )
    programming_signals, programming_snapshots = _build_openrouter_programming_signals(
        programming_entries,
        verified_at=verified_at,
        resolution_indexes=resolution_indexes,
        canonical_id_lookup=canonical_id_lookup,
        canonical_name_lookup=canonical_name_lookup,
    )

    updates_by_model_id: dict[str, dict[str, Any]] = {}
    for model_id, values in global_signals.items():
        updates_by_model_id.setdefault(model_id, {}).update(values)
    for model_id, values in programming_signals.items():
        updates_by_model_id.setdefault(model_id, {}).update(values)

    with ENGINE.begin() as conn:
        conn.execute(
            update(models_table)
            .where(models_table.c.active == 1)
            .values(**_empty_openrouter_market_values())
        )

        snapshot_rows = global_snapshots + programming_snapshots
        if snapshot_rows:
            stmt = sqlite_insert(model_market_snapshots_table).values(snapshot_rows)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["source_name", "scope", "category_slug", "snapshot_date", "model_id"]
            )
            conn.execute(stmt)

        for model_id, values in updates_by_model_id.items():
            source_url = values.pop("_market_source_url", OPENROUTER_RANKINGS_URL)
            conn.execute(
                update(models_table)
                .where(models_table.c.id == model_id)
                .values(
                    **values,
                    market_source_name=OPENROUTER_MARKET_SOURCE_NAME,
                    market_source_url=source_url,
                    market_verified_at=verified_at,
                )
            )


def _fetch_openrouter_models() -> list[dict[str, Any]]:
    return openrouter_metadata.fetch_openrouter_models(
        url=OPENROUTER_MODELS_URL,
        headers=HTTP_HEADERS,
        params={"output_modalities": "all"},
    )


def _fetch_openrouter_global_rankings() -> list[dict[str, Any]]:
    try:
        payloads = _fetch_openrouter_flight_payloads(OPENROUTER_RANKINGS_URL)
        return openrouter_metadata.extract_global_rankings(payloads)
    except ValueError as exc:
        raise OptionalSourceUnavailable(str(exc)) from exc


def _fetch_openrouter_programming_rankings() -> list[dict[str, Any]]:
    try:
        payloads = _fetch_openrouter_flight_payloads(OPENROUTER_PROGRAMMING_COLLECTION_URL)
        return openrouter_metadata.extract_programming_rankings(payloads)
    except ValueError as exc:
        raise OptionalSourceUnavailable(str(exc)) from exc


def _fetch_openrouter_flight_payloads(url: str) -> list[dict[str, Any]]:
    return openrouter_metadata.fetch_openrouter_flight_payloads(
        url=url,
        headers=HTTP_HEADERS,
        next_flight_push_re=_NEXT_FLIGHT_PUSH_RE,
    )


def _iter_openrouter_payload_dicts(value: Any) -> Iterable[dict[str, Any]]:
    yield from openrouter_metadata.iter_openrouter_payload_dicts(value)


def _find_openrouter_payload(
    payloads: Iterable[dict[str, Any]],
    predicate,
) -> dict[str, Any] | None:
    return openrouter_metadata.find_openrouter_payload(payloads, predicate)


def _build_openrouter_global_signals(
    entries: list[dict[str, Any]],
    *,
    verified_at: str,
    resolution_indexes: dict[str, dict[str, str]],
    canonical_id_lookup: dict[str, str],
    canonical_name_lookup: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    totals_by_model_id: dict[str, dict[str, Any]] = {}
    total_tokens_all = 0
    snapshot_date = _latest_snapshot_date(entries, date_key="date")

    for entry in entries:
        total_tokens = _openrouter_ranking_total_tokens(entry)
        if total_tokens <= 0:
            continue

        total_tokens_all += total_tokens
        model_id = _resolve_openrouter_model_id(
            {
                "id": str(entry.get("variant_permaslug") or entry.get("model_permaslug") or "").strip(),
                "canonical_slug": str(entry.get("model_permaslug") or "").strip(),
            },
            resolution_indexes=resolution_indexes,
            canonical_id_lookup=canonical_id_lookup,
            canonical_name_lookup=canonical_name_lookup,
        )
        if not model_id:
            continue

        current = totals_by_model_id.setdefault(
            model_id,
            {
                "openrouter_slug": str(entry.get("variant_permaslug") or entry.get("model_permaslug") or "").strip(),
                "total_tokens": 0,
                "request_count": 0,
                "change_weight": 0,
                "change_weighted_sum": 0.0,
                "rows": [],
            },
        )
        current["rows"].append(entry)
        current["total_tokens"] += total_tokens
        current["request_count"] += _safe_int(entry.get("count")) or 0

        current_slug = str(current.get("openrouter_slug") or "")
        candidate_slug = str(entry.get("variant_permaslug") or entry.get("model_permaslug") or "").strip()
        if total_tokens > 0 and (not current_slug or total_tokens >= int(current["total_tokens"]) - total_tokens):
            current["openrouter_slug"] = candidate_slug or current_slug

        change_ratio = _safe_float(entry.get("change"))
        if change_ratio is not None:
            current["change_weight"] += total_tokens
            current["change_weighted_sum"] += change_ratio * total_tokens

    ordered = sorted(
        totals_by_model_id.items(),
        key=lambda item: (
            -int(item[1]["total_tokens"]),
            -int(item[1]["request_count"]),
            item[0],
        ),
    )

    values_by_model_id: dict[str, dict[str, Any]] = {}
    snapshots: list[dict[str, Any]] = []
    for rank, (model_id, data) in enumerate(ordered, start=1):
        total_tokens = int(data["total_tokens"])
        request_count = int(data["request_count"])
        share = (total_tokens / total_tokens_all) if total_tokens_all > 0 else None
        change_weight = int(data["change_weight"])
        change_ratio = (float(data["change_weighted_sum"]) / change_weight) if change_weight > 0 else None
        values_by_model_id[model_id] = {
            "openrouter_global_rank": rank,
            "openrouter_global_total_tokens": total_tokens,
            "openrouter_global_share": share,
            "openrouter_global_change_ratio": change_ratio,
            "openrouter_global_request_count": request_count,
            "_market_source_url": OPENROUTER_RANKINGS_URL,
        }
        snapshots.append(
            _openrouter_market_snapshot_row(
                scope="global",
                category_slug="",
                snapshot_date=snapshot_date,
                model_id=model_id,
                openrouter_slug=str(data.get("openrouter_slug") or "") or None,
                rank=rank,
                total_tokens=total_tokens,
                share=share,
                change_ratio=change_ratio,
                request_count=request_count,
                volume=None,
                source_url=OPENROUTER_RANKINGS_URL,
                payload={
                    "rows": data["rows"],
                    "verified_at": verified_at,
                },
                collected_at=verified_at,
            )
        )

    return values_by_model_id, snapshots


def _build_openrouter_programming_signals(
    entries: list[dict[str, Any]],
    *,
    verified_at: str,
    resolution_indexes: dict[str, dict[str, str]],
    canonical_id_lookup: dict[str, str],
    canonical_name_lookup: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    data_by_model_id: dict[str, dict[str, Any]] = {}
    snapshot_date = _latest_snapshot_date(entries, date_key="date")

    for entry in entries:
        model_slug = str(entry.get("model_slug") or entry.get("model") or "").strip()
        if not model_slug:
            continue

        model_id = _resolve_openrouter_model_id(
            {
                "id": model_slug,
                "canonical_slug": model_slug,
            },
            resolution_indexes=resolution_indexes,
            canonical_id_lookup=canonical_id_lookup,
            canonical_name_lookup=canonical_name_lookup,
        )
        if not model_id:
            continue

        total_tokens = _openrouter_category_total_tokens(entry)
        request_count = _safe_int(entry.get("count")) or 0
        volume = _safe_float(entry.get("volume"))
        rank = _safe_int(entry.get("rank"))

        current = data_by_model_id.setdefault(
            model_id,
            {
                "openrouter_slug": model_slug,
                "rank": rank,
                "total_tokens": 0,
                "request_count": 0,
                "volume": None,
                "rows": [],
            },
        )
        current["rows"].append(entry)
        current["total_tokens"] += total_tokens
        current["request_count"] += request_count
        if rank is not None and (current.get("rank") is None or rank < int(current["rank"])):
            current["rank"] = rank
        if volume is not None:
            current["volume"] = max(float(current["volume"] or 0.0), volume)

    values_by_model_id: dict[str, dict[str, Any]] = {}
    snapshots: list[dict[str, Any]] = []
    for model_id, data in sorted(
        data_by_model_id.items(),
        key=lambda item: (
            int(item[1]["rank"]) if item[1].get("rank") is not None else 1_000_000,
            -int(item[1]["total_tokens"]),
            item[0],
        ),
    ):
        rank = _safe_int(data.get("rank"))
        total_tokens = int(data["total_tokens"])
        request_count = int(data["request_count"])
        volume = _safe_float(data.get("volume"))
        values_by_model_id[model_id] = {
            "openrouter_programming_rank": rank,
            "openrouter_programming_total_tokens": total_tokens,
            "openrouter_programming_volume": volume,
            "openrouter_programming_request_count": request_count,
            "_market_source_url": OPENROUTER_PROGRAMMING_COLLECTION_URL,
        }
        snapshots.append(
            _openrouter_market_snapshot_row(
                scope="category",
                category_slug="programming",
                snapshot_date=snapshot_date,
                model_id=model_id,
                openrouter_slug=str(data.get("openrouter_slug") or "") or None,
                rank=rank or 0,
                total_tokens=total_tokens,
                share=None,
                change_ratio=None,
                request_count=request_count,
                volume=volume,
                source_url=OPENROUTER_PROGRAMMING_COLLECTION_URL,
                payload={
                    "rows": data["rows"],
                    "verified_at": verified_at,
                },
                collected_at=verified_at,
            )
        )

    return values_by_model_id, snapshots


def _openrouter_market_snapshot_row(
    *,
    scope: str,
    category_slug: str,
    snapshot_date: str,
    model_id: str,
    openrouter_slug: str | None,
    rank: int,
    total_tokens: int | None,
    share: float | None,
    change_ratio: float | None,
    request_count: int | None,
    volume: float | None,
    source_url: str,
    payload: dict[str, Any],
    collected_at: str,
) -> dict[str, Any]:
    return {
        "source_name": OPENROUTER_MARKET_SOURCE_NAME,
        "scope": scope,
        "category_slug": category_slug,
        "snapshot_date": snapshot_date,
        "model_id": model_id,
        "openrouter_slug": openrouter_slug,
        "rank": rank,
        "total_tokens": total_tokens,
        "share": share,
        "change_ratio": change_ratio,
        "request_count": request_count,
        "volume": volume,
        "source_url": source_url,
        "payload_json": json.dumps(payload, ensure_ascii=True),
        "collected_at": collected_at,
    }


def _empty_openrouter_market_values() -> dict[str, Any]:
    return {
        "openrouter_global_rank": None,
        "openrouter_global_total_tokens": None,
        "openrouter_global_share": None,
        "openrouter_global_change_ratio": None,
        "openrouter_global_request_count": None,
        "openrouter_programming_rank": None,
        "openrouter_programming_total_tokens": None,
        "openrouter_programming_volume": None,
        "openrouter_programming_request_count": None,
        "market_source_name": None,
        "market_source_url": None,
        "market_verified_at": None,
    }


def _latest_snapshot_date(entries: Iterable[dict[str, Any]], *, date_key: str) -> str:
    dates = [str(entry.get(date_key) or "").strip() for entry in entries if str(entry.get(date_key) or "").strip()]
    return max(dates) if dates else utc_now_iso()


def _openrouter_ranking_total_tokens(entry: dict[str, Any]) -> int:
    return sum(
        _safe_int(entry.get(field)) or 0
        for field in ("total_prompt_tokens", "total_completion_tokens", "total_native_tokens_reasoning")
    )


def _openrouter_category_total_tokens(entry: dict[str, Any]) -> int:
    return sum(
        _safe_int(entry.get(field)) or 0
        for field in ("total_prompt_tokens", "total_completion_tokens")
    )


def _resolve_openrouter_model_id(
    item: dict[str, Any],
    *,
    resolution_indexes: dict[str, dict[str, str]],
    canonical_id_lookup: dict[str, str],
    canonical_name_lookup: dict[str, str],
) -> str | None:
    for candidate in _openrouter_candidate_names(item):
        resolved = _resolve_model_candidate_from_indexes(candidate, resolution_indexes)
        if resolved:
            return resolved

    provider_hint = _openrouter_provider_name(item)
    model_id = str(item.get("id") or "").strip()
    for candidate in _openrouter_candidate_names(item):
        identity = infer_model_identity(candidate, provider_hint, model_id or None)
        if identity.canonical_model_id in canonical_id_lookup:
            return canonical_id_lookup[identity.canonical_model_id]
        canonical_name = normalize_text(identity.canonical_model_name)
        if canonical_name in canonical_name_lookup:
            return canonical_name_lookup[canonical_name]

    return None


def _build_name_resolution_indexes(model_rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    exact_lookup: dict[str, str] = {}
    alias_lookup: dict[str, str] = {}
    signature_lookup: dict[str, str] = {}
    ordered_rows = sorted(model_rows, key=_model_resolution_priority)
    normalized_lookup = build_model_lookup(ordered_rows)

    for row in ordered_rows:
        normalized_model = normalized_lookup[str(row["id"])]
        model_id = str(row["id"])
        for alias in normalized_model.exact_names:
            exact_lookup.setdefault(alias, model_id)
        for alias in normalized_model.aliases:
            alias_lookup.setdefault(alias, model_id)
        for signature in normalized_model.signatures:
            signature_lookup.setdefault(signature, model_id)

    return {
        "exact": exact_lookup,
        "alias": alias_lookup,
        "signature": signature_lookup,
    }


def _resolve_model_candidate_from_indexes(
    raw_name: str,
    resolution_indexes: dict[str, dict[str, str]],
) -> str | None:
    normalized = normalize_text(raw_name)
    compact = normalized.replace(" ", "")
    for key in (normalized, compact):
        if key:
            resolved = resolution_indexes["exact"].get(key) or resolution_indexes["alias"].get(key)
            if resolved:
                return resolved

    for signature in name_signatures(raw_name):
        resolved = resolution_indexes["signature"].get(signature)
        if resolved:
            return resolved
    return None


def _model_resolution_priority(row: dict[str, Any]) -> tuple[int, int, str]:
    provider_unknown = 1 if not row.get("provider") or str(row.get("provider")).lower() == "unknown" else 0
    has_provider_prefix = 1 if "/" in str(row.get("name") or "") else 0
    return (provider_unknown, has_provider_prefix, str(row["id"]))


def _openrouter_candidate_names(item: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    display_name = _openrouter_display_name(item)
    model_id = str(item.get("id") or "").strip()
    canonical_slug = str(item.get("canonical_slug") or "").strip()
    hugging_face_id = str(item.get("hugging_face_id") or "").strip()

    for candidate in (
        display_name,
        model_id,
        model_id.split("/", 1)[1] if "/" in model_id else model_id,
        canonical_slug,
        canonical_slug.split("/", 1)[1] if "/" in canonical_slug else canonical_slug,
        hugging_face_id,
        hugging_face_id.split("/", 1)[1] if "/" in hugging_face_id else hugging_face_id,
    ):
        for variant in _openrouter_name_variants(candidate):
            if variant and variant not in candidates:
                candidates.append(variant)
    return candidates


def _openrouter_name_variants(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []

    variants: list[str] = []
    pending = [text]
    seen: set[str] = set()
    while pending:
        candidate = pending.pop()
        candidate = str(candidate or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        variants.append(candidate)

        parenthetical_stripped = _DISPLAY_TRAILING_PAREN_VARIANT_RE.sub("", candidate).strip(" -_:")
        if parenthetical_stripped and parenthetical_stripped != candidate:
            pending.append(parenthetical_stripped)

        alias_stripped = _OPENROUTER_TRAILING_ALIAS_RE.sub("", candidate).strip(" -_:")
        if alias_stripped and alias_stripped != candidate:
            pending.append(alias_stripped)

        version_stripped = _OPENROUTER_TRAILING_VERSION_RE.sub("", candidate).strip(" -_:")
        if version_stripped and version_stripped != candidate:
            pending.append(version_stripped)

    return variants


def _openrouter_display_name(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    if not name:
        model_id = str(item.get("id") or "").strip()
        return model_id.split("/", 1)[1] if "/" in model_id else model_id
    if ":" in name:
        return name.split(":", 1)[1].strip()
    return name


def _openrouter_provider_name(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    if ":" in name:
        provider_name = name.split(":", 1)[0].strip()
        if provider_name:
            return canonical_provider_name(provider_name)

    model_id = str(item.get("id") or "").strip()
    provider_slug = model_id.split("/", 1)[0].strip().lower() if "/" in model_id else ""
    provider_map = {
        "amazon": "Amazon",
        "anthropic": "Anthropic",
        "azure": "Microsoft",
        "openai": "OpenAI",
        "google": "Google",
        "microsoft": "Microsoft",
        "x-ai": "xAI",
        "xai": "xAI",
        "moonshotai": "Moonshot",
        "qwen": "Alibaba",
        "z-ai": "Z AI",
        "zhipu": "Zhipu AI",
    }
    return canonical_provider_name(provider_map.get(provider_slug, provider_slug or "Unknown"))


def _should_import_openrouter_exact_release(
    item: dict[str, Any],
    *,
    represented_openrouter_keys: set[str],
    existing_canonical_model_ids: set[str],
    model_rows_by_canonical_id: dict[str, dict[str, Any]],
    resolved_model_row: dict[str, Any] | None,
    resolved_model_id: str | None,
    require_release_alias: bool,
    verified_at: str,
) -> bool:
    identity_keys = _openrouter_identity_keys(item)
    if not identity_keys or identity_keys.intersection(represented_openrouter_keys):
        return False
    if resolved_model_id and resolved_model_row is not None:
        return not require_release_alias or _openrouter_row_looks_like_release_alias(resolved_model_row)

    model_id = str(item.get("id") or "").strip()
    canonical_slug = str(item.get("canonical_slug") or "").strip()
    display_name = _suggest_display_name(_openrouter_display_name(item)) or _openrouter_display_name(item) or model_id
    identity = infer_model_identity(
        display_name,
        _openrouter_provider_name(item),
        canonical_slug or model_id or None,
    )
    if identity.canonical_model_id not in existing_canonical_model_ids:
        if not require_release_alias and _openrouter_item_is_recent_release(item, verified_at=verified_at):
            return True
        return False
    if not require_release_alias:
        return True
    return _openrouter_row_looks_like_release_alias(model_rows_by_canonical_id.get(identity.canonical_model_id, {}))


def _openrouter_row_looks_like_release_alias(row: dict[str, Any]) -> bool:
    values = (
        str(row.get("id") or ""),
        str(row.get("name") or ""),
    )
    alias_token_pattern = re.compile(r"(?<![a-z0-9])(preview|latest)(?![a-z0-9])", re.IGNORECASE)
    if any(alias_token_pattern.search(value) for value in values):
        return True
    return any(value.startswith("~") for value in values)


def _openrouter_identity_keys(item: dict[str, Any]) -> set[str]:
    return {
        key
        for key in (
            str(item.get("id") or "").strip(),
            str(item.get("canonical_slug") or "").strip(),
        )
        if key
    }


def _openrouter_exact_release_import_key(item: dict[str, Any]) -> str:
    return str(item.get("canonical_slug") or item.get("id") or "").strip()


def _openrouter_item_rank(item: dict[str, Any]) -> tuple[Any, ...]:
    model_id = str(item.get("id") or "")
    canonical_slug = str(item.get("canonical_slug") or "")
    top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
    pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    context_length = _safe_int(top_provider.get("context_length")) or _safe_int(item.get("context_length")) or 0
    max_completion_tokens = _safe_int(top_provider.get("max_completion_tokens")) or 0
    price_fields = sum(
        1 for key in ("prompt", "completion")
        if _safe_float(pricing.get(key)) is not None
    )
    return (
        int(model_id == canonical_slug and model_id != ""),
        int(":free" not in model_id),
        int(not _openrouter_item_looks_like_release_alias(item)),
        price_fields,
        int(max_completion_tokens > 0),
        context_length,
        model_id,
    )


def _openrouter_item_looks_like_release_alias(item: dict[str, Any]) -> bool:
    values = (
        str(item.get("name") or ""),
        str(item.get("id") or ""),
        str(item.get("canonical_slug") or ""),
    )
    alias_token_pattern = re.compile(r"(?<![a-z0-9])(preview|latest)(?![a-z0-9])", re.IGNORECASE)
    if any(alias_token_pattern.search(value) for value in values):
        return True
    return any(value.startswith("~") for value in values)


def _openrouter_item_is_recent_release(item: dict[str, Any], *, verified_at: str) -> bool:
    created_at = _openrouter_created_at(item.get("created"))
    if not created_at:
        return False
    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        verified_dt = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return created_dt >= verified_dt - timedelta(days=OPENROUTER_NEW_RELEASE_LOOKBACK_DAYS)


def _openrouter_model_values(
    item: dict[str, Any],
    *,
    verified_at: str,
    current_model_roles: Any | None = None,
    current_metadata_source_name: Any | None = None,
    current_catalog_status: Any | None = None,
) -> dict[str, Any]:
    top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
    pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    architecture = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
    context_tokens = _safe_int(top_provider.get("context_length")) or _safe_int(item.get("context_length"))
    max_output_tokens = _safe_int(top_provider.get("max_completion_tokens"))
    input_price = _pricing_per_mtok(pricing.get("prompt"))
    output_price = _pricing_per_mtok(pricing.get("completion"))
    huggingface_repo_id = _clean_text(item.get("hugging_face_id"))
    openrouter_capabilities = _build_openrouter_capabilities(
        architecture=architecture,
        supported_parameters=item.get("supported_parameters"),
    )

    values: dict[str, Any] = {}
    if not _clean_text(current_metadata_source_name) or _clean_text(current_metadata_source_name) == "openrouter" or _clean_text(current_catalog_status) == CATALOG_STATUS_PROVISIONAL:
        values.update(
            metadata_source_name="openrouter",
            metadata_source_url=OPENROUTER_MODELS_URL,
            metadata_verified_at=verified_at,
        )

    model_id = str(item.get("id") or "").strip()
    canonical_slug = str(item.get("canonical_slug") or "").strip()
    if model_id:
        values["openrouter_model_id"] = model_id
    if canonical_slug:
        values["openrouter_canonical_slug"] = canonical_slug
    created_at = _openrouter_created_at(item.get("created"))
    if created_at:
        values["openrouter_added_at"] = created_at
    if huggingface_repo_id:
        values["huggingface_repo_id"] = huggingface_repo_id
    if context_tokens is not None:
        values["context_window_tokens"] = context_tokens
        values["context_window"] = _format_context_window_tokens(context_tokens)
    if max_output_tokens is not None:
        values["max_output_tokens"] = max_output_tokens
    if input_price is not None:
        values["price_input_per_mtok"] = input_price
    if output_price is not None:
        values["price_output_per_mtok"] = output_price
    if openrouter_capabilities:
        values["capabilities_json"] = json.dumps(openrouter_capabilities, ensure_ascii=True)
    inferred_roles = _merge_inferred_audio_roles(
        current_model_roles if current_model_roles is not None else (MODEL_ROLE_GENERATOR,),
        capabilities=openrouter_capabilities,
        names=(model_id, canonical_slug, item.get("name"), huggingface_repo_id),
    )
    if MODEL_ROLE_SPEECH_TO_TEXT in inferred_roles or MODEL_ROLE_TEXT_TO_SPEECH in inferred_roles:
        values["model_roles_json"] = json.dumps(inferred_roles, ensure_ascii=True)

    return values


def _build_openrouter_capabilities(
    *,
    architecture: dict[str, Any] | None,
    supported_parameters: Any,
) -> list[str]:
    capabilities: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = _clean_text(value)
        if not text:
            return
        normalized = text.lower()
        if normalized in seen:
            return
        seen.add(normalized)
        capabilities.append(text)

    architecture = architecture or {}
    add(architecture.get("modality"))
    for modality in architecture.get("input_modalities") or []:
        add(f"{modality}-input")
    for modality in architecture.get("output_modalities") or []:
        add(f"{modality}-output")

    parameter_map = {
        "tools": "tool-use",
        "tool_choice": "tool-choice",
        "response_format": "structured-output",
        "reasoning": "reasoning",
        "image_input": "image-input",
        "audio_input": "audio-input",
    }
    for parameter in supported_parameters if isinstance(supported_parameters, list) else []:
        normalized = str(parameter or "").strip().lower()
        if not normalized:
            continue
        add(parameter_map.get(normalized, normalized.replace("_", "-")))
    return capabilities


def _refresh_model_card_metadata(*, force: bool = False) -> None:
    with get_connection(ENGINE) as conn:
        model_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.model_roles_json,
                models_table.c.huggingface_repo_id,
                models_table.c.model_card_verified_at,
                models_table.c.model_card_url,
                models_table.c.license_id,
                models_table.c.license_name,
                models_table.c.capabilities_json,
                models_table.c.intended_use_short,
                models_table.c.limitations_short,
                models_table.c.training_data_summary,
                models_table.c.training_cutoff,
            ).where(
                models_table.c.active == 1,
                models_table.c.huggingface_repo_id.is_not(None),
            ),
        )

    if not model_rows:
        return

    now = datetime.now(timezone.utc)
    rows_by_repo: dict[str, list[dict[str, Any]]] = {}
    for row in model_rows:
        repo_id = _clean_text(row.get("huggingface_repo_id"))
        if not repo_id:
            continue
        rows_by_repo.setdefault(repo_id, []).append(row)

    verified_at = utc_now_iso()
    with httpx.Client(headers=HTTP_HEADERS, follow_redirects=True, timeout=30.0) as client:
        for repo_id, rows in rows_by_repo.items():
            if not force and not any(_needs_model_card_refresh(row, now=now) for row in rows):
                continue
            try:
                values = _fetch_huggingface_model_card_values(client, repo_id, verified_at=verified_at)
            except Exception:
                continue
            if not values:
                continue
            with ENGINE.begin() as conn:
                for row in rows:
                    merged_values = dict(values)
                    existing_capabilities = _decode_json_string_list(row.get("capabilities_json"))
                    merged_capabilities = _decode_json_string_list(merged_values.get("capabilities_json"))
                    if existing_capabilities:
                        merged_capabilities = _merge_string_lists(
                            existing_capabilities,
                            merged_capabilities,
                        )
                        if merged_capabilities:
                            merged_values["capabilities_json"] = json.dumps(merged_capabilities, ensure_ascii=True)
                    inferred_roles = _merge_inferred_audio_roles(
                        row.get("model_roles_json"),
                        capabilities=merged_capabilities,
                        names=(row.get("name"), row.get("huggingface_repo_id")),
                    )
                    current_roles = _normalise_model_roles(row.get("model_roles_json"), default=())
                    if inferred_roles != current_roles:
                        merged_values["model_roles_json"] = json.dumps(inferred_roles, ensure_ascii=True)
                    conn.execute(
                        update(models_table)
                        .where(models_table.c.id == row["id"])
                        .values(**merged_values)
                    )


def _needs_model_card_refresh(row: dict[str, Any], *, now: datetime) -> bool:
    verified_at = _parse_iso_datetime(row.get("model_card_verified_at"))
    if verified_at is None:
        return True
    if verified_at <= now - timedelta(days=MODEL_CARD_REFRESH_STALE_DAYS):
        return True
    if not _clean_text(row.get("model_card_url")):
        return True
    if not (_clean_text(row.get("license_id")) or _clean_text(row.get("license_name"))):
        return True
    if not _decode_json_string_list(row.get("capabilities_json")):
        return True
    if not _clean_text(row.get("intended_use_short")) and not _clean_text(row.get("limitations_short")):
        return True
    return False


def _fetch_huggingface_model_card_values(
    client: httpx.Client,
    repo_id: str,
    *,
    verified_at: str,
) -> dict[str, Any]:
    info = _fetch_huggingface_model_info(client, repo_id)
    siblings = info.get("siblings") if isinstance(info.get("siblings"), list) else []
    readme_text = ""
    if any(str(sibling.get("rfilename") or "").strip().lower() == "readme.md" for sibling in siblings if isinstance(sibling, dict)):
        try:
            readme_text = _fetch_huggingface_readme(client, repo_id)
        except Exception:
            # Keep partial model-card metadata from the structured API even if raw README access is blocked.
            readme_text = ""
    return _build_huggingface_model_card_values(
        info,
        readme_text,
        repo_id=repo_id,
        verified_at=verified_at,
    )


def _fetch_huggingface_model_info(client: httpx.Client, repo_id: str) -> dict[str, Any]:
    response = client.get(
        HUGGINGFACE_MODEL_API_URL_TEMPLATE.format(repo_id=repo_id),
        params={"full": "true", "cardData": "true"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Hugging Face API returned invalid payload for {repo_id}")
    return payload


def _fetch_huggingface_readme(client: httpx.Client, repo_id: str) -> str:
    response = client.get(HUGGINGFACE_RAW_README_URL_TEMPLATE.format(repo_id=repo_id))
    response.raise_for_status()
    return response.text


def _build_huggingface_model_card_values(
    info: dict[str, Any],
    readme_text: str,
    *,
    repo_id: str,
    verified_at: str,
) -> dict[str, Any]:
    return model_card_refresh.build_huggingface_model_card_values(
        info,
        readme_text,
        repo_id=repo_id,
        verified_at=verified_at,
    )


def _refresh_model_license_metadata() -> dict[str, int]:
    inferred_summary = apply_inferred_model_licenses(ENGINE)
    baseline_summary = apply_model_license_baseline(ENGINE)
    return {
        **inferred_summary,
        **{f"baseline_{key}": value for key, value in baseline_summary.items()},
        "total_updates": int(inferred_summary.get("total_updates", 0)) + int(baseline_summary.get("total_updates", 0)),
    }


def _merge_string_lists(*lists: list[str] | None) -> list[str]:
    return model_card_refresh.merge_string_lists(*lists)


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _import_openrouter_provisional_models(
    conn: Any,
    *,
    unmatched_items: list[dict[str, Any]],
    existing_canonical_model_ids: set[str],
    verified_at: str,
    allow_existing_canonical_model_ids: bool = False,
) -> None:
    reserved_ids = {
        str(row[0])
        for row in conn.execute(select(models_table.c.id)).fetchall()
    }

    for item in unmatched_items:
        model_id = str(item.get("id") or "").strip()
        canonical_slug = str(item.get("canonical_slug") or "").strip()
        provider = _openrouter_provider_name(item)
        display_name = _suggest_display_name(_openrouter_display_name(item)) or _openrouter_display_name(item) or model_id
        if _gpt56_identity_and_configuration(display_name) is not None:
            # GPT-5.6 effort and product modes belong to the stable base model,
            # not the active review catalog as provisional model identities.
            continue
        identity = infer_model_identity(display_name, provider, canonical_slug or model_id or None)
        if not allow_existing_canonical_model_ids and identity.canonical_model_id in existing_canonical_model_ids:
            continue

        provider_id = _ensure_provider_row(provider, conn=conn)
        provisional_model_id = _choose_model_id(display_name, canonical_slug or model_id or None, reserved_ids=reserved_ids)
        reserved_ids.add(provisional_model_id)
        existing_canonical_model_ids.add(identity.canonical_model_id)

        values = {
            "id": provisional_model_id,
            "name": display_name,
            "provider_id": provider_id,
            "provider": provider,
            "type": _infer_openrouter_model_type(item),
            "catalog_status": CATALOG_STATUS_PROVISIONAL,
            "release_date": None,
            "release_date_precision": None,
            "release_date_confidence": None,
            "release_date_source_name": None,
            "release_date_source_url": None,
            "release_date_verified_at": None,
            "context_window": None,
            "family_id": identity.family_id,
            "family_name": identity.family_name,
            "canonical_model_id": identity.canonical_model_id,
            "canonical_model_name": identity.canonical_model_name,
            "variant_label": identity.variant_label,
            "discovered_at": verified_at,
            "discovered_update_log_id": None,
            "active": 1,
        }
        values.update(_openrouter_model_values(item, verified_at=verified_at))
        conn.execute(sqlite_insert(models_table).values(**values).on_conflict_do_nothing(index_elements=["id"]))


def _infer_openrouter_model_type(item: dict[str, Any]) -> str:
    hugging_face_id = str(item.get("hugging_face_id") or "").strip()
    if hugging_face_id:
        return "open_weights"
    return "proprietary"


def _openrouter_created_at(value: Any) -> str | None:
    try:
        if value in (None, ""):
            return None
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pricing_per_mtok(value: Any) -> float | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return numeric * 1_000_000.0


def _format_context_window_tokens(value: int) -> str:
    if value >= 1_000_000:
        scaled = value / 1_000_000.0
        suffix = "M"
    elif value >= 1_000:
        scaled = value / 1_000.0
        suffix = "K"
    else:
        return f"{value:,} tokens"

    if abs(scaled - round(scaled)) < 0.05:
        text_value = str(int(round(scaled)))
    else:
        text_value = f"{scaled:.1f}".rstrip("0").rstrip(".")
    return f"{text_value}{suffix} tokens"


def _preferred_model_signature(model_row: dict[str, Any]) -> str | None:
    values = []
    name = str(model_row.get("name") or "").strip()
    model_id = str(model_row.get("id") or "").strip()
    if name:
        values.append(name)
    if model_id:
        values.append(model_id)

    signatures = [
        signature
        for value in values
        for signature in name_signatures(value)
        if signature
    ]
    if not signatures:
        return None
    return sorted(set(signatures), key=lambda item: (len(item.split()), len(item), item))[0]


def _is_openrouter_exact_identity_row(model_row: dict[str, Any]) -> bool:
    if str(model_row.get("catalog_status") or "") != CATALOG_STATUS_PROVISIONAL:
        return False
    return bool(
        str(model_row.get("openrouter_model_id") or "").strip()
        or str(model_row.get("openrouter_canonical_slug") or "").strip()
    )


def _has_provider_conflict(group: list[dict[str, Any]]) -> bool:
    providers = {
        str(row.get("provider") or "").strip().lower()
        for row in group
        if str(row.get("provider") or "").strip()
        and str(row.get("provider") or "").strip().lower() != "unknown"
    }
    return len(providers) > 1


def _choose_canonical_model(group: list[dict[str, Any]], score_counts: dict[str, int]) -> dict[str, Any]:
    def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        name = str(row.get("name") or row.get("id") or "")
        metadata_fields = (
            int(bool(row.get("release_date")))
            + int(bool(row.get("context_window")))
            + int(bool(row.get("parameter_count_b") or row.get("active_parameter_count_b")))
            + int(bool(row.get("license_id") or row.get("license_name")))
            + int(bool(row.get("model_card_url")))
            + int(bool(_decode_json_string_list(row.get("capabilities_json"))))
        )
        known_provider = int(
            bool(str(row.get("provider") or "").strip())
            and str(row.get("provider") or "").strip().lower() != "unknown"
        )
        readable_name = _readable_name_score(name)
        score_count = int(score_counts.get(str(row["id"]), 0))
        return (
            -metadata_fields,
            -known_provider,
            -readable_name,
            -score_count,
            len(name),
            str(row["id"]),
        )

    return sorted(group, key=sort_key)[0]


def _readable_name_score(name: str) -> int:
    has_space = int(" " in name)
    mixed_case = int(any(ch.isupper() for ch in name) and any(ch.islower() for ch in name))
    slug_like = int("-" in name and name == name.lower())
    return (has_space * 2) + (mixed_case * 2) + (0 if slug_like else 1)


def _canonical_model_enrichment(group: list[dict[str, Any]], canonical: dict[str, Any]) -> dict[str, Any]:
    preferred_name = max(group, key=lambda row: _readable_name_score(str(row.get("name") or row.get("id") or "")))
    payload: dict[str, Any] = {}

    canonical_name = str(canonical.get("name") or canonical.get("id") or "")
    preferred_name_value = str(preferred_name.get("name") or preferred_name.get("id") or "")
    if _readable_name_score(preferred_name_value) > _readable_name_score(canonical_name):
        payload["name"] = preferred_name_value

    canonical_provider = str(canonical.get("provider") or "").strip().lower()
    if not canonical_provider or canonical_provider == "unknown":
        for row in group:
            provider = str(row.get("provider") or "").strip()
            if provider and provider.lower() != "unknown":
                payload["provider"] = provider
                break

    if not canonical.get("release_date"):
        for row in group:
            if row.get("release_date"):
                payload["release_date"] = row["release_date"]
                break

    for release_field in (
        "release_date_precision",
        "release_date_confidence",
        "release_date_source_name",
        "release_date_source_url",
        "release_date_verified_at",
    ):
        if canonical.get(release_field):
            continue
        for row in group:
            if row.get(release_field):
                payload[release_field] = row[release_field]
                break

    if not canonical.get("context_window"):
        for row in group:
            if row.get("context_window"):
                payload["context_window"] = row["context_window"]
                break

    merge_fields = (
        "context_window_tokens",
        "max_output_tokens",
        "parameter_count_b",
        "active_parameter_count_b",
        "model_size_class",
        "model_size_source_name",
        "model_size_source_url",
        "model_size_verified_at",
        "price_input_per_mtok",
        "price_output_per_mtok",
        "openrouter_model_id",
        "openrouter_canonical_slug",
        "openrouter_added_at",
        "huggingface_repo_id",
        "huggingface_created_at",
        "huggingface_last_modified_at",
        "metadata_source_name",
        "metadata_source_url",
        "metadata_verified_at",
        "model_card_url",
        "model_card_source",
        "model_card_verified_at",
        "documentation_url",
        "repo_url",
        "paper_url",
        "license_id",
        "license_name",
        "license_url",
        "base_models_json",
        "supported_languages_json",
        "capabilities_json",
        "intended_use_short",
        "limitations_short",
        "training_data_summary",
        "training_cutoff",
    )
    for field_name in merge_fields:
        canonical_value = canonical.get(field_name)
        if canonical_value not in (None, "", "[]"):
            continue
        for row in group:
            row_value = row.get(field_name)
            if row_value not in (None, "", "[]"):
                payload[field_name] = row_value
                break

    if not bool(canonical.get("small_model_candidate")) and any(bool(row.get("small_model_candidate")) for row in group):
        payload["small_model_candidate"] = 1

    merged_roles = sorted(
        dict.fromkeys(
            role
            for row in group
            for role in _normalise_model_roles(row.get("model_roles_json"), default=())
        )
    )
    if merged_roles:
        payload["model_roles_json"] = json.dumps(merged_roles, ensure_ascii=True)

    suggested_name = _suggest_display_name(preferred_name_value)
    candidate_name = payload.get("name", canonical_name)
    if suggested_name and _readable_name_score(suggested_name) > _readable_name_score(candidate_name):
        payload["name"] = suggested_name

    return payload


def _suggest_display_name(raw_name: str) -> str | None:
    candidate = raw_name.strip()
    if not candidate:
        return None

    candidate = _DISPLAY_PROVIDER_PREFIX_RE.sub("", candidate, count=1)
    while True:
        updated = _DISPLAY_TRAILING_THINKING_RE.sub("", candidate).strip("-_ ")
        updated = _DISPLAY_TRAILING_NON_REASONING_RE.sub("", updated).strip("-_ ")
        updated = _DISPLAY_TRAILING_ISO_DATE_RE.sub("", updated).strip("-_ ")
        updated = _DISPLAY_TRAILING_COMPACT_DATE_RE.sub("", updated).strip("-_ ")
        if updated == candidate:
            break
        candidate = updated

    candidate = re.sub(r"[-_]+", " ", candidate).strip()
    if not candidate:
        return None

    raw_tokens = candidate.split()
    tokens: list[str] = []
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        next_token = raw_tokens[index + 1] if index + 1 < len(raw_tokens) else None
        if next_token and re.fullmatch(r"\d", token) and re.fullmatch(r"\d", next_token):
            tokens.append(f"{token}.{next_token}")
            index += 2
            continue
        tokens.append(token)
        index += 1

    humanized = " ".join(_humanize_display_token(token) for token in tokens).strip()
    return humanized or None


def _humanize_display_token(token: str) -> str:
    lowered = token.lower()
    if lowered in _DISPLAY_TOKEN_MAP:
        return _DISPLAY_TOKEN_MAP[lowered]
    if token.isalpha():
        return token.capitalize()
    return token


def _resolve_model_id(raw_model_name: str) -> str | None:
    gpt56 = _gpt56_identity_and_configuration(raw_model_name)
    if gpt56 is not None:
        with get_connection(ENGINE) as conn:
            existing = fetch_one(
                conn,
                select(models_table.c.id).where(models_table.c.id == gpt56[0], models_table.c.active == 1),
            )
        return gpt56[0] if existing is not None else None
    with get_connection(ENGINE) as conn:
        model_rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.name,
                models_table.c.provider,
                models_table.c.type,
                models_table.c.family_name,
                models_table.c.canonical_model_name,
                models_table.c.variant_label,
            ).where(models_table.c.active == 1)
        )
    return resolve_model_name(raw_model_name, model_rows)


_GPT56_NAME_RE = re.compile(r"gpt\s*[-.]?\s*5[.-]6\s+(sol|terra|luna)\b", re.IGNORECASE)
_GPT56_EFFORT_RE = re.compile(r"\b(none|low|medium|high|xhigh|max)\b", re.IGNORECASE)
_GPT56_BASE_MODELS = {
    "gpt-5-6-sol": ("GPT-5.6 Sol", 5.0, 30.0),
    "gpt-5-6-terra": ("GPT-5.6 Terra", 2.5, 15.0),
    "gpt-5-6-luna": ("GPT-5.6 Luna", 1.0, 6.0),
}


def _gpt56_identity_and_configuration(raw_name: str) -> tuple[str, str | None, str | None] | None:
    """Map GPT-5.6 evaluation labels to their provider model and request configuration."""
    text = str(raw_name or "")
    tier_match = _GPT56_NAME_RE.search(text)
    if tier_match is None:
        return None
    model_id = f"gpt-5-6-{tier_match.group(1).lower()}"
    lowered = text.lower()
    if re.search(r"\bnon[- ]reasoning\b", lowered):
        return model_id, "reasoning_effort", "none"
    effort_match = _GPT56_EFFORT_RE.search(lowered)
    if effort_match is not None:
        return model_id, "reasoning_effort", effort_match.group(1).lower()
    if re.search(r"\bpro\b", lowered):
        return model_id, "product_mode", "pro"
    if re.search(r"\bultra\b", lowered):
        return model_id, "product_mode", "ultra"
    return model_id, None, None


def _ensure_gpt56_base_model(model_id: str) -> str:
    """Create a stable GPT-5.6 base identity if benchmark evidence arrives first."""
    name, input_price, output_price = _GPT56_BASE_MODELS[model_id]
    tier = model_id.rsplit("-", 1)[-1]
    with ENGINE.begin() as conn:
        provider_id = _ensure_provider_row("OpenAI", conn=conn)
        stmt = sqlite_insert(models_table).values(
            id=model_id,
            name=name,
            provider_id=provider_id,
            provider="OpenAI",
            type="proprietary",
            model_roles_json=json.dumps([MODEL_ROLE_GENERATOR]),
            catalog_status=CATALOG_STATUS_TRACKED,
            release_date="2026-07-09",
            price_input_per_mtok=input_price,
            price_output_per_mtok=output_price,
            metadata_source_name=CATALOG_MODEL_DISCOVERY_SOURCE_NAME,
            metadata_source_url="https://openai.com/index/gpt-5-6/",
            family_id="openai::gpt-5-6",
            family_name="GPT-5.6",
            canonical_model_id=f"openai::gpt-5-6-{tier}",
            canonical_model_name=name,
            discovered_at=utc_now_iso(),
            active=1,
        ).on_conflict_do_nothing(index_elements=["id"])
        conn.execute(stmt)
    return model_id


def _load_latest_scores() -> dict[tuple[str, str], dict[str, Any]]:
    with get_connection(ENGINE) as conn:
        rows = [dict(row._mapping) for row in conn.exec_driver_sql("SELECT * FROM latest_scores").fetchall()]
    payload: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["model_id"], row["benchmark_id"])
        if key in payload:
            raise ValueError(f"Duplicate latest score rows detected for model={key[0]} benchmark={key[1]}")
        payload[key] = row
    return payload


def _load_latest_score_configurations() -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Return the newest observation for each explicit evaluation configuration."""
    with get_connection(ENGINE) as conn:
        rows = [dict(row._mapping) for row in conn.exec_driver_sql(
            """
            SELECT * FROM (
                SELECT s.*, ROW_NUMBER() OVER (
                    PARTITION BY model_id, benchmark_id, configuration_key, configuration_value
                    ORDER BY collected_at DESC, id DESC
                ) AS row_num
                FROM scores s
                WHERE configuration_key IS NOT NULL AND configuration_value IS NOT NULL
            ) WHERE row_num = 1
            ORDER BY model_id, benchmark_id, configuration_key, configuration_value
            """
        ).fetchall()]
    return {
        (str(row["model_id"]), str(row["benchmark_id"]), str(row["configuration_key"]), str(row["configuration_value"])): row
        for row in rows
    }


def _serialize_benchmark(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["higher_is_better"] = bool(payload.get("higher_is_better", 1))
    payload["active"] = bool(payload.get("active", 1))
    payload.setdefault("range_min", None)
    payload.setdefault("range_max", None)
    payload.setdefault("data_points", 0)
    payload.setdefault("latest_updated_at", None)
    return payload


def _serialize_provider(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    origin_countries = _load_origin_countries(
        payload.get("origin_countries_json"),
        payload.get("country_code"),
        payload.get("country_name"),
    )
    country_code, country_name = derive_provider_origin_fields(origin_countries)
    payload["country_code"] = country_code
    payload["country_name"] = country_name
    payload["origin_countries"] = origin_countries
    payload.pop("origin_countries_json", None)
    payload["active"] = bool(payload.get("active", 1))
    return payload


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _clean_release_date(value: Any) -> str | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    precision = _release_date_precision(text_value)
    return text_value if precision is not None else None


def _release_date_precision(value: Any) -> str | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text_value):
        return "day"
    if re.fullmatch(r"\d{4}-\d{2}", text_value):
        return "month"
    if re.fullmatch(r"\d{4}-Q[1-4]", text_value, flags=re.IGNORECASE):
        return "quarter"
    if re.fullmatch(r"\d{4}", text_value):
        return "year"
    return None


def _release_precision_rank(value: Any) -> int:
    return {
        "year": 1,
        "quarter": 2,
        "month": 3,
        "day": 4,
    }.get(str(value or "").strip().lower(), 0)


def _release_confidence_rank(value: Any) -> int:
    text_value = str(value or "").strip().lower()
    if text_value == "high":
        return 3
    if text_value == "low":
        return 1
    return 2


def _model_age_payload(model: dict[str, Any], *, reference_date: date | None = None) -> dict[str, Any]:
    today = reference_date or datetime.now(timezone.utc).date()
    candidates = [
        {
            "date": _clean_text(model.get("release_date")),
            "basis": "release_date",
            "confidence": _clean_text(model.get("release_date_confidence")) or "medium",
            "source_name": _clean_text(model.get("release_date_source_name")),
            "source_url": _clean_text(model.get("release_date_source_url")),
        },
        {
            "date": _clean_text(model.get("huggingface_created_at")),
            "basis": "huggingface_created_at",
            "confidence": "low",
            "source_name": "huggingface",
            "source_url": f"https://huggingface.co/{model.get('huggingface_repo_id')}"
            if _clean_text(model.get("huggingface_repo_id"))
            else None,
        },
        {
            "date": _clean_text(model.get("openrouter_added_at")),
            "basis": "openrouter_added_at",
            "confidence": "low",
            "source_name": "openrouter",
            "source_url": OPENROUTER_MODELS_URL,
        },
        {
            "date": _clean_text(model.get("discovered_at")),
            "basis": "discovered_at",
            "confidence": "low",
            "source_name": _clean_text(model.get("metadata_source_name")),
            "source_url": _clean_text(model.get("metadata_source_url")),
        },
    ]

    for candidate in candidates:
        parsed_date = _age_basis_date(candidate["date"], basis=str(candidate["basis"]))
        if parsed_date is None:
            continue
        return {
            "model_age_days": max((today - parsed_date).days, 0),
            "model_age_basis": candidate["basis"],
            "model_age_confidence": candidate["confidence"],
            "model_age_source_name": candidate["source_name"],
            "model_age_source_url": candidate["source_url"],
            "model_age_reference_date": today.isoformat(),
        }

    return {
        "model_age_days": None,
        "model_age_basis": None,
        "model_age_confidence": None,
        "model_age_source_name": None,
        "model_age_source_url": None,
        "model_age_reference_date": today.isoformat(),
    }


def _age_basis_date(value: Any, *, basis: str) -> date | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    if basis == "release_date" and _release_date_precision(text_value) != "day":
        return None
    candidate = text_value[:10]
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def _resolve_provider_metadata(
    row: dict[str, Any],
    providers_by_id: dict[str, dict[str, Any]],
    providers_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    provider_id = str(row.get("provider_id") or "").strip()
    if provider_id:
        provider_metadata = providers_by_id.get(provider_id)
        if provider_metadata is not None:
            return provider_metadata

    provider_name = str(row.get("provider") or "").strip()
    if provider_name:
        return providers_by_name.get(normalize_text(provider_name))

    return None


def _country_flag_emoji(country_code: str | None) -> str | None:
    if not isinstance(country_code, str):
        return None

    normalized = country_code.strip().upper()
    if len(normalized) != 2 or not normalized.isalpha():
        return None

    return "".join(chr(127397 + ord(char)) for char in normalized)


def _serialize_model(
    row: dict[str, Any],
    provider_metadata: dict[str, Any] | None = None,
    use_case_approvals: dict[str, dict[str, Any]] | None = None,
    recommendation_proposals: dict[str, dict[str, Any]] | None = None,
    inference_route_approvals: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    payload = dict(row)
    payload["active"] = bool(payload.get("active", 1))
    provider_name = str(payload.get("provider") or "").strip()
    provider_id = payload.get("provider_id")

    if provider_metadata is not None:
        provider_name = str(provider_metadata.get("name") or provider_name)
        provider_id = provider_metadata.get("id") or provider_id

    payload["provider"] = provider_name
    payload["provider_id"] = provider_id or (
        provider_id_from_name(provider_name) if provider_name and provider_name != "Unknown" else None
    )
    payload["catalog_status"] = str(payload.get("catalog_status") or CATALOG_STATUS_TRACKED)
    payload["model_roles"] = _normalise_model_roles(payload.pop("model_roles_json", None))
    payload["provider_origin_countries"] = provider_metadata.get("origin_countries", []) if provider_metadata is not None else []
    payload["provider_country_code"] = provider_metadata.get("country_code") if provider_metadata is not None else None
    payload["provider_country_name"] = provider_metadata.get("country_name") if provider_metadata is not None else None
    payload["provider_country_flag"] = _country_flag_emoji(payload["provider_country_code"])
    payload["provider_origin_basis"] = provider_metadata.get("origin_basis") if provider_metadata is not None else None
    payload["provider_origin_source_url"] = provider_metadata.get("source_url") if provider_metadata is not None else None
    payload["provider_origin_verified_at"] = provider_metadata.get("verified_at") if provider_metadata is not None else None
    payload["release_date"] = _clean_text(payload.get("release_date"))
    payload["release_date_precision"] = _clean_text(payload.get("release_date_precision")) or _release_date_precision(payload.get("release_date"))
    payload["release_date_confidence"] = _clean_text(payload.get("release_date_confidence")) or (
        "medium" if payload.get("release_date") else None
    )
    payload["release_date_source_name"] = _clean_text(payload.get("release_date_source_name"))
    payload["release_date_source_url"] = _clean_text(payload.get("release_date_source_url"))
    payload["small_model_candidate"] = bool(payload.get("small_model_candidate", 0))
    payload["model_size_class"] = _clean_text(payload.get("model_size_class"))
    payload["model_size_source_name"] = _clean_text(payload.get("model_size_source_name"))
    payload["model_size_source_url"] = _clean_text(payload.get("model_size_source_url"))
    payload["huggingface_repo_id"] = _clean_text(payload.get("huggingface_repo_id"))
    payload["huggingface_created_at"] = _clean_text(payload.get("huggingface_created_at"))
    payload["huggingface_last_modified_at"] = _clean_text(payload.get("huggingface_last_modified_at"))
    payload["base_models"] = _decode_json_string_list(payload.pop("base_models_json", None))
    payload["supported_languages"] = _decode_json_string_list(payload.pop("supported_languages_json", None))
    payload["capabilities"] = _decode_json_string_list(payload.pop("capabilities_json", None))
    payload["license_id"] = _clean_text(payload.get("license_id"))
    payload["license_name"] = _clean_text(payload.get("license_name"))
    payload["license_url"] = _clean_text(payload.get("license_url"))
    payload.update(build_license_policy_payload(payload["license_id"], payload["license_name"]))
    payload["model_card_url"] = _clean_text(payload.get("model_card_url"))
    payload["model_card_source"] = _clean_text(payload.get("model_card_source"))
    payload["documentation_url"] = _clean_text(payload.get("documentation_url"))
    payload["repo_url"] = _clean_text(payload.get("repo_url"))
    payload["paper_url"] = _clean_text(payload.get("paper_url"))
    payload["intended_use_short"] = _clean_text(payload.get("intended_use_short"))
    payload["limitations_short"] = _clean_text(payload.get("limitations_short"))
    payload["training_data_summary"] = _clean_text(payload.get("training_data_summary"))
    payload["training_cutoff"] = _clean_text(payload.get("training_cutoff"))
    payload.update(
        build_provenance_policy_payload(
            base_models=payload["base_models"],
            provider=payload.get("provider"),
            model_card_url=payload.get("model_card_url"),
            training_data_summary=payload.get("training_data_summary"),
        )
    )
    payload["discovered_at"] = payload.get("discovered_at")
    payload["discovered_update_log_id"] = payload.get("discovered_update_log_id")
    payload["general_approved_for_use"] = bool(payload.get("general_approved_for_use", 0))
    payload["general_approval_notes"] = _clean_text(payload.get("general_approval_notes"))
    payload["general_approval_updated_at"] = payload.get("general_approval_updated_at")
    payload["general_recommendation_status"] = _normalize_recommendation_status(
        payload.get("general_recommendation_status")
    )
    payload["general_recommendation_notes"] = _clean_text(payload.get("general_recommendation_notes"))
    payload["general_recommendation_updated_at"] = payload.get("general_recommendation_updated_at")
    payload["reasoning_effort_ceiling"] = _clean_text(payload.get("reasoning_effort_ceiling"))
    payload["restricted_modes"] = _decode_json_string_list(payload.pop("restricted_modes_json", None))
    payload["usage_policy_notes"] = _clean_text(payload.get("usage_policy_notes"))
    payload["usage_policy_updated_at"] = payload.get("usage_policy_updated_at")
    payload["suggested_use_cases"] = _build_suggested_use_cases(recommendation_proposals)
    payload.update(_model_age_payload(payload))
    payload["use_case_approvals"] = {
        use_case_id: dict(approval)
        for use_case_id, approval in (use_case_approvals or {}).items()
    }
    for use_case_id, route_entries in (inference_route_approvals or {}).items():
        payload["use_case_approvals"].setdefault(
            use_case_id,
            _default_use_case_approval_payload(use_case_id),
        )["inference_route_approvals"] = [dict(entry) for entry in route_entries]
    _attach_license_policy_use_case_overlays(payload)
    _attach_provenance_policy_use_case_overlays(payload)
    _attach_recommendation_proposals(payload, recommendation_proposals)
    approval_summary = _approval_summary_from_use_case_approvals(payload["use_case_approvals"])
    payload["approved_for_use"] = bool(approval_summary["approved_for_use"] or payload.get("approved_for_use", 0))
    payload["approval_use_case_count"] = int(approval_summary["approval_use_case_count"] or 0)
    payload["approval_notes"] = approval_summary["approval_notes"] or _clean_text(payload.get("approval_notes"))
    payload["approval_updated_at"] = approval_summary["approval_updated_at"] or payload.get("approval_updated_at")
    return payload


def _attach_inference_route_destination_metadata(model: dict[str, Any]) -> None:
    destination_lookup = {
        str(destination.get("id") or ""): destination
        for destination in (model.get("inference_destinations") or [])
        if str(destination.get("id") or "").strip()
    }
    for approval in (model.get("use_case_approvals") or {}).values():
        route_entries = approval.get("inference_route_approvals") or []
        if not route_entries:
            continue
        enriched_entries: list[dict[str, Any]] = []
        for entry in route_entries:
            destination = destination_lookup.get(str(entry.get("destination_id") or ""))
            enriched_entries.append(
                {
                    **entry,
                    "destination_name": entry.get("destination_name") or (destination.get("name") if destination is not None else None),
                    "hyperscaler": entry.get("hyperscaler") or (destination.get("hyperscaler") if destination is not None else None),
                }
            )
        approval["inference_route_approvals"] = sorted(
            enriched_entries,
            key=lambda item: (
                str(item.get("destination_name") or ""),
                str(item.get("location_label") or ""),
            ),
        )


def _serialize_score(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": row["value"],
        "raw_value": row.get("raw_value"),
        "collected_at": row["collected_at"],
        "source_url": row.get("source_url"),
        "source_type": row.get("source_type", "primary"),
        "verified": bool(row.get("verified", 0)),
        "notes": row.get("notes"),
        "confidence_lower": row.get("confidence_lower"),
        "confidence_upper": row.get("confidence_upper"),
        "variance": row.get("variance"),
        "vote_count": row.get("vote_count"),
        "observation_count": row.get("observation_count"),
        "session_count": row.get("session_count"),
        "rank": row.get("rank"),
        "category": row.get("category"),
        "publication_date": row.get("publication_date"),
        "methodology": row.get("methodology"),
        "source_listing_status": row.get("source_listing_status"),
        "style_control": None if row.get("style_control") is None else bool(row.get("style_control")),
        "preliminary": None if row.get("preliminary") is None else bool(row.get("preliminary")),
        "source_metadata": _decode_json_object(row.get("source_metadata_json")),
        "variant_model_id": row.get("variant_model_id"),
        "variant_model_name": row.get("variant_model_name"),
        "configuration_key": row.get("configuration_key"),
        "configuration_value": row.get("configuration_value"),
    }


def _decode_update_steps(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(step) for step in value if isinstance(step, dict)]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [dict(step) for step in parsed if isinstance(step, dict)]
    return []


def _build_update_progress_steps(
    payload: dict[str, Any],
    source_runs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, float]:
    step_plan = _decode_update_steps(payload.get("steps_json"))
    current_step_key = str(payload.get("current_step_key") or "")
    current_step_index = int(payload.get("current_step_index") or 0)
    status = str(payload.get("status") or "running")
    source_runs_by_name = {str(source_run.get("source_name") or ""): source_run for source_run in source_runs}
    progress_steps: list[dict[str, Any]] = []

    for index, base_step in enumerate(step_plan, start=1):
        step = {
            "key": str(base_step.get("key") or ""),
            "label": str(base_step.get("label") or base_step.get("key") or f"Step {index}"),
            "kind": str(base_step.get("kind") or "phase"),
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "detail": None,
            "records_found": None,
            "error_message": None,
        }

        if step["kind"] == "source":
            source_run = source_runs_by_name.get(str(base_step.get("source_name") or ""))
            if source_run is not None:
                step["status"] = str(source_run.get("status") or "pending")
                step["started_at"] = source_run.get("started_at")
                step["completed_at"] = source_run.get("completed_at")
                step["detail"] = source_run.get("benchmark_id")
                step["records_found"] = source_run.get("records_found")
                step["error_message"] = source_run.get("error_message")
                progress_steps.append(step)
                continue

        if status == "completed":
            step["status"] = "completed"
        elif status == "failed":
            if current_step_index and index < current_step_index:
                step["status"] = "completed"
            elif step["key"] == current_step_key or (current_step_index and index == current_step_index):
                step["status"] = "failed"
                step["started_at"] = payload.get("current_step_started_at")
            else:
                step["status"] = "pending"
        else:
            if current_step_index and index < current_step_index:
                step["status"] = "completed"
            elif step["key"] == current_step_key or (current_step_index and index == current_step_index):
                step["status"] = "running"
                step["started_at"] = payload.get("current_step_started_at")
            else:
                step["status"] = "pending"

        progress_steps.append(step)

    finished_steps = sum(1 for step in progress_steps if step["status"] in {"completed", "failed"})
    total_steps = len(progress_steps)
    progress_percent = (finished_steps / total_steps) * 100 if total_steps else 0.0
    return progress_steps, finished_steps, progress_percent


def _serialize_update_log(
    row: dict[str, Any],
    source_runs: list[dict[str, Any]] | None = None,
    audit_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(row)
    payload["errors"] = _decode_json_list(payload.get("errors"))
    change_summary = _decode_json_object(payload.get("change_summary_json"))
    payload["change_summary"] = change_summary or None
    payload["source_runs"] = source_runs or []
    payload["total_steps"] = int(payload.get("total_steps") or len(_decode_update_steps(payload.get("steps_json"))))
    payload["current_step_index"] = int(payload.get("current_step_index") or 0)
    progress_steps, finished_steps, progress_percent = _build_update_progress_steps(payload, payload["source_runs"])
    payload["progress_steps"] = progress_steps
    payload["finished_steps"] = finished_steps
    payload["progress_percent"] = progress_percent
    payload["audit_summary"] = audit_summary
    payload.pop("steps_json", None)
    payload.pop("change_summary_json", None)
    return payload


def _audit_errors(audit_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not audit_result:
        return []
    findings = audit_result.get("findings") or []
    return [
        {
            "benchmark_id": "audit",
            "source_id": "audit",
            "error_message": finding.get("message"),
            "check_name": finding.get("check_name"),
            "severity": finding.get("severity"),
        }
        for finding in findings
        if finding.get("severity") == "blocker"
    ]


def _serialize_source_run(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return payload


def _serialize_market_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["category_slug"] = str(payload.get("category_slug") or "")
    payload["model_name"] = str(payload.get("model_name") or payload.get("model_id") or "")
    payload["provider"] = str(payload.get("provider") or "Unknown")
    return payload


def _load_source_runs_by_log_id(log_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not log_ids:
        return {}

    with get_connection(ENGINE) as conn:
        rows = fetch_all(
            conn,
            select(source_runs_table)
            .where(source_runs_table.c.update_log_id.in_(log_ids))
            .order_by(
                source_runs_table.c.update_log_id.desc(),
                source_runs_table.c.started_at.asc(),
                source_runs_table.c.id.asc(),
            ),
        )

    payload: dict[int, list[dict[str, Any]]] = {log_id: [] for log_id in log_ids}
    for row in rows:
        update_log_id = int(row["update_log_id"])
        payload.setdefault(update_log_id, []).append(_serialize_source_run(row))
    return payload


def _get_base_use_case(use_case_id: str) -> dict[str, Any] | None:
    for use_case in USE_CASES:
        if use_case["id"] == use_case_id:
            return use_case
    return None


def _get_use_case(use_case_id: str) -> dict[str, Any] | None:
    use_case = _get_base_use_case(use_case_id)
    if use_case is None:
        return None

    with get_connection(ENGINE) as conn:
        weight_overrides_by_use_case = _load_use_case_weight_overrides(conn)
    return _resolve_use_case_definition(use_case, weight_overrides_by_use_case)


def _benchmark_ranges(
    models: list[dict[str, Any]],
    weights: dict[str, float],
) -> dict[str, tuple[float, float]]:
    return ranking_views.benchmark_ranges(models, weights)


def _benchmark_stats(latest_scores: dict[tuple[str, str], dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in latest_scores.values():
        benchmark_id = row["benchmark_id"]
        numeric_value = float(row["value"])
        current = stats.setdefault(
            benchmark_id,
            {
                "range_min": numeric_value,
                "range_max": numeric_value,
                "data_points": 0,
                "latest_updated_at": row["collected_at"],
            },
        )
        current["range_min"] = min(float(current["range_min"]), numeric_value)
        current["range_max"] = max(float(current["range_max"]), numeric_value)
        current["data_points"] = int(current["data_points"]) + 1
        if str(row["collected_at"]) > str(current["latest_updated_at"]):
            current["latest_updated_at"] = row["collected_at"]
    return stats


def _normalise_score(raw_value: float, minimum: float, maximum: float, higher_is_better: bool) -> float:
    return ranking_views.normalise_score(raw_value, minimum, maximum, higher_is_better)


def _model_summary(model: dict[str, Any]) -> dict[str, Any]:
    license_id = _clean_text(model.get("license_id"))
    license_name = _clean_text(model.get("license_name"))
    summary = {
        "id": model["id"],
        "name": model["name"],
        "provider_id": model.get("provider_id"),
        "provider": model["provider"],
        "provider_country_code": model.get("provider_country_code"),
        "provider_country_name": model.get("provider_country_name"),
        "provider_country_flag": model.get("provider_country_flag"),
        "provider_origin_countries": model.get("provider_origin_countries", []),
        "provider_origin_basis": model.get("provider_origin_basis"),
        "provider_origin_source_url": model.get("provider_origin_source_url"),
        "provider_origin_verified_at": model.get("provider_origin_verified_at"),
        "type": model.get("type", "proprietary"),
        "model_roles": _normalise_model_roles(
            model.get("model_roles_json") if "model_roles_json" in model else model.get("model_roles"),
        ),
        "catalog_status": model.get("catalog_status", CATALOG_STATUS_TRACKED),
        "release_date": _clean_text(model.get("release_date")),
        "release_date_precision": _clean_text(model.get("release_date_precision")) or _release_date_precision(model.get("release_date")),
        "release_date_confidence": _clean_text(model.get("release_date_confidence")) or (
            "medium" if _clean_text(model.get("release_date")) else None
        ),
        "release_date_source_name": _clean_text(model.get("release_date_source_name")),
        "release_date_source_url": _clean_text(model.get("release_date_source_url")),
        "release_date_verified_at": model.get("release_date_verified_at"),
        "context_window": model.get("context_window"),
        "context_window_tokens": model.get("context_window_tokens"),
        "max_output_tokens": model.get("max_output_tokens"),
        "parameter_count_b": model.get("parameter_count_b"),
        "active_parameter_count_b": model.get("active_parameter_count_b"),
        "model_size_class": _clean_text(model.get("model_size_class")),
        "small_model_candidate": bool(model.get("small_model_candidate", False)),
        "model_size_source_name": _clean_text(model.get("model_size_source_name")),
        "model_size_source_url": _clean_text(model.get("model_size_source_url")),
        "model_size_verified_at": model.get("model_size_verified_at"),
        "openrouter_added_at": model.get("openrouter_added_at"),
        "huggingface_repo_id": _clean_text(model.get("huggingface_repo_id")),
        "huggingface_created_at": _clean_text(model.get("huggingface_created_at")),
        "huggingface_last_modified_at": _clean_text(model.get("huggingface_last_modified_at")),
        "model_card_url": model.get("model_card_url"),
        "model_card_source": model.get("model_card_source"),
        "model_card_verified_at": model.get("model_card_verified_at"),
        "documentation_url": model.get("documentation_url"),
        "repo_url": model.get("repo_url"),
        "paper_url": model.get("paper_url"),
        "license_id": license_id,
        "license_name": license_name,
        "license_url": _clean_text(model.get("license_url")),
        "provenance_policy_class": model.get("provenance_policy_class"),
        "provenance_policy_label": model.get("provenance_policy_label"),
        "provenance_policy_note": _clean_text(model.get("provenance_policy_note")),
        "derivative_model": bool(model.get("derivative_model", False)),
        "potential_provenance_review": bool(model.get("potential_provenance_review", False)),
        "production_provenance_blocked": bool(model.get("production_provenance_blocked", False)),
        "provenance_gap_fields": list(model.get("provenance_gap_fields", []) or []),
        "base_models": _decode_json_string_list(model.get("base_models_json"))
        if "base_models_json" in model
        else list(model.get("base_models", []) or []),
        "supported_languages": _decode_json_string_list(model.get("supported_languages_json"))
        if "supported_languages_json" in model
        else list(model.get("supported_languages", []) or []),
        "capabilities": _decode_json_string_list(model.get("capabilities_json"))
        if "capabilities_json" in model
        else list(model.get("capabilities", []) or []),
        "intended_use_short": _clean_text(model.get("intended_use_short")),
        "limitations_short": _clean_text(model.get("limitations_short")),
        "training_data_summary": _clean_text(model.get("training_data_summary")),
        "training_cutoff": _clean_text(model.get("training_cutoff")),
        "openrouter_global_rank": model.get("openrouter_global_rank"),
        "openrouter_global_total_tokens": model.get("openrouter_global_total_tokens"),
        "openrouter_global_share": model.get("openrouter_global_share"),
        "openrouter_programming_rank": model.get("openrouter_programming_rank"),
        "openrouter_programming_total_tokens": model.get("openrouter_programming_total_tokens"),
        "family_id": model.get("family_id"),
        "family_name": model.get("family_name"),
        "canonical_model_id": model.get("canonical_model_id"),
        "canonical_model_name": model.get("canonical_model_name"),
        "variant_label": model.get("variant_label"),
        "discovered_at": model.get("discovered_at"),
        "discovered_update_log_id": model.get("discovered_update_log_id"),
        "approved_for_use": bool(model.get("approved_for_use", False)),
        "approval_use_case_count": int(model.get("approval_use_case_count") or 0),
        "use_case_approvals": model.get("use_case_approvals", {}),
        "approval_notes": model.get("approval_notes"),
        "approval_updated_at": model.get("approval_updated_at"),
        "active": bool(model.get("active", True)),
        "inference_summary": model.get("inference_summary", {}),
        "source_freshness": list(model.get("source_freshness", []) or []),
    }
    summary.update(_model_age_payload(summary))
    summary.update(build_license_policy_payload(license_id, license_name))
    summary.update(
        build_provenance_policy_payload(
            base_models=summary["base_models"],
            provider=summary.get("provider"),
            model_card_url=summary.get("model_card_url"),
            training_data_summary=summary.get("training_data_summary"),
        )
    )
    return summary


def _infer_provider(metadata: dict[str, Any], raw_model_name: str) -> str | None:
    for key in (
        "model_provider",
        "provider",
        "modelOrganization",
        "model_creator",
        "organization_name",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return canonical_provider_name(value.strip())

    name_hint = _provider_hint_from_name(raw_model_name)
    if name_hint:
        return canonical_provider_name(name_hint)

    for key in ("organization", "submission_organization"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return canonical_provider_name(value.strip())
    return None


def _provider_hint_from_name(raw_model_name: str) -> str | None:
    lowered = raw_model_name.strip().lower()
    for prefix, provider in _PROVIDER_PREFIX_HINTS:
        if lowered.startswith(prefix):
            return provider

    for prefix, provider in _PROVIDER_NAME_HINTS:
        if lowered.startswith(prefix):
            return provider
    return None


def _repair_submitter_provider_leaks() -> int:
    repaired_count = 0
    with ENGINE.begin() as conn:
        rows = fetch_all(
            conn,
            select(
                models_table.c.id,
                models_table.c.provider,
                models_table.c.openrouter_canonical_slug,
            ).where(models_table.c.active == 1),
        )
        for row in rows:
            current_provider = str(row.get("provider") or "").strip()
            canonical_slug = str(row.get("openrouter_canonical_slug") or "").strip()
            if not current_provider or not canonical_slug:
                continue

            inferred_provider = _provider_hint_from_name(canonical_slug)
            if not inferred_provider or normalize_text(inferred_provider) == normalize_text(current_provider):
                continue

            source_rows = fetch_all(
                conn,
                select(raw_source_records_table.c.payload_json)
                .select_from(
                    raw_source_records_table.join(
                        source_runs_table,
                        raw_source_records_table.c.source_run_id == source_runs_table.c.id,
                    )
                )
                .where(
                    raw_source_records_table.c.normalized_model_id == str(row["id"]),
                    source_runs_table.c.source_name == "swebench",
                ),
            )
            if not source_rows:
                continue

            if not any(
                _swebench_submission_org_from_payload(source_row.get("payload_json")) == normalize_text(current_provider)
                for source_row in source_rows
            ):
                continue

            provider_id = _ensure_provider_row(inferred_provider, conn=conn)
            conn.execute(
                update(models_table)
                .where(models_table.c.id == row["id"])
                .values(
                    provider=inferred_provider,
                    provider_id=provider_id,
                    type="proprietary" if inferred_provider != "Unknown" else "open_weights",
                )
            )
            repaired_count += 1
    return repaired_count


def _swebench_submission_org_from_payload(payload_json: Any) -> str:
    payload = _decode_json_object(payload_json)
    tags = payload.get("tags") if isinstance(payload, dict) else None
    if not isinstance(tags, list):
        return ""
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("Org: "):
            return normalize_text(tag.split("Org: ", 1)[1].strip())
    return ""


def _decode_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _choose_model_id(
    raw_model_name: str,
    raw_model_key: str | None,
    *,
    reserved_ids: set[str] | None = None,
) -> str:
    raw_name_norm = normalize_text(raw_model_name)
    candidate_ids = [
        candidate_id
        for candidate_id in (
            _slugify_model_id(raw_model_name),
            _slugify_model_id(raw_model_key) if raw_model_key else None,
        )
        if candidate_id
    ]
    candidate_ids = list(dict.fromkeys(candidate_ids))

    with get_connection(ENGINE) as conn:
        existing_rows = fetch_all(
            conn,
            select(models_table.c.id, models_table.c.name).where(models_table.c.id.in_(candidate_ids))
        )
    existing_by_id = {str(row["id"]): str(row["name"]) for row in existing_rows}
    reserved_ids = reserved_ids or set()

    for candidate_id in candidate_ids:
        if candidate_id in reserved_ids:
            continue
        existing_name = existing_by_id.get(candidate_id)
        if existing_name is None:
            return candidate_id
        if normalize_text(existing_name) == raw_name_norm:
            return candidate_id

    base_id = candidate_ids[0] if candidate_ids else "unknown-model"
    suffix = 2
    while True:
        candidate_id = f"{base_id}-{suffix}"
        if candidate_id in reserved_ids:
            suffix += 1
            continue
        with get_connection(ENGINE) as conn:
            existing = fetch_one(
                conn,
                select(models_table.c.name).where(models_table.c.id == candidate_id),
            )
        if existing is None:
            return candidate_id
        if normalize_text(str(existing["name"])) == raw_name_norm:
            return candidate_id
        suffix += 1


def _slugify_model_id(raw_model_name: str) -> str:
    normalized = normalize_text(raw_model_name)
    slug = "-".join(normalized.split())
    return slug or "unknown-model"


def _record_identity(raw_model_name: str, raw_model_key: str | None) -> str:
    return f"{raw_model_key or raw_model_name}|{normalize_text(raw_model_name)}"


def _should_skip_raw_model_resolution(raw_record: RawSourceRecord) -> bool:
    return bool(
        raw_record.metadata.get("aggregate_submission")
        or raw_record.metadata.get("existing_models_only")
    )


def _resolution_status_for_raw_record(
    raw_record: RawSourceRecord,
    *,
    normalized_model_id: str | None,
    skipped_resolution: bool,
) -> str:
    if normalized_model_id:
        return "resolved"
    if skipped_resolution:
        if raw_record.metadata.get("existing_models_only"):
            return "skipped_unmatched_listing"
        return "skipped_aggregate"
    return "unresolved"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


__all__ = [
    "bootstrap",
    "get_update_log",
    "get_rankings",
    "list_benchmarks",
    "list_market_snapshots",
    "list_models",
    "list_raw_source_records",
    "list_source_runs",
    "list_update_logs",
    "list_use_cases",
    "refresh_model_discovery_metadata",
    "run_update_now",
    "run_update_sync",
    "schedule_update",
    "apply_model_family_approval_bulk",
    "apply_model_family_approval_delta",
    "apply_model_inference_route_approval_bulk",
    "curate_model_identity",
    "merge_model_duplicate",
    "update_manual_benchmark_score",
    "update_model_approval",
    "update_model_use_case_inference_approval",
    "update_model_use_case_approval",
    "update_provider_origin",
    "update_use_case_internal_weight",
]
