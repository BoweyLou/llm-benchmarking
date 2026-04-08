"""SQLAlchemy Core schema and database helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import Column, Float, ForeignKey, Integer, MetaData, String, Table, Text, create_engine, event, text
from sqlalchemy.engine import Connection, Engine, RowMapping

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "db.sqlite"
DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

metadata = MetaData()

benchmarks = Table(
    "benchmarks",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("short", String, nullable=False),
    Column("source", String, nullable=False),
    Column("url", String, nullable=False),
    Column("category", String, nullable=False),
    Column("metric", String, nullable=False),
    Column("higher_is_better", Integer, nullable=False, server_default=text("1")),
    Column("tier", Integer, nullable=False, server_default=text("2")),
    Column("description", Text),
    Column("scraper_id", String),
    Column("active", Integer, nullable=False, server_default=text("1")),
)

providers = Table(
    "providers",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False, unique=True),
    Column("country_code", String),
    Column("country_name", String),
    Column("origin_countries_json", Text, nullable=False, server_default=text("'[]'")),
    Column("origin_basis", String),
    Column("source_url", String),
    Column("verified_at", String),
    Column("active", Integer, nullable=False, server_default=text("1")),
)

model_use_case_approvals = Table(
    "model_use_case_approvals",
    metadata,
    Column("model_id", String, ForeignKey("models.id"), primary_key=True),
    Column("use_case_id", String, primary_key=True),
    Column("approved_for_use", Integer, nullable=False, server_default=text("0")),
    Column("approval_notes", Text),
    Column("approval_updated_at", String),
    Column("recommendation_status", String, nullable=False, server_default=text("'unrated'")),
    Column("recommendation_notes", Text),
    Column("recommendation_updated_at", String),
)

models = Table(
    "models",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("provider_id", String, ForeignKey("providers.id")),
    Column("provider", String, nullable=False),
    Column("type", String, nullable=False, server_default=text("'proprietary'")),
    Column("catalog_status", String, nullable=False, server_default=text("'tracked'")),
    Column("release_date", String),
    Column("context_window", String),
    Column("context_window_tokens", Integer),
    Column("max_output_tokens", Integer),
    Column("price_input_per_mtok", Float),
    Column("price_output_per_mtok", Float),
    Column("openrouter_model_id", String),
    Column("openrouter_canonical_slug", String),
    Column("openrouter_added_at", String),
    Column("metadata_source_name", String),
    Column("metadata_source_url", String),
    Column("metadata_verified_at", String),
    Column("openrouter_global_rank", Integer),
    Column("openrouter_global_total_tokens", Integer),
    Column("openrouter_global_share", Float),
    Column("openrouter_global_change_ratio", Float),
    Column("openrouter_global_request_count", Integer),
    Column("openrouter_programming_rank", Integer),
    Column("openrouter_programming_total_tokens", Integer),
    Column("openrouter_programming_volume", Float),
    Column("openrouter_programming_request_count", Integer),
    Column("market_source_name", String),
    Column("market_source_url", String),
    Column("market_verified_at", String),
    Column("family_id", String),
    Column("family_name", String),
    Column("canonical_model_id", String),
    Column("canonical_model_name", String),
    Column("variant_label", String),
    Column("discovered_at", String),
    Column("discovered_update_log_id", Integer),
    Column("approved_for_use", Integer, nullable=False, server_default=text("0")),
    Column("approval_notes", Text),
    Column("approval_updated_at", String),
    Column("active", Integer, nullable=False, server_default=text("1")),
)

model_inference_destinations = Table(
    "model_inference_destinations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("model_id", String, ForeignKey("models.id"), nullable=False),
    Column("destination_id", String, nullable=False),
    Column("name", String, nullable=False),
    Column("hyperscaler", String, nullable=False),
    Column("availability_scope", String, nullable=False),
    Column("availability_note", Text),
    Column("location_scope", String, nullable=False),
    Column("regions_json", Text, nullable=False, server_default=text("'[]'")),
    Column("region_count", Integer, nullable=False, server_default=text("0")),
    Column("deployment_modes_json", Text, nullable=False, server_default=text("'[]'")),
    Column("pricing_label", String),
    Column("pricing_note", Text),
    Column("sources_json", Text, nullable=False, server_default=text("'[]'")),
    Column("catalog_model_id", String),
    Column("synced_at", String, nullable=False),
)

inference_sync_status = Table(
    "inference_sync_status",
    metadata,
    Column("destination_id", String, primary_key=True),
    Column("last_status", String, nullable=False, server_default=text("'pending'")),
    Column("last_attempted_at", String),
    Column("last_completed_at", String),
    Column("detail_json", Text),
)

scores = Table(
    "scores",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("model_id", String, ForeignKey("models.id"), nullable=False),
    Column("benchmark_id", String, ForeignKey("benchmarks.id"), nullable=False),
    Column("value", Float, nullable=False),
    Column("raw_value", Text),
    Column("collected_at", String, nullable=False),
    Column("source_url", String),
    Column("source_type", String, nullable=False, server_default=text("'primary'")),
    Column("verified", Integer, nullable=False, server_default=text("0")),
    Column("notes", Text),
)

use_case_benchmark_weights = Table(
    "use_case_benchmark_weights",
    metadata,
    Column("use_case_id", String, primary_key=True),
    Column("benchmark_id", String, ForeignKey("benchmarks.id"), primary_key=True),
    Column("weight", Float, nullable=False),
    Column("updated_at", String, nullable=False),
)

model_market_snapshots = Table(
    "model_market_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_name", String, nullable=False),
    Column("scope", String, nullable=False),
    Column("category_slug", String, nullable=False, server_default=text("''")),
    Column("snapshot_date", String, nullable=False),
    Column("model_id", String, ForeignKey("models.id"), nullable=False),
    Column("openrouter_slug", String),
    Column("rank", Integer, nullable=False),
    Column("total_tokens", Integer),
    Column("share", Float),
    Column("change_ratio", Float),
    Column("request_count", Integer),
    Column("volume", Float),
    Column("source_url", String),
    Column("payload_json", Text, nullable=False),
    Column("collected_at", String, nullable=False),
)

update_log = Table(
    "update_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("started_at", String, nullable=False),
    Column("completed_at", String),
    Column("triggered_by", String, nullable=False, server_default=text("'manual'")),
    Column("status", String, nullable=False, server_default=text("'running'")),
    Column("scores_added", Integer, server_default=text("0")),
    Column("scores_updated", Integer, server_default=text("0")),
    Column("errors", Text),
    Column("current_step_key", String),
    Column("current_step_label", String),
    Column("current_step_started_at", String),
    Column("current_step_index", Integer, nullable=False, server_default=text("0")),
    Column("total_steps", Integer, nullable=False, server_default=text("0")),
    Column("steps_json", Text),
)

source_runs = Table(
    "source_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("update_log_id", Integer, ForeignKey("update_log.id")),
    Column("source_name", String, nullable=False),
    Column("benchmark_id", String),
    Column("started_at", String, nullable=False),
    Column("completed_at", String),
    Column("status", String, nullable=False, server_default=text("'running'")),
    Column("records_found", Integer, server_default=text("0")),
    Column("error_message", Text),
    Column("details_json", Text),
)

raw_source_records = Table(
    "raw_source_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_run_id", Integer, ForeignKey("source_runs.id"), nullable=False),
    Column("benchmark_id", String),
    Column("raw_model_name", String, nullable=False),
    Column("normalized_model_id", String, ForeignKey("models.id")),
    Column("raw_key", String),
    Column("raw_value", Text),
    Column("payload_json", Text, nullable=False),
    Column("source_url", String),
    Column("source_type", String, nullable=False, server_default=text("'primary'")),
    Column("verified", Integer, nullable=False, server_default=text("0")),
    Column("resolution_status", String, nullable=False, server_default=text("'resolved'")),
    Column("collected_at", String, nullable=False),
    Column("notes", Text),
)

audit_runs = Table(
    "audit_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("update_log_id", Integer, ForeignKey("update_log.id"), nullable=False, unique=True),
    Column("started_at", String, nullable=False),
    Column("completed_at", String),
    Column("status", String, nullable=False, server_default=text("'passed'")),
    Column("blocker_count", Integer, nullable=False, server_default=text("0")),
    Column("warning_count", Integer, nullable=False, server_default=text("0")),
    Column("info_count", Integer, nullable=False, server_default=text("0")),
    Column("summary_json", Text),
)

audit_findings = Table(
    "audit_findings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("audit_run_id", Integer, ForeignKey("audit_runs.id"), nullable=False),
    Column("severity", String, nullable=False),
    Column("check_name", String, nullable=False),
    Column("message", Text, nullable=False),
    Column("details_json", Text),
    Column("created_at", String, nullable=False),
)

TABLES: tuple[Table, ...] = (
    benchmarks,
    providers,
    models,
    model_inference_destinations,
    inference_sync_status,
    scores,
    use_case_benchmark_weights,
    model_market_snapshots,
    update_log,
    source_runs,
    raw_source_records,
    audit_runs,
    audit_findings,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or DEFAULT_DATABASE_URL
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, connect_args=connect_args)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[unused-ignore]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def _create_schema_sql() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS benchmarks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            short TEXT NOT NULL,
            source TEXT NOT NULL,
            url TEXT NOT NULL,
            category TEXT NOT NULL,
            metric TEXT NOT NULL,
            higher_is_better INTEGER NOT NULL DEFAULT 1,
            tier INTEGER NOT NULL DEFAULT 2,
            description TEXT,
            scraper_id TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            country_code TEXT,
            country_name TEXT,
            origin_countries_json TEXT NOT NULL DEFAULT '[]',
            origin_basis TEXT,
            source_url TEXT,
            verified_at TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            provider_id TEXT REFERENCES providers(id),
            provider TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'proprietary',
            catalog_status TEXT NOT NULL DEFAULT 'tracked',
            release_date TEXT,
            context_window TEXT,
            context_window_tokens INTEGER,
            max_output_tokens INTEGER,
            price_input_per_mtok REAL,
            price_output_per_mtok REAL,
            openrouter_model_id TEXT,
            openrouter_canonical_slug TEXT,
            openrouter_added_at TEXT,
            metadata_source_name TEXT,
            metadata_source_url TEXT,
            metadata_verified_at TEXT,
            openrouter_global_rank INTEGER,
            openrouter_global_total_tokens INTEGER,
            openrouter_global_share REAL,
            openrouter_global_change_ratio REAL,
            openrouter_global_request_count INTEGER,
            openrouter_programming_rank INTEGER,
            openrouter_programming_total_tokens INTEGER,
            openrouter_programming_volume REAL,
            openrouter_programming_request_count INTEGER,
            market_source_name TEXT,
            market_source_url TEXT,
            market_verified_at TEXT,
            family_id TEXT,
            family_name TEXT,
            canonical_model_id TEXT,
            canonical_model_name TEXT,
            variant_label TEXT,
            discovered_at TEXT,
            discovered_update_log_id INTEGER REFERENCES update_log(id),
            approved_for_use INTEGER NOT NULL DEFAULT 0,
            approval_notes TEXT,
            approval_updated_at TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_use_case_approvals (
            model_id TEXT NOT NULL REFERENCES models(id),
            use_case_id TEXT NOT NULL,
            approved_for_use INTEGER NOT NULL DEFAULT 0,
            approval_notes TEXT,
            approval_updated_at TEXT,
            recommendation_status TEXT NOT NULL DEFAULT 'unrated',
            recommendation_notes TEXT,
            recommendation_updated_at TEXT,
            PRIMARY KEY (model_id, use_case_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_inference_destinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT NOT NULL REFERENCES models(id),
            destination_id TEXT NOT NULL,
            name TEXT NOT NULL,
            hyperscaler TEXT NOT NULL,
            availability_scope TEXT NOT NULL,
            availability_note TEXT,
            location_scope TEXT NOT NULL,
            regions_json TEXT NOT NULL DEFAULT '[]',
            region_count INTEGER NOT NULL DEFAULT 0,
            deployment_modes_json TEXT NOT NULL DEFAULT '[]',
            pricing_label TEXT,
            pricing_note TEXT,
            sources_json TEXT NOT NULL DEFAULT '[]',
            catalog_model_id TEXT,
            synced_at TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_model_inference_destinations_unique
        ON model_inference_destinations (model_id, destination_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS inference_sync_status (
            destination_id TEXT PRIMARY KEY,
            last_status TEXT NOT NULL DEFAULT 'pending',
            last_attempted_at TEXT,
            last_completed_at TEXT,
            detail_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT NOT NULL REFERENCES models(id),
            benchmark_id TEXT NOT NULL REFERENCES benchmarks(id),
            value REAL NOT NULL,
            raw_value TEXT,
            collected_at TEXT NOT NULL,
            source_url TEXT,
            source_type TEXT NOT NULL DEFAULT 'primary',
            verified INTEGER NOT NULL DEFAULT 0,
            notes TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS use_case_benchmark_weights (
            use_case_id TEXT NOT NULL,
            benchmark_id TEXT NOT NULL REFERENCES benchmarks(id),
            weight REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (use_case_id, benchmark_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            scope TEXT NOT NULL,
            category_slug TEXT NOT NULL DEFAULT '',
            snapshot_date TEXT NOT NULL,
            model_id TEXT NOT NULL REFERENCES models(id),
            openrouter_slug TEXT,
            rank INTEGER NOT NULL,
            total_tokens INTEGER,
            share REAL,
            change_ratio REAL,
            request_count INTEGER,
            volume REAL,
            source_url TEXT,
            payload_json TEXT NOT NULL,
            collected_at TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_model_market_snapshots_unique
        ON model_market_snapshots (source_name, scope, category_slug, snapshot_date, model_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'running',
            scores_added INTEGER DEFAULT 0,
            scores_updated INTEGER DEFAULT 0,
            errors TEXT,
            current_step_key TEXT,
            current_step_label TEXT,
            current_step_started_at TEXT,
            current_step_index INTEGER NOT NULL DEFAULT 0,
            total_steps INTEGER NOT NULL DEFAULT 0,
            steps_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS source_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            update_log_id INTEGER REFERENCES update_log(id),
            source_name TEXT NOT NULL,
            benchmark_id TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            records_found INTEGER DEFAULT 0,
            error_message TEXT,
            details_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS raw_source_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_run_id INTEGER NOT NULL REFERENCES source_runs(id),
            benchmark_id TEXT,
            raw_model_name TEXT NOT NULL,
            normalized_model_id TEXT REFERENCES models(id),
            raw_key TEXT,
            raw_value TEXT,
            payload_json TEXT NOT NULL,
            source_url TEXT,
            source_type TEXT NOT NULL DEFAULT 'primary',
            verified INTEGER NOT NULL DEFAULT 0,
            resolution_status TEXT NOT NULL DEFAULT 'resolved',
            collected_at TEXT NOT NULL,
            notes TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            update_log_id INTEGER NOT NULL UNIQUE REFERENCES update_log(id),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL DEFAULT 'passed',
            blocker_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            info_count INTEGER NOT NULL DEFAULT 0,
            summary_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_run_id INTEGER NOT NULL REFERENCES audit_runs(id),
            severity TEXT NOT NULL,
            check_name TEXT NOT NULL,
            message TEXT NOT NULL,
            details_json TEXT,
            created_at TEXT NOT NULL
        )
        """,
    ]


