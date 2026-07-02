from __future__ import annotations

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
        self._insert_review_model("catalog-model", family_id="provider::catalog-family")

        with patch("backend.main.bootstrap"):
            client = TestClient(main.app)
            app_response = client.get("/review")
            catalog_response = client.get("/api/review/catalog")

        self.assertEqual(app_response.status_code, 200)
        self.assertIn("Banking Model Review", app_response.text)
        self.assertIn("Effective recommendation", app_response.text)
        self.assertIn("Manual recommendation", app_response.text)
        self.assertIn("manualRecommendationFilter", app_response.text)
        self.assertIn("General approval", app_response.text)
        self.assertIn("approve_model", app_response.text)
        self.assertEqual(catalog_response.status_code, 200)
        payload = catalog_response.json()
        self.assertGreaterEqual(payload["summary"]["model_count"], 1)
        self.assertIn("models", payload)
        self.assertIn("families", payload)
        self.assertIn("facets", payload)
        model = next(model for model in payload["models"] if model["id"] == "catalog-model")
        self.assertFalse(model["general_approved_for_use"])

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
                    "model_roles": ["generator"],
                    "catalog_status": "provisional",
                    "notes": "Added in the review workbench.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_id"], "manual-workbench-model")
        model = next(model for model in update_engine.list_models() if model["id"] == "manual-workbench-model")
        self.assertEqual(model["catalog_status"], "provisional")
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
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                {
                    "id": model_id,
                    "name": model_id,
                    "provider": "Bank Test Provider",
                    "type": "proprietary",
                    "catalog_status": "tracked",
                    "family_id": family_id,
                    "family_name": family_name,
                    "canonical_model_id": family_id,
                    "canonical_model_name": family_name,
                    "model_card_url": "https://example.com/model-card",
                    "model_card_verified_at": "2026-07-01T00:00:00Z",
                    "license_id": "apache-2.0",
                    "license_name": "Apache 2.0",
                    "training_data_summary": "Reviewed public and licensed data.",
                    "active": 1,
                },
            )
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


if __name__ == "__main__":
    unittest.main()
