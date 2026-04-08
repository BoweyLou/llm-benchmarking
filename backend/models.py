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
FamilyApprovalScope = Literal["family", "delta"]
RecommendationStatusIn = Literal["unrated", "recommended", "not_recommended", "discouraged"]
RecommendationStatusOut = Literal["unrated", "recommended", "not_recommended", "discouraged", "mixed"]
UpdateProgressStatus = Literal["pending", "running", "completed", "failed"]


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
    variant_model_id: str | None = None
    variant_model_name: str | None = None


class InferenceSourceOut(APIModel):
    label: str
    url: str


class InferenceDestinationOut(APIModel):
    id: str
    name: str
    hyperscaler: str
    availability_scope: str
    availability_note: str | None = None
    location_scope: str
    regions: list[str] = Field(default_factory=list)
    region_count: int = 0
    deployment_modes: list[str] = Field(default_factory=list)
    pricing_label: str | None = None
    pricing_note: str | None = None
    sources: list[InferenceSourceOut] = Field(default_factory=list)


class InferenceSummaryOut(APIModel):
    destination_count: int = 0
    region_count: int = 0
    platform_names: list[str] = Field(default_factory=list)
    deployment_modes: list[str] = Field(default_factory=list)


class OriginCountryOut(APIModel):
    code: str | None = None
    name: str


class OriginCountryIn(APIModel):
    code: str | None = None
    name: str


class UseCaseApprovalOut(APIModel):
    use_case_id: str
    approved_for_use: bool = False
    approval_notes: str | None = None
    approval_updated_at: datetime | None = None
    recommendation_status: RecommendationStatusOut = "unrated"
    recommendation_notes: str | None = None
    recommendation_updated_at: datetime | None = None
    approval_member_count: int = 0
    approval_total_count: int = 1
    recommended_member_count: int = 0
    not_recommended_member_count: int = 0
    discouraged_member_count: int = 0
    inference_route_approvals: list["InferenceRouteApprovalOut"] = Field(default_factory=list)


class UseCaseApprovalIn(APIModel):
    approved_for_use: bool = False
    approval_notes: str | None = None
    recommendation_status: RecommendationStatusIn = "unrated"
    recommendation_notes: str | None = None


class InferenceRouteApprovalOut(APIModel):
    use_case_id: str
    destination_id: str
    destination_name: str | None = None
    hyperscaler: str | None = None
    location_key: str
    location_label: str
    approved_for_use: bool = False
    approval_notes: str | None = None
    approval_updated_at: datetime | None = None


class InferenceRouteApprovalIn(APIModel):
    destination_id: str
    location_key: str | None = None
    location_label: str
    approved_for_use: bool = False
    approval_notes: str | None = None


class InferenceRouteApprovalBulkIn(APIModel):
    model_ids: list[str] = Field(default_factory=list)
    destination_id: str
    location_key: str | None = None
    location_label: str
    approved_for_use: bool = False
    approval_notes: str | None = None


class InferenceRouteApprovalBulkOut(APIModel):
    use_case_id: str
    destination_id: str
    destination_name: str | None = None
    hyperscaler: str | None = None
    location_key: str
    location_label: str
    approved_for_use: bool = False
    approval_notes: str | None = None
    updated_count: int = 0
    updated_model_ids: list[str] = Field(default_factory=list)
    applied_at: datetime | None = None


class FamilyApprovalDeltaIn(APIModel):
    approval_notes: str | None = None


class FamilyApprovalDeltaOut(APIModel):
    family_id: str
    family_name: str | None = None
    use_case_id: str
    updated_count: int = 0
    candidate_count: int = 0
    reference_approved_count: int = 0
    updated_model_ids: list[str] = Field(default_factory=list)
    approval_notes: str | None = None
    applied_at: datetime | None = None


class FamilyApprovalBulkIn(APIModel):
    use_case_ids: list[str] = Field(default_factory=list)
    approval_notes: str | None = None
    scope: FamilyApprovalScope = "family"


class FamilyApprovalBulkUseCaseOut(APIModel):
    use_case_id: str
    updated_count: int = 0
    candidate_count: int = 0
    reference_approved_count: int = 0
    updated_model_ids: list[str] = Field(default_factory=list)
    skipped_reason: str | None = None


