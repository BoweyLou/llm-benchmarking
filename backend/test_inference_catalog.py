from __future__ import annotations

import unittest

from backend.inference_catalog import attach_inference_catalog


class InferenceCatalogTests(unittest.TestCase):
    def test_openai_models_surface_azure_foundry(self) -> None:
        model = attach_inference_catalog(
            {
                "id": "gpt-4-1-2025-04-14",
                "name": "GPT 4.1",
                "provider": "OpenAI",
                "family_id": "openai::gpt-4-1",
            }
        )

        destination_ids = [destination["id"] for destination in model["inference_destinations"]]
        self.assertEqual(destination_ids, ["azure-ai-foundry"])
        self.assertEqual(model["inference_summary"]["destination_count"], 1)

    def test_newer_claude_families_surface_bedrock_and_vertex(self) -> None:
        model = attach_inference_catalog(
            {
                "id": "claude-4-6-opus",
                "name": "Claude Opus 4.6",
                "provider": "Anthropic",
                "family_id": "anthropic::claude-4-6",
            }
        )

        destination_ids = [destination["id"] for destination in model["inference_destinations"]]
        self.assertEqual(destination_ids, ["aws-bedrock", "google-vertex-ai"])
        self.assertEqual(model["inference_summary"]["destination_count"], 2)
        self.assertGreater(model["inference_summary"]["region_count"], 0)

    def test_unmapped_provider_has_empty_directory(self) -> None:
        model = attach_inference_catalog(
            {
                "id": "custom-model",
                "name": "Custom Model",
                "provider": "Unknown",
                "family_id": "unknown::custom-model",
            }
        )

        self.assertEqual(model["inference_destinations"], [])
        self.assertEqual(model["inference_summary"]["destination_count"], 0)
        self.assertEqual(model["inference_summary"]["region_count"], 0)

    def test_live_destination_overrides_curated_metadata_for_synced_cloud(self) -> None:
        model = attach_inference_catalog(
            {
                "id": "gpt-4-1-2025-04-14",
                "name": "GPT 4.1",
                "provider": "OpenAI",
                "family_id": "openai::gpt-4-1",
            },
            synced_destinations=[
                {
                    "id": "azure-ai-foundry",
                    "name": "Azure AI Foundry",
                    "hyperscaler": "Azure",
                    "availability_scope": "Configured account + deployment scoped",
                    "availability_note": "Live from the configured Foundry account.",
                    "location_scope": "Configured Foundry account regions",
                    "regions": ["eastus2"],
                    "deployment_modes": ["Provisioned"],
                    "pricing_label": "Input USD $2.00 / Output USD $8.00 per 1M tokens",
                    "pricing_note": "Live retail meter pricing.",
                    "sources": [],
                }
            ],
            authoritative_destinations={"azure-ai-foundry"},
        )

        self.assertEqual(model["inference_destinations"][0]["regions"], ["eastus2"])
        self.assertEqual(model["inference_destinations"][0]["deployment_modes"], ["Provisioned"])
        self.assertEqual(
            model["inference_destinations"][0]["pricing_label"],
            "Input USD $2.00 / Output USD $8.00 per 1M tokens",
        )

    def test_authoritative_sync_hides_curated_destination_when_cloud_checked_and_not_found(self) -> None:
        model = attach_inference_catalog(
            {
                "id": "claude-4-6-opus",
                "name": "Claude Opus 4.6",
                "provider": "Anthropic",
                "family_id": "anthropic::claude-4-6",
            },
            synced_destinations=[],
            authoritative_destinations={"aws-bedrock"},
        )

        destination_ids = [destination["id"] for destination in model["inference_destinations"]]
        self.assertEqual(destination_ids, ["google-vertex-ai"])


if __name__ == "__main__":
    unittest.main()
