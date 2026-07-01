"""Governed recommendation proposal engine for model/use-case suitability."""

from __future__ import annotations

from collections import Counter
import json
from typing import Any, Iterable

from sqlalchemy import delete
from sqlalchemy.engine import Engine

from . import ranking_views
from .database import (
    get_connection,
    init_db,
    model_use_case_recommendation_proposals as recommendation_proposals_table,
    utc_now_iso,
)
from .seed_data import INTERNAL_VIEW_BENCHMARK_ID, USE_CASES

PROFILE_AUSTRALIAN_BANK = "australian_bank"
POLICY_VERSION_AUSTRALIAN_BANK = "australian-bank-v1"
SUPPORTED_PROFILES = {PROFILE_AUSTRALIAN_BANK}

STATUS_UNRATED = "unrated"
STATUS_RECOMMENDED = "recommended"
STATUS_NOT_RECOMMENDED = "not_recommended"
STATUS_DISCOURAGED = "discouraged"

VALID_STATUSES = {
    STATUS_UNRATED,
    STATUS_RECOMMENDED,
    STATUS_NOT_RECOMMENDED,
    STATUS_DISCOURAGED,
}

PROFILE_SUMMARIES: dict[str, dict[str, Any]] = {
    PROFILE_AUSTRALIAN_BANK: {
        "label": "Australian bank",
        "policy_version": POLICY_VERSION_AUSTRALIAN_BANK,
        "governance_context": [
            "APRA CPS 230 operational risk and service-provider governance",
            "APRA CPS 234 information security capability",
            "Privacy Act and OAIC commercial AI privacy guidance for personal information",
            "ASIC AI governance, fairness, bias, and disclosure expectations",
        ],
    },
}

DEFAULT_POLICY: dict[str, Any] = {
    "risk_tier": "standard",
    "min_score": 55.0,
    "min_confidence": 0.50,
    "production_commercial": False,
    "customer_visible": False,
    "uses_personal_information": False,
    "system_actions": False,
    "requires_tracked_catalog": False,
    "requires_model_card": False,
    "requires_approved_route": False,
    "requires_australian_route": False,
    "required_controls": [
        "Record model owner, approved use case, and review date before production use.",
        "Monitor benchmark evidence and recommendation drift after catalog refreshes.",
    ],
}

ENTERPRISE_POLICY: dict[str, Any] = {
    **DEFAULT_POLICY,
    "risk_tier": "enterprise",
    "min_score": 60.0,
    "min_confidence": 0.55,
    "production_commercial": True,
    "requires_tracked_catalog": True,
    "requires_model_card": True,
    "requires_approved_route": True,
    "required_controls": [
        "Assign accountable model owner and production use-case owner.",
        "Complete vendor, legal, privacy, security, and operational-risk review.",
        "Record approved inference destination and data-location constraints.",
        "Define fallback, monitoring, incident, and periodic recertification controls.",
    ],
}

