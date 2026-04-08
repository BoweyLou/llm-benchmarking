from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select, update

from backend import audit_engine
from backend import update_engine
from backend.database import fetch_all, fetch_one, get_connection, get_engine, init_db, scores as scores_table
from backend.seed_data import seed_reference_data
from backend.sources.artificial_analysis import ArtificialAnalysisAdapter
from backend.sources.base import RawSourceRecord, SourceFetchResult
from backend.sources.chatbot_arena import ChatbotArenaAdapter
from backend.sources.ifeval import IfevalAdapter
from backend.sources.swebench import SwebenchAdapter

FUTURE_COLLECTED_AT = "2099-01-01T00:00:00Z"


class SourceSpotCheckTests(unittest.TestCase):
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

    def _persist_records(self, adapter, raw_records: list[RawSourceRecord]) -> tuple[int, int, list, tuple[int, int]]:
        result = SourceFetchResult(
            source_id=adapter.source_id,
            source_url=adapter.source_url,
            fetched_at=raw_records[0].collected_at if raw_records else FUTURE_COLLECTED_AT,
            raw_records=raw_records,
            candidates=adapter.normalize(raw_records),
        )
        log_id = update_engine._create_update_log("test")
        source_run_id = update_engine._start_source_run(log_id, adapter)
        outcomes = update_engine._persist_source_result(source_run_id, result)
        update_engine._finish_source_run(
            source_run_id,
            status="completed",
            records_found=len(raw_records),
            error_message=None,
        )
        return log_id, source_run_id, result.candidates, outcomes

    def _latest_score(self, model_id: str, benchmark_id: str) -> dict:
        with get_connection(self.engine) as conn:
            row = fetch_one(
                conn,
                select(scores_table)
                .where(scores_table.c.model_id == model_id)
                .where(scores_table.c.benchmark_id == benchmark_id)
                .order_by(scores_table.c.collected_at.desc(), scores_table.c.id.desc())
                .limit(1),
            )
        self.assertIsNotNone(row, f"Missing latest score for model={model_id} benchmark={benchmark_id}")
        return dict(row)

    def test_artificial_analysis_spot_check_persists_multimetric_scores(self) -> None:
        adapter = ArtificialAnalysisAdapter()
        metrics = {
            "intelligence_index": 61.2,
            "median_output_speed": 144.8,
            "price_1m_blended_3_to_1": 18.75,
        }
        raw_record = RawSourceRecord(
            source_id=adapter.source_id,
            benchmark_id="aa_intelligence",
            raw_model_name="Claude Opus 4.6",
            raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
            source_url=adapter.source_url,
            collected_at=FUTURE_COLLECTED_AT,
            raw_model_key="anthropic/claude-opus-4.6",
            payload={"slug": "anthropic/claude-opus-4.6", **metrics},
            metadata={
                "model_creator": "Anthropic",
                "metrics": metrics,
            },
        )

        _, source_run_id, candidates, _ = self._persist_records(adapter, [raw_record])

        candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
        self.assertEqual(
            candidate_values,
            {
                "aa_intelligence": 61.2,
                "aa_speed": 144.8,
                "aa_cost": 18.75,
            },
        )

        intelligence = self._latest_score("claude-opus-4-6", "aa_intelligence")
        speed = self._latest_score("claude-opus-4-6", "aa_speed")
        cost = self._latest_score("claude-opus-4-6", "aa_cost")

        self.assertAlmostEqual(float(intelligence["value"]), 61.2)
        self.assertAlmostEqual(float(speed["value"]), 144.8)
        self.assertAlmostEqual(float(cost["value"]), 18.75)
        self.assertEqual(intelligence["source_type"], "primary")
        self.assertEqual(intelligence["verified"], 1)
        self.assertIn("Artificial Analysis field", str(intelligence["notes"]))

        raw_rows = update_engine.list_raw_source_records(source_run_id)
        self.assertEqual(len(raw_rows), 1)
        self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
        self.assertEqual(raw_rows[0]["resolution_status"], "resolved")

    def test_swebench_spot_check_keeps_best_submission_for_each_model(self) -> None:
        adapter = SwebenchAdapter()
        raw_records = [
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="swebench_verified",
                raw_model_name="Claude Opus 4.6",
                raw_value="0.54",
                source_url=adapter.page_url,
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="Claude Opus 4.6",
                payload={"resolved": 0.54},
                metadata={
                    "verified": True,
                    "leaderboard_name": "Verified",
                    "leaderboard_date": "2026-02-16",
                    "submission_name": "mini-SWE-agent + Claude Opus 4.6",
                    "single_model_submission": True,
                    "tags": ["Model: Claude Opus 4.6"],
                },
            ),
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="swebench_verified",
                raw_model_name="Claude Opus 4.6",
                raw_value="0.61",
                source_url=adapter.page_url,
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="Claude Opus 4.6",
                payload={"resolved": 0.61},
                metadata={
                    "verified": True,
                    "leaderboard_name": "Verified",
                    "leaderboard_date": "2026-02-17",
                    "submission_name": "mini-SWE-agent + Claude Opus 4.6",
                    "single_model_submission": True,
                    "tags": ["Model: Claude Opus 4.6"],
                },
            ),
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="swebench_verified",
                raw_model_name="GPT-5.4 (xhigh)",
                raw_value="0.58",
                source_url=adapter.page_url,
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="GPT-5.4 (xhigh)",
                payload={"resolved": 0.58},
                metadata={
                    "verified": True,
                    "leaderboard_name": "Verified",
                    "leaderboard_date": "2026-02-17",
                    "submission_name": "mini-SWE-agent + GPT-5.4 (xhigh)",
                    "single_model_submission": True,
                    "tags": ["Model: GPT-5.4 (xhigh)"],
                },
            ),
        ]

        _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

        self.assertEqual(len(candidates), 2)
        candidate_values = {candidate.raw_model_name: candidate.value for candidate in candidates}
        self.assertAlmostEqual(candidate_values["Claude Opus 4.6"], 61.0)
        self.assertAlmostEqual(candidate_values["GPT-5.4 (xhigh)"], 58.0)

        claude = self._latest_score("claude-opus-4-6", "swebench_verified")
        gpt = self._latest_score("gpt-5-4", "swebench_verified")
        self.assertAlmostEqual(float(claude["value"]), 61.0)
        self.assertAlmostEqual(float(gpt["value"]), 58.0)
        self.assertEqual(claude["verified"], 1)
        self.assertEqual(claude["source_type"], "secondary")
        self.assertIn("official SWE-bench Verified board", str(claude["notes"]))

        raw_rows = update_engine.list_raw_source_records(source_run_id)
        self.assertEqual(len(raw_rows), 3)
        self.assertTrue(all(row["resolution_status"] == "resolved" for row in raw_rows))
        self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
        self.assertEqual(raw_rows[-1]["normalized_model_id"], "gpt-5-4")
        self.assertTrue(all(row["source_type"] == "secondary" for row in raw_rows))

    def test_ifeval_spot_check_preserves_secondary_trust_labels(self) -> None:
        adapter = IfevalAdapter()
        raw_record = RawSourceRecord(
            source_id=adapter.source_id,
            benchmark_id="ifeval",
            raw_model_name="GPT-5.4 (xhigh)",
            raw_value="0.873",
            source_url=adapter.source_url,
            collected_at=FUTURE_COLLECTED_AT,
            raw_model_key="gpt-5.4",
            payload={"model_id": "gpt-5.4", "score": 0.873},
            metadata={
                "details_url": "https://api.llm-stats.com/leaderboard/benchmarks/ifeval/details",
                "organization_name": "OpenAI",
                "verified": False,
                "self_reported": True,
                "rank": 9,
                "model_id": "gpt-5.4",
            },
        )

        _, source_run_id, candidates, _ = self._persist_records(adapter, [raw_record])

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertAlmostEqual(candidate.value, 87.3)
        self.assertEqual(candidate.source_type, "secondary")
        self.assertFalse(candidate.verified)
        self.assertIn("self-reported", str(candidate.notes))

        score = self._latest_score("gpt-5-4", "ifeval")
        self.assertAlmostEqual(float(score["value"]), 87.3)
        self.assertEqual(score["source_type"], "secondary")
        self.assertEqual(score["verified"], 0)
        self.assertIn("self-reported", str(score["notes"]))

        raw_rows = update_engine.list_raw_source_records(source_run_id)
        self.assertEqual(len(raw_rows), 1)
        self.assertEqual(raw_rows[0]["normalized_model_id"], "gpt-5-4")
        self.assertEqual(raw_rows[0]["source_type"], "secondary")
        self.assertEqual(raw_rows[0]["verified"], 0)

    def test_chatbot_arena_same_run_duplicate_resolution_keeps_single_best_score(self) -> None:
        adapter = ChatbotArenaAdapter()
        raw_records = [
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="chatbot_arena",
                raw_model_name="claude-opus-4-6-thinking",
                raw_value="1504",
                source_url=adapter.source_url,
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="claude-opus-4-6-thinking",
                payload={"modelDisplayName": "claude-opus-4-6-thinking", "rating": 1504.0, "votes": "13,979"},
                metadata={"votes": "13,979"},
            ),
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="chatbot_arena",
                raw_model_name="claude-opus-4-6",
                raw_value="1499",
                source_url=adapter.source_url,
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="claude-opus-4-6",
                payload={"modelDisplayName": "claude-opus-4-6", "rating": 1499.0, "votes": "14,934"},
                metadata={"votes": "14,934"},
            ),
        ]

        log_id, source_run_id, _, _ = self._persist_records(adapter, raw_records)

        with get_connection(self.engine) as conn:
            rows = fetch_all(
                conn,
                select(scores_table)
                .where(scores_table.c.model_id == "claude-opus-4-6")
                .where(scores_table.c.benchmark_id == "chatbot_arena")
                .order_by(scores_table.c.id.asc()),
            )
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows[0]["value"]), 1504.0)

        with patch.object(audit_engine, "MIN_EXPECTED_RECORDS", {}):
            audit_result = audit_engine.run_audit(self.engine, log_id)

        mismatches = [
            finding
            for finding in audit_result["findings"]
            if finding["check_name"] == "source_spot_check_mismatch"
        ]
        self.assertFalse(mismatches)

        raw_rows = update_engine.list_raw_source_records(source_run_id)
        self.assertEqual(len(raw_rows), 2)
        self.assertTrue(all(row["normalized_model_id"] == "claude-opus-4-6" for row in raw_rows))

    def test_runtime_audit_ignores_legacy_primary_swebench_history_when_latest_is_secondary(self) -> None:
        adapter = SwebenchAdapter()
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": "claude-opus-4-6",
                        "benchmark_id": "swebench_verified",
                        "value": 55.0,
                        "raw_value": "55.0",
                        "collected_at": "2026-04-01T00:00:00Z",
                        "source_url": adapter.page_url,
                        "source_type": "primary",
                        "verified": 1,
                        "notes": "Legacy incorrect trust label.",
                    }
                ],
            )

        raw_record = RawSourceRecord(
            source_id=adapter.source_id,
            benchmark_id="swebench_verified",
            raw_model_name="Claude Opus 4.6",
            raw_value="0.61",
            source_url=adapter.page_url,
            collected_at=FUTURE_COLLECTED_AT,
            raw_model_key="Claude Opus 4.6",
            payload={"resolved": 0.61},
            metadata={
                "verified": True,
                "leaderboard_name": "Verified",
                "leaderboard_date": "2026-02-17",
                "submission_name": "mini-SWE-agent + Claude Opus 4.6",
                "single_model_submission": True,
                "tags": ["Model: Claude Opus 4.6"],
            },
        )

        log_id, _, _, _ = self._persist_records(adapter, [raw_record])

        with patch.object(audit_engine, "MIN_EXPECTED_RECORDS", {}):
            audit_result = audit_engine.run_audit(self.engine, log_id)

        swebench_findings = [
            finding
            for finding in audit_result["findings"]
            if finding["check_name"] == "swebench_trust_labeling"
        ]
        self.assertFalse(swebench_findings)

    def test_trust_label_repair_normalizes_legacy_swebench_and_ifeval_rows(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": "claude-opus-4-6",
                        "benchmark_id": "swebench_verified",
                        "value": 55.0,
                        "raw_value": "55.0",
                        "collected_at": "2026-04-01T00:00:00Z",
                        "source_url": "https://www.swebench.com/#verified",
                        "source_type": "primary",
                        "verified": 1,
                        "notes": "Legacy incorrect trust label.",
                    },
                    {
                        "model_id": "gpt-5-4",
                        "benchmark_id": "ifeval",
                        "value": 87.3,
                        "raw_value": "87.3",
                        "collected_at": "2026-04-01T00:00:00Z",
                        "source_url": "https://llm-stats.com/benchmarks/ifeval",
                        "source_type": "primary",
                        "verified": 1,
                        "notes": "Legacy incorrect trust label.",
                    },
                ],
            )

        update_engine._repair_score_trust_labels()

        swebench = self._latest_score("claude-opus-4-6", "swebench_verified")
        ifeval = self._latest_score("gpt-5-4", "ifeval")
        self.assertEqual(swebench["source_type"], "secondary")
        self.assertEqual(swebench["verified"], 1)
        self.assertEqual(ifeval["source_type"], "secondary")
        self.assertEqual(ifeval["verified"], 0)

    def test_runtime_audit_flags_spot_check_mismatch(self) -> None:
        adapter = ArtificialAnalysisAdapter()
        metrics = {
            "intelligence_index": 61.2,
            "median_output_speed": 144.8,
            "price_1m_blended_3_to_1": 18.75,
        }
        raw_record = RawSourceRecord(
            source_id=adapter.source_id,
            benchmark_id="aa_intelligence",
            raw_model_name="Claude Opus 4.6",
            raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
            source_url=adapter.source_url,
            collected_at=FUTURE_COLLECTED_AT,
            raw_model_key="anthropic/claude-opus-4.6",
            payload={"slug": "anthropic/claude-opus-4.6", **metrics},
            metadata={
                "model_creator": "Anthropic",
                "metrics": metrics,
            },
        )

        log_id, _, _, _ = self._persist_records(adapter, [raw_record])

        with self.engine.begin() as conn:
            conn.execute(
                update(scores_table)
                .where(scores_table.c.model_id == "claude-opus-4-6")
                .where(scores_table.c.benchmark_id == "aa_intelligence")
                .values(value=12.0)
            )

        with patch.object(audit_engine, "MIN_EXPECTED_RECORDS", {}):
            audit_result = audit_engine.run_audit(self.engine, log_id)

        mismatch = next(
            (
                finding
                for finding in audit_result["findings"]
                if finding["check_name"] == "source_spot_check_mismatch"
            ),
            None,
        )
        self.assertIsNotNone(mismatch)
        self.assertEqual(mismatch["details"]["model_id"], "claude-opus-4-6")
        self.assertEqual(mismatch["details"]["benchmark_id"], "aa_intelligence")
        self.assertAlmostEqual(float(mismatch["details"]["expected_value"]), 61.2)
        self.assertAlmostEqual(float(mismatch["details"]["actual_value"]), 12.0)


if __name__ == "__main__":
    unittest.main()
