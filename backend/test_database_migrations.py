from __future__ import annotations

import json
import unittest

from sqlalchemy.engine import Connection

from backend import database
from backend.database import (
    SCHEMA_MIGRATIONS,
    benchmarks as benchmarks_table,
    get_engine,
    init_db,
    model_source_listings as model_source_listings_table,
    models as models_table,
    raw_source_records as raw_source_records_table,
    scores as scores_table,
    source_runs as source_runs_table,
)


class DatabaseMigrationTests(unittest.TestCase):
    def test_fresh_bootstrap_records_schema_migrations(self) -> None:
        engine = init_db(get_engine("sqlite:///:memory:"))

        with engine.begin() as conn:
            migration_ids = _migration_ids(conn)
            table_names = _tables(conn)
            model_columns = _columns(conn, "models")
            update_log_columns = _columns(conn, "update_log")
            latest_scores_view = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'view' AND name = 'latest_scores'"
            ).fetchone()

        self.assertEqual(migration_ids, [migration_id for migration_id, _migration in SCHEMA_MIGRATIONS])
        self.assertIn("model_use_case_recommendation_proposals", table_names)
        self.assertIn("provider_id", model_columns)
        self.assertIn("model_roles_json", model_columns)
        self.assertIn("openrouter_global_rank", model_columns)
        self.assertIn("parameter_count_b", model_columns)
        self.assertIn("active_parameter_count_b", model_columns)
        self.assertIn("model_size_class", model_columns)
        self.assertIn("small_model_candidate", model_columns)
        self.assertIn("model_size_source_name", model_columns)
        self.assertIn("model_size_source_url", model_columns)
        self.assertIn("model_size_verified_at", model_columns)
        self.assertIn("general_approved_for_use", model_columns)
        self.assertIn("general_approval_notes", model_columns)
        self.assertIn("general_approval_updated_at", model_columns)
        self.assertIn("general_recommendation_status", model_columns)
        self.assertIn("general_recommendation_notes", model_columns)
        self.assertIn("general_recommendation_updated_at", model_columns)
        self.assertIn("reasoning_effort_ceiling", model_columns)
        self.assertIn("restricted_modes_json", model_columns)
        self.assertIn("change_summary_json", update_log_columns)
        self.assertIsNotNone(latest_scores_view)

    def test_legacy_schema_upgrade_adds_missing_columns_once(self) -> None:
        engine = get_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            _create_legacy_schema(conn)

        init_db(engine)
        init_db(engine)

        with engine.begin() as conn:
            migration_ids = _migration_ids(conn)
            table_names = _tables(conn)
            provider_columns = _columns(conn, "providers")
            model_columns = _columns(conn, "models")
            raw_record_columns = _columns(conn, "raw_source_records")
            approval_columns = _columns(conn, "model_use_case_approvals")
            inference_approval_columns = _columns(conn, "model_use_case_inference_approvals")
            update_log_columns = _columns(conn, "update_log")
            score_columns = _columns(conn, "scores")

        self.assertEqual(migration_ids, [migration_id for migration_id, _migration in SCHEMA_MIGRATIONS])
        self.assertIn("origin_countries_json", provider_columns)
        self.assertIn("provider_id", model_columns)
        self.assertIn("model_roles_json", model_columns)
        self.assertIn("catalog_status", model_columns)
        self.assertIn("base_models_json", model_columns)
        self.assertIn("openrouter_programming_request_count", model_columns)
        self.assertIn("parameter_count_b", model_columns)
        self.assertIn("active_parameter_count_b", model_columns)
        self.assertIn("model_size_class", model_columns)
        self.assertIn("small_model_candidate", model_columns)
        self.assertIn("model_size_source_name", model_columns)
        self.assertIn("model_size_source_url", model_columns)
        self.assertIn("model_size_verified_at", model_columns)
        self.assertIn("general_approved_for_use", model_columns)
        self.assertIn("general_approval_notes", model_columns)
        self.assertIn("general_approval_updated_at", model_columns)
        self.assertIn("general_recommendation_status", model_columns)
        self.assertIn("general_recommendation_notes", model_columns)
        self.assertIn("general_recommendation_updated_at", model_columns)
        self.assertIn("reasoning_effort_ceiling", model_columns)
        self.assertIn("restricted_modes_json", model_columns)
        self.assertIn("resolution_status", raw_record_columns)
        self.assertIn("recommendation_status", approval_columns)
        self.assertIn("model_use_case_recommendation_proposals", table_names)
        self.assertIn("location_label", inference_approval_columns)
        self.assertIn("approval_updated_at", inference_approval_columns)
        self.assertIn("current_step_key", update_log_columns)
        self.assertIn("steps_json", update_log_columns)
        self.assertIn("change_summary_json", update_log_columns)
        self.assertIn("model_source_listings", table_names)
        self.assertTrue(
            {
                "confidence_lower",
                "confidence_upper",
                "variance",
                "vote_count",
                "observation_count",
                "session_count",
                "rank",
                "category",
                "publication_date",
                "methodology",
                "source_listing_status",
                "style_control",
                "preliminary",
                "source_metadata_json",
                "configuration_key",
                "configuration_value",
            }.issubset(score_columns)
        )
        self.assertIn("20260708_001_update_change_summary", migration_ids)
        self.assertIn("20260713_001_score_evidence", migration_ids)
        self.assertIn("20260714_001_general_model_recommendations", migration_ids)

    def test_speech_to_text_role_migration_backfills_transcription_capabilities(self) -> None:
        engine = init_db(get_engine("sqlite:///:memory:"))
        with engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                {
                    "id": "gpt-4o-transcribe",
                    "name": "GPT-4o Transcribe",
                    "provider": "OpenAI",
                    "type": "proprietary",
                    "model_roles_json": json.dumps(["generator"], ensure_ascii=True),
                    "capabilities_json": json.dumps(["audio-input", "transcription-output"], ensure_ascii=True),
                    "active": 1,
                },
            )
            database._migration_20260703_speech_to_text_roles(conn)
            row = conn.execute(
                models_table.select().where(models_table.c.id == "gpt-4o-transcribe"),
            ).mappings().one()

        self.assertEqual(json.loads(str(row["model_roles_json"])), ["speech_to_text"])

    def test_text_to_speech_role_migration_backfills_speech_output_capabilities(self) -> None:
        engine = init_db(get_engine("sqlite:///:memory:"))
        with engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                {
                    "id": "gemini-3-1-flash-tts",
                    "name": "Gemini 3.1 Flash TTS",
                    "provider": "Google",
                    "type": "proprietary",
                    "model_roles_json": json.dumps(["generator"], ensure_ascii=True),
                    "capabilities_json": json.dumps(["text->speech", "text-input", "speech-output"], ensure_ascii=True),
                    "active": 1,
                },
            )
            database._migration_20260703_text_to_speech_roles(conn)
            row = conn.execute(
                models_table.select().where(models_table.c.id == "gemini-3-1-flash-tts"),
            ).mappings().one()

        self.assertEqual(json.loads(str(row["model_roles_json"])), ["text_to_speech"])

    def test_general_recommendation_simplification_migrates_discouraged(self) -> None:
        engine = init_db(get_engine("sqlite:///:memory:"))
        with engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                {
                    "id": "discouraged-general-model",
                    "name": "Discouraged General Model",
                    "provider": "Test Provider",
                    "type": "proprietary",
                    "general_recommendation_status": "discouraged",
                    "active": 1,
                },
            )
            database._migration_20260714_general_recommendation_simplification(conn)
            row = conn.execute(
                models_table.select().where(models_table.c.id == "discouraged-general-model")
            ).mappings().one()

        self.assertEqual(row["general_recommendation_status"], "not_recommended")

    def test_gpt56_migration_is_idempotent_and_preserves_decisions_and_evidence(self) -> None:
        engine = init_db(get_engine("sqlite:///:memory:"))
        with engine.begin() as conn:
            conn.execute(benchmarks_table.insert(), {
                "id": "aa_intelligence", "name": "AA", "short": "AA", "source": "AA",
                "url": "https://example.test", "category": "reasoning", "metric": "score",
            })
            conn.execute(models_table.insert(), [
                {
                    "id": "gpt-5-6-sol-low", "name": "GPT-5.6 Sol (low)", "provider": "OpenAI",
                    "type": "proprietary", "general_approved_for_use": 1,
                    "general_recommendation_status": "recommended",
                    "general_recommendation_notes": "Base Sol is recommended.", "active": 1,
                },
                {
                    "id": "gpt-5-6-sol-pro", "name": "GPT-5.6 Sol Pro", "provider": "OpenAI",
                    "type": "proprietary", "general_approved_for_use": 1,
                    "general_recommendation_status": "restricted",
                    "general_recommendation_notes": "Pro mode is restricted.", "active": 1,
                },
                {
                    "id": "openai-gpt-5-6-sol-pro-20260709", "name": "GPT 5.6 Sol Pro", "provider": "OpenAI",
                    "type": "proprietary", "general_approved_for_use": 1,
                    "general_recommendation_status": "restricted",
                    "general_recommendation_notes": "Dated Pro alias is restricted.", "active": 1,
                },
            ])
            conn.execute(scores_table.insert(), {
                "model_id": "gpt-5-6-sol-low", "benchmark_id": "aa_intelligence", "value": 58.8,
                "raw_value": "58.8", "collected_at": "2026-07-14T00:00:00Z",
            })
            source_run_id = conn.execute(source_runs_table.insert(), {
                "source_name": "artificial_analysis", "started_at": "2026-07-14T00:00:00Z",
                "status": "completed",
            }).inserted_primary_key[0]
            conn.execute(raw_source_records_table.insert(), {
                "source_run_id": source_run_id, "benchmark_id": "aa_intelligence",
                "raw_model_name": "GPT-5.6 Sol (max)", "normalized_model_id": "gpt-5-6-sol-low",
                "raw_value": "58.8", "payload_json": "{}", "source_type": "primary",
                "verified": 1, "collected_at": "2026-07-14T00:00:00Z",
            })
            conn.execute(model_source_listings_table.insert(), {
                "source_name": "artificial_analysis", "benchmark_id": "aa_intelligence",
                "raw_model_name": "GPT-5.6 Sol (max)", "raw_model_key": "sol-max",
                "model_id": "gpt-5-6-sol-low", "listing_status": "listed",
                "first_seen_at": "2026-07-14T00:00:00Z", "last_seen_at": "2026-07-14T00:00:00Z",
            })
            database._migration_20260714_gpt56_configuration_policy(conn)
            database._migration_20260714_gpt56_configuration_policy(conn)
            base = conn.execute(models_table.select().where(models_table.c.id == "gpt-5-6-sol")).mappings().one()
            score = conn.execute(scores_table.select()).mappings().one()
            raw = conn.execute(raw_source_records_table.select()).mappings().one()
            listing = conn.execute(model_source_listings_table.select()).mappings().one()
            legacy = conn.execute(models_table.select().where(models_table.c.id == "gpt-5-6-sol-low")).mappings().one()
            dated_legacy = conn.execute(
                models_table.select().where(models_table.c.id == "openai-gpt-5-6-sol-pro-20260709")
            ).mappings().one()

        self.assertEqual(base["general_approved_for_use"], 1)
        self.assertEqual(base["general_recommendation_status"], "recommended")
        self.assertEqual(base["general_recommendation_notes"], "Base Sol is recommended.")
        self.assertEqual(json.loads(base["restricted_modes_json"]), ["pro"])
        self.assertEqual(score["model_id"], "gpt-5-6-sol")
        self.assertIsNone(score["configuration_value"])
        self.assertEqual(raw["normalized_model_id"], "gpt-5-6-sol")
        self.assertEqual(listing["model_id"], "gpt-5-6-sol")
        self.assertEqual((legacy["catalog_status"], legacy["active"]), ("deprecated", 0))
        self.assertEqual((dated_legacy["catalog_status"], dated_legacy["active"]), ("deprecated", 0))

    def test_speech_to_text_role_migration_does_not_backfill_tts_name_only_rows(self) -> None:
        engine = init_db(get_engine("sqlite:///:memory:"))
        with engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                {
                    "id": "voxtral-tts",
                    "name": "Voxtral TTS",
                    "provider": "Mistral AI",
                    "type": "open_weights",
                    "model_roles_json": json.dumps(["generator"], ensure_ascii=True),
                    "capabilities_json": json.dumps(["text-to-speech"], ensure_ascii=True),
                    "active": 1,
                },
            )
            database._migration_20260703_speech_to_text_roles(conn)
            row = conn.execute(
                models_table.select().where(models_table.c.id == "voxtral-tts"),
            ).mappings().one()

        self.assertEqual(json.loads(str(row["model_roles_json"])), ["generator"])


