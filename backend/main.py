from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .models import (
    AuditRunOut,
    BenchmarkOut,
    ModelOut,
    RawSourceRecordOut,
    RankingsResponseOut,
    SourceRunOut,
    UpdateLogOut,
    UpdateStartIn,
    UpdateStartOut,
    UseCaseOut,
)
from .audit_engine import get_audit_run
from .update_engine import (
    ENGINE,
    bootstrap,
    get_rankings,
    get_update_log,
    list_benchmarks,
    list_models,
    list_raw_source_records,
    list_source_runs,
    list_update_logs,
    list_use_cases,
    schedule_update,
)

app = FastAPI(title="LLM Benchmarking API", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    bootstrap()


@app.get("/api/benchmarks", response_model=list[BenchmarkOut])
def api_benchmarks() -> list[dict]:
    return list_benchmarks()


@app.get("/api/use-cases", response_model=list[UseCaseOut])
def api_use_cases() -> list[dict]:
    return list_use_cases()


@app.get("/api/models", response_model=list[ModelOut])
def api_models() -> list[dict]:
    return list_models()


@app.post("/api/update", response_model=UpdateStartOut)
def api_update(payload: UpdateStartIn | None = None) -> UpdateStartOut:
    log_id = schedule_update(benchmarks=payload.benchmarks if payload else None, triggered_by="api")
    return UpdateStartOut(log_id=log_id, status="running")


@app.get("/api/update/status/{log_id}", response_model=UpdateLogOut)
def api_update_status(log_id: int) -> dict:
    log = get_update_log(log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Update log not found")
    return log


@app.get("/api/update/history", response_model=list[UpdateLogOut])
def api_update_history() -> list[dict]:
    return list_update_logs()


@app.get("/api/update/history/{log_id}/sources", response_model=list[SourceRunOut])
def api_update_history_sources(log_id: int) -> list[dict]:
    log = get_update_log(log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Update log not found")
    return list_source_runs(log_id)


@app.get("/api/update/source-runs/{source_run_id}/raw-records", response_model=list[RawSourceRecordOut])
def api_source_run_raw_records(source_run_id: int) -> list[dict]:
    records = list_raw_source_records(source_run_id)
    if not records:
        raise HTTPException(status_code=404, detail="Source run raw records not found")
    return records


@app.get("/api/update/audit/{log_id}", response_model=AuditRunOut)
def api_update_audit(log_id: int) -> dict:
    audit = get_audit_run(ENGINE, log_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit run not found")
    return audit


@app.get("/api/rankings", response_model=RankingsResponseOut)
def api_rankings(use_case: str) -> dict:
    rankings = get_rankings(use_case)
    if rankings is None:
        raise HTTPException(status_code=404, detail="Use case not found")
    return rankings
