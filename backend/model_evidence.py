"""Selection-evidence helpers for review exports."""

from __future__ import annotations

from typing import Any, Iterable

from . import ranking_views

EVIDENCE_FIELDS = [
    "model_type_primary",
    "model_type_tags",
    "evidence_context_use_case_id",
    "evidence_context_use_case_label",
    "strongest_signal_kind",
    "strongest_signal_label",
    "strongest_signal_value",
    "strongest_signal_source_url",
    "strongest_signal_notes",
    "ranking_rank",
    "ranking_score",
    "ranking_coverage",
    "cost_signal",
    "speed_signal",
    "hyperscaler_signal",
    "inference_location_signal",
]

AUSTRALIA_REGION_MARKERS = ("ap-southeast-2", "australia")


def enrich_models_with_selection_evidence(
    models: list[dict[str, Any]],
    *,
    use_cases: list[dict[str, Any]],
    benchmarks: list[dict[str, Any]],
) -> None:
    """Attach default and use-case-specific selection evidence to review models."""
    benchmarks_by_id = {str(benchmark.get("id")): benchmark for benchmark in benchmarks}
    use_cases_by_id = {str(use_case.get("id")): use_case for use_case in use_cases}
    ranking_evidence = _build_ranking_evidence_by_use_case(
        models=models,
        use_cases=use_cases,
        benchmarks_by_id=benchmarks_by_id,
    )

    for model in models:
        model.update(_model_type_payload(model))
        context_evidence = _context_evidence_for_model(
            model,
            use_cases_by_id=use_cases_by_id,
            ranking_evidence=ranking_evidence,
        )
        default_evidence = _default_evidence_for_model(
            model,
            use_cases_by_id=use_cases_by_id,
            context_evidence=context_evidence,
        )
        model.update(default_evidence)
        if context_evidence:
            model["selection_evidence_by_use_case"] = context_evidence


