from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
from sqlalchemy import event, select, update

from backend import benchmark_comparisons, update_engine
from backend.database import (
    fetch_all,
    get_connection,
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
from backend.sources.base import ScoreCandidate, SourceFetchResult


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

    def test_bootstrap_is_local_only_and_does_not_run_external_refreshes(self) -> None:
        update_engine.BOOTSTRAPPED = False

        with patch.object(update_engine, "_refresh_openrouter_model_metadata") as openrouter_models, patch.object(
            update_engine,
            "_refresh_model_card_metadata",
        ) as model_cards, patch.object(update_engine, "_refresh_model_license_metadata") as model_licenses, patch.object(
            update_engine,
            "_refresh_openrouter_market_signals",
        ) as openrouter_market:
            update_engine.bootstrap()

        openrouter_models.assert_not_called()
        model_cards.assert_not_called()
        model_licenses.assert_not_called()
        openrouter_market.assert_not_called()
        self.assertTrue(update_engine.BOOTSTRAPPED)

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
        model_roles: list[str] | None = None,
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
                        "model_roles_json": json.dumps(model_roles or ["generator"], ensure_ascii=True),
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
        change_summary: dict | None = None,
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
                        "change_summary_json": json.dumps(change_summary or {}),
                    }
                ],
            )

    def add_source_run(
        self,
        source_name: str,
        benchmark_id: str,
        *,
        status: str = "completed",
        started_at: str = "2026-04-08T00:00:00Z",
        completed_at: str | None = "2026-04-08T00:01:00Z",
        records_found: int = 1,
        error_message: str | None = None,
    ) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                source_runs_table.insert().values(
                    update_log_id=None,
                    source_name=source_name,
                    benchmark_id=benchmark_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    status=status,
                    records_found=records_found,
                    error_message=error_message,
                    details_json=None,
                )
            )
            return int(result.inserted_primary_key[0])

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

    def test_model_role_rankings_do_not_mix_generator_and_embedding_models(self) -> None:
        self.add_model("generator-a", "Generator A", model_roles=["generator"])
        self.add_model("embedding-a", "Embedding A", model_roles=["embedding"])
        self.add_model("reranker-a", "Reranker A", model_roles=["reranker"])
        self.add_model("tts-a", "TTS A", model_roles=["text_to_speech"])

        for model_id, score in (("generator-a", 75.0), ("embedding-a", 99.0), ("tts-a", 100.0)):
            self.add_score(model_id, "gpqa_diamond", score)
            self.add_score(model_id, "aa_intelligence", score)
            self.add_score(model_id, "chatbot_arena", score)

        self.add_score("embedding-a", "mteb_retrieval", 62.0)
        self.add_score("embedding-a", "mteb_retrieval_reranking", 58.0)
        self.add_score("reranker-a", "mteb_reranking", 64.0)
        self.add_score("reranker-a", "mteb_retrieval_reranking", 58.0)
        self.add_score("generator-a", "mteb_retrieval", 100.0)
        self.add_score("tts-a", "aa_tts_quality_elo", 1213.0)
        self.add_score("tts-a", "aa_tts_generation_time", 2.0)
        self.add_score("tts-a", "aa_tts_price_per_1m_chars", 18.0)
        self.add_score("generator-a", "aa_tts_quality_elo", 9999.0)

        reasoning = update_engine.get_rankings("general_reasoning")
        retrieval = update_engine.get_rankings("retrieval_embeddings")
        reranking = update_engine.get_rankings("retrieval_reranking")
        tts = update_engine.get_rankings("text_to_speech")

        self.assertIsNotNone(reasoning)
        self.assertIsNotNone(retrieval)
        self.assertIsNotNone(reranking)
        self.assertIsNotNone(tts)

        self.assertEqual(reasoning["use_case"]["model_roles"], ["generator"])
        self.assertEqual(retrieval["use_case"]["model_roles"], ["embedding"])
        self.assertEqual(reranking["use_case"]["model_roles"], ["reranker"])
        self.assertEqual(tts["use_case"]["model_roles"], ["text_to_speech"])

        self.assertEqual([row["model"]["name"] for row in reasoning["rankings"]], ["Generator A"])
        self.assertEqual([row["model"]["name"] for row in retrieval["rankings"]], ["Embedding A"])
        self.assertEqual([row["model"]["name"] for row in reranking["rankings"]], ["Reranker A"])
        self.assertEqual([row["model"]["name"] for row in tts["rankings"]], ["TTS A"])
        self.assertEqual(retrieval["rankings"][0]["model"]["model_roles"], ["embedding"])
        self.assertEqual(reranking["rankings"][0]["model"]["model_roles"], ["reranker"])
        self.assertEqual(tts["rankings"][0]["model"]["model_roles"], ["text_to_speech"])

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

    def test_huggingface_model_discovery_is_visible_but_ranking_evidence_gated(self) -> None:
        self.add_model("gemma-4-12b-it", "Gemma 4 12B It", provider="Google")
        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "gemma-4-12b-it")
                .values(
                    catalog_status="tracked",
                    openrouter_model_id="google/gemma-4-12b-it",
                    metadata_source_name="curated",
                    metadata_source_url="https://example.test/curated",
                )
            )

        entry = {
            "source": "huggingface",
            "family": "gemma",
            "provider": "Google",
            "author": "google",
            "queries": ["gemma-4"],
            "include_patterns": ["google/gemma-4*"],
            "trusted_mirrors": [],
        }
        items = [
            {"modelId": "google/gemma-4-12B-it", "tags": ["text-generation"]},
            {"modelId": "google/gemma-4-E2B-it"},
            {"modelId": "google/gemma-4-E4B-it"},
            {"modelId": "google/gemma-4-26B-A4B-it"},
            {"modelId": "google/gemma-4-31B-it"},
            {"modelId": "google/gemma-4-12B-it-qat"},
            {"modelId": "google/gemma-4-12B-it-GGUF"},
            {"modelId": "google/gemma-4-mobile"},
            {"modelId": "google/gemma-4-assistant"},
            {"modelId": "community/gemma-4-12B-it-GGUF"},
        ]

        with patch.object(update_engine.model_discovery, "huggingface_discovery_entries", return_value=[entry]), patch.object(
            update_engine.model_discovery,
            "fetch_huggingface_discovery_items",
            return_value=items,
        ):
            summary = update_engine.refresh_model_discovery_metadata(source="huggingface", family="gemma")

        self.assertEqual(summary["records_found"], 9)
        self.assertGreaterEqual(summary["models_created"], 8)

        models = update_engine.list_models()
        by_repo_id = {model.get("huggingface_repo_id"): model for model in models if model.get("huggingface_repo_id")}
        self.assertIn("google/gemma-4-12B-it", by_repo_id)
        self.assertIn("google/gemma-4-E2B-it", by_repo_id)
        self.assertIn("google/gemma-4-26B-A4B-it", by_repo_id)
        self.assertNotIn("community/gemma-4-12B-it-GGUF", by_repo_id)

        existing = by_repo_id["google/gemma-4-12B-it"]
        self.assertEqual(existing["id"], "gemma-4-12b-it")
        self.assertEqual(existing["metadata_source_name"], "curated")
        self.assertEqual(existing["openrouter_model_id"], "google/gemma-4-12b-it")
        self.assertEqual(existing["parameter_count_b"], 12.0)
        self.assertTrue(existing["small_model_candidate"])

        e2b = by_repo_id["google/gemma-4-E2B-it"]
        self.assertEqual(e2b["active_parameter_count_b"], 2.0)
        self.assertIsNone(e2b["parameter_count_b"])
        self.assertEqual(e2b["model_size_class"], "small")
        self.assertTrue(e2b["small_model_candidate"])
        self.assertEqual(e2b["catalog_status"], "provisional")

        moe = by_repo_id["google/gemma-4-26B-A4B-it"]
        self.assertEqual(moe["parameter_count_b"], 26.0)
        self.assertEqual(moe["active_parameter_count_b"], 4.0)
        self.assertTrue(moe["small_model_candidate"])

        medium = by_repo_id["google/gemma-4-31B-it"]
        self.assertEqual(medium["model_size_class"], "medium")
        self.assertFalse(medium["small_model_candidate"])

        with get_connection(self.engine) as conn:
            score_rows = fetch_all(conn, select(scores_table))
            source_runs = fetch_all(
                conn,
                select(source_runs_table).where(source_runs_table.c.source_name == "huggingface_model_discovery"),
            )
            raw_records = fetch_all(
                conn,
                select(raw_source_records_table).where(raw_source_records_table.c.source_run_id == source_runs[0]["id"]),
            )
        self.assertEqual(score_rows, [])
        self.assertEqual(len(source_runs), 1)
        self.assertEqual(len(raw_records), 9)

        rankings = update_engine.get_rankings("small_model_routing")
        self.assertIsNotNone(rankings)
        ranked_names = [row["model"]["name"] for row in rankings["rankings"]]
        self.assertNotIn(e2b["name"], ranked_names)

        self.add_score(e2b["id"], "aa_cost", 0.02)
        self.add_score(e2b["id"], "aa_speed", 220.0)

        refreshed_rankings = update_engine.get_rankings("small_model_routing")
        self.assertIsNotNone(refreshed_rankings)
        refreshed_ranked_names = [row["model"]["name"] for row in refreshed_rankings["rankings"]]
        self.assertIn(e2b["name"], refreshed_ranked_names)

    def test_huggingface_model_discovery_applies_configured_model_roles(self) -> None:
        entry = {
            "source": "huggingface",
            "family": "nvidia-embedding",
            "provider": "NVIDIA",
            "author": "nvidia",
            "queries": ["NV-Embed"],
            "include_patterns": ["nvidia/NV-Embed*"],
            "trusted_mirrors": [],
            "model_roles": ["embedding"],
        }
        items = [
            {
                "modelId": "nvidia/NV-Embed-v2",
                "pipeline_tag": "feature-extraction",
                "tags": ["sentence-transformers", "retrieval"],
            }
        ]

        with patch.object(update_engine.model_discovery, "huggingface_discovery_entries", return_value=[entry]), patch.object(
            update_engine.model_discovery,
            "fetch_huggingface_discovery_items",
            return_value=items,
        ):
            summary = update_engine.refresh_model_discovery_metadata(source="huggingface", family="nvidia-embedding")

        self.assertEqual(summary["records_found"], 1)
        models = update_engine.list_models()
        discovered = next(model for model in models if model.get("huggingface_repo_id") == "nvidia/NV-Embed-v2")
        self.assertEqual(discovered["provider"], "NVIDIA")
        self.assertEqual(discovered["model_roles"], ["embedding"])
        self.assertEqual(discovered["metadata_source_name"], "huggingface_model_discovery")

    def test_huggingface_model_discovery_adds_phi_small_model_candidates(self) -> None:
        entry = {
            "source": "huggingface",
            "family": "phi",
            "provider": "Microsoft",
            "author": "microsoft",
            "queries": ["Phi"],
            "include_patterns": ["microsoft/Phi-4*", "microsoft/phi-4*"],
            "exclude_patterns": ["microsoft/Phi-Ground*"],
            "trusted_mirrors": [],
            "model_roles": ["generator"],
            "small_model_candidate_if_unknown": True,
        }
        items = [
            {
                "modelId": "microsoft/Phi-4-mini-instruct",
                "pipeline_tag": "text-generation",
                "tags": ["transformers", "text-generation", "license:mit"],
            },
            {
                "modelId": "microsoft/phi-4",
                "pipeline_tag": "text-generation",
                "tags": ["transformers", "text-generation", "license:mit"],
            },
            {
                "modelId": "microsoft/Phi-Ground",
                "pipeline_tag": None,
                "tags": ["pytorch"],
            },
        ]

        with patch.object(update_engine.model_discovery, "huggingface_discovery_entries", return_value=[entry]), patch.object(
            update_engine.model_discovery,
            "fetch_huggingface_discovery_items",
            return_value=items,
        ):
            summary = update_engine.refresh_model_discovery_metadata(source="huggingface", family="phi")

        self.assertEqual(summary["records_found"], 2)
        self.assertEqual(summary["models_created"], 2)

        models = update_engine.list_models()
        by_repo_id = {model.get("huggingface_repo_id"): model for model in models if model.get("huggingface_repo_id")}
        self.assertIn("microsoft/Phi-4-mini-instruct", by_repo_id)
        self.assertIn("microsoft/phi-4", by_repo_id)
        self.assertNotIn("microsoft/Phi-Ground", by_repo_id)

        mini = by_repo_id["microsoft/Phi-4-mini-instruct"]
        self.assertEqual(mini["provider"], "Microsoft")
        self.assertEqual(mini["model_roles"], ["generator"])
        self.assertTrue(mini["small_model_candidate"])
        self.assertEqual(mini["model_size_class"], "small")
        self.assertIsNone(mini["parameter_count_b"])
        self.assertEqual(mini["metadata_source_name"], "huggingface_model_discovery")

        with get_connection(self.engine) as conn:
            score_rows = fetch_all(conn, select(scores_table))
            raw_records = fetch_all(conn, select(raw_source_records_table))
        self.assertEqual(score_rows, [])
        self.assertEqual(len(raw_records), 2)

    def test_catalog_model_discovery_adds_provider_catalog_embedding_rows(self) -> None:
        entry = {
            "source": "catalog",
            "family": "ibm-watsonx-retrieval",
            "provider": "IBM",
            "source_url": "https://example.test/ibm-embeddings",
            "models": [
                {
                    "id": "ibm-slate-30m-english-rtrvr",
                    "name": "Slate 30M English Retriever",
                    "catalog_model_id": "ibm/slate-30m-english-rtrvr",
                    "model_roles": ["embedding"],
                    "parameter_count_b": 0.03,
                    "context_window_tokens": 8192,
                    "max_output_tokens": 1024,
                    "price_input_per_mtok": 0.25,
                    "price_output_per_mtok": 1.25,
                    "release_date": "2026-06-15",
                    "release_date_precision": "day",
                    "release_date_confidence": "high",
                    "model_card_url": "https://example.test/slate-card",
                    "capabilities": ["embedding", "retrieval", "watsonx"],
                }
            ],
        }

        with patch.object(update_engine.model_discovery, "catalog_discovery_entries", return_value=[entry]):
            summary = update_engine.refresh_model_discovery_metadata(source="catalog", family="ibm-watsonx-retrieval")

        self.assertEqual(summary["records_found"], 1)
        model = next(model for model in update_engine.list_models() if model["id"] == "ibm-slate-30m-english-rtrvr")
        self.assertEqual(model["provider"], "IBM")
        self.assertEqual(model["model_roles"], ["embedding"])
        self.assertEqual(model["catalog_status"], "tracked")
        self.assertEqual(model["metadata_source_name"], "catalog_model_discovery")
        self.assertEqual(model["model_card_url"], "https://example.test/slate-card")
        self.assertEqual(model["parameter_count_b"], 0.03)
        self.assertEqual(model["context_window_tokens"], 8192)
        self.assertEqual(model["max_output_tokens"], 1024)
        self.assertEqual(model["price_input_per_mtok"], 0.25)
        self.assertEqual(model["price_output_per_mtok"], 1.25)
        self.assertEqual(model["release_date"], "2026-06-15")
        self.assertEqual(model["release_date_confidence"], "high")

        with get_connection(self.engine) as conn:
            score_rows = fetch_all(conn, select(scores_table))
            source_runs = fetch_all(
                conn,
                select(source_runs_table).where(source_runs_table.c.source_name == "catalog_model_discovery"),
            )
            raw_records = fetch_all(
                conn,
                select(raw_source_records_table).where(raw_source_records_table.c.source_run_id == source_runs[0]["id"]),
            )
        self.assertEqual(score_rows, [])
        self.assertEqual(len(source_runs), 1)
        self.assertEqual(len(raw_records), 1)

    def test_blueprint_catalog_imports_all_roles_and_corrects_existing_vl_reranker(self) -> None:
        self.add_model(
            "llama-nemotron-rerank-vl-1b-v2",
            "Llama Nemotron Rerank VL 1B V2",
            provider="NVIDIA",
            model_roles=["generator"],
        )
        summary = update_engine.refresh_model_discovery_metadata(
            source="catalog", family="nvidia-enterprise-rag-blueprint"
        )
        self.assertEqual(summary["records_found"], 15)
        models = {model["id"]: model for model in update_engine.list_models()}
        self.assertEqual(models["llama-nemotron-rerank-vl-1b-v2"]["model_roles"], ["reranker"])
        self.assertEqual(models["nemotron-page-elements-v3"]["model_roles"], ["document_layout"])
        self.assertEqual(models["nemotron-ocr-v1"]["model_roles"], ["ocr"])
        self.assertEqual(models["llama-3_1-nemoguard-8b-topic-control"]["model_roles"], ["content_safety"])

    def test_openrouter_normal_and_free_aliases_create_one_canonical_row(self) -> None:
        self.add_model("anchor", "Anchor")
        items = [
            {"id": "nvidia/llama-nemotron-rerank-vl-1b-v2", "canonical_slug": "nvidia/llama-nemotron-rerank-vl-1b-v2", "name": "NVIDIA: Llama Nemotron Rerank VL 1B V2", "created": 1780000000},
            {"id": "nvidia/llama-nemotron-rerank-vl-1b-v2:free", "canonical_slug": "nvidia/llama-nemotron-rerank-vl-1b-v2", "name": "NVIDIA: Llama Nemotron Rerank VL 1B V2 (free)", "created": 1780000000},
        ]
        with patch.object(update_engine, "_fetch_openrouter_models", return_value=items), patch.object(
            update_engine.pricing, "sync_openrouter_items"
        ):
            update_engine._refresh_openrouter_model_metadata()
        with get_connection(self.engine) as conn:
            rows = fetch_all(conn, select(models_table).where(
                models_table.c.openrouter_canonical_slug == "nvidia/llama-nemotron-rerank-vl-1b-v2"
            ))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Llama Nemotron Rerank Vl 1B V2")
        self.assertEqual(rows[0]["openrouter_model_id"], "nvidia/llama-nemotron-rerank-vl-1b-v2")
        self.assertEqual(rows[0]["openrouter_canonical_slug"], "nvidia/llama-nemotron-rerank-vl-1b-v2")
        self.assertEqual(json.loads(rows[0]["model_roles_json"]), ["reranker"])

    def test_repair_trailing_free_display_names_preserves_linked_fields(self) -> None:
        self.add_model("free-model", "Example (free)")
        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "free-model")
                .values(openrouter_model_id="vendor/example:free", openrouter_canonical_slug="vendor/example")
            )
            conn.execute(
                model_use_case_approvals_table.insert().values(
                    model_id="free-model",
                    use_case_id="customer_service",
                    approved_for_use=1,
                    approval_notes="retain",
                    approval_updated_at="2026-07-17T00:00:00Z",
                )
            )

        self.assertEqual(update_engine._repair_trailing_free_display_names(), 1)
        with self.engine.connect() as conn:
            model = conn.execute(select(models_table).where(models_table.c.id == "free-model")).mappings().one()
            approval = conn.execute(
                select(model_use_case_approvals_table).where(model_use_case_approvals_table.c.model_id == "free-model")
            ).mappings().one()
        self.assertEqual(model["name"], "Example")
        self.assertEqual(model["openrouter_model_id"], "vendor/example:free")
        self.assertEqual(model["openrouter_canonical_slug"], "vendor/example")
        self.assertEqual(approval["approval_notes"], "retain")

    def test_provider_api_model_discovery_adds_rich_provider_catalog_rows(self) -> None:
        catalog = {
            "id": "openai",
            "family": "openai-api",
            "provider": "OpenAI",
            "model_type": "proprietary",
            "model_roles": ["generator"],
            "source_url": "https://api.openai.com/v1/models",
            "documentation_url": "https://platform.openai.com/docs/api-reference/models/list",
        }
        items = [
            {
                "id": "gpt-5-6-sol",
                "name": "GPT-5.6 Sol",
                "provider": "OpenAI",
                "catalog_model_id": "openai/gpt-5.6-sol",
                "model_roles": ["generator"],
                "context_window_tokens": 256000,
                "max_output_tokens": 32768,
                "price_input_per_mtok": 5.0,
                "price_output_per_mtok": 30.0,
                "capabilities": ["reasoning", "tool-use", "provider-api:openai"],
                "metadata_source_name": "provider_api_model_discovery",
                "documentation_url": "https://platform.openai.com/docs/models",
                "source_url": "https://api.openai.com/v1/models",
            }
        ]

        with patch.object(update_engine.provider_catalogs, "provider_api_catalogs", return_value=[catalog]), patch.object(
            update_engine.provider_catalogs,
            "fetch_provider_api_catalog_models",
            return_value=items,
        ):
            summary = update_engine.refresh_model_discovery_metadata(source="provider-api", family="openai")

        self.assertEqual(summary["records_found"], 1)
        self.assertEqual(summary["models_created"], 1)
        self.assertEqual(summary["sources_skipped"], 0)
        model = next(model for model in update_engine.list_models() if model["id"] == "gpt-5-6-sol")
        self.assertEqual(model["provider"], "OpenAI")
        self.assertEqual(model["metadata_source_name"], "provider_api_model_discovery")
        self.assertEqual(model["context_window_tokens"], 256000)
        self.assertEqual(model["max_output_tokens"], 32768)
        self.assertEqual(model["price_input_per_mtok"], 5.0)
        self.assertEqual(model["price_output_per_mtok"], 30.0)
        self.assertEqual(model["catalog_status"], "provisional")
        self.assertIn("provider-api:openai", model["capabilities"])

        with get_connection(self.engine) as conn:
            score_rows = fetch_all(conn, select(scores_table))
            source_runs = fetch_all(
                conn,
                select(source_runs_table).where(source_runs_table.c.source_name == "provider_api_model_discovery"),
            )
            raw_records = fetch_all(
                conn,
                select(raw_source_records_table).where(raw_source_records_table.c.source_run_id == source_runs[0]["id"]),
            )
        self.assertEqual(score_rows, [])
        self.assertEqual(len(source_runs), 1)
        self.assertEqual(source_runs[0]["status"], "completed")
        self.assertEqual(len(raw_records), 1)

    def test_provider_api_model_discovery_skips_missing_credentials(self) -> None:
        catalog = {
            "id": "anthropic",
            "family": "anthropic-api",
            "provider": "Anthropic",
            "model_type": "proprietary",
            "model_roles": ["generator"],
        }

        with patch.object(update_engine.provider_catalogs, "provider_api_catalogs", return_value=[catalog]), patch.object(
            update_engine.provider_catalogs,
            "fetch_provider_api_catalog_models",
            side_effect=update_engine.provider_catalogs.ProviderCatalogNotConfigured("Missing ANTHROPIC_API_KEY"),
        ):
            summary = update_engine.refresh_model_discovery_metadata(source="provider-api", family="anthropic")

        self.assertEqual(summary["records_found"], 0)
        self.assertEqual(summary["sources_skipped"], 1)
        with get_connection(self.engine) as conn:
            source_runs = fetch_all(
                conn,
                select(source_runs_table).where(source_runs_table.c.source_name == "provider_api_model_discovery"),
            )
        self.assertEqual(len(source_runs), 1)
        self.assertEqual(source_runs[0]["status"], "skipped")

    def test_provider_api_failure_redacts_google_query_key(self) -> None:
        secret = "google-super-secret"
        catalog = {
            "id": "google-gemini",
            "family": "google-gemini",
            "provider": "Google",
            "model_type": "proprietary",
            "model_roles": ["generator"],
        }
        request = httpx.Request(
            "GET",
            f"https://generativelanguage.googleapis.com/v1beta/models?key={secret}&pageSize=1000",
        )
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError("provider failed", request=request, response=response)

        with patch.object(update_engine.provider_catalogs, "provider_api_catalogs", return_value=[catalog]), patch.object(
            update_engine.provider_catalogs,
            "fetch_provider_api_catalog_models",
            side_effect=error,
        ):
            summary = update_engine.refresh_model_discovery_metadata(
                source="provider-api", family="google-gemini"
            )

        with get_connection(self.engine) as conn:
            source_run = fetch_all(
                conn,
                select(source_runs_table).where(
                    source_runs_table.c.source_name == "provider_api_model_discovery"
                ),
            )[0]
        self.assertEqual(summary["sources_failed"], 1)
        self.assertNotIn(secret, json.dumps(summary))
        self.assertNotIn(secret, str(source_run["error_message"]))

    def test_provider_api_gpt_5_6_identity_does_not_duplicate_curated_tracked_row(self) -> None:
        self.add_model("gpt-5-6-sol", "GPT-5.6 Sol", provider="OpenAI")
        catalog = {
            "id": "openai",
            "family": "openai-api",
            "provider": "OpenAI",
            "model_type": "proprietary",
            "model_roles": ["generator"],
        }
        items = [{
            "id": "gpt-5.6-sol",
            "name": "GPT-5.6 Sol",
            "provider": "OpenAI",
            "catalog_model_id": "openai/gpt-5.6-sol",
            "catalog_status": "provisional",
            "model_roles": ["generator"],
            "metadata_source_name": "provider_api_model_discovery",
            "source_url": "https://api.openai.com/v1/models",
        }]

        with patch.object(update_engine.provider_catalogs, "provider_api_catalogs", return_value=[catalog]), patch.object(
            update_engine.provider_catalogs,
            "fetch_provider_api_catalog_models",
            return_value=items,
        ):
            summary = update_engine.refresh_model_discovery_metadata(source="provider-api", family="openai")

        matching = [model for model in update_engine.list_models() if model["name"] == "GPT-5.6 Sol"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["id"], "gpt-5-6-sol")
        self.assertEqual(matching[0]["catalog_status"], "tracked")
        self.assertEqual(summary["models_created"], 0)

    def test_gpt_5_6_effort_observations_use_three_models_and_remain_distinct(self) -> None:
        tiers = ("sol", "terra", "luna")
        efforts = ("none", "low", "medium", "high", "xhigh", "max")
        candidates = [
            ScoreCandidate(
                source_id="artificial_analysis",
                benchmark_id="aa_intelligence",
                raw_model_name=f"GPT-5.6 {tier.title()} ({effort})",
                raw_model_key=f"gpt-5-6-{tier}-{effort}",
                value=float(index),
                raw_value=str(index),
                source_url="https://artificialanalysis.ai/leaderboards/models",
                collected_at="2026-07-14T00:00:00Z",
            )
            for index, (tier, effort) in enumerate(
                ((tier, effort) for tier in tiers for effort in efforts), start=1
            )
        ]
        result = SourceFetchResult(
            source_id="artificial_analysis",
            source_url="https://artificialanalysis.ai/leaderboards/models",
            fetched_at="2026-07-14T00:00:00Z",
            raw_records=[],
            candidates=candidates,
        )

        added, updated = update_engine._persist_source_result(1, result)

        self.assertEqual((added, updated), (18, 0))
        with self.engine.begin() as conn:
            rows = conn.execute(
                scores_table.select().where(scores_table.c.model_id.like("gpt-5-6-%"))
            ).mappings().all()
            active_ids = conn.execute(
                select(models_table.c.id).where(models_table.c.id.like("gpt-5-6-%"), models_table.c.active == 1)
            ).scalars().all()
        self.assertEqual(set(active_ids), {"gpt-5-6-sol", "gpt-5-6-terra", "gpt-5-6-luna"})
        self.assertEqual(len(rows), 18)
        self.assertEqual({row["configuration_key"] for row in rows}, {"reasoning_effort"})
        self.assertEqual({row["configuration_value"] for row in rows}, set(efforts))
        models = {model["id"]: model for model in update_engine.list_models() if model["id"] in active_ids}
        self.assertTrue(all(len(model["score_configurations"]) == 6 for model in models.values()))

    def test_openrouter_does_not_clobber_curated_provenance_or_import_gpt56_modes(self) -> None:
        values = update_engine._openrouter_model_values(
            {"id": "openai/gpt-5.6-sol", "canonical_slug": "openai/gpt-5.6-sol"},
            verified_at="2026-07-14T00:00:00Z",
            current_metadata_source_name="catalog_model_discovery",
            current_catalog_status="tracked",
        )
        self.assertNotIn("metadata_source_name", values)
        with self.engine.begin() as conn:
            update_engine._import_openrouter_provisional_models(
                conn,
                unmatched_items=[{
                    "id": "openai/gpt-5.6-sol-pro",
                    "canonical_slug": "openai/gpt-5.6-sol-pro-20260709",
                    "name": "OpenAI: GPT-5.6 Sol Pro",
                }],
                existing_canonical_model_ids=set(),
                verified_at="2026-07-14T00:00:00Z",
                allow_existing_canonical_model_ids=True,
            )
            rows = conn.execute(
                select(models_table.c.id).where(models_table.c.name.like("%GPT-5.6%"))
            ).all()
        self.assertEqual(rows, [])

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

    def test_canonical_models_use_provenance_first_variant_per_benchmark(self) -> None:
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

        self.add_score(
            "suite-b",
            "swebench_verified",
            95.0,
            collected_at="2026-04-02T00:01:00Z",
            source_type="secondary",
            verified=False,
        )
        self.add_score(
            "suite-b",
            "aa_intelligence",
            95.0,
            collected_at="2026-04-02T00:01:00Z",
            source_type="secondary",
            verified=False,
        )
        self.add_score(
            "suite-b",
            "terminal_bench",
            95.0,
            collected_at="2026-04-02T00:01:00Z",
            source_type="secondary",
            verified=False,
        )

        self.add_score("competitor", "swebench_verified", 70.0)
        self.add_score("competitor", "aa_intelligence", 50.0)
        self.add_score("competitor", "terminal_bench", 70.0)

        suite = self.ranking_for("coding", "Suite")
        breakdown = {item["benchmark_id"]: item for item in suite["breakdown"]}

        self.assertEqual(suite["model"]["id"], "suite")
        self.assertEqual(breakdown["swebench_verified"]["variant_model_name"], "Suite A")
        self.assertEqual(breakdown["terminal_bench"]["variant_model_name"], "Suite A")
        self.assertEqual(breakdown["aa_intelligence"]["variant_model_name"], "Suite A")
        self.assertIn("display", breakdown["swebench_verified"])
        self.assertIn("comparison", breakdown["swebench_verified"])
        self.assertIn("evidence", breakdown["swebench_verified"])

    def test_list_models_reuses_one_full_comparison_context_and_has_constant_query_count(self) -> None:
        self.add_model("cache-one", "Cache One")
        self.add_score("cache-one", "gpqa_diamond", 70.0)
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                {
                    "model_id": "cache-one",
                    "benchmark_id": "gpqa_diamond",
                    "value": 71.0,
                    "raw_value": "71.0",
                    "collected_at": "2026-04-03T00:00:00Z",
                    "source_type": "primary",
                    "verified": 1,
                    "configuration_key": "reasoning_effort",
                    "configuration_value": "high",
                },
            )

        benchmark_comparisons.invalidate_comparison_cache()
        builds_before = benchmark_comparisons.comparison_cache_info()["builds"]
        update_engine.list_models()
        after_first = benchmark_comparisons.comparison_cache_info()
        update_engine.list_models()
        after_second = benchmark_comparisons.comparison_cache_info()

        self.assertEqual(after_first["builds"], builds_before + 1)
        self.assertEqual(after_second["builds"], after_first["builds"])
        self.assertEqual(after_second["cohort_stats"], after_first["cohort_stats"])
        self.assertEqual(after_second["positions"], after_first["positions"])

        def select_count() -> int:
            statements: list[str] = []

            def before_cursor_execute(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
                if str(statement).lstrip().upper().startswith("SELECT"):
                    statements.append(str(statement))

            event.listen(self.engine, "before_cursor_execute", before_cursor_execute)
            try:
                update_engine.list_models()
            finally:
                event.remove(self.engine, "before_cursor_execute", before_cursor_execute)
            return len(statements)

        one_model_queries = select_count()
        for index in range(12):
            model_id = f"cache-extra-{index}"
            self.add_model(model_id, f"Cache Extra {index}")
            self.add_score(model_id, "gpqa_diamond", 40.0 + index)
        benchmark_comparisons.invalidate_comparison_cache()
        many_model_queries = select_count()
        self.assertEqual(many_model_queries, one_model_queries)

    def test_equal_value_refresh_enriches_evidence_without_lowering_source_trust(self) -> None:
        self.add_model("mteb-refresh", "MTEB Refresh", model_roles=["embedding"])
        self.add_score(
            "mteb-refresh",
            "mteb_retrieval",
            73.14,
            collected_at="2026-01-01T00:00:00Z",
        )
        with self.engine.begin() as conn:
            conn.execute(
                update(scores_table)
                .where(scores_table.c.model_id == "mteb-refresh")
                .values(
                    observation_count=12,
                    confidence_lower=70.0,
                    rank=4,
                    methodology="preserve me",
                    style_control=0,
                    source_metadata_json=json.dumps(
                        {"task_names": ["NFCorpus"], "dataset_revision": "dataset-a"},
                        sort_keys=True,
                    ),
                )
            )
        candidate = ScoreCandidate(
            source_id="mteb",
            benchmark_id="mteb_retrieval",
            raw_model_name="MTEB Refresh",
            raw_model_key="MTEB Refresh",
            value=73.14,
            raw_value="73.14",
            source_url="https://example.test/mteb",
            collected_at="2026-07-15T00:00:00Z",
            source_type="primary",
            verified=True,
            observation_count=12,
            source_metadata={
                "task_names": ["NFCorpus", "SciFact"],
                "dataset_revision": "dataset-a",
            },
            metadata={"model_roles": ["embedding"]},
        )

        result = update_engine._persist_score_candidate(candidate, resolved_model_id="mteb-refresh")
        self.assertEqual(result, ("mteb-refresh", "updated"))
        with get_connection(self.engine) as conn:
            refreshed = fetch_all(
                conn,
                select(scores_table)
                .where(scores_table.c.model_id == "mteb-refresh")
                .where(scores_table.c.benchmark_id == "mteb_retrieval"),
            )
        self.assertEqual(len(refreshed), 1)
        self.assertEqual(refreshed[0]["observation_count"], 12)
        source_metadata = json.loads(str(refreshed[0]["source_metadata_json"]))
        self.assertEqual(source_metadata["dataset_revision"], "dataset-a")
        self.assertEqual(source_metadata["task_names"], ["NFCorpus", "SciFact"])
        self.assertEqual(refreshed[0]["collected_at"], "2026-07-15T00:00:00Z")
        self.assertEqual(refreshed[0]["confidence_lower"], 70.0)
        self.assertEqual(refreshed[0]["rank"], 4)
        self.assertEqual(refreshed[0]["methodology"], "preserve me")
        self.assertEqual(refreshed[0]["style_control"], 0)

        lower_trust = replace(
            candidate,
            collected_at="2026-07-16T00:00:00Z",
            source_type="secondary",
            verified=False,
            observation_count=99,
        )
        self.assertEqual(
            update_engine._persist_score_candidate(lower_trust, resolved_model_id="mteb-refresh"),
            ("mteb-refresh", "skipped"),
        )

    def test_source_result_duplicate_candidates_use_provenance_not_numeric_value(self) -> None:
        self.add_model("batch-probe", "Batch Probe")
        source_run_id = self.add_source_run("probe", "gpqa_diamond")

        def candidate(*, value: float, source_type: str, verified: bool) -> ScoreCandidate:
            return ScoreCandidate(
                source_id="probe",
                benchmark_id="gpqa_diamond",
                raw_model_name="Batch Probe",
                raw_model_key="batch-probe",
                value=value,
                raw_value=str(value),
                source_url="https://example.test/probe",
                collected_at="2026-07-15T00:00:00Z",
                source_type=source_type,
                verified=verified,
                metadata={"existing_models_only": True, "model_roles": ["generator"]},
            )

        result = SourceFetchResult(
            source_id="probe",
            source_url="https://example.test/probe",
            fetched_at="2026-07-15T00:00:00Z",
            raw_records=[],
            candidates=[
                candidate(value=90.0, source_type="secondary", verified=False),
                candidate(value=70.0, source_type="primary", verified=True),
            ],
        )

        self.assertEqual(update_engine._persist_source_result(source_run_id, result), (1, 0))
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(scores_table)
                .where(scores_table.c.model_id == "batch-probe")
                .where(scores_table.c.benchmark_id == "gpqa_diamond")
            ).mappings().all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["value"]), 70.0)
        self.assertEqual(rows[0]["source_type"], "primary")
        self.assertEqual(int(rows[0]["verified"]), 1)

    def test_source_result_dedup_keeps_distinct_evaluation_signatures(self) -> None:
        self.add_model("signature-probe", "Signature Probe", model_roles=["embedding"])
        source_run_id = self.add_source_run("mteb", "mteb_retrieval")

        def candidate(task_name: str, value: float) -> ScoreCandidate:
            return ScoreCandidate(
                source_id="mteb",
                benchmark_id="mteb_retrieval",
                raw_model_name="Signature Probe",
                raw_model_key="signature-probe",
                value=value,
                raw_value=str(value),
                source_url="https://example.test/mteb",
                collected_at="2026-07-15T00:00:00Z",
                source_type="primary",
                verified=True,
                source_metadata={"task_names": [task_name], "dataset_revision": "rev-a"},
                metadata={"existing_models_only": True, "model_roles": ["embedding"]},
            )

        result = SourceFetchResult(
            source_id="mteb",
            source_url="https://example.test/mteb",
            fetched_at="2026-07-15T00:00:00Z",
            raw_records=[],
            candidates=[candidate("NFCorpus", 70.0), candidate("SciFact", 90.0)],
        )
        persisted: list[ScoreCandidate] = []

        def capture(candidate: ScoreCandidate, resolved_model_id: str | None = None, **_kwargs) -> tuple[str, str]:
            persisted.append(candidate)
            return resolved_model_id or "signature-probe", "added"

        with patch.object(update_engine, "_persist_score_candidate", side_effect=capture):
            self.assertEqual(update_engine._persist_source_result(source_run_id, result), (2, 0))

        self.assertEqual(len(persisted), 2)
        self.assertEqual(
            {tuple(item.source_metadata["task_names"]) for item in persisted},
            {("NFCorpus",), ("SciFact",)},
        )

    def test_score_refresh_cannot_rewind_downgrade_or_choose_a_flattering_value(self) -> None:
        self.add_model("refresh-guard", "Refresh Guard", model_roles=["embedding"])
        trusted = ScoreCandidate(
            source_id="mteb",
            benchmark_id="mteb_retrieval",
            raw_model_name="Refresh Guard",
            raw_model_key="refresh-guard",
            value=73.14,
            raw_value="73.14",
            source_url="https://example.test/mteb",
            collected_at="2026-07-15T00:00:00Z",
            source_type="primary",
            verified=True,
            observation_count=12,
            source_metadata={"task_names": ["NFCorpus"], "dataset_revision": "rev-a"},
            metadata={"model_roles": ["embedding"]},
        )
        self.assertEqual(
            update_engine._persist_score_candidate(trusted, resolved_model_id="refresh-guard"),
            ("refresh-guard", "added"),
        )

        older = replace(
            trusted,
            collected_at="2026-01-01T00:00:00Z",
            observation_count=99,
            source_metadata={"task_names": ["NFCorpus", "SciFact"], "dataset_revision": "rev-old"},
        )
        lower_trust_revision = replace(
            trusted,
            source_type="secondary",
            verified=False,
            observation_count=99,
            source_metadata={"task_names": ["NFCorpus"], "dataset_revision": "rev-b"},
        )
        flattering_same_signature = replace(trusted, value=99.0, raw_value="99.0")

        for rejected in (older, lower_trust_revision, flattering_same_signature):
            self.assertEqual(
                update_engine._persist_score_candidate(rejected, resolved_model_id="refresh-guard"),
                ("refresh-guard", "skipped"),
            )

        with self.engine.connect() as conn:
            rows = conn.execute(
                select(scores_table)
                .where(scores_table.c.model_id == "refresh-guard")
                .where(scores_table.c.benchmark_id == "mteb_retrieval")
            ).mappings().all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["value"]), 73.14)
        self.assertEqual(rows[0]["collected_at"], "2026-07-15T00:00:00Z")
        self.assertEqual(rows[0]["source_type"], "primary")
        self.assertEqual(int(rows[0]["verified"]), 1)
        self.assertEqual(
            json.loads(str(rows[0]["source_metadata_json"]))["dataset_revision"],
            "rev-a",
        )

    def test_non_finite_public_score_is_null_invalid_and_excluded_from_rankings(self) -> None:
        self.add_model("non-finite", "Non-finite")
        self.add_score("non-finite", "gpqa_diamond", float("inf"))

        public_models = update_engine.list_models()
        public = next(model for model in public_models if model["id"] == "non-finite")
        score = public["scores"]["gpqa_diamond"]
        self.assertIsNone(score["value"])
        self.assertEqual(score["raw_value"], "inf")
        self.assertEqual(score["display"]["formatted"], "Data check needed")
        self.assertEqual(score["comparison"]["status"], "invalid")
        json.dumps(public_models, allow_nan=False)

        benchmarks = {item["id"]: item for item in update_engine.list_benchmarks()}
        self.assertIsNone(benchmarks["gpqa_diamond"]["range_min"])
        self.assertIsNone(benchmarks["gpqa_diamond"]["range_max"])
        canonical = update_engine._build_canonical_models(public_models, benchmarks)
        canonical_model = next(model for model in canonical if model["id"] == "non-finite")
        self.assertIsNone(canonical_model["scores"]["gpqa_diamond"])

        recommendation_models = update_engine.list_models(include_recommendation_proposals=False)
        recommendation = next(model for model in recommendation_models if model["id"] == "non-finite")
        self.assertIsNone(recommendation["scores"]["gpqa_diamond"])

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

        self.assertEqual(len(gpt["inference_destinations"]), 2)
        azure = next(item for item in gpt["inference_destinations"] if item["id"] == "azure-ai-foundry")
        self.assertEqual(azure["regions"], ["eastus2"])
        self.assertEqual(azure["deployment_modes"], ["Provisioned"])
        self.assertEqual(
            azure["pricing_label"],
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

    def test_provider_aliases_are_canonicalized_for_models_and_provider_facets(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                providers_table.insert(),
                [
                    {
                        "id": "amazon-nova",
                        "name": "Amazon Nova",
                        "country_code": "US",
                        "country_name": "United States",
                        "origin_countries_json": "[]",
                        "active": 1,
                    },
                    {
                        "id": "microsoft-azure",
                        "name": "Microsoft Azure",
                        "country_code": "US",
                        "country_name": "United States",
                        "origin_countries_json": "[]",
                        "active": 1,
                    },
                    {
                        "id": "qwen",
                        "name": "Qwen",
                        "country_code": "CN",
                        "country_name": "China",
                        "origin_countries_json": "[]",
                        "active": 1,
                    },
                    {
                        "id": "mistral",
                        "name": "Mistral",
                        "country_code": "FR",
                        "country_name": "France",
                        "origin_countries_json": "[]",
                        "active": 1,
                    },
                    {
                        "id": "ibm-granite",
                        "name": "ibm-granite",
                        "country_code": "US",
                        "country_name": "United States",
                        "origin_countries_json": "[]",
                        "active": 1,
                    },
                ],
            )
            conn.execute(
                models_table.insert(),
                [
                    {
                        "id": "nova-provider-alias",
                        "name": "Nova Pro",
                        "provider_id": "amazon-nova",
                        "provider": "Amazon Nova",
                        "type": "proprietary",
                        "family_id": "amazon-nova::nova",
                        "family_name": "Nova",
                        "canonical_model_id": "amazon-nova::nova-pro",
                        "canonical_model_name": "Nova Pro",
                        "model_roles_json": json.dumps(["generator"], ensure_ascii=True),
                        "active": 1,
                    },
                    {
                        "id": "phi-provider-alias",
                        "name": "Phi 4",
                        "provider_id": "microsoft-azure",
                        "provider": "Microsoft Azure",
                        "type": "proprietary",
                        "family_id": "microsoft-azure::phi",
                        "family_name": "Phi",
                        "canonical_model_id": "microsoft-azure::phi-4",
                        "canonical_model_name": "Phi 4",
                        "model_roles_json": json.dumps(["generator"], ensure_ascii=True),
                        "active": 1,
                    },
                    {
                        "id": "qwen-provider-alias",
                        "name": "Qwen2.5 7B Instruct",
                        "provider_id": "qwen",
                        "provider": "Qwen",
                        "type": "open_weights",
                        "family_id": "qwen::qwen2-5",
                        "family_name": "Qwen2.5",
                        "canonical_model_id": "qwen::qwen2-5-7b-instruct",
                        "canonical_model_name": "Qwen2.5 7B Instruct",
                        "model_roles_json": json.dumps(["generator"], ensure_ascii=True),
                        "active": 1,
                    },
                    {
                        "id": "mistral-provider-alias",
                        "name": "Mistral 7B Instruct",
                        "provider_id": "mistral",
                        "provider": "Mistral",
                        "type": "open_weights",
                        "family_id": "mistral::mistral-7b",
                        "family_name": "Mistral 7B",
                        "canonical_model_id": "mistral::mistral-7b-instruct",
                        "canonical_model_name": "Mistral 7B Instruct",
                        "model_roles_json": json.dumps(["generator"], ensure_ascii=True),
                        "active": 1,
                    },
                    {
                        "id": "ibm-granite-provider-alias",
                        "name": "Granite 4.1 3B",
                        "provider_id": "ibm-granite",
                        "provider": "ibm-granite",
                        "type": "open_weights",
                        "family_id": "ibm-granite::granite-4-1",
                        "family_name": "Granite 4.1",
                        "canonical_model_id": "ibm-granite::granite-4-1-3b",
                        "canonical_model_name": "Granite 4.1 3B",
                        "model_roles_json": json.dumps(["generator"], ensure_ascii=True),
                        "active": 1,
                    },
                ],
            )

        update_engine._sync_provider_directory()
        update_engine._canonicalize_provider_aliases()
        update_engine._refresh_model_identity_metadata()

        models = update_engine.list_models()
        nova = next(model for model in models if model["id"] == "nova-provider-alias")
        phi = next(model for model in models if model["id"] == "phi-provider-alias")
        qwen = next(model for model in models if model["id"] == "qwen-provider-alias")
        mistral = next(model for model in models if model["id"] == "mistral-provider-alias")
        granite = next(model for model in models if model["id"] == "ibm-granite-provider-alias")
        self.assertEqual(nova["provider"], "Amazon")
        self.assertEqual(nova["provider_id"], "amazon")
        self.assertEqual(nova["family_id"], "amazon::nova-pro")
        self.assertEqual(phi["provider"], "Microsoft")
        self.assertEqual(phi["provider_id"], "microsoft")
        self.assertEqual(phi["family_id"], "microsoft::phi-4")
        self.assertEqual(qwen["provider"], "Alibaba")
        self.assertEqual(qwen["provider_id"], "alibaba")
        self.assertEqual(qwen["family_id"], "alibaba::qwen2-5")
        self.assertEqual(mistral["provider"], "Mistral AI")
        self.assertEqual(mistral["provider_id"], "mistral-ai")
        self.assertEqual(mistral["family_id"], "mistral-ai::mistral-7b")
        self.assertEqual(granite["provider"], "IBM")
        self.assertEqual(granite["provider_id"], "ibm")
        self.assertEqual(granite["family_id"], "ibm::granite-4-1")

        provider_names = {provider["name"] for provider in update_engine.list_providers()}
        self.assertIn("Amazon", provider_names)
        self.assertIn("Microsoft", provider_names)
        self.assertIn("Alibaba", provider_names)
        self.assertIn("Mistral AI", provider_names)
        self.assertIn("IBM", provider_names)
        self.assertNotIn("Amazon Nova", provider_names)
        self.assertNotIn("Microsoft Azure", provider_names)
        self.assertNotIn("Qwen", provider_names)
        self.assertNotIn("Mistral", provider_names)
        self.assertNotIn("ibm-granite", provider_names)

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

    def test_seed_reference_data_preserves_model_decisions_across_reseed(self) -> None:
        preserved_sentinels = {
            "general_approved_for_use": 1,
            "general_approval_notes": "General approval sentinel",
            "general_approval_updated_at": "2026-07-15T01:02:03Z",
            "general_recommendation_status": "restricted",
            "general_recommendation_notes": "General recommendation sentinel",
            "general_recommendation_updated_at": "2026-07-15T02:03:04Z",
            "reasoning_effort_ceiling": "high",
            "restricted_modes_json": '["pro"]',
            "usage_policy_notes": "Usage policy sentinel",
            "usage_policy_updated_at": "2026-07-15T03:04:05Z",
            "approved_for_use": 1,
            "approval_notes": "Legacy approval sentinel",
            "approval_updated_at": "2026-07-15T04:05:06Z",
            "catalog_status": "deprecated",
            "model_card_url": "https://example.com/enriched-model-card",
        }
        stale_seed_owned_values = {
            "name": "Stale seed name",
            "provider_id": None,
            "provider": "Stale provider",
            "type": "stale-type",
            "model_roles_json": '["reranker"]',
            "release_date": "1900",
            "context_window": "1 token",
            "active": 0,
        }

        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "gpt-5-4")
                .values(**preserved_sentinels, **stale_seed_owned_values)
            )
            seed_reference_data(conn, include_seed_scores=False)
            seed_reference_data(conn, include_seed_scores=False)
            model = conn.execute(
                models_table.select().where(models_table.c.id == "gpt-5-4")
            ).mappings().one()

        for field, expected in preserved_sentinels.items():
            with self.subTest(field=field):
                self.assertEqual(model[field], expected)

        self.assertEqual(
            {field: model[field] for field in stale_seed_owned_values},
            {
                "name": "GPT-5.4 (xhigh)",
                "provider_id": "openai",
                "provider": "OpenAI",
                "type": "proprietary",
                "model_roles_json": '["generator"]',
                "release_date": "2026-Q1",
                "context_window": "128k tokens",
                "active": 1,
            },
        )

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
        self.add_model(
            "family-restricted",
            "Family Restricted",
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
        update_engine.update_model_use_case_approval(
            "family-restricted",
            "coding",
            True,
            "Allowed for cyber team",
            "restricted",
            "Restricted to approved cyber staff.",
        )

        models = update_engine.list_models()
        recommended = next(model for model in models if model["id"] == "family-recommended")
        not_recommended = next(model for model in models if model["id"] == "family-not-recommended")
        restricted = next(model for model in models if model["id"] == "family-restricted")

        self.assertEqual(recommended["use_case_approvals"]["coding"]["recommendation_status"], "recommended")
        self.assertEqual(not_recommended["use_case_approvals"]["coding"]["recommendation_status"], "not_recommended")
        self.assertEqual(restricted["use_case_approvals"]["coding"]["recommendation_status"], "restricted")

        benchmarks = {benchmark["id"]: benchmark for benchmark in update_engine.list_benchmarks()}
        canonical_models = update_engine._build_canonical_models(models, benchmarks)
        family_model = next(model for model in canonical_models if model.get("family_id") == "rec-family")
        family_approval = family_model["use_case_approvals"]["coding"]

        self.assertEqual(family_approval["recommendation_status"], "mixed")
        self.assertEqual(family_approval["recommended_member_count"], 1)
        self.assertEqual(family_approval["not_recommended_member_count"], 1)
        self.assertEqual(family_approval["discouraged_member_count"], 0)
        self.assertEqual(family_approval["restricted_member_count"], 1)

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

    def test_fetch_openrouter_global_rankings_reports_missing_ranking_data_as_optional(self) -> None:
        with patch.object(update_engine, "_fetch_openrouter_flight_payloads", return_value=[{"props": {"page": "rankings"}}]):
            with self.assertRaises(update_engine.OptionalSourceUnavailable) as context:
                update_engine._fetch_openrouter_global_rankings()

        self.assertIn("rankingData", str(context.exception))

    def test_update_completes_with_nonfatal_openrouter_market_warning(self) -> None:
        audit_result = {
            "status": "passed",
            "findings": [],
            "blocker_count": 0,
            "warning_count": 0,
            "info_count": 0,
        }

        with (
            patch.object(update_engine, "_refresh_openrouter_model_metadata"),
            patch.object(update_engine, "_refresh_model_card_metadata"),
            patch.object(update_engine, "_refresh_model_license_metadata"),
            patch.object(update_engine.pricing, "sync_pricing", return_value={"providers": {}}),
            patch.object(
                update_engine,
                "_refresh_openrouter_market_signals",
                side_effect=update_engine.OptionalSourceUnavailable(
                    "OpenRouter rankings page did not expose rankingData."
                ),
            ),
            patch.object(update_engine, "run_audit", return_value=audit_result),
        ):
            log = update_engine.run_update_now(benchmarks=["does-not-exist"], triggered_by="cli")

        self.assertEqual(log["status"], "completed")
        self.assertEqual(log["scores_added"], 0)
        self.assertEqual(log["scores_updated"], 0)
        self.assertEqual(len(log["errors"]), 1)
        warning = log["errors"][0]
        self.assertEqual(warning["source_id"], "openrouter_market")
        self.assertEqual(warning["severity"], "warning")
        self.assertTrue(warning["nonfatal"])
        self.assertIn("rankingData", warning["error_message"])

    def test_list_models_exposes_stale_source_freshness_after_failed_run(self) -> None:
        self.add_model("acme-model", "Acme Model", provider="Acme")
        self.add_score("acme-model", "chatbot_arena", 1234.0, collected_at="2026-04-08T00:00:00Z")
        self.add_source_run(
            "chatbot_arena",
            "chatbot_arena",
            status="completed",
            started_at="2026-04-08T00:00:00Z",
            completed_at="2026-04-08T00:01:00Z",
            records_found=1,
        )
        self.add_source_run(
            "chatbot_arena",
            "chatbot_arena",
            status="failed",
            started_at="2026-04-09T00:00:00Z",
            completed_at="2026-04-09T00:01:00Z",
            records_found=0,
            error_message="upstream changed shape",
        )

        models = update_engine.list_models()
        model = next(model for model in models if model["id"] == "acme-model")
        source = next(entry for entry in model["source_freshness"] if entry["source_name"] == "chatbot_arena")

        self.assertEqual(source["source_label"], "Chatbot Arena")
        self.assertEqual(source["latest_source_status"], "failed")
        self.assertEqual(source["latest_success_at"], "2026-04-08T00:01:00Z")
        self.assertEqual(source["latest_failure_at"], "2026-04-09T00:01:00Z")
        self.assertEqual(source["latest_error"], "upstream changed shape")
        self.assertEqual(source["latest_model_score_at"], "2026-04-08T00:00:00Z")
        self.assertEqual(source["model_evidence_status"], "stale")
        self.assertTrue(source["has_model_score"])
        self.assertTrue(source["degraded"])
        self.assertTrue(source["stale"])
        self.assertFalse(source["missing_because_source_failed"])

    def test_list_models_marks_missing_score_when_latest_source_failed(self) -> None:
        self.add_model("acme-model", "Acme Model", provider="Acme")
        self.add_source_run(
            "ifeval",
            "ifeval",
            status="failed",
            started_at="2026-04-09T00:00:00Z",
            completed_at="2026-04-09T00:01:00Z",
            records_found=0,
            error_message="rate limited",
        )

        models = update_engine.list_models()
        model = next(model for model in models if model["id"] == "acme-model")
        source = next(entry for entry in model["source_freshness"] if entry["source_name"] == "ifeval")

        self.assertEqual(source["latest_source_status"], "failed")
        self.assertEqual(source["model_evidence_status"], "missing_source_failed")
        self.assertFalse(source["has_model_score"])
        self.assertTrue(source["degraded"])
        self.assertFalse(source["stale"])
        self.assertTrue(source["missing_because_source_failed"])

    def test_refresh_openrouter_model_metadata_persists_created_timestamp_and_alias_match(self) -> None:
        self.add_model("nova-pro", "Nova Pro", provider="Amazon")

        openrouter_items = [
            {
                "id": "amazon/nova-pro-v1",
                "canonical_slug": "amazon/nova-pro-v1",
                "name": "Amazon: Nova Pro 1.0",
                "hugging_face_id": "amazon/nova-pro-hf",
                "created": 1775592472,
                "architecture": {
                    "modality": "text+image->text",
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                },
                "supported_parameters": ["tools", "response_format"],
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
        self.assertEqual(nova["huggingface_repo_id"], "amazon/nova-pro-hf")
        self.assertEqual(nova["context_window_tokens"], 300000)
        self.assertEqual(nova["max_output_tokens"], 8192)
        self.assertIn("text+image->text", nova["capabilities"])
        self.assertIn("image-input", nova["capabilities"])
        self.assertIn("tool-use", nova["capabilities"])
        self.assertIn("structured-output", nova["capabilities"])

    def test_refresh_openrouter_model_metadata_tags_transcription_models(self) -> None:
        self.add_model("gpt-4o-transcribe", "GPT-4o Transcribe", provider="OpenAI")

        openrouter_items = [
            {
                "id": "openai/gpt-4o-transcribe",
                "canonical_slug": "openai/gpt-4o-transcribe",
                "name": "OpenAI: GPT-4o Transcribe",
                "created": 1775592472,
                "architecture": {
                    "modality": "audio->transcription",
                    "input_modalities": ["audio"],
                    "output_modalities": ["transcription"],
                },
                "supported_parameters": [],
                "top_provider": {},
                "pricing": {},
            }
        ]

        with patch.object(update_engine, "_fetch_openrouter_models", return_value=openrouter_items):
            update_engine._refresh_openrouter_model_metadata()

        models = update_engine.list_models()
        model = next(model for model in models if model["id"] == "gpt-4o-transcribe")
        self.assertEqual(model["model_roles"], ["speech_to_text"])
        self.assertIn("audio-input", model["capabilities"])
        self.assertIn("transcription-output", model["capabilities"])

    def test_refresh_openrouter_model_metadata_tags_text_to_speech_models(self) -> None:
        self.add_model("gemini-3-1-flash-tts", "Gemini 3.1 Flash TTS", provider="Google")

        openrouter_items = [
            {
                "id": "google/gemini-3-1-flash-tts",
                "canonical_slug": "google/gemini-3-1-flash-tts",
                "name": "Google: Gemini 3.1 Flash TTS",
                "created": 1780800472,
                "architecture": {
                    "modality": "text->speech",
                    "input_modalities": ["text"],
                    "output_modalities": ["speech"],
                },
                "supported_parameters": [],
                "top_provider": {},
                "pricing": {},
            }
        ]

        with patch.object(update_engine, "_fetch_openrouter_models", return_value=openrouter_items):
            update_engine._refresh_openrouter_model_metadata()

        models = update_engine.list_models()
        model = next(model for model in models if model["id"] == "gemini-3-1-flash-tts")
        self.assertEqual(model["model_roles"], ["text_to_speech"])
        self.assertNotIn("speech_to_text", model["model_roles"])
        self.assertIn("text->speech", model["capabilities"])
        self.assertIn("speech-output", model["capabilities"])

    def test_persist_source_result_promotes_missing_chatbot_arena_metadata(self) -> None:
        self.add_model("acme-model", "Acme Model", provider="Unknown")
        source_run_id = self.add_source_run("chatbot_arena", "chatbot_arena")
        result = SourceFetchResult(
            source_id="chatbot_arena",
            source_url="https://arena.ai/leaderboard/text",
            fetched_at="2026-04-08T00:00:00Z",
            raw_records=[],
            candidates=[
                ScoreCandidate(
                    source_id="chatbot_arena",
                    benchmark_id="chatbot_arena",
                    raw_model_name="Acme Model",
                    raw_model_key="Acme Model",
                    value=1234.0,
                    raw_value="1234",
                    source_url="https://arena.ai/leaderboard/text",
                    collected_at="2026-04-08T00:00:00Z",
                    source_type="primary",
                    verified=True,
                    metadata={
                        "organization": "Acme AI",
                        "license": "Apache 2.0",
                        "input_price_per_million": "0.25",
                        "output_price_per_million": "1.25",
                        "context_length": "128K",
                        "model_url": "https://example.com/acme-model",
                    },
                )
            ],
        )

        added, updated = update_engine._persist_source_result(source_run_id, result)

        self.assertEqual((added, updated), (1, 0))
        with self.engine.connect() as conn:
            row = conn.execute(
                select(models_table).where(models_table.c.id == "acme-model")
            ).mappings().one()

        self.assertEqual(row["provider"], "Acme AI")
        self.assertEqual(row["provider_id"], update_engine.provider_id_from_name("Acme AI"))
        self.assertEqual(row["license_name"], "Apache 2.0")
        self.assertEqual(row["context_window"], "128K tokens")
        self.assertEqual(row["context_window_tokens"], 128000)
        self.assertEqual(row["price_input_per_mtok"], 0.25)
        self.assertEqual(row["price_output_per_mtok"], 1.25)
        self.assertEqual(row["documentation_url"], "https://example.com/acme-model")
        self.assertEqual(row["metadata_source_name"], "Chatbot Arena")
        self.assertEqual(row["metadata_source_url"], "https://arena.ai/leaderboard/text")
        self.assertEqual(row["metadata_verified_at"], "2026-04-08T00:00:00Z")

    def test_same_date_new_source_revision_replaces_lower_corrected_score(self) -> None:
        self.add_model("acme-model", "Acme Model")
        collected_at = "2026-07-10T00:00:00Z"

        def candidate(revision: str, value: float) -> ScoreCandidate:
            return ScoreCandidate(
                source_id="chatbot_arena",
                benchmark_id="chatbot_arena",
                raw_model_name="Acme Model",
                raw_model_key="Acme Model",
                value=value,
                raw_value=str(value),
                source_url=f"https://huggingface.co/revision/{revision}",
                collected_at=collected_at,
                source_type="primary",
                verified=True,
                publication_date="2026-07-10",
                source_listing_status="listed",
                source_metadata={"dataset_revision": revision},
            )

        _, first_outcome = update_engine._persist_score_candidate(
            candidate("a" * 40, 1400.0), resolved_model_id="acme-model"
        )
        _, corrected_outcome = update_engine._persist_score_candidate(
            candidate("b" * 40, 1390.0), resolved_model_id="acme-model"
        )
        _, same_revision_lower_outcome = update_engine._persist_score_candidate(
            candidate("b" * 40, 1380.0), resolved_model_id="acme-model"
        )

        with self.engine.connect() as conn:
            rows = conn.execute(
                select(scores_table)
                .where(scores_table.c.model_id == "acme-model")
                .where(scores_table.c.benchmark_id == "chatbot_arena")
            ).mappings().all()
        self.assertEqual(first_outcome, "added")
        self.assertEqual(corrected_outcome, "updated")
        self.assertEqual(same_revision_lower_outcome, "skipped")
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["value"]), 1390.0)
        self.assertEqual(
            json.loads(str(rows[0]["source_metadata_json"]))["dataset_revision"],
            "b" * 40,
        )

    def test_persist_source_result_does_not_override_existing_higher_trust_metadata(self) -> None:
        self.add_model("acme-model", "Acme Model", provider="OpenAI")
        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "acme-model")
                .values(
                    provider_id=update_engine.provider_id_from_name("OpenAI"),
                    context_window="200K tokens",
                    context_window_tokens=200000,
                    price_input_per_mtok=2.0,
                    price_output_per_mtok=8.0,
                    license_name="Curated License",
                    documentation_url="https://docs.example.com/acme",
                    metadata_source_name="openrouter",
                    metadata_source_url="https://openrouter.ai/api/v1/models",
                    metadata_verified_at="2026-04-01T00:00:00Z",
                )
            )

        source_run_id = self.add_source_run("chatbot_arena", "chatbot_arena")
        result = SourceFetchResult(
            source_id="chatbot_arena",
            source_url="https://arena.ai/leaderboard/text",
            fetched_at="2026-04-08T00:00:00Z",
            raw_records=[],
            candidates=[
                ScoreCandidate(
                    source_id="chatbot_arena",
                    benchmark_id="chatbot_arena",
                    raw_model_name="Acme Model",
                    raw_model_key="Acme Model",
                    value=1234.0,
                    raw_value="1234",
                    source_url="https://arena.ai/leaderboard/text",
                    collected_at="2026-04-08T00:00:00Z",
                    source_type="primary",
                    verified=True,
                    metadata={
                        "organization": "Acme AI",
                        "license": "Apache 2.0",
                        "input_price_per_million": "0.25",
                        "output_price_per_million": "1.25",
                        "context_length": "128K",
                        "model_url": "https://example.com/acme-model",
                    },
                )
            ],
        )

        update_engine._persist_source_result(source_run_id, result)

        with self.engine.connect() as conn:
            row = conn.execute(
                select(models_table).where(models_table.c.id == "acme-model")
            ).mappings().one()

        self.assertEqual(row["provider"], "OpenAI")
        self.assertEqual(row["provider_id"], update_engine.provider_id_from_name("OpenAI"))
        self.assertEqual(row["license_name"], "Curated License")
        self.assertEqual(row["context_window"], "200K tokens")
        self.assertEqual(row["context_window_tokens"], 200000)
        self.assertEqual(row["price_input_per_mtok"], 2.0)
        self.assertEqual(row["price_output_per_mtok"], 8.0)
        self.assertEqual(row["documentation_url"], "https://docs.example.com/acme")
        self.assertEqual(row["metadata_source_name"], "openrouter")
        self.assertEqual(row["metadata_source_url"], "https://openrouter.ai/api/v1/models")
        self.assertEqual(row["metadata_verified_at"], "2026-04-01T00:00:00Z")

    def test_persist_source_result_promotes_verified_ifeval_metadata(self) -> None:
        self.add_model("verified-model", "Verified Model", provider="Unknown")
        source_run_id = self.add_source_run("ifeval", "ifeval")
        result = SourceFetchResult(
            source_id="ifeval",
            source_url="https://llm-stats.com/benchmarks/ifeval",
            fetched_at="2026-04-08T00:00:00Z",
            raw_records=[],
            candidates=[
                ScoreCandidate(
                    source_id="ifeval",
                    benchmark_id="ifeval",
                    raw_model_name="Verified Model",
                    raw_model_key="verified/model",
                    value=82.0,
                    raw_value="82",
                    source_url="https://llm-stats.com/benchmarks/ifeval",
                    collected_at="2026-04-08T00:00:00Z",
                    source_type="primary",
                    verified=True,
                    metadata={
                        "details_url": "https://api.llm-stats.com/leaderboard/benchmarks/ifeval/details",
                        "organization_name": "Verified Org",
                        "verified": True,
                        "self_reported": False,
                        "input_cost_per_million": "0.3",
                        "output_cost_per_million": "0.9",
                        "context_window": 32768,
                    },
                )
            ],
        )

        update_engine._persist_source_result(source_run_id, result)

        with self.engine.connect() as conn:
            row = conn.execute(
                select(models_table).where(models_table.c.id == "verified-model")
            ).mappings().one()

        self.assertEqual(row["provider"], "Verified Org")
        self.assertEqual(row["context_window"], "32.8K tokens")
        self.assertEqual(row["context_window_tokens"], 32768)
        self.assertEqual(row["price_input_per_mtok"], 0.3)
        self.assertEqual(row["price_output_per_mtok"], 0.9)
        self.assertEqual(row["metadata_source_name"], "IFEval")
        self.assertEqual(
            row["metadata_source_url"],
            "https://api.llm-stats.com/leaderboard/benchmarks/ifeval/details",
        )

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

    def test_refresh_openrouter_model_metadata_imports_unrepresented_exact_release_as_provisional(self) -> None:
        identity = update_engine.infer_model_identity("Nova Premier", "Amazon", "amazon/nova-premier-v1")
        self.add_model(
            "nova-premier-preview",
            "Nova Premier Preview",
            provider="Amazon",
            canonical_model_id=identity.canonical_model_id,
            canonical_model_name=identity.canonical_model_name,
        )

        openrouter_items = [
            {
                "id": "amazon/nova-premier-v1",
                "canonical_slug": "amazon/nova-premier-v1",
                "name": "Amazon: Nova Premier",
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
        existing = next(model for model in models if model["id"] == "nova-premier-preview")

        self.assertNotEqual(imported["id"], existing["id"])
        self.assertEqual(imported["catalog_status"], "provisional")
        self.assertEqual(imported["name"], "Nova Premier")
        self.assertIsNone(existing["openrouter_model_id"])

    def test_refresh_openrouter_model_metadata_imports_non_best_exact_variant_as_provisional(self) -> None:
        self.add_model("nova-pro", "Nova Pro", provider="Amazon")

        openrouter_items = [
            {
                "id": "amazon/nova-pro-v1",
                "canonical_slug": "amazon/nova-pro-v1",
                "name": "Amazon: Nova Pro",
                "created": 1761950332,
                "top_provider": {
                    "context_length": 1000000,
                    "max_completion_tokens": 32768,
                },
                "pricing": {
                    "prompt": "0.000004",
                    "completion": "0.000016",
                },
            },
            {
                "id": "amazon/nova-pro-v2",
                "canonical_slug": "amazon/nova-pro-v2",
                "name": "Amazon: Nova Pro",
                "created": 1775592472,
                "top_provider": {
                    "context_length": 2000000,
                    "max_completion_tokens": 32768,
                },
                "pricing": {
                    "prompt": "0.000004",
                    "completion": "0.000016",
                },
            },
        ]

        with patch.object(update_engine, "_fetch_openrouter_models", return_value=openrouter_items):
            update_engine._refresh_openrouter_model_metadata()

        models = update_engine.list_models()
        existing = next(model for model in models if model["id"] == "nova-pro")
        imported = next(model for model in models if model["openrouter_model_id"] == "amazon/nova-pro-v1")

        self.assertEqual(existing["openrouter_model_id"], "amazon/nova-pro-v2")
        self.assertNotEqual(imported["id"], existing["id"])
        self.assertEqual(imported["catalog_status"], "provisional")

    def test_refresh_openrouter_model_metadata_prefers_final_entry_over_preview(self) -> None:
        self.add_model("gemini-3-pro-image", "Gemini 3 Pro Image", provider="Google")
        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "gemini-3-pro-image")
                .values(
                    openrouter_model_id="google/gemini-3-pro-image-preview",
                    openrouter_canonical_slug="google/gemini-3-pro-image-preview-20251120",
                )
            )

        openrouter_items = [
            {
                "id": "google/gemini-3-pro-image-preview",
                "canonical_slug": "google/gemini-3-pro-image-preview-20251120",
                "name": "Google: Nano Banana Pro (Gemini 3 Pro Image Preview)",
                "created": 1763653797,
                "top_provider": {
                    "context_length": 1000000,
                    "max_completion_tokens": 32768,
                },
                "pricing": {
                    "prompt": "0.000004",
                    "completion": "0.000016",
                },
            },
            {
                "id": "google/gemini-3-pro-image",
                "canonical_slug": "google/gemini-3-pro-image-20260528",
                "name": "Google: Nano Banana Pro (Gemini 3 Pro Image)",
                "created": 1781754054,
                "top_provider": {
                    "context_length": 1000000,
                    "max_completion_tokens": 32768,
                },
                "pricing": {
                    "prompt": "0.000004",
                    "completion": "0.000016",
                },
            },
        ]

        with patch.object(update_engine, "_fetch_openrouter_models", return_value=openrouter_items):
            update_engine._refresh_openrouter_model_metadata()

        models = update_engine.list_models()
        existing = next(model for model in models if model["id"] == "gemini-3-pro-image")

        self.assertEqual(existing["openrouter_model_id"], "google/gemini-3-pro-image")

    def test_build_huggingface_model_card_values_extracts_metadata(self) -> None:
        info = {
            "cardData": {
                "license": "apache-2.0",
                "license_name": "Apache 2.0",
                "license_link": "https://example.com/license",
                "language": ["en", "de"],
                "pipeline_tag": "text-generation",
                "base_model": "acme/Base-1",
            },
            "tags": ["chat", "arxiv:2401.12345"],
        }
        readme = """---
license: apache-2.0
---

<a href="https://docs.acme.test/model">Documentation</a>
<a href="https://github.com/acme/model">GitHub</a>

Acme Model is built for coding and reasoning workloads in enterprise settings.

## Intended Use
Use this model for coding assistants and long-form analysis inside governed environments.

## Limitations
This model can still hallucinate and should be reviewed before use in regulated workflows.

## Training Data
Mixed public and licensed corpora with synthetic post-training examples.

## Knowledge Cutoff
January 2026
"""

        values = update_engine._build_huggingface_model_card_values(
            info,
            readme,
            repo_id="acme/model",
            verified_at="2026-04-09T00:00:00Z",
        )

        self.assertEqual(values["model_card_url"], "https://huggingface.co/acme/model")
        self.assertEqual(values["documentation_url"], "https://docs.acme.test/model")
        self.assertEqual(values["repo_url"], "https://github.com/acme/model")
        self.assertEqual(values["paper_url"], "https://arxiv.org/abs/2401.12345")
        self.assertEqual(values["license_id"], "apache-2.0")
        self.assertEqual(values["license_name"], "Apache 2.0")
        self.assertEqual(values["license_url"], "https://example.com/license")
        self.assertEqual(json.loads(values["base_models_json"]), ["acme/Base-1"])
        self.assertEqual(json.loads(values["supported_languages_json"]), ["en", "de"])
        self.assertIn("text-generation", json.loads(values["capabilities_json"]))
        self.assertIn("chat", json.loads(values["capabilities_json"]))
        self.assertIn("coding assistants", values["intended_use_short"])
        self.assertIn("hallucinate", values["limitations_short"])
        self.assertIn("licensed corpora", values["training_data_summary"])
        self.assertEqual(values["training_cutoff"], "January 2026")

    def test_fetch_huggingface_model_card_values_keeps_structured_metadata_when_readme_fails(self) -> None:
        info = {
            "cardData": {
                "license": "apache-2.0",
                "pipeline_tag": "text-generation",
            },
            "siblings": [{"rfilename": "README.md"}],
            "tags": [],
        }
        request = httpx.Request("GET", "https://huggingface.co/acme/model/raw/main/README.md")
        response = httpx.Response(401, request=request)
        readme_error = httpx.HTTPStatusError("unauthorized", request=request, response=response)

        with httpx.Client() as client:
            with patch.object(update_engine, "_fetch_huggingface_model_info", return_value=info), patch.object(
                update_engine,
                "_fetch_huggingface_readme",
                side_effect=readme_error,
            ):
                values = update_engine._fetch_huggingface_model_card_values(
                    client,
                    "acme/model",
                    verified_at="2026-04-09T00:00:00Z",
                )

        self.assertEqual(values["model_card_url"], "https://huggingface.co/acme/model")
        self.assertEqual(values["model_card_source"], "huggingface")
        self.assertEqual(values["license_id"], "apache-2.0")
        self.assertIn("text-generation", json.loads(values["capabilities_json"]))

    def test_refresh_model_card_metadata_populates_models_with_huggingface_repo(self) -> None:
        self.add_model("gemma-variant", "Gemma Variant", provider="Google")
        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "gemma-variant")
                .values(huggingface_repo_id="google/gemma-4-26B-A4B-it")
            )

        mocked_values = {
            "huggingface_repo_id": "google/gemma-4-26B-A4B-it",
            "model_card_url": "https://huggingface.co/google/gemma-4-26B-A4B-it",
            "model_card_source": "huggingface",
            "model_card_verified_at": "2026-04-09T00:00:00Z",
            "license_id": "apache-2.0",
            "license_name": "Apache 2.0",
            "documentation_url": "https://ai.google.dev/gemma/docs/core",
            "repo_url": "https://github.com/google-gemma",
            "capabilities_json": json.dumps(["image-text-to-text", "reasoning"], ensure_ascii=True),
        }

        with patch.object(update_engine, "_fetch_huggingface_model_card_values", return_value=mocked_values):
            update_engine._refresh_model_card_metadata(force=True)

        models = update_engine.list_models()
        gemma = next(model for model in models if model["id"] == "gemma-variant")

        self.assertEqual(gemma["license_id"], "apache-2.0")
        self.assertEqual(gemma["license_name"], "Apache 2.0")
        self.assertEqual(gemma["documentation_url"], "https://ai.google.dev/gemma/docs/core")
        self.assertEqual(gemma["repo_url"], "https://github.com/google-gemma")
        self.assertEqual(gemma["model_card_source"], "huggingface")
        self.assertIn("image-text-to-text", gemma["capabilities"])

    def test_refresh_model_card_metadata_commits_repo_updates_incrementally(self) -> None:
        self.add_model("card-first", "Card First", provider="Acme")
        self.add_model("card-second", "Card Second", provider="Acme")
        mocked_rows = [
            {
                "id": "card-first",
                "huggingface_repo_id": "acme/first",
                "model_card_verified_at": None,
                "model_card_url": None,
                "license_id": None,
                "license_name": None,
                "capabilities_json": "[]",
                "intended_use_short": None,
                "limitations_short": None,
                "training_data_summary": None,
                "training_cutoff": None,
            },
            {
                "id": "card-second",
                "huggingface_repo_id": "acme/second",
                "model_card_verified_at": None,
                "model_card_url": None,
                "license_id": None,
                "license_name": None,
                "capabilities_json": "[]",
                "intended_use_short": None,
                "limitations_short": None,
                "training_data_summary": None,
                "training_cutoff": None,
            },
        ]

        def fake_fetch_model_card(_client: httpx.Client, repo_id: str, *, verified_at: str) -> dict[str, str]:
            if repo_id == "acme/second":
                raise KeyboardInterrupt()
            return {
                "huggingface_repo_id": repo_id,
                "model_card_url": f"https://huggingface.co/{repo_id}",
                "model_card_source": "huggingface",
                "model_card_verified_at": verified_at,
                "license_id": "apache-2.0",
                "license_name": "Apache 2.0",
            }

        with patch.object(update_engine, "fetch_all", return_value=mocked_rows), patch.object(
            update_engine,
            "_fetch_huggingface_model_card_values",
            side_effect=fake_fetch_model_card,
        ):
            with self.assertRaises(KeyboardInterrupt):
                update_engine._refresh_model_card_metadata(force=True)

        models = update_engine.list_models()
        first = next(model for model in models if model["id"] == "card-first")
        second = next(model for model in models if model["id"] == "card-second")

        self.assertEqual(first["license_id"], "apache-2.0")
        self.assertEqual(first["model_card_url"], "https://huggingface.co/acme/first")
        self.assertIsNone(second["license_id"])

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

    def test_canonicalize_model_catalog_preserves_openrouter_exact_identity_rows(self) -> None:
        self.add_model(
            "gemini-3-1-flash-lite",
            "Gemini 3.1 Flash-Lite Preview",
            provider="Google",
        )
        self.add_model(
            "google-gemini-3-1-flash-lite-20260507",
            "Gemini 3.1 Flash Lite",
            provider="Google",
        )
        with self.engine.begin() as conn:
            conn.execute(
                update(models_table)
                .where(models_table.c.id == "google-gemini-3-1-flash-lite-20260507")
                .values(
                    catalog_status="provisional",
                    openrouter_model_id="google/gemini-3.1-flash-lite",
                    openrouter_canonical_slug="google/gemini-3.1-flash-lite-20260507",
                )
            )

        update_engine._canonicalize_model_catalog()

        with get_connection(self.engine) as conn:
            rows = fetch_all(
                conn,
                select(models_table.c.id, models_table.c.active).where(
                    models_table.c.id.in_(
                        [
                            "gemini-3-1-flash-lite",
                            "google-gemini-3-1-flash-lite-20260507",
                        ]
                    )
                ),
            )

        self.assertEqual({row["id"] for row in rows}, {"gemini-3-1-flash-lite", "google-gemini-3-1-flash-lite-20260507"})
        self.assertTrue(all(row["active"] == 1 for row in rows))

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

    def test_get_update_log_includes_change_summary(self) -> None:
        self.add_update_log(
            904,
            change_summary={
                "generated_at": "2026-04-08T00:05:00Z",
                "model_count_before": 1,
                "model_count_after": 2,
                "model_count_delta": 1,
                "new_model_count": 1,
                "changed_model_count": 1,
                "removed_model_count": 0,
                "unchanged_model_count": 0,
                "source_record_count": 12,
                "source_failure_count": 0,
                "new_models": [
                    {
                        "id": "new-model",
                        "name": "New Model",
                        "provider": "Provider",
                        "catalog_status": "provisional",
                        "model_roles": ["generator"],
                    }
                ],
                "changed_models": [
                    {
                        "id": "existing-model",
                        "name": "Existing Model",
                        "provider": "Provider",
                        "catalog_status": "tracked",
                        "model_roles": ["generator"],
                        "changed_fields": ["Model card"],
                    }
                ],
                "removed_models": [],
                "truncated": {"new_models": 0, "changed_models": 0, "removed_models": 0},
            },
        )

        log = update_engine.get_update_log(904)

        self.assertIsNotNone(log)
        assert log is not None
        self.assertEqual(log["change_summary"]["new_model_count"], 1)
        self.assertEqual(log["change_summary"]["changed_model_count"], 1)
        self.assertEqual(log["change_summary"]["new_models"][0]["id"], "new-model")
        self.assertEqual(log["change_summary"]["changed_models"][0]["changed_fields"], ["Model card"])

    def test_update_change_summary_detects_new_and_changed_models(self) -> None:
        self.add_update_log(905)
        with self.engine.begin() as conn:
            conn.execute(
                source_runs_table.insert(),
                [
                    {
                        "update_log_id": 905,
                        "source_name": "catalog_model_discovery",
                        "benchmark_id": "model_discovery",
                        "started_at": "2026-04-08T00:00:10Z",
                        "completed_at": "2026-04-08T00:00:20Z",
                        "status": "completed",
                        "records_found": 7,
                    },
                    {
                        "update_log_id": 905,
                        "source_name": "model_card_metadata",
                        "benchmark_id": None,
                        "started_at": "2026-04-08T00:00:30Z",
                        "completed_at": "2026-04-08T00:00:40Z",
                        "status": "failed",
                        "records_found": 0,
                    },
                ],
            )
        before = {
            "existing-model": {
                "id": "existing-model",
                "name": "Existing Model",
                "provider": "Provider",
                "catalog_status": "tracked",
                "model_roles": ["generator"],
                "release_date": None,
            }
        }
        after = {
            "existing-model": {
                **before["existing-model"],
                "release_date": "2026-04-08",
                "metadata_source_name": "model_card",
            },
            "new-model": {
                "id": "new-model",
                "name": "New Model",
                "provider": "Provider",
                "catalog_status": "provisional",
                "model_roles": ["generator"],
            },
        }

        summary = update_engine._build_update_change_summary(before, after, log_id=905)

        self.assertEqual(summary["new_model_count"], 1)
        self.assertEqual(summary["changed_model_count"], 1)
        self.assertEqual(summary["source_record_count"], 7)
        self.assertEqual(summary["source_failure_count"], 1)
        self.assertEqual(summary["new_models"][0]["id"], "new-model")
        self.assertIn("Release date", summary["changed_models"][0]["changed_fields"])

    def test_schedule_update_reuses_existing_running_log(self) -> None:
        self.add_update_log(902, status="running", completed_at=None)

        with patch.object(update_engine.threading, "Thread") as thread_cls:
            log_id = update_engine.schedule_update(benchmarks=["terminal_bench"], triggered_by="api")

        self.assertEqual(log_id, 902)
        thread_cls.assert_not_called()

    def test_schedule_update_creates_single_active_log_for_duplicate_requests(self) -> None:
        with patch.object(update_engine.threading, "Thread") as thread_cls:
            first_log_id = update_engine.schedule_update(benchmarks=["does-not-exist"], triggered_by="api")
            second_log_id = update_engine.schedule_update(benchmarks=["does-not-exist"], triggered_by="api")

        self.assertEqual(first_log_id, second_log_id)
        self.assertEqual(thread_cls.call_count, 1)
        thread_cls.return_value.start.assert_called_once()
        log = update_engine.get_update_log(first_log_id)
        self.assertIsNotNone(log)
        assert log is not None
        self.assertEqual(log["status"], "running")

    def test_recover_interrupted_updates_marks_running_logs_failed(self) -> None:
        self.add_update_log(903, status="running", completed_at=None)

        update_engine._recover_interrupted_updates()

        log = update_engine.get_update_log(903)
        self.assertIsNotNone(log)
        assert log is not None
        self.assertEqual(log["status"], "failed")
        self.assertIsNotNone(log["completed_at"])
        self.assertEqual(len(log["errors"]), 1)
        self.assertEqual(log["errors"][0]["source_id"], "update")
        self.assertIn("interrupted", log["errors"][0]["error_message"].lower())

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
