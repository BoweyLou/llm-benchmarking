from __future__ import annotations

from ipaddress import ip_address, ip_network
import os
from pathlib import Path
from secrets import compare_digest
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from .catalog_export import build_model_metadata_list
from .models import (
    AuditRunOut,
    BenchmarkWeightUpdateIn,
    BenchmarkOut,
    FamilyApprovalBulkIn,
    FamilyApprovalBulkOut,
    FamilyApprovalDeltaIn,
    FamilyApprovalDeltaOut,
    InferenceRouteApprovalBulkIn,
    InferenceRouteApprovalBulkOut,
    InferenceRouteApprovalIn,
    ManualScoreResultOut,
    ManualScoreUpdateIn,
    MarketSnapshotOut,
    ModelApprovalUpdateIn,
    ModelDuplicateCurationIn,
    ModelIdentityCurationIn,
    ModelOut,
    ModelSummaryOut,
    ProviderOut,
    ProviderUpdateIn,
    RawSourceRecordOut,
    RankingsResponseOut,
    ReviewDecisionIn,
    ReviewModelApprovalIn,
    ReviewModelDecisionIn,
    ReviewModelCreateIn,
    ReviewSnapshotIn,
    SourceRunOut,
    UpdateLogOut,
    UpdateStartIn,
    UpdateStartOut,
    UseCaseApprovalIn,
    UseCaseOut,
)
from .audit_engine import get_audit_run
from .update_engine import (
    ENGINE,
    bootstrap,
    get_rankings,
    get_update_log,
    list_benchmarks,
    list_market_snapshots,
    list_models,
    list_providers,
    list_raw_source_records,
    list_source_runs,
    list_update_logs,
    list_use_cases,
    schedule_update,
    apply_model_family_approval_bulk,
    apply_model_family_approval_delta,
    apply_model_inference_route_approval_bulk,
    curate_model_identity,
    update_manual_benchmark_score,
    merge_model_duplicate,
    update_model_approval,
    update_model_use_case_inference_approval,
    update_model_use_case_approval,
    update_provider_origin,
    update_use_case_internal_weight,
)
from .review_workbench import (
    add_review_model,
    apply_model_decisions,
    apply_model_approvals,
    apply_review_decisions,
    build_review_catalog,
    export_review_snapshot,
    import_review_snapshot,
)

ADMIN_TOKEN_ENV_VAR = "LLM_BENCHMARKING_ADMIN_TOKEN"
ADMIN_TOKEN_HEADER = "x-llm-benchmarking-admin-token"
TRUSTED_TAILNET_WRITES_ENV_VAR = "LLM_BENCHMARKING_TRUSTED_TAILNET_WRITES"
TAILSCALE_IPV4_NETWORK = ip_network("100.64.0.0/10")
TAILSCALE_IPV6_NETWORK = ip_network("fd7a:115c:a1e0::/48")
REVIEW_APP_PATH = Path(__file__).resolve().parent / "static" / "review.html"


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _request_client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def _is_trusted_tailnet_client(host: str) -> bool:
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address in TAILSCALE_IPV4_NETWORK or address in TAILSCALE_IPV6_NETWORK


def _trusted_tailnet_write_allowed(request: Request) -> bool:
    return _env_truthy(TRUSTED_TAILNET_WRITES_ENV_VAR) and _is_trusted_tailnet_client(_request_client_host(request))


def require_local_admin(request: Request) -> None:
    if _trusted_tailnet_write_allowed(request):
        return

    expected_token = os.getenv(ADMIN_TOKEN_ENV_VAR, "").strip()
    if not expected_token:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Admin mutations are disabled. Set {ADMIN_TOKEN_ENV_VAR} to enable local write routes, "
                f"or set {TRUSTED_TAILNET_WRITES_ENV_VAR}=1 for trusted Tailscale/loopback clients."
            ),
        )

    provided_token = (
        request.headers.get(ADMIN_TOKEN_HEADER)
        or _bearer_token(request.headers.get("authorization"))
        or ""
    ).strip()
    if not provided_token or not compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