USE_CASE_POLICY_OVERRIDES: dict[str, dict[str, Any]] = {
    "customer_support": {
        "risk_tier": "customer_facing",
        "min_score": 65.0,
        "min_confidence": 0.60,
        "customer_visible": True,
        "uses_personal_information": True,
        "requires_australian_route": True,
        "required_controls": [
            "Complete privacy impact assessment before customer or personal information use.",
            "Approve human escalation, disclosure, harmful-output, and complaint handling controls.",
            "Record CPS 230 service-provider and critical-operation owner sign-off if support is material.",
            "Record CPS 234 security control review for the approved route.",
        ],
    },
    "document_operations": {
        "risk_tier": "sensitive_documents",
        "min_score": 63.0,
        "min_confidence": 0.60,
        "uses_personal_information": True,
        "requires_australian_route": True,
        "required_controls": [
            "Complete privacy impact assessment before processing customer or staff documents.",
            "Define document retention, redaction, access logging, and human-review controls.",
            "Record CPS 234 security control review for the approved document-processing route.",
        ],
    },
    "knowledge_work_rag_sorting": {
        "risk_tier": "sensitive_knowledge",
        "min_score": 62.0,
        "min_confidence": 0.60,
        "uses_personal_information": True,
        "requires_australian_route": True,
        "required_controls": [
            "Approve retrieval corpus classification and personal-information handling controls.",
            "Define groundedness, citation, and human-review controls for regulated advice contexts.",
            "Record CPS 234 security control review for the approved RAG route.",
        ],
    },
    "governed_enterprise_rollout": {
        "risk_tier": "governance",
        "min_score": 62.0,
        "min_confidence": 0.60,
        "required_controls": [
            "Complete model-risk, vendor-risk, privacy, legal, and security review before rollout.",
            "Record operational-risk owner acceptance and periodic recertification cadence.",
            "Document usage constraints, fallback path, monitoring, and incident-response ownership.",
        ],
    },
    "enterprise_automation": {
        "risk_tier": "business_process",
        "min_score": 62.0,
        "min_confidence": 0.58,
        "system_actions": True,
        "required_controls": [
            "Define approval gates for actions that update records, move money, or affect customers.",
            "Record CPS 230 operational-risk owner sign-off for material business-process automation.",
            "Implement audit logging, rollback, rate limits, and human override controls.",
        ],
    },
    "workflow_automation": {
        "risk_tier": "business_process",
        "min_score": 62.0,
        "min_confidence": 0.58,
        "system_actions": True,
        "required_controls": [
            "Define approval gates for business-system actions and queue disposition changes.",
            "Implement audit logging, rollback, rate limits, and human override controls.",
            "Record operational-risk review for material workflows.",
        ],
    },
    "developer_platform_agent": {
        "risk_tier": "internal_engineering",
        "min_score": 63.0,
        "min_confidence": 0.58,
        "system_actions": True,
        "requires_australian_route": False,
        "required_controls": [
            "Approve source-code, secrets, and CI/CD data handling controls before production use.",
            "Require change-review gates for write-capable engineering agents.",
            "Record route, logging, rollback, and incident-response ownership.",
        ],
    },
    "agentic": {
        "risk_tier": "tool_use",
        "min_score": 62.0,
        "min_confidence": 0.55,
        "system_actions": True,
        "requires_model_card": True,
        "required_controls": [
            "Constrain available tools, permissions, data scopes, and write actions per use case.",
            "Require approval gates for customer, financial, privileged, or destructive actions.",
            "Record audit logging, fallback, and incident-response ownership.",
        ],
    },
}


