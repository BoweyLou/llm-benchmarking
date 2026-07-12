"""SQLAlchemy Core schema and database helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterator

from sqlalchemy import Column, Float, ForeignKey, Integer, MetaData, String, Table, Text, create_engine, event, text
from sqlalchemy.engine import Connection, Engine, RowMapping

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "db.sqlite"
DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

metadata = MetaData()

schema_migrations = Table(
    "schema_migrations",
    metadata,
    Column("id", String, primary_key=True),
    Column("applied_at", String, nullable=False),
)

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

model_use_case_recommendation_proposals = Table(
    "model_use_case_recommendation_proposals",
    metadata,
    Column("profile_id", String, primary_key=True),
    Column("model_id", String, ForeignKey("models.id"), primary_key=True),
    Column("use_case_id", String, primary_key=True),
    Column("proposed_status", String, nullable=False),
    Column("score", Float),
    Column("confidence", Float),
    Column("blockers_json", Text, nullable=False, server_default=text("'[]'")),
    Column("warnings_json", Text, nullable=False, server_default=text("'[]'")),
    Column("reasons_json", Text, nullable=False, server_default=text("'[]'")),
    Column("required_controls_json", Text, nullable=False, server_default=text("'[]'")),
    Column("policy_version", String, nullable=False),
    Column("computed_at", String, nullable=False),
    Column("source_profile_json", Text, nullable=False, server_default=text("'{}'")),
)

model_use_case_inference_approvals = Table(
    "model_use_case_inference_approvals",
    metadata,
    Column("model_id", String, ForeignKey("models.id"), primary_key=True),
    Column("use_case_id", String, primary_key=True),
    Column("destination_id", String, primary_key=True),
    Column("location_key", String, primary_key=True),
    Column("location_label", String, nullable=False),
    Column("approved_for_use", Integer, nullable=False, server_default=text("0")),
    Column("approval_notes", Text),
    Column("approval_updated_at", String),
)

model_identity_overrides = Table(
    "model_identity_overrides",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_model_id", String, nullable=False, unique=True),
    Column("match_provider", String, nullable=False),
    Column("match_name", String, nullable=False),
    Column("match_key", String, nullable=False, unique=True),
    Column("family_id", String, nullable=False),
    Column("family_name", String, nullable=False),
    Column("canonical_model_id", String, nullable=False),
    Column("canonical_model_name", String, nullable=False),
    Column("variant_label", String),
    Column("notes", Text),
    Column("updated_at", String, nullable=False),
    Column("active", Integer, nullable=False, server_default=text("1")),
)

model_duplicate_overrides = Table(
    "model_duplicate_overrides",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_model_id", String, nullable=False, unique=True),
    Column("match_provider", String, nullable=False),
    Column("match_name", String, nullable=False),
    Column("match_key", String, nullable=False, unique=True),
    Column("target_model_id", String, nullable=False),
    Column("notes", Text),
    Column("updated_at", String, nullable=False),
    Column("active", Integer, nullable=False, server_default=text("1")),
)

models = Table(
    "models",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("provider_id", String, ForeignKey("providers.id")),
    Column("provider", String, nullable=False),
    Column("type", String, nullable=False, server_default=text("'proprietary'")),
    Column("model_roles_json", Text, nullable=False, server_default=text("'[\"generator\"]'")),
    Column("catalog_status", String, nullable=False, server_default=text("'tracked'")),
    Column("release_date", String),
    Column("release_date_precision", String),
    Column("release_date_confidence", String),
    Column("release_date_source_name", String),
    Column("release_date_source_url", String),
    Column("release_date_verified_at", String),
    Column("context_window", String),
    Column("context_window_tokens", Integer),
    Column("max_output_tokens", Integer),
    Column("parameter_count_b", Float),
    Column("active_parameter_count_b", Float),
    Column("model_size_class", String),
    Column("small_model_candidate", Integer, nullable=False, server_default=text("0")),
    Column("model_size_source_name", String),
    Column("model_size_source_url", String),
    Column("model_size_verified_at", String),
    Column("price_input_per_mtok", Float),
    Column("price_output_per_mtok", Float),
    Column("openrouter_model_id", String),
    Column("openrouter_canonical_slug", String),
    Column("openrouter_added_at", String),
    Column("huggingface_repo_id", String),
    Column("huggingface_created_at", String),
    Column("huggingface_last_modified_at", String),
    Column("metadata_source_name", String),
    Column("metadata_source_url", String),
    Column("metadata_verified_at", String),
    Column("model_card_url", String),
    Column("model_card_source", String),
    Column("model_card_verified_at", String),
    Column("documentation_url", String),
    Column("repo_url", String),
    Column("paper_url", String),
    Column("license_id", String),
    Column("license_name", String),
    Column("license_url", String),
    Column("base_models_json", Text, nullable=False, server_default=text("'[]'")),
    Column("supported_languages_json", Text, nullable=False, server_default=text("'[]'")),
    Column("capabilities_json", Text, nullable=False, server_default=text("'[]'")),
    Column("intended_use_short", Text),
    Column("limitations_short", Text),
    Column("training_data_summary", Text),
    Column("training_cutoff", String),
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
    Column("general_approved_for_use", Integer, nullable=False, server_default=text("0")),
    Column("general_approval_notes", Text),
    Column("general_approval_updated_at", String),
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
    Column("confidence_lower", Float),
    Column("confidence_upper", Float),
    Column("variance", Float),
    Column("vote_count", Integer),
    Column("observation_count", Integer),
    Column("session_count", Integer),
    Column("rank", Integer),
    Column("category", String),
    Column("publication_date", String),
    Column("methodology", String),
    Column("source_listing_status", String),
    Column("style_control", Integer),
    Column("preliminary", Integer),
    Column("source_metadata_json", Text),
)

model_source_listings = Table(
    "model_source_listings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_name", String, nullable=False),
    Column("benchmark_id", String, nullable=False),
    Column("raw_model_name", String, nullable=False),
    Column("raw_model_key", String, nullable=False),
    Column("model_id", String, ForeignKey("models.id")),
    Column("listing_status", String, nullable=False),
    Column("source_revision", String),
    Column("publication_date", String),
    Column("first_seen_at", String, nullable=False),
    Column("last_seen_at", String, nullable=False),
    Column("metadata_json", Text, nullable=False, server_default=text("'{}'")),
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
    schema_migrations,
    benchmarks,
    providers,
    model_use_case_approvals,
    model_use_case_recommendation_proposals,
    model_use_case_inference_approvals,
    model_identity_overrides,
    model_duplicate_overrides,
    models,
    model_inference_destinations,
    inference_sync_status,
    scores,
    model_source_listings,
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
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """,
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
            model_roles_json TEXT NOT NULL DEFAULT '["generator"]',
            catalog_status TEXT NOT NULL DEFAULT 'tracked',
            release_date TEXT,
            release_date_precision TEXT,
            release_date_confidence TEXT,
            release_date_source_name TEXT,
            release_date_source_url TEXT,
            release_date_verified_at TEXT,
            context_window TEXT,
            context_window_tokens INTEGER,
            max_output_tokens INTEGER,
            parameter_count_b REAL,
            active_parameter_count_b REAL,
            model_size_class TEXT,
            small_model_candidate INTEGER NOT NULL DEFAULT 0,
            model_size_source_name TEXT,
            model_size_source_url TEXT,
            model_size_verified_at TEXT,
            price_input_per_mtok REAL,
            price_output_per_mtok REAL,
            openrouter_model_id TEXT,
            openrouter_canonical_slug TEXT,
            openrouter_added_at TEXT,
            huggingface_repo_id TEXT,
            huggingface_created_at TEXT,
            huggingface_last_modified_at TEXT,
            metadata_source_name TEXT,
            metadata_source_url TEXT,
            metadata_verified_at TEXT,
            model_card_url TEXT,
            model_card_source TEXT,
            model_card_verified_at TEXT,
            documentation_url TEXT,
            repo_url TEXT,
            paper_url TEXT,
            license_id TEXT,
            license_name TEXT,
            license_url TEXT,
            base_models_json TEXT NOT NULL DEFAULT '[]',
            supported_languages_json TEXT NOT NULL DEFAULT '[]',
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            intended_use_short TEXT,
            limitations_short TEXT,
            training_data_summary TEXT,
            training_cutoff TEXT,
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
            general_approved_for_use INTEGER NOT NULL DEFAULT 0,
            general_approval_notes TEXT,
            general_approval_updated_at TEXT,
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
        CREATE TABLE IF NOT EXISTS model_use_case_recommendation_proposals (
            profile_id TEXT NOT NULL,
            model_id TEXT NOT NULL REFERENCES models(id),
            use_case_id TEXT NOT NULL,
            proposed_status TEXT NOT NULL,
            score REAL,
            confidence REAL,
            blockers_json TEXT NOT NULL DEFAULT '[]',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            reasons_json TEXT NOT NULL DEFAULT '[]',
            required_controls_json TEXT NOT NULL DEFAULT '[]',
            policy_version TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            source_profile_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (profile_id, model_id, use_case_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_use_case_inference_approvals (
            model_id TEXT NOT NULL REFERENCES models(id),
            use_case_id TEXT NOT NULL,
            destination_id TEXT NOT NULL,
            location_key TEXT NOT NULL,
            location_label TEXT NOT NULL,
            approved_for_use INTEGER NOT NULL DEFAULT 0,
            approval_notes TEXT,
            approval_updated_at TEXT,
            PRIMARY KEY (model_id, use_case_id, destination_id, location_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_identity_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_model_id TEXT NOT NULL UNIQUE,
            match_provider TEXT NOT NULL,
            match_name TEXT NOT NULL,
            match_key TEXT NOT NULL UNIQUE,
            family_id TEXT NOT NULL,
            family_name TEXT NOT NULL,
            canonical_model_id TEXT NOT NULL,
            canonical_model_name TEXT NOT NULL,
            variant_label TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_duplicate_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_model_id TEXT NOT NULL UNIQUE,
            match_provider TEXT NOT NULL,
            match_name TEXT NOT NULL,
            match_key TEXT NOT NULL UNIQUE,
            target_model_id TEXT NOT NULL,
            notes TEXT,
            updated_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
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
            notes TEXT,
            confidence_lower REAL,
            confidence_upper REAL,
            variance REAL,
            vote_count INTEGER,
            observation_count INTEGER,
            session_count INTEGER,
            rank INTEGER,
            category TEXT,
            publication_date TEXT,
            methodology TEXT,
            source_listing_status TEXT
            ,style_control INTEGER
            ,preliminary INTEGER
            ,source_metadata_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_source_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            benchmark_id TEXT NOT NULL,
            raw_model_name TEXT NOT NULL,
            raw_model_key TEXT NOT NULL,
            model_id TEXT REFERENCES models(id),
            listing_status TEXT NOT NULL,
            source_revision TEXT,
            publication_date TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE (source_name, benchmark_id, raw_model_key)
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
    ranked.notes,
    ranked.confidence_lower,
    ranked.confidence_upper,
    ranked.variance,
    ranked.vote_count,
    ranked.observation_count,
    ranked.session_count,
    ranked.rank,
    ranked.category,
    ranked.publication_date,
    ranked.methodology,
    ranked.source_listing_status
    ,ranked.style_control
    ,ranked.preliminary
    ,ranked.source_metadata_json
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

    _ensure_schema_migrations_table(conn)
    applied_migration_ids = _load_applied_schema_migration_ids(conn)
    for migration_id, migration in SCHEMA_MIGRATIONS:
        if migration_id in applied_migration_ids:
            continue
        migration(conn)
        _record_schema_migration(conn, migration_id)


def _ensure_schema_migrations_table(conn: Connection) -> None:
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _load_applied_schema_migration_ids(conn: Connection) -> set[str]:
    rows = conn.exec_driver_sql("SELECT id FROM schema_migrations").fetchall()
    return {str(row[0]) for row in rows}


def _record_schema_migration(conn: Connection, migration_id: str) -> None:
    conn.execute(
        schema_migrations.insert().values(
            id=migration_id,
            applied_at=utc_now_iso(),
        )
    )


def _migration_20260701_schema_repairs(conn: Connection) -> None:
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
        "model_roles_json": "ALTER TABLE models ADD COLUMN model_roles_json TEXT NOT NULL DEFAULT '[\"generator\"]'",
        "catalog_status": "ALTER TABLE models ADD COLUMN catalog_status TEXT NOT NULL DEFAULT 'tracked'",
        "release_date_precision": "ALTER TABLE models ADD COLUMN release_date_precision TEXT",
        "release_date_confidence": "ALTER TABLE models ADD COLUMN release_date_confidence TEXT",
        "release_date_source_name": "ALTER TABLE models ADD COLUMN release_date_source_name TEXT",
        "release_date_source_url": "ALTER TABLE models ADD COLUMN release_date_source_url TEXT",
        "release_date_verified_at": "ALTER TABLE models ADD COLUMN release_date_verified_at TEXT",
        "context_window_tokens": "ALTER TABLE models ADD COLUMN context_window_tokens INTEGER",
        "max_output_tokens": "ALTER TABLE models ADD COLUMN max_output_tokens INTEGER",
        "parameter_count_b": "ALTER TABLE models ADD COLUMN parameter_count_b REAL",
        "active_parameter_count_b": "ALTER TABLE models ADD COLUMN active_parameter_count_b REAL",
        "model_size_class": "ALTER TABLE models ADD COLUMN model_size_class TEXT",
        "small_model_candidate": "ALTER TABLE models ADD COLUMN small_model_candidate INTEGER NOT NULL DEFAULT 0",
        "model_size_source_name": "ALTER TABLE models ADD COLUMN model_size_source_name TEXT",
        "model_size_source_url": "ALTER TABLE models ADD COLUMN model_size_source_url TEXT",
        "model_size_verified_at": "ALTER TABLE models ADD COLUMN model_size_verified_at TEXT",
        "price_input_per_mtok": "ALTER TABLE models ADD COLUMN price_input_per_mtok REAL",
        "price_output_per_mtok": "ALTER TABLE models ADD COLUMN price_output_per_mtok REAL",
        "openrouter_model_id": "ALTER TABLE models ADD COLUMN openrouter_model_id TEXT",
        "openrouter_canonical_slug": "ALTER TABLE models ADD COLUMN openrouter_canonical_slug TEXT",
        "openrouter_added_at": "ALTER TABLE models ADD COLUMN openrouter_added_at TEXT",
        "huggingface_repo_id": "ALTER TABLE models ADD COLUMN huggingface_repo_id TEXT",
        "huggingface_created_at": "ALTER TABLE models ADD COLUMN huggingface_created_at TEXT",
        "huggingface_last_modified_at": "ALTER TABLE models ADD COLUMN huggingface_last_modified_at TEXT",
        "metadata_source_name": "ALTER TABLE models ADD COLUMN metadata_source_name TEXT",
        "metadata_source_url": "ALTER TABLE models ADD COLUMN metadata_source_url TEXT",
        "metadata_verified_at": "ALTER TABLE models ADD COLUMN metadata_verified_at TEXT",
        "model_card_url": "ALTER TABLE models ADD COLUMN model_card_url TEXT",
        "model_card_source": "ALTER TABLE models ADD COLUMN model_card_source TEXT",
        "model_card_verified_at": "ALTER TABLE models ADD COLUMN model_card_verified_at TEXT",
        "documentation_url": "ALTER TABLE models ADD COLUMN documentation_url TEXT",
        "repo_url": "ALTER TABLE models ADD COLUMN repo_url TEXT",
        "paper_url": "ALTER TABLE models ADD COLUMN paper_url TEXT",
        "license_id": "ALTER TABLE models ADD COLUMN license_id TEXT",
        "license_name": "ALTER TABLE models ADD COLUMN license_name TEXT",
        "license_url": "ALTER TABLE models ADD COLUMN license_url TEXT",
        "base_models_json": "ALTER TABLE models ADD COLUMN base_models_json TEXT NOT NULL DEFAULT '[]'",
        "supported_languages_json": "ALTER TABLE models ADD COLUMN supported_languages_json TEXT NOT NULL DEFAULT '[]'",
        "capabilities_json": "ALTER TABLE models ADD COLUMN capabilities_json TEXT NOT NULL DEFAULT '[]'",
        "intended_use_short": "ALTER TABLE models ADD COLUMN intended_use_short TEXT",
        "limitations_short": "ALTER TABLE models ADD COLUMN limitations_short TEXT",
        "training_data_summary": "ALTER TABLE models ADD COLUMN training_data_summary TEXT",
        "training_cutoff": "ALTER TABLE models ADD COLUMN training_cutoff TEXT",
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
        "general_approved_for_use": "ALTER TABLE models ADD COLUMN general_approved_for_use INTEGER NOT NULL DEFAULT 0",
        "general_approval_notes": "ALTER TABLE models ADD COLUMN general_approval_notes TEXT",
        "general_approval_updated_at": "ALTER TABLE models ADD COLUMN general_approval_updated_at TEXT",
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
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS model_use_case_inference_approvals (
            model_id TEXT NOT NULL REFERENCES models(id),
            use_case_id TEXT NOT NULL,
            destination_id TEXT NOT NULL,
            location_key TEXT NOT NULL,
            location_label TEXT NOT NULL,
            approved_for_use INTEGER NOT NULL DEFAULT 0,
            approval_notes TEXT,
            approval_updated_at TEXT,
            PRIMARY KEY (model_id, use_case_id, destination_id, location_key)
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS model_identity_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_model_id TEXT NOT NULL UNIQUE,
            match_provider TEXT NOT NULL,
            match_name TEXT NOT NULL,
            match_key TEXT NOT NULL UNIQUE,
            family_id TEXT NOT NULL,
            family_name TEXT NOT NULL,
            canonical_model_id TEXT NOT NULL,
            canonical_model_name TEXT NOT NULL,
            variant_label TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS model_duplicate_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_model_id TEXT NOT NULL UNIQUE,
            match_provider TEXT NOT NULL,
            match_name TEXT NOT NULL,
            match_key TEXT NOT NULL UNIQUE,
            target_model_id TEXT NOT NULL,
            notes TEXT,
            updated_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
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
    conn.exec_driver_sql(_recommendation_proposal_table_sql())
    inference_approval_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(model_use_case_inference_approvals)").fetchall()
    }
    expected_inference_approval_columns = {
        "location_label": "ALTER TABLE model_use_case_inference_approvals ADD COLUMN location_label TEXT NOT NULL DEFAULT ''",
        "approved_for_use": "ALTER TABLE model_use_case_inference_approvals ADD COLUMN approved_for_use INTEGER NOT NULL DEFAULT 0",
        "approval_notes": "ALTER TABLE model_use_case_inference_approvals ADD COLUMN approval_notes TEXT",
        "approval_updated_at": "ALTER TABLE model_use_case_inference_approvals ADD COLUMN approval_updated_at TEXT",
    }
    for column_name, statement in expected_inference_approval_columns.items():
        if column_name not in inference_approval_columns:
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


def _recommendation_proposal_table_sql() -> str:
    return """
        CREATE TABLE IF NOT EXISTS model_use_case_recommendation_proposals (
            profile_id TEXT NOT NULL,
            model_id TEXT NOT NULL REFERENCES models(id),
            use_case_id TEXT NOT NULL,
            proposed_status TEXT NOT NULL,
            score REAL,
            confidence REAL,
            blockers_json TEXT NOT NULL DEFAULT '[]',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            reasons_json TEXT NOT NULL DEFAULT '[]',
            required_controls_json TEXT NOT NULL DEFAULT '[]',
            policy_version TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            source_profile_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (profile_id, model_id, use_case_id)
        )
    """


def _migration_20260701_recommendation_proposals(conn: Connection) -> None:
    conn.exec_driver_sql(_recommendation_proposal_table_sql())


def _migration_20260701_model_roles(conn: Connection) -> None:
    model_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(models)").fetchall()
    }
    if "model_roles_json" not in model_columns:
        conn.exec_driver_sql("ALTER TABLE models ADD COLUMN model_roles_json TEXT NOT NULL DEFAULT '[\"generator\"]'")


def _migration_20260701_model_size_metadata(conn: Connection) -> None:
    model_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(models)").fetchall()
    }
    expected_model_columns = {
        "parameter_count_b": "ALTER TABLE models ADD COLUMN parameter_count_b REAL",
        "active_parameter_count_b": "ALTER TABLE models ADD COLUMN active_parameter_count_b REAL",
        "model_size_class": "ALTER TABLE models ADD COLUMN model_size_class TEXT",
        "small_model_candidate": "ALTER TABLE models ADD COLUMN small_model_candidate INTEGER NOT NULL DEFAULT 0",
        "model_size_source_name": "ALTER TABLE models ADD COLUMN model_size_source_name TEXT",
        "model_size_source_url": "ALTER TABLE models ADD COLUMN model_size_source_url TEXT",
        "model_size_verified_at": "ALTER TABLE models ADD COLUMN model_size_verified_at TEXT",
    }
    for column_name, statement in expected_model_columns.items():
        if column_name not in model_columns:
            conn.exec_driver_sql(statement)


def _migration_20260702_model_age_metadata(conn: Connection) -> None:
    model_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(models)").fetchall()
    }
    expected_model_columns = {
        "release_date_precision": "ALTER TABLE models ADD COLUMN release_date_precision TEXT",
        "release_date_confidence": "ALTER TABLE models ADD COLUMN release_date_confidence TEXT",
        "release_date_source_name": "ALTER TABLE models ADD COLUMN release_date_source_name TEXT",
        "release_date_source_url": "ALTER TABLE models ADD COLUMN release_date_source_url TEXT",
        "release_date_verified_at": "ALTER TABLE models ADD COLUMN release_date_verified_at TEXT",
        "huggingface_created_at": "ALTER TABLE models ADD COLUMN huggingface_created_at TEXT",
        "huggingface_last_modified_at": "ALTER TABLE models ADD COLUMN huggingface_last_modified_at TEXT",
    }
    for column_name, statement in expected_model_columns.items():
        if column_name not in model_columns:
            conn.exec_driver_sql(statement)


def _migration_20260702_general_model_approvals(conn: Connection) -> None:
    model_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(models)").fetchall()
    }
    expected_model_columns = {
        "general_approved_for_use": "ALTER TABLE models ADD COLUMN general_approved_for_use INTEGER NOT NULL DEFAULT 0",
        "general_approval_notes": "ALTER TABLE models ADD COLUMN general_approval_notes TEXT",
        "general_approval_updated_at": "ALTER TABLE models ADD COLUMN general_approval_updated_at TEXT",
    }
    for column_name, statement in expected_model_columns.items():
        if column_name not in model_columns:
            conn.exec_driver_sql(statement)