app = FastAPI(title="LLM Benchmarking API", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    bootstrap()


@app.get("/", response_model=list[ModelOut])
def root_model_metadata_list() -> list[dict]:
    return build_model_metadata_list()


@app.get("/review", response_class=HTMLResponse, include_in_schema=False)
def review_workbench_app() -> str:
    return REVIEW_APP_PATH.read_text(encoding="utf-8")


@app.get("/api/benchmarks", response_model=list[BenchmarkOut])
def api_benchmarks() -> list[dict]:
    return list_benchmarks()


@app.get("/api/use-cases", response_model=list[UseCaseOut])
def api_use_cases() -> list[dict]:
    return list_use_cases()


@app.get("/api/models", response_model=list[ModelOut])
def api_models() -> list[dict]:
    return list_models()


@app.get("/api/providers", response_model=list[ProviderOut])
def api_providers() -> list[dict]:
    return list_providers()


@app.get("/api/review/catalog", response_model=dict[str, Any])
def api_review_catalog() -> dict[str, Any]:
    return build_review_catalog()


@app.post("/api/review/decisions", response_model=dict[str, Any], dependencies=[Depends(require_local_admin)])
def api_apply_review_decisions(payload: ReviewDecisionIn) -> dict[str, Any]:
    try:
        return apply_review_decisions(
            model_ids=payload.model_ids,
            use_case_ids=payload.use_case_ids,
            approved_for_use=payload.approved_for_use,
            approval_notes=payload.approval_notes,
            recommendation_status=payload.recommendation_status,
            recommendation_notes=payload.recommendation_notes,
            catalog_status=payload.catalog_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/review/model-approvals", response_model=dict[str, Any], dependencies=[Depends(require_local_admin)])
def api_apply_review_model_approvals(payload: ReviewModelApprovalIn) -> dict[str, Any]:
    try:
        return apply_model_approvals(
            model_ids=payload.model_ids,
            approved_for_use=payload.approved_for_use,
            approval_status=payload.approval_status,
            approval_notes=payload.approval_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/review/model-decisions", response_model=dict[str, Any], dependencies=[Depends(require_local_admin)])
def api_apply_review_model_decisions(payload: ReviewModelDecisionIn) -> dict[str, Any]:
    try:
        return apply_model_decisions(
            model_ids=payload.model_ids,
            approval_status=payload.approval_status,
            approval_notes=payload.approval_notes,
            recommendation_status=payload.recommendation_status,
            recommendation_notes=payload.recommendation_notes,
            reasoning_effort_ceiling=payload.reasoning_effort_ceiling,
            reasoning_effort_ceiling_set="reasoning_effort_ceiling" in payload.model_fields_set,
            restricted_modes=payload.restricted_modes,
            usage_policy_notes=payload.usage_policy_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/review/models", response_model=dict[str, Any], dependencies=[Depends(require_local_admin)])
def api_add_review_model(payload: ReviewModelCreateIn) -> dict[str, Any]:
    try:
        return add_review_model(
            name=payload.name,
            provider=payload.provider,
            model_id=payload.model_id,
            model_type=payload.type,
            model_roles=payload.model_roles,
            catalog_status=payload.catalog_status,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/review/snapshots/export", response_model=dict[str, Any], dependencies=[Depends(require_local_admin)])
def api_export_review_snapshot() -> dict[str, Any]:
    return export_review_snapshot()


@app.post("/api/review/snapshots/import", response_model=dict[str, Any], dependencies=[Depends(require_local_admin)])
def api_import_review_snapshot(payload: ReviewSnapshotIn) -> dict[str, Any]:
    try:
        return import_review_snapshot(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/providers/{provider_id}", response_model=ProviderOut, dependencies=[Depends(require_local_admin)])
def api_update_provider(provider_id: str, payload: ProviderUpdateIn) -> dict:
    try:
        provider = update_provider_origin(provider_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@app.patch("/api/models/{model_id}/approval", response_model=ModelSummaryOut, dependencies=[Depends(require_local_admin)])
def api_update_model_approval(model_id: str, payload: ModelApprovalUpdateIn) -> dict:
    model = update_model_approval(model_id, payload.approved_for_use, payload.approval_notes)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@app.patch(
    "/api/models/{model_id}/approvals/{use_case_id}",
    response_model=ModelSummaryOut,
    dependencies=[Depends(require_local_admin)],
)
def api_update_model_use_case_approval(model_id: str, use_case_id: str, payload: UseCaseApprovalIn) -> dict:
    try:
        model = update_model_use_case_approval(
            model_id,
            use_case_id,
            payload.approved_for_use,
            payload.approval_notes,
            payload.recommendation_status,
            payload.recommendation_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@app.put(
    "/api/models/{model_id}/approvals/{use_case_id}/inference-route",
    response_model=ModelSummaryOut,
    dependencies=[Depends(require_local_admin)],
)
def api_update_model_use_case_inference_approval(model_id: str, use_case_id: str, payload: InferenceRouteApprovalIn) -> dict:
    try:
        model = update_model_use_case_inference_approval(
            model_id,
            use_case_id,
            payload.destination_id,
            payload.location_label,
            payload.approved_for_use,
            payload.approval_notes,
            location_key=payload.location_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@app.put("/api/models/{model_id}/curation/identity", response_model=ModelSummaryOut, dependencies=[Depends(require_local_admin)])
def api_curate_model_identity(model_id: str, payload: ModelIdentityCurationIn) -> dict:
    try:
        model = curate_model_identity(
            model_id,
            payload.target_model_id,
            variant_label=payload.variant_label,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@app.put("/api/models/{model_id}/curation/duplicate", response_model=ModelSummaryOut, dependencies=[Depends(require_local_admin)])
def api_merge_model_duplicate(model_id: str, payload: ModelDuplicateCurationIn) -> dict:
    try:
        model = merge_model_duplicate(
            model_id,
            payload.target_model_id,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@app.post(
    "/api/models/approvals/{use_case_id}/inference-route/bulk",
    response_model=InferenceRouteApprovalBulkOut,
    dependencies=[Depends(require_local_admin)],
)
def api_apply_model_use_case_inference_approval_bulk(use_case_id: str, payload: InferenceRouteApprovalBulkIn) -> dict:
    try:
        return apply_model_inference_route_approval_bulk(
            payload.model_ids,
            use_case_id,
            payload.destination_id,
            payload.location_label,
            payload.approved_for_use,
            payload.approval_notes,
            location_key=payload.location_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/model-families/{family_id}/approvals/{use_case_id}/apply-delta",
    response_model=FamilyApprovalDeltaOut,
    dependencies=[Depends(require_local_admin)],
)
def api_apply_model_family_approval_delta(family_id: str, use_case_id: str, payload: FamilyApprovalDeltaIn | None = None) -> dict:
    try:
        result = apply_model_family_approval_delta(
            family_id,
            use_case_id,
            payload.approval_notes if payload is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Model family not found")
    return result


@app.post(
    "/api/model-families/{family_id}/approvals/bulk",
    response_model=FamilyApprovalBulkOut,
    dependencies=[Depends(require_local_admin)],
)
def api_apply_model_family_approval_bulk(family_id: str, payload: FamilyApprovalBulkIn) -> dict:
    try:
        result = apply_model_family_approval_bulk(
            family_id,
            payload.use_case_ids,
            payload.approval_notes,
            scope=payload.scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Model family not found")
    return result


@app.patch("/api/use-cases/{use_case_id}/internal-weight", response_model=UseCaseOut, dependencies=[Depends(require_local_admin)])
def api_update_use_case_internal_weight(use_case_id: str, payload: BenchmarkWeightUpdateIn) -> dict:
    use_case = update_use_case_internal_weight(use_case_id, payload.weight)
    if use_case is None:
        raise HTTPException(status_code=404, detail="Use case not found")
    return use_case


@app.put(
    "/api/models/{model_id}/benchmarks/{benchmark_id}/manual-score",
    response_model=ManualScoreResultOut,
    dependencies=[Depends(require_local_admin)],
)
def api_update_manual_score(model_id: str, benchmark_id: str, payload: ManualScoreUpdateIn) -> dict:
    try:
        result = update_manual_benchmark_score(
            model_id,
            benchmark_id,
            value=payload.value,
            raw_value=payload.raw_value,
            notes=payload.notes,
            source_url=payload.source_url,
            verified=payload.verified,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=404, detail="Model or benchmark not found")
    return result


@app.post("/api/update", response_model=UpdateStartOut, dependencies=[Depends(require_local_admin)])
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


@app.get("/api/market-snapshots", response_model=list[MarketSnapshotOut])
def api_market_snapshots(scope: str | None = None, category: str | None = None, limit: int = 300) -> list[dict]:
    return list_market_snapshots(scope=scope, category_slug=category, limit=limit)


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