class FamilyApprovalBulkOut(APIModel):
    family_id: str
    family_name: str | None = None
    scope: FamilyApprovalScope = "family"
    use_case_ids: list[str] = Field(default_factory=list)
    total_updated_count: int = 0
    results: list[FamilyApprovalBulkUseCaseOut] = Field(default_factory=list)
    approval_notes: str | None = None
    applied_at: datetime | None = None


class ModelIdentityCurationIn(APIModel):
    target_model_id: str
    variant_label: str | None = None
    notes: str | None = None


class ModelDuplicateCurationIn(APIModel):
    target_model_id: str
    notes: str | None = None


class ModelOut(APIModel):
    id: str
    name: str
    provider_id: str | None = None
    provider: str
    provider_country_code: str | None = None
    provider_country_name: str | None = None
    provider_country_flag: str | None = None
    provider_origin_countries: list[OriginCountryOut] = Field(default_factory=list)
    provider_origin_basis: str | None = None
    provider_origin_source_url: str | None = None
    provider_origin_verified_at: datetime | None = None
    type: str = "proprietary"
    catalog_status: str = "tracked"
    release_date: str | None = None
    context_window: str | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    openrouter_model_id: str | None = None
    openrouter_canonical_slug: str | None = None
    openrouter_added_at: datetime | None = None
    huggingface_repo_id: str | None = None
    metadata_source_name: str | None = None
    metadata_source_url: str | None = None
    metadata_verified_at: datetime | None = None
    model_card_url: str | None = None
    model_card_source: str | None = None
    model_card_verified_at: datetime | None = None
    documentation_url: str | None = None
    repo_url: str | None = None
    paper_url: str | None = None
    license_id: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    base_models: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    intended_use_short: str | None = None
    limitations_short: str | None = None
    training_data_summary: str | None = None
    training_cutoff: str | None = None
    openrouter_global_rank: int | None = None
    openrouter_global_total_tokens: int | None = None
    openrouter_global_share: float | None = None
    openrouter_global_change_ratio: float | None = None
    openrouter_global_request_count: int | None = None
    openrouter_programming_rank: int | None = None
    openrouter_programming_total_tokens: int | None = None
    openrouter_programming_volume: float | None = None
    openrouter_programming_request_count: int | None = None
    market_source_name: str | None = None
    market_source_url: str | None = None
    market_verified_at: datetime | None = None
    family_id: str | None = None
    family_name: str | None = None
    canonical_model_id: str | None = None
    canonical_model_name: str | None = None
    variant_label: str | None = None
    discovered_at: datetime | None = None
    discovered_update_log_id: int | None = None
    approved_for_use: bool = False
    approval_use_case_count: int = 0
    use_case_approvals: dict[str, UseCaseApprovalOut] = Field(default_factory=dict)
    approval_notes: str | None = None
    approval_updated_at: datetime | None = None
    active: bool = True
    inference_destinations: list[InferenceDestinationOut] = Field(default_factory=list)
    inference_summary: InferenceSummaryOut = Field(default_factory=InferenceSummaryOut)
    scores: dict[str, ScoreOut | None] = Field(default_factory=dict)


class ModelSummaryOut(APIModel):
    id: str
    name: str
    provider_id: str | None = None
    provider: str
    provider_country_code: str | None = None
    provider_country_name: str | None = None
    provider_country_flag: str | None = None
    provider_origin_countries: list[OriginCountryOut] = Field(default_factory=list)
    provider_origin_basis: str | None = None
    provider_origin_source_url: str | None = None
    provider_origin_verified_at: datetime | None = None
    type: str = "proprietary"
    catalog_status: str = "tracked"
    release_date: str | None = None
    context_window: str | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    openrouter_added_at: datetime | None = None
    huggingface_repo_id: str | None = None
    model_card_url: str | None = None
    model_card_source: str | None = None
    model_card_verified_at: datetime | None = None
    documentation_url: str | None = None
    repo_url: str | None = None
    paper_url: str | None = None
    license_id: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    base_models: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    intended_use_short: str | None = None
    limitations_short: str | None = None
    training_data_summary: str | None = None
    training_cutoff: str | None = None
    openrouter_global_rank: int | None = None
    openrouter_global_total_tokens: int | None = None
    openrouter_global_share: float | None = None
    openrouter_programming_rank: int | None = None
    openrouter_programming_total_tokens: int | None = None
    family_id: str | None = None
    family_name: str | None = None
    canonical_model_id: str | None = None
    canonical_model_name: str | None = None
    variant_label: str | None = None
    discovered_at: datetime | None = None
    discovered_update_log_id: int | None = None
    approved_for_use: bool = False
    approval_use_case_count: int = 0
    use_case_approvals: dict[str, UseCaseApprovalOut] = Field(default_factory=dict)
    approval_notes: str | None = None
    approval_updated_at: datetime | None = None
    active: bool = True
    inference_summary: InferenceSummaryOut = Field(default_factory=InferenceSummaryOut)