_SPEECH_TO_TEXT_ROLE = "speech_to_text"
_TEXT_TO_SPEECH_ROLE = "text_to_speech"
_VALID_MODEL_ROLES = {
    "generator",
    "embedding",
    "reranker",
    "multimodal_embedding",
    _SPEECH_TO_TEXT_ROLE,
    _TEXT_TO_SPEECH_ROLE,
}
_SPEECH_TO_TEXT_CAPABILITY_MARKERS = {
    "automatic-speech-recognition",
    "speech-to-text",
    "voice-to-text",
    "transcription-output",
    "transcription",
    "audio-transcription",
    "asr",
}
_SPEECH_TO_TEXT_NAME_RE = re.compile(
    r"(?<![a-z0-9])(?:asr|whisper|transcribe|transcription|parakeet|mai-transcribe|(?:chirp|voxtral).*(?:asr|stt|transcri))(?![a-z0-9])",
    re.IGNORECASE,
)
_TEXT_TO_SPEECH_CAPABILITY_MARKERS = {
    "text-to-speech",
    "speech-synthesis",
    "text->speech",
    "speech-output",
    "tts",
}
_TEXT_GENERATION_CAPABILITY_MARKERS = {
    "text-output",
    "text->text",
    "chat-completion",
    "completion",
    "structured-output",
    "reasoning",
    "tool-use",
    "tool-choice",
}
_TEXT_TO_SPEECH_NAME_RE = re.compile(
    r"(?<![a-z0-9])(?:tts|text-to-speech|speech-synthesis|gpt-4o-mini-tts|tts-1(?:-hd)?|sonic(?:[-\s]\d(?:\.\d)?)?|kokoro|orpheus|zonos|chatterbox|aura|polly|playdialog|play3|chirp(?:[-\s]*3)?[-:\s]*hd|grok-voice-tts|gemini.*tts|voxtral.*tts|mai-voice|eleven(?:labs)?|multilingual-v2|flash-v2-5|speech-\d+(?:\.\d+)?(?:[-\s](?:hd|turbo))?)(?![a-z0-9])",
    re.IGNORECASE,
)


