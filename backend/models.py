"""Pydantic response and request models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["primary", "secondary", "manual"]
RawSourceResolutionStatus = Literal["resolved", "skipped_aggregate", "unresolved"]
UpdateStatus = Literal["running", "completed", "failed"]
TriggeredBy = Literal["manual", "api", "scheduled", "bootstrap", "cli"]
AuditStatus = Literal["passed", "warning", "failed"]
AuditSeverity = Literal["blocker", "warning", "info"]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class BenchmarkOut(APIModel):
    id: str
    name: str
    short: str
    source: str
    url: str
    category: str
    metric: str
    higher_is_better: bool = True
    tier: int = 2
    description: str | None = None
    scraper_id: str | None = None
    active: bool = True
    range_min: float | None = None
    range_max: float | None = None
    data_points: int = 0
    latest_updated_at: datetime | None = None


class ScoreOut(APIModel):
    value: float
    raw_value: str | None = None
    collected_at: datetime
    source_url: str | None = None
    source_type: SourceType = "primary"
    verified: bool = False
    notes: str | None = None


class ModelOut(APIModel):
    id: str
    name: str
    provider: str
    type: str = "proprietary"
    release_date: str | None = None
    context_window: str | None = None
    active: bool = True
    scores: dict[str, ScoreOut | None] = Field(default_factory=dict)


class ModelSummaryOut(APIModel):
    id: str
    name: str
    provider: str
    type: str = "proprietary"
    release_date: str | None = None
    context_window: str | None = None
    active: bool = True


class UseCaseOut(APIModel):
    id: str
    label: str
    icon: str
    description: str
    segment: str = "core"
    status: Literal["ready", "preview"] = "ready"
    min_coverage: float = 0.5
    required_benchmarks: list[str] = Field(default_factory=list)
    benchmark_notes: dict[str, str] = Field(default_factory=dict)
    weights: dict[str, float]


class RankingBreakdownOut(APIModel):
    benchmark_id: str
    raw_value: float
    normalised: float
    weight: float
    metric: str
    source_type: SourceType = "primary"
    verified: bool = False
    notes: str | None = None


class RankingOut(APIModel):
    rank: int
    score: float
    coverage: float
    model: ModelSummaryOut
    breakdown: list[RankingBreakdownOut] = Field(default_factory=list)
    missing_benchmarks: list[str] = Field(default_factory=list)
    critical_missing_benchmarks: list[str] = Field(default_factory=list)


class RankingsResponseOut(APIModel):
    use_case: UseCaseOut
    rankings: list[RankingOut] = Field(default_factory=list)


class UpdateLogOut(APIModel):
    id: int
    started_at: datetime
    completed_at: datetime | None = None
    triggered_by: TriggeredBy = "manual"
    status: UpdateStatus = "running"
    scores_added: int = 0
    scores_updated: int = 0
    errors: Any = None
    audit_summary: AuditSummaryOut | None = None
    source_runs: list[SourceRunOut] = Field(default_factory=list)


class SourceRunOut(APIModel):
    id: int
    update_log_id: int | None = None
    source_name: str
    benchmark_id: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    status: UpdateStatus = "running"
    records_found: int = 0
    error_message: str | None = None
    details_json: str | None = None


class RawSourceRecordOut(APIModel):
    id: int
    source_run_id: int
    benchmark_id: str | None = None
    raw_model_name: str
    normalized_model_id: str | None = None
    raw_key: str | None = None
    raw_value: str | None = None
    payload_json: str
    source_url: str | None = None
    source_type: SourceType = "primary"
    verified: bool = False
    resolution_status: RawSourceResolutionStatus = "resolved"
    collected_at: datetime
    notes: str | None = None


class AuditFindingOut(APIModel):
    id: int
    audit_run_id: int
    severity: AuditSeverity
    check_name: str
    message: str
    details_json: str | None = None
    created_at: datetime


class AuditSummaryOut(APIModel):
    id: int
    update_log_id: int
    started_at: datetime
    completed_at: datetime | None = None
    status: AuditStatus = "passed"
    blocker_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    summary_json: str | None = None


class AuditRunOut(AuditSummaryOut):
    findings: list[AuditFindingOut] = Field(default_factory=list)


class UpdateStartIn(APIModel):
    benchmarks: list[str] | None = None


class UpdateStartOut(APIModel):
    log_id: int
    status: UpdateStatus


class ManualScoreIn(APIModel):
    model_id: str
    benchmark_id: str
    value: float
    raw_value: str | None = None
    notes: str | None = None
    source_url: str | None = None
    source_type: SourceType = "manual"
    verified: bool = False


class HistoryEntryOut(APIModel):
    date: str
    note: str
    model_count: int
    benchmark_count: int


__all__ = [
    "APIModel",
    "AuditFindingOut",
    "AuditRunOut",
    "AuditStatus",
    "AuditSeverity",
    "AuditSummaryOut",
    "BenchmarkOut",
    "HistoryEntryOut",
    "ManualScoreIn",
    "ModelOut",
    "ModelSummaryOut",
    "RawSourceRecordOut",
    "RawSourceResolutionStatus",
    "RankingBreakdownOut",
    "RankingOut",
    "RankingsResponseOut",
    "ScoreOut",
    "SourceRunOut",
    "UpdateLogOut",
    "UpdateStartIn",
    "UpdateStartOut",
    "UpdateStatus",
    "UseCaseOut",
]
