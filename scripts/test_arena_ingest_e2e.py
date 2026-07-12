#!/usr/bin/env python3
"""Live Arena ingestion smoke test against an isolated temporary SQLite DB."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from pathlib import Path
import sys
import tempfile

import httpx
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import audit_engine, update_engine
from backend.catalog_export import render_model_metadata_csv_bundle
from backend.database import (
    get_connection,
    get_engine,
    init_db,
    model_source_listings,
    models,
    scores,
)
from backend.seed_data import seed_reference_data
from backend.sources.chatbot_arena import ChatbotArenaAdapter


async def _run() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="arena-ingest-e2e-") as tempdir:
        database_path = Path(tempdir) / "arena.sqlite"
        engine = init_db(get_engine(f"sqlite:///{database_path}"))
        init_db(engine)  # migration idempotency
        with engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

        adapter = ChatbotArenaAdapter()
        async with httpx.AsyncClient() as client:
            result = await adapter.collect(client)
        if not result.candidates:
            raise AssertionError("Live Arena collection returned no candidates.")

        original_engine = update_engine.ENGINE
        original_bootstrapped = update_engine.BOOTSTRAPPED
        update_engine.ENGINE = engine
        update_engine.BOOTSTRAPPED = True
        try:
            seeded_names: set[str] = set()
            for known_candidate in result.candidates:
                if known_candidate.raw_model_name.casefold() in seeded_names:
                    continue
                update_engine._ensure_model(
                    known_candidate.raw_model_name,
                    known_candidate.metadata,
                    known_candidate.raw_model_key,
                )
                seeded_names.add(known_candidate.raw_model_name.casefold())
                if len(seeded_names) >= 25:
                    break
            with get_connection(engine) as conn:
                model_count_before = int(conn.scalar(select(func.count()).select_from(models)) or 0)

            log_id = update_engine._create_update_log("test")
            source_run_id = update_engine._start_source_run(log_id, adapter)
            added, updated = update_engine._persist_source_result(source_run_id, result)
            update_engine._finish_source_run(
                source_run_id,
                status="completed",
                records_found=len(result.raw_records),
                error_message=None,
            )

            with get_connection(engine) as conn:
                model_count_after = int(conn.scalar(select(func.count()).select_from(models)) or 0)
                listing_count = int(conn.scalar(select(func.count()).select_from(model_source_listings)) or 0)
                resolved_listing_count = int(
                    conn.scalar(
                        select(func.count())
                        .select_from(model_source_listings)
                        .where(model_source_listings.c.model_id.is_not(None))
                    )
                    or 0
                )
                score_rows = [dict(row) for row in conn.execute(select(scores)).mappings().all()]
            if model_count_after != model_count_before:
                raise AssertionError("Arena persistence created a catalog model.")
            if listing_count != len(result.raw_records):
                raise AssertionError("Arena listing evidence was not upserted for every raw record.")
            if resolved_listing_count < 20:
                raise AssertionError("Arena identity audit fixture did not seed enough canonical identities.")
            if not score_rows:
                raise AssertionError("Known Arena identity did not produce a score.")
            evidence = score_rows[0]
            for required_field in (
                "confidence_lower",
                "confidence_upper",
                "rank",
                "category",
                "publication_date",
                "methodology",
                "source_listing_status",
                "source_metadata_json",
            ):
                if evidence.get(required_field) is None:
                    raise AssertionError(f"Arena score evidence is missing {required_field}.")

            audit = audit_engine.run_audit(engine, log_id)
            if audit["status"] == "failed":
                raise AssertionError(f"Arena audit failed: {audit['findings']}")

            exported_models = update_engine.list_models()
            exported_known = next(
                model for model in exported_models if model["id"] == score_rows[0]["model_id"]
            )
            if not exported_known["source_listings"]:
                raise AssertionError("API model payload omitted Arena listing lifecycle evidence.")
            bundle = render_model_metadata_csv_bundle([exported_known])
            score_csv = list(csv.DictReader(io.StringIO(bundle["scores"])))
            listing_csv = list(csv.DictReader(io.StringIO(bundle["source-listings"])))
            if not score_csv or not listing_csv:
                raise AssertionError("CSV export omitted Arena score or listing evidence.")

            revisions = {
                record.metadata.get("dataset_revision") for record in result.raw_records
            }
            if len(revisions) != 1:
                raise AssertionError("Arena subsets were not pinned to one revision.")
            return {
                "status": "passed",
                "database": str(database_path),
                "dataset_revision": next(iter(revisions)),
                "raw_records": len(result.raw_records),
                "benchmark_ids": sorted({record.benchmark_id for record in result.raw_records}),
                "scores_added": added,
                "scores_updated": updated,
                "listing_evidence_rows": listing_count,
                "resolved_listing_evidence_rows": resolved_listing_count,
                "audit_status": audit["status"],
                "models_created_by_ingest": model_count_after - model_count_before,
            }
        finally:
            update_engine.ENGINE = original_engine
            update_engine.BOOTSTRAPPED = original_bootstrapped
            engine.dispose()


def main() -> int:
    print(json.dumps(asyncio.run(_run()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
