from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from sqlalchemy import select

from backend.database import (
    fetch_all,
    fetch_one,
    get_engine,
    inference_sync_status as inference_sync_status_table,
    init_db,
    model_inference_destinations as model_inference_destinations_table,
    source_runs as source_runs_table,
)
from backend.inference_sync import (
    MissingConfiguration,
    RetryableSyncSkip,
    SyncOutcome,
    _cached_local_model_match_features,
    _cached_remote_candidate_match_features,
    _catalog_entry_matches_model,
    _price_per_mtok,
    _google_pricing_rates,
    _google_price_kind_from_text,
    _google_sku_matches_model,
    _sync_azure_foundry,
    _sync_azure_foundry_public_pricing,
    _sync_google_vertex_ai,
    sync_inference_catalog,
)
from backend.model_taxonomy import infer_model_identity
from backend.seed_data import seed_reference_data


class InferenceSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.engine = get_engine(f"sqlite:///{Path(self.tempdir.name) / 'test.sqlite'}")
        init_db(self.engine)
        with self.engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_sync_persists_destination_records_and_completion_status(self) -> None:
        outcome = SyncOutcome(
            destination_id="aws-bedrock",
            records=[
                {
                    "model_id": "claude-opus-4-6",
                    "destination_id": "aws-bedrock",
                    "name": "AWS Bedrock",
                    "hyperscaler": "AWS",
                    "availability_scope": "Account + region scoped",
                    "availability_note": "Live account catalog.",
                    "location_scope": "Live Bedrock regions",
                    "regions_json": '["us-east-1","us-west-2"]',
                    "region_count": 2,
                    "deployment_modes_json": '["On-demand","Provisioned"]',
                    "pricing_label": "Input USD $3.00 / Output USD $15.00 per 1M tokens",
                    "pricing_note": "Live pricing rows.",
                    "sources_json": "[]",
                    "catalog_model_id": "anthropic.claude-opus-4-6",
                    "synced_at": "2026-04-07T00:00:00Z",
                    "_pricing_entries": [
                        {
                            "catalog_model_id": "anthropic.claude-opus-4-6",
                            "region": "us-east-1",
                            "price_kind": "input",
                            "price_per_mtok": 3.0,
                            "unit": "1M tokens",
                        }
                    ],
                }
            ],
            detail={"mode": "pricing-only", "model_count": 1},
        )

        with patch("backend.inference_sync._sync_destination", return_value=outcome):
            summary = sync_inference_catalog(destination_ids=["aws-bedrock"], engine=self.engine)

        self.assertEqual(summary["records_written"], 1)
        self.assertEqual(summary["destinations"]["aws-bedrock"]["status"], "completed")

        with self.engine.begin() as conn:
            records = fetch_all(
                conn,
                select(model_inference_destinations_table).where(
                    model_inference_destinations_table.c.destination_id == "aws-bedrock"
                ),
            )
            status = fetch_one(
                conn,
                select(inference_sync_status_table).where(
                    inference_sync_status_table.c.destination_id == "aws-bedrock"
                ),
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["model_id"], "claude-opus-4-6")
        self.assertIsNotNone(status)
        self.assertEqual(status["last_status"], "completed")
        self.assertIsNotNone(status["last_completed_at"])

    def test_empty_cloud_pricing_is_a_visible_failed_source_run(self) -> None:
        outcome = SyncOutcome(
            destination_id="aws-bedrock",
            records=[
                {
                    "model_id": "claude-opus-4-6", "destination_id": "aws-bedrock",
                    "name": "AWS Bedrock", "hyperscaler": "AWS",
                    "availability_scope": "Account scoped", "availability_note": "Available.",
                    "location_scope": "Regions", "regions_json": "[]", "region_count": 0,
                    "deployment_modes_json": "[]", "pricing_label": None, "pricing_note": None,
                    "sources_json": "[]", "catalog_model_id": "anthropic.claude-opus-4-6",
                    "synced_at": "2026-04-07T00:00:00Z", "_pricing_entries": [],
                }
            ],
            detail={"mode": "account-catalog", "model_count": 1},
        )
        with patch("backend.inference_sync._sync_destination", return_value=outcome):
            summary = sync_inference_catalog(destination_ids=["aws-bedrock"], engine=self.engine)
        destination = summary["destinations"]["aws-bedrock"]
        self.assertEqual(destination["status"], "failed")
        self.assertTrue(destination["pricing"]["last_known_good_preserved"])
        with self.engine.begin() as conn:
            failed = fetch_one(
                conn,
                select(source_runs_table).where(
                    source_runs_table.c.source_name == "pricing_aws-bedrock",
                    source_runs_table.c.status == "failed",
                ),
            )
        self.assertIsNotNone(failed)

    def test_missing_configuration_is_reported_as_skipped(self) -> None:
        with patch(
            "backend.inference_sync._sync_destination",
            side_effect=MissingConfiguration("missing credentials"),
        ):
            summary = sync_inference_catalog(destination_ids=["google-vertex-ai"], engine=self.engine)

        self.assertEqual(summary["records_written"], 0)
        self.assertEqual(summary["destinations"]["google-vertex-ai"]["status"], "skipped")
        self.assertEqual(summary["destinations"]["google-vertex-ai"]["reason"], "missing credentials")

        with self.engine.begin() as conn:
            records = fetch_all(conn, select(model_inference_destinations_table))
            status = fetch_one(
                conn,
                select(inference_sync_status_table).where(
                    inference_sync_status_table.c.destination_id == "google-vertex-ai"
                ),
            )

        self.assertEqual(records, [])
        self.assertIsNone(status)

    def test_retryable_sync_skip_is_reported_as_skipped(self) -> None:
        with patch(
            "backend.inference_sync._sync_destination",
            side_effect=RetryableSyncSkip(
                "Azure Retail Prices API rate limited inference sync (HTTP 429); retry later.",
                skip_type="rate_limited",
            ),
        ):
            summary = sync_inference_catalog(destination_ids=["azure-ai-foundry"], engine=self.engine)

        destination = summary["destinations"]["azure-ai-foundry"]
        self.assertEqual(summary["records_written"], 0)
        self.assertEqual(destination["status"], "skipped")
        self.assertTrue(destination["retryable"])
        self.assertEqual(destination["skip_type"], "rate_limited")
        self.assertIn("HTTP 429", destination["reason"])

        with self.engine.begin() as conn:
            records = fetch_all(conn, select(model_inference_destinations_table))

        self.assertEqual(records, [])

    def test_azure_sync_falls_back_to_public_pricing_when_account_config_missing(self) -> None:
        outcome = SyncOutcome(
            destination_id="azure-ai-foundry",
            records=[],
            detail={"mode": "public-pricing-only", "model_count": 0},
        )
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "backend.inference_sync._sync_azure_foundry_public_pricing",
                return_value=outcome,
            ) as public_sync:
                result = _sync_azure_foundry([], client=None)  # type: ignore[arg-type]

        self.assertIs(result, outcome)
        public_sync.assert_called_once()

    def test_azure_public_pricing_429_is_retryable_skip(self) -> None:
        request = httpx.Request("GET", "https://prices.azure.com/api/retail/prices")
        response = httpx.Response(429, headers={"Retry-After": "60"}, request=request)
        error = httpx.HTTPStatusError("rate limited", request=request, response=response)
        models = [
            {
                "id": "gpt-5",
                "name": "GPT 5",
                "provider": "OpenAI",
                "family_id": "openai::gpt-5",
                "canonical_model_id": "openai::gpt-5",
            }
        ]

        with patch("backend.inference_sync._request_json", side_effect=error):
            with self.assertRaises(RetryableSyncSkip) as context:
                _sync_azure_foundry_public_pricing(models, client=None)  # type: ignore[arg-type]

        self.assertEqual(context.exception.skip_type, "rate_limited")
        self.assertIn("HTTP 429", str(context.exception))
        self.assertIn("Retry-After: 60", str(context.exception))

    def test_price_per_mtok_supports_bare_k_and_m_units(self) -> None:
        self.assertEqual(_price_per_mtok(2.5, "1M"), 2.5)
        self.assertEqual(_price_per_mtok(0.0022, "1K"), 2.2)

    def test_google_sync_falls_back_to_published_endpoints_without_token(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            outcome = _sync_google_vertex_ai(
                [
                    {
                        "id": "claude-opus-4-6",
                        "name": "Claude Opus 4.6",
                        "provider": "Anthropic",
                        "family_id": "anthropic::claude-4-6",
                        "canonical_model_id": "anthropic::claude-4-6-opus",
                    }
                ],
                client=None,  # type: ignore[arg-type]
            )

        self.assertEqual(outcome.destination_id, "google-vertex-ai")
        self.assertEqual(outcome.detail["mode"], "published-endpoints-only")
        self.assertEqual(len(outcome.records), 1)
        self.assertIn("global", outcome.records[0]["regions_json"])
        self.assertEqual(outcome.records[0]["_pricing_entries"], [])
        self.assertIn("require authenticated Google APIs", outcome.records[0]["pricing_note"])

    def test_google_cloud_billing_api_key_adds_pricing_to_published_endpoints(self) -> None:
        secret = "test-cloud-billing-key"
        calls: list[tuple[str, dict[str, object]]] = []

        def fake_request(client, url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/v1/services"):
                return {
                    "services": [
                        {
                            "name": "services/3AFC-marketplace",
                            "displayName": "Dace IT with Sense Traffic Pulse and Vertex AI",
                            "businessEntityName": "Dace IT",
                        },
                        {
                            "name": "services/C7E2-9256-1C43",
                            "displayName": "Vertex AI",
                            "businessEntityName": "Google LLC",
                        },
                    ]
                }
            if "/services/C7E2-9256-1C43/skus" in url:
                return {
                    "skus": [
                        {
                            "name": "skus/claude-opus-input",
                            "displayName": "Claude Opus 4.6",
                            "description": "Claude Opus 4.6 Input Tokens",
                            "serviceRegions": ["global"],
                            "pricingInfo": [
                                {
                                    "effectiveTime": "2026-07-01T00:00:00Z",
                                    "pricingExpression": {
                                        "usageUnitDescription": "1,000 tokens",
                                        "displayQuantity": 1000,
                                        "tieredRates": [
                                            {
                                                "startUsageAmount": 0,
                                                "unitPrice": {"units": "0", "nanos": 3000000},
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ]
                }
            self.fail(f"Unexpected URL: {url}")

        models = [
            {
                "id": "claude-opus-4-6",
                "name": "Claude Opus 4.6",
                "provider": "Anthropic",
                "family_id": "anthropic::claude-4-6",
                "canonical_model_id": "anthropic::claude-4-6-opus",
            }
        ]
        with patch.dict(os.environ, {"GOOGLE_CLOUD_BILLING_API_KEY": secret}, clear=True):
            with patch("backend.inference_sync._request_json", side_effect=fake_request):
                outcome = _sync_google_vertex_ai(models, client=None)  # type: ignore[arg-type]

        self.assertEqual(outcome.detail["mode"], "published-endpoints+pricing")
        self.assertEqual(len(outcome.records), 1)
        self.assertEqual(len(outcome.records[0]["_pricing_entries"]), 1)
        self.assertEqual(outcome.records[0]["_pricing_entries"][0]["price_per_mtok"], 3.0)
        self.assertIn("Cloud Billing SKUs matched: 1", outcome.records[0]["pricing_note"])
        self.assertEqual(len(calls), 2)
        for url, kwargs in calls:
            self.assertIn("cloudbilling.googleapis.com", url)
            self.assertEqual(kwargs["params"]["key"], secret)  # type: ignore[index]
            self.assertNotIn("Authorization", kwargs.get("headers") or {})
        self.assertNotIn(secret, repr(outcome.detail))
        self.assertNotIn(secret, repr(outcome.records))

    def test_google_cloud_billing_api_key_is_redacted_from_errors(self) -> None:
        secret = "test-cloud-billing-key"

        def fake_request(client, url, **kwargs):
            if url.endswith("/v1/services"):
                return {"services": [{"name": "services/vertex-service", "displayName": "Vertex AI"}]}
            request = httpx.Request("GET", f"{url}?key={secret}")
            response = httpx.Response(403, request=request)
            raise httpx.HTTPStatusError("forbidden", request=request, response=response)

        with patch.dict(os.environ, {"GOOGLE_CLOUD_BILLING_API_KEY": secret}, clear=True):
            with patch("backend.inference_sync._request_json", side_effect=fake_request):
                with self.assertRaises(RuntimeError) as context:
                    _sync_google_vertex_ai([], client=None)  # type: ignore[arg-type]

        self.assertNotIn(secret, str(context.exception))
        self.assertIn("HTTP 403", str(context.exception))

    def test_google_cloud_billing_preserves_every_tier_rate(self) -> None:
        rates = _google_pricing_rates(
            {
                "effectiveTime": "2026-07-01T00:00:00Z",
                "pricingExpression": {
                    "usageUnitDescription": "1,000 characters",
                    "displayQuantity": 1000,
                    "tieredRates": [
                        {"startUsageAmount": 0, "unitPrice": {"units": "0", "nanos": 5000000}},
                        {"startUsageAmount": 1000000, "unitPrice": {"units": "0", "nanos": 3000000}},
                    ],
                },
            }
        )
        self.assertEqual(len(rates), 2)
        self.assertEqual(rates[0]["billing_unit"], "character")
        self.assertEqual(rates[0]["unit_quantity"], 1000)
        self.assertEqual(rates[0]["end_usage_amount"], 1000000)
        self.assertEqual(rates[1]["start_usage_amount"], 1000000)

    def test_catalog_matching_reuses_remote_identity_features(self) -> None:
        model = {
            "id": "performance-cache-probe-model-77",
            "name": "Performance Cache Probe Model 77",
            "provider": "Probe Provider",
            "family_id": "probe::performance-cache-probe-model-77",
            "canonical_model_id": "probe::performance-cache-probe-model-77",
        }
        _cached_local_model_match_features.cache_clear()
        _cached_remote_candidate_match_features.cache_clear()
        try:
            with patch(
                "backend.inference_sync.infer_model_identity",
                wraps=infer_model_identity,
            ) as identity_parser:
                self.assertTrue(
                    _catalog_entry_matches_model(
                        model,
                        "Probe Provider",
                        "Performance Cache Probe Model 77",
                    )
                )
                self.assertTrue(
                    _catalog_entry_matches_model(
                        model,
                        "Probe Provider",
                        "Performance Cache Probe Model 77",
                    )
                )

            self.assertEqual(identity_parser.call_count, 1)
            self.assertGreaterEqual(_cached_local_model_match_features.cache_info().hits, 1)
            self.assertGreaterEqual(_cached_remote_candidate_match_features.cache_info().hits, 1)
        finally:
            _cached_local_model_match_features.cache_clear()
            _cached_remote_candidate_match_features.cache_clear()

    def test_google_sku_matching_uses_specific_model_prefix_and_pricing_suffix(self) -> None:
        gemini_pro = {
            "id": "gemini-2-5-pro",
            "name": "Gemini 2.5 Pro",
            "provider": "Google",
            "family_id": "google::gemini-2-5",
            "canonical_model_id": "google::gemini-2-5-pro",
        }
        gemini_flash = {
            **gemini_pro,
            "id": "gemini-2-5-flash",
            "name": "Gemini 2.5 Flash",
            "canonical_model_id": "google::gemini-2-5-flash",
        }
        generic_prefix = {
            **gemini_pro,
            "id": "gemini-2-5",
            "name": "Gemini 2.5",
            "canonical_model_id": "google::gemini-2-5",
        }
        dated_variant = {
            **gemini_pro,
            "id": "gemini-2-5-pro-2025-06-05",
            "name": "Gemini 2.5 Pro 2025-06-05",
        }
        reasoning_variant = {
            **gemini_pro,
            "id": "gemini-2-5-pro-deep-think",
            "name": "Gemini 2.5 Pro Deep Think",
        }
        sku = {
            "provider": None,
            "display_name": "Gemini 2.5 Pro Text Output Priority (Long) - Predictions",
            "description": "Gemini 2.5 Pro Text Output Priority (Long) - Predictions",
            "catalog_model_id": "8D12-realistic-vertex-sku",
        }

        self.assertTrue(_google_sku_matches_model(gemini_pro, sku))
        self.assertFalse(_google_sku_matches_model(gemini_flash, sku))
        self.assertFalse(_google_sku_matches_model(generic_prefix, sku))
        self.assertFalse(_google_sku_matches_model(dated_variant, sku))
        self.assertFalse(_google_sku_matches_model(reasoning_variant, sku))

    def test_google_sku_matching_strips_only_known_vertex_boilerplate(self) -> None:
        gemma = {
            "id": "gemma-4",
            "name": "Gemma 4",
            "provider": "Google",
            "family_id": "google::gemma-4",
            "canonical_model_id": "google::gemma-4",
        }
        sku = {
            "provider": None,
            "display_name": "Cloud Vertex AI Model Garden Model as a Service Gemma-4 Input Token",
            "description": "Cloud Vertex AI Model Garden Model as a Service Gemma-4 Input Token",
            "catalog_model_id": "A1B2-realistic-model-garden-sku",
        }

        self.assertTrue(_google_sku_matches_model(gemma, sku))
        sku["description"] = "Unrelated Marketplace Gemma-4 Input Token"
        sku["display_name"] = sku["description"]
        self.assertFalse(_google_sku_matches_model(gemma, sku))

    def test_google_price_kind_supports_modality_rows_without_token_wording(self) -> None:
        for modality in ("Text", "Image", "Audio", "Video"):
            self.assertEqual(
                _google_price_kind_from_text(f"Gemini 2.5 Pro {modality} Input - Predictions"),
                "input",
            )
            self.assertEqual(
                _google_price_kind_from_text(f"Gemini 2.5 Pro {modality} Output Priority - Predictions"),
                "output",
            )


if __name__ == "__main__":
    unittest.main()