def build_recommendation_audit(
    *,
    profile_id: str = PROFILE_AUSTRALIAN_BANK,
    use_case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build recommendation proposals from the current serialized catalog."""
    from . import update_engine

    profile_id = _validate_profile_id(profile_id)
    models = update_engine.list_models(include_recommendation_proposals=False)
    benchmarks = {row["id"]: row for row in update_engine.list_benchmarks()}
    return build_recommendation_proposals(
        models=models,
        benchmarks=benchmarks,
        use_cases=USE_CASES,
        profile_id=profile_id,
        use_case_ids=use_case_ids,
    )


def build_recommendation_proposals(
    *,
    models: list[dict[str, Any]],
    benchmarks: dict[str, dict[str, Any]],
    use_cases: list[dict[str, Any]],
    profile_id: str = PROFILE_AUSTRALIAN_BANK,
    use_case_ids: Iterable[str] | None = None,
    computed_at: str | None = None,
) -> dict[str, Any]:
    profile_id = _validate_profile_id(profile_id)
    computed_at = computed_at or utc_now_iso()
    selected_use_case_ids = _normalize_use_case_ids(use_case_ids)
    selected_use_cases = [
        use_case
        for use_case in use_cases
        if not selected_use_case_ids or str(use_case.get("id") or "") in selected_use_case_ids
    ]
    rankings_by_use_case = {
        str(use_case["id"]): _rankings_by_model_id(models, benchmarks, use_case)
        for use_case in selected_use_cases
    }

    proposals: list[dict[str, Any]] = []
    for model in models:
        for use_case in selected_use_cases:
            use_case_id = str(use_case["id"])
            proposals.append(
                _evaluate_model_use_case(
                    model=model,
                    use_case=use_case,
                    ranking=rankings_by_use_case.get(use_case_id, {}).get(str(model.get("id") or "")),
                    profile_id=profile_id,
                    computed_at=computed_at,
                )
            )

    status_counts = Counter(str(proposal["proposed_status"]) for proposal in proposals)
    blocker_counts = Counter(
        blocker
        for proposal in proposals
        for blocker in proposal.get("blockers", [])
    )
    use_case_counts: dict[str, dict[str, int]] = {}
    for proposal in proposals:
        use_case_counts.setdefault(str(proposal["use_case_id"]), Counter())
        use_case_counts[str(proposal["use_case_id"])][str(proposal["proposed_status"])] += 1

    return {
        "profile_id": profile_id,
        "profile": PROFILE_SUMMARIES.get(profile_id, {"label": profile_id}),
        "policy_version": _policy_version(profile_id),
        "computed_at": computed_at,
        "model_count": len(models),
        "use_case_count": len(selected_use_cases),
        "proposal_count": len(proposals),
        "status_counts": dict(sorted(status_counts.items())),
        "blocker_counts": dict(blocker_counts.most_common()),
        "use_case_counts": {
            use_case_id: dict(sorted(counts.items()))
            for use_case_id, counts in sorted(use_case_counts.items())
        },
        "proposals": proposals,
    }


def sync_recommendation_proposals(
    *,
    profile_id: str = PROFILE_AUSTRALIAN_BANK,
    use_case_ids: Iterable[str] | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Regenerate and persist recommendation proposals for the current catalog."""
    from . import update_engine

    profile_id = _validate_profile_id(profile_id)
    active_engine = engine or update_engine.ENGINE
    init_db(active_engine)
    audit = build_recommendation_audit(profile_id=profile_id, use_case_ids=use_case_ids)
    selected_use_case_ids = _normalize_use_case_ids(use_case_ids)
    rows = [_proposal_db_row(proposal) for proposal in audit["proposals"]]

    with get_connection(active_engine) as conn:
        delete_statement = delete(recommendation_proposals_table).where(
            recommendation_proposals_table.c.profile_id == profile_id
        )
        if selected_use_case_ids:
            delete_statement = delete_statement.where(
                recommendation_proposals_table.c.use_case_id.in_(sorted(selected_use_case_ids))
            )
        conn.execute(delete_statement)
        if rows:
            conn.execute(recommendation_proposals_table.insert(), rows)

    return {
        **{key: value for key, value in audit.items() if key != "proposals"},
        "stored_count": len(rows),
    }


def format_recommendation_audit_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"Recommendation audit: {summary.get('profile_id')} ({summary.get('policy_version')})",
        f"Computed at: {summary.get('computed_at')}",
        (
            f"Models: {summary.get('model_count', 0)}; "
            f"use cases: {summary.get('use_case_count', 0)}; "
            f"proposals: {summary.get('proposal_count', 0)}"
        ),
        "Status counts:",
    ]
    status_counts = summary.get("status_counts") or {}
    for status in (STATUS_RECOMMENDED, STATUS_DISCOURAGED, STATUS_NOT_RECOMMENDED, STATUS_UNRATED):
        lines.append(f"- {status}: {int(status_counts.get(status, 0))}")

    blocker_counts = summary.get("blocker_counts") or {}
    if blocker_counts:
        lines.append("Top blockers:")
        for blocker, count in list(blocker_counts.items())[:8]:
            lines.append(f"- {count}: {blocker}")

    return "\n".join(lines) + "\n"


def _evaluate_model_use_case(
    *,
    model: dict[str, Any],
    use_case: dict[str, Any],
    ranking: dict[str, Any] | None,
    profile_id: str,
    computed_at: str,
) -> dict[str, Any]:
    use_case_id = str(use_case["id"])
    policy = _policy_for_use_case(use_case)
    approval = (model.get("use_case_approvals") or {}).get(use_case_id, {})
    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []
    required_controls = _clean_sequence(policy.get("required_controls"))

    _append_policy_blockers(model, approval, policy, blockers, warnings)
    _append_catalog_blockers(model, policy, blockers, warnings)
    _append_metadata_gates(model, policy, blockers, warnings)
    _append_route_gates(approval, policy, blockers, warnings)

    score = float(ranking["score"]) if ranking is not None and ranking.get("score") is not None else None
    confidence = float(ranking["coverage"]) if ranking is not None and ranking.get("coverage") is not None else None
    min_score = float(policy.get("min_score", DEFAULT_POLICY["min_score"]))
    min_confidence = float(policy.get("min_confidence", DEFAULT_POLICY["min_confidence"]))

    if ranking is None:
        warnings.append(
            "evidence: Insufficient benchmark coverage for this use case; do not rely on this model without manual review."
        )
    else:
        reasons.append(f"benchmark: Use-case score {score:.1f} with evidence confidence {confidence:.2f}.")
        if score < min_score:
            warnings.append(f"benchmark: Score {score:.1f} is below the {min_score:.1f} profile threshold.")
        if confidence < min_confidence:
            warnings.append(
                f"evidence: Confidence {confidence:.2f} is below the {min_confidence:.2f} profile threshold."
            )

    proposed_status = _proposed_status(
        blockers=blockers,
        ranking=ranking,
        score=score,
        confidence=confidence,
        min_score=min_score,
        min_confidence=min_confidence,
    )
    if proposed_status == STATUS_RECOMMENDED:
        reasons.append("policy: No hard governance blockers were found for this profile.")
    elif proposed_status == STATUS_NOT_RECOMMENDED:
        reasons.append("policy: One or more hard governance blockers apply.")
    else:
        reasons.append("policy: No hard blocker was found, but the evidence does not meet recommendation thresholds.")

    return {
        "profile_id": profile_id,
        "model_id": str(model.get("id") or ""),
        "model_name": str(model.get("name") or ""),
        "provider": str(model.get("provider") or ""),
        "use_case_id": use_case_id,
        "use_case_label": str(use_case.get("label") or use_case_id),
        "proposed_status": proposed_status,
        "score": round(score, 4) if score is not None else None,
        "confidence": round(confidence, 4) if confidence is not None else None,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "reasons": _dedupe(reasons),
        "required_controls": _dedupe(required_controls),
        "policy_version": _policy_version(profile_id),
        "computed_at": computed_at,
        "source_profile": {
            "profile": PROFILE_SUMMARIES.get(profile_id, {"label": profile_id}),
            "policy": policy,
        },
    }