def _columns(conn: Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()}


def _migration_ids(conn: Connection) -> list[str]:
    rows = conn.exec_driver_sql("SELECT id FROM schema_migrations ORDER BY id").fetchall()
    return [str(row[0]) for row in rows]


def _tables(conn: Connection) -> set[str]:
    rows = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in rows}


def _create_legacy_schema(conn: Connection) -> None:
    conn.exec_driver_sql(
        """
        CREATE TABLE providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            country_code TEXT,
            country_name TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            provider TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'proprietary',
            release_date TEXT,
            context_window TEXT,
            approved_for_use INTEGER NOT NULL DEFAULT 0,
            approval_notes TEXT,
            approval_updated_at TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE raw_source_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_run_id INTEGER NOT NULL,
            benchmark_id TEXT,
            raw_model_name TEXT NOT NULL,
            normalized_model_id TEXT,
            raw_key TEXT,
            raw_value TEXT,
            payload_json TEXT NOT NULL,
            source_url TEXT,
            source_type TEXT NOT NULL DEFAULT 'primary',
            verified INTEGER NOT NULL DEFAULT 0,
            collected_at TEXT NOT NULL,
            notes TEXT
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE model_use_case_approvals (
            model_id TEXT NOT NULL,
            use_case_id TEXT NOT NULL,
            approved_for_use INTEGER NOT NULL DEFAULT 0,
            approval_notes TEXT,
            approval_updated_at TEXT,
            PRIMARY KEY (model_id, use_case_id)
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE model_use_case_inference_approvals (
            model_id TEXT NOT NULL,
            use_case_id TEXT NOT NULL,
            destination_id TEXT NOT NULL,
            location_key TEXT NOT NULL,
            PRIMARY KEY (model_id, use_case_id, destination_id, location_key)
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'running',
            scores_added INTEGER DEFAULT 0,
            scores_updated INTEGER DEFAULT 0,
            errors TEXT
        )
        """
    )


if __name__ == "__main__":
    unittest.main()
