from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend import recommendation_engine, update_engine
from backend.database import (
    get_engine,
    init_db,
    model_use_case_inference_approvals as model_use_case_inference_approvals_table,
    model_use_case_recommendation_proposals as recommendation_proposals_table,
    models as models_table,
    scores as scores_table,
)
from backend.seed_data import seed_reference_data


class RecommendationEngineTests(unittest.TestCase):
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

    def test_customer_support_policy_requires_australian_approved_route(self) -> None:
        benchmarks = _customer_support_benchmarks()
        use_case = _use_case("customer_support")
        base_model = _model_payload("bank-good")

        summary = recommendation_engine.build_recommendation_proposals(
            models=[
                {
                    **base_model,
                    "use_case_approvals": {
                        "customer_support": {
                            "inference_route_approvals": [
                                {
                                    "approved_for_use": True,
                                    "location_key": "australia",
                                    "location_label": "Australia",
                                }
                            ]
                        }
                    },
                },
                _model_payload("bank-missing-route"),
            ],
            benchmarks=benchmarks,
            use_cases=[use_case],
            computed_at="2026-07-01T00:00:00Z",
        )

        proposals = {proposal["model_id"]: proposal for proposal in summary["proposals"]}
        self.assertEqual(proposals["bank-good"]["proposed_status"], "recommended")
        self.assertEqual(proposals["bank-missing-route"]["proposed_status"], "not_recommended")
        self.assertIn(
            "routing: No bank-approved inference route is recorded for this use case.",
            proposals["bank-missing-route"]["blockers"],
        )

    def test_sync_persists_proposals_and_list_models_exposes_effective_status(self) -> None:
        self._insert_bank_model(
            "bank-route-missing",
            model_card_url="https://example.com/model-card",
            model_card_verified_at="2026-07-01T00:00:00Z",
        )
        self._insert_customer_support_scores("bank-route-missing")

        sync_summary = recommendation_engine.sync_recommendation_proposals(
            use_case_ids=["customer_support"],
            engine=self.engine,
        )
        self.assertGreater(sync_summary["stored_count"], 0)

        with self.engine.begin() as conn:
            row = conn.execute(
                recommendation_proposals_table.select().where(
                    recommendation_proposals_table.c.model_id == "bank-route-missing",
                    recommendation_proposals_table.c.use_case_id == "customer_support",
                )
            ).mappings().one()
        self.assertEqual(row["proposed_status"], "not_recommended")
        self.assertIn("routing", json.loads(row["blockers_json"])[0])

        update_engine.update_model_use_case_approval(
            "bank-route-missing",
            "customer_support",
            True,
            "Approved with compensating controls.",
            "recommended",
            "Manual executive risk acceptance.",
        )
        model = next(model for model in update_engine.list_models() if model["id"] == "bank-route-missing")
        approval = model["use_case_approvals"]["customer_support"]

        self.assertEqual(approval["proposed_recommendation_status"], "not_recommended")
        self.assertEqual(approval["recommendation_status"], "recommended")
        self.assertEqual(approval["effective_recommendation_status"], "recommended")
        self.assertTrue(approval["proposed_recommendation_blockers"])

    def test_sync_recommends_when_sensitive_controls_are_present(self) -> None:
        self._insert_bank_model(
            "bank-ready",
            model_card_url="https://example.com/model-card",
            model_card_verified_at="2026-07-01T00:00:00Z",
        )
        self._insert_customer_support_scores("bank-ready")
        with self.engine.begin() as conn:
            conn.execute(
                model_use_case_inference_approvals_table.insert(),
                {
                    "model_id": "bank-ready",
                    "use_case_id": "customer_support",
                    "destination_id": "azure-ai-foundry",
                    "location_key": "australia",
                    "location_label": "Australia",
                    "approved_for_use": 1,
                    "approval_notes": "Approved Australian-hosted route.",
                    "approval_updated_at": "2026-07-01T00:00:00Z",
                },
            )

        recommendation_engine.sync_recommendation_proposals(
            use_case_ids=["customer_support"],
            engine=self.engine,
        )
        model = next(model for model in update_engine.list_models() if model["id"] == "bank-ready")
        approval = model["use_case_approvals"]["customer_support"]

        self.assertEqual(approval["proposed_recommendation_status"], "recommended")
        self.assertEqual(approval["effective_recommendation_status"], "recommended")
        self.assertIn("Complete privacy impact assessment", " ".join(approval["proposed_recommendation_required_controls"]))

    def _insert_bank_model(
        self,
        model_id: str,
        *,
        model_card_url: str | None = None,
        model_card_verified_at: str | None = None,
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
                    "model_card_url": model_card_url,
                    "model_card_verified_at": model_card_verified_at,
                    "license_id": "apache-2.0",
                    "license_name": "Apache 2.0",
                    "training_data_summary": "Reviewed public and licensed data.",
                    "active": 1,
                },
            )

    def _insert_customer_support_scores(self, model_id: str) -> None:
        score_rows = [
            ("chatbot_arena", 1400.0),
            ("aa_cost", 0.20),
            ("aa_speed", 120.0),
            ("ifeval", 82.0),
            ("ailuminate", 75.0),
        ]
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": model_id,
                        "benchmark_id": benchmark_id,
                        "value": value,
                        "raw_value": str(value),
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_url": None,
                        "source_type": "primary",
                        "verified": 1,
                        "notes": None,
                    }
                    for benchmark_id, value in score_rows
                ],
            )


def _use_case(use_case_id: str) -> dict:
    return next(use_case for use_case in update_engine.USE_CASES if use_case["id"] == use_case_id)


def _customer_support_benchmarks() -> dict[str, dict]:
    return {
        "chatbot_arena": {"higher_is_better": True, "metric": "elo"},
        "aa_cost": {"higher_is_better": False, "metric": "cost"},
        "aa_speed": {"higher_is_better": True, "metric": "tokens/sec"},
        "ifeval": {"higher_is_better": True, "metric": "score"},
        "ailuminate": {"higher_is_better": True, "metric": "score"},
    }


def _model_payload(model_id: str) -> dict:
    return {
        "id": model_id,
        "name": model_id,
        "provider": "Bank Test Provider",
        "catalog_status": "tracked",
        "license_policy_class": "commercial_clear",
        "provenance_policy_class": "standard",
        "model_card_url": "https://example.com/model-card",
        "model_card_verified_at": "2026-07-01T00:00:00Z",
        "provider_origin_countries": [{"code": "US", "name": "United States"}],
        "provenance_gap_fields": [],
        "scores": {
            "chatbot_arena": {"value": 1400.0, "source_type": "primary", "verified": True},
            "aa_cost": {"value": 0.20, "source_type": "primary", "verified": True},
            "aa_speed": {"value": 120.0, "source_type": "primary", "verified": True},
            "ifeval": {"value": 82.0, "source_type": "primary", "verified": True},
            "ailuminate": {"value": 75.0, "source_type": "primary", "verified": True},
        },
        "use_case_approvals": {},
    }


if __name__ == "__main__":
    unittest.main()
