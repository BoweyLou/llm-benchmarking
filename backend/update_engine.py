"""Update orchestration and API-facing read helpers for Phase 1 ingestion."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Iterable

import httpx
from sqlalchemy import insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .database import (
    benchmarks as benchmarks_table,
    fetch_all,
    fetch_one,
    get_connection,
    get_engine,
    init_db,
    models as models_table,
    raw_source_records as raw_source_records_table,
    scores as scores_table,
    source_runs as source_runs_table,
    update_log as update_log_table,
    utc_now_iso,
)
from .audit_engine import get_audit_run, get_audit_summary, run_audit
from .name_resolution import normalize_text, resolve_model_name
from .seed_data import USE_CASES, seed_reference_data
from .sources import get_source_adapters
from .sources.base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, SourceFetchResult

ENGINE = get_engine()
UPDATE_LOCK = threading.Lock()
BOOTSTRAP_LOCK = threading.Lock()
BOOTSTRAPPED = False
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LLMBenchmarkingBot/0.1; +https://localhost)",
    "Accept": "application/json,text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
}
MIN_RANKING_COVERAGE = 0.5


def bootstrap() -> None:
    global BOOTSTRAPPED
    if BOOTSTRAPPED:
        return

    with BOOTSTRAP_LOCK:
        if BOOTSTRAPPED:
            return
        init_db(ENGINE)
        with ENGINE.begin() as conn:
            seed_reference_data(conn)
        BOOTSTRAPPED = True


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
    return [
        {
            "id": use_case["id"],
            "label": use_case["label"],
            "icon": use_case["icon"],
            "description": use_case["description"],
            "weights": dict(use_case["weights"]),
        }
        for use_case in USE_CASES
    ]


def list_models() -> list[dict[str, Any]]:
    bootstrap()
    benchmarks = list_benchmarks()
    benchmark_ids = [benchmark["id"] for benchmark in benchmarks]
    latest_scores = _load_latest_scores()

    with get_connection(ENGINE) as conn:
        model_rows = fetch_all(
            conn,
            select(models_table)
            .where(models_table.c.active == 1)
            .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
        )

    payload: list[dict[str, Any]] = []
    for row in model_rows:
        model = _serialize_model(row)
        model["scores"] = {
            benchmark_id: _serialize_score(latest_scores[(model["id"], benchmark_id)])
            if (model["id"], benchmark_id) in latest_scores
            else None
            for benchmark_id in benchmark_ids
        }
        payload.append(model)
    return payload


def schedule_update(benchmarks: Iterable[str] | None = None, triggered_by: str = "manual") -> int:
    bootstrap()
    selected_benchmarks = {benchmark_id for benchmark_id in (benchmarks or [])}

    log_id = _create_update_log(triggered_by)

    worker = threading.Thread(
        target=_run_update_job,
        args=(log_id, selected_benchmarks or None, triggered_by),
        daemon=True,
    )
    worker.start()
    return log_id


def run_update_sync(benchmarks: Iterable[str] | None = None, triggered_by: str = "manual") -> int:
    bootstrap()
    selected_benchmarks = {benchmark_id for benchmark_id in (benchmarks or [])}
    log_id = _create_update_log(triggered_by)
    _run_update_job(log_id, selected_benchmarks or None, triggered_by)
    return log_id


def run_update_now(benchmarks: Iterable[str] | None = None, triggered_by: str = "bootstrap") -> dict[str, Any]:
    log_id = run_update_sync(benchmarks=benchmarks, triggered_by=triggered_by)
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


def get_rankings(use_case_id: str) -> dict[str, Any] | None:
    bootstrap()
    use_case = _get_use_case(use_case_id)
    if use_case is None:
        return None

    benchmarks = {row["id"]: row for row in list_benchmarks()}
    models = list_models()
    weights = use_case["weights"]
    ranges = _benchmark_ranges(models, weights)

    rankings: list[dict[str, Any]] = []
    for model in models:
        weighted_sum = 0.0
        total_weight = 0.0
        breakdown: list[dict[str, Any]] = []
        missing_benchmarks: list[str] = []

        for benchmark_id, weight in weights.items():
            score = model["scores"].get(benchmark_id)
            benchmark = benchmarks.get(benchmark_id)
            score_range = ranges.get(benchmark_id)

            if score is None or benchmark is None or score_range is None:
                missing_benchmarks.append(benchmark_id)
                continue

            raw_value = float(score["value"])
            normalised = _normalise_score(
                raw_value,
                score_range[0],
                score_range[1],
                bool(benchmark["higher_is_better"]),
            )
            weighted_sum += normalised * weight
            total_weight += weight
            breakdown.append(
                {
                    "benchmark_id": benchmark_id,
                    "raw_value": raw_value,
                    "normalised": normalised,
                    "weight": weight,
                    "metric": benchmark["metric"],
                }
            )

        if total_weight <= 0:
            continue

        coverage = total_weight / sum(weights.values())
        if coverage < MIN_RANKING_COVERAGE:
            continue

        rankings.append(
            {
                "score": weighted_sum / total_weight,
                "coverage": coverage,
                "model": _model_summary(model),
                "breakdown": breakdown,
                "missing_benchmarks": missing_benchmarks,
            }
        )

    rankings.sort(
        key=lambda item: (
            -float(item["score"]),
            -float(item["coverage"]),
            item["model"]["name"].lower(),
            item["model"]["id"],
        )
    )

    for index, ranking in enumerate(rankings, start=1):
        ranking["rank"] = index

    return {
        "use_case": {
            "id": use_case["id"],
            "label": use_case["label"],
            "icon": use_case["icon"],
            "description": use_case["description"],
            "weights": dict(use_case["weights"]),
        },
        "rankings": rankings,
    }


def _run_update_job(log_id: int, selected_benchmarks: set[str] | None, triggered_by: str) -> None:
    bootstrap()
    adapters = _selected_adapters(selected_benchmarks)
    errors: list[dict[str, Any]] = []
    scores_added = 0
    scores_updated = 0
    audit_result: dict[str, Any] | None = None

    with UPDATE_LOCK:
        for adapter in adapters:
            source_run_id = _start_source_run(log_id, adapter)
            try:
                result = asyncio.run(_collect_adapter(adapter))
                added, updated = _persist_source_result(source_run_id, result)
                scores_added += added
                scores_updated += updated
                _finish_source_run(source_run_id, status="completed", records_found=len(result.raw_records), error_message=None)
            except Exception as exc:
                error = {
                    "benchmark_id": ",".join(adapter.benchmark_ids),
                    "source_id": adapter.source_id,
                    "error_message": str(exc),
                }
                errors.append(error)
                _finish_source_run(source_run_id, status="failed", records_found=0, error_message=str(exc))

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

    with ENGINE.begin() as conn:
        final_status = "completed"
        if errors or (audit_result is not None and audit_result.get("status") == "failed"):
            final_status = "failed"
        conn.execute(
            update(update_log_table)
            .where(update_log_table.c.id == log_id)
            .values(
                completed_at=utc_now_iso(),
                status=final_status,
                scores_added=scores_added,
                scores_updated=scores_updated,
                errors=json.dumps(errors + (_audit_errors(audit_result) if audit_result else [])),
            )
        )


def _create_update_log(triggered_by: str) -> int:
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
            )
        )
        return int(result.inserted_primary_key[0])


async def _collect_adapter(adapter: BaseSourceAdapter) -> SourceFetchResult:
    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True, timeout=30.0) as client:
        return await adapter.collect(client)


def _selected_adapters(selected_benchmarks: set[str] | None) -> list[BaseSourceAdapter]:
    include_phase_two = bool(selected_benchmarks and "terminal_bench" in selected_benchmarks)
    adapters = get_source_adapters(include_phase_two=include_phase_two)
    if not selected_benchmarks:
        return adapters
    return [
        adapter
        for adapter in adapters
        if selected_benchmarks.intersection(adapter.benchmark_ids)
    ]


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


def _persist_source_result(source_run_id: int, result: SourceFetchResult) -> tuple[int, int]:
    scores_added = 0
    scores_updated = 0
    model_ids_by_identity: dict[str, str] = {}
    source_meta_by_identity: dict[str, tuple[str, bool]] = {}

    for candidate in result.candidates:
        model_id, outcome = _persist_score_candidate(candidate)
        identity = _record_identity(candidate.raw_model_name, candidate.raw_model_key)
        model_ids_by_identity[identity] = model_id
        source_meta_by_identity[identity] = (candidate.source_type, candidate.verified)
        if outcome == "added":
            scores_added += 1
        elif outcome == "updated":
            scores_updated += 1

    for raw_record in result.raw_records:
        identity = _record_identity(raw_record.raw_model_name, raw_record.raw_model_key)
        normalized_model_id = model_ids_by_identity.get(identity)
        if normalized_model_id is None and not _should_skip_raw_model_resolution(raw_record):
            normalized_model_id = _ensure_model(
                raw_record.raw_model_name,
                raw_record.metadata,
                raw_record.raw_model_key,
            )
            model_ids_by_identity[identity] = normalized_model_id

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
        )

    return scores_added, scores_updated


def _insert_raw_source_record(
    source_run_id: int,
    raw_record: RawSourceRecord,
    *,
    normalized_model_id: str | None,
    source_type: str,
    verified: bool,
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
                collected_at=raw_record.collected_at,
                notes=_stringify(raw_record.metadata) if raw_record.metadata else None,
            )
        )


def _persist_score_candidate(candidate: ScoreCandidate) -> tuple[str, str]:
    model_id = _ensure_model(candidate.raw_model_name, candidate.metadata, candidate.raw_model_key)

    with ENGINE.begin() as conn:
        latest = fetch_one(
            conn,
            select(scores_table.c.value)
            .where(
                scores_table.c.model_id == model_id,
                scores_table.c.benchmark_id == candidate.benchmark_id,
            )
            .order_by(scores_table.c.collected_at.desc(), scores_table.c.id.desc())
            .limit(1),
        )

        if latest is not None and abs(float(latest["value"]) - candidate.value) <= 0.1:
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
            )
        )

    return model_id, "updated" if latest is not None else "added"


def _ensure_model(raw_model_name: str, metadata: dict[str, Any], raw_model_key: str | None = None) -> str:
    resolved = _resolve_model_id(raw_model_name)
    if resolved:
        return resolved

    model_id = _choose_model_id(raw_model_name, raw_model_key)
    provider = _infer_provider(metadata) or "Unknown"
    stmt = sqlite_insert(models_table).values(
        id=model_id,
        name=raw_model_name,
        provider=provider,
        type="proprietary" if provider != "Unknown" else "open_weights",
        release_date=None,
        context_window=None,
        active=1,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
    with ENGINE.begin() as conn:
        conn.execute(stmt)
    return model_id


def _resolve_model_id(raw_model_name: str) -> str | None:
    with get_connection(ENGINE) as conn:
        model_rows = fetch_all(
            conn,
            select(models_table.c.id, models_table.c.name, models_table.c.provider, models_table.c.type)
            .where(models_table.c.active == 1)
        )
    return resolve_model_name(raw_model_name, model_rows)


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


def _serialize_benchmark(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["higher_is_better"] = bool(payload.get("higher_is_better", 1))
    payload["active"] = bool(payload.get("active", 1))
    payload.setdefault("range_min", None)
    payload.setdefault("range_max", None)
    payload.setdefault("data_points", 0)
    payload.setdefault("latest_updated_at", None)
    return payload


def _serialize_model(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["active"] = bool(payload.get("active", 1))
    return payload


def _serialize_score(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": row["value"],
        "raw_value": row.get("raw_value"),
        "collected_at": row["collected_at"],
        "source_url": row.get("source_url"),
        "source_type": row.get("source_type", "primary"),
        "verified": bool(row.get("verified", 0)),
        "notes": row.get("notes"),
    }


def _serialize_update_log(
    row: dict[str, Any],
    source_runs: list[dict[str, Any]] | None = None,
    audit_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(row)
    errors = payload.get("errors")
    if isinstance(errors, str):
        try:
            payload["errors"] = json.loads(errors)
        except json.JSONDecodeError:
            payload["errors"] = errors
    payload["source_runs"] = source_runs or []
    payload["audit_summary"] = audit_summary
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


def _get_use_case(use_case_id: str) -> dict[str, Any] | None:
    for use_case in USE_CASES:
        if use_case["id"] == use_case_id:
            return use_case
    return None


def _benchmark_ranges(
    models: list[dict[str, Any]],
    weights: dict[str, float],
) -> dict[str, tuple[float, float]]:
    ranges: dict[str, tuple[float, float]] = {}
    for benchmark_id in weights:
        values = [
            float(score["value"])
            for model in models
            for score in [model["scores"].get(benchmark_id)]
            if score is not None and score.get("value") is not None
        ]
        if values:
            ranges[benchmark_id] = (min(values), max(values))
    return ranges


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
    if maximum == minimum:
        return 75.0

    scaled = (raw_value - minimum) / (maximum - minimum) * 100.0
    score = scaled if higher_is_better else 100.0 - scaled
    return max(0.0, min(100.0, score))


def _model_summary(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": model["id"],
        "name": model["name"],
        "provider": model["provider"],
        "type": model.get("type", "proprietary"),
        "release_date": model.get("release_date"),
        "context_window": model.get("context_window"),
        "active": bool(model.get("active", True)),
    }


def _infer_provider(metadata: dict[str, Any]) -> str | None:
    for key in (
        "organization",
        "organization_name",
        "modelOrganization",
        "model_creator",
        "model_provider",
        "provider",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _choose_model_id(raw_model_name: str, raw_model_key: str | None) -> str:
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

    for candidate_id in candidate_ids:
        existing_name = existing_by_id.get(candidate_id)
        if existing_name is None:
            return candidate_id
        if normalize_text(existing_name) == raw_name_norm:
            return candidate_id

    base_id = candidate_ids[0] if candidate_ids else "unknown-model"
    suffix = 2
    while True:
        candidate_id = f"{base_id}-{suffix}"
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
    return bool(raw_record.metadata.get("aggregate_submission"))


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
    "list_models",
    "list_source_runs",
    "list_update_logs",
    "list_use_cases",
    "run_update_now",
    "run_update_sync",
    "schedule_update",
]
