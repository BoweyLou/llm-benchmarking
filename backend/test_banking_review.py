from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from backend import banking_review, cli, update_engine
from backend.database import (
    get_engine,
    init_db,
    model_use_case_approvals as model_use_case_approvals_table,
    models as models_table,
    scores as scores_table,
)
from backend.seed_data import seed_reference_data


class BankingReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.engine = get_engine(f"sqlite:///{Path(self.tempdir.name) / 'test.sqlite'}")
        init_db(self.engine)
        with self.engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

        self.original_engine = update_engine.ENGINE
        self.original_bootstrapped = update_engine.BOOTSTRAPPED
        update_engine.ENGINE = self.engine
        update_engine.BOOTSTRAPPED = True

    def tearDown(self) -> None:
        update_engine.ENGINE = self.original_engine
        update_engine.BOOTSTRAPPED = self.original_bootstrapped
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_render_banking_review_csv_combines_model_and_approval_fields(self) -> None:
        rendered = banking_review.render_banking_review_csv(
            [
                {
                    "id": "model-a",
                    "name": "Model A",
                    "provider": "Provider",
                    "family_id": "provider::model-a",
                    "family_name": "Model A",
                    "catalog_status": "tracked",
                    "active": True,
                    "use_case_approvals": {
                        "customer_support": {
                            "use_case_id": "customer_support",
                            "approved_for_use": True,
                            "recommendation_status": "recommended",
                            "proposed_recommendation_status": "not_recommended",
                            "effective_recommendation_status": "recommended",
                            "proposed_recommendation_blockers": ["routing"],
                        }
                    },
                }
            ]
        )

        rows = list(csv.DictReader(io.StringIO(rendered)))
        self.assertEqual(rows[0]["model_id"], "model-a")
        self.assertEqual(rows[0]["use_case_id"], "customer_support")
        self.assertEqual(rows[0]["family_id"], "provider::model-a")
        self.assertEqual(rows[0]["recommendation_status"], "recommended")
        self.assertEqual(rows[0]["proposed_recommendation_status"], "not_recommended")
        self.assertEqual(rows[0]["proposed_recommendation_blockers"], "routing")

    def test_export_syncs_banking_proposals_into_combined_csv(self) -> None:
        self._insert_review_model("bank-export-model")
        output_path = Path(self.tempdir.name) / "banking.csv"

        summary = banking_review.export_banking_review_list(output_path)

        self.assertEqual(summary["output_path"], str(output_path))
        self.assertTrue(summary["synced_proposals"])
        self.assertGreater(summary["stored_proposal_count"], 0)
        rows = list(csv.DictReader(io.StringIO(output_path.read_text(encoding="utf-8"))))
        matching_rows = [row for row in rows if row["model_id"] == "bank-export-model"]
        self.assertTrue(matching_rows)
        self.assertIn("proposed_recommendation_status", matching_rows[0])

    def test_set_review_state_can_update_whole_family(self) -> None:
        self._insert_review_model("family-a", family_id="provider::review-family", family_name="Review Family")
        self._insert_review_model("family-b", family_id="provider::review-family", family_name="Review Family")

        summary = banking_review.set_review_state(
            family_ids=["provider::review-family"],
            use_case_ids=["customer_support"],
            approved_for_use=True,
            recommendation_status="recommended",
            approval_notes="Approved for bank pilot.",
            recommendation_notes="Preferred family for this use case.",
        )

        self.assertEqual(summary["target_model_count"], 2)
        self.assertEqual(summary["updated_count"], 2)
        models = {model["id"]: model for model in update_engine.list_models()}
        for model_id in ("family-a", "family-b"):
            approval = models[model_id]["use_case_approvals"]["customer_support"]
            self.assertTrue(approval["approved_for_use"])
            self.assertEqual(approval["recommendation_status"], "recommended")
            self.assertEqual(approval["approval_notes"], "Approved for bank pilot.")

    def test_set_review_state_preserves_recommendation_timestamp_for_approval_only_update(self) -> None:
        self._insert_review_model("timestamp-model")
        banking_review.set_review_state(
            model_ids=["timestamp-model"],
            use_case_ids=["customer_support"],
            recommendation_status="recommended",
            recommendation_notes="Initial recommendation.",
        )
        first_row = self._approval_row("timestamp-model", "customer_support")

        banking_review.set_review_state(
            model_ids=["timestamp-model"],
            use_case_ids=["customer_support"],
            approved_for_use=True,
            approval_notes="Approved after review.",
        )
        second_row = self._approval_row("timestamp-model", "customer_support")

        self.assertEqual(second_row["recommendation_status"], "recommended")
        self.assertEqual(second_row["recommendation_notes"], "Initial recommendation.")
        self.assertEqual(second_row["recommendation_updated_at"], first_row["recommendation_updated_at"])

    def test_add_model_and_deprecate_keeps_listing_export_visible(self) -> None:
        added = banking_review.add_model_to_listing(
            name="Manual Banking Model",
            provider="Manual Provider",
            model_roles=["generator"],
            notes="Added from banking review.",
        )
        self.assertEqual(added["model_id"], "manual-banking-model")

        deprecated = banking_review.deprecate_listings(
            model_ids=["manual-banking-model"],
            notes="Deprecated from review.",
            mark_not_recommended=True,
            use_case_ids=["customer_support"],
        )

        self.assertEqual(deprecated["deprecated_count"], 1)
        model = next(model for model in update_engine.list_models() if model["id"] == "manual-banking-model")
        self.assertEqual(model["catalog_status"], "deprecated")
        self.assertTrue(model["active"])
        approval = model["use_case_approvals"]["customer_support"]
        self.assertEqual(approval["recommendation_status"], "not_recommended")

    def test_cli_banking_review_set_writes_json_summary(self) -> None:
        self._insert_review_model("cli-review-model")
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = cli.main(
                [
                    "banking-review",
                    "set",
                    "--model-id",
                    "cli-review-model",
                    "--use-case",
                    "customer_support",
                    "--approval",
                    "approved",
                    "--recommendation",
                    "recommended",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["updated_count"], 1)

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

    def _approval_row(self, model_id: str, use_case_id: str) -> dict:
        with self.engine.begin() as conn:
            return dict(
                conn.execute(
                    model_use_case_approvals_table.select().where(
                        model_use_case_approvals_table.c.model_id == model_id,
                        model_use_case_approvals_table.c.use_case_id == use_case_id,
                    )
                )
                .mappings()
                .one()
            )


if __name__ == "__main__":
    unittest.main()