class ProviderOut(APIModel):
    id: str
    name: str
    country_code: str | None = None
    country_name: str | None = None
    origin_countries: list[OriginCountryOut] = Field(default_factory=list)
    origin_basis: str | None = None
    source_url: str | None = None
    verified_at: str | None = None
    active: bool = True


class ProviderUpdateIn(APIModel):
    country_code: str | None = None
    country_name: str | None = None
    origin_countries: list[OriginCountryIn] | None = None
    origin_basis: str | None = None
    source_url: str | None = None
    verified_at: str | None = None


class ModelApprovalUpdateIn(APIModel):
    approved_for_use: bool = False
    approval_notes: str | None = None


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
    internal_view_weight: float = 0.0
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
    variant_model_id: str | None = None
    variant_model_name: str | None = None


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


class MarketSnapshotOut(APIModel):
    source_name: str
    scope: str
    category_slug: str = ""
    snapshot_date: str
    model_id: str
    model_name: str
    provider: str
    openrouter_slug: str | None = None
    rank: int
    total_tokens: int | None = None
    share: float | None = None
    change_ratio: float | None = None
    request_count: int | None = None
    volume: float | None = None
    source_url: str | None = None
    collected_at: datetime | None = None


class UpdateProgressStepOut(APIModel):
    key: str
    label: str
    kind: str
    status: UpdateProgressStatus = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    detail: str | None = None
    records_found: int | None = None
    error_message: str | None = None


class UpdateLogOut(APIModel):
    id: int
    started_at: datetime
    completed_at: datetime | None = None
    triggered_by: TriggeredBy = "manual"
    status: UpdateStatus = "running"
    scores_added: int = 0
    scores_updated: int = 0
    errors: Any = None
    current_step_key: str | None = None
    current_step_label: str | None = None
    current_step_started_at: datetime | None = None
    current_step_index: int = 0
    total_steps: int = 0
    finished_steps: int = 0
    progress_percent: float = 0.0
    progress_steps: list[UpdateProgressStepOut] = Field(default_factory=list)
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


class ManualScoreUpdateIn(APIModel):
    value: float | None = None
    raw_value: str | None = None
    notes: str | None = None
    source_url: str | None = None
    verified: bool = False


class ManualScoreResultOut(APIModel):
    model_id: str
    benchmark_id: str
    score: ScoreOut | None = None


class BenchmarkWeightUpdateIn(APIModel):
    weight: float = Field(ge=0.0, le=1.0)


class HistoryEntryOut(APIModel):
    date: str
    note: str
    model_count: int
    benchmark_count: int


UseCaseApprovalOut.model_rebuild()


__all__ = [
    "APIModel",
    "AuditFindingOut",
    "AuditRunOut",
    "AuditStatus",
    "AuditSeverity",
    "AuditSummaryOut",
    "BenchmarkWeightUpdateIn",
    "BenchmarkOut",
    "FamilyApprovalBulkIn",
    "FamilyApprovalBulkOut",
    "FamilyApprovalBulkUseCaseOut",
    "FamilyApprovalDeltaIn",
    "FamilyApprovalDeltaOut",
    "HistoryEntryOut",
    "InferenceRouteApprovalBulkIn",
    "InferenceRouteApprovalBulkOut",
    "InferenceRouteApprovalIn",
    "InferenceRouteApprovalOut",
    "ManualScoreIn",
    "ManualScoreResultOut",
    "ManualScoreUpdateIn",
    "MarketSnapshotOut",
    "ModelApprovalUpdateIn",
    "ModelOut",
    "ModelSummaryOut",
    "ProviderOut",
    "ProviderUpdateIn",
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
