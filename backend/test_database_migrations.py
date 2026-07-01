from __future__ import annotations

import unittest

from sqlalchemy.engine import Connection

from backend.database import SCHEMA_MIGRATIONS, get_engine, init_db


class DatabaseMigrationTests(unittest.TestCase):
    def test_fresh_bootstrap_records_schema_migrations(self) -> None:
        engine = init_db(get_engine("sqlite:///:memory:"))

        with engine.begin() as conn:
            migration_ids = _migration_ids(conn)
            model_columns = _columns(conn, "models")
            latest_scores_view = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'view' AND name = 'latest_scores'"
            ).fetchone()

        self.assertEqual(migration_ids, [migration_id for migration_id, _migration in SCHEMA_MIGRATIONS])
        self.assertIn("provider_id", model_columns)
        self.assertIn("model_roles_json", model_columns)
        self.assertIn("openrouter_global_rank", model_columns)
        self.assertIsNotNone(latest_scores_view)

    def test_legacy_schema_upgrade_adds_missing_columns_once(self) -> None:
        engine = get_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            _create_legacy_schema(conn)

        init_db(engine)
        init_db(engine)

        with engine.begin() as conn:
            migration_ids = _migration_ids(conn)
            provider_columns = _columns(conn, "providers")
            model_columns = _columns(conn, "models")
            raw_record_columns = _columns(conn, "raw_source_records")
            approval_columns = _columns(conn, "model_use_case_approvals")
            inference_approval_columns = _columns(conn, "model_use_case_inference_approvals")
            update_log_columns = _columns(conn, "update_log")

        self.assertEqual(migration_ids, [migration_id for migration_id, _migration in SCHEMA_MIGRATIONS])
        self.assertIn("origin_countries_json", provider_columns)
        self.assertIn("provider_id", model_columns)
        self.assertIn("model_roles_json", model_columns)
        self.assertIn("catalog_status", model_columns)
        self.assertIn("base_models_json", model_columns)
        self.assertIn("openrouter_programming_request_count", model_columns)
        self.assertIn("resolution_status", raw_record_columns)
        self.assertIn("recommendation_status", approval_columns)
        self.assertIn("location_label", inference_approval_columns)
        self.assertIn("approval_updated_at", inference_approval_columns)
        self.assertIn("current_step_key", update_log_columns)
        self.assertIn("steps_json", update_log_columns)


def _columns(conn: Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()}


def _migration_ids(conn: Connection) -> list[str]:
    rows = conn.exec_driver_sql("SELECT id FROM schema_migrations ORDER BY id").fetchall()
    return [str(row[0]) for row in rows]


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
