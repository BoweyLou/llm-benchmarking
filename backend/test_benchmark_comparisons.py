from __future__ import annotations

import json
import unittest

from starlette.responses import JSONResponse

from backend import benchmark_comparisons
from backend.models import ScoreOut
from backend.seed_data import BENCHMARKS


def _score(
    value: float,
    *,
    collected_at: str = "2026-07-15T00:00:00Z",
    source_type: str = "primary",
    verified: bool = True,
    observation_count: int | None = None,
    configuration_key: str | None = None,
    configuration_value: str | None = None,
    source_metadata: dict | None = None,
) -> dict:
    return {
        "value": value,
        "raw_value": str(value),
        "collected_at": collected_at,
        "source_type": source_type,
        "verified": verified,
        "observation_count": observation_count,
        "configuration_key": configuration_key,
        "configuration_value": configuration_value,
        "source_metadata": source_metadata or {},
    }


def _model(
    model_id: str,
    benchmark_id: str,
    score: dict,
    *,
    role: str = "generator",
    canonical_model_id: str | None = None,
    configured: list[dict] | None = None,
) -> dict:
    return {
        "id": model_id,
        "name": model_id.replace("-", " ").title(),
        "active": True,
        "model_roles": [role],
        "canonical_model_id": canonical_model_id,
        "scores": {benchmark_id: score},
        "score_configurations": configured or [],
    }


class BenchmarkPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        benchmark_comparisons.invalidate_comparison_cache()
        self.benchmarks = {benchmark["id"]: dict(benchmark) for benchmark in BENCHMARKS}

    def test_registry_is_exhaustive_and_matches_seed_directions(self) -> None:
        benchmark_comparisons.validate_policy_registry(BENCHMARKS)

        active_ids = {benchmark["id"] for benchmark in BENCHMARKS if benchmark.get("active", 1)}
        self.assertEqual(set(benchmark_comparisons.BENCHMARK_POLICIES), active_ids)
        for benchmark in BENCHMARKS:
            policy = benchmark_comparisons.BENCHMARK_POLICIES[benchmark["id"]]
            self.assertEqual(policy.higher_is_better, bool(benchmark.get("higher_is_better", 1)))
            self.assertTrue(policy.roles)
            self.assertGreaterEqual(policy.precision, 0)

    def test_display_formatting_is_policy_owned(self) -> None:
        percent = benchmark_comparisons.format_score_display(
            benchmark_comparisons.BENCHMARK_POLICIES["mteb_retrieval"],
            73.144,
        )
        ratio = benchmark_comparisons.format_score_display(
            benchmark_comparisons.BENCHMARK_POLICIES["chatbot_arena_agent"],
            0.7314,
        )
        elo = benchmark_comparisons.format_score_display(
            benchmark_comparisons.BENCHMARK_POLICIES["chatbot_arena"],
            1267.4,
        )
        cost = benchmark_comparisons.format_score_display(
            benchmark_comparisons.BENCHMARK_POLICIES["aa_cost"],
            2.5,
        )

        self.assertEqual(percent["formatted"], "73.14%")
        self.assertEqual(percent["direction"], "higher")
        self.assertEqual(ratio["value"], 73.14)
        self.assertEqual(ratio["formatted"], "73.1%")
        self.assertEqual(elo["formatted"], "1,267")
        self.assertEqual(cost["formatted"], "$2.5000 / 1M tokens")
        self.assertEqual(cost["direction_label"], "Lower is better")

    def test_every_metric_kind_has_policy_owned_formatting(self) -> None:
        cases = {
            "internal_view": (80.0, None, "80.0"),
            "aa_intelligence": (57.25, None, "57.25"),
            "mteb_retrieval": (73.14, None, "73.14%"),
            "chatbot_arena_agent": (0.7314, None, "73.1%"),
            "chatbot_arena": (1267.4, None, "1,267"),
            "ailuminate": (75.0, "Very Good", "Very Good"),
            "aa_cost": (2.5, None, "$2.5000 / 1M tokens"),
            "aa_ifbench_time": (1.25, None, "1.25 min / task"),
            "aa_speed": (12.34, None, "12.3 tokens / sec"),
            "aa_ifbench_output_tokens": (1235.1, None, "1,235 tokens / task"),
            "asr_english_short_wer": (140.0, None, "140.00%"),
            "asr_realtime_factor": (2.5, None, "2.50×"),
            "helm_capabilities_mean": (65.0, None, "65.00%"),
        }
        for benchmark_id, (value, raw_label, expected) in cases.items():
            with self.subTest(benchmark_id=benchmark_id):
                display = benchmark_comparisons.format_score_display(
                    benchmark_comparisons.BENCHMARK_POLICIES[benchmark_id],
                    value,
                    raw_label,
                )
                self.assertEqual(display["formatted"], expected)
                policy = benchmark_comparisons.BENCHMARK_POLICIES[benchmark_id]
                expected_value = 73.14 if benchmark_id == "chatbot_arena_agent" else (
                    float(round(value)) if policy.precision == 0 else value
                )
                self.assertEqual(display["value"], expected_value)

    def test_higher_and_lower_is_better_rank_ties_and_quantiles(self) -> None:
        higher_models = [
            _model("a", "gpqa_diamond", _score(90.0)),
            _model("b", "gpqa_diamond", _score(90.0)),
            _model("c", "gpqa_diamond", _score(50.0)),
            _model("d", "gpqa_diamond", _score(10.0)),
            _model("e", "gpqa_diamond", _score(0.0)),
        ]
        lower_models = [
            _model("a", "aa_cost", _score(1.0)),
            _model("b", "aa_cost", _score(2.0)),
            _model("c", "aa_cost", _score(3.0)),
            _model("d", "aa_cost", _score(4.0)),
            _model("e", "aa_cost", _score(5.0)),
        ]

        benchmark_comparisons.enrich_models(higher_models, self.benchmarks)
        benchmark_comparisons.enrich_models(lower_models, self.benchmarks)

        tied = higher_models[0]["scores"]["gpqa_diamond"]["comparison"]["strict"]
        cheap = lower_models[0]["scores"]["aa_cost"]["comparison"]["strict"]
        self.assertEqual(tied["rank"], 1)
        self.assertEqual(tied["tie_count"], 2)
        self.assertAlmostEqual(tied["percentile"], 100.0)
        self.assertEqual(tied["distribution"]["median"], 50.0)
        self.assertEqual(cheap["rank"], 1)
        self.assertEqual(cheap["percentile"], 100.0)

    def test_small_and_large_cohort_status_and_bands(self) -> None:
        small = [_model(str(index), "gpqa_diamond", _score(float(index))) for index in range(4)]
        large = [_model(str(index), "gpqa_diamond", _score(float(index))) for index in range(20)]
        benchmark_comparisons.enrich_models(small, self.benchmarks)
        benchmark_comparisons.enrich_models(large, self.benchmarks)

        small_comparison = small[-1]["scores"]["gpqa_diamond"]["comparison"]
        large_position = large[-1]["scores"]["gpqa_diamond"]["comparison"]["strict"]
        self.assertEqual(small_comparison["status"], "limited")
        self.assertIsNone(small_comparison["strict"]["percentile"])
        self.assertIn("Very small cohort", small_comparison["warnings"])
        self.assertEqual(large_position["position_band"], "Leading")

    def test_strict_mteb_cohort_and_broad_context_are_separate(self) -> None:
        task_a = {"task_names": ["ChemNQ", "ChemHotpotQA"], "dataset_revision": "rev-1"}
        task_b = {"task_names": ["NFCorpus"], "dataset_revision": "rev-1"}
        models = [
            _model("target", "mteb_retrieval", _score(73.14, source_metadata=task_a), role="embedding"),
            _model("same", "mteb_retrieval", _score(75.0, source_metadata=task_a), role="embedding"),
            _model("mixed", "mteb_retrieval", _score(20.0, source_metadata=task_b), role="embedding"),
        ]

        benchmark_comparisons.enrich_models(models, self.benchmarks)
        comparison = models[0]["scores"]["mteb_retrieval"]["comparison"]

        self.assertEqual(comparison["strict"]["cohort_size"], 2)
        self.assertEqual(comparison["strict"]["rank"], 2)
        self.assertEqual(comparison["broad"]["cohort_size"], 3)
        self.assertEqual(comparison["broad"]["rank"], 2)
        self.assertIn("Broad cohort mixes evaluation configurations", comparison["warnings"])
        self.assertEqual(comparison["coverage"]["eligible_count"], 3)

    def test_missing_strict_metadata_returns_limited_broad_context(self) -> None:
        models = [
            _model("one", "mteb_retrieval", _score(70.0), role="embedding"),
            _model("two", "mteb_retrieval", _score(60.0), role="embedding"),
        ]

        benchmark_comparisons.enrich_models(models, self.benchmarks)
        comparison = models[0]["scores"]["mteb_retrieval"]["comparison"]

        self.assertEqual(comparison["status"], "limited")
        self.assertIsNone(comparison["strict"])
        self.assertEqual(comparison["broad"]["rank"], 1)
        self.assertIn("Comparable cohort unavailable because evaluation metadata is incomplete", comparison["warnings"])

    def test_configured_scores_compare_only_with_matching_configuration(self) -> None:
        models = []
        for model_id, high, low in (("one", 90.0, 20.0), ("two", 80.0, 30.0)):
            high_score = _score(
                high,
                configuration_key="reasoning_effort",
                configuration_value="high",
            )
            low_score = _score(
                low,
                configuration_key="reasoning_effort",
                configuration_value="low",
            )
            models.append(
                _model(
                    model_id,
                    "aa_intelligence",
                    high_score,
                    configured=[
                        {"benchmark_id": "aa_intelligence", **high_score},
                        {"benchmark_id": "aa_intelligence", **low_score},
                    ],
                )
            )

        benchmark_comparisons.enrich_models(models, self.benchmarks)
        one_low = next(
            item
            for item in models[0]["score_configurations"]
            if item["configuration_value"] == "low"
        )
        one_high = next(
            item
            for item in models[0]["score_configurations"]
            if item["configuration_value"] == "high"
        )
        self.assertEqual(one_low["comparison"]["broad"]["cohort_size"], 2)
        self.assertEqual(one_low["comparison"]["broad"]["rank"], 2)
        self.assertEqual(one_high["comparison"]["broad"]["rank"], 1)
        self.assertIn("Broad cohort mixes evaluation configurations", one_low["comparison"]["warnings"])

    def test_canonical_arbitration_is_provenance_first_not_best_numeric(self) -> None:
        models = [
            _model(
                "suite-primary",
                "gpqa_diamond",
                _score(40.0, verified=True, source_type="primary"),
                canonical_model_id="suite",
            ),
            _model(
                "suite-unverified",
                "gpqa_diamond",
                _score(99.0, verified=False, source_type="secondary", collected_at="2026-07-16T00:00:00Z"),
                canonical_model_id="suite",
            ),
            _model("competitor", "gpqa_diamond", _score(50.0)),
        ]

        benchmark_comparisons.enrich_models(models, self.benchmarks)
        target = models[0]["scores"]["gpqa_diamond"]["comparison"]

        self.assertEqual(target["broad"]["cohort_size"], 2)
        self.assertEqual(target["broad"]["rank"], 2)
        self.assertEqual(target["contributor_model_id"], "suite-primary")
        self.assertTrue(target["selected_for_entity"])
        self.assertTrue(any(item.startswith("Canonical aliases report different values") for item in target["warnings"]))
        alias = models[1]["scores"]["gpqa_diamond"]["comparison"]
        self.assertFalse(alias["selected_for_entity"])
        self.assertEqual(alias["contributor_model_id"], "suite-primary")
        self.assertEqual(alias["broad"]["rank"], target["broad"]["rank"])

    def test_unverified_sources_are_equivalent_before_recency_and_evidence(self) -> None:
        current = _score(
            90.0,
            collected_at="2026-07-15T00:00:00Z",
            source_type="primary",
            verified=False,
            observation_count=100,
        )
        newer_manual = _score(
            10.0,
            collected_at="2026-07-16T00:00:00Z",
            source_type="manual",
            verified=False,
            observation_count=1,
        )
        verified_manual = _score(
            5.0,
            collected_at="2026-01-01T00:00:00Z",
            source_type="manual",
            verified=True,
        )

        self.assertTrue(benchmark_comparisons.prefer_score_candidate(newer_manual, current))
        self.assertTrue(benchmark_comparisons.prefer_score_candidate(verified_manual, newer_manual))

        verified_primary = {**verified_manual, "source_type": "primary"}
        verified_secondary = {**verified_manual, "source_type": "secondary"}
        self.assertTrue(
            benchmark_comparisons.prefer_score_candidate(verified_primary, verified_secondary)
        )

    def test_rank_and_ties_use_raw_values_not_display_rounding(self) -> None:
        models = [
            _model("a", "gpqa_diamond", _score(50.001)),
            _model("b", "gpqa_diamond", _score(50.004)),
            _model("c", "gpqa_diamond", _score(40.0)),
            _model("d", "gpqa_diamond", _score(30.0)),
            _model("e", "gpqa_diamond", _score(20.0)),
        ]

        benchmark_comparisons.enrich_models(models, self.benchmarks)
        first = models[0]["scores"]["gpqa_diamond"]["comparison"]["broad"]
        second = models[1]["scores"]["gpqa_diamond"]["comparison"]["broad"]
        self.assertEqual((first["rank"], first["tie_count"]), (2, 1))
        self.assertEqual((second["rank"], second["tie_count"]), (1, 1))

    def test_percentile_endpoints_and_all_equal_distribution(self) -> None:
        endpoint_models = [
            _model("best-a", "gpqa_diamond", _score(90.0)),
            _model("best-b", "gpqa_diamond", _score(90.0)),
            _model("middle", "gpqa_diamond", _score(50.0)),
            _model("worst-a", "gpqa_diamond", _score(10.0)),
            _model("worst-b", "gpqa_diamond", _score(10.0)),
        ]
        equal_models = [
            _model(f"equal-{index}", "gpqa_diamond", _score(50.0))
            for index in range(20)
        ]
        benchmark_comparisons.enrich_models(endpoint_models, self.benchmarks)
        benchmark_comparisons.enrich_models(equal_models, self.benchmarks)

        best = endpoint_models[0]["scores"]["gpqa_diamond"]["comparison"]["strict"]
        worst = endpoint_models[-1]["scores"]["gpqa_diamond"]["comparison"]["strict"]
        equal = equal_models[0]["scores"]["gpqa_diamond"]["comparison"]["strict"]
        self.assertEqual(best["percentile"], 100.0)
        self.assertEqual(worst["percentile"], 0.0)
        self.assertEqual(equal["percentile"], 50.0)
        self.assertEqual(equal["position_band"], "Mid-pack")
        self.assertEqual(set(equal["distribution"].values()), {50.0})

    def test_multi_role_benchmark_cohorts_and_coverage_are_target_role_compatible(self) -> None:
        models = [
            *[
                _model(str(index), "mteb_retrieval_reranking", _score(50.0 + index), role="embedding")
                for index in range(5)
            ],
            *[
                _model(f"reranker-{index}", "mteb_retrieval_reranking", _score(80.0 + index), role="reranker")
                for index in range(7)
            ],
        ]
        benchmark_comparisons.enrich_models(models, self.benchmarks)

        embedding = models[0]["scores"]["mteb_retrieval_reranking"]["comparison"]
        reranker = models[-1]["scores"]["mteb_retrieval_reranking"]["comparison"]
        self.assertEqual(embedding["broad"]["cohort_size"], 5)
        self.assertEqual(embedding["coverage"]["eligible_count"], 5)
        self.assertEqual(reranker["broad"]["cohort_size"], 7)
        self.assertEqual(reranker["coverage"]["eligible_count"], 7)

    def test_configuration_does_not_substitute_for_required_evaluation_signature(self) -> None:
        score = _score(
            73.14,
            configuration_key="task_set",
            configuration_value="default",
        )
        models = [_model("embedding", "mteb_retrieval", score, role="embedding")]
        benchmark_comparisons.enrich_models(models, self.benchmarks)

        comparison = score["comparison"]
        self.assertIsNone(comparison["strict"])
        self.assertEqual(comparison["status"], "limited")
        self.assertIn("evaluation metadata is incomplete", " ".join(comparison["warnings"]))

    def test_low_coverage_warning_and_duplicate_configured_observation(self) -> None:
        duplicate = _score(70.0)
        duplicate.update(configuration_key="task_set", configuration_value="default")
        models = [
            _model(
                "scored",
                "mteb_retrieval",
                duplicate,
                role="embedding",
                configured=[{"benchmark_id": "mteb_retrieval", **duplicate}],
            ),
            {"id": "missing-a", "name": "Missing A", "active": True, "model_roles": ["embedding"], "scores": {}, "score_configurations": []},
            {"id": "missing-b", "name": "Missing B", "active": True, "model_roles": ["embedding"], "scores": {}, "score_configurations": []},
        ]
        benchmark_comparisons.enrich_models(models, self.benchmarks)

        comparison = duplicate["comparison"]
        self.assertEqual(comparison["broad"]["cohort_size"], 1)
        self.assertEqual(comparison["coverage"]["scored_count"], 1)
        self.assertIn("Low database coverage", comparison["warnings"])

    def test_invalid_bounded_value_is_quarantined_but_wer_above_100_is_valid(self) -> None:
        invalid_models = [
            _model("broken", "swebench_verified", _score(140.0)),
            _model("valid", "swebench_verified", _score(40.0)),
        ]
        wer_models = [
            _model("noisy", "asr_english_short_wer", _score(140.0), role="speech_to_text"),
            _model("clear", "asr_english_short_wer", _score(20.0), role="speech_to_text"),
        ]

        benchmark_comparisons.enrich_models(invalid_models, self.benchmarks)
        benchmark_comparisons.enrich_models(wer_models, self.benchmarks)

        invalid = invalid_models[0]["scores"]["swebench_verified"]["comparison"]
        wer = wer_models[0]["scores"]["asr_english_short_wer"]["comparison"]
        self.assertEqual(invalid["status"], "invalid")
        self.assertIsNone(invalid["broad"])
        self.assertEqual(
            invalid_models[0]["scores"]["swebench_verified"]["display"]["formatted"],
            "Data check needed",
        )
        self.assertEqual(invalid_models[0]["scores"]["swebench_verified"]["value"], 140.0)
        self.assertEqual(wer["broad"]["cohort_size"], 2)
        self.assertEqual(wer["broad"]["rank"], 2)
        self.assertEqual(
            wer_models[0]["scores"]["asr_english_short_wer"]["display"]["formatted"],
            "140.00%",
        )

        benchmark_comparisons.enrich_models(invalid_models, self.benchmarks)
        self.assertEqual(invalid_models[0]["scores"]["swebench_verified"]["value"], 140.0)
        self.assertEqual(
            invalid_models[0]["scores"]["swebench_verified"]["display"]["formatted"],
            "Data check needed",
        )

    def test_non_finite_scores_remain_invalid_but_are_json_transport_safe(self) -> None:
        primary = _score(float("inf"))
        primary["raw_value"] = "inf"
        configured = _score(float("nan"), configuration_key="task_set", configuration_value="broken")
        configured["raw_value"] = "nan"
        models = [
            _model(
                "broken",
                "gpqa_diamond",
                primary,
                configured=[{"benchmark_id": "gpqa_diamond", **configured}],
            )
        ]

        benchmark_comparisons.enrich_models(models, self.benchmarks)

        score = models[0]["scores"]["gpqa_diamond"]
        configured_score = models[0]["score_configurations"][0]
        for item, raw_value in ((score, "inf"), (configured_score, "nan")):
            self.assertIsNone(item["value"])
            self.assertEqual(item["raw_value"], raw_value)
            self.assertEqual(item["display"]["formatted"], "Data check needed")
            self.assertEqual(item["comparison"]["status"], "invalid")
            self.assertIsNone(item["comparison"]["broad"])

        json.dumps(models, allow_nan=False)
        response_payload = ScoreOut.model_validate(score).model_dump(mode="json")
        self.assertTrue(JSONResponse(response_payload).body)

        # Cached/enriched objects may pass through more than one public output.
        # A second pass must not accidentally reinterpret the safe placeholder.
        benchmark_comparisons.enrich_models(models, self.benchmarks)
        self.assertEqual(score["comparison"]["status"], "invalid")
        self.assertEqual(score["display"]["formatted"], "Data check needed")
        self.assertTrue(any("sanitized for JSON transport" in warning for warning in score["comparison"]["warnings"]))
        json.dumps(models, allow_nan=False)

    def test_role_coverage_and_evidence_are_structured(self) -> None:
        models = [
            _model("embed-scored", "mteb_retrieval", _score(70.0, observation_count=2), role="embedding"),
            {
                "id": "embed-unscored",
                "name": "Unscored",
                "active": True,
                "model_roles": ["embedding"],
                "scores": {},
                "score_configurations": [],
            },
            _model("generator", "mteb_retrieval", _score(99.0), role="generator"),
        ]

        benchmark_comparisons.enrich_models(models, self.benchmarks)
        score = models[0]["scores"]["mteb_retrieval"]

        self.assertEqual(score["comparison"]["coverage"]["eligible_count"], 2)
        self.assertEqual(score["comparison"]["coverage"]["scored_count"], 1)
        self.assertEqual(score["evidence"]["count"], 2)
        self.assertEqual(score["evidence"]["label"], "2 task results")
        self.assertEqual(
            models[0]["relevant_benchmark_ids"],
            ["mteb_retrieval", "mteb_retrieval_reranking", "rteb_finance"],
        )
        self.assertEqual(len(models[2]["relevant_benchmark_ids"]), 5)

    def test_comparison_index_is_cached_and_fingerprint_invalidates_it(self) -> None:
        models = [_model("one", "gpqa_diamond", _score(50.0))]
        first = benchmark_comparisons.enrich_models(models, self.benchmarks)
        first_builds = benchmark_comparisons.comparison_cache_info()["builds"]

        benchmark_comparisons.enrich_models(models, self.benchmarks)
        self.assertEqual(benchmark_comparisons.comparison_cache_info()["builds"], first_builds)

        models[0]["scores"]["gpqa_diamond"]["value"] = 60.0
        benchmark_comparisons.enrich_models(models, self.benchmarks)
        self.assertEqual(benchmark_comparisons.comparison_cache_info()["builds"], first_builds + 1)
        self.assertIs(first, models)

    def test_cache_fingerprint_is_order_insensitive_and_tracks_contributor_name(self) -> None:
        models = [
            _model("one", "gpqa_diamond", _score(50.0)),
            _model("two", "gpqa_diamond", _score(60.0)),
        ]
        models[0]["name"] = "Old name"
        benchmark_comparisons.enrich_models(models, self.benchmarks)
        first_builds = benchmark_comparisons.comparison_cache_info()["builds"]

        benchmark_comparisons.enrich_models(list(reversed(models)), self.benchmarks)
        self.assertEqual(benchmark_comparisons.comparison_cache_info()["builds"], first_builds)

        models[0]["name"] = "Renamed model"
        benchmark_comparisons.enrich_models(models, self.benchmarks)
        comparison = models[0]["scores"]["gpqa_diamond"]["comparison"]
        self.assertEqual(benchmark_comparisons.comparison_cache_info()["builds"], first_builds + 1)
        self.assertEqual(comparison["contributor_model_name"], "Renamed model")

    def test_benchmark_summaries_include_policy_distribution_and_coverage(self) -> None:
        models = [
            _model("one", "gpqa_diamond", _score(50.0)),
            _model("two", "gpqa_diamond", _score(75.0)),
            {
                "id": "three",
                "name": "Three",
                "active": True,
                "model_roles": ["generator"],
                "scores": {},
                "score_configurations": [],
            },
        ]
        index = benchmark_comparisons.get_comparison_index(models, self.benchmarks)
        summary = index.benchmark_summary("gpqa_diamond")

        self.assertEqual(summary["scored_count"], 2)
        self.assertEqual(summary["eligible_count"], 3)
        self.assertAlmostEqual(summary["coverage_percent"], 66.67)
        self.assertEqual(summary["distribution"]["median"], 62.5)
        self.assertEqual(index.presentation("gpqa_diamond")["unit"], "%")


if __name__ == "__main__":
    unittest.main()