def _migration_20260703_speech_to_text_roles(conn: Connection) -> None:
    model_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(models)").fetchall()
    }
    required_columns = {"id", "name", "model_roles_json", "capabilities_json"}
    if not required_columns.issubset(model_columns):
        return

    optional_columns = [
        column
        for column in ("huggingface_repo_id", "openrouter_model_id", "openrouter_canonical_slug", "documentation_url")
        if column in model_columns
    ]
    selected_columns = ["id", "name", "model_roles_json", "capabilities_json", *optional_columns]
    rows = conn.exec_driver_sql(f"SELECT {', '.join(selected_columns)} FROM models").mappings().fetchall()
    for row in rows:
        capabilities = _migration_json_list(row.get("capabilities_json"))
        names = [row.get("name"), *[row.get(column) for column in optional_columns]]
        if not _migration_values_indicate_speech_to_text([*capabilities, *names]):
            continue
        roles = [
            role
            for role in _migration_json_list(row.get("model_roles_json"))
            if role in _VALID_MODEL_ROLES
        ] or ["generator"]
        if set(roles) == {"generator"} and not _migration_values_indicate_text_generation(capabilities):
            roles = []
        if _SPEECH_TO_TEXT_ROLE in roles:
            continue
        roles.append(_SPEECH_TO_TEXT_ROLE)
        conn.exec_driver_sql(
            "UPDATE models SET model_roles_json = ? WHERE id = ?",
            (json.dumps(sorted(dict.fromkeys(roles)), ensure_ascii=True), row["id"]),
        )


