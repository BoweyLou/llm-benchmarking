from __future__ import annotations

from typing import Any, Callable, Iterable


ModelSummaryBuilder = Callable[[dict[str, Any]], dict[str, Any]]


def build_rankings_response(
    *,
    use_case: dict[str, Any],
    models: list[dict[str, Any]],
    benchmarks: dict[str, dict[str, Any]],
    model_summary: ModelSummaryBuilder,
    min_ranking_coverage: float,
    coverage_exempt_benchmark_ids: Iterable[str],
) -> dict[str, Any]:
    weights = use_case["weights"]
    required_benchmarks = list(use_case.get("required_benchmarks", []))
    use_case_min_coverage = float(use_case.get("min_coverage", min_ranking_coverage))
    ranges = benchmark_ranges(models, weights)
    total_configured_weight = sum(weights.values())
    coverage_exempt_ids = set(coverage_exempt_benchmark_ids)
    total_coverage_weight = sum(
        weight
        for benchmark_id, weight in weights.items()
        if benchmark_id not in coverage_exempt_ids
    )

    rankings: list[dict[str, Any]] = []
    for model in models:
        ranking = build_model_ranking(
            model=model,
            benchmarks=benchmarks,
            weights=weights,
            required_benchmarks=required_benchmarks,
            ranges=ranges,
            total_configured_weight=total_configured_weight,
            total_coverage_weight=total_coverage_weight,
            use_case_min_coverage=use_case_min_coverage,
            coverage_exempt_benchmark_ids=coverage_exempt_ids,
            model_summary=model_summary,
        )
        if ranking is not None:
            rankings.append(ranking)

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
            "segment": use_case.get("segment", "core"),
            "status": use_case.get("status", "ready"),
            "min_coverage": use_case_min_coverage,
            "required_benchmarks": required_benchmarks,
            "benchmark_notes": dict(use_case.get("benchmark_notes", {})),
            "weights": dict(use_case["weights"]),
        },
        "rankings": rankings,
    }


def build_model_ranking(
    *,
    model: dict[str, Any],
    benchmarks: dict[str, dict[str, Any]],
    weights: dict[str, float],
    required_benchmarks: list[str],
    ranges: dict[str, tuple[float, float]],
    total_configured_weight: float,
    total_coverage_weight: float,
    use_case_min_coverage: float,
    coverage_exempt_benchmark_ids: set[str],
    model_summary: ModelSummaryBuilder,
) -> dict[str, Any] | None:
    weighted_sum = 0.0
    available_coverage_weight = 0.0
    breakdown: list[dict[str, Any]] = []
    missing_benchmarks: list[str] = []
    critical_missing_benchmarks: list[str] = []

    for benchmark_id, weight in weights.items():
        score = model["scores"].get(benchmark_id)
        benchmark = benchmarks.get(benchmark_id)
        score_range = ranges.get(benchmark_id)

        if score is None or benchmark is None or score_range is None:
            missing_benchmarks.append(benchmark_id)
            if benchmark_id in required_benchmarks:
                critical_missing_benchmarks.append(benchmark_id)
            continue

        raw_value = float(score["value"])
        normalised = normalise_score(
            raw_value,
            score_range[0],
            score_range[1],
            bool(benchmark["higher_is_better"]),
        )
        weighted_sum += normalised * weight
        if benchmark_id not in coverage_exempt_benchmark_ids:
            available_coverage_weight += weight
        breakdown.append(
            {
                "benchmark_id": benchmark_id,
                "raw_value": raw_value,
                "normalised": normalised,
                "weight": weight,
                "metric": benchmark["metric"],
                "source_type": score.get("source_type", "primary"),
                "verified": bool(score.get("verified", False)),
                "notes": score.get("notes"),
                "variant_model_id": score.get("variant_model_id"),
                "variant_model_name": score.get("variant_model_name"),
            }
        )

    if total_configured_weight <= 0:
        return None

    coverage = 1.0 if total_coverage_weight <= 0 else available_coverage_weight / total_coverage_weight
    if coverage < use_case_min_coverage:
        return None
    if critical_missing_benchmarks:
        return None

    return {
        "score": weighted_sum / total_configured_weight,
        "coverage": coverage,
        "model": model_summary(model),
        "breakdown": breakdown,
        "missing_benchmarks": missing_benchmarks,
        "critical_missing_benchmarks": critical_missing_benchmarks,
    }


def benchmark_ranges(
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


def normalise_score(raw_value: float, minimum: float, maximum: float, higher_is_better: bool) -> float:
    if maximum == minimum:
        return 75.0

    scaled = (raw_value - minimum) / (maximum - minimum) * 100.0
    score = scaled if higher_is_better else 100.0 - scaled
    return max(0.0, min(100.0, score))
