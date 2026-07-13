from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main, recommendation_engine, review_workbench, update_engine
from backend.database import (
    get_engine,
    init_db,
    model_inference_destinations as model_inference_destinations_table,
    model_use_case_approvals as model_use_case_approvals_table,
    models as models_table,
    scores as scores_table,
)
from backend.seed_data import seed_reference_data


class ReviewWorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.engine = get_engine(f"sqlite:///{Path(self.tempdir.name) / 'test.sqlite'}")
        init_db(self.engine)
        with self.engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

        self.original_engine = update_engine.ENGINE
        self.original_bootstrapped = update_engine.BOOTSTRAPPED
        self.original_token = os.environ.get(main.ADMIN_TOKEN_ENV_VAR)
        self.original_trusted_tailnet_writes = os.environ.get(main.TRUSTED_TAILNET_WRITES_ENV_VAR)
        update_engine.ENGINE = self.engine
        update_engine.BOOTSTRAPPED = True
        os.environ.pop(main.ADMIN_TOKEN_ENV_VAR, None)
        os.environ.pop(main.TRUSTED_TAILNET_WRITES_ENV_VAR, None)

    def tearDown(self) -> None:
        update_engine.ENGINE = self.original_engine
        update_engine.BOOTSTRAPPED = self.original_bootstrapped
        if self.original_token is None:
            os.environ.pop(main.ADMIN_TOKEN_ENV_VAR, None)
        else:
            os.environ[main.ADMIN_TOKEN_ENV_VAR] = self.original_token
        if self.original_trusted_tailnet_writes is None:
            os.environ.pop(main.TRUSTED_TAILNET_WRITES_ENV_VAR, None)
        else:
            os.environ[main.TRUSTED_TAILNET_WRITES_ENV_VAR] = self.original_trusted_tailnet_writes
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_review_app_and_catalog_are_readable(self) -> None:
        self._insert_review_model(
            "catalog-model",
            family_id="provider::catalog-family",
            release_date="2026-01-15",
            release_date_confidence="high",
        )
        self._insert_review_model(
            "speech-catalog-model",
            model_roles=["speech_to_text"],
            capabilities=["automatic-speech-recognition"],
            include_default_scores=False,
        )
        self._insert_review_model(
            "tts-catalog-model",
            model_roles=["text_to_speech"],
            capabilities=["text-to-speech"],
            include_default_scores=False,
        )
        self._insert_inference_destination("catalog-model", "azure-ai-foundry", "Azure AI Foundry")

        with patch("backend.main.bootstrap"):
            client = TestClient(main.app)
            app_response = client.get("/review")
            catalog_response = client.get("/api/review/catalog")

        self.assertEqual(app_response.status_code, 200)
        self.assertIn("Banking Model Review", app_response.text)
        self.assertIn("Effective recommendation", app_response.text)
        self.assertIn("Manual recommendation", app_response.text)
        self.assertIn("Restricted", app_response.text)
        self.assertIn('data-action="restricted"', app_response.text)
        self.assertIn("manualRecommendationFilter", app_response.text)
        self.assertIn("hasSavedManualRecommendation", app_response.text)
        self.assertIn('<option value="pending">Pending</option>', app_response.text)
        self.assertIn("useCaseApprovalStatus", app_response.text)
        self.assertIn('state.filters.approval !== "pending"', app_response.text)
        self.assertIn("All matching use cases", app_response.text)
        self.assertIn("countryFilter", app_response.text)
        self.assertIn("Country", app_response.text)
        self.assertIn("hyperscalerFilter", app_response.text)
        self.assertIn("Hyperscaler availability", app_response.text)
        self.assertIn("runUpdates", app_response.text)
        self.assertIn("Run updates", app_response.text)
        self.assertIn("updateProgressPanel", app_response.text)
        self.assertIn("/api/update/status/", app_response.text)
        self.assertIn("updateSummaryPanel", app_response.text)
        self.assertIn("renderUpdateChangeSummary", app_response.text)
        self.assertIn("Latest update changes", app_response.text)
        self.assertIn('sort: { key: "release_date", direction: "desc" }', app_response.text)
        self.assertIn('name="model_roles"', app_response.text)
        self.assertIn('value="embedding"', app_response.text)
        self.assertIn("body.model_roles = [body.model_roles]", app_response.text)
        self.assertIn("preferredUseCaseIdForModel", app_response.text)
        self.assertIn("bulkUseCaseIdForModels", app_response.text)
        self.assertIn('${header("release_date", "Release")}', app_response.text)
        self.assertIn("modelReleaseInfo", app_response.text)
        self.assertIn("best_release_date", app_response.text)
        self.assertNotIn('${header("approval_updated_at", "Updated")}', app_response.text)
        self.assertIn("Unreviewed", app_response.text)
        self.assertIn("general_approval_status", app_response.text)
        self.assertIn('data-inspector-tab="controls"', app_response.text)
        self.assertIn('data-inspector-tab="activity"', app_response.text)
        self.assertIn('data-inspector-tab="notes"', app_response.text)
        self.assertIn("renderControlsPanel", app_response.text)
        self.assertIn("renderActivityPanel", app_response.text)
        self.assertIn("renderNotesPanel", app_response.text)
        self.assertIn("Rankings", app_response.text)
        self.assertIn("renderRankingsView", app_response.text)
        self.assertIn("rankingUseCaseSelect", app_response.text)
        self.assertIn("rankingBenchmarkSelect", app_response.text)
        self.assertIn("/api/rankings?use_case=", app_response.text)
        self.assertIn("/api/benchmarks", app_response.text)
        self.assertIn("Benchmark leaderboard", app_response.text)
        self.assertIn("benchmarkCompatibleRoles", app_response.text)
        self.assertIn("Speech to text", app_response.text)
        self.assertIn("Text to speech", app_response.text)
        self.assertIn("capabilityFilter", app_response.text)
        self.assertIn("Capability", app_response.text)
        self.assertIn("General approval", app_response.text)
        self.assertIn("approve_model", app_response.text)
        self.assertIn("model_type_primary", app_response.text)
        self.assertIn("strongest_signal_kind", app_response.text)
        self.assertIn("evidenceForExport", app_response.text)
        self.assertEqual(catalog_response.status_code, 200)
        payload = catalog_response.json()
        self.assertGreaterEqual(payload["summary"]["model_count"], 1)
        self.assertIn("models", payload)
        self.assertIn("families", payload)
        self.assertIn("facets", payload)
        self.assertIn("countries", payload["facets"])
        self.assertTrue(payload["facets"]["countries"])
        self.assertIn("hyperscalers", payload["facets"])
        capability_counts = {item["id"]: item["count"] for item in payload["facets"]["capabilities"]}
        self.assertGreaterEqual(capability_counts.get("automatic-speech-recognition", 0), 1)
        self.assertGreaterEqual(capability_counts.get("text-to-speech", 0), 1)
        role_counts = {item["id"]: item["count"] for item in payload["facets"]["model_roles"]}
        self.assertGreaterEqual(role_counts.get("speech_to_text", 0), 1)
        self.assertGreaterEqual(role_counts.get("text_to_speech", 0), 1)
        general_approval_counts = {item["id"]: item["count"] for item in payload["facets"]["general_approvals"]}
        self.assertGreaterEqual(general_approval_counts.get("unreviewed", 0), 1)
        hyperscaler_names = {item["name"] for item in payload["facets"]["hyperscalers"]}
        self.assertIn("Any hyperscaler", hyperscaler_names)
        self.assertIn("Azure AI Foundry", hyperscaler_names)
        self.assertIn("No hyperscaler route", hyperscaler_names)
        model = next(model for model in payload["models"] if model["id"] == "catalog-model")
        self.assertFalse(model["general_approved_for_use"])
        self.assertEqual(model["general_approval_status"], "unreviewed")
        self.assertIn("Azure AI Foundry", model["inference_summary"]["platform_names"])
        self.assertEqual(model["release_date"], "2026-01-15")
        self.assertEqual(model["release_date_confidence"], "high")
        self.assertEqual(model["model_age_basis"], "release_date")
        self.assertEqual(model["model_type_primary"], "frontier")
        self.assertIn("frontier", model["model_type_tags"])
        self.assertIn("hyperscaler_available", model["model_type_tags"])
        self.assertEqual(model["strongest_signal_kind"], "hyperscaler")
        self.assertEqual(model["hyperscaler_signal"], "Azure AI Foundry")
        speech_model = next(model for model in payload["models"] if model["id"] == "speech-catalog-model")
        self.assertEqual(speech_model["model_type_primary"], "speech_to_text")
        self.assertEqual(speech_model["evidence_context_use_case_id"], "voice_to_text")
        tts_model = next(model for model in payload["models"] if model["id"] == "tts-catalog-model")
        self.assertEqual(tts_model["model_type_primary"], "text_to_speech")
        self.assertEqual(tts_model["evidence_context_use_case_id"], "text_to_speech")

    def test_review_catalog_adds_ranked_benchmark_selection_evidence(self) -> None:
        self._insert_review_model("ranked-generator")
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": "ranked-generator",
                        "benchmark_id": "aa_intelligence",
                        "value": 55.0,
                        "raw_value": "55.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_url": "https://example.com/aa",
                        "source_type": "primary",
                        "verified": 1,
                    },
                    {
                        "model_id": "ranked-generator",
                        "benchmark_id": "gpqa_diamond",
                        "value": 80.0,
                        "raw_value": "80.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_url": "https://example.com/gpqa",
                        "source_type": "primary",
                        "verified": 1,
                    }
                ],
            )

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "ranked-generator")

        self.assertEqual(model["model_type_primary"], "frontier")
        self.assertEqual(model["evidence_context_use_case_id"], "general_reasoning")
        self.assertEqual(model["strongest_signal_kind"], "benchmark")
        self.assertEqual(model["strongest_signal_label"], "AA Intel")
        self.assertIsNotNone(model["ranking_rank"])
        self.assertGreater(model["ranking_score"], 0)
        self.assertEqual(model["cost_signal"], "Cost: 0.2")
        self.assertEqual(model["speed_signal"], "Speed: 120.0")
        self.assertIn("general_reasoning", model["selection_evidence_by_use_case"])

    def test_review_catalog_adds_embedding_reranker_and_local_sml_types(self) -> None:
        self._insert_review_model("embedding-model", model_roles=["embedding"], include_default_scores=False)
        self._insert_review_model("reranker-model", model_roles=["reranker"], include_default_scores=False)
        self._insert_review_model("tts-model", model_roles=["text_to_speech"], include_default_scores=False)
        self._insert_review_model(
            "local-small-model",
            model_type="open_weights",
            model_roles=["generator"],
            small_model_candidate=True,
            model_size_class="small",
            parameter_count_b=4.0,
            include_default_scores=False,
        )
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": "embedding-model",
                        "benchmark_id": "mteb_retrieval",
                        "value": 70.0,
                        "raw_value": "70.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_type": "primary",
                        "verified": 1,
                    },
                    {
                        "model_id": "reranker-model",
                        "benchmark_id": "mteb_reranking",
                        "value": 72.0,
                        "raw_value": "72.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_type": "primary",
                        "verified": 1,
                    },
                    {
                        "model_id": "tts-model",
                        "benchmark_id": "aa_tts_quality_elo",
                        "value": 1213.0,
                        "raw_value": "1213.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_type": "primary",
                        "verified": 1,
                    },
                ],
            )

        models = {model["id"]: model for model in review_workbench.build_review_catalog()["models"]}

        self.assertEqual(models["embedding-model"]["model_type_primary"], "embedding")
        self.assertEqual(models["embedding-model"]["evidence_context_use_case_id"], "retrieval_embeddings")
        self.assertEqual(models["embedding-model"]["strongest_signal_kind"], "benchmark")
        self.assertEqual(models["reranker-model"]["model_type_primary"], "reranker")
        self.assertEqual(models["reranker-model"]["evidence_context_use_case_id"], "retrieval_reranking")
        self.assertEqual(models["reranker-model"]["strongest_signal_kind"], "benchmark")
        self.assertEqual(models["tts-model"]["model_type_primary"], "text_to_speech")
        self.assertEqual(models["tts-model"]["evidence_context_use_case_id"], "text_to_speech")
        self.assertEqual(models["tts-model"]["strongest_signal_kind"], "benchmark")
        self.assertEqual(models["local-small-model"]["model_type_primary"], "local_sml")
        self.assertIn("local_sml", models["local-small-model"]["model_type_tags"])
        self.assertEqual(models["local-small-model"]["strongest_signal_kind"], "local_sml")
        self.assertEqual(models["local-small-model"]["strongest_signal_value"], "4.0B parameters")

    def test_review_catalog_prefers_approved_route_before_hyperscaler_fallback(self) -> None:
        self._insert_review_model("approved-route-model", include_default_scores=False)
        self._insert_inference_destination(
            "approved-route-model",
            "azure-ai-foundry",
            "Azure AI Foundry",
            regions=["ap-southeast-2"],
        )
        update_engine.update_model_use_case_inference_approval(
            "approved-route-model",
            "customer_support",
            "azure-ai-foundry",
            "Australia",
            True,
            "Approved Australian route.",
        )

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "approved-route-model")

        self.assertEqual(model["strongest_signal_kind"], "approved_inference_route")
        self.assertIn("Approved route: Azure AI Foundry", model["strongest_signal_label"])
        self.assertEqual(model["strongest_signal_notes"], "Approved Australian route.")

    def test_review_catalog_uses_australia_route_fallback(self) -> None:
        self._insert_review_model("australia-route-model", include_default_scores=False, model_card_url=None)
        self._insert_inference_destination(
            "australia-route-model",
            "aws-bedrock",
            "AWS Bedrock",
            hyperscaler="AWS",
            regions=["ap-southeast-2", "us-east-1"],
        )

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "australia-route-model")

        self.assertEqual(model["strongest_signal_kind"], "inference_location")
        self.assertEqual(model["strongest_signal_label"], "Australia inference route")
        self.assertIn("australia_route", model["model_type_tags"])
        self.assertIn("ap-southeast-2", model["inference_location_signal"])

    def test_review_catalog_marks_models_without_selection_evidence(self) -> None:
        self._insert_review_model("no-evidence-model", include_default_scores=False, model_card_url=None)

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "no-evidence-model")

        self.assertEqual(model["strongest_signal_kind"], "insufficient_evidence")
        self.assertEqual(model["strongest_signal_label"], "Insufficient evidence")

    def test_review_decision_route_requires_admin_token(self) -> None:
        self._insert_review_model("guard-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={"model_ids": ["guard-model"], "use_case_ids": ["customer_support"], "recommendation_status": "recommended"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn(main.ADMIN_TOKEN_ENV_VAR, response.json()["detail"])

    def test_review_decision_route_saves_bulk_decisions_and_catalog_status(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("bulk-a", family_id="provider::bulk-family")
        self._insert_review_model("bulk-b", family_id="provider::bulk-family")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={
                    "model_ids": ["bulk-a", "bulk-b"],
                    "use_case_ids": ["customer_support"],
                    "approved_for_use": True,
                    "recommendation_status": "recommended",
                    "approval_notes": "Approved by workbench.",
                    "recommendation_notes": "Preferred for this review.",
                    "catalog_status": "deprecated",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["updated_count"], 2)
        self.assertEqual(payload["catalog_status_updated_count"], 2)
        with self.engine.begin() as conn:
            approval_rows = conn.execute(
                model_use_case_approvals_table.select().where(
                    model_use_case_approvals_table.c.model_id.in_(["bulk-a", "bulk-b"])
                )
            ).mappings().all()
            model_rows = conn.execute(
                models_table.select().where(models_table.c.id.in_(["bulk-a", "bulk-b"]))
            ).mappings().all()
        self.assertEqual({row["recommendation_status"] for row in approval_rows}, {"recommended"})
        self.assertEqual({row["approved_for_use"] for row in approval_rows}, {1})
        self.assertEqual({row["catalog_status"] for row in model_rows}, {"deprecated"})

    def test_review_decision_route_saves_restricted_recommendation(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("restricted-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={
                    "model_ids": ["restricted-model"],
                    "use_case_ids": ["safety_compliance"],
                    "recommendation_status": "restricted",
                    "recommendation_notes": "Cyber model limited to approved cyber team members.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        model = next(model for model in update_engine.list_models() if model["id"] == "restricted-model")
        approval = model["use_case_approvals"]["safety_compliance"]
        self.assertEqual(approval["recommendation_status"], "restricted")
        self.assertEqual(approval["effective_recommendation_status"], "restricted")
        self.assertEqual(approval["recommendation_notes"], "Cyber model limited to approved cyber team members.")

    def test_review_decision_route_can_clear_approval_boolean(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("unapprove-model")
        review_workbench.apply_review_decisions(
            model_ids=["unapprove-model"],
            use_case_ids=["customer_support"],
            approved_for_use=True,
            recommendation_status="recommended",
        )

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={
                    "model_ids": ["unapprove-model"],
                    "use_case_ids": ["customer_support"],
                    "approved_for_use": False,
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 1)
        model = next(model for model in update_engine.list_models() if model["id"] == "unapprove-model")
        approval = model["use_case_approvals"]["customer_support"]
        self.assertFalse(approval["approved_for_use"])
        self.assertEqual(approval["recommendation_status"], "recommended")

    def test_review_model_approval_route_updates_general_state_only(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("general-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/model-approvals",
                json={
                    "model_ids": ["general-model"],
                    "approved_for_use": True,
                    "approval_notes": "Generally approved for model catalog use.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 1)
        with self.engine.begin() as conn:
            model_row = conn.execute(
                models_table.select().where(models_table.c.id == "general-model")
            ).mappings().one()
            approval_rows = conn.execute(
                model_use_case_approvals_table.select().where(
                    model_use_case_approvals_table.c.model_id == "general-model"
                )
            ).mappings().all()
        self.assertEqual(model_row["general_approved_for_use"], 1)
        self.assertEqual(model_row["general_approval_notes"], "Generally approved for model catalog use.")
        self.assertEqual(approval_rows, [])

        review_workbench.apply_review_decisions(
            model_ids=["general-model"],
            use_case_ids=["customer_support"],
            approved_for_use=False,
            recommendation_status="not_recommended",
        )
        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "general-model")
        self.assertTrue(model["general_approved_for_use"])
        self.assertFalse(model["use_case_approvals"]["customer_support"]["approved_for_use"])

    def test_review_model_approval_route_tracks_unreviewed_state(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("triage-model")

        with patch("backend.main.bootstrap"):
            client = TestClient(main.app)
            not_approved_response = client.post(
                "/api/review/model-approvals",
                json={
                    "model_ids": ["triage-model"],
                    "approval_status": "not_approved",
                    "approval_notes": "Reviewed and rejected for general use.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(not_approved_response.status_code, 200)
        self.assertEqual(not_approved_response.json()["approval_status"], "not_approved")
        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "triage-model")
        self.assertFalse(model["general_approved_for_use"])
        self.assertEqual(model["general_approval_status"], "not_approved")
        self.assertIsNotNone(model["general_approval_updated_at"])

        with patch("backend.main.bootstrap"):
            unreviewed_response = TestClient(main.app).post(
                "/api/review/model-approvals",
                json={
                    "model_ids": ["triage-model"],
                    "approval_status": "unreviewed",
                    "approval_notes": "Should be cleared.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(unreviewed_response.status_code, 200)
        self.assertEqual(unreviewed_response.json()["approval_status"], "unreviewed")
        with self.engine.begin() as conn:
            row = conn.execute(models_table.select().where(models_table.c.id == "triage-model")).mappings().one()
        self.assertEqual(row["general_approved_for_use"], 0)
        self.assertIsNone(row["general_approval_notes"])
        self.assertIsNone(row["general_approval_updated_at"])
        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "triage-model")
        self.assertEqual(model["general_approval_status"], "unreviewed")

    def test_seed_reapply_preserves_general_model_approval(self) -> None:
        review_workbench.apply_model_approvals(
            model_ids=["gpt-5-4"],
            approved_for_use=True,
            approval_notes="General approval survives seed refresh.",
        )

        with self.engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

        model = next(model for model in update_engine.list_models() if model["id"] == "gpt-5-4")
        self.assertTrue(model["general_approved_for_use"])
        self.assertEqual(model["general_approval_notes"], "General approval survives seed refresh.")

    def test_add_model_route_creates_manual_listing(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/models",
                json={
                    "name": "Manual Workbench Model",
                    "provider": "Manual Provider",
                    "model_roles": "embedding",
                    "catalog_status": "provisional",
                    "notes": "Added in the review workbench.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_id"], "manual-workbench-model")
        model = next(model for model in update_engine.list_models() if model["id"] == "manual-workbench-model")
        self.assertEqual(model["catalog_status"], "provisional")
        self.assertEqual(model["model_roles"], ["embedding"])
        self.assertEqual(model["metadata_source_name"], "manual")

    def test_manual_decision_survives_bootstrap_and_recommendation_sync(self) -> None:
        self._insert_review_model("persistence-model")

        review_workbench.apply_review_decisions(
            model_ids=["persistence-model"],
            use_case_ids=["customer_support"],
            approved_for_use=True,
            recommendation_status="recommended",
            recommendation_notes="Human decision survives generated proposals.",
        )
        update_engine.BOOTSTRAPPED = False
        update_engine.bootstrap()
        recommendation_engine.sync_recommendation_proposals()

        model = next(model for model in update_engine.list_models() if model["id"] == "persistence-model")
        approval = model["use_case_approvals"]["customer_support"]
        self.assertTrue(approval["approved_for_use"])
        self.assertEqual(approval["recommendation_status"], "recommended")
        self.assertEqual(approval["effective_recommendation_status"], "recommended")

    def test_snapshot_export_import_restores_manual_models_statuses_and_decisions(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        review_workbench.add_review_model(
            name="Snapshot Manual Model",
            provider="Snapshot Provider",
            model_id="snapshot-manual-model",
            catalog_status="deprecated",
            notes="Manual snapshot model.",
        )
        review_workbench.apply_review_decisions(
            model_ids=["snapshot-manual-model"],
            use_case_ids=["customer_support"],
            approved_for_use=True,
            recommendation_status="not_recommended",
            recommendation_notes="Snapshot decision.",
        )
        review_workbench.apply_model_approvals(
            model_ids=["snapshot-manual-model"],
            approved_for_use=True,
            approval_notes="Snapshot general model approval.",
        )

        with patch("backend.main.bootstrap"):
            client = TestClient(main.app)
            export_response = client.post(
                "/api/review/snapshots/export",
                json={},
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )
        self.assertEqual(export_response.status_code, 200)
        snapshot = export_response.json()
        self.assertEqual(len(snapshot["model_approvals"]), 1)
        self.assertEqual(snapshot["model_approvals"][0]["approval_status"], "approved")

        second_tempdir = tempfile.TemporaryDirectory()
        second_engine = get_engine(f"sqlite:///{Path(second_tempdir.name) / 'import.sqlite'}")
        init_db(second_engine)
        with second_engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

        active_engine = update_engine.ENGINE
        active_bootstrapped = update_engine.BOOTSTRAPPED
        try:
            update_engine.ENGINE = second_engine
            update_engine.BOOTSTRAPPED = True
            with patch("backend.main.bootstrap"):
                import_response = TestClient(main.app).post(
                    "/api/review/snapshots/import",
                    json=snapshot,
                    headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
                )
            self.assertEqual(import_response.status_code, 200)
            self.assertEqual(import_response.json()["created_manual_model_count"], 1)
            self.assertEqual(import_response.json()["model_approval_updated_count"], 1)
            imported_model = next(
                model for model in update_engine.list_models() if model["id"] == "snapshot-manual-model"
            )
            self.assertEqual(imported_model["catalog_status"], "deprecated")
            self.assertTrue(imported_model["general_approved_for_use"])
            self.assertEqual(imported_model["general_approval_notes"], "Snapshot general model approval.")
            approval = imported_model["use_case_approvals"]["customer_support"]
            self.assertTrue(approval["approved_for_use"])
            self.assertEqual(approval["recommendation_status"], "not_recommended")
        finally:
            update_engine.ENGINE = active_engine
            update_engine.BOOTSTRAPPED = active_bootstrapped
            second_engine.dispose()
            second_tempdir.cleanup()

    def _insert_review_model(
        self,
        model_id: str,
        *,
        family_id: str = "provider::review-model",
        family_name: str = "Review Model",
        release_date: str | None = None,
        release_date_confidence: str | None = None,
        model_type: str = "proprietary",
        model_roles: list[str] | None = None,
        small_model_candidate: bool = False,
        model_size_class: str | None = None,
        parameter_count_b: float | None = None,
        include_default_scores: bool = True,
        model_card_url: str | None = "https://example.com/model-card",
        capabilities: list[str] | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                {
                    "id": model_id,
                    "name": model_id,
                    "provider": "Bank Test Provider",
                    "type": model_type,
                    "catalog_status": "tracked",
                    "family_id": family_id,
                    "family_name": family_name,
                    "canonical_model_id": family_id,
                    "canonical_model_name": family_name,
                    "model_roles_json": json.dumps(model_roles or ["generator"], ensure_ascii=True),
                    "model_card_url": model_card_url,
                    "model_card_verified_at": "2026-07-01T00:00:00Z" if model_card_url else None,
                    "release_date": release_date,
                    "release_date_precision": "day" if release_date else None,
                    "release_date_confidence": release_date_confidence,
                    "release_date_source_name": "test-fixture" if release_date else None,
                    "release_date_source_url": "https://example.com/release" if release_date else None,
                    "release_date_verified_at": "2026-07-01T00:00:00Z" if release_date else None,
                    "parameter_count_b": parameter_count_b,
                    "model_size_class": model_size_class,
                    "small_model_candidate": 1 if small_model_candidate else 0,
                    "model_size_source_name": "test-fixture" if parameter_count_b is not None or model_size_class else None,
                    "model_size_source_url": "https://example.com/model-size" if parameter_count_b is not None or model_size_class else None,
                    "model_size_verified_at": "2026-07-01T00:00:00Z" if parameter_count_b is not None or model_size_class else None,
                    "license_id": "apache-2.0",
                    "license_name": "Apache 2.0",
                    "training_data_summary": "Reviewed public and licensed data.",
                    "capabilities_json": json.dumps(capabilities or [], ensure_ascii=True),
                    "active": 1,
                },
            )
            if not include_default_scores:
                return
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": model_id,
                        "benchmark_id": benchmark_id,
                        "value": value,
                        "raw_value": str(value),
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_type": "primary",
                        "verified": 1,
                    }
                    for benchmark_id, value in (
                        ("chatbot_arena", 1400.0),
                        ("aa_cost", 0.20),
                        ("aa_speed", 120.0),
                        ("ifeval", 82.0),
                        ("ailuminate", 75.0),
                    )
                ],
            )

    def _insert_inference_destination(
        self,
        model_id: str,
        destination_id: str,
        name: str,
        *,
        hyperscaler: str = "Azure",
        regions: list[str] | None = None,
    ) -> None:
        resolved_regions = regions or ["eastus2"]
        with self.engine.begin() as conn:
            conn.execute(
                model_inference_destinations_table.insert(),
                {
                    "model_id": model_id,
                    "destination_id": destination_id,
                    "name": name,
                    "hyperscaler": hyperscaler,
                    "availability_scope": "Configured account",
                    "availability_note": "Live from configured hyperscaler catalog.",
                    "location_scope": "Configured account regions",
                    "regions_json": json.dumps(resolved_regions, ensure_ascii=True),
                    "region_count": len(resolved_regions),
                    "deployment_modes_json": '["Provisioned"]',
                    "pricing_label": "Configured account pricing",
                    "pricing_note": "Pricing depends on configured account.",
                    "sources_json": "[]",
                    "catalog_model_id": model_id,
                    "synced_at": "2026-07-01T00:00:00Z",
                },
            )


if __name__ == "__main__":
    unittest.main()