def _migration_20260703_text_to_speech_roles(conn: Connection) -> None:
    model_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(models)").fetchall()
    }
    required_columns = {"id", "name", "model_roles_json", "capabilities_json"}
    if not required_columns.issubset(model_columns):
        return

    optional_columns = [
        column
        for column in ("huggingface_repo_id", "openrouter_model_id", "openrouter_canonical_slug", "documentation_url")
        if column in model_columns
    ]
    selected_columns = ["id", "name", "model_roles_json", "capabilities_json", *optional_columns]
    rows = conn.exec_driver_sql(f"SELECT {', '.join(selected_columns)} FROM models").mappings().fetchall()
    for row in rows:
        capabilities = _migration_json_list(row.get("capabilities_json"))
        names = [row.get("name"), *[row.get(column) for column in optional_columns]]
        if not _migration_values_indicate_text_to_speech([*capabilities, *names]):
            continue
        roles = [
            role
            for role in _migration_json_list(row.get("model_roles_json"))
            if role in _VALID_MODEL_ROLES
        ] or ["generator"]
        if set(roles) == {"generator"} and not _migration_values_indicate_text_generation(capabilities):
            roles = []
        if _TEXT_TO_SPEECH_ROLE in roles:
            continue
        roles.append(_TEXT_TO_SPEECH_ROLE)
        conn.exec_driver_sql(
            "UPDATE models SET model_roles_json = ? WHERE id = ?",
            (json.dumps(sorted(dict.fromkeys(roles)), ensure_ascii=True), row["id"]),
        )