def _build_ranking_evidence_by_use_case(
    *,
    models: list[dict[str, Any]],
    use_cases: list[dict[str, Any]],
    benchmarks_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    ranking_evidence: dict[str, dict[str, dict[str, Any]]] = {}
    models_by_id = {str(model.get("id") or ""): model for model in models}
    for use_case in use_cases:
        use_case_id = str(use_case.get("id") or "")
        if not use_case_id:
            continue
        rankings = ranking_views.build_rankings_response(
            use_case=use_case,
            models=models,
            benchmarks=benchmarks_by_id,
            model_summary=_model_summary,
            min_ranking_coverage=float(use_case.get("min_coverage", 0.5)),
            coverage_exempt_benchmark_ids=(),
        )
        rows_by_model_id: dict[str, dict[str, Any]] = {}
        for row in rankings.get("rankings", []):
            model_id = str((row.get("model") or {}).get("id") or "")
            model = models_by_id.get(model_id)
            if not model:
                continue
            rows_by_model_id[model_id] = _ranking_evidence(
                model,
                row,
                use_case=use_case,
                benchmarks_by_id=benchmarks_by_id,
            )
        if rows_by_model_id:
            ranking_evidence[use_case_id] = rows_by_model_id
    return ranking_evidence


def _context_evidence_for_model(
    model: dict[str, Any],
    *,
    use_cases_by_id: dict[str, dict[str, Any]],
    ranking_evidence: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    model_id = str(model.get("id") or "")
    payload: dict[str, dict[str, Any]] = {}
    for use_case_id, rows_by_model_id in ranking_evidence.items():
        evidence = rows_by_model_id.get(model_id)
        if evidence:
            payload[use_case_id] = evidence

    approvals = model.get("use_case_approvals") if isinstance(model.get("use_case_approvals"), dict) else {}
    for use_case_id, approval in approvals.items():
        if use_case_id in payload:
            continue
        use_case = use_cases_by_id.get(str(use_case_id), {"id": use_case_id, "label": str(use_case_id)})
        route_evidence = _approved_route_evidence(model, use_case=use_case)
        if route_evidence:
            payload[str(use_case_id)] = route_evidence

    return payload


def _default_evidence_for_model(
    model: dict[str, Any],
    *,
    use_cases_by_id: dict[str, dict[str, Any]],
    context_evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    default_context_ids = list(_default_context_ids(model))
    for use_case_id in default_context_ids:
        evidence = context_evidence.get(use_case_id)
        if evidence:
            return evidence
    if not default_context_ids and context_evidence:
        return next(iter(context_evidence.values()))

    default_context_id = next(iter(default_context_ids), "")
    default_use_case = use_cases_by_id.get(default_context_id, {"id": default_context_id, "label": ""})
    return _fallback_evidence(model, use_case=default_use_case)


def _ranking_evidence(
    model: dict[str, Any],
    ranking: dict[str, Any],
    *,
    use_case: dict[str, Any],
    benchmarks_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    strongest = _strongest_breakdown_item(ranking.get("breakdown") or [])
    use_case_id = str(use_case.get("id") or "")
    use_case_label = str(use_case.get("label") or use_case_id)
    cost_signal = _score_signal(model, ("aa_cost", "aa_ifbench_cost"), "Cost")
    speed_signal = _score_signal(model, ("aa_speed", "aa_ifbench_time"), "Speed")

    if strongest is None:
        return {
            **_base_evidence(model, use_case=use_case),
            "strongest_signal_kind": "ranking",
            "strongest_signal_label": f"{use_case_label} ranking",
            "strongest_signal_value": _round_float(ranking.get("score")),
            "strongest_signal_source_url": None,
            "strongest_signal_notes": f"Rank #{ranking.get('rank')} with coverage {_format_float(ranking.get('coverage'))}.",
            "ranking_rank": ranking.get("rank"),
            "ranking_score": _round_float(ranking.get("score")),
            "ranking_coverage": _round_float(ranking.get("coverage")),
            "cost_signal": cost_signal,
            "speed_signal": speed_signal,
        }

    benchmark_id = str(strongest.get("benchmark_id") or "")
    benchmark = benchmarks_by_id.get(benchmark_id, {})
    score = (model.get("scores") or {}).get(benchmark_id) or {}
    contribution = float(strongest.get("normalised") or 0.0) * float(strongest.get("weight") or 0.0)
    benchmark_label = str(benchmark.get("short") or benchmark.get("name") or benchmark_id)
    benchmark_note = str((use_case.get("benchmark_notes") or {}).get(benchmark_id) or strongest.get("notes") or "").strip()
    notes_parts = [
        f"Rank #{ranking.get('rank')} for {use_case_label}",
        f"weighted contribution {_format_float(contribution)}",
        f"coverage {_format_float(ranking.get('coverage'))}",
    ]
    if benchmark_note:
        notes_parts.append(benchmark_note)
    return {
        **_base_evidence(model, use_case=use_case),
        "strongest_signal_kind": "benchmark",
        "strongest_signal_label": benchmark_label,
        "strongest_signal_value": strongest.get("raw_value"),
        "strongest_signal_source_url": score.get("source_url") or benchmark.get("url"),
        "strongest_signal_notes": "; ".join(notes_parts) + ".",
        "ranking_rank": ranking.get("rank"),
        "ranking_score": _round_float(ranking.get("score")),
        "ranking_coverage": _round_float(ranking.get("coverage")),
        "cost_signal": cost_signal,
        "speed_signal": speed_signal,
    }


def _fallback_evidence(model: dict[str, Any], *, use_case: dict[str, Any]) -> dict[str, Any]:
    route_evidence = _approved_route_evidence(model, use_case=use_case)
    if route_evidence:
        return route_evidence

    australia_destination = _australia_destination(model)
    if australia_destination:
        return {
            **_base_evidence(model, use_case=use_case),
            "strongest_signal_kind": "inference_location",
            "strongest_signal_label": "Australia inference route",
            "strongest_signal_value": _destination_name(australia_destination),
            "strongest_signal_source_url": _first_destination_source_url(australia_destination),
            "strongest_signal_notes": _destination_region_note(australia_destination, prefix="Australia route includes"),
        }

    destination = _first_inference_destination(model)
    if destination:
        return {
            **_base_evidence(model, use_case=use_case),
            "strongest_signal_kind": "hyperscaler",
            "strongest_signal_label": "Hyperscaler availability",
            "strongest_signal_value": _destination_name(destination),
            "strongest_signal_source_url": _first_destination_source_url(destination),
            "strongest_signal_notes": _destination_region_note(destination, prefix="Known hyperscaler route includes"),
        }

    if _is_local_sml(model):
        return {
            **_base_evidence(model, use_case=use_case),
            "strongest_signal_kind": "local_sml",
            "strongest_signal_label": "Open-weight small-model candidate",
            "strongest_signal_value": _model_size_value(model),
            "strongest_signal_source_url": model.get("model_size_source_url") or model.get("repo_url") or model.get("model_card_url"),
            "strongest_signal_notes": "Open-weight model marked as a small-model candidate for local or self-hosted routing review.",
        }

    documentation_url = model.get("model_card_url") or model.get("documentation_url") or model.get("repo_url")
    if documentation_url:
        return {
            **_base_evidence(model, use_case=use_case),
            "strongest_signal_kind": "model_metadata",
            "strongest_signal_label": "Model card / documentation",
            "strongest_signal_value": model.get("metadata_source_name") or model.get("model_card_source") or "available",
            "strongest_signal_source_url": documentation_url,
            "strongest_signal_notes": "Provider or repository documentation is available, but no stronger benchmark, route, or local-SML signal was selected.",
        }

    return {
        **_base_evidence(model, use_case=use_case),
        "strongest_signal_kind": "insufficient_evidence",
        "strongest_signal_label": "Insufficient evidence",
        "strongest_signal_value": None,
        "strongest_signal_source_url": None,
        "strongest_signal_notes": "No ranking, approved route, hyperscaler/location, local-SML, or model-card evidence is available.",
    }


def _approved_route_evidence(model: dict[str, Any], *, use_case: dict[str, Any]) -> dict[str, Any] | None:
    use_case_id = str(use_case.get("id") or "")
    approvals = model.get("use_case_approvals") if isinstance(model.get("use_case_approvals"), dict) else {}
    preferred_approvals = []
    if use_case_id and isinstance(approvals.get(use_case_id), dict):
        preferred_approvals.append(approvals[use_case_id])
    preferred_approvals.extend(
        approval
        for key, approval in approvals.items()
        if key != use_case_id and isinstance(approval, dict)
    )
    for approval in preferred_approvals:
        for route in approval.get("inference_route_approvals") or []:
            if not isinstance(route, dict) or not route.get("approved_for_use"):
                continue
            destination = str(route.get("destination_name") or route.get("destination_id") or "Inference route")
            location = str(route.get("location_label") or route.get("location_key") or "").strip()
            label = f"Approved route: {destination}"
            if location:
                label = f"{label} ({location})"
            notes = str(route.get("approval_notes") or "").strip() or "Bank-approved inference route is recorded for this model/use case."
            return {
                **_base_evidence(model, use_case=use_case),
                "strongest_signal_kind": "approved_inference_route",
                "strongest_signal_label": label,
                "strongest_signal_value": "approved",
                "strongest_signal_source_url": None,
                "strongest_signal_notes": notes,
            }
    return None


def _base_evidence(model: dict[str, Any], *, use_case: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_context_use_case_id": use_case.get("id") or "",
        "evidence_context_use_case_label": use_case.get("label") or "",
        "strongest_signal_kind": None,
        "strongest_signal_label": None,
        "strongest_signal_value": None,
        "strongest_signal_source_url": None,
        "strongest_signal_notes": None,
        "ranking_rank": None,
        "ranking_score": None,
        "ranking_coverage": None,
        "cost_signal": _score_signal(model, ("aa_cost", "aa_ifbench_cost", "aa_tts_price_per_1m_chars"), "Cost"),
        "speed_signal": _score_signal(model, ("aa_speed", "aa_ifbench_time", "aa_tts_generation_time"), "Speed"),
        "hyperscaler_signal": _hyperscaler_signal(model),
        "inference_location_signal": _inference_location_signal(model),
    }


def _model_type_payload(model: dict[str, Any]) -> dict[str, Any]:
    roles = [str(role) for role in model.get("model_roles") or [] if str(role or "").strip()]
    role_set = set(roles)
    tags: list[str] = []
    tags.extend(roles)

    if _is_local_sml(model):
        tags.append("local_sml")
    if _is_frontier(model):
        tags.append("frontier")

    model_type = str(model.get("type") or "").strip()
    if model_type in {"open_weights", "proprietary"}:
        tags.append(model_type)
    if _first_inference_destination(model):
        tags.append("hyperscaler_available")
    if _australia_destination(model):
        tags.append("australia_route")

    primary = _primary_model_type(role_set, model)
    return {
        "model_type_primary": primary,
        "model_type_tags": _unique(tags),
    }


def _primary_model_type(role_set: set[str], model: dict[str, Any]) -> str:
    if "embedding" in role_set:
        return "embedding"
    if "reranker" in role_set:
        return "reranker"
    if "multimodal_embedding" in role_set:
        return "multimodal_embedding"
    if "document_layout" in role_set:
        return "document_layout"
    if "document_parsing" in role_set:
        return "document_parsing"
    if "ocr" in role_set:
        return "ocr"
    if "content_safety" in role_set:
        return "content_safety"
    if "text_to_speech" in role_set:
        return "text_to_speech"
    if "speech_to_text" in role_set:
        return "speech_to_text"
    if _is_local_sml(model):
        return "local_sml"
    if _is_frontier(model):
        return "frontier"
    if "generator" in role_set:
        return "generator"
    return "unknown"


def _is_frontier(model: dict[str, Any]) -> bool:
    roles = set(str(role) for role in model.get("model_roles") or [])
    return "generator" in roles and not bool(model.get("small_model_candidate"))


def _is_local_sml(model: dict[str, Any]) -> bool:
    return str(model.get("type") or "") == "open_weights" and bool(model.get("small_model_candidate"))


def _default_context_ids(model: dict[str, Any]) -> Iterable[str]:
    roles = set(str(role) for role in model.get("model_roles") or [])
    if "embedding" in roles:
        yield "retrieval_embeddings"
    if "reranker" in roles:
        yield "retrieval_reranking"
    if "speech_to_text" in roles:
        yield "voice_to_text"
    if "text_to_speech" in roles:
        yield "text_to_speech"
    if "generator" in roles and bool(model.get("small_model_candidate")):
        yield "small_model_routing"
    if "generator" in roles and not bool(model.get("small_model_candidate")):
        yield "general_reasoning"


def _strongest_breakdown_item(breakdown: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in breakdown
        if isinstance(item, dict) and item.get("benchmark_id") and item.get("raw_value") is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: float(item.get("normalised") or 0.0) * float(item.get("weight") or 0.0))


def _model_summary(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": model.get("id"),
        "name": model.get("name"),
        "provider": model.get("provider"),
        "model_roles": model.get("model_roles") or ["generator"],
    }


def _score_signal(model: dict[str, Any], benchmark_ids: tuple[str, ...], label: str) -> str | None:
    scores = model.get("scores") if isinstance(model.get("scores"), dict) else {}
    for benchmark_id in benchmark_ids:
        score = scores.get(benchmark_id)
        if isinstance(score, dict):
            value = score.get("raw_value") or score.get("value")
            if value is not None:
                return f"{label}: {value}"
    return None


def _hyperscaler_signal(model: dict[str, Any]) -> str | None:
    summary = model.get("inference_summary") if isinstance(model.get("inference_summary"), dict) else {}
    platforms = [str(platform) for platform in summary.get("platform_names") or [] if str(platform or "").strip()]
    return "; ".join(_unique(platforms)) or None


def _inference_location_signal(model: dict[str, Any]) -> str | None:
    australia_destination = _australia_destination(model)
    if australia_destination:
        return _destination_region_note(australia_destination, prefix="Australia route")
    summary = model.get("inference_summary") if isinstance(model.get("inference_summary"), dict) else {}
    region_count = int(summary.get("region_count") or 0)
    if region_count:
        return f"{region_count} known region{'s' if region_count != 1 else ''}"
    return None


def _first_inference_destination(model: dict[str, Any]) -> dict[str, Any] | None:
    for destination in model.get("inference_destinations") or []:
        if isinstance(destination, dict):
            return destination
    return None


def _australia_destination(model: dict[str, Any]) -> dict[str, Any] | None:
    for destination in model.get("inference_destinations") or []:
        if not isinstance(destination, dict):
            continue
        region_text = " ".join(str(region) for region in destination.get("regions") or []).lower()
        if any(marker in region_text for marker in AUSTRALIA_REGION_MARKERS):
            return destination
    return None


def _destination_name(destination: dict[str, Any]) -> str:
    return str(destination.get("name") or destination.get("destination_name") or destination.get("id") or "Inference destination")


def _destination_region_note(destination: dict[str, Any], *, prefix: str) -> str:
    regions = [str(region) for region in destination.get("regions") or [] if str(region or "").strip()]
    if "australia" in prefix.lower():
        australia_regions = [
            region
            for region in regions
            if any(marker in region.lower() for marker in AUSTRALIA_REGION_MARKERS)
        ]
        if australia_regions:
            regions = australia_regions
    region_label = ", ".join(regions[:4])
    if len(regions) > 4:
        region_label = f"{region_label}, +{len(regions) - 4} more"
    destination_name = _destination_name(destination)
    if region_label:
        return f"{prefix} {region_label} via {destination_name}."
    return f"{prefix} {destination_name}."


def _first_destination_source_url(destination: dict[str, Any]) -> str | None:
    for source in destination.get("sources") or []:
        if isinstance(source, dict) and source.get("url"):
            return str(source["url"])
    return None


def _model_size_value(model: dict[str, Any]) -> str | None:
    parameter_count = model.get("parameter_count_b")
    if parameter_count is not None:
        return f"{parameter_count}B parameters"
    return model.get("model_size_class") or "small"


def _round_float(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _format_float(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


def _unique(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    return unique
