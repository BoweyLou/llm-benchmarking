from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend import cli
from backend.catalog_export import render_model_metadata_csv_bundle, render_model_metadata_list


class CatalogExportTests(unittest.TestCase):
    def test_render_jsonl_prints_one_complete_model_per_line(self) -> None:
        models = [
            {
                "id": "model-a",
                "name": "Model A",
                "provider": "Provider",
                "scores": {"benchmark": {
                    "value": 95.0,
                    "verified": True,
                    "confidence_lower": 94.0,
                    "confidence_upper": 96.0,
                    "rank": 1,
                    "category": "overall",
                    "publication_date": "2026-07-10",
                    "methodology": "bradley_terry_style_controlled",
                    "source_listing_status": "listed",
                    "style_control": True,
                    "preliminary": False,
                    "source_metadata": {"dataset_revision": "a" * 40},
                    "display": {
                        "value": 95.0,
                        "unit": "%",
                        "formatted": "95%",
                        "precision": 2,
                        "direction": "higher",
                        "direction_label": "Higher is better",
                    },
                    "evidence": {"count": 2, "unit": "task files", "label": "2 task files"},
                    "comparison": {
                        "status": "comparable",
                        "strict": {
                            "rank": 2,
                            "tie_count": 1,
                            "cohort_size": 20,
                            "percentile": 94.7,
                            "position_band": "Leading",
                            "cohort_label": "Comparable models",
                            "distribution": {
                                "min": 40.0,
                                "p10": 55.0,
                                "p25": 70.0,
                                "median": 82.0,
                                "p75": 91.0,
                                "p90": 96.0,
                                "max": 98.0,
                            },
                        },
                        "broad": {
                            "rank": 4,
                            "tie_count": 1,
                            "cohort_size": 169,
                            "percentile": 98.2,
                            "position_band": "Leading",
                            "cohort_label": "All scored embedding models",
                            "distribution": {"median": 28.4, "p25": 12.0, "p75": 47.14},
                        },
                        "coverage": {
                            "scored_count": 169,
                            "eligible_count": 233,
                            "percent": 72.5,
                            "label": "169 of 233 embedding models",
                        },
                        "warnings": ["Broad cohort mixes task sets."],
                        "as_of": "2026-07-14T00:00:00Z",
                        "contributor_model_id": "model-a",
                        "contributor_model_name": "Model A",
                    },
                }},
                "inference_destinations": [{"id": "aws-bedrock", "regions": ["us-east-1"]}],
            },
            {
                "id": "model-b",
                "name": "Model B",
                "provider": "Provider",
                "license_id": "apache-2.0",
            },
        ]

        rendered = render_model_metadata_list(models, output_format="jsonl")

        lines = rendered.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), models[0])
        self.assertEqual(json.loads(lines[1]), models[1])

    def test_invalid_non_finite_score_exports_as_null_with_raw_text_and_status(self) -> None:
        score = {
            "value": None,
            "raw_value": "Infinity",
            "collected_at": "2026-07-15T00:00:00Z",
            "source_type": "primary",
            "verified": True,
            "display": {
                "value": None,
                "formatted": "Data check needed",
                "unit": "%",
                "precision": 2,
                "direction": "higher",
                "direction_label": "Higher is better",
            },
            "evidence": {"count": None, "unit": "observation", "label": "Evidence count unavailable"},
            "comparison": {
                "status": "invalid",
                "strict": None,
                "broad": None,
                "coverage": {
                    "scored_count": 0,
                    "eligible_count": 1,
                    "percent": 0.0,
                    "label": "0 of 1 compatible models scored",
                },
                "warnings": ["Data check needed: score is missing, non-numeric, or non-finite"],
                "as_of": "2026-07-15T00:00:00Z",
            },
        }
        models = [{
            "id": "invalid-model",
            "name": "Invalid Model",
            "provider": "Provider",
            "scores": {"benchmark": score},
        }]

        json_payload = json.loads(render_model_metadata_list(models, output_format="json"))
        jsonl_payload = json.loads(render_model_metadata_list(models, output_format="jsonl"))
        self.assertIsNone(json_payload[0]["scores"]["benchmark"]["value"])
        self.assertIsNone(jsonl_payload["scores"]["benchmark"]["value"])
        self.assertEqual(json_payload[0]["scores"]["benchmark"]["raw_value"], "Infinity")

        score_row = next(csv.DictReader(io.StringIO(render_model_metadata_csv_bundle(models)["scores"])))
        self.assertEqual(score_row["value"], "")
        self.assertEqual(score_row["raw_value"], "Infinity")
        self.assertEqual(score_row["display_value"], "")
        self.assertEqual(score_row["display_formatted"], "Data check needed")
        self.assertEqual(score_row["comparison_status"], "invalid")

    def test_render_csv_summarizes_nested_metadata_without_json_cells(self) -> None:
        models = [
            {
                "id": "model-a",
                "name": "Model A",
                "provider": "Provider",
                "parameter_count_b": 12.0,
                "active_parameter_count_b": None,
                "model_size_class": "small",
                "small_model_candidate": True,
                "model_size_source_name": "huggingface_model_discovery",
                "model_size_source_url": "https://huggingface.co/provider/model-a",
                "model_size_verified_at": "2026-07-01T00:00:00Z",
                "release_date": "2026-06-15",
                "release_date_precision": "day",
                "release_date_confidence": "high",
                "release_date_source_name": "Artificial Analysis",
                "release_date_source_url": "https://artificialanalysis.ai/models/model-a",
                "release_date_verified_at": "2026-07-01T00:00:00Z",
                "model_age_days": 16,
                "model_age_basis": "release_date",
                "model_age_confidence": "high",
                "model_age_source_name": "Artificial Analysis",
                "model_age_source_url": "https://artificialanalysis.ai/models/model-a",
                "model_age_reference_date": "2026-07-01",
                "huggingface_created_at": "2026-06-16T12:00:00Z",
                "huggingface_last_modified_at": "2026-06-25T18:30:00Z",
                "model_roles": ["embedding", "reranker"],
                "relevant_benchmark_ids": ["benchmark", "missing-benchmark"],
                "general_recommendation_status": "restricted",
                "suggested_use_cases": [
                    {
                        "use_case_id": "customer_support",
                        "label": "Customer support",
                        "fit_score": 88.4,
                        "confidence": 0.81,
                        "reasons": ["Strong instruction following"],
                        "warnings": ["Monitor hallucinations"],
                        "required_controls": ["Human escalation"],
                    }
                ],
                "provider_origin_countries": [{"code": "US", "name": "United States"}],
                "scores": {"benchmark": {
                    "value": 95.0,
                    "verified": True,
                    "confidence_lower": 94.0,
                    "confidence_upper": 96.0,
                    "rank": 1,
                    "category": "overall",
                    "publication_date": "2026-07-10",
                    "methodology": "bradley_terry_style_controlled",
                    "source_listing_status": "listed",
                    "style_control": True,
                    "preliminary": False,
                    "source_metadata": {"dataset_revision": "a" * 40},
                    "comparison": {
                        "status": "comparable",
                        "strict": {"position_band": "Leading"},
                    },
                }},
                "use_case_approvals": {
                    "customer_support": {
                        "approved_for_use": True,
                        "recommendation_status": "recommended",
                        "proposed_recommendation_status": "not_recommended",
                        "effective_recommendation_status": "recommended",
                    },
                    "coding": {
                        "approved_for_use": False,
                        "recommendation_status": "restricted",
                        "effective_recommendation_status": "restricted",
                    }
                },
                "inference_destinations": [
                    {"id": "aws-bedrock", "name": "AWS Bedrock", "regions": ["us-east-1"]}
                ],
            }
        ]

        rendered = render_model_metadata_list(models, output_format="csv")

        rows = list(csv.DictReader(io.StringIO(rendered)))
        self.assertEqual(rows[0]["id"], "model-a")
        self.assertNotIn("scores", rows[0])
        self.assertNotIn("inference_destinations", rows[0])
        self.assertEqual(rows[0]["parameter_count_b"], "12.0")
        self.assertEqual(rows[0]["model_size_class"], "small")
        self.assertEqual(rows[0]["small_model_candidate"], "true")
        self.assertEqual(rows[0]["model_size_source_name"], "huggingface_model_discovery")
        self.assertEqual(rows[0]["release_date"], "2026-06-15")
        self.assertEqual(rows[0]["release_date_precision"], "day")
        self.assertEqual(rows[0]["release_date_confidence"], "high")
        self.assertEqual(rows[0]["release_date_source_name"], "Artificial Analysis")
        self.assertEqual(rows[0]["model_age_days"], "16")
        self.assertEqual(rows[0]["model_age_basis"], "release_date")
        self.assertEqual(rows[0]["model_age_confidence"], "high")
        self.assertEqual(rows[0]["huggingface_created_at"], "2026-06-16T12:00:00Z")
        self.assertEqual(rows[0]["huggingface_last_modified_at"], "2026-06-25T18:30:00Z")
        self.assertEqual(rows[0]["model_roles"], "embedding; reranker")
        self.assertEqual(rows[0]["provider_origin_country_names"], "United States")
        self.assertEqual(rows[0]["score_count"], "1")
        self.assertEqual(rows[0]["verified_score_count"], "1")
        self.assertEqual(rows[0]["benchmark_ids_with_scores"], "benchmark")
        self.assertEqual(rows[0]["comparable_score_count"], "1")
        self.assertEqual(rows[0]["limited_score_count"], "0")
        self.assertEqual(rows[0]["leading_score_count"], "1")
        self.assertEqual(rows[0]["missing_relevant_benchmark_count"], "1")
        self.assertEqual(rows[0]["general_recommendation_status"], "restricted")
        self.assertEqual(rows[0]["suggested_use_case_count"], "1")
        self.assertEqual(rows[0]["suggested_use_case_ids"], "customer_support")
        self.assertEqual(rows[0]["inference_destination_count"], "1")
        self.assertEqual(rows[0]["inference_platform_names"], "AWS Bedrock")
        self.assertEqual(rows[0]["inference_region_names"], "us-east-1")
        self.assertEqual(rows[0]["approved_use_case_ids"], "customer_support")
        self.assertEqual(rows[0]["restricted_use_case_ids"], "coding")
        self.assertNotIn("proposed_recommended_use_case_ids", rows[0])
        self.assertNotIn("proposed_not_recommended_use_case_ids", rows[0])
        self.assertNotIn("effective_recommended_use_case_ids", rows[0])
        self.assertNotIn("effective_restricted_use_case_ids", rows[0])

    def test_render_raw_csv_preserves_nested_payloads(self) -> None:
        models = [
            {
                "id": "model-a",
                "name": "Model A",
                "provider": "Provider",
                "model_roles": ["embedding"],
                "scores": {"benchmark": {"value": 95.0, "verified": True}},
                "inference_destinations": [{"id": "aws-bedrock", "regions": ["us-east-1"]}],
            }
        ]

        rendered = render_model_metadata_list(models, output_format="raw-csv")

        rows = list(csv.DictReader(io.StringIO(rendered)))
        self.assertEqual(rows[0]["id"], "model-a")
        self.assertEqual(json.loads(rows[0]["model_roles"]), ["embedding"])
        self.assertEqual(json.loads(rows[0]["scores"]), models[0]["scores"])
        self.assertEqual(json.loads(rows[0]["inference_destinations"]), models[0]["inference_destinations"])

    def test_configured_score_comparison_is_flattened_and_counted(self) -> None:
        models = [{
            "id": "configured-model",
            "name": "Configured Model",
            "provider": "Provider",
            "scores": {},
            "relevant_benchmark_ids": ["benchmark"],
            "score_configurations": [{
                "benchmark_id": "benchmark",
                "configuration_key": "reasoning_effort",
                "configuration_value": "high",
                "value": 90.0,
                "display": {
                    "value": 90.0,
                    "formatted": "90%",
                    "unit": "%",
                    "precision": 1,
                    "direction": "higher",
                    "direction_label": "Higher is better",
                },
                "evidence": {"count": 3, "unit": "runs", "label": "3 runs"},
                "comparison": {
                    "status": "limited",
                    "strict": None,
                    "broad": {
                        "rank": 1,
                        "tie_count": 1,
                        "cohort_size": 3,
                        "percentile": None,
                        "distribution": {"median": 80.0},
                        "cohort_label": "Matching high-effort configurations",
                        "position_band": None,
                    },
                    "coverage": {"scored_count": 3, "eligible_count": 5, "percent": 60.0, "label": "3 of 5 models"},
                    "warnings": ["Very small cohort"],
                    "as_of": "2026-07-15T00:00:00Z",
                    "contributor_model_id": "configured-model",
                    "contributor_model_name": "Configured Model",
                },
            }],
        }]

        clean_row = next(csv.DictReader(io.StringIO(render_model_metadata_list(models, output_format="csv"))))
        score_row = next(csv.DictReader(io.StringIO(render_model_metadata_csv_bundle(models)["scores"])))

        self.assertEqual(clean_row["limited_score_count"], "1")
        self.assertEqual(clean_row["score_count"], "1")
        self.assertEqual(clean_row["missing_relevant_benchmark_count"], "0")
        self.assertEqual(score_row["configuration_value"], "high")
        self.assertEqual(score_row["comparison_status"], "limited")
        self.assertEqual(score_row["broad_cohort_label"], "Matching high-effort configurations")
        self.assertEqual(score_row["evidence_label"], "3 runs")

    def test_duplicate_latest_configured_observation_is_exported_and_counted_once(self) -> None:
        observation = {
            "value": 90.0,
            "raw_value": "90.0",
            "collected_at": "2026-07-15T00:00:00Z",
            "source_url": "https://example.com/result",
            "source_type": "primary",
            "verified": True,
            "configuration_key": "reasoning_effort",
            "configuration_value": "high",
            "source_metadata": {"dataset_revision": "revision-a"},
            "comparison": {"status": "comparable"},
        }
        distinct_signature = {
            **observation,
            "value": 89.0,
            "raw_value": "89.0",
            "source_metadata": {"dataset_revision": "revision-b"},
        }
        models = [{
            "id": "configured-model",
            "name": "Configured Model",
            "provider": "Provider",
            "scores": {"benchmark": dict(observation)},
            "score_configurations": [
                {"benchmark_id": "benchmark", **observation},
                {"benchmark_id": "benchmark", **distinct_signature},
            ],
        }]

        clean_row = next(csv.DictReader(io.StringIO(render_model_metadata_list(models, output_format="csv"))))
        score_rows = list(csv.DictReader(io.StringIO(render_model_metadata_csv_bundle(models)["scores"])))

        self.assertEqual(clean_row["score_count"], "2")
        self.assertEqual(clean_row["comparable_score_count"], "2")
        self.assertEqual(len(score_rows), 2)
        self.assertEqual(
            {json.loads(row["source_metadata"])["dataset_revision"] for row in score_rows},
            {"revision-a", "revision-b"},
        )

    def test_render_csv_bundle_normalizes_nested_tables(self) -> None:
        models = [
            {
                "id": "model-a",
                "name": "Model A",
                "provider": "Provider",
                "provider_origin_countries": [{"code": "AU", "name": "Australia"}],
                "scores": {"benchmark": {
                    "value": 95.0,
                    "verified": True,
                    "confidence_lower": 94.0,
                    "confidence_upper": 96.0,
                    "rank": 1,
                    "category": "overall",
                    "publication_date": "2026-07-10",
                    "methodology": "bradley_terry_style_controlled",
                    "source_listing_status": "listed",
                    "style_control": True,
                    "preliminary": False,
                    "source_metadata": {"dataset_revision": "a" * 40},
                    "display": {
                        "value": 95.0,
                        "unit": "%",
                        "formatted": "95%",
                        "precision": 2,
                        "direction": "higher",
                        "direction_label": "Higher is better",
                    },
                    "evidence": {"count": 2, "unit": "task files", "label": "2 task files"},
                    "comparison": {
                        "status": "comparable",
                        "strict": {
                            "rank": 2,
                            "tie_count": 1,
                            "cohort_size": 20,
                            "percentile": 94.7,
                            "position_band": "Leading",
                            "cohort_label": "Comparable models",
                            "distribution": {"median": 82.0, "p25": 70.0, "p75": 91.0},
                        },
                        "broad": {
                            "rank": 4,
                            "tie_count": 1,
                            "cohort_size": 169,
                            "percentile": 98.2,
                            "position_band": "Leading",
                            "cohort_label": "All scored embedding models",
                            "distribution": {"median": 28.4, "p25": 12.0, "p75": 47.14},
                        },
                        "coverage": {
                            "scored_count": 169,
                            "eligible_count": 233,
                            "percent": 72.5,
                            "label": "169 of 233 embedding models",
                        },
                        "warnings": ["Broad cohort mixes task sets."],
                        "as_of": "2026-07-14T00:00:00Z",
                        "contributor_model_id": "model-a",
                        "contributor_model_name": "Model A",
                    },
                }},
                "use_case_approvals": {
                    "customer_support": {
                        "approved_for_use": True,
                        "recommendation_status": "recommended",
                        "proposed_recommendation_status": "recommended",
                        "proposed_recommendation_required_controls": ["PIA"],
                        "effective_recommendation_status": "recommended",
                    }
                },
                "suggested_use_cases": [{
                    "use_case_id": "customer_support",
                    "label": "Customer support",
                    "description": "Customer-facing assistance",
                    "fit_score": 88.4,
                    "confidence": 0.81,
                    "reasons": ["Strong instruction following"],
                    "warnings": ["Monitor hallucinations"],
                    "required_controls": ["Human escalation"],
                    "policy_version": "test-policy",
                    "computed_at": "2026-07-14T00:00:00Z",
                }],
                "inference_destinations": [
                    {
                        "id": "aws-bedrock",
                        "name": "AWS Bedrock",
                        "hyperscaler": "AWS",
                        "regions": ["ap-southeast-2"],
                    }
                ],
                "source_freshness": [
                    {
                        "source_name": "chatbot_arena",
                        "source_label": "Chatbot Arena",
                        "benchmark_ids": ["chatbot_arena"],
                        "model_evidence_status": "current",
                    }
                ],
                "source_listings": [{
                    "source_name": "chatbot_arena",
                    "benchmark_id": "chatbot_arena",
                    "raw_model_name": "model-a",
                    "raw_model_key": "model-a",
                    "listing_status": "listed",
                    "source_revision": "a" * 40,
                    "publication_date": "2026-07-10",
                    "first_seen_at": "2026-07-10T00:00:00Z",
                    "last_seen_at": "2026-07-10T00:00:00Z",
                    "metadata": {"dataset_split": "text_style_control"},
                }],
            }
        ]

        bundle = render_model_metadata_csv_bundle(models)

        score_rows = list(csv.DictReader(io.StringIO(bundle["scores"])))
        self.assertEqual(score_rows[0]["benchmark_id"], "benchmark")
        self.assertEqual(score_rows[0]["value"], "95.0")
        self.assertEqual(score_rows[0]["confidence_lower"], "94.0")
        self.assertEqual(score_rows[0]["style_control"], "true")
        self.assertEqual(json.loads(score_rows[0]["source_metadata"])["dataset_revision"], "a" * 40)
        self.assertEqual(score_rows[0]["display_formatted"], "95%")
        self.assertEqual(score_rows[0]["display_direction"], "higher")
        self.assertEqual(score_rows[0]["comparison_status"], "comparable")
        self.assertEqual(score_rows[0]["strict_rank"], "2")
        self.assertEqual(score_rows[0]["strict_cohort_size"], "20")
        self.assertEqual(score_rows[0]["strict_median"], "82.0")
        self.assertEqual(score_rows[0]["strict_cohort_label"], "Comparable models")
        self.assertEqual(score_rows[0]["strict_position_band"], "Leading")
        self.assertEqual(score_rows[0]["broad_rank"], "4")
        self.assertEqual(score_rows[0]["broad_percentile"], "98.2")
        self.assertEqual(score_rows[0]["coverage_scored_count"], "169")
        self.assertEqual(score_rows[0]["coverage_eligible_count"], "233")
        self.assertEqual(score_rows[0]["evidence_label"], "2 task files")
        self.assertEqual(score_rows[0]["comparison_warnings"], "Broad cohort mixes task sets.")
        self.assertEqual(score_rows[0]["contributor_model_id"], "model-a")

        approval_rows = list(csv.DictReader(io.StringIO(bundle["use-case-approvals"])))
        self.assertEqual(approval_rows[0]["use_case_id"], "customer_support")
        self.assertEqual(approval_rows[0]["proposed_recommendation_required_controls"], "PIA")
        self.assertNotIn("effective_recommendation_status", approval_rows[0])

        suggestion_rows = list(csv.DictReader(io.StringIO(bundle["suggested-use-cases"])))
        self.assertEqual(suggestion_rows[0]["use_case_id"], "customer_support")
        self.assertEqual(suggestion_rows[0]["fit_score"], "88.4")
        self.assertEqual(suggestion_rows[0]["required_controls"], "Human escalation")

        destination_rows = list(csv.DictReader(io.StringIO(bundle["inference-destinations"])))
        self.assertEqual(destination_rows[0]["destination_id"], "aws-bedrock")
        self.assertEqual(destination_rows[0]["regions"], "ap-southeast-2")

        origin_rows = list(csv.DictReader(io.StringIO(bundle["provider-origin-countries"])))
        self.assertEqual(origin_rows[0]["country_code"], "AU")

        freshness_rows = list(csv.DictReader(io.StringIO(bundle["source-freshness"])))
        self.assertEqual(freshness_rows[0]["source_name"], "chatbot_arena")

        listing_rows = list(csv.DictReader(io.StringIO(bundle["source-listings"])))
        self.assertEqual(listing_rows[0]["listing_status"], "listed")
        self.assertEqual(listing_rows[0]["source_revision"], "a" * 40)

    def test_cli_list_models_writes_output_file(self) -> None:
        models = [{"id": "model-a", "name": "Model A", "provider": "Provider"}]

        with tempfile.TemporaryDirectory() as tempdir:
            output_path = Path(tempdir) / "models.json"
            stdout = io.StringIO()

            with patch("backend.cli.build_model_metadata_list", return_value=models), redirect_stdout(stdout):
                exit_code = cli.main(["list-models", "--output", str(output_path), "--no-csv"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), models)
            self.assertIn("Exported 1 models", stdout.getvalue())

    def test_cli_list_models_writes_default_csv_sidecar(self) -> None:
        models = [{"id": "model-a", "name": "Model A", "provider": "Provider"}]

        with tempfile.TemporaryDirectory() as tempdir:
            output_path = Path(tempdir) / "models.json"
            csv_output_path = Path(tempdir) / "model-list.csv"
            stdout = io.StringIO()

            with patch("backend.cli.build_model_metadata_list", return_value=models), redirect_stdout(stdout):
                exit_code = cli.main(
                    [
                        "list-models",
                        "--output",
                        str(output_path),
                        "--csv-output",
                        str(csv_output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), models)
            rows = list(csv.DictReader(io.StringIO(csv_output_path.read_text(encoding="utf-8"))))
            self.assertEqual(rows[0]["id"], "model-a")
            self.assertEqual(rows[0]["provider"], "Provider")
            self.assertTrue((Path(tempdir) / "model-list-scores.csv").exists())
            self.assertTrue((Path(tempdir) / "model-list-use-case-approvals.csv").exists())
            self.assertTrue((Path(tempdir) / "model-list-inference-destinations.csv").exists())
            self.assertTrue((Path(tempdir) / "model-list-provider-origin-countries.csv").exists())
            self.assertTrue((Path(tempdir) / "model-list-source-freshness.csv").exists())
            self.assertIn("Exported CSV sidecar", stdout.getvalue())
            self.assertIn("CSV companion files", stdout.getvalue())

    def test_cli_update_can_force_model_discovery_for_benchmark_scope(self) -> None:
        with patch(
            "backend.cli.run_update_now",
            return_value={"id": 12, "status": "completed", "scores_added": 0, "scores_updated": 0},
        ) as run_update_now:
            exit_code = cli.main(["update", "--benchmarks", "aa_cost", "--refresh-model-discovery"])

        self.assertEqual(exit_code, 0)
        run_update_now.assert_called_once_with(
            benchmarks=["aa_cost"],
            triggered_by="cli",
            refresh_model_discovery=True,
        )

    def test_cli_model_discovery_sync_prints_summary(self) -> None:
        stdout = io.StringIO()
        with patch(
            "backend.cli.refresh_model_discovery_metadata",
            return_value={"log_id": 7, "source": "huggingface", "records_found": 2},
        ) as refresh_model_discovery_metadata, redirect_stdout(stdout):
            exit_code = cli.main(["model-discovery-sync", "--source", "huggingface", "--family", "gemma"])

        self.assertEqual(exit_code, 0)
        refresh_model_discovery_metadata.assert_called_once_with(source="huggingface", family="gemma")
        self.assertIn('"records_found": 2', stdout.getvalue())

    def test_cli_model_discovery_sync_accepts_provider_api_source(self) -> None:
        stdout = io.StringIO()
        with patch(
            "backend.cli.refresh_model_discovery_metadata",
            return_value={"log_id": 8, "source": "provider-api", "records_found": 1},
        ) as refresh_model_discovery_metadata, redirect_stdout(stdout):
            exit_code = cli.main(["model-discovery-sync", "--source", "provider-api", "--family", "openai"])

        self.assertEqual(exit_code, 0)
        refresh_model_discovery_metadata.assert_called_once_with(source="provider-api", family="openai")
        self.assertIn('"source": "provider-api"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