def _migration_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item or "").strip()]


def _migration_values_indicate_speech_to_text(values: list[Any]) -> bool:
    if _migration_values_indicate_text_to_speech(values):
        explicit_values = [
            value
            for value in values
            if str(value or "").strip().lower().replace("_", "-") in _SPEECH_TO_TEXT_CAPABILITY_MARKERS
            or (
                str(value or "").strip().lower().replace("_", "-").endswith("-output")
                and "transcription" in str(value or "").strip().lower().replace("_", "-")
            )
        ]
        if not explicit_values:
            return False
    for value in values:
        text = str(value or "").strip().lower().replace("_", "-")
        if not text:
            continue
        if text in _SPEECH_TO_TEXT_CAPABILITY_MARKERS:
            return True
        if text.endswith("-output") and "transcription" in text:
            return True
        if _SPEECH_TO_TEXT_NAME_RE.search(text):
            return True
    return False


def _migration_values_indicate_text_to_speech(values: list[Any]) -> bool:
    for value in values:
        text = str(value or "").strip().lower().replace("_", "-")
        if not text:
            continue
        if text in _TEXT_TO_SPEECH_CAPABILITY_MARKERS:
            return True
        if text.endswith("-output") and "speech" in text:
            return True
        if _TEXT_TO_SPEECH_NAME_RE.search(text):
            return True
    return False


