from __future__ import annotations

import json
from typing import Any

from sqlalchemy import insert, select, update

from .database import (
    audit_runs as audit_runs_table,
    audit_findings as audit_findings_table,
    benchmarks as benchmarks_table,
    fetch_all,
    fetch_one,
    get_connection,
    model_use_case_approvals as model_use_case_approvals_table,
    models as models_table,
    raw_source_records as raw_source_records_table,
    scores as scores_table,
    source_runs as source_runs_table,
    update_log as update_log_table,
    utc_now_iso,
)
from .sources import get_source_adapters
from .sources.base import RawSourceRecord

MIN_EXPECTED_RECORDS = {
    "artificial_analysis": 100,
    "ailuminate": 20,
    "chatbot_arena": 200,
    "epoch_ai": 100,
    "faithjudge": 30,
    "ifeval": 50,
    "mmmu": 120,
    "swebench": 10,
    "terminal_bench": 50,
    "vectara_hallucination": 80,
}
DRIFT_MIN_BASELINE_RECORDS = 20
DRIFT_BLOCKER_DROP_THRESHOLD = -0.5
DRIFT_WARNING_DROP_THRESHOLD = -0.2
DRIFT_WARNING_SPIKE_THRESHOLD = 1.0
SPOT_CHECK_SAMPLE_SIZE = 3


