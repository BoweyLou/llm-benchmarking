from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from backend.database import (
    fetch_all,
    fetch_one,
    get_engine,
    inference_sync_status as inference_sync_status_table,
    init_db,
    model_inference_destinations as model_inference_destinations_table,
)
from backend.inference_sync import (
    MissingConfiguration,
    SyncOutcome,
    _price_per_mtok,
    _sync_azure_foundry,
    _sync_google_vertex_ai,
    sync_inference_catalog,
)
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


if __name__ == "__main__":
    unittest.main()
