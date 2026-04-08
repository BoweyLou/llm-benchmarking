from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select, update

from backend import update_engine
from backend.database import (
    get_engine,
    inference_sync_status as inference_sync_status_table,
    init_db,
    model_duplicate_overrides as model_duplicate_overrides_table,
    model_inference_destinations as model_inference_destinations_table,
    model_identity_overrides as model_identity_overrides_table,
    model_market_snapshots as model_market_snapshots_table,
    model_use_case_inference_approvals as model_use_case_inference_approvals_table,
    model_use_case_approvals as model_use_case_approvals_table,
    models as models_table,
    providers as providers_table,
    raw_source_records as raw_source_records_table,
    scores as scores_table,
    source_runs as source_runs_table,
    update_log as update_log_table,
)
from backend.model_curation import build_model_curation_match_key
from backend.seed_data import seed_reference_data


class RankingTests(unittest.TestCase):
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

    def add_model(
        self,
        model_id: str,
        name: str,
        *,
        provider: str = "Test Provider",
        family_id: str | None = None,
        family_name: str | None = None,
        canonical_model_id: str | None = None,
        canonical_model_name: str | None = None,
        discovered_at: str | None = None,
        discovered_update_log_id: int | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                [
                    {
                        "id": model_id,
                        "name": name,
                        "provider": provider,
                        "type": "proprietary",
                        "release_date": None,
                        "context_window": None,
                        "family_id": family_id,
                        "family_name": family_name,
                        "canonical_model_id": canonical_model_id,
                        "canonical_model_name": canonical_model_name,
                        "variant_label": None,
                        "discovered_at": discovered_at,
                        "discovered_update_log_id": discovered_update_log_id,
                        "active": 1,
                    }
                ],
            )

    def add_score(
        self,
        model_id: str,
        benchmark_id: str,
        value: float,
        *,
        collected_at: str = "2026-04-02T00:00:00Z",
        source_type: str = "primary",
        verified: bool = True,
        notes: str | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": model_id,
                        "benchmark_id": benchmark_id,
                        "value": value,
                        "raw_value": str(value),
                        "collected_at": collected_at,
                        "source_url": None,
                        "source_type": source_type,
                        "verified": int(verified),
                        "notes": notes,
                    }
                ],
            )

    def add_update_log(
        self,
        log_id: int,
        *,
        status: str = "completed",
        completed_at: str | None = "2026-04-08T00:05:00Z",
        current_step_key: str | None = None,
        current_step_label: str | None = None,
        current_step_started_at: str | None = None,
        current_step_index: int = 0,
        total_steps: int = 0,
        steps_json: str | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update_log_table.insert(),
                [
                    {
                        "id": log_id,
                        "started_at": "2026-04-08T00:00:00Z",
                        "completed_at": completed_at,
                        "triggered_by": "manual",
                        "status": status,
                        "scores_added": 0,
                        "scores_updated": 0,
                        "errors": json.dumps([]),
                        "current_step_key": current_step_key,
                        "current_step_label": current_step_label,
                        "current_step_started_at": current_step_started_at,
                        "current_step_index": current_step_index,
                        "total_steps": total_steps,
                        "steps_json": steps_json,
                    }
                ],
            )

    def ranking_for(self, use_case_id: str, model_name: str) -> dict:
        rankings = update_engine.get_rankings(use_case_id)
        self.assertIsNotNone(rankings)
        match = next((row for row in rankings["rankings"] if row["model"]["name"] == model_name), None)
        self.assertIsNotNone(match, f"{model_name} was not ranked for {use_case_id}")
        return match

    def test_coding_excludes_models_missing_required_benchmarks(self) -> None:
        self.add_model("complete-model", "Complete Model")
        self.add_model("intel-only", "Intel Only")

        self.add_score("complete-model", "swebench_verified", 80.0)
        self.add_score("complete-model", "terminal_bench", 60.0)
        self.add_score("complete-model", "aa_intelligence", 50.0)
        self.add_score("intel-only", "aa_intelligence", 99.0)

        rankings = update_engine.get_rankings("coding")
        self.assertIsNotNone(rankings)

        ranked_names = [row["model"]["name"] for row in rankings["rankings"]]
        self.assertIn("Complete Model", ranked_names)
        self.assertNotIn("Intel Only", ranked_names)

    def test_coding_prefers_stronger_swebench_when_other_edges_are_smaller(self) -> None:
        self.add_model("flash", "Flash")
        self.add_model("pro", "Pro")

        self.add_score("flash", "swebench_verified", 80.0)
        self.add_score("flash", "aa_intelligence", 50.0)
        self.add_score("flash", "terminal_bench", 40.0)

        self.add_score("pro", "swebench_verified", 70.0)
        self.add_score("pro", "aa_intelligence", 60.0)
        self.add_score("pro", "terminal_bench", 50.0)

        rankings = update_engine.get_rankings("coding")
        self.assertIsNotNone(rankings)

        ordered_names = [row["model"]["name"] for row in rankings["rankings"][:2]]
        self.assertEqual(ordered_names, ["Flash", "Pro"])

        flash = self.ranking_for("coding", "Flash")
        pro = self.ranking_for("coding", "Pro")
        self.assertAlmostEqual(flash["score"], 55.0)
        self.assertAlmostEqual(pro["score"], 45.0)

    def test_rankings_change_by_use_case_weights(self) -> None:
        self.add_model("flash", "Flash")
        self.add_model("pro", "Pro")

        self.add_score("flash", "swebench_verified", 80.0)
        self.add_score("flash", "aa_intelligence", 50.0)
        self.add_score("flash", "terminal_bench", 40.0)
        self.add_score("flash", "gpqa_diamond", 70.0)
        self.add_score("flash", "chatbot_arena", 80.0)

        self.add_score("pro", "swebench_verified", 70.0)
        self.add_score("pro", "aa_intelligence", 60.0)
        self.add_score("pro", "terminal_bench", 50.0)
        self.add_score("pro", "gpqa_diamond", 95.0)
        self.add_score("pro", "chatbot_arena", 95.0)

        coding = update_engine.get_rankings("coding")
        reasoning = update_engine.get_rankings("general_reasoning")
        self.assertIsNotNone(coding)
        self.assertIsNotNone(reasoning)

        self.assertEqual(coding["rankings"][0]["model"]["name"], "Flash")
        self.assertEqual(reasoning["rankings"][0]["model"]["name"], "Pro")

    def test_cost_efficiency_inverts_lower_is_better_metrics(self) -> None:
        self.add_model("cheap", "Cheap")
        self.add_model("expensive", "Expensive")

        self.add_score("cheap", "aa_cost", 0.1)
        self.add_score("cheap", "aa_speed", 100.0)
        self.add_score("cheap", "aa_intelligence", 50.0)

        self.add_score("expensive", "aa_cost", 10.0)
        self.add_score("expensive", "aa_speed", 100.0)
        self.add_score("expensive", "aa_intelligence", 50.0)

        rankings = update_engine.get_rankings("cost_efficiency")
        self.assertIsNotNone(rankings)
        self.assertEqual(rankings["rankings"][0]["model"]["name"], "Cheap")

        cheap = self.ranking_for("cost_efficiency", "Cheap")
        expensive = self.ranking_for("cost_efficiency", "Expensive")
        cheap_cost = next(item for item in cheap["breakdown"] if item["benchmark_id"] == "aa_cost")
        expensive_cost = next(item for item in expensive["breakdown"] if item["benchmark_id"] == "aa_cost")

        self.assertAlmostEqual(cheap_cost["normalised"], 100.0)
        self.assertAlmostEqual(expensive_cost["normalised"], 0.0)

    def test_internal_view_weight_boosts_scored_models_without_blocking_missing_models(self) -> None:
        self.add_model("internal-a", "Internal A")
        self.add_model("internal-b", "Internal B")

        for model_id in ("internal-a", "internal-b"):
            self.add_score(model_id, "gpqa_diamond", 85.0)
            self.add_score(model_id, "aa_intelligence", 60.0)
            self.add_score(model_id, "chatbot_arena", 70.0)

        use_case = update_engine.update_use_case_internal_weight("general_reasoning", 0.2)
        self.assertIsNotNone(use_case)
        self.assertAlmostEqual(use_case["internal_view_weight"], 0.2)
        self.assertAlmostEqual(use_case["weights"]["internal_view"], 0.2)

        result = update_engine.update_manual_benchmark_score(
            "internal-a",
            "internal_view",
            value=95.0,
            notes="Strong internal preference.",
        )
        self.assertIsNotNone(result)

        rankings = update_engine.get_rankings("general_reasoning")
        self.assertIsNotNone(rankings)
        ranked_names = [row["model"]["name"] for row in rankings["rankings"]]
        self.assertIn("Internal A", ranked_names)
        self.assertIn("Internal B", ranked_names)
        self.assertLess(ranked_names.index("Internal A"), ranked_names.index("Internal B"))

    def test_internal_view_can_be_cleared(self) -> None:
        self.add_model("clear-target", "Clear Target")
        result = update_engine.update_manual_benchmark_score(
            "clear-target",
            "internal_view",
            value=42.0,
            notes="Temporary signal.",
        )
        self.assertIsNotNone(result)
        models = update_engine.list_models()
        target = next(model for model in models if model["id"] == "clear-target")
        self.assertIsNotNone(target["scores"]["internal_view"])

        cleared = update_engine.update_manual_benchmark_score(
            "clear-target",
            "internal_view",
            value=None,
        )
        self.assertIsNotNone(cleared)
        self.assertIsNone(cleared["score"])

        refreshed_models = update_engine.list_models()
        refreshed_target = next(model for model in refreshed_models if model["id"] == "clear-target")
        self.assertIsNone(refreshed_target["scores"]["internal_view"])

    def test_canonical_models_use_best_variant_per_benchmark(self) -> None:
        self.add_model(
            "suite-a",
            "Suite A",
            canonical_model_id="suite",
            canonical_model_name="Suite",
        )
        self.add_model(
            "suite-b",
            "Suite B",
            canonical_model_id="suite",
            canonical_model_name="Suite",
        )
        self.add_model("competitor", "Competitor")

        self.add_score("suite-a", "swebench_verified", 90.0)
        self.add_score("suite-a", "aa_intelligence", 60.0)
        self.add_score("suite-a", "terminal_bench", 45.0)

        self.add_score("suite-b", "swebench_verified", 75.0)
        self.add_score("suite-b", "aa_intelligence", 55.0, collected_at="2026-04-02T00:01:00Z")
        self.add_score("suite-b", "terminal_bench", 85.0)

        self.add_score("competitor", "swebench_verified", 70.0)
        self.add_score("competitor", "aa_intelligence", 50.0)
        self.add_score("competitor", "terminal_bench", 70.0)

        suite = self.ranking_for("coding", "Suite")
        breakdown = {item["benchmark_id"]: item for item in suite["breakdown"]}

        self.assertEqual(suite["model"]["id"], "suite")
        self.assertEqual(breakdown["swebench_verified"]["variant_model_name"], "Suite A")
        self.assertEqual(breakdown["terminal_bench"]["variant_model_name"], "Suite B")

    def test_list_models_enriches_seeded_provider_origin(self) -> None:
        models = update_engine.list_models()

        gpt = next(model for model in models if model["id"] == "gpt-5-4")
        self.assertEqual(gpt["provider_id"], "openai")
        self.assertEqual(gpt["provider_country_code"], "US")
        self.assertEqual(gpt["provider_country_name"], "United States")
        self.assertEqual(gpt["provider_country_flag"], "🇺🇸")
        self.assertIsNotNone(gpt["provider_origin_source_url"])

    def test_list_models_prefers_cached_inference_directory_for_synced_clouds(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                model_inference_destinations_table.insert(),
                [
                    {
                        "model_id": "gpt-5-4",
                        "destination_id": "azure-ai-foundry",
                        "name": "Azure AI Foundry",
                        "hyperscaler": "Azure",
                        "availability_scope": "Configured account + deployment scoped",
                        "availability_note": "Live from the configured Foundry account.",
                        "location_scope": "Configured Foundry account regions",
                        "regions_json": json.dumps(["eastus2"]),
                        "region_count": 1,
                        "deployment_modes_json": json.dumps(["Provisioned"]),
                        "pricing_label": "Input USD $2.00 / Output USD $8.00 per 1M tokens",
                        "pricing_note": "Live retail meter pricing.",
                        "sources_json": json.dumps([]),
                        "catalog_model_id": "gpt-5-4",
                        "synced_at": "2026-04-07T00:00:00Z",
                    }
                ],
            )
            conn.execute(
                inference_sync_status_table.insert(),
                [
                    {
                        "destination_id": "azure-ai-foundry",
                        "last_status": "completed",
                        "last_attempted_at": "2026-04-07T00:00:00Z",
                        "last_completed_at": "2026-04-07T00:00:00Z",
                        "detail_json": "{}",
                    }
                ],
            )

        models = update_engine.list_models()
        gpt = next(model for model in models if model["id"] == "gpt-5-4")

        self.assertEqual(len(gpt["inference_destinations"]), 1)
        self.assertEqual(gpt["inference_destinations"][0]["regions"], ["eastus2"])
        self.assertEqual(gpt["inference_destinations"][0]["deployment_modes"], ["Provisioned"])
        self.assertEqual(
            gpt["inference_destinations"][0]["pricing_label"],
            "Input USD $2.00 / Output USD $8.00 per 1M tokens",
        )

    def test_sync_provider_directory_backfills_provider_ids_for_existing_rows(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(models_table).values(provider_id=None))

        update_engine._sync_provider_directory()

        models = update_engine.list_models()
        claude = next(model for model in models if model["id"] == "claude-opus-4-6")
        self.assertEqual(claude["provider_id"], "anthropic")
        self.assertEqual(claude["provider_country_code"], "US")

    def test_list_providers_returns_seeded_provider_origin(self) -> None:
        providers = update_engine.list_providers()

        openai = next(provider for provider in providers if provider["id"] == "openai")
        self.assertEqual(openai["country_code"], "US")
        self.assertEqual(openai["country_name"], "United States")

    def test_update_provider_origin_persists_manual_changes_across_reseed(self) -> None:
        updated = update_engine.update_provider_origin(
            "openai",
            {
                "country_code": "US",
                "country_name": "United States",
                "origin_basis": "Manually reviewed",
                "source_url": "https://example.com/openai-origin",
                "verified_at": "2026-04-03T00:00:00Z",
            },
        )
        self.assertIsNotNone(updated)

        with self.engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)
            provider = conn.execute(
                providers_table.select().where(providers_table.c.id == "openai")
            ).mappings().one()

        self.assertEqual(provider["origin_basis"], "Manually reviewed")
        self.assertEqual(provider["source_url"], "https://example.com/openai-origin")

    def test_update_model_approval_persists_manual_changes_across_reseed(self) -> None:
        updated = update_engine.update_model_approval("gpt-5-4", True, "Approved by internal review")
        self.assertIsNotNone(updated)
        self.assertTrue(updated["approved_for_use"])
        self.assertGreater(updated["approval_use_case_count"], 0)

        with self.engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)
            model = conn.execute(
                models_table.select().where(models_table.c.id == "gpt-5-4")
            ).mappings().one()
            approvals = conn.execute(
                model_use_case_approvals_table.select().where(model_use_case_approvals_table.c.model_id == "gpt-5-4")
            ).mappings().all()

        self.assertEqual(model["approved_for_use"], 1)
        self.assertEqual(model["approval_notes"], "Approved by internal review")
        self.assertEqual(len(approvals), len(update_engine.USE_CASES))

    def test_update_model_use_case_approval_updates_only_selected_lens(self) -> None:
        updated = update_engine.update_model_use_case_approval(
            "gpt-5-4",
            "coding",
            True,
            "Approved for coding only",
            "recommended",
            "Primary coding default",
        )
        self.assertIsNotNone(updated)
        self.assertTrue(updated["use_case_approvals"]["coding"]["approved_for_use"])
        self.assertEqual(updated["use_case_approvals"]["coding"]["approval_notes"], "Approved for coding only")
        self.assertEqual(updated["use_case_approvals"]["coding"]["recommendation_status"], "recommended")
        self.assertEqual(updated["use_case_approvals"]["coding"]["recommendation_notes"], "Primary coding default")
        self.assertFalse(updated["use_case_approvals"].get("rag_groundedness", {}).get("approved_for_use", False))

    def test_update_model_use_case_inference_approval_persists_route_and_auto_enables_base_approval(self) -> None:
        updated = update_engine.update_model_use_case_inference_approval(
            "gpt-5-4",
            "general_reasoning",
            "azure-ai-foundry",
            "Australia",
            True,
            "Approved only for Australian hosting.",
        )
        self.assertIsNotNone(updated)

        approval = updated["use_case_approvals"]["general_reasoning"]
        self.assertTrue(approval["approved_for_use"])
        route = next(
            entry
            for entry in approval["inference_route_approvals"]
            if entry["destination_id"] == "azure-ai-foundry" and entry["location_label"] == "Australia"
        )
        self.assertTrue(route["approved_for_use"])
        self.assertEqual(route["destination_name"], "Azure AI Foundry")
        self.assertEqual(route["hyperscaler"], "Azure")
        self.assertEqual(route["approval_notes"], "Approved only for Australian hosting.")

    def test_apply_model_inference_route_approval_bulk_updates_multiple_models(self) -> None:
        self.add_model("gpt-route-b", "GPT Route B", provider="OpenAI")

        result = update_engine.apply_model_inference_route_approval_bulk(
            ["gpt-5-4", "gpt-route-b"],
            "general_reasoning",
            "azure-ai-foundry",
            "Australia",
            True,
            "Australia only",
        )

        self.assertEqual(result["updated_count"], 2)
        self.assertEqual(result["destination_name"], "Azure AI Foundry")
        self.assertEqual(result["location_label"], "Australia")

        models = update_engine.list_models()
        gpt_primary = next(model for model in models if model["id"] == "gpt-5-4")
        gpt_secondary = next(model for model in models if model["id"] == "gpt-route-b")

        primary_route = next(
            entry
            for entry in gpt_primary["use_case_approvals"]["general_reasoning"]["inference_route_approvals"]
            if entry["destination_id"] == "azure-ai-foundry" and entry["location_label"] == "Australia"
        )
        secondary_route = next(
            entry
            for entry in gpt_secondary["use_case_approvals"]["general_reasoning"]["inference_route_approvals"]
            if entry["destination_id"] == "azure-ai-foundry" and entry["location_label"] == "Australia"
        )

        self.assertTrue(primary_route["approved_for_use"])
        self.assertTrue(secondary_route["approved_for_use"])

    def test_use_case_approval_recommendation_persists_and_aggregates(self) -> None:
        self.add_model(
            "family-recommended",
            "Family Recommended",
            family_id="rec-family",
            family_name="Recommendation Family",
            canonical_model_id="rec-canonical",
            canonical_model_name="Recommendation Canonical",
        )
        self.add_model(
            "family-not-recommended",
            "Family Not Recommended",
            family_id="rec-family",
            family_name="Recommendation Family",
            canonical_model_id="rec-canonical",
            canonical_model_name="Recommendation Canonical",
        )

        update_engine.update_model_use_case_approval(
            "family-recommended",
            "coding",
            True,
            "Allowed",
            "recommended",
            "Default coding option",
        )
        update_engine.update_model_use_case_approval(
            "family-not-recommended",
            "coding",
            True,
            "Allowed for legacy fallback",
            "not_recommended",
            "Legacy compatibility only",
        )

        models = update_engine.list_models()
        recommended = next(model for model in models if model["id"] == "family-recommended")
        not_recommended = next(model for model in models if model["id"] == "family-not-recommended")

        self.assertEqual(recommended["use_case_approvals"]["coding"]["recommendation_status"], "recommended")
        self.assertEqual(not_recommended["use_case_approvals"]["coding"]["recommendation_status"], "not_recommended")

        benchmarks = {benchmark["id"]: benchmark for benchmark in update_engine.list_benchmarks()}
        canonical_models = update_engine._build_canonical_models(models, benchmarks)
        family_model = next(model for model in canonical_models if model.get("family_id") == "rec-family")
        family_approval = family_model["use_case_approvals"]["coding"]

        self.assertEqual(family_approval["recommendation_status"], "mixed")
        self.assertEqual(family_approval["recommended_member_count"], 1)
        self.assertEqual(family_approval["not_recommended_member_count"], 1)
        self.assertEqual(family_approval["discouraged_member_count"], 0)

    def test_legacy_global_approval_migrates_to_use_case_rows(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "gpt-5-4")
                .values(
                    approved_for_use=1,
                    approval_notes="Legacy approval",
                    approval_updated_at="2026-04-03T00:00:00Z",
                )
            )

        update_engine._migrate_legacy_model_approvals()

        with self.engine.begin() as conn:
            approvals = conn.execute(
                model_use_case_approvals_table.select().where(model_use_case_approvals_table.c.model_id == "gpt-5-4")
            ).mappings().all()

        self.assertEqual(len(approvals), len(update_engine.USE_CASES))
        self.assertTrue(all(row["approved_for_use"] == 1 for row in approvals))

    def test_ensure_model_stamps_discovery_metadata_for_new_models(self) -> None:
        self.add_update_log(321)
        model_id = update_engine._ensure_model(
            "Fresh Frontier Model",
            {"organization": "Test Provider"},
            discovered_update_log_id=321,
        )

        with self.engine.begin() as conn:
            row = conn.execute(
                models_table.select().where(models_table.c.id == model_id)
            ).mappings().one()

        self.assertEqual(row["discovered_update_log_id"], 321)
        self.assertIsNotNone(row["discovered_at"])

    def test_curate_model_identity_persists_manual_override_across_refresh(self) -> None:
        self.add_model(
            "manual-family-source",
            "Manual Family Source",
            family_id="wrong-family",
            family_name="Wrong Family",
            canonical_model_id="wrong-canonical",
            canonical_model_name="Wrong Canonical",
        )
        self.add_model(
            "manual-family-target",
            "Manual Family Target",
            family_id="right-family",
            family_name="Right Family",
            canonical_model_id="right-canonical",
            canonical_model_name="Right Canonical",
        )

        with patch.object(update_engine, "export_model_curation_baseline"):
            updated = update_engine.curate_model_identity(
                "manual-family-source",
                "manual-family-target",
                variant_label="Preview",
                notes="Manual family correction",
            )

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["family_id"], "right-family")
        self.assertEqual(updated["canonical_model_id"], "right-canonical")
        self.assertEqual(updated["variant_label"], "Preview")

        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "manual-family-source")
                .values(
                    family_id="regressed-family",
                    family_name="Regressed Family",
                    canonical_model_id="regressed-canonical",
                    canonical_model_name="Regressed Canonical",
                    variant_label=None,
                )
            )

        update_engine._refresh_model_identity_metadata()

        with self.engine.begin() as conn:
            model_row = conn.execute(
                models_table.select().where(models_table.c.id == "manual-family-source")
            ).mappings().one()
            override_row = conn.execute(
                model_identity_overrides_table.select().where(
                    model_identity_overrides_table.c.source_model_id == "manual-family-source"
                )
            ).mappings().one()

        self.assertEqual(model_row["family_id"], "right-family")
        self.assertEqual(model_row["canonical_model_id"], "right-canonical")
        self.assertEqual(model_row["variant_label"], "Preview")
        self.assertEqual(override_row["family_name"], "Right Family")
        self.assertEqual(override_row["active"], 1)

    def test_ensure_model_uses_identity_override_for_future_insert(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                model_identity_overrides_table.insert(),
                [
                    {
                        "source_model_id": "curated-future-variant",
                        "match_provider": "Test Provider",
                        "match_name": "Curated Future Variant",
                        "match_key": build_model_curation_match_key("Test Provider", "Curated Future Variant"),
                        "family_id": "future-family",
                        "family_name": "Future Family",
                        "canonical_model_id": "future-canonical",
                        "canonical_model_name": "Future Canonical",
                        "variant_label": "Instruct",
                        "notes": "Future match rule",
                        "updated_at": "2026-04-08T00:00:00Z",
                        "active": 1,
                    }
                ],
            )

        model_id = update_engine._ensure_model(
            "Curated Future Variant",
            {"organization": "Test Provider"},
            raw_model_key="curated-future-variant",
        )

        self.assertEqual(model_id, "curated-future-variant")

        with self.engine.begin() as conn:
            row = conn.execute(
                models_table.select().where(models_table.c.id == "curated-future-variant")
            ).mappings().one()

        self.assertEqual(row["family_id"], "future-family")
        self.assertEqual(row["canonical_model_id"], "future-canonical")
        self.assertEqual(row["variant_label"], "Instruct")

    def test_merge_model_duplicate_persists_future_redirect(self) -> None:
        self.add_model("nova-pro", "Nova Pro", provider="Amazon")
        self.add_model("nova-pro-preview", "Nova Pro Preview", provider="Amazon")
        self.add_score("nova-pro-preview", "aa_intelligence", 77.0)
        update_engine.update_model_use_case_approval("nova-pro-preview", "coding", True, "Legacy duplicate approval")

        with patch.object(update_engine, "export_model_curation_baseline"):
            merged = update_engine.merge_model_duplicate(
                "nova-pro-preview",
                "nova-pro",
                notes="Preview row is a duplicate of Nova Pro",
            )

        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertEqual(merged["id"], "nova-pro")

        with self.engine.begin() as conn:
            model_ids = {row["id"] for row in conn.execute(models_table.select()).mappings().all()}
            duplicate_override = conn.execute(
                model_duplicate_overrides_table.select().where(
                    model_duplicate_overrides_table.c.source_model_id == "nova-pro-preview"
                )
            ).mappings().one()
            approval_rows = conn.execute(
                model_use_case_approvals_table.select().where(
                    model_use_case_approvals_table.c.model_id == "nova-pro"
                )
            ).mappings().all()

        self.assertIn("nova-pro", model_ids)
        self.assertNotIn("nova-pro-preview", model_ids)
        self.assertEqual(duplicate_override["target_model_id"], "nova-pro")
        self.assertTrue(any(row["use_case_id"] == "coding" and row["approved_for_use"] == 1 for row in approval_rows))

        rerouted_id = update_engine._ensure_model(
            "Nova Pro Preview",
            {"organization": "Amazon"},
            raw_model_key="nova-pro-preview",
        )
        self.assertEqual(rerouted_id, "nova-pro")

        with self.engine.begin() as conn:
            model_ids_after_reroute = {row["id"] for row in conn.execute(models_table.select()).mappings().all()}

        self.assertNotIn("nova-pro-preview", model_ids_after_reroute)

    def test_apply_model_family_approval_delta_only_updates_new_unreviewed_members(self) -> None:
        self.add_update_log(77)
        self.add_model(
            "family-approved",
            "Family Approved",
            family_id="test-family",
            family_name="Test Family",
            canonical_model_id="test-family-core",
            canonical_model_name="Test Family Core",
        )
        self.add_model(
            "family-new",
            "Family New",
            family_id="test-family",
            family_name="Test Family",
            canonical_model_id="test-family-core",
            canonical_model_name="Test Family Core",
            discovered_at="2026-04-08T00:00:00Z",
            discovered_update_log_id=77,
        )
        self.add_model(
            "family-reviewed-no",
            "Family Reviewed No",
            family_id="test-family",
            family_name="Test Family",
            discovered_at="2026-04-08T00:00:00Z",
            discovered_update_log_id=77,
        )
        self.add_model(
            "family-legacy-unapproved",
            "Family Legacy Unapproved",
            family_id="test-family",
            family_name="Test Family",
        )

        update_engine.update_model_use_case_approval("family-approved", "coding", True, "Reference approval")
        update_engine.update_model_use_case_approval("family-reviewed-no", "coding", False, "Explicitly rejected")

        result = update_engine.apply_model_family_approval_delta(
            "test-family",
            "coding",
            "Approved through family delta",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["reference_approved_count"], 1)
        self.assertEqual(result["updated_model_ids"], ["family-new"])

        models = update_engine.list_models()
        family_new = next(model for model in models if model["id"] == "family-new")
        family_reviewed_no = next(model for model in models if model["id"] == "family-reviewed-no")
        family_legacy_unapproved = next(model for model in models if model["id"] == "family-legacy-unapproved")

        self.assertTrue(family_new["use_case_approvals"]["coding"]["approved_for_use"])
        self.assertEqual(family_new["use_case_approvals"]["coding"]["approval_notes"], "Approved through family delta")
        self.assertFalse(family_reviewed_no["use_case_approvals"]["coding"]["approved_for_use"])
        self.assertNotIn("coding", family_legacy_unapproved["use_case_approvals"])

    def test_apply_model_family_approval_bulk_across_multiple_use_cases(self) -> None:
        self.add_model(
            "bulk-family-a",
            "Bulk Family A",
            family_id="bulk-family",
            family_name="Bulk Family",
        )
        self.add_model(
            "bulk-family-b",
            "Bulk Family B",
            family_id="bulk-family",
            family_name="Bulk Family",
        )

        result = update_engine.apply_model_family_approval_bulk(
            "bulk-family",
            ["coding", "general_reasoning"],
            "Bulk family approval",
            scope="family",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["scope"], "family")
        self.assertEqual(result["total_updated_count"], 4)
        self.assertEqual([item["use_case_id"] for item in result["results"]], ["coding", "general_reasoning"])
        self.assertTrue(all(item["updated_count"] == 2 for item in result["results"]))

        models = update_engine.list_models()
        family_a = next(model for model in models if model["id"] == "bulk-family-a")
        family_b = next(model for model in models if model["id"] == "bulk-family-b")

        self.assertTrue(family_a["use_case_approvals"]["coding"]["approved_for_use"])
        self.assertTrue(family_a["use_case_approvals"]["general_reasoning"]["approved_for_use"])
        self.assertTrue(family_b["use_case_approvals"]["coding"]["approved_for_use"])
        self.assertTrue(family_b["use_case_approvals"]["general_reasoning"]["approved_for_use"])

    def test_refresh_openrouter_market_signals_persists_latest_rankings(self) -> None:
        global_entries = [
            {
                "date": "2026-03-31 00:00:00",
                "model_permaslug": "anthropic/claude-opus-4.6",
                "variant": "standard",
                "variant_permaslug": "anthropic/claude-opus-4.6",
                "total_prompt_tokens": 600,
                "total_completion_tokens": 150,
                "total_native_tokens_reasoning": 50,
                "count": 40,
                "change": 0.25,
            },
            {
                "date": "2026-03-31 00:00:00",
                "model_permaslug": "openai/gpt-5.4",
                "variant": "standard",
                "variant_permaslug": "openai/gpt-5.4",
                "total_prompt_tokens": 400,
                "total_completion_tokens": 80,
                "total_native_tokens_reasoning": 20,
                "count": 28,
                "change": 0.10,
            },
        ]
        programming_entries = [
            {
                "date": "2026-03-31",
                "model_slug": "anthropic/claude-opus-4.6",
                "model": "anthropic/claude-opus-4.6",
                "category": "programming",
                "count": 12,
                "total_prompt_tokens": 300,
                "total_completion_tokens": 60,
                "volume": 18.5,
                "rank": 2,
            },
            {
                "date": "2026-03-31",
                "model_slug": "openai/gpt-5.4",
                "model": "openai/gpt-5.4",
                "category": "programming",
                "count": 8,
                "total_prompt_tokens": 180,
                "total_completion_tokens": 40,
                "volume": 11.25,
                "rank": 5,
            },
        ]

        with (
            patch.object(update_engine, "_fetch_openrouter_global_rankings", return_value=global_entries),
            patch.object(update_engine, "_fetch_openrouter_programming_rankings", return_value=programming_entries),
        ):
            update_engine._refresh_openrouter_market_signals()
            update_engine._refresh_openrouter_market_signals()

        models = update_engine.list_models()
        claude = next(model for model in models if model["id"] == "claude-opus-4-6")
        gpt = next(model for model in models if model["id"] == "gpt-5-4")

        self.assertEqual(claude["openrouter_global_rank"], 1)
        self.assertEqual(claude["openrouter_global_total_tokens"], 800)
        self.assertAlmostEqual(claude["openrouter_global_share"], 800 / 1300)
        self.assertAlmostEqual(claude["openrouter_global_change_ratio"], 0.25)
        self.assertEqual(claude["openrouter_programming_rank"], 2)
        self.assertEqual(claude["openrouter_programming_total_tokens"], 360)
        self.assertAlmostEqual(claude["openrouter_programming_volume"], 18.5)
        self.assertEqual(claude["market_source_name"], "openrouter")

        self.assertEqual(gpt["openrouter_global_rank"], 2)
        self.assertEqual(gpt["openrouter_programming_rank"], 5)

        global_snapshots = update_engine.list_market_snapshots(scope="global", limit=10)
        programming_snapshots = update_engine.list_market_snapshots(scope="category", category_slug="programming", limit=10)
        self.assertEqual(global_snapshots[0]["model_name"], "Claude Opus 4.6")
        self.assertEqual(global_snapshots[0]["rank"], 1)
        self.assertEqual(programming_snapshots[0]["category_slug"], "programming")
        self.assertEqual(programming_snapshots[0]["provider"], "Anthropic")

        with self.engine.begin() as conn:
            snapshots = conn.execute(model_market_snapshots_table.select()).mappings().all()

        self.assertEqual(len(snapshots), 4)

    def test_refresh_openrouter_model_metadata_persists_created_timestamp_and_alias_match(self) -> None:
        self.add_model("nova-pro", "Nova Pro", provider="Amazon")

        openrouter_items = [
            {
                "id": "amazon/nova-pro-v1",
                "canonical_slug": "amazon/nova-pro-v1",
                "name": "Amazon: Nova Pro 1.0",
                "created": 1775592472,
                "top_provider": {
                    "context_length": 300000,
                    "max_completion_tokens": 8192,
                },
                "pricing": {
                    "prompt": "0.0000025",
                    "completion": "0.00001",
                },
            }
        ]

        with patch.object(update_engine, "_fetch_openrouter_models", return_value=openrouter_items):
            update_engine._refresh_openrouter_model_metadata()

        models = update_engine.list_models()
        nova = next(model for model in models if model["id"] == "nova-pro")

        self.assertEqual(nova["openrouter_model_id"], "amazon/nova-pro-v1")
        self.assertEqual(nova["openrouter_canonical_slug"], "amazon/nova-pro-v1")
        self.assertEqual(nova["openrouter_added_at"], "2026-04-07T20:07:52Z")
        self.assertEqual(nova["context_window_tokens"], 300000)
        self.assertEqual(nova["max_output_tokens"], 8192)

    def test_refresh_openrouter_model_metadata_imports_untracked_openrouter_model_as_provisional(self) -> None:
        openrouter_items = [
            {
                "id": "amazon/nova-premier-v1",
                "canonical_slug": "amazon/nova-premier-v1",
                "name": "Amazon: Nova Premier 1.0",
                "created": 1761950332,
                "top_provider": {
                    "context_length": 1000000,
                    "max_completion_tokens": 32768,
                },
                "pricing": {
                    "prompt": "0.000004",
                    "completion": "0.000016",
                },
            }
        ]

        with patch.object(update_engine, "_fetch_openrouter_models", return_value=openrouter_items):
            update_engine._refresh_openrouter_model_metadata()

        models = update_engine.list_models()
        imported = next(model for model in models if model["openrouter_model_id"] == "amazon/nova-premier-v1")

        self.assertEqual(imported["name"], "Nova Premier 1.0")
        self.assertEqual(imported["provider"], "Amazon")
        self.assertEqual(imported["catalog_status"], "provisional")
        self.assertEqual(imported["type"], "proprietary")
        self.assertEqual(imported["openrouter_added_at"], "2025-10-31T22:38:52Z")
        self.assertEqual(imported["context_window_tokens"], 1000000)

    def test_canonicalize_model_catalog_remaps_dependent_rows_before_delete(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                [
                    {
                        "id": "duplicate-nova-pro-preview-row",
                        "name": "Nova Pro",
                        "provider": "Amazon",
                        "type": "proprietary",
                        "catalog_status": "tracked",
                        "release_date": None,
                        "context_window": None,
                        "active": 1,
                    },
                    {
                        "id": "duplicate-nova-pro-canonical-row",
                        "name": "Nova Pro",
                        "provider": "Amazon",
                        "type": "proprietary",
                        "catalog_status": "tracked",
                        "release_date": "2025",
                        "context_window": "300k tokens",
                        "active": 1,
                    },
                ],
            )
            conn.execute(
                model_use_case_approvals_table.insert(),
                [
                    {
                        "model_id": "duplicate-nova-pro-preview-row",
                        "use_case_id": "general_reasoning",
                        "approved_for_use": 1,
                        "approval_notes": "legacy duplicate",
                    }
                ],
            )
            conn.execute(
                model_use_case_inference_approvals_table.insert(),
                [
                    {
                        "model_id": "duplicate-nova-pro-preview-row",
                        "use_case_id": "general_reasoning",
                        "destination_id": "azure-ai-foundry",
                        "location_key": "australia",
                        "location_label": "Australia",
                        "approved_for_use": 1,
                        "approval_notes": "AU only",
                    }
                ],
            )
            conn.execute(
                model_inference_destinations_table.insert(),
                [
                    {
                        "model_id": "duplicate-nova-pro-preview-row",
                        "destination_id": "aws-us-east-1",
                        "name": "AWS us-east-1",
                        "hyperscaler": "AWS",
                        "availability_scope": "regional",
                        "location_scope": "regional",
                        "regions_json": '["us-east-1"]',
                        "region_count": 1,
                        "deployment_modes_json": '["on_demand"]',
                        "sources_json": "[]",
                        "synced_at": "2026-04-08T00:00:00Z",
                    }
                ],
            )
            conn.execute(
                model_market_snapshots_table.insert(),
                [
                    {
                        "source_name": "openrouter",
                        "scope": "global",
                        "category_slug": "",
                        "snapshot_date": "2026-04-08",
                        "model_id": "duplicate-nova-pro-preview-row",
                        "rank": 9,
                        "payload_json": "{}",
                        "collected_at": "2026-04-08T00:00:00Z",
                    }
                ],
            )

        update_engine._canonicalize_model_catalog()

        with self.engine.begin() as conn:
            model_ids = {row["id"] for row in conn.execute(models_table.select()).mappings().all()}
            approval_rows = conn.execute(model_use_case_approvals_table.select()).mappings().all()
            inference_approval_rows = conn.execute(model_use_case_inference_approvals_table.select()).mappings().all()
            inference_rows = conn.execute(model_inference_destinations_table.select()).mappings().all()
            snapshot_rows = conn.execute(model_market_snapshots_table.select()).mappings().all()

        self.assertNotIn("duplicate-nova-pro-preview-row", model_ids)
        self.assertIn("duplicate-nova-pro-canonical-row", model_ids)
        self.assertEqual(approval_rows[0]["model_id"], "duplicate-nova-pro-canonical-row")
        self.assertEqual(inference_approval_rows[0]["model_id"], "duplicate-nova-pro-canonical-row")
        self.assertEqual(inference_rows[0]["model_id"], "duplicate-nova-pro-canonical-row")
        self.assertEqual(snapshot_rows[0]["model_id"], "duplicate-nova-pro-canonical-row")

    def test_canonicalize_model_catalog_deduplicates_market_snapshot_collisions(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                [
                    {
                        "id": "duplicate-market-preview-row",
                        "name": "Nova Pro",
                        "provider": "Amazon",
                        "type": "proprietary",
                        "catalog_status": "tracked",
                        "active": 1,
                    },
                    {
                        "id": "duplicate-market-canonical-row",
                        "name": "Nova Pro",
                        "provider": "Amazon",
                        "type": "proprietary",
                        "catalog_status": "tracked",
                        "release_date": "2025",
                        "active": 1,
                    },
                ],
            )
            conn.execute(
                model_market_snapshots_table.insert(),
                [
                    {
                        "source_name": "openrouter",
                        "scope": "global",
                        "category_slug": "",
                        "snapshot_date": "2026-04-08",
                        "model_id": "duplicate-market-preview-row",
                        "rank": 9,
                        "payload_json": "{}",
                        "collected_at": "2026-04-08T00:00:00Z",
                    },
                    {
                        "source_name": "openrouter",
                        "scope": "global",
                        "category_slug": "",
                        "snapshot_date": "2026-04-08",
                        "model_id": "duplicate-market-canonical-row",
                        "rank": 9,
                        "payload_json": "{}",
                        "collected_at": "2026-04-08T00:00:00Z",
                    },
                ],
            )

        update_engine._canonicalize_model_catalog()

        with self.engine.begin() as conn:
            snapshot_rows = conn.execute(model_market_snapshots_table.select()).mappings().all()

        self.assertEqual(len(snapshot_rows), 1)
        self.assertEqual(snapshot_rows[0]["model_id"], "duplicate-market-canonical-row")

    def test_get_update_log_includes_progress_steps_and_counts(self) -> None:
        steps = [
            {
                "key": "source:artificial_analysis",
                "label": "Ingest Artificial Analysis",
                "kind": "source",
                "source_name": "artificial_analysis",
                "benchmark_id": "aa_intelligence,aa_speed,aa_cost",
            },
            {
                "key": "phase:catalog-canonicalization",
                "label": "Canonicalize model catalog",
                "kind": "phase",
            },
            {
                "key": "phase:finalize",
                "label": "Finalize update",
                "kind": "phase",
            },
        ]
        self.add_update_log(
            901,
            status="running",
            completed_at=None,
            current_step_key="phase:catalog-canonicalization",
            current_step_label="Canonicalize model catalog",
            current_step_started_at="2026-04-08T00:01:30Z",
            current_step_index=2,
            total_steps=3,
            steps_json=json.dumps(steps),
        )
        with self.engine.begin() as conn:
            conn.execute(
                source_runs_table.insert(),
                [
                    {
                        "update_log_id": 901,
                        "source_name": "artificial_analysis",
                        "benchmark_id": "aa_intelligence,aa_speed,aa_cost",
                        "started_at": "2026-04-08T00:00:10Z",
                        "completed_at": "2026-04-08T00:01:20Z",
                        "status": "completed",
                        "records_found": 185,
                    }
                ],
            )

        log = update_engine.get_update_log(901)
        self.assertIsNotNone(log)
        assert log is not None
        self.assertEqual(log["finished_steps"], 1)
        self.assertAlmostEqual(log["progress_percent"], 100 / 3)
        self.assertEqual(log["progress_steps"][0]["status"], "completed")
        self.assertEqual(log["progress_steps"][1]["status"], "running")
        self.assertEqual(log["progress_steps"][2]["status"], "pending")

    def test_infer_provider_prefers_model_name_hint_over_submission_org(self) -> None:
        inferred = update_engine._infer_provider(
            {
                "organization": "42-b3yond-6ug",
                "submission_organization": "42-b3yond-6ug",
            },
            "Qwen3 Coder 30B A3B Instruct",
        )
        self.assertEqual(inferred, "Alibaba")

    def test_repair_submitter_provider_leaks_uses_openrouter_slug(self) -> None:
        update_engine._ensure_provider_row("42-b3yond-6ug")
        with self.engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                [
                    {
                        "id": "qwen3-coder-30b-a3b-instruct",
                        "name": "Qwen3 Coder 30B A3B Instruct",
                        "provider": "42-b3yond-6ug",
                        "provider_id": "42-b3yond-6ug",
                        "type": "proprietary",
                        "catalog_status": "tracked",
                        "release_date": None,
                        "context_window": None,
                        "context_window_tokens": None,
                        "openrouter_canonical_slug": "qwen/qwen3-coder-30b-a3b-instruct",
                        "active": 1,
                    }
                ],
            )
            source_run = conn.execute(
                source_runs_table.insert().values(
                    update_log_id=None,
                    source_name="swebench",
                    benchmark_id="swebench_verified",
                    started_at="2026-04-08T00:00:00Z",
                    completed_at="2026-04-08T00:01:00Z",
                    status="completed",
                    records_found=1,
                    error_message=None,
                    details_json=None,
                )
            )
            source_run_id = int(source_run.inserted_primary_key[0])
            conn.execute(
                raw_source_records_table.insert(),
                [
                    {
                        "source_run_id": source_run_id,
                        "benchmark_id": "swebench_verified",
                        "raw_model_name": "Qwen3 Coder 30B A3B Instruct",
                        "normalized_model_id": "qwen3-coder-30b-a3b-instruct",
                        "raw_key": "qwen3-coder-30b-a3b-instruct",
                        "raw_value": "64.2",
                        "payload_json": json.dumps(
                            {
                                "tags": [
                                    "Model: Qwen3 Coder 30B A3B Instruct",
                                    "Org: 42-b3yond-6ug",
                                ]
                            }
                        ),
                        "source_url": "https://www.swebench.com/#verified",
                        "source_type": "secondary",
                        "verified": 1,
                        "resolution_status": "resolved",
                        "collected_at": "2026-04-08T00:00:00Z",
                        "notes": None,
                    }
                ],
            )

        repaired = update_engine._repair_submitter_provider_leaks()
        self.assertEqual(repaired, 1)

        with self.engine.connect() as conn:
            row = conn.execute(
                select(models_table.c.provider, models_table.c.provider_id).where(
                    models_table.c.id == "qwen3-coder-30b-a3b-instruct"
                )
            ).mappings().one()

        self.assertEqual(row["provider"], "Alibaba")
        self.assertEqual(row["provider_id"], update_engine.provider_id_from_name("Alibaba"))


if __name__ == "__main__":
    unittest.main()
