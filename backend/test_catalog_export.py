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

        approval_rows = list(csv.DictReader(io.StringIO(bundle["use-case-approvals"])))
        self.assertEqual(approval_rows[0]["use_case_id"], "customer_support")
        self.assertEqual(approval_rows[0]["proposed_recommendation_required_controls"], "PIA")
        self.assertNotIn("effective_recommendation_status", approval_rows[0])

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
