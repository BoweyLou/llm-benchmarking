from __future__ import annotations

import unittest

from backend import update_engine
from backend import model_licenses
from backend.model_licenses import (
    LICENSE_POLICY_COMMERCIAL_BLOCKED,
    LICENSE_POLICY_COMMERCIAL_CLEAR,
    LICENSE_POLICY_POTENTIAL_LEGAL_REVIEW,
    build_license_policy_payload,
)


class ModelLicensePolicyTests(unittest.TestCase):
    def test_build_license_policy_payload_marks_mit_as_commercial_clear(self) -> None:
        payload = build_license_policy_payload("mit", "MIT")

        self.assertEqual(payload["license_policy_class"], LICENSE_POLICY_COMMERCIAL_CLEAR)
        self.assertFalse(payload["potential_legal_review"])
        self.assertFalse(payload["commercial_use_blocked"])
        self.assertIsNone(payload["license_policy_note"])

    def test_build_license_policy_payload_marks_proprietary_as_potential_review(self) -> None:
        payload = build_license_policy_payload("proprietary", "Proprietary")

        self.assertEqual(payload["license_policy_class"], LICENSE_POLICY_POTENTIAL_LEGAL_REVIEW)
        self.assertTrue(payload["potential_legal_review"])
        self.assertFalse(payload["commercial_use_blocked"])
        self.assertIn("legal/procurement review", payload["license_policy_note"])

    def test_build_license_policy_payload_marks_non_commercial_as_blocked(self) -> None:
        payload = build_license_policy_payload("cc-by-nc-4.0", "cc-by-nc-4.0")

        self.assertEqual(payload["license_policy_class"], LICENSE_POLICY_COMMERCIAL_BLOCKED)
        self.assertFalse(payload["potential_legal_review"])
        self.assertTrue(payload["commercial_use_blocked"])
        self.assertIn("not recommended", payload["license_policy_note"])

    def test_enterprise_lenses_default_to_production_commercial(self) -> None:
        enterprise_use_case = next(use_case for use_case in update_engine.USE_CASES if use_case["id"] == "customer_support")
        resolved = update_engine._resolve_use_case_definition(enterprise_use_case, {})

        self.assertTrue(resolved["production_commercial"])

    def test_core_lenses_do_not_default_to_production_commercial(self) -> None:
        core_use_case = next(use_case for use_case in update_engine.USE_CASES if use_case["id"] == "coding")
        resolved = update_engine._resolve_use_case_definition(core_use_case, {})

        self.assertFalse(resolved["production_commercial"])

    def test_blocked_license_adds_auto_not_recommended_for_production_lenses(self) -> None:
        model = update_engine._serialize_model(
            {
                "id": "restricted-model",
                "name": "Restricted Model",
                "provider": "Unknown",
                "type": "open_weights",
                "active": 1,
                "license_id": "cc-by-nc-4.0",
                "license_name": "cc-by-nc-4.0",
            }
        )

        self.assertEqual(model["license_policy_class"], LICENSE_POLICY_COMMERCIAL_BLOCKED)
        self.assertEqual(
            model["use_case_approvals"]["customer_support"]["auto_recommendation_status"],
            update_engine.RECOMMENDATION_STATUS_NOT_RECOMMENDED,
        )
        self.assertNotIn("coding", model["use_case_approvals"])

    def test_non_proprietary_family_name_inference_uses_existing_donor(self) -> None:
        updates = model_licenses._build_unique_family_name_non_proprietary_updates(
            [
                {
                    "id": "gemma-hosted",
                    "family_name": "Gemma 3",
                    "type": "proprietary",
                    "license_id": "proprietary",
                    "license_name": "Proprietary",
                    "license_url": "https://example.com/proprietary",
                },
                {
                    "id": "gemma-open",
                    "family_name": "Gemma 3",
                    "type": "proprietary",
                    "license_id": "gemma",
                    "license_name": "gemma",
                    "license_url": "https://example.com/gemma",
                },
                {
                    "id": "gemma-missing",
                    "family_name": "Gemma 3",
                    "type": "open_weights",
                    "license_id": None,
                    "license_name": None,
                    "license_url": None,
                },
            ]
        )

        self.assertEqual(
            updates["gemma-missing"],
            {
                "license_id": "gemma",
                "license_name": "gemma",
                "license_url": "https://example.com/gemma",
            },
        )


if __name__ == "__main__":
    unittest.main()