LATEST_SCORES_VIEW_SQL = """
CREATE VIEW latest_scores AS
SELECT
    ranked.id,
    ranked.model_id,
    ranked.benchmark_id,
    ranked.value,
    ranked.raw_value,
    ranked.collected_at,
    ranked.source_url,
    ranked.source_type,
    ranked.verified,
    ranked.notes
FROM (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY s.model_id, s.benchmark_id
            ORDER BY s.collected_at DESC, s.id DESC
        ) AS row_num
    FROM scores s
) ranked
WHERE ranked.row_num = 1
"""


def init_db(engine: Engine | None = None) -> Engine:
    engine = engine or get_engine()
    if engine.url.get_backend_name() == "sqlite":
        database_path = engine.url.database
        if database_path and database_path != ":memory:":
            Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    with engine.begin() as conn:
        for statement in _create_schema_sql():
            conn.exec_driver_sql(statement)
        _ensure_schema_migrations(conn)
        conn.exec_driver_sql("DROP VIEW IF EXISTS latest_scores")
        conn.exec_driver_sql(LATEST_SCORES_VIEW_SQL)
    return engine


def _ensure_schema_migrations(conn: Connection) -> None:
    if conn.engine.url.get_backend_name() != "sqlite":
        return

    raw_source_record_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(raw_source_records)").fetchall()
    }
    if "resolution_status" not in raw_source_record_columns:
        conn.exec_driver_sql(
            "ALTER TABLE raw_source_records "
            "ADD COLUMN resolution_status TEXT NOT NULL DEFAULT 'resolved'"
        )

    provider_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(providers)").fetchall()
    }
    expected_provider_columns = {
        "origin_countries_json": "ALTER TABLE providers ADD COLUMN origin_countries_json TEXT NOT NULL DEFAULT '[]'",
    }
    for column_name, statement in expected_provider_columns.items():
        if column_name not in provider_columns:
            conn.exec_driver_sql(statement)

    model_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(models)").fetchall()
    }
    expected_model_columns = {
        "provider_id": "ALTER TABLE models ADD COLUMN provider_id TEXT",
        "catalog_status": "ALTER TABLE models ADD COLUMN catalog_status TEXT NOT NULL DEFAULT 'tracked'",
        "context_window_tokens": "ALTER TABLE models ADD COLUMN context_window_tokens INTEGER",
        "max_output_tokens": "ALTER TABLE models ADD COLUMN max_output_tokens INTEGER",
        "price_input_per_mtok": "ALTER TABLE models ADD COLUMN price_input_per_mtok REAL",
        "price_output_per_mtok": "ALTER TABLE models ADD COLUMN price_output_per_mtok REAL",
        "openrouter_model_id": "ALTER TABLE models ADD COLUMN openrouter_model_id TEXT",
        "openrouter_canonical_slug": "ALTER TABLE models ADD COLUMN openrouter_canonical_slug TEXT",
        "openrouter_added_at": "ALTER TABLE models ADD COLUMN openrouter_added_at TEXT",
        "metadata_source_name": "ALTER TABLE models ADD COLUMN metadata_source_name TEXT",
        "metadata_source_url": "ALTER TABLE models ADD COLUMN metadata_source_url TEXT",
        "metadata_verified_at": "ALTER TABLE models ADD COLUMN metadata_verified_at TEXT",
        "openrouter_global_rank": "ALTER TABLE models ADD COLUMN openrouter_global_rank INTEGER",
        "openrouter_global_total_tokens": "ALTER TABLE models ADD COLUMN openrouter_global_total_tokens INTEGER",
        "openrouter_global_share": "ALTER TABLE models ADD COLUMN openrouter_global_share REAL",
        "openrouter_global_change_ratio": "ALTER TABLE models ADD COLUMN openrouter_global_change_ratio REAL",
        "openrouter_global_request_count": "ALTER TABLE models ADD COLUMN openrouter_global_request_count INTEGER",
        "openrouter_programming_rank": "ALTER TABLE models ADD COLUMN openrouter_programming_rank INTEGER",
        "openrouter_programming_total_tokens": "ALTER TABLE models ADD COLUMN openrouter_programming_total_tokens INTEGER",
        "openrouter_programming_volume": "ALTER TABLE models ADD COLUMN openrouter_programming_volume REAL",
        "openrouter_programming_request_count": "ALTER TABLE models ADD COLUMN openrouter_programming_request_count INTEGER",
        "market_source_name": "ALTER TABLE models ADD COLUMN market_source_name TEXT",
        "market_source_url": "ALTER TABLE models ADD COLUMN market_source_url TEXT",
        "market_verified_at": "ALTER TABLE models ADD COLUMN market_verified_at TEXT",
        "family_id": "ALTER TABLE models ADD COLUMN family_id TEXT",
        "family_name": "ALTER TABLE models ADD COLUMN family_name TEXT",
        "canonical_model_id": "ALTER TABLE models ADD COLUMN canonical_model_id TEXT",
        "canonical_model_name": "ALTER TABLE models ADD COLUMN canonical_model_name TEXT",
        "variant_label": "ALTER TABLE models ADD COLUMN variant_label TEXT",
        "discovered_at": "ALTER TABLE models ADD COLUMN discovered_at TEXT",
        "discovered_update_log_id": "ALTER TABLE models ADD COLUMN discovered_update_log_id INTEGER",
        "approved_for_use": "ALTER TABLE models ADD COLUMN approved_for_use INTEGER NOT NULL DEFAULT 0",
        "approval_notes": "ALTER TABLE models ADD COLUMN approval_notes TEXT",
        "approval_updated_at": "ALTER TABLE models ADD COLUMN approval_updated_at TEXT",
    }
    for column_name, statement in expected_model_columns.items():
        if column_name not in model_columns:
            conn.exec_driver_sql(statement)

    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS model_market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            scope TEXT NOT NULL,
            category_slug TEXT NOT NULL DEFAULT '',
            snapshot_date TEXT NOT NULL,
            model_id TEXT NOT NULL REFERENCES models(id),
            openrouter_slug TEXT,
            rank INTEGER NOT NULL,
            total_tokens INTEGER,
            share REAL,
            change_ratio REAL,
            request_count INTEGER,
            volume REAL,
            source_url TEXT,
            payload_json TEXT NOT NULL,
            collected_at TEXT NOT NULL
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_model_market_snapshots_unique
        ON model_market_snapshots (source_name, scope, category_slug, snapshot_date, model_id)
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS model_inference_destinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT NOT NULL REFERENCES models(id),
            destination_id TEXT NOT NULL,
            name TEXT NOT NULL,
            hyperscaler TEXT NOT NULL,
            availability_scope TEXT NOT NULL,
            availability_note TEXT,
            location_scope TEXT NOT NULL,
            regions_json TEXT NOT NULL DEFAULT '[]',
            region_count INTEGER NOT NULL DEFAULT 0,
            deployment_modes_json TEXT NOT NULL DEFAULT '[]',
            pricing_label TEXT,
            pricing_note TEXT,
            sources_json TEXT NOT NULL DEFAULT '[]',
            catalog_model_id TEXT,
            synced_at TEXT NOT NULL
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_model_inference_destinations_unique
        ON model_inference_destinations (model_id, destination_id)
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS inference_sync_status (
            destination_id TEXT PRIMARY KEY,
            last_status TEXT NOT NULL DEFAULT 'pending',
            last_attempted_at TEXT,
            last_completed_at TEXT,
            detail_json TEXT
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS model_use_case_approvals (
            model_id TEXT NOT NULL REFERENCES models(id),
            use_case_id TEXT NOT NULL,
            approved_for_use INTEGER NOT NULL DEFAULT 0,
            approval_notes TEXT,
            approval_updated_at TEXT,
            recommendation_status TEXT NOT NULL DEFAULT 'unrated',
            recommendation_notes TEXT,
            recommendation_updated_at TEXT,
            PRIMARY KEY (model_id, use_case_id)
        )
        """
    )
    approval_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(model_use_case_approvals)").fetchall()
    }
    expected_approval_columns = {
        "recommendation_status": "ALTER TABLE model_use_case_approvals ADD COLUMN recommendation_status TEXT NOT NULL DEFAULT 'unrated'",
        "recommendation_notes": "ALTER TABLE model_use_case_approvals ADD COLUMN recommendation_notes TEXT",
        "recommendation_updated_at": "ALTER TABLE model_use_case_approvals ADD COLUMN recommendation_updated_at TEXT",
    }
    for column_name, statement in expected_approval_columns.items():
        if column_name not in approval_columns:
            conn.exec_driver_sql(statement)
    update_log_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(update_log)").fetchall()
    }
    expected_update_log_columns = {
        "current_step_key": "ALTER TABLE update_log ADD COLUMN current_step_key TEXT",
        "current_step_label": "ALTER TABLE update_log ADD COLUMN current_step_label TEXT",
        "current_step_started_at": "ALTER TABLE update_log ADD COLUMN current_step_started_at TEXT",
        "current_step_index": "ALTER TABLE update_log ADD COLUMN current_step_index INTEGER NOT NULL DEFAULT 0",
        "total_steps": "ALTER TABLE update_log ADD COLUMN total_steps INTEGER NOT NULL DEFAULT 0",
        "steps_json": "ALTER TABLE update_log ADD COLUMN steps_json TEXT",
    }
    for column_name, statement in expected_update_log_columns.items():
        if column_name not in update_log_columns:
            conn.exec_driver_sql(statement)


@contextmanager
def get_connection(engine: Engine | None = None) -> Iterator[Connection]:
    engine = engine or get_engine()
    with engine.begin() as conn:
        yield conn


def fetch_all(conn: Connection, statement: Any, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = conn.execute(statement, parameters or {})
    return [dict(row._mapping) for row in result.fetchall()]


def fetch_one(
    conn: Connection,
    statement: Any,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    result = conn.execute(statement, parameters or {})
    row = result.mappings().first()
    return dict(row) if row is not None else None


def row_to_dict(row: RowMapping | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


__all__ = [
    "DEFAULT_DATABASE_URL",
    "DEFAULT_DB_PATH",
    "LATEST_SCORES_VIEW_SQL",
    "TABLES",
    "audit_findings",
    "audit_runs",
    "benchmarks",
    "fetch_all",
    "fetch_one",
    "get_connection",
    "get_engine",
    "init_db",
    "inference_sync_status",
    "metadata",
    "models",
    "model_inference_destinations",
    "model_market_snapshots",
    "model_use_case_approvals",
    "providers",
    "raw_source_records",
    "row_to_dict",
    "scores",
    "source_runs",
    "update_log",
    "use_case_benchmark_weights",
    "utc_now",
    "utc_now_iso",
]