def run_audit(engine, update_log_id: int) -> dict[str, Any]:
    started_at = utc_now_iso()

    with engine.begin() as conn:
        result = conn.execute(
            insert(audit_runs_table).values(
                update_log_id=update_log_id,
                started_at=started_at,
                completed_at=None,
                status="passed",
                blocker_count=0,
                warning_count=0,
                info_count=0,
                summary_json=None,
            )
        )
        audit_run_id = int(result.inserted_primary_key[0])

    findings: list[dict[str, Any]] = []

    with get_connection(engine) as conn:
        source_runs = fetch_all(
            conn,
            select(source_runs_table).where(source_runs_table.c.update_log_id == update_log_id),
        )
        source_run_ids = [int(row["id"]) for row in source_runs]

        for source_run in source_runs:
            source_name = str(source_run["source_name"])
            records_found = int(source_run.get("records_found") or 0)
            status = str(source_run.get("status") or "failed")

            if status != "completed":
                findings.append(
                    _finding(
                        audit_run_id,
                        "blocker",
                        "source_run_failed",
                        f"Source run {source_name} did not complete.",
                        {
                            "source_run_id": source_run["id"],
                            "source_name": source_name,
                            "status": status,
                            "error_message": source_run.get("error_message"),
                        },
                    )
                )

            if records_found == 0:
                findings.append(
                    _finding(
                        audit_run_id,
                        "blocker",
                        "zero_row_source",
                        f"Source {source_name} returned zero rows.",
                        {
                            "source_run_id": source_run["id"],
                            "source_name": source_name,
                        },
                    )
                )
            else:
                minimum = MIN_EXPECTED_RECORDS.get(source_name)
                if minimum is not None and records_found < minimum:
                    findings.append(
                        _finding(
                            audit_run_id,
                            "warning",
                            "low_row_count",
                            f"Source {source_name} returned fewer rows than expected.",
                            {
                                "source_run_id": source_run["id"],
                                "source_name": source_name,
                                "records_found": records_found,
                                "minimum_expected": minimum,
                            },
                        )
                    )

        if source_run_ids:
            unresolved = fetch_all(
                conn,
                select(
                    raw_source_records_table.c.id,
                    raw_source_records_table.c.source_run_id,
                    raw_source_records_table.c.raw_model_name,
                    raw_source_records_table.c.resolution_status,
                )
                .where(raw_source_records_table.c.source_run_id.in_(source_run_ids))
                .where(raw_source_records_table.c.resolution_status == "unresolved"),
            )
            if unresolved:
                findings.append(
                    _finding(
                        audit_run_id,
                        "blocker",
                        "unresolved_raw_records",
                        "One or more raw source records did not resolve to a model.",
                        {
                            "count": len(unresolved),
                            "sample": unresolved[:10],
                        },
                    )
                )

        duplicate_latest_rows = [
            dict(row._mapping)
            for row in conn.exec_driver_sql(
                """
                SELECT model_id, benchmark_id, COUNT(*) AS duplicate_count
                FROM latest_scores
                GROUP BY model_id, benchmark_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()
        ]
        if duplicate_latest_rows:
            findings.append(
                _finding(
                    audit_run_id,
                    "blocker",
                    "duplicate_latest_scores",
                    "Duplicate latest score identities were detected.",
                    {"count": len(duplicate_latest_rows), "sample": duplicate_latest_rows[:10]},
                )
            )

        ifeval_trust_violations = fetch_all(
            conn,
            select(
                scores_table.c.id,
                scores_table.c.model_id,
                scores_table.c.source_type,
                scores_table.c.verified,
            )
            .where(scores_table.c.benchmark_id == "ifeval")
            .where((scores_table.c.source_type != "secondary") | (scores_table.c.verified != 0)),
        )
        if ifeval_trust_violations:
            findings.append(
                _finding(
                    audit_run_id,
                    "blocker",
                    "ifeval_trust_labeling",
                    "IFEval rows must remain secondary and unverified.",
                    {"count": len(ifeval_trust_violations), "sample": ifeval_trust_violations[:10]},
                )
            )

        swebench_trust_violations = [
            dict(row._mapping)
            for row in conn.exec_driver_sql(
                """
                SELECT id, model_id, source_type, verified
                FROM latest_scores
                WHERE benchmark_id = 'swebench_verified'
                  AND source_type != 'secondary'
                """
            ).fetchall()
        ]
        if swebench_trust_violations:
            findings.append(
                _finding(
                    audit_run_id,
                    "blocker",
                    "swebench_trust_labeling",
                    "SWE-bench Verified rows must remain secondary because they are derived from official system submissions.",
                    {"count": len(swebench_trust_violations), "sample": swebench_trust_violations[:10]},
                )
            )

        findings.extend(_run_source_spot_checks(conn, audit_run_id, source_runs))

        previous_run = _load_previous_comparable_run(conn, update_log_id)
        if previous_run is not None:
            current_counts = {str(row["source_name"]): int(row.get("records_found") or 0) for row in source_runs}
            previous_counts = _load_source_counts(conn, previous_run["id"])
            for source_name, current_count in current_counts.items():
                previous_count = previous_counts.get(source_name)
                if previous_count is None or previous_count < DRIFT_MIN_BASELINE_RECORDS:
                    continue
                drift = _classify_row_count_drift(previous_count, current_count)
                if drift is None:
                    continue
                severity, check_name, message = drift
                if severity == "blocker" and current_count == 0:
                    message = f"Source {source_name} disappeared relative to the previous run."
                findings.append(
                    _finding(
                        audit_run_id,
                        severity,
                        check_name,
                        message,
                        {
                            "source_name": source_name,
                            "previous_update_log_id": previous_run["id"],
                            "baseline_kind": previous_run["kind"],
                            "previous_records_found": previous_count,
                            "current_records_found": current_count,
                            "pct_change": round(((current_count - previous_count) / previous_count) * 100.0, 2),
                        },
                    )
                )

        findings.extend(_run_new_model_review_checks(conn, audit_run_id, update_log_id))

    blocker_count = sum(1 for finding in findings if finding["severity"] == "blocker")
    warning_count = sum(1 for finding in findings if finding["severity"] == "warning")
    info_count = sum(1 for finding in findings if finding["severity"] == "info")
    status = "failed" if blocker_count else "warning" if warning_count else "passed"
    completed_at = utc_now_iso()
    new_models_finding = next((finding for finding in findings if finding["check_name"] == "new_models_discovered"), None)
    summary = {
        "status": status,
        "finding_count": len(findings),
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "new_model_count": int(new_models_finding["details"].get("count") or 0) if new_models_finding else 0,
        "family_delta_candidate_count": int(new_models_finding["details"].get("family_delta_candidate_count") or 0)
        if new_models_finding
        else 0,
    }

    with engine.begin() as conn:
        conn.execute(
            update(audit_runs_table)
            .where(audit_runs_table.c.id == audit_run_id)
            .values(
                completed_at=completed_at,
                status=status,
                blocker_count=blocker_count,
                warning_count=warning_count,
                info_count=info_count,
                summary_json=json.dumps(summary, ensure_ascii=True, sort_keys=True),
            )
        )
        for finding in findings:
            conn.execute(
                insert(audit_findings_table).values(
                    audit_run_id=audit_run_id,
                    severity=finding["severity"],
                    check_name=finding["check_name"],
                    message=finding["message"],
                    details_json=json.dumps(finding["details"], ensure_ascii=True, sort_keys=True),
                    created_at=completed_at,
                )
            )

    return {
        "id": audit_run_id,
        "update_log_id": update_log_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": status,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "summary_json": summary,
        "findings": findings,
    }


def _run_source_spot_checks(conn, audit_run_id: int, source_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    adapters_by_name = {adapter.source_id: adapter for adapter in get_source_adapters(include_phase_two=True)}

    for source_run in source_runs:
        source_name = str(source_run["source_name"])
        adapter = adapters_by_name.get(source_name)
        if adapter is None or str(source_run.get("status") or "") != "completed":
            continue

        raw_rows = fetch_all(
            conn,
            select(raw_source_records_table)
            .where(raw_source_records_table.c.source_run_id == source_run["id"])
            .order_by(raw_source_records_table.c.id.asc()),
        )
        if not raw_rows:
            continue

        raw_records = [_deserialize_raw_source_record(row, adapter.source_url) for row in raw_rows]
        candidates = adapter.normalize(raw_records)
        if not candidates:
            continue

        model_ids_by_identity = {}
        for row in raw_rows:
            normalized_model_id = row.get("normalized_model_id")
            if not normalized_model_id:
                continue
            identity = (
                str(row.get("raw_model_name") or ""),
                str(row.get("raw_key") or ""),
            )
            model_ids_by_identity.setdefault(identity, str(normalized_model_id))

        benchmark_ids = sorted({str(candidate.benchmark_id) for candidate in candidates})
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

        resolved_candidates: dict[tuple[str, str], tuple[str, Any]] = {}
        for candidate in candidates:
            identity = (candidate.raw_model_name, str(candidate.raw_model_key or ""))
            model_id = model_ids_by_identity.get(identity)
            if not model_id:
                findings.append(
                    _finding(
                        audit_run_id,
                        "blocker",
                        "source_spot_check_missing_model",
                        f"Spot check could not map a normalized model for source {source_name}.",
                        {
                            "source_run_id": source_run["id"],
                            "source_name": source_name,
                            "raw_model_name": candidate.raw_model_name,
                            "raw_model_key": candidate.raw_model_key,
                            "benchmark_id": candidate.benchmark_id,
                        },
                    )
                )
                continue

            candidate_key = (model_id, candidate.benchmark_id)
            existing = resolved_candidates.get(candidate_key)
            if existing is not None:
                benchmark = benchmarks_by_id.get(candidate.benchmark_id)
                current_candidate = {
                    "value": float(existing[1].value),
                    "collected_at": str(existing[1].collected_at),
                }
                next_candidate = {
                    "value": float(candidate.value),
                    "collected_at": str(candidate.collected_at),
                }
                if not _is_better_candidate(next_candidate, current_candidate, benchmark):
                    continue

            resolved_candidates[candidate_key] = (model_id, candidate)

        for model_id, candidate in list(resolved_candidates.values())[:SPOT_CHECK_SAMPLE_SIZE]:

            latest = fetch_one(
                conn,
                select(
                    scores_table.c.value,
                    scores_table.c.source_type,
                    scores_table.c.verified,
                )
                .where(scores_table.c.model_id == model_id)
                .where(scores_table.c.benchmark_id == candidate.benchmark_id)
                .order_by(scores_table.c.collected_at.desc(), scores_table.c.id.desc())
                .limit(1),
            )
            if latest is None:
                findings.append(
                    _finding(
                        audit_run_id,
                        "blocker",
                        "source_spot_check_missing_score",
                        f"Spot check found no latest score for a sampled source candidate from {source_name}.",
                        {
                            "source_run_id": source_run["id"],
                            "source_name": source_name,
                            "model_id": model_id,
                            "raw_model_name": candidate.raw_model_name,
                            "benchmark_id": candidate.benchmark_id,
                        },
                    )
                )
                continue

            value_mismatch = abs(float(latest["value"]) - float(candidate.value)) > 0.1
            source_type_mismatch = str(latest["source_type"]) != candidate.source_type
            verified_mismatch = bool(latest["verified"]) != bool(candidate.verified)
            if not (value_mismatch or source_type_mismatch or verified_mismatch):
                continue

            findings.append(
                _finding(
                    audit_run_id,
                    "blocker",
                    "source_spot_check_mismatch",
                    f"Sampled source candidate from {source_name} does not match the latest score row.",
                    {
                        "source_run_id": source_run["id"],
                        "source_name": source_name,
                        "model_id": model_id,
                        "raw_model_name": candidate.raw_model_name,
                        "benchmark_id": candidate.benchmark_id,
                        "expected_value": candidate.value,
                        "actual_value": latest["value"],
                        "expected_source_type": candidate.source_type,
                        "actual_source_type": latest["source_type"],
                        "expected_verified": bool(candidate.verified),
                        "actual_verified": bool(latest["verified"]),
                    },
                )
            )

    return findings


def _run_new_model_review_checks(conn, audit_run_id: int, update_log_id: int) -> list[dict[str, Any]]:
    new_models = fetch_all(
        conn,
        select(
            models_table.c.id,
            models_table.c.name,
            models_table.c.provider,
            models_table.c.family_id,
            models_table.c.family_name,
            models_table.c.canonical_model_id,
            models_table.c.canonical_model_name,
        )
        .where(models_table.c.active == 1)
        .where(models_table.c.discovered_update_log_id == update_log_id)
        .order_by(models_table.c.provider.asc(), models_table.c.name.asc()),
    )
    if not new_models:
        return []

    family_ids = sorted({str(row.get("family_id") or "").strip() for row in new_models if str(row.get("family_id") or "").strip()})
    approvals_by_family: dict[str, list[str]] = {}
    if family_ids:
        family_approval_rows = fetch_all(
            conn,
            select(
                models_table.c.family_id,
                model_use_case_approvals_table.c.use_case_id,
            )
            .select_from(
                models_table.join(
                    model_use_case_approvals_table,
                    model_use_case_approvals_table.c.model_id == models_table.c.id,
                )
            )
            .where(models_table.c.family_id.in_(family_ids))
            .where(model_use_case_approvals_table.c.approved_for_use == 1)
            .group_by(models_table.c.family_id, model_use_case_approvals_table.c.use_case_id),
        )
        for row in family_approval_rows:
            family_id = str(row.get("family_id") or "").strip()
            use_case_id = str(row.get("use_case_id") or "").strip()
            if not family_id or not use_case_id:
                continue
            approvals_by_family.setdefault(family_id, []).append(use_case_id)

    candidate_count = 0
    sample = []
    for row in new_models[:10]:
        family_id = str(row.get("family_id") or "").strip()
        suggested_use_cases = sorted(approvals_by_family.get(family_id, []))
        if suggested_use_cases:
            candidate_count += 1
        sample.append(
            {
                "model_id": str(row.get("id") or ""),
                "name": str(row.get("name") or ""),
                "provider": str(row.get("provider") or ""),
                "family_id": family_id or None,
                "family_name": str(row.get("family_name") or "") or None,
                "canonical_model_id": str(row.get("canonical_model_id") or "") or None,
                "canonical_model_name": str(row.get("canonical_model_name") or "") or None,
                "suggested_use_cases": suggested_use_cases,
            }
        )

    return [
        _finding(
            audit_run_id,
            "info",
            "new_models_discovered",
            f"{len(new_models)} new model(s) were discovered and need Admin review.",
            {
                "count": len(new_models),
                "family_delta_candidate_count": candidate_count,
                "sample": sample,
            },
        )
    ]


def _is_better_candidate(candidate: dict[str, Any], current_best: dict[str, Any], benchmark: dict[str, Any] | None) -> bool:
    candidate_value = float(candidate["value"])
    current_value = float(current_best["value"])
    higher_is_better = bool(benchmark["higher_is_better"]) if benchmark is not None else True
    if candidate_value != current_value:
        return candidate_value > current_value if higher_is_better else candidate_value < current_value
    return str(candidate.get("collected_at") or "") > str(current_best.get("collected_at") or "")


def _deserialize_raw_source_record(row: dict[str, Any], default_source_url: str) -> RawSourceRecord:
    payload = _load_json_mapping(row.get("payload_json"))
    metadata = _load_json_mapping(row.get("notes"))
    return RawSourceRecord(
        source_id="",
        benchmark_id=str(row.get("benchmark_id") or ""),
        raw_model_name=str(row.get("raw_model_name") or ""),
        raw_value=str(row.get("raw_value") or ""),
        source_url=str(row.get("source_url") or default_source_url),
        collected_at=str(row.get("collected_at") or ""),
        raw_model_key=str(row.get("raw_key") or "") or None,
        payload=payload,
        metadata=metadata,
    )


def _load_json_mapping(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_audit_run(engine, update_log_id: int) -> dict[str, Any] | None:
    with get_connection(engine) as conn:
        audit_run = fetch_one(
            conn,
            select(audit_runs_table).where(audit_runs_table.c.update_log_id == update_log_id),
        )
        if audit_run is None:
            return None
        findings = fetch_all(
            conn,
            select(audit_findings_table).where(audit_findings_table.c.audit_run_id == audit_run["id"]),
        )
    audit_run["findings"] = findings
    return audit_run


def get_audit_summary(engine, update_log_id: int) -> dict[str, Any] | None:
    audit_run = get_audit_run(engine, update_log_id)
    if audit_run is None:
        return None
    return {key: audit_run[key] for key in (
        "id",
        "update_log_id",
        "started_at",
        "completed_at",
        "status",
        "blocker_count",
        "warning_count",
        "info_count",
        "summary_json",
    )}


def _load_previous_comparable_run(conn, update_log_id: int) -> dict[str, Any] | None:
    passed_or_warning = fetch_one(
        conn,
        select(
            audit_runs_table.c.update_log_id,
            audit_runs_table.c.id.label("audit_run_id"),
            audit_runs_table.c.status,
        )
        .select_from(
            audit_runs_table.join(
                source_runs_table,
                source_runs_table.c.update_log_id == audit_runs_table.c.update_log_id,
            )
        )
        .where(audit_runs_table.c.update_log_id < update_log_id)
        .where(audit_runs_table.c.status.in_(("passed", "warning")))
        .group_by(audit_runs_table.c.update_log_id, audit_runs_table.c.id, audit_runs_table.c.status)
        .order_by(audit_runs_table.c.update_log_id.desc(), audit_runs_table.c.id.desc())
        .limit(1),
    )
    if passed_or_warning is not None:
        return {"id": int(passed_or_warning["update_log_id"]), "kind": "successful", "audit_status": passed_or_warning["status"]}

    fallback = fetch_one(
        conn,
        select(
            update_log_table.c.id.label("update_log_id"),
        )
        .where(update_log_table.c.id < update_log_id)
        .where(update_log_table.c.status == "completed")
        .order_by(update_log_table.c.id.desc())
        .limit(1),
    )
    if fallback is None:
        return None
    return {"id": int(fallback["update_log_id"]), "kind": "completed", "audit_status": None}


def _load_source_counts(conn, update_log_id: int) -> dict[str, int]:
    rows = fetch_all(
        conn,
        select(source_runs_table.c.source_name, source_runs_table.c.records_found)
        .where(source_runs_table.c.update_log_id == update_log_id),
    )
    return {str(row["source_name"]): int(row.get("records_found") or 0) for row in rows}


def _classify_row_count_drift(previous_count: int, current_count: int) -> tuple[str, str, str] | None:
    if previous_count <= 0:
        return None
    if current_count == 0:
        return (
            "blocker",
            "source_row_count_missing",
            "Source row count dropped to zero relative to the previous comparable run.",
        )

    pct_change = (current_count - previous_count) / previous_count
    if pct_change <= DRIFT_BLOCKER_DROP_THRESHOLD:
        return (
            "blocker",
            "source_row_count_drop",
            "Source row count dropped sharply relative to the previous comparable run.",
        )
    if pct_change <= DRIFT_WARNING_DROP_THRESHOLD:
        return (
            "warning",
            "source_row_count_drop",
            "Source row count declined relative to the previous comparable run.",
        )
    if pct_change >= DRIFT_WARNING_SPIKE_THRESHOLD:
        return (
            "warning",
            "source_row_count_spike",
            "Source row count increased sharply relative to the previous comparable run.",
        )
    return None


def _finding(audit_run_id: int, severity: str, check_name: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_run_id": audit_run_id,
        "severity": severity,
        "check_name": check_name,
        "message": message,
        "details": details,
    }
