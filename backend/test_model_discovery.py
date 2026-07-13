from __future__ import annotations

import unittest

from backend import model_discovery, provider_catalogs, update_engine


class ModelDiscoveryTests(unittest.TestCase):
    def test_default_baseline_includes_common_small_generator_families(self) -> None:
        families = {
            entry.get("family")
            for entry in model_discovery.huggingface_discovery_entries()
        }

        self.assertIn("gemma", families)
        self.assertIn("phi", families)
        self.assertIn("llama-small", families)
        self.assertIn("qwen-small", families)
        self.assertIn("mistral-small", families)
        self.assertIn("ibm-granite-generator", families)

    def test_filters_official_huggingface_repos_and_excludes_community_by_default(self) -> None:
        entry = {
            "source": "huggingface",
            "family": "gemma",
            "author": "google",
            "include_patterns": ["google/gemma-4*"],
            "trusted_mirrors": [],
        }
        items = [
            {"modelId": "google/gemma-4-12B-it"},
            {"modelId": "google/gemma-4-E2B-it"},
            {"modelId": "google/gemma-4-26B-A4B-it-qat"},
            {"modelId": "google/gemma-4-12B-it-GGUF"},
            {"modelId": "google/gemma-4-mobile"},
            {"modelId": "google/gemma-4-assistant"},
            {"modelId": "community/gemma-4-12B-it-GGUF"},
            {"modelId": "google/gemini-4-12B"},
        ]

        filtered = model_discovery.filter_huggingface_discovery_items(items, entry)

        self.assertEqual(
            [item["modelId"] for item in filtered],
            [
                "google/gemma-4-12B-it",
                "google/gemma-4-E2B-it",
                "google/gemma-4-26B-A4B-it-qat",
                "google/gemma-4-12B-it-GGUF",
                "google/gemma-4-mobile",
                "google/gemma-4-assistant",
            ],
        )

    def test_parses_total_and_active_parameter_sizes_without_collapsing_variants(self) -> None:
        cases = {
            "google/gemma-4-270M-it": (0.27, None, "small", True),
            "google/gemma-4-12B-it": (12.0, None, "small", True),
            "google/gemma-4-31B-it": (31.0, None, "medium", False),
            "google/gemma-4-26B-A4B-it": (26.0, 4.0, "small", True),
            "google/gemma-4-E2B-it": (None, 2.0, "small", True),
            "google/gemma-4-E4B-it-qat": (None, 4.0, "small", True),
            "google/gemma-4-12B-it-GGUF": (12.0, None, "small", True),
        }

        parsed = {
            name: model_discovery.infer_model_size_metadata(name)
            for name in cases
        }

        for name, expected in cases.items():
            with self.subTest(name=name):
                metadata = parsed[name]
                self.assertEqual(
                    (
                        metadata.parameter_count_b,
                        metadata.active_parameter_count_b,
                        metadata.model_size_class,
                        metadata.small_model_candidate,
                    ),
                    expected,
                )

        distinct_size_keys = {
            (
                metadata.parameter_count_b,
                metadata.active_parameter_count_b,
            )
            for metadata in parsed.values()
        }
        self.assertGreater(len(distinct_size_keys), 4)

    def test_update_scope_defaults_run_discovery_only_for_full_updates(self) -> None:
        self.assertTrue(update_engine._should_refresh_model_discovery(set(), refresh_model_discovery=None))
        self.assertFalse(update_engine._should_refresh_model_discovery({"aa_cost"}, refresh_model_discovery=None))
        self.assertTrue(update_engine._should_refresh_model_discovery({"aa_cost"}, refresh_model_discovery=True))
        self.assertFalse(update_engine._should_refresh_model_discovery(set(), refresh_model_discovery=False))

    def test_extracts_huggingface_timestamp_metadata(self) -> None:
        values = model_discovery.huggingface_timestamp_values_from_item(
            {
                "createdAt": "2026-06-16T12:00:00Z",
                "lastModified": "2026-06-25T18:30:00Z",
            }
        )

        self.assertEqual(
            values,
            {
                "huggingface_created_at": "2026-06-16T12:00:00Z",
                "huggingface_last_modified_at": "2026-06-25T18:30:00Z",
            },
        )

    def test_ignores_blank_huggingface_timestamp_metadata(self) -> None:
        values = model_discovery.huggingface_timestamp_values_from_item(
            {
                "createdAt": "  ",
                "lastModified": None,
            }
        )

        self.assertEqual(values, {})

    def test_baseline_includes_nvidia_and_ibm_retrieval_catalog_sources(self) -> None:
        catalog_families = {
            entry["family"]
            for entry in model_discovery.catalog_discovery_entries()
        }
        huggingface_families = {
            entry["family"]
            for entry in model_discovery.huggingface_discovery_entries()
        }

        self.assertIn("nvidia-retrieval", catalog_families)
        self.assertIn("ibm-watsonx-retrieval", catalog_families)
        self.assertIn("nvidia-embedding", huggingface_families)
        self.assertIn("nvidia-reranking", huggingface_families)
        self.assertIn("ibm-granite-embedding", huggingface_families)
        self.assertIn("ibm-granite-reranking", huggingface_families)

    def test_baseline_includes_restricted_frontier_catalog_models(self) -> None:
        catalog_models = {
            model["id"]: model
            for entry in model_discovery.catalog_discovery_entries()
            for model in model_discovery.catalog_discovery_models(entry)
        }

        mythos = catalog_models["claude-mythos-5"]
        cyber = catalog_models["gpt-5-5-cyber"]

        self.assertEqual(mythos["catalog_model_id"], "anthropic/claude-mythos-5")
        self.assertIn("trusted-access", mythos["capabilities"])
        self.assertEqual(cyber["catalog_model_id"], "openai/gpt-5.5-cyber")
        self.assertIn("trusted-access-for-cyber", cyber["capabilities"])

    def test_baseline_includes_openai_gpt_5_6_catalog_models(self) -> None:
        catalog_models = {
            model["id"]: model
            for entry in model_discovery.catalog_discovery_entries()
            for model in model_discovery.catalog_discovery_models(entry)
        }

        expected = {
            "gpt-5-6-sol": ("openai/gpt-5.6-sol", 5.0, 30.0),
            "gpt-5-6-terra": ("openai/gpt-5.6-terra", 2.5, 15.0),
            "gpt-5-6-luna": ("openai/gpt-5.6-luna", 1.0, 6.0),
        }
        for model_id, (catalog_id, input_price, output_price) in expected.items():
            with self.subTest(model_id=model_id):
                model = catalog_models[model_id]
                self.assertEqual(model["catalog_model_id"], catalog_id)
                self.assertEqual(model["release_date"], "2026-07-09")
                self.assertEqual(model["documentation_url"], "https://help.openai.com/en/articles/20001354")
                self.assertEqual(model["price_input_per_mtok"], input_price)
                self.assertEqual(model["price_output_per_mtok"], output_price)

    def test_provider_api_catalogs_cover_main_authenticated_providers(self) -> None:
        catalog_ids = {catalog.id for catalog in provider_catalogs.provider_api_catalogs()}

        self.assertGreaterEqual(
            catalog_ids,
            {"openai", "anthropic", "google-gemini", "mistral", "cohere", "xai"},
        )

    def test_provider_api_parser_preserves_richer_metadata(self) -> None:
        google_models = provider_catalogs.parse_provider_api_catalog_models(
            "google-gemini",
            {
                "models": [
                    {
                        "name": "models/gemini-3.5-flash",
                        "displayName": "Gemini 3.5 Flash",
                        "description": "Fast Gemini text and multimodal model.",
                        "inputTokenLimit": 1048576,
                        "outputTokenLimit": 65536,
                        "supportedGenerationMethods": ["generateContent", "embedContent"],
                    }
                ]
            },
        )
        xai_models = provider_catalogs.parse_provider_api_catalog_models(
            "xai",
            {
                "models": [
                    {
                        "id": "grok-4.5",
                        "input_modalities": ["text", "image"],
                        "output_modalities": ["text"],
                        "prompt_text_token_price": 12500,
                        "completion_text_token_price": 25000,
                    }
                ]
            },
        )
        cohere_models = provider_catalogs.parse_provider_api_catalog_models(
            "cohere",
            {
                "models": [
                    {
                        "name": "embed-v4.0",
                        "endpoints": ["embed"],
                        "features": ["embeddings"],
                        "context_length": 131072,
                        "tokenizer_url": "https://cohere.com/tokenizer/embed-v4.json",
                    }
                ]
            },
        )

        gemini = google_models[0]
        self.assertEqual(gemini["catalog_status"], "provisional")
        self.assertEqual(gemini["id"], "gemini-3.5-flash")
        self.assertEqual(gemini["catalog_model_id"], "google/gemini-3.5-flash")
        self.assertEqual(gemini["context_window_tokens"], 1048576)
        self.assertEqual(gemini["max_output_tokens"], 65536)
        self.assertEqual(set(gemini["model_roles"]), {"embedding", "generator"})
        self.assertIn("generate-content", gemini["capabilities"])

        grok = xai_models[0]
        self.assertEqual(grok["price_input_per_mtok"], 1.25)
        self.assertEqual(grok["price_output_per_mtok"], 2.5)
        self.assertIn("image", grok["capabilities"])

        embed = cohere_models[0]
        self.assertEqual(embed["catalog_status"], "provisional")
        self.assertEqual(embed["model_roles"], ["embedding"])
        self.assertEqual(embed["context_window_tokens"], 131072)
        self.assertEqual(embed["repo_url"], "https://cohere.com/tokenizer/embed-v4.json")


if __name__ == "__main__":
    unittest.main()