def _append_policy_blockers(
    model: dict[str, Any],
    approval: dict[str, Any],
    policy: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> None:
    production = bool(policy.get("production_commercial"))
    if str(approval.get("auto_recommendation_status") or "") == STATUS_NOT_RECOMMENDED:
        blockers.append(
            "policy-overlay: Existing license or provenance policy marks this production use case not recommended."
        )
    if production and model.get("license_policy_class") == "commercial_blocked":
        blockers.append("license: License policy blocks commercial production use.")
    elif model.get("license_policy_class") == "potential_legal_review":
        warnings.append("license: License metadata needs legal review before production use.")

    if production and model.get("provenance_policy_class") == "derivative_unverified":
        blockers.append("provenance: Derivative provenance is unverified for production use.")
    elif model.get("provenance_policy_class") == "derivative_review":
        warnings.append("provenance: Derivative provenance needs review before production use.")


def _append_catalog_blockers(
    model: dict[str, Any],
    policy: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> None:
    catalog_status = str(model.get("catalog_status") or "tracked")
    if catalog_status == "tracked":
        return
    message = f"catalog: Catalog status is {catalog_status}; newly discovered models need curation before governed use."
    if policy.get("requires_tracked_catalog"):
        blockers.append(message)
    else:
        warnings.append(message)


def _append_metadata_gates(
    model: dict[str, Any],
    policy: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> None:
    if policy.get("requires_model_card") and not model.get("model_card_url"):
        blockers.append("metadata: Model card URL is missing for this governed use case.")
    elif not model.get("model_card_url"):
        warnings.append("metadata: Model card URL is missing.")

    if policy.get("requires_model_card") and model.get("model_card_url") and not model.get("model_card_verified_at"):
        warnings.append("metadata: Model card exists but has not been verified locally.")

    if policy.get("uses_personal_information") and not model.get("provider_origin_countries"):
        warnings.append("vendor: Provider origin countries are missing for privacy and vendor-risk review.")

    provenance_gap_fields = list(model.get("provenance_gap_fields") or [])
    if policy.get("uses_personal_information") and "training_data_summary" in provenance_gap_fields:
        warnings.append("provenance: Training-data summary is missing for a personal-information use case.")


def _append_route_gates(
    approval: dict[str, Any],
    policy: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> None:
    if not policy.get("requires_approved_route"):
        return

    approved_routes = [
        route
        for route in (approval.get("inference_route_approvals") or [])
        if route.get("approved_for_use")
    ]
    if not approved_routes:
        blockers.append("routing: No bank-approved inference route is recorded for this use case.")
        return

    if policy.get("requires_australian_route") and not any(_route_is_australian(route) for route in approved_routes):
        blockers.append("routing: No bank-approved Australian inference route is recorded for this use case.")
    elif not any(_route_is_australian(route) for route in approved_routes):
        warnings.append("routing: Approved route is not marked as Australian hosted.")


def _route_is_australian(route: dict[str, Any]) -> bool:
    fields = [
        str(route.get("location_key") or ""),
        str(route.get("location_label") or ""),
    ]
    return any("australia" in field.lower() or field.lower() == "au" for field in fields)


def _proposed_status(
    *,
    blockers: list[str],
    ranking: dict[str, Any] | None,
    score: float | None,
    confidence: float | None,
    min_score: float,
    min_confidence: float,
) -> str:
    if blockers:
        return STATUS_NOT_RECOMMENDED
    if ranking is None or score is None or confidence is None:
        return STATUS_DISCOURAGED
    if score < min_score or confidence < min_confidence:
        return STATUS_DISCOURAGED
    return STATUS_RECOMMENDED


def _rankings_by_model_id(
    models: list[dict[str, Any]],
    benchmarks: dict[str, dict[str, Any]],
    use_case: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    weights = dict(use_case["weights"])
    total_configured_weight = sum(weights.values())
    coverage_exempt_benchmark_ids = {INTERNAL_VIEW_BENCHMARK_ID}
    total_coverage_weight = sum(
        weight
        for benchmark_id, weight in weights.items()
        if benchmark_id not in coverage_exempt_benchmark_ids
    )
    ranges = ranking_views.benchmark_ranges(models, weights)
    rankings: dict[str, dict[str, Any]] = {}
    for model in models:
        ranking = ranking_views.build_model_ranking(
            model=model,
            benchmarks=benchmarks,
            weights=weights,
            required_benchmarks=list(use_case.get("required_benchmarks", [])),
            ranges=ranges,
            total_configured_weight=total_configured_weight,
            total_coverage_weight=total_coverage_weight,
            use_case_min_coverage=float(use_case.get("min_coverage", 0.5)),
            coverage_exempt_benchmark_ids=coverage_exempt_benchmark_ids,
            model_summary=lambda item: {"id": item.get("id"), "name": item.get("name")},
        )
        if ranking is not None:
            rankings[str(model.get("id") or "")] = ranking
    return rankings


def _policy_for_use_case(use_case: dict[str, Any]) -> dict[str, Any]:
    base = ENTERPRISE_POLICY if str(use_case.get("segment") or "") == "enterprise" else DEFAULT_POLICY
    override = USE_CASE_POLICY_OVERRIDES.get(str(use_case.get("id") or ""), {})
    return {
        **base,
        **override,
        "use_case_id": str(use_case.get("id") or ""),
        "use_case_label": str(use_case.get("label") or use_case.get("id") or ""),
        "use_case_segment": str(use_case.get("segment") or "core"),
    }


def _policy_version(profile_id: str) -> str:
    if profile_id == PROFILE_AUSTRALIAN_BANK:
        return POLICY_VERSION_AUSTRALIAN_BANK
    raise ValueError(f"Unsupported recommendation profile: {profile_id}")


def _validate_profile_id(profile_id: str) -> str:
    normalized = str(profile_id or "").strip()
    if normalized not in SUPPORTED_PROFILES:
        raise ValueError(f"Unsupported recommendation profile: {profile_id}")
    return normalized


def _proposal_db_row(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": proposal["profile_id"],
        "model_id": proposal["model_id"],
        "use_case_id": proposal["use_case_id"],
        "proposed_status": proposal["proposed_status"],
        "score": proposal.get("score"),
        "confidence": proposal.get("confidence"),
        "blockers_json": json.dumps(_clean_sequence(proposal.get("blockers")), sort_keys=True),
        "warnings_json": json.dumps(_clean_sequence(proposal.get("warnings")), sort_keys=True),
        "reasons_json": json.dumps(_clean_sequence(proposal.get("reasons")), sort_keys=True),
        "required_controls_json": json.dumps(_clean_sequence(proposal.get("required_controls")), sort_keys=True),
        "policy_version": proposal["policy_version"],
        "computed_at": proposal["computed_at"],
        "source_profile_json": json.dumps(proposal.get("source_profile") or {}, sort_keys=True),
    }


def _normalize_use_case_ids(use_case_ids: Iterable[str] | None) -> set[str]:
    return {str(use_case_id).strip() for use_case_id in (use_case_ids or []) if str(use_case_id).strip()}


def _clean_sequence(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


__all__ = [
    "POLICY_VERSION_AUSTRALIAN_BANK",
    "PROFILE_AUSTRALIAN_BANK",
    "SUPPORTED_PROFILES",
    "build_recommendation_audit",
    "build_recommendation_proposals",
    "format_recommendation_audit_summary",
    "sync_recommendation_proposals",
]
