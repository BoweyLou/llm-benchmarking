from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.inference_catalog import attach_inference_catalog, load_synced_inference_catalog
from backend.pricing import attach_pricing


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
        self.assertEqual(destination_ids, ["openai-direct", "azure-ai-foundry"])
        self.assertEqual(model["inference_summary"]["destination_count"], 2)

        direct, azure = model["inference_destinations"]
        self.assertEqual(direct["availability_evidence_kind"], "provider_managed")
        self.assertEqual(azure["availability_evidence_kind"], "curated_fallback")
        self.assertIsNone(azure["catalog_model_id"])
        self.assertIsNone(azure["synced_at"])

    def test_provider_aliases_surface_parent_cloud_destinations(self) -> None:
        nova = attach_inference_catalog(
            {
                "id": "nova-pro",
                "name": "Nova Pro",
                "provider": "Amazon Nova",
                "family_id": "amazon::nova",
            }
        )
        phi = attach_inference_catalog(
            {
                "id": "phi-4",
                "name": "Phi 4",
                "provider": "Microsoft Azure",
                "family_id": "microsoft::phi",
            }
        )

        self.assertEqual([destination["id"] for destination in nova["inference_destinations"]], ["aws-bedrock"])
        self.assertEqual([destination["id"] for destination in phi["inference_destinations"]], ["azure-ai-foundry"])

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
        self.assertEqual(destination_ids, ["anthropic-direct", "aws-bedrock", "google-vertex-ai"])
        self.assertEqual(model["inference_summary"]["destination_count"], 3)
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

    def test_router_routes_are_explicitly_provider_routed(self) -> None:
        model = attach_inference_catalog(
            {
                "id": "routed-model",
                "name": "Routed Model",
                "provider": "Unknown",
                "family_id": "unknown::routed-model",
                "openrouter_model_id": "unknown/routed-model",
            }
        )

        self.assertEqual(len(model["inference_destinations"]), 1)
        route = model["inference_destinations"][0]
        self.assertEqual(route["id"], "openrouter")
        self.assertEqual(route["availability_evidence_kind"], "provider_routed")

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
                    "catalog_model_id": "azureml://registries/azure-openai/models/gpt-4.1/versions/2025-04-14",
                    "synced_at": "2026-07-15T02:00:00Z",
                    "freshness": {"status": "fresh", "age_days": 0},
                }
            ],
            authoritative_destinations={"azure-ai-foundry"},
        )

        azure = next(item for item in model["inference_destinations"] if item["id"] == "azure-ai-foundry")
        self.assertEqual(azure["regions"], ["eastus2"])
        self.assertEqual(azure["deployment_modes"], ["Provisioned"])
        self.assertEqual(
            azure["pricing_label"],
            "Input USD $2.00 / Output USD $8.00 per 1M tokens",
        )
        self.assertEqual(azure["availability_evidence_kind"], "synced")
        self.assertEqual(
            azure["catalog_model_id"],
            "azureml://registries/azure-openai/models/gpt-4.1/versions/2025-04-14",
        )
        self.assertEqual(azure["synced_at"], "2026-07-15T02:00:00Z")
        self.assertEqual(azure["freshness"], {"status": "fresh", "age_days": 0})

    def test_loaded_sync_modes_keep_provenance_and_truthful_evidence_kinds(self) -> None:
        rows = [
            {
                "model_id": "account-catalog-model",
                "destination_id": "aws-bedrock",
                "name": "AWS Bedrock",
                "hyperscaler": "AWS",
                "availability_scope": "Account + region scoped",
                "availability_note": "Live account catalog.",
                "location_scope": "Live Bedrock regions",
                "regions_json": '["ap-southeast-2"]',
                "region_count": 1,
                "deployment_modes_json": '["On-demand"]',
                "pricing_label": None,
                "pricing_note": None,
                "sources_json": "[]",
                "catalog_model_id": "anthropic.claude-opus-4-6-v1:0",
                "synced_at": "2026-07-15T01:00:00Z",
            },
            {
                "model_id": "public-price-model",
                "destination_id": "azure-ai-foundry",
                "name": "Azure AI Foundry",
                "hyperscaler": "Azure",
                "availability_scope": "Public retail pricing footprint",
                "availability_note": "Pricing does not confirm deployment entitlements.",
                "location_scope": "Live Azure retail pricing regions",
                "regions_json": '["australiaeast"]',
                "region_count": 1,
                "deployment_modes_json": '["Serverless"]',
                "pricing_label": "Input USD $2.00 per 1M tokens",
                "pricing_note": "Public retail pricing.",
                "sources_json": "[]",
                "catalog_model_id": "GPT-4.1 Global Standard Input",
                "synced_at": "2026-07-15T01:01:00Z",
            },
            {
                "model_id": "published-route-model",
                "destination_id": "google-vertex-ai",
                "name": "Google Vertex AI",
                "hyperscaler": "Google Cloud",
                "availability_scope": "Published endpoint footprint",
                "availability_note": "Published regions plus curated model routing.",
                "location_scope": "Published Vertex endpoints",
                "regions_json": '["australia-southeast1"]',
                "region_count": 1,
                "deployment_modes_json": '["Regional endpoint"]',
                "pricing_label": None,
                "pricing_note": None,
                "sources_json": "[]",
                "catalog_model_id": "google/gemini-2.5-pro",
                "synced_at": "2026-07-15T01:02:00Z",
            },
        ]
        statuses = [
            {"destination_id": "aws-bedrock", "detail_json": '{"mode":"account-catalog+pricing"}'},
            {"destination_id": "azure-ai-foundry", "detail_json": '{"mode":"public-pricing-only"}'},
            {"destination_id": "google-vertex-ai", "detail_json": '{"mode":"published-endpoints-only"}'},
        ]

        with patch("backend.inference_catalog.fetch_all", side_effect=[rows, statuses]):
            catalog = load_synced_inference_catalog(object(), [row["model_id"] for row in rows])

        synced = catalog["account-catalog-model"][0]
        price_only = catalog["public-price-model"][0]
        curated = catalog["published-route-model"][0]
        self.assertEqual(synced["availability_evidence_kind"], "synced")
        self.assertEqual(synced["catalog_model_id"], "anthropic.claude-opus-4-6-v1:0")
        self.assertEqual(synced["synced_at"], "2026-07-15T01:00:00Z")
        self.assertEqual(price_only["availability_evidence_kind"], "pricing_only")
        self.assertEqual(price_only["catalog_model_id"], "GPT-4.1 Global Standard Input")
        self.assertEqual(price_only["synced_at"], "2026-07-15T01:01:00Z")
        self.assertEqual(curated["availability_evidence_kind"], "curated_fallback")

    def test_price_discovered_destinations_do_not_invent_or_cross_attach_regions(self) -> None:
        model = attach_pricing(
            {
                "id": "price-only-model",
                "inference_destinations": [],
            },
            [
                {
                    "id": 1,
                    "destination_id": "aws-bedrock",
                    "region": "us-east-1",
                    "provenance": {
                        "verified_at": "2026-07-15T03:00:00Z",
                        "stale": False,
                    },
                },
                {
                    "id": 2,
                    "destination_id": "azure-ai-foundry",
                    "region": "australiaeast",
                    "provenance": {
                        "verified_at": "2026-07-15T03:01:00Z",
                        "stale": True,
                    },
                },
            ],
        )

        destinations = {item["id"]: item for item in model["inference_destinations"]}
        bedrock = destinations["aws-bedrock"]
        azure = destinations["azure-ai-foundry"]
        self.assertEqual(bedrock["availability_evidence_kind"], "pricing_only")
        self.assertEqual(azure["availability_evidence_kind"], "pricing_only")
        self.assertEqual(bedrock["regions"], [])
        self.assertEqual(azure["regions"], [])
        self.assertEqual([offer["id"] for offer in bedrock["pricing_offers"]], [1])
        self.assertEqual([offer["region"] for offer in bedrock["pricing_offers"]], ["us-east-1"])
        self.assertEqual([offer["id"] for offer in azure["pricing_offers"]], [2])
        self.assertEqual([offer["region"] for offer in azure["pricing_offers"]], ["australiaeast"])
        self.assertEqual(
            azure["pricing_offers"][0]["provenance"],
            {"verified_at": "2026-07-15T03:01:00Z", "stale": True},
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
        self.assertEqual(destination_ids, ["anthropic-direct", "google-vertex-ai"])


if __name__ == "__main__":
    unittest.main()