def _migration_values_indicate_text_generation(values: list[Any]) -> bool:
    for value in values:
        text = str(value or "").strip().lower().replace("_", "-")
        if not text:
            continue
        if text in _TEXT_GENERATION_CAPABILITY_MARKERS:
            return True
        if text.endswith("->text") and not any(marker in text for marker in ("audio", "speech", "transcription")):
            return True
    return False


def _migration_20260713_score_evidence(conn: Connection) -> None:
    score_columns = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(scores)").fetchall()
    }
    expected_columns = {
        "confidence_lower": "REAL",
        "confidence_upper": "REAL",
        "variance": "REAL",
        "vote_count": "INTEGER",
        "observation_count": "INTEGER",
        "session_count": "INTEGER",
        "rank": "INTEGER",
        "category": "TEXT",
        "publication_date": "TEXT",
        "methodology": "TEXT",
        "source_listing_status": "TEXT",
        "style_control": "INTEGER",
        "preliminary": "INTEGER",
        "source_metadata_json": "TEXT",
    }
    for column_name, column_type in expected_columns.items():
        if column_name not in score_columns:
            conn.exec_driver_sql(f"ALTER TABLE scores ADD COLUMN {column_name} {column_type}")
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS model_source_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            benchmark_id TEXT NOT NULL,
            raw_model_name TEXT NOT NULL,
            raw_model_key TEXT NOT NULL,
            model_id TEXT REFERENCES models(id),
            listing_status TEXT NOT NULL,
            source_revision TEXT,
            publication_date TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE (source_name, benchmark_id, raw_model_key)
        )
        """
    )


SCHEMA_MIGRATIONS: tuple[tuple[str, Callable[[Connection], None]], ...] = (
    ("20260701_001_schema_repairs", _migration_20260701_schema_repairs),
    ("20260701_002_model_roles", _migration_20260701_model_roles),
    ("20260701_003_recommendation_proposals", _migration_20260701_recommendation_proposals),
    ("20260701_004_model_size_metadata", _migration_20260701_model_size_metadata),
    ("20260702_001_model_age_metadata", _migration_20260702_model_age_metadata),
    ("20260702_002_general_model_approvals", _migration_20260702_general_model_approvals),
    ("20260703_001_speech_to_text_roles", _migration_20260703_speech_to_text_roles),
    ("20260703_002_text_to_speech_roles", _migration_20260703_text_to_speech_roles),
    ("20260713_001_score_evidence", _migration_20260713_score_evidence),
)


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
    "SCHEMA_MIGRATIONS",
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
    "model_duplicate_overrides",
    "model_identity_overrides",
    "model_inference_destinations",
    "model_market_snapshots",
    "model_use_case_inference_approvals",
    "model_use_case_approvals",
    "model_use_case_recommendation_proposals",
    "providers",
    "raw_source_records",
    "row_to_dict",
    "schema_migrations",
    "scores",
    "source_runs",
    "update_log",
    "use_case_benchmark_weights",
    "utc_now",
    "utc_now_iso",
]
