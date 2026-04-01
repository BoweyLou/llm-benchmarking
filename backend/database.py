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

models = Table(
    "models",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("provider", String, nullable=False),
    Column("type", String, nullable=False, server_default=text("'proprietary'")),
    Column("release_date", String),
    Column("context_window", String),
    Column("active", Integer, nullable=False, server_default=text("1")),
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
    models,
    scores,
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
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            provider TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'proprietary',
            release_date TEXT,
            context_window TEXT,
            active INTEGER NOT NULL DEFAULT 1
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
        CREATE TABLE IF NOT EXISTS update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'running',
            scores_added INTEGER DEFAULT 0,
            scores_updated INTEGER DEFAULT 0,
            errors TEXT
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
    "metadata",
    "models",
    "raw_source_records",
    "row_to_dict",
    "scores",
    "source_runs",
    "update_log",
    "utc_now",
    "utc_now_iso",
]
