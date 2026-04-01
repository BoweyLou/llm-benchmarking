from __future__ import annotations

import json
from typing import Any

from sqlalchemy import insert, select, update

from .database import (
    audit_runs as audit_runs_table,
    audit_findings as audit_findings_table,
    fetch_all,
    fetch_one,
    get_connection,
    raw_source_records as raw_source_records_table,
    scores as scores_table,
    source_runs as source_runs_table,
    update_log as update_log_table,
    utc_now_iso,
)

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

    blocker_count = sum(1 for finding in findings if finding["severity"] == "blocker")
    warning_count = sum(1 for finding in findings if finding["severity"] == "warning")
    info_count = sum(1 for finding in findings if finding["severity"] == "info")
    status = "failed" if blocker_count else "warning" if warning_count else "passed"
    completed_at = utc_now_iso()
    summary = {
        "status": status,
        "finding_count": len(findings),
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "info_count": info_count,
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
