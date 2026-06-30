from __future__ import annotations

import unittest

from backend import update_engine
from backend.model_provenance import (
    PROVENANCE_POLICY_DERIVATIVE_REVIEW,
    PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED,
    PROVENANCE_POLICY_STANDARD,
    build_provenance_policy_payload,
)


class ModelProvenancePolicyTests(unittest.TestCase):
    def test_non_derivative_model_is_standard(self) -> None:
        payload = build_provenance_policy_payload(
            base_models=[],
            provider="OpenAI",
            model_card_url="https://example.com/model-card",
            training_data_summary="Mixed public data.",
        )

        self.assertEqual(payload["provenance_policy_class"], PROVENANCE_POLICY_STANDARD)
        self.assertFalse(payload["derivative_model"])
        self.assertFalse(payload["potential_provenance_review"])
        self.assertFalse(payload["production_provenance_blocked"])
        self.assertEqual(payload["provenance_gap_fields"], [])

    def test_disclosed_derivative_requires_review(self) -> None:
        payload = build_provenance_policy_payload(
            base_models=["meta-llama/Llama-3.1-70B-Instruct"],
            provider="Acme",
            model_card_url="https://huggingface.co/acme/model",
            training_data_summary="Synthetic and licensed instruction data.",
        )

        self.assertEqual(payload["provenance_policy_class"], PROVENANCE_POLICY_DERIVATIVE_REVIEW)
        self.assertTrue(payload["derivative_model"])
        self.assertTrue(payload["potential_provenance_review"])
        self.assertFalse(payload["production_provenance_blocked"])
        self.assertIn("Derivative model", payload["provenance_policy_note"])

    def test_unknown_provider_derivative_is_blocked(self) -> None:
        payload = build_provenance_policy_payload(
            base_models=["meta-llama/Llama-3.1-70B-Instruct"],
            provider="Unknown",
            model_card_url="https://huggingface.co/acme/model",
            training_data_summary="Synthetic and licensed instruction data.",
        )

        self.assertEqual(payload["provenance_policy_class"], PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED)
        self.assertTrue(payload["production_provenance_blocked"])
        self.assertEqual(payload["provenance_gap_fields"], ["unknown_provider"])
        self.assertIn("provider identity is unknown", payload["provenance_policy_note"])

    def test_missing_training_summary_derivative_is_blocked_for_production_lenses(self) -> None:
        model = update_engine._serialize_model(
            {
                "id": "derivative-model",
                "name": "Derivative Model",
                "provider": "Known Provider",
                "type": "open_weights",
                "active": 1,
                "model_card_url": "https://huggingface.co/known/derivative-model",
                "base_models_json": '["base/model"]',
                "training_data_summary": None,
            }
        )

        self.assertEqual(model["provenance_policy_class"], PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED)
        self.assertEqual(
            model["use_case_approvals"]["customer_support"]["auto_recommendation_status"],
            update_engine.RECOMMENDATION_STATUS_NOT_RECOMMENDED,
        )
        self.assertEqual(
            model["use_case_approvals"]["customer_support"]["auto_not_recommended_member_count"],
            1,
        )
        self.assertNotIn("coding", model["use_case_approvals"])

    def test_aggregate_use_case_approvals_preserves_auto_not_recommended_counts(self) -> None:
        aggregated = update_engine._aggregate_use_case_approvals(
            [
                {
                    "use_case_approvals": {
                        "customer_support": {
                            "use_case_id": "customer_support",
                            "approved_for_use": False,
                            "approval_notes": None,
                            "approval_updated_at": None,
                            "recommendation_status": "unrated",
                            "recommendation_notes": None,
                            "recommendation_updated_at": None,
                            "auto_recommendation_status": "not_recommended",
                            "auto_recommendation_notes": "Blocked for provenance.",
                        }
                    }
                },
                {
                    "use_case_approvals": {
                        "customer_support": {
                            "use_case_id": "customer_support",
                            "approved_for_use": False,
                            "approval_notes": None,
                            "approval_updated_at": None,
                            "recommendation_status": "recommended",
                            "recommendation_notes": "Recommended variant.",
                            "recommendation_updated_at": "2026-04-30T00:00:00Z",
                            "auto_recommendation_status": "unrated",
                            "auto_recommendation_notes": None,
                        }
                    }
                },
            ]
        )

        self.assertEqual(
            aggregated["customer_support"]["auto_recommendation_status"],
            update_engine.RECOMMENDATION_STATUS_NOT_RECOMMENDED,
        )
        self.assertEqual(aggregated["customer_support"]["auto_not_recommended_member_count"], 1)
        self.assertEqual(aggregated["customer_support"]["approval_total_count"], 2)


if __name__ == "__main__":
    unittest.main()
