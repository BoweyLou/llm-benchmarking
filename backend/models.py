"""Pydantic response and request models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal["primary", "secondary", "manual"]
ModelRole = Literal["generator", "embedding", "reranker", "multimodal_embedding", "speech_to_text", "text_to_speech"]
RawSourceResolutionStatus = Literal["resolved", "skipped_aggregate", "skipped_unmatched_listing", "unresolved"]
UpdateStatus = Literal["running", "completed", "failed"]
SourceRunStatus = Literal["running", "completed", "failed", "skipped"]
ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
RestrictedMode = Literal["pro", "ultra"]
TriggeredBy = Literal["manual", "api", "scheduled", "bootstrap", "cli"]
AuditStatus = Literal["passed", "warning", "failed"]
AuditSeverity = Literal["blocker", "warning", "info"]
FamilyApprovalScope = Literal["family", "delta"]
RecommendationStatusIn = Literal["unrated", "recommended", "not_recommended", "discouraged", "restricted"]
RecommendationStatusOut = Literal["unrated", "recommended", "not_recommended", "discouraged", "restricted", "mixed"]
GeneralRecommendationStatusIn = Literal["unrated", "recommended", "not_recommended", "restricted"]
CatalogStatusIn = Literal["tracked", "provisional", "deprecated"]
GeneralApprovalStatusIn = Literal["approved", "not_approved", "unreviewed"]
UpdateProgressStatus = Literal["pending", "running", "completed", "failed"]
LicensePolicyClass = Literal["commercial_clear", "potential_legal_review", "commercial_blocked"]
ProvenancePolicyClass = Literal["standard", "derivative_review", "derivative_unverified"]


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
    confidence_lower: float | None = None
    confidence_upper: float | None = None
    variance: float | None = None
    vote_count: int | None = None
    observation_count: int | None = None
    session_count: int | None = None
    rank: int | None = None
    category: str | None = None
    publication_date: str | None = None
    methodology: str | None = None
    source_listing_status: str | None = None
    style_control: bool | None = None
    preliminary: bool | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    variant_model_id: str | None = None
    variant_model_name: str | None = None
    configuration_key: str | None = None
    configuration_value: str | None = None


class InferenceSourceOut(APIModel):
    label: str
    url: str


class PricingProvenanceOut(APIModel):
    kind: str
    label: str
    url: str
    verified_at: datetime
    stale: bool = False


class PricingComponentOut(APIModel):
    modality: str = "text"
    charge_type: str
    amount: float | None = None
    billing_unit: str
    unit_quantity: float = 1
    conditions: dict[str, Any] = Field(default_factory=dict)


class PricingOfferOut(APIModel):
    id: int
    destination_id: str
    provider_model_id: str | None = None
    service_tier: str = "standard"
    region: str | None = None
    currency: str = "USD"
    constraints: dict[str, Any] = Field(default_factory=dict)
    price_status: str = "published"
    components: list[PricingComponentOut] = Field(default_factory=list)
    provenance: PricingProvenanceOut


class PricingSummaryOut(APIModel):
    priced_route_count: int = 0
    offer_count: int = 0
    currencies: list[str] = Field(default_factory=list)
    stale_offer_count: int = 0


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
    pricing_offers: list[PricingOfferOut] = Field(default_factory=list)


class InferenceSummaryOut(APIModel):
    destination_count: int = 0
    region_count: int = 0
    platform_names: list[str] = Field(default_factory=list)
    deployment_modes: list[str] = Field(default_factory=list)


class SourceFreshnessOut(APIModel):
    source_name: str
    source_label: str
    benchmark_ids: list[str] = Field(default_factory=list)
    model_benchmark_ids: list[str] = Field(default_factory=list)
    latest_source_status: str | None = None
    latest_attempted_at: datetime | None = None
    latest_success_at: datetime | None = None
    latest_failure_at: datetime | None = None
    latest_error: str | None = None
    latest_model_score_at: datetime | None = None
    latest_model_raw_record_at: datetime | None = None
    has_model_score: bool = False
    has_model_raw_record: bool = False
    model_evidence_status: str = "unknown"
    degraded: bool = False
    stale: bool = False
    missing_because_source_failed: bool = False


class SourceListingOut(APIModel):
    id: int
    source_name: str
    benchmark_id: str
    raw_model_name: str
    raw_model_key: str
    model_id: str | None = None
    listing_status: str
    source_revision: str | None = None
    publication_date: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    auto_recommendation_status: RecommendationStatusOut = "unrated"
    auto_recommendation_notes: str | None = None
    auto_not_recommended_member_count: int = 0
    approval_member_count: int = 0
    approval_total_count: int = 1
    recommended_member_count: int = 0
    not_recommended_member_count: int = 0
    discouraged_member_count: int = 0
    restricted_member_count: int = 0
    proposed_recommendation_status: RecommendationStatusOut = "unrated"
    proposed_recommendation_score: float | None = None
    proposed_recommendation_confidence: float | None = None
    proposed_recommendation_blockers: list[str] = Field(default_factory=list)
    proposed_recommendation_warnings: list[str] = Field(default_factory=list)
    proposed_recommendation_reasons: list[str] = Field(default_factory=list)
    proposed_recommendation_required_controls: list[str] = Field(default_factory=list)
    proposed_recommendation_policy_version: str | None = None
    proposed_recommendation_computed_at: datetime | None = None
    effective_recommendation_status: RecommendationStatusOut = "unrated"
    inference_route_approvals: list["InferenceRouteApprovalOut"] = Field(default_factory=list)


class UseCaseApprovalIn(APIModel):
    approved_for_use: bool = False
    approval_notes: str | None = None
    recommendation_status: RecommendationStatusIn = "unrated"
    recommendation_notes: str | None = None


class SuggestedUseCaseOut(APIModel):
    use_case_id: str
    label: str
    description: str | None = None
    fit_score: float
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_controls: list[str] = Field(default_factory=list)
    policy_version: str | None = None
    computed_at: datetime | None = None


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
    model_roles: list[ModelRole] = Field(default_factory=lambda: ["generator"])
    catalog_status: str = "tracked"
    release_date: str | None = None
    release_date_precision: str | None = None
    release_date_confidence: str | None = None
    release_date_source_name: str | None = None
    release_date_source_url: str | None = None
    release_date_verified_at: datetime | None = None
    model_age_days: int | None = None
    model_age_basis: str | None = None
    model_age_confidence: str | None = None
    model_age_source_name: str | None = None
    model_age_source_url: str | None = None
    model_age_reference_date: str | None = None
    context_window: str | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    parameter_count_b: float | None = None
    active_parameter_count_b: float | None = None
    model_size_class: str | None = None
    small_model_candidate: bool = False
    model_size_source_name: str | None = None
    model_size_source_url: str | None = None
    model_size_verified_at: datetime | None = None
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    openrouter_model_id: str | None = None
    openrouter_canonical_slug: str | None = None
    openrouter_added_at: datetime | None = None
    huggingface_repo_id: str | None = None
    huggingface_created_at: datetime | None = None
    huggingface_last_modified_at: datetime | None = None
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
    license_policy_class: LicensePolicyClass = "potential_legal_review"
    license_policy_label: str | None = None
    license_policy_note: str | None = None
    potential_legal_review: bool = False
    commercial_use_blocked: bool = False
    provenance_policy_class: ProvenancePolicyClass = "standard"
    provenance_policy_label: str | None = None
    provenance_policy_note: str | None = None
    derivative_model: bool = False
    potential_provenance_review: bool = False
    production_provenance_blocked: bool = False
    provenance_gap_fields: list[str] = Field(default_factory=list)
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
    general_approved_for_use: bool = False
    general_approval_notes: str | None = None
    general_approval_updated_at: datetime | None = None
    general_recommendation_status: GeneralRecommendationStatusIn = "unrated"
    general_recommendation_notes: str | None = None
    general_recommendation_updated_at: datetime | None = None
    reasoning_effort_ceiling: ReasoningEffort | None = None
    restricted_modes: list[RestrictedMode] = Field(default_factory=list)
    usage_policy_notes: str | None = None
    usage_policy_updated_at: datetime | None = None
    score_configurations: list[dict[str, Any]] = Field(default_factory=list)
    suggested_use_cases: list[SuggestedUseCaseOut] = Field(default_factory=list)
    approved_for_use: bool = False
    approval_use_case_count: int = 0
    use_case_approvals: dict[str, UseCaseApprovalOut] = Field(default_factory=dict)
    approval_notes: str | None = None
    approval_updated_at: datetime | None = None
    active: bool = True
    inference_destinations: list[InferenceDestinationOut] = Field(default_factory=list)
    inference_summary: InferenceSummaryOut = Field(default_factory=InferenceSummaryOut)
    pricing_summary: PricingSummaryOut = Field(default_factory=PricingSummaryOut)
    source_freshness: list[SourceFreshnessOut] = Field(default_factory=list)
    source_listings: list[SourceListingOut] = Field(default_factory=list)
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
    model_roles: list[ModelRole] = Field(default_factory=lambda: ["generator"])
    catalog_status: str = "tracked"
    release_date: str | None = None
    release_date_precision: str | None = None
    release_date_confidence: str | None = None
    release_date_source_name: str | None = None
    release_date_source_url: str | None = None
    release_date_verified_at: datetime | None = None
    model_age_days: int | None = None
    model_age_basis: str | None = None
    model_age_confidence: str | None = None
    model_age_source_name: str | None = None
    model_age_source_url: str | None = None
    model_age_reference_date: str | None = None
    context_window: str | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    parameter_count_b: float | None = None
    active_parameter_count_b: float | None = None
    model_size_class: str | None = None
    small_model_candidate: bool = False
    model_size_source_name: str | None = None
    model_size_source_url: str | None = None
    model_size_verified_at: datetime | None = None
    openrouter_added_at: datetime | None = None
    huggingface_repo_id: str | None = None
    huggingface_created_at: datetime | None = None
    huggingface_last_modified_at: datetime | None = None
    model_card_url: str | None = None
    model_card_source: str | None = None
    model_card_verified_at: datetime | None = None
    documentation_url: str | None = None
    repo_url: str | None = None
    paper_url: str | None = None
    license_id: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    license_policy_class: LicensePolicyClass = "potential_legal_review"
    license_policy_label: str | None = None
    license_policy_note: str | None = None
    potential_legal_review: bool = False
    commercial_use_blocked: bool = False
    provenance_policy_class: ProvenancePolicyClass = "standard"
    provenance_policy_label: str | None = None
    provenance_policy_note: str | None = None
    derivative_model: bool = False
    potential_provenance_review: bool = False
    production_provenance_blocked: bool = False
    provenance_gap_fields: list[str] = Field(default_factory=list)
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
    general_approved_for_use: bool = False
    general_approval_notes: str | None = None
    general_approval_updated_at: datetime | None = None
    general_recommendation_status: GeneralRecommendationStatusIn = "unrated"
    general_recommendation_notes: str | None = None
    general_recommendation_updated_at: datetime | None = None
    reasoning_effort_ceiling: ReasoningEffort | None = None
    restricted_modes: list[RestrictedMode] = Field(default_factory=list)
    usage_policy_notes: str | None = None
    usage_policy_updated_at: datetime | None = None
    suggested_use_cases: list[SuggestedUseCaseOut] = Field(default_factory=list)
    approved_for_use: bool = False
    approval_use_case_count: int = 0
    use_case_approvals: dict[str, UseCaseApprovalOut] = Field(default_factory=dict)
    approval_notes: str | None = None
    approval_updated_at: datetime | None = None
    active: bool = True
    inference_summary: InferenceSummaryOut = Field(default_factory=InferenceSummaryOut)
    source_freshness: list[SourceFreshnessOut] = Field(default_factory=list)


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


class ReviewDecisionIn(APIModel):
    model_ids: list[str] = Field(default_factory=list)
    use_case_ids: list[str] = Field(default_factory=list)
    approved_for_use: bool | None = None
    approval_notes: str | None = None
    recommendation_status: RecommendationStatusIn | None = None
    recommendation_notes: str | None = None
    catalog_status: CatalogStatusIn | None = None


class ReviewModelApprovalIn(APIModel):
    model_ids: list[str] = Field(default_factory=list)
    approved_for_use: bool = False
    approval_status: GeneralApprovalStatusIn | None = None
    approval_notes: str | None = None


class ReviewModelDecisionIn(APIModel):
    model_ids: list[str] = Field(default_factory=list)
    approval_status: GeneralApprovalStatusIn | None = None
    approval_notes: str | None = None
    recommendation_status: GeneralRecommendationStatusIn | None = None
    recommendation_notes: str | None = None
    reasoning_effort_ceiling: ReasoningEffort | None = None
    restricted_modes: list[RestrictedMode] | None = None
    usage_policy_notes: str | None = None

    @field_validator("recommendation_status", mode="before")
    @classmethod
    def normalize_legacy_general_recommendation(cls, value: Any) -> Any:
        return "not_recommended" if value == "discouraged" else value


class ReviewModelCreateIn(APIModel):
    name: str
    provider: str
    model_id: str | None = None
    type: str = "proprietary"
    model_roles: list[ModelRole] = Field(default_factory=lambda: ["generator"])
    catalog_status: CatalogStatusIn = "tracked"
    notes: str | None = None

    @field_validator("model_roles", mode="before")
    @classmethod
    def coerce_model_roles(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        return value


class ReviewSnapshotIn(APIModel):
    schema_version: int
    exported_at: str | None = None
    catalog_statuses: list[dict[str, Any]] = Field(default_factory=list)
    model_approvals: list[dict[str, Any]] = Field(default_factory=list)
    manual_models: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)


class UseCaseOut(APIModel):
    id: str
    label: str
    icon: str
    description: str
    segment: str = "core"
    status: Literal["ready", "preview"] = "ready"
    model_roles: list[ModelRole] = Field(default_factory=lambda: ["generator"])
    production_commercial: bool = False
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


class UpdateModelFieldChangeOut(APIModel):
    field: str
    label: str
    before: Any = None
    after: Any = None


class UpdateModelChangeOut(APIModel):
    id: str
    name: str | None = None
    provider: str | None = None
    catalog_status: str | None = None
    model_roles: list[str] = Field(default_factory=list)
    metadata_source_name: str | None = None
    metadata_source_url: str | None = None
    discovered_at: datetime | None = None
    changed_fields: list[str] = Field(default_factory=list)
    field_changes: list[UpdateModelFieldChangeOut] = Field(default_factory=list)


class UpdateChangeSummaryOut(APIModel):
    generated_at: datetime | None = None
    model_count_before: int = 0
    model_count_after: int = 0
    model_count_delta: int = 0
    new_model_count: int = 0
    changed_model_count: int = 0
    removed_model_count: int = 0
    unchanged_model_count: int = 0
    source_record_count: int = 0
    source_failure_count: int = 0
    new_models: list[UpdateModelChangeOut] = Field(default_factory=list)
    changed_models: list[UpdateModelChangeOut] = Field(default_factory=list)
    removed_models: list[UpdateModelChangeOut] = Field(default_factory=list)
    truncated: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


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
    change_summary: UpdateChangeSummaryOut | None = None


class SourceRunOut(APIModel):
    id: int
    update_log_id: int | None = None
    source_name: str
    benchmark_id: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    status: SourceRunStatus = "running"
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
    "ModelRole",
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
    "SourceFreshnessOut",
    "SourceRunOut",
    "UpdateLogOut",
    "UpdateChangeSummaryOut",
    "UpdateModelChangeOut",
    "UpdateModelFieldChangeOut",
    "UpdateStartIn",
    "UpdateStartOut",
    "UpdateStatus",
    "UseCaseOut",
]
