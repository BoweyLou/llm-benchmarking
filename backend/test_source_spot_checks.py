from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select, update

from backend import audit_engine
from backend import update_engine
from backend.database import (
    benchmarks as benchmarks_table,
    fetch_all,
    fetch_one,
    get_connection,
    get_engine,
    init_db,
    model_source_listings as model_source_listings_table,
    models as models_table,
    scores as scores_table,
)
from backend.seed_data import seed_reference_data
from backend.sources.ailuminate import AILuminateAdapter
from backend.sources.artificial_analysis import ArtificialAnalysisAdapter
from backend.sources.artificial_analysis_ifbench import ArtificialAnalysisIfbenchAdapter
from backend.sources.artificial_analysis_tts import ArtificialAnalysisTtsAdapter
from backend.sources.base import RawSourceRecord, SourceFetchResult
from backend.sources.bfcl import BfclAdapter
from backend.sources.bigcodebench import BigCodeBenchAdapter
from backend.sources.chatbot_arena import ChatbotArenaAdapter
from backend.sources.faithjudge import FaithJudgeAdapter
from backend.sources.helm_capabilities import HelmCapabilitiesAdapter
from backend.sources.ifeval import IfevalAdapter
from backend.sources.livebench import LiveBenchAdapter
from backend.sources.livecodebench import LiveCodeBenchAdapter
from backend.sources.mmmu import MmmuAdapter
from backend.sources.mteb import MtebAdapter
from backend.sources.open_asr_leaderboard import OpenAsrLeaderboardAdapter
from backend.sources.ragtruth import RagtruthAdapter
from backend.sources.swebench import SwebenchAdapter
from backend.sources.taubench import TaubenchAdapter
from backend.sources.terminal_bench import TerminalBenchAdapter
from backend.sources.vectara_hallucination import VectaraHallucinationAdapter

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

    def test_mteb_spot_check_persists_embedding_and_reranker_scores(self) -> None:
        adapter = MtebAdapter()
        raw_records = [
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="mteb_retrieval",
                raw_model_name="BAAI/bge-large-en-v1.5",
                raw_value="38.061",
                source_url="https://raw.githubusercontent.com/embeddings-benchmark/results/main/results/BAAI__bge-large-en-v1.5/rev/NFCorpus.json",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="BAAI/bge-large-en-v1.5",
                payload={"task_name": "NFCorpus", "scores": {"test": [{"main_score": 0.38061}]}},
                metadata={
                    "model_provider": "BAAI",
                    "model_roles": ["embedding"],
                    "task_category": "retrieval",
                    "task_name": "NFCorpus",
                    "languages": ["eng-Latn"],
                },
            ),
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="mteb_reranking",
                raw_model_name="BAAI/bge-large-en-v1.5",
                raw_value="32.4653",
                source_url="https://raw.githubusercontent.com/embeddings-benchmark/results/main/results/BAAI__bge-large-en-v1.5/rev/VoyageMMarcoReranking.json",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="BAAI/bge-large-en-v1.5",
                payload={"task_name": "VoyageMMarcoReranking", "scores": {"test": [{"main_score": 0.324653}]}},
                metadata={
                    "model_provider": "BAAI",
                    "model_roles": ["reranker"],
                    "task_category": "reranking",
                    "task_name": "VoyageMMarcoReranking",
                    "languages": ["jpn-Jpan"],
                },
            ),
        ]

        _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

        candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
        self.assertEqual(set(candidate_values), {"mteb_retrieval", "mteb_reranking", "mteb_retrieval_reranking"})
        self.assertAlmostEqual(candidate_values["mteb_retrieval"], 38.061)
        self.assertAlmostEqual(candidate_values["mteb_reranking"], 32.4653)
        self.assertAlmostEqual(candidate_values["mteb_retrieval_reranking"], 35.2631)

        with get_connection(self.engine) as conn:
            model_row = fetch_one(
                conn,
                select(models_table).where(models_table.c.name == "BAAI/bge-large-en-v1.5"),
            )
        self.assertIsNotNone(model_row)
        model_id = str(model_row["id"])
        self.assertEqual(json.loads(str(model_row["model_roles_json"])), ["embedding", "reranker"])

        retrieval = self._latest_score(model_id, "mteb_retrieval")
        reranking = self._latest_score(model_id, "mteb_reranking")
        blended = self._latest_score(model_id, "mteb_retrieval_reranking")

        self.assertAlmostEqual(float(retrieval["value"]), 38.061)
        self.assertAlmostEqual(float(reranking["value"]), 32.4653)
        self.assertAlmostEqual(float(blended["value"]), 35.2631)
        self.assertIn("Official MTEB retrieval", str(retrieval["notes"]))

        raw_rows = update_engine.list_raw_source_records(source_run_id)
        self.assertEqual(len(raw_rows), 2)
        self.assertTrue(all(row["resolution_status"] == "resolved" for row in raw_rows))

    def test_open_asr_spot_check_persists_speech_to_text_scores(self) -> None:
        adapter = OpenAsrLeaderboardAdapter()
        raw_records = [
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="asr_english_short_wer",
                raw_model_name="nvidia/parakeet-tdt-0.6b-v3",
                raw_value="8.5",
                source_url="https://huggingface.co/datasets/hf-audio/open-asr-leaderboard-results",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="nvidia/parakeet-tdt-0.6b-v3",
                payload={"RTFx": "920.4", "AMI WER": "10.0", "LS Clean WER": "7.0"},
                metadata={
                    "model_provider": "NVIDIA",
                    "model_roles": ["speech_to_text"],
                    "capabilities": ["automatic-speech-recognition", "speech-to-text"],
                    "asr_split": "english_short",
                    "asr_split_label": "English short-form",
                },
            ),
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="asr_multilingual_wer",
                raw_model_name="nvidia/parakeet-tdt-0.6b-v3",
                raw_value="11.25",
                source_url="https://huggingface.co/datasets/Steveeeeeeen/multilingual_evals",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="nvidia/parakeet-tdt-0.6b-v3",
                payload={"RTFx": "875.2", "Avg": "11.25"},
                metadata={
                    "model_provider": "NVIDIA",
                    "model_roles": ["speech_to_text"],
                    "capabilities": ["automatic-speech-recognition", "speech-to-text"],
                    "asr_split": "multilingual",
                    "asr_split_label": "Multilingual",
                },
            ),
        ]

        _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

        candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
        self.assertEqual(
            set(candidate_values),
            {"asr_english_short_wer", "asr_multilingual_wer", "asr_realtime_factor"},
        )
        self.assertAlmostEqual(candidate_values["asr_english_short_wer"], 8.5)
        self.assertAlmostEqual(candidate_values["asr_multilingual_wer"], 11.25)
        self.assertAlmostEqual(candidate_values["asr_realtime_factor"], 920.4)

        with get_connection(self.engine) as conn:
            model_row = fetch_one(
                conn,
                select(models_table).where(models_table.c.name == "nvidia/parakeet-tdt-0.6b-v3"),
            )
        self.assertIsNotNone(model_row)
        model_id = str(model_row["id"])
        self.assertEqual(json.loads(str(model_row["model_roles_json"])), ["speech_to_text"])

        english = self._latest_score(model_id, "asr_english_short_wer")
        multilingual = self._latest_score(model_id, "asr_multilingual_wer")
        rtfx = self._latest_score(model_id, "asr_realtime_factor")
        self.assertAlmostEqual(float(english["value"]), 8.5)
        self.assertAlmostEqual(float(multilingual["value"]), 11.25)
        self.assertAlmostEqual(float(rtfx["value"]), 920.4)
        self.assertIn("Open ASR Leaderboard", str(english["notes"]))

        raw_rows = update_engine.list_raw_source_records(source_run_id)
        self.assertEqual(len(raw_rows), 2)
        self.assertTrue(all(row["resolution_status"] == "resolved" for row in raw_rows))

    def test_artificial_analysis_tts_parser_extracts_quality_price_and_generation_time(self) -> None:
        adapter = ArtificialAnalysisTtsAdapter()
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Dataset","name":"Text to Speech Arena Quality Elo","data":[{"label":"Gemini 3.1 Flash TTS","qualityElo":1213.26,"detailsUrl":"/text-to-speech/providers/gemini-3-1-tts"}]}
        </script>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Dataset","name":"Price","data":[{"label":"Gemini 3.1 Flash TTS, Google","pricePer1mCharacters":18.31,"detailsUrl":"/text-to-speech/models/gemini-3-1-tts"}]}
        </script>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Dataset","name":"Characters Per Second","data":[{"label":"Gemini 3.1 Flash TTS, Google","charactersPerSecond":250.0,"detailsUrl":"/text-to-speech/providers/gemini-3-1-tts"}]}
        </script>
        </head></html>
        """

        entries = adapter._entries_from_datasets(adapter._extract_datasets(html))
        raw_records = adapter._build_raw_records(entries, fetched_at=FUTURE_COLLECTED_AT)
        candidates = adapter.normalize(raw_records)

        self.assertEqual(len(raw_records), 1)
        self.assertEqual(raw_records[0].raw_model_name, "Gemini 3.1 Flash TTS")
        self.assertEqual(raw_records[0].metadata["model_roles"], ["text_to_speech"])
        candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
        self.assertAlmostEqual(candidate_values["aa_tts_quality_elo"], 1213.26)
        self.assertAlmostEqual(candidate_values["aa_tts_price_per_1m_chars"], 18.31)
        self.assertAlmostEqual(candidate_values["aa_tts_generation_time"], 2.0)

    def test_artificial_analysis_tts_spot_check_persists_text_to_speech_scores(self) -> None:
        adapter = ArtificialAnalysisTtsAdapter()
        raw_records = [
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="aa_tts_quality_elo",
                raw_model_name="Gemini 3.1 Flash TTS",
                raw_value=json.dumps(
                    {
                        "generation_time_seconds": 2.0,
                        "price_per_1m_chars": 18.31,
                        "quality_elo": 1213.26,
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                source_url="https://artificialanalysis.ai/text-to-speech/models",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="gemini-3-1-flash-tts",
                payload={"metrics": {"quality_elo": 1213.26}},
                metadata={
                    "model_creator": "Google",
                    "model_roles": ["text_to_speech"],
                    "capabilities": ["text-to-speech", "speech-synthesis", "speech-output"],
                    "metrics": {
                        "generation_time_seconds": 2.0,
                        "price_per_1m_chars": 18.31,
                        "quality_elo": 1213.26,
                    },
                    "metric_source_urls": {
                        "generation_time_seconds": "https://artificialanalysis.ai/text-to-speech/providers/gemini-3-1-tts",
                        "price_per_1m_chars": "https://artificialanalysis.ai/text-to-speech/models/gemini-3-1-tts",
                        "quality_elo": "https://artificialanalysis.ai/text-to-speech/providers/gemini-3-1-tts",
                    },
                    "release_date": "2026-04-15",
                },
            ),
        ]

        _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

        candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
        self.assertEqual(
            set(candidate_values),
            {"aa_tts_generation_time", "aa_tts_price_per_1m_chars", "aa_tts_quality_elo"},
        )
        self.assertAlmostEqual(candidate_values["aa_tts_quality_elo"], 1213.26)
        self.assertAlmostEqual(candidate_values["aa_tts_generation_time"], 2.0)
        self.assertAlmostEqual(candidate_values["aa_tts_price_per_1m_chars"], 18.31)

        with get_connection(self.engine) as conn:
            model_row = fetch_one(
                conn,
                select(models_table).where(models_table.c.name == "Gemini 3.1 Flash TTS"),
            )
        self.assertIsNotNone(model_row)
        model_id = str(model_row["id"])
        self.assertEqual(json.loads(str(model_row["model_roles_json"])), ["text_to_speech"])
        self.assertEqual(model_row["provider"], "Google")

        quality = self._latest_score(model_id, "aa_tts_quality_elo")
        generation_time = self._latest_score(model_id, "aa_tts_generation_time")
        price = self._latest_score(model_id, "aa_tts_price_per_1m_chars")
        self.assertAlmostEqual(float(quality["value"]), 1213.26)
        self.assertAlmostEqual(float(generation_time["value"]), 2.0)
        self.assertAlmostEqual(float(price["value"]), 18.31)

        raw_rows = update_engine.list_raw_source_records(source_run_id)
        self.assertEqual(len(raw_rows), 1)
        self.assertTrue(all(row["resolution_status"] == "resolved" for row in raw_rows))

    def test_mteb_spot_check_persists_rteb_finance_scores(self) -> None:
        adapter = MtebAdapter()
        raw_records = [
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="rteb_finance",
                raw_model_name="BAAI/bge-m3",
                raw_value="66.529",
                source_url="https://huggingface.co/spaces/mteb/leaderboard?benchmark_name=RTEB%28fin%2C%20beta%29",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="BAAI/bge-m3",
                payload={
                    "model_name": "BAAI/bge-m3",
                    "task_name": "FinanceBenchRetrieval",
                    "score": 0.66529,
                    "is_public": True,
                },
                metadata={
                    "model_provider": "BAAI",
                    "model_roles": ["embedding"],
                    "task_category": "retrieval",
                    "benchmark_group": "RTEB(fin, beta)",
                    "benchmark_name": "RTEB Finance",
                    "task_name": "FinanceBenchRetrieval",
                    "languages": ["eng-Latn"],
                    "is_public": True,
                    "trained_on": False,
                },
            ),
            RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="rteb_finance",
                raw_model_name="BAAI/bge-m3",
                raw_value="72.033",
                source_url="https://huggingface.co/spaces/mteb/leaderboard?benchmark_name=RTEB%28fin%2C%20beta%29",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="BAAI/bge-m3",
                payload={
                    "model_name": "BAAI/bge-m3",
                    "task_name": "EnglishFinance1Retrieval",
                    "score": 0.72033,
                    "is_public": False,
                },
                metadata={
                    "model_provider": "BAAI",
                    "model_roles": ["embedding"],
                    "task_category": "retrieval",
                    "benchmark_group": "RTEB(fin, beta)",
                    "benchmark_name": "RTEB Finance",
                    "task_name": "EnglishFinance1Retrieval",
                    "languages": ["eng-Latn"],
                    "is_public": False,
                    "trained_on": False,
                },
            ),
        ]

        _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

        self.assertEqual([candidate.benchmark_id for candidate in candidates], ["rteb_finance"])
        self.assertAlmostEqual(candidates[0].value, 69.281)
        self.assertEqual(candidates[0].metadata["private_row_count"], 1)
        self.assertIn("RTEB Finance", str(candidates[0].notes))

        with get_connection(self.engine) as conn:
            model_row = fetch_one(
                conn,
                select(models_table).where(models_table.c.name == "BAAI/bge-m3"),
            )
        self.assertIsNotNone(model_row)
        model_id = str(model_row["id"])
        self.assertEqual(json.loads(str(model_row["model_roles_json"])), ["embedding"])

        finance = self._latest_score(model_id, "rteb_finance")
        self.assertAlmostEqual(float(finance["value"]), 69.281)
        self.assertIn("closed/private", str(finance["notes"]))

        raw_rows = update_engine.list_raw_source_records(source_run_id)
        self.assertEqual(len(raw_rows), 2)
        self.assertTrue(all(row["resolution_status"] == "resolved" for row in raw_rows))

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
                    "release_date": "2026-02-05",
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

            with get_connection(self.engine) as conn:
                model_row = fetch_one(
                    conn,
                    select(models_table).where(models_table.c.id == "claude-opus-4-6"),
                )
            self.assertIsNotNone(model_row)
            self.assertEqual(model_row["release_date"], "2026-02-05")
            self.assertEqual(model_row["release_date_precision"], "day")
            self.assertEqual(model_row["release_date_confidence"], "high")
            self.assertEqual(model_row["release_date_source_name"], "Artificial Analysis")
            self.assertEqual(model_row["release_date_source_url"], adapter.source_url)

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
            self.assertEqual(raw_rows[0]["resolution_status"], "resolved")

    def test_ailuminate_spot_check_persists_locale_and_system_class_metrics(self) -> None:
            adapter = AILuminateAdapter()
            raw_records = [
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="ailuminate",
                    raw_model_name="Claude Opus 4.6",
                    raw_value="Good",
                    source_url=adapter.source_url,
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={
                        "locale": "en_us",
                        "system_class": "AI Systems",
                        "grade_label": "Good",
                        "risk_ordinal": 3,
                    },
                    metadata={
                        "page_url": adapter.source_url,
                        "locale": "en_us",
                        "benchmark_version": "1.0-en_us-official-ensemble",
                        "system_class": "AI Systems",
                        "detail_url": f"{adapter.source_url}/claude-opus-4-6",
                        "risk_ordinal": 3,
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="ailuminate",
                    raw_model_name="Claude Opus 4.6",
                    raw_value="Very Good",
                    source_url="https://ailuminate.mlcommons.org/benchmarks/general_purpose_ai_chat/1.0-fr_fr-official-ensemble",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={
                        "locale": "fr_fr",
                        "system_class": "AI Systems",
                        "grade_label": "Very Good",
                        "risk_ordinal": 4,
                    },
                    metadata={
                        "page_url": "https://ailuminate.mlcommons.org/benchmarks/general_purpose_ai_chat/1.0-fr_fr-official-ensemble",
                        "locale": "fr_fr",
                        "benchmark_version": "1.0-fr_fr-official-ensemble",
                        "system_class": "AI Systems",
                        "detail_url": "https://ailuminate.mlcommons.org/benchmarks/general_purpose_ai_chat/1.0-fr_fr-official-ensemble/claude-opus-4-6",
                        "risk_ordinal": 4,
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="ailuminate",
                    raw_model_name="Claude Opus 4.6",
                    raw_value="Fair",
                    source_url=adapter.source_url,
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={
                        "locale": "en_us",
                        "system_class": "Bare Models",
                        "grade_label": "Fair",
                        "risk_ordinal": 2,
                    },
                    metadata={
                        "page_url": adapter.source_url,
                        "locale": "en_us",
                        "benchmark_version": "1.0-en_us-official-ensemble",
                        "system_class": "Bare Models",
                        "detail_url": f"{adapter.source_url}/claude-opus-4-6-bare",
                        "risk_ordinal": 2,
                    },
                ),
            ]

            _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

            candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
            self.assertEqual(
                candidate_values,
                {
                    "ailuminate": 75.0,
                    "ailuminate_ai_systems": 75.0,
                    "ailuminate_bare_models": 25.0,
                    "ailuminate_en_us": 50.0,
                    "ailuminate_fr_fr": 75.0,
                },
            )

            locale_candidate = next(candidate for candidate in candidates if candidate.benchmark_id == "ailuminate_en_us")
            self.assertEqual(locale_candidate.metadata["score_scope"], "locale")
            self.assertEqual(locale_candidate.metadata["locale"], "en_us")
            self.assertEqual(locale_candidate.metadata["system_class"], "AI Systems")
            self.assertIn("Risk ordinal: 3", str(locale_candidate.notes))

            system_candidate = next(candidate for candidate in candidates if candidate.benchmark_id == "ailuminate_bare_models")
            self.assertEqual(system_candidate.metadata["score_scope"], "system_class")
            self.assertEqual(system_candidate.metadata["system_class"], "Bare Models")

            for benchmark_id, expected_value in candidate_values.items():
                score = self._latest_score("claude-opus-4-6", benchmark_id)
                self.assertAlmostEqual(float(score["value"]), expected_value)
                self.assertEqual(score["source_type"], "primary")
                self.assertEqual(score["verified"], 1)

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 3)
            self.assertTrue(all(row["normalized_model_id"] == "claude-opus-4-6" for row in raw_rows))
            raw_notes = [json.loads(str(row["notes"])) for row in raw_rows]
            self.assertEqual({note["locale"] for note in raw_notes}, {"en_us", "fr_fr"})
            self.assertEqual({note["system_class"] for note in raw_notes}, {"AI Systems", "Bare Models"})
            self.assertEqual({note["risk_ordinal"] for note in raw_notes}, {2, 3, 4})

    def test_artificial_analysis_ifbench_spot_check_persists_score_efficiency_metrics(self) -> None:
            adapter = ArtificialAnalysisIfbenchAdapter()
            raw_records = adapter._build_raw_records(
                [
                    {
                        "name": "IFBench Benchmark Leaderboard: Score",
                        "data": [
                            {
                                "label": "Claude Opus 4.6",
                                "IFBench Benchmark Leaderboard": 0.8125,
                                "detailsUrl": "/models/claude-opus-4-6",
                            }
                        ],
                    },
                    {
                        "name": "IFBench Benchmark Leaderboard: Output Tokens per Task",
                        "data": [
                            {
                                "label": "Claude Opus 4.6",
                                "answer": 110.0,
                                "reasoning": 240.5,
                                "detailsUrl": "/models/claude-opus-4-6",
                            }
                        ],
                    },
                    {
                        "name": "IFBench Benchmark Leaderboard: Cost per Task",
                        "data": [
                            {
                                "label": "Claude Opus 4.6",
                                "answer": 0.012,
                                "reasoning": 0.034,
                                "cacheWrite": 0.001,
                                "cacheHit": 0.002,
                                "input": 0.003,
                                "detailsUrl": "/models/claude-opus-4-6",
                            }
                        ],
                    },
                    {
                        "name": "IFBench Benchmark Leaderboard: Time per Task",
                        "data": [
                            {
                                "label": "Claude Opus 4.6",
                                "IFBench Benchmark Leaderboard time per task": 0.75,
                                "detailsUrl": "/models/claude-opus-4-6",
                            }
                        ],
                    },
                ],
                fetched_at=FUTURE_COLLECTED_AT,
            )

            _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

            candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
            self.assertEqual(
                set(candidate_values),
                {"aa_ifbench", "aa_ifbench_cost", "aa_ifbench_output_tokens", "aa_ifbench_time"},
            )
            self.assertAlmostEqual(candidate_values["aa_ifbench"], 81.25)
            self.assertAlmostEqual(candidate_values["aa_ifbench_cost"], 0.052)
            self.assertAlmostEqual(candidate_values["aa_ifbench_output_tokens"], 350.5)
            self.assertAlmostEqual(candidate_values["aa_ifbench_time"], 0.75)

            score_candidate = next(candidate for candidate in candidates if candidate.benchmark_id == "aa_ifbench")
            self.assertEqual(score_candidate.raw_model_key, "claude-opus-4-6")
            self.assertEqual(score_candidate.metadata["metric"], "score_percent")
            self.assertEqual(score_candidate.metadata["details_url"], "https://artificialanalysis.ai/models/claude-opus-4-6")

            cost_candidate = next(candidate for candidate in candidates if candidate.benchmark_id == "aa_ifbench_cost")
            self.assertEqual(cost_candidate.metadata["metric_group"], "cost")
            self.assertAlmostEqual(cost_candidate.metadata["metrics"]["cost_per_task_usd"], 0.052)

            for benchmark_id, expected_value in candidate_values.items():
                score = self._latest_score("claude-opus-4-6", benchmark_id)
                self.assertAlmostEqual(float(score["value"]), expected_value)
                self.assertEqual(score["source_type"], "primary")
                self.assertEqual(score["verified"], 1)
                self.assertIn("Artificial Analysis IFBench field", str(score["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
            raw_notes = json.loads(str(raw_rows[0]["notes"]))
            self.assertEqual(raw_notes["evaluation"], "IFBench")
            self.assertEqual(raw_notes["metrics"]["output_tokens_per_task"], 350.5)
            self.assertAlmostEqual(raw_notes["metrics"]["score_fraction"], 0.8125)

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

    def test_terminal_bench_spot_check_preserves_agent_harness_evidence(self) -> None:
            adapter = TerminalBenchAdapter()
            raw_records = [
                adapter._build_raw_record(
                    {
                        "agent": "Terminus",
                        "agentName": "Terminus",
                        "agentVersion": "2.3.1",
                        "agentOrganization": "Acme Agents",
                        "model": ["Claude Opus 4.6"],
                        "modelNames": ["Claude Opus 4.6"],
                        "modelOrganization": ["Anthropic"],
                        "modelProviders": ["Anthropic"],
                        "accuracy": 0.621,
                        "stderr": 0.012,
                        "integrationMethod": "Anthropic Messages API",
                        "date": "2026-06-15",
                        "rank": 3,
                        "verified": True,
                        "key": "terminus__claude-opus-4-6",
                    },
                    fetched_at=FUTURE_COLLECTED_AT,
                ),
                adapter._build_raw_record(
                    {
                        "agent": "Multiple",
                        "agentName": "Multiple",
                        "agentVersion": "system",
                        "agentOrganization": "Benchmark Lab",
                        "model": ["Claude Opus 4.6", "GPT-5.4"],
                        "modelNames": ["Claude Opus 4.6", "GPT-5.4"],
                        "modelOrganization": ["Multiple"],
                        "modelProviders": ["Anthropic", "OpenAI"],
                        "accuracy": 0.7,
                        "stderr": 0.009,
                        "integrationMethod": "Mixed harness",
                        "date": "2026-06-16",
                        "rank": 1,
                        "verified": True,
                        "key": "mixed-agent-system",
                    },
                    fetched_at=FUTURE_COLLECTED_AT,
                ),
            ]

            _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

            self.assertEqual(len(candidates), 1)
            candidate = candidates[0]
            self.assertEqual(candidate.raw_model_name, "Claude Opus 4.6")
            self.assertAlmostEqual(candidate.value, 62.1)
            self.assertEqual(candidate.source_type, "secondary")
            self.assertTrue(candidate.verified)
            self.assertIn("Terminus v2.3.1", str(candidate.notes))
            self.assertIn("Anthropic Messages API", str(candidate.notes))

            score = self._latest_score("claude-opus-4-6", "terminal_bench")
            self.assertAlmostEqual(float(score["value"]), 62.1)
            self.assertEqual(score["source_type"], "secondary")
            self.assertEqual(score["verified"], 1)
            self.assertIn("best verified single-model Terminal-Bench submission", str(score["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 2)

            resolved = next(row for row in raw_rows if row["raw_model_name"] == "Claude Opus 4.6")
            resolved_notes = json.loads(str(resolved["notes"]))
            resolved_payload = json.loads(str(resolved["payload_json"]))
            self.assertEqual(resolved["normalized_model_id"], "claude-opus-4-6")
            self.assertEqual(resolved["resolution_status"], "resolved")
            self.assertEqual(resolved_notes["agent"], "Terminus")
            self.assertEqual(resolved_notes["agent_version"], "2.3.1")
            self.assertEqual(resolved_notes["integration_method"], "Anthropic Messages API")
            self.assertEqual(resolved_notes["stderr"], 0.012)
            self.assertTrue(resolved_notes["agent_system_evidence"])
            self.assertEqual(resolved_notes["score_scope"], "model_capability_from_agent_system_run")
            self.assertEqual(resolved_payload["agentOrganization"], "Acme Agents")

            aggregate = next(row for row in raw_rows if row["raw_model_name"] == "Multiple (multiple models)")
            aggregate_notes = json.loads(str(aggregate["notes"]))
            self.assertIsNone(aggregate["normalized_model_id"])
            self.assertEqual(aggregate["resolution_status"], "skipped_aggregate")
            self.assertTrue(aggregate_notes["aggregate_submission"])
            self.assertEqual(aggregate_notes["integration_method"], "Mixed harness")

    def test_swebench_spot_check_persists_additional_split_scores(self) -> None:
            adapter = SwebenchAdapter()
            raw_records = [
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
                        "tags": ["Model: Claude Opus 4.6", "Org: Test Lab", "System: Attempts - 1"],
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="swebench_lite",
                    raw_model_name="Claude Opus 4.6",
                    raw_value="0.44",
                    source_url="https://www.swebench.com/#lite",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={"resolved": 0.44},
                    metadata={
                        "verified": True,
                        "leaderboard_name": "Lite",
                        "leaderboard_date": "2026-02-16",
                        "submission_name": "older Lite submission",
                        "single_model_submission": True,
                        "tags": ["Model: Claude Opus 4.6"],
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="swebench_lite",
                    raw_model_name="Claude Opus 4.6",
                    raw_value="0.48",
                    source_url="https://www.swebench.com/#lite",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={"resolved": 0.48},
                    metadata={
                        "verified": True,
                        "leaderboard_name": "Lite",
                        "leaderboard_date": "2026-02-17",
                        "submission_name": "better Lite submission",
                        "single_model_submission": True,
                        "tags": ["Model: Claude Opus 4.6"],
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="swebench_multilingual",
                    raw_model_name="Claude Opus 4.6",
                    raw_value="0.72",
                    source_url="https://www.swebench.com/#multilingual",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={"resolved": 0.72},
                    metadata={
                        "verified": True,
                        "leaderboard_name": "Multilingual",
                        "leaderboard_date": "2026-02-18",
                        "submission_name": "multilingual submission",
                        "single_model_submission": True,
                        "tags": ["Model: Claude Opus 4.6"],
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="swebench_full",
                    raw_model_name="GPT-5.4 (xhigh)",
                    raw_value="0.52",
                    source_url="https://www.swebench.com/#full",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="GPT-5.4 (xhigh)",
                    payload={"resolved": 0.52},
                    metadata={
                        "verified": True,
                        "leaderboard_name": "Full",
                        "leaderboard_date": "2026-02-18",
                        "submission_name": "full submission",
                        "single_model_submission": True,
                        "tags": ["Model: GPT-5.4 (xhigh)"],
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="swebench_multimodal",
                    raw_model_name="GPT-5.4 (xhigh)",
                    raw_value="0.35",
                    source_url="https://www.swebench.com/#multimodal",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="GPT-5.4 (xhigh)",
                    payload={"resolved": 0.35},
                    metadata={
                        "verified": True,
                        "leaderboard_name": "Multimodal",
                        "leaderboard_date": "2026-02-18",
                        "submission_name": "multimodal submission",
                        "single_model_submission": True,
                        "tags": ["Model: GPT-5.4 (xhigh)"],
                    },
                ),
            ]

            _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

            candidate_values = {(candidate.raw_model_name, candidate.benchmark_id): candidate.value for candidate in candidates}
            self.assertEqual(len(candidates), 5)
            self.assertAlmostEqual(candidate_values[("Claude Opus 4.6", "swebench_verified")], 61.0)
            self.assertAlmostEqual(candidate_values[("Claude Opus 4.6", "swebench_lite")], 48.0)
            self.assertAlmostEqual(candidate_values[("Claude Opus 4.6", "swebench_multilingual")], 72.0)
            self.assertAlmostEqual(candidate_values[("GPT-5.4 (xhigh)", "swebench_full")], 52.0)
            self.assertAlmostEqual(candidate_values[("GPT-5.4 (xhigh)", "swebench_multimodal")], 35.0)

            claude_lite = self._latest_score("claude-opus-4-6", "swebench_lite")
            claude_multilingual = self._latest_score("claude-opus-4-6", "swebench_multilingual")
            gpt_full = self._latest_score("gpt-5-4", "swebench_full")
            gpt_multimodal = self._latest_score("gpt-5-4", "swebench_multimodal")
            self.assertAlmostEqual(float(claude_lite["value"]), 48.0)
            self.assertIn("official SWE-bench Lite board", str(claude_lite["notes"]))
            self.assertAlmostEqual(float(claude_multilingual["value"]), 72.0)
            self.assertIn("official SWE-bench Multilingual board", str(claude_multilingual["notes"]))
            self.assertAlmostEqual(float(gpt_full["value"]), 52.0)
            self.assertIn("official SWE-bench Full board", str(gpt_full["notes"]))
            self.assertAlmostEqual(float(gpt_multimodal["value"]), 35.0)
            self.assertIn("official SWE-bench Multimodal board", str(gpt_multimodal["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 6)
            self.assertTrue(all(row["source_type"] == "secondary" for row in raw_rows))
            raw_notes = [json.loads(str(row["notes"])) for row in raw_rows]
            self.assertEqual(
                {note["leaderboard_name"] for note in raw_notes},
                {"Verified", "Lite", "Multilingual", "Full", "Multimodal"},
            )

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

    def test_vectara_spot_check_persists_companion_metrics(self) -> None:
            adapter = VectaraHallucinationAdapter()
            raw_record = RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="rag_groundedness",
                raw_model_name="Claude Opus 4.6",
                raw_value="98.2",
                source_url=adapter.source_url,
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="Claude Opus 4.6",
                payload={
                    "table_row": "| Claude Opus 4.6 | 1.8% | 98.2% | 94.3% | 71 |",
                },
                metadata={
                    "rank": 1,
                    "hallucination_rate": 1.8,
                    "factual_consistency_rate": 98.2,
                    "answer_rate": 94.3,
                    "average_summary_length_words": 71.0,
                },
            )

            _, source_run_id, candidates, _ = self._persist_records(adapter, [raw_record])

            candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
            self.assertEqual(
                candidate_values,
                {
                    "rag_groundedness": 98.2,
                    "rag_hallucination_rate": 1.8,
                    "rag_answer_rate": 94.3,
                },
            )

            groundedness = self._latest_score("claude-opus-4-6", "rag_groundedness")
            hallucination = self._latest_score("claude-opus-4-6", "rag_hallucination_rate")
            answer = self._latest_score("claude-opus-4-6", "rag_answer_rate")

            self.assertAlmostEqual(float(groundedness["value"]), 98.2)
            self.assertAlmostEqual(float(hallucination["value"]), 1.8)
            self.assertAlmostEqual(float(answer["value"]), 94.3)
            self.assertIn("Lower is better", str(hallucination["notes"]))
            self.assertIn("Coverage signal", str(answer["notes"]))

            with get_connection(self.engine) as conn:
                benchmark_rows = fetch_all(
                    conn,
                    select(benchmarks_table.c.id, benchmarks_table.c.higher_is_better).where(
                        benchmarks_table.c.id.in_(["rag_hallucination_rate", "rag_answer_rate"])
                    ),
                )
            direction_by_id = {row["id"]: row["higher_is_better"] for row in benchmark_rows}
            self.assertEqual(direction_by_id["rag_hallucination_rate"], 0)
            self.assertEqual(direction_by_id["rag_answer_rate"], 1)

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
            self.assertEqual(raw_rows[0]["resolution_status"], "resolved")

    def test_faithjudge_spot_check_persists_task_metrics(self) -> None:
            adapter = FaithJudgeAdapter()
            raw_record = RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="rag_task_faithfulness",
                raw_model_name="Claude Opus 4.6",
                raw_value="4.25",
                source_url=adapter.source_url,
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="Claude Opus 4.6",
                payload={
                    "table_row": "| 1 | [Claude Opus 4.6](https://example.test/model) | Anthropic | n/a | 4.25% | 2.00% | 3.50% | 6.00% | 5.50% |",
                },
                metadata={
                    "rank": "1",
                    "organization": "Anthropic",
                    "parameters": "n/a",
                    "model_url": "https://example.test/model",
                    "overall_hallucination_rate": 4.25,
                    "faithbench_summarization": 2.0,
                    "ragtruth_summarization": 3.5,
                    "ragtruth_question_answering": 6.0,
                    "ragtruth_data_to_text": 5.5,
                },
            )

            _, source_run_id, candidates, _ = self._persist_records(adapter, [raw_record])

            candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
            self.assertEqual(
                candidate_values,
                {
                    "rag_task_faithfulness": 4.25,
                    "faithjudge_faithbench_summarization": 2.0,
                    "faithjudge_ragtruth_summarization": 3.5,
                    "faithjudge_ragtruth_question_answering": 6.0,
                    "faithjudge_ragtruth_data_to_text": 5.5,
                },
            )

            aggregate = self._latest_score("claude-opus-4-6", "rag_task_faithfulness")
            qa = self._latest_score("claude-opus-4-6", "faithjudge_ragtruth_question_answering")
            data_to_text = self._latest_score("claude-opus-4-6", "faithjudge_ragtruth_data_to_text")
            self.assertAlmostEqual(float(aggregate["value"]), 4.25)
            self.assertAlmostEqual(float(qa["value"]), 6.0)
            self.assertAlmostEqual(float(data_to_text["value"]), 5.5)
            self.assertIn("Lower is better", str(qa["notes"]))

            new_ids = [
                "faithjudge_faithbench_summarization",
                "faithjudge_ragtruth_summarization",
                "faithjudge_ragtruth_question_answering",
                "faithjudge_ragtruth_data_to_text",
            ]
            with get_connection(self.engine) as conn:
                benchmark_rows = fetch_all(
                    conn,
                    select(benchmarks_table.c.id, benchmarks_table.c.higher_is_better).where(
                        benchmarks_table.c.id.in_(new_ids)
                    ),
                )
            direction_by_id = {row["id"]: row["higher_is_better"] for row in benchmark_rows}
            self.assertEqual(direction_by_id, {benchmark_id: 0 for benchmark_id in new_ids})

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
            self.assertEqual(raw_rows[0]["resolution_status"], "resolved")

    def test_mmmu_spot_check_persists_companion_metrics_and_pro_only_rows(self) -> None:
            adapter = MmmuAdapter()
            raw_records = [
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="mmmu",
                    raw_model_name="Claude Opus 4.6",
                    raw_value="72.4",
                    source_url=adapter.source_url,
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={},
                    metadata={
                        "info_type": "proprietary",
                        "validation_overall": "72.4",
                        "validation_source": "author",
                        "test_overall": "74.1",
                        "test_source": "official",
                        "pro_overall": "68.5",
                        "pro_source": "author",
                        "date": "2026-02-05",
                        "size": "-",
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="mmmu_pro",
                    raw_model_name="GPT-5.4 (xhigh)",
                    raw_value="70.5",
                    source_url=adapter.source_url,
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="GPT-5.4 (xhigh)",
                    payload={},
                    metadata={
                        "info_type": "proprietary",
                        "validation_overall": None,
                        "test_overall": None,
                        "pro_overall": "70.5",
                        "pro_source": "author",
                        "date": "2026-03-01",
                        "size": "-",
                    },
                ),
            ]

            _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

            candidate_values = {
                (candidate.raw_model_name, candidate.benchmark_id): candidate.value for candidate in candidates
            }
            self.assertEqual(
                candidate_values,
                {
                    ("Claude Opus 4.6", "mmmu"): 72.4,
                    ("Claude Opus 4.6", "mmmu_test"): 74.1,
                    ("Claude Opus 4.6", "mmmu_pro"): 68.5,
                    ("GPT-5.4 (xhigh)", "mmmu_pro"): 70.5,
                },
            )

            claude_validation = self._latest_score("claude-opus-4-6", "mmmu")
            claude_test = self._latest_score("claude-opus-4-6", "mmmu_test")
            claude_pro = self._latest_score("claude-opus-4-6", "mmmu_pro")
            gpt_pro = self._latest_score("gpt-5-4", "mmmu_pro")
            self.assertAlmostEqual(float(claude_validation["value"]), 72.4)
            self.assertAlmostEqual(float(claude_test["value"]), 74.1)
            self.assertAlmostEqual(float(claude_pro["value"]), 68.5)
            self.assertAlmostEqual(float(gpt_pro["value"]), 70.5)
            self.assertIn("MMMU-Pro", str(claude_pro["notes"]))

            with get_connection(self.engine) as conn:
                benchmark_rows = fetch_all(
                    conn,
                    select(benchmarks_table.c.id, benchmarks_table.c.higher_is_better).where(
                        benchmarks_table.c.id.in_(["mmmu_test", "mmmu_pro"])
                    ),
                )
            direction_by_id = {row["id"]: row["higher_is_better"] for row in benchmark_rows}
            self.assertEqual(direction_by_id, {"mmmu_test": 1, "mmmu_pro": 1})

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 2)
            self.assertTrue(all(row["resolution_status"] == "resolved" for row in raw_rows))

    def test_livebench_spot_check_derives_category_scores_and_skips_malformed_rows(self) -> None:
            adapter = LiveBenchAdapter()
            categories_json = json.dumps(
                {
                    "Reasoning": ["theory_of_mind", "zebra_puzzle", "spatial", "logic_with_navigation"],
                    "Coding": ["code_generation", "code_completion"],
                    "Agentic Coding": ["javascript", "typescript", "python"],
                    "Mathematics": ["AMPS_Hard", "integrals_with_game", "math_comp", "olympiad"],
                    "Data Analysis": ["consecutive_events", "tablejoin", "tablereformat"],
                    "Language": ["connections", "plot_unscrambling", "typos"],
                    "IF": ["paraphrase", "simplify", "story_generation", "summarize"],
                }
            )
            table_csv = "\n".join(
                [
                    (
                        "model,AMPS_Hard,code_completion,code_generation,connections,"
                        "consecutive_events,integrals_with_game,javascript,logic_with_navigation,"
                        "math_comp,olympiad,paraphrase,plot_unscrambling,python,simplify,spatial,"
                        "story_generation,summarize,tablejoin,tablereformat,theory_of_mind,"
                        "typescript,typos,zebra_puzzle"
                    ),
                    (
                        "Claude Sonnet 4.6,80,50,70,90,15,60,0,40,40,20,20,60,60,40,30,"
                        "60,80,45,75,10,30,30,20"
                    ),
                    "malformed-short-row,80,50",
                ]
            )

            raw_records = adapter._build_raw_records(table_csv, categories_json, collected_at=FUTURE_COLLECTED_AT)
            self.assertEqual(len(raw_records), 1)
            raw_record = raw_records[0]
            self.assertEqual(raw_record.raw_model_name, "Claude Sonnet 4.6")
            self.assertEqual(raw_record.metadata["release"], "2026-01-08")
            self.assertIn("artifact_sha256", raw_record.metadata)

            candidates = adapter.normalize(raw_records)
            candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
            self.assertEqual(len(candidate_values), 8)
            self.assertAlmostEqual(candidate_values["livebench_reasoning"], 25.0)
            self.assertAlmostEqual(candidate_values["livebench_coding"], 60.0)
            self.assertAlmostEqual(candidate_values["livebench_agentic_coding"], 30.0)
            self.assertAlmostEqual(candidate_values["livebench_math"], 50.0)
            self.assertAlmostEqual(candidate_values["livebench_data_analysis"], 45.0)
            self.assertAlmostEqual(candidate_values["livebench_language"], 60.0)
            self.assertAlmostEqual(candidate_values["livebench_instruction_following"], 50.0)
            self.assertAlmostEqual(candidate_values["livebench_overall"], 45.714285714285715)
            self.assertTrue(all(candidate.source_type == "primary" for candidate in candidates))
            self.assertTrue(all(candidate.verified for candidate in candidates))

            _, source_run_id, _, _ = self._persist_records(adapter, raw_records)

            overall = self._latest_score("claude-sonnet-4-6", "livebench_overall")
            coding = self._latest_score("claude-sonnet-4-6", "livebench_coding")
            self.assertAlmostEqual(float(overall["value"]), 45.714285714285715)
            self.assertAlmostEqual(float(coding["value"]), 60.0)
            self.assertEqual(overall["source_type"], "primary")
            self.assertEqual(overall["verified"], 1)
            self.assertIn("LiveBench 2026-01-08", str(overall["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-sonnet-4-6")
            self.assertEqual(raw_rows[0]["resolution_status"], "resolved")

    def test_bfcl_spot_check_preserves_components_and_evaluation_mode(self) -> None:
            adapter = BfclAdapter()
            header = (
                "Rank,Overall Acc,Model,Model Link,Total Cost ($),Latency Mean (s),"
                "Latency Standard Deviation (s),Latency 95th Percentile (s),"
                "Non-Live AST Acc,Non-Live Simple AST,Non-Live Multiple AST,"
                "Non-Live Parallel AST,Non-Live Parallel Multiple AST,Live Acc,"
                "Live Simple AST,Live Multiple AST,Live Parallel AST,Live Parallel Multiple AST,"
                "Multi Turn Acc,Multi Turn Base,Multi Turn Miss Func,Multi Turn Miss Param,"
                "Multi Turn Long Context,Web Search Acc,Web Search Base,Web Search No Snippet,"
                "Memory Acc,Memory KV,Memory Vector,Memory Recursive Summarization,"
                "Relevance Detection,Irrelevance Detection,Format Sensitivity Max Delta,"
                "Format Sensitivity Standard Deviation,Organization,License"
            )
            table_csv = "\n".join(
                [
                    header,
                    (
                        "7,62.5%,Claude Opus 4.6 (FC),https://www.anthropic.com/claude,"
                        "86.55,4.38,3.13,7.56,88.58%,76.83%,95.50%,93.50%,88.50%,"
                        "79.79%,86.43%,78.16%,87.50%,75.00%,68.38%,81.00%,64.00%,"
                        "58.00%,70.50%,84.50%,84.00%,85.00%,73.76%,70.97%,72.90%,"
                        "77.42%,62.50%,84.72%,N/A,N/A,Anthropic,Proprietary"
                    ),
                    (
                        "8,55.87%,GPT-5.4 (Prompt),https://openai.com/gpt-5,85.65,5.1,2.0,"
                        "8.2,81.85%,70.00%,90.00%,88.00%,84.00%,70.39%,72.00%,68.00%,"
                        "75.00%,69.00%,28.12%,35.00%,25.00%,20.00%,32.00%,75.50%,76.00%,"
                        "75.00%,45.81%,42.00%,46.00%,49.00%,60.00%,80.00%,8.5,1.7,OpenAI,Proprietary"
                    ),
                    (
                        "9,N/A,Missing Overall (FC),https://example.com,1.0,1.0,0.1,1.2,"
                        "10%,10%,10%,10%,10%,10%,10%,10%,10%,10%,10%,10%,10%,10%,10%,"
                        "10%,10%,10%,10%,10%,10%,10%,10%,10%,N/A,N/A,Example,Proprietary"
                    ),
                ]
            )

            raw_records = adapter._build_raw_records(table_csv, collected_at=FUTURE_COLLECTED_AT)
            self.assertEqual(len(raw_records), 2)
            claude_record = raw_records[0]
            self.assertEqual(claude_record.raw_model_name, "Claude Opus 4.6")
            self.assertEqual(claude_record.raw_model_key, "Claude Opus 4.6 (FC)")
            self.assertEqual(claude_record.metadata["evaluation_mode"], "FC")
            self.assertEqual(claude_record.metadata["organization"], "Anthropic")
            self.assertEqual(claude_record.metadata["license"], "Proprietary")
            self.assertAlmostEqual(claude_record.metadata["overall_acc"], 62.5)
            self.assertAlmostEqual(claude_record.metadata["component_scores"]["multi_turn_acc"], 68.38)
            self.assertAlmostEqual(claude_record.metadata["component_scores"]["web_search_acc"], 84.5)
            self.assertIsNone(claude_record.metadata["format_sensitivity"]["max_delta"])

            candidates = adapter.normalize(raw_records)
            self.assertEqual(len(candidates), 2)
            self.assertEqual(candidates[0].benchmark_id, "bfcl_overall")
            self.assertEqual(candidates[0].source_type, "primary")
            self.assertTrue(candidates[0].verified)
            self.assertAlmostEqual(candidates[0].value, 62.5)

            _, source_run_id, _, _ = self._persist_records(adapter, raw_records)

            score = self._latest_score("claude-opus-4-6", "bfcl_overall")
            self.assertAlmostEqual(float(score["value"]), 62.5)
            self.assertEqual(score["source_type"], "primary")
            self.assertEqual(score["verified"], 1)
            self.assertIn("BFCL V4", str(score["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 2)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
            self.assertEqual(raw_rows[0]["resolution_status"], "resolved")

    def test_livecodebench_spot_check_aggregates_default_window(self) -> None:
            adapter = LiveCodeBenchAdapter()
            payload = {
                "date_marks": [
                    1682899200000,
                    1685577600000,
                    1688169600000,
                    1690848000000,
                    1693526400000,
                    1696118400000,
                    1698796800000,
                    1701388800000,
                    1704067200000,
                    1706745600000,
                    1709251200000,
                    1711929600000,
                    1714521600000,
                    1717200000000,
                    1719792000000,
                    1722470400000,
                    1725148800000,
                ],
                "models": [
                    {
                        "model_name": "claude-opus-4.6",
                        "model_repr": "Claude Opus 4.6",
                        "model_style": "AnthropicAPI",
                        "release_date": 1719705600000,
                        "link": "https://example.test/claude",
                    },
                    {
                        "model_name": "gpt-5.4",
                        "model_repr": "GPT-5.4 (xhigh)",
                        "model_style": "OpenAIAPI",
                        "release_date": 1725148800000,
                        "link": "https://example.test/gpt",
                    },
                    {
                        "model_name": "missing-release",
                        "model_repr": "Missing Release",
                        "model_style": "Unknown",
                        "link": "https://example.test/missing",
                    },
                ],
                "performances": [
                    {
                        "question_id": "before-window",
                        "model": "Claude Opus 4.6",
                        "date": 1719792000000,
                        "difficulty": "easy",
                        "pass@1": 0.0,
                        "platform": "codeforces",
                    },
                    {
                        "question_id": "easy-1",
                        "model": "Claude Opus 4.6",
                        "date": 1722470400000,
                        "difficulty": "easy",
                        "pass@1": 50.0,
                        "platform": "codeforces",
                    },
                    {
                        "question_id": "medium-1",
                        "model": "Claude Opus 4.6",
                        "date": 1722470400000,
                        "difficulty": "medium",
                        "pass@1": 100.0,
                        "platform": "leetcode",
                    },
                    {
                        "question_id": "hard-1",
                        "model": "Claude Opus 4.6",
                        "date": 1725148800000,
                        "difficulty": "hard",
                        "pass@1": 70.0,
                        "platform": "codeforces",
                    },
                    {
                        "question_id": "gpt-1",
                        "model": "GPT-5.4 (xhigh)",
                        "date": 1725148800000,
                        "difficulty": "easy",
                        "pass@1": 90.0,
                        "platform": "codeforces",
                    },
                ],
            }
            raw_records = adapter._records_from_payload(
                payload,
                fetched_at=FUTURE_COLLECTED_AT,
                artifact_metadata={"artifact_sha256": "fixture-sha"},
            )

            _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

            candidate_values = {candidate.raw_model_name: candidate.value for candidate in candidates}
            self.assertEqual(len(candidates), 2)
            self.assertAlmostEqual(candidate_values["Claude Opus 4.6"], 73.3)
            self.assertAlmostEqual(candidate_values["GPT-5.4 (xhigh)"], 90.0)

            claude_candidate = next(candidate for candidate in candidates if candidate.raw_model_name == "Claude Opus 4.6")
            self.assertEqual(claude_candidate.metadata["problem_count"], 3)
            self.assertEqual(claude_candidate.metadata["window_start_date"], "2024-08-01")
            self.assertEqual(claude_candidate.metadata["difficulty_counts"], {"easy": 1, "hard": 1, "medium": 1})
            self.assertEqual(claude_candidate.metadata["difficulty_scores"], {"easy": 50.0, "hard": 70.0, "medium": 100.0})
            self.assertEqual(claude_candidate.metadata["platform_counts"], {"codeforces": 2, "leetcode": 1})
            self.assertFalse(claude_candidate.metadata["contaminated_by_window"])
            self.assertEqual(claude_candidate.metadata["artifact_sha256"], "fixture-sha")

            gpt_candidate = next(candidate for candidate in candidates if candidate.raw_model_name == "GPT-5.4 (xhigh)")
            self.assertTrue(gpt_candidate.metadata["contaminated_by_window"])
            self.assertIn("potentially contaminated", str(gpt_candidate.notes))

            claude = self._latest_score("claude-opus-4-6", "livecodebench_codegen")
            gpt = self._latest_score("gpt-5-4", "livecodebench_codegen")
            self.assertAlmostEqual(float(claude["value"]), 73.3)
            self.assertAlmostEqual(float(gpt["value"]), 90.0)
            self.assertEqual(claude["source_type"], "primary")
            self.assertEqual(claude["verified"], 1)

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 2)
            self.assertTrue(all(row["resolution_status"] == "resolved" for row in raw_rows))

    def test_bigcodebench_spot_check_persists_full_and_hard_scores(self) -> None:
            adapter = BigCodeBenchAdapter()
            raw_records = [
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="bigcodebench_full",
                    raw_model_name="Claude Opus 4.6",
                    raw_value=json.dumps({"instruct": 61.0, "complete": 57.0}, ensure_ascii=True, sort_keys=True),
                    source_url="https://bigcode-bench.github.io/results.json",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={"pass@1": {"instruct": 61.0, "complete": 57.0}},
                    metadata={
                        "dataset": "Full",
                        "result_url": "https://bigcode-bench.github.io/results.json",
                        "model_link": "https://example.test/claude-opus-4-6",
                        "open_data": "No",
                        "prompted": True,
                        "moe": False,
                        "size_b": None,
                        "active_parameters_b": None,
                        "leaderboard_date": "2026-03-01",
                        "prefill": True,
                        "pass_at_1": {"instruct": 61.0, "complete": 57.0},
                        "source_policy": "official_leaderboard_pass_at_1_greedy",
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="bigcodebench_hard",
                    raw_model_name="Claude Opus 4.6",
                    raw_value=json.dumps({"instruct": 31.0, "complete": 27.0}, ensure_ascii=True, sort_keys=True),
                    source_url="https://bigcode-bench.github.io/results-hard.json",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={"pass@1": {"instruct": 31.0, "complete": 27.0}},
                    metadata={
                        "dataset": "Hard",
                        "result_url": "https://bigcode-bench.github.io/results-hard.json",
                        "model_link": "https://example.test/claude-opus-4-6",
                        "open_data": "No",
                        "prompted": True,
                        "moe": False,
                        "size_b": None,
                        "active_parameters_b": None,
                        "leaderboard_date": "2026-03-01",
                        "prefill": True,
                        "pass_at_1": {"instruct": 31.0, "complete": 27.0},
                        "source_policy": "official_leaderboard_pass_at_1_greedy",
                    },
                ),
            ]

            _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

            candidate_values = {candidate.benchmark_id: candidate.value for candidate in candidates}
            self.assertEqual(
                candidate_values,
                {
                    "bigcodebench_full": 59.0,
                    "bigcodebench_full_instruct": 61.0,
                    "bigcodebench_full_complete": 57.0,
                    "bigcodebench_hard": 29.0,
                    "bigcodebench_hard_instruct": 31.0,
                    "bigcodebench_hard_complete": 27.0,
                },
            )

            full = self._latest_score("claude-opus-4-6", "bigcodebench_full")
            hard = self._latest_score("claude-opus-4-6", "bigcodebench_hard")
            self.assertAlmostEqual(float(full["value"]), 59.0)
            self.assertAlmostEqual(float(hard["value"]), 29.0)
            self.assertEqual(full["source_type"], "primary")
            self.assertEqual(full["verified"], 1)
            self.assertIn("Official BigCodeBench Full Average", str(full["notes"]))
            self.assertIn("Official BigCodeBench Hard Average", str(hard["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 2)
            self.assertTrue(all(row["normalized_model_id"] == "claude-opus-4-6" for row in raw_rows))
            self.assertTrue(all(row["source_type"] == "primary" for row in raw_rows))
            raw_notes = [json.loads(str(row["notes"])) for row in raw_rows]
            self.assertEqual({note["dataset"] for note in raw_notes}, {"Full", "Hard"})

    def test_helm_capabilities_spot_check_persists_mean_and_components(self) -> None:
            adapter = HelmCapabilitiesAdapter()
            metrics = {
                "helm_capabilities_mean": {
                    "header": "Mean score",
                    "label": "Mean accuracy score",
                    "value": 0.65,
                    "description": None,
                    "run_spec_names": [],
                },
                "helm_capabilities_mmlu_pro": {
                    "header": "MMLU-Pro - COT correct",
                    "label": "MMLU-Pro COT correct",
                    "value": 0.7,
                    "description": "min=0.7, mean=0.7, max=0.7, sum=0.7 (1)",
                    "run_spec_names": ["mmlu_pro:subset=all,model=anthropic_claude-opus-4-6"],
                },
                "helm_capabilities_gpqa": {
                    "header": "GPQA - COT correct",
                    "label": "GPQA COT correct",
                    "value": 0.6,
                    "description": "min=0.6, mean=0.6, max=0.6, sum=0.6 (1)",
                    "run_spec_names": ["gpqa:subset=gpqa_main,model=anthropic_claude-opus-4-6"],
                },
                "helm_capabilities_ifeval": {
                    "header": "IFEval - IFEval Strict Acc",
                    "label": "IFEval strict accuracy",
                    "value": 0.82,
                    "description": "min=0.82, mean=0.82, max=0.82, sum=0.82 (1)",
                    "run_spec_names": ["ifeval:model=anthropic_claude-opus-4-6"],
                },
                "helm_capabilities_wildbench": {
                    "header": "WildBench - WB Score",
                    "label": "WildBench score",
                    "value": 0.58,
                    "description": "min=0.58, mean=0.58, max=0.58, sum=0.58 (1)",
                    "run_spec_names": ["wildbench:subset=v2,model=anthropic_claude-opus-4-6"],
                },
                "helm_capabilities_omni_math": {
                    "header": "Omni-MATH - Acc",
                    "label": "Omni-MATH accuracy",
                    "value": 0.55,
                    "description": "min=0.55, mean=0.55, max=0.55, sum=0.55 (1)",
                    "run_spec_names": ["omni_math:model=anthropic_claude-opus-4-6"],
                },
            }
            raw_record = RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="helm_capabilities_mean",
                raw_model_name="Claude Opus 4.6",
                raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
                source_url="https://storage.googleapis.com/crfm-helm-public/capabilities/benchmark_output/releases/v1.15.0/groups/core_scenarios.json",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="anthropic/claude-opus-4.6",
                payload={"row": []},
                metadata={
                    "project": "capabilities",
                    "release": "v1.15.0",
                    "release_date": "2025-11-24",
                    "group_name": "core_scenarios",
                    "table_title": "Accuracy",
                    "model": {
                        "name": "anthropic/claude-opus-4.6",
                        "display_name": "Claude Opus 4.6",
                        "creator_organization": "Anthropic",
                        "access": "limited",
                        "release_date": "2026-02-17",
                    },
                    "metrics": metrics,
                    "source_policy": "official_helm_capabilities_core_scenarios_accuracy",
                },
            )

            _, source_run_id, candidates, _ = self._persist_records(adapter, [raw_record])

            candidate_values = {candidate.benchmark_id: round(candidate.value, 3) for candidate in candidates}
            self.assertEqual(
                candidate_values,
                {
                    "helm_capabilities_mean": 65.0,
                    "helm_capabilities_mmlu_pro": 70.0,
                    "helm_capabilities_gpqa": 60.0,
                    "helm_capabilities_ifeval": 82.0,
                    "helm_capabilities_wildbench": 58.0,
                    "helm_capabilities_omni_math": 55.0,
                },
            )

            mean = self._latest_score("claude-opus-4-6", "helm_capabilities_mean")
            ifeval = self._latest_score("claude-opus-4-6", "helm_capabilities_ifeval")
            self.assertAlmostEqual(float(mean["value"]), 65.0)
            self.assertAlmostEqual(float(ifeval["value"]), 82.0)
            self.assertEqual(mean["source_type"], "primary")
            self.assertEqual(mean["verified"], 1)
            self.assertIn("Official HELM Capabilities v1.15.0 Mean accuracy", str(mean["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
            self.assertEqual(raw_rows[0]["source_type"], "primary")
            raw_note = json.loads(str(raw_rows[0]["notes"]))
            self.assertEqual(raw_note["release"], "v1.15.0")
            self.assertEqual(raw_note["table_title"], "Accuracy")

    def test_taubench_spot_check_persists_standard_scores_and_skips_custom_systems(self) -> None:
            adapter = TaubenchAdapter()
            complete_metrics = {
                "airline": {
                    "domain": "airline",
                    "benchmark_id": "taubench_text_airline",
                    "label": "Airline",
                    "pass_1": 84.0,
                    "pass_2": 77.67,
                    "pass_3": 73.5,
                    "pass_4": 70.0,
                    "cost": 0.39919,
                    "retrieval_config": None,
                },
                "retail": {
                    "domain": "retail",
                    "benchmark_id": "taubench_text_retail",
                    "label": "Retail",
                    "pass_1": 79.61,
                    "pass_2": 67.4,
                    "pass_3": 58.77,
                    "pass_4": 51.75,
                    "cost": 0.38695,
                    "retrieval_config": None,
                },
                "telecom": {
                    "domain": "telecom",
                    "benchmark_id": "taubench_text_telecom",
                    "label": "Telecom",
                    "pass_1": 92.32,
                    "pass_2": 86.11,
                    "pass_3": 81.36,
                    "pass_4": 78.07,
                    "cost": 0.71992,
                    "retrieval_config": None,
                },
                "banking_knowledge": {
                    "domain": "banking_knowledge",
                    "benchmark_id": "taubench_text_banking_knowledge",
                    "label": "Banking knowledge",
                    "pass_1": 21.39,
                    "pass_2": 13.4,
                    "pass_3": 10.31,
                    "pass_4": 8.25,
                    "cost": None,
                    "retrieval_config": "alltools",
                },
            }
            raw_records = [
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="taubench_text_mean",
                    raw_model_name="Claude Opus 4.6",
                    raw_value=json.dumps(complete_metrics, ensure_ascii=True, sort_keys=True),
                    source_url="https://sierra-tau-bench-public.s3.amazonaws.com/submissions/claude-opus-4-6_sierra_2026-05-05/submission.json",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Claude Opus 4.6",
                    payload={"model_name": "Claude Opus 4.6"},
                    metadata={
                        "submission_id": "claude-opus-4-6_sierra_2026-05-05",
                        "modality": "text",
                        "submission_type": "standard",
                        "verified": True,
                        "single_model_submission": True,
                        "aggregate_submission": False,
                        "self_reported": True,
                        "agent_system_evidence": True,
                        "complete_domain_set": True,
                        "available_domain_count": 4,
                        "expected_domain_count": 4,
                        "domain_metrics": complete_metrics,
                    },
                ),
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="taubench_text_banking_knowledge",
                    raw_model_name="Distyl ButtonAgent",
                    raw_value=json.dumps(
                        {"banking_knowledge": complete_metrics["banking_knowledge"]},
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
                    source_url="https://sierra-tau-bench-public.s3.amazonaws.com/submissions/distyl-buttonagent_distyl_2026-03-25/submission.json",
                    collected_at=FUTURE_COLLECTED_AT,
                    raw_model_key="Distyl ButtonAgent",
                    payload={"model_name": "Distyl ButtonAgent"},
                    metadata={
                        "submission_id": "distyl-buttonagent_distyl_2026-03-25",
                        "modality": "text",
                        "submission_type": "custom",
                        "verified": True,
                        "single_model_submission": False,
                        "aggregate_submission": True,
                        "self_reported": True,
                        "agent_system_evidence": True,
                        "complete_domain_set": False,
                        "available_domain_count": 1,
                        "expected_domain_count": 4,
                        "domain_metrics": {"banking_knowledge": complete_metrics["banking_knowledge"]},
                    },
                ),
            ]

            _, source_run_id, candidates, _ = self._persist_records(adapter, raw_records)

            candidate_values = {candidate.benchmark_id: round(candidate.value, 3) for candidate in candidates}
            self.assertEqual(
                candidate_values,
                {
                    "taubench_text_airline": 84.0,
                    "taubench_text_retail": 79.61,
                    "taubench_text_telecom": 92.32,
                    "taubench_text_banking_knowledge": 21.39,
                    "taubench_text_mean": 69.33,
                },
            )

            mean = self._latest_score("claude-opus-4-6", "taubench_text_mean")
            banking = self._latest_score("claude-opus-4-6", "taubench_text_banking_knowledge")
            self.assertAlmostEqual(float(mean["value"]), 69.33)
            self.assertAlmostEqual(float(banking["value"]), 21.39)
            self.assertEqual(mean["source_type"], "secondary")
            self.assertEqual(mean["verified"], 1)
            self.assertIn("complete text domain set", str(mean["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 2)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "claude-opus-4-6")
            self.assertEqual(raw_rows[0]["source_type"], "secondary")
            self.assertEqual(raw_rows[0]["resolution_status"], "resolved")
            self.assertIsNone(raw_rows[1]["normalized_model_id"])
            self.assertEqual(raw_rows[1]["source_type"], "secondary")
            self.assertEqual(raw_rows[1]["resolution_status"], "skipped_aggregate")

    def test_ragtruth_spot_check_persists_overall_and_task_rates(self) -> None:
            adapter = RagtruthAdapter()
            metrics = {
                "ragtruth_hallucination_rate": {
                    "label": "Overall",
                    "responses": 450,
                    "hallucinated_responses": 42,
                    "hallucination_spans": 73,
                    "hallucination_rate": 9.333333333333334,
                },
                "ragtruth_summary_hallucination_rate": {
                    "label": "Summarization",
                    "task_type": "Summary",
                    "responses": 150,
                    "hallucinated_responses": 6,
                    "hallucination_spans": 8,
                    "hallucination_rate": 4.0,
                },
                "ragtruth_qa_hallucination_rate": {
                    "label": "Question answering",
                    "task_type": "QA",
                    "responses": 150,
                    "hallucinated_responses": 1,
                    "hallucination_spans": 1,
                    "hallucination_rate": 0.6666666666666666,
                },
                "ragtruth_data_to_text_hallucination_rate": {
                    "label": "Data-to-text",
                    "task_type": "Data2txt",
                    "responses": 150,
                    "hallucinated_responses": 35,
                    "hallucination_spans": 64,
                    "hallucination_rate": 23.333333333333332,
                },
            }
            raw_record = RawSourceRecord(
                source_id=adapter.source_id,
                benchmark_id="ragtruth_hallucination_rate",
                raw_model_name="gpt-4-0613",
                raw_value=json.dumps(metrics, ensure_ascii=True, sort_keys=True),
                source_url="https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/response.jsonl",
                collected_at=FUTURE_COLLECTED_AT,
                raw_model_key="gpt-4-0613",
                payload={"model": "gpt-4-0613", "split": "test", "metrics": metrics},
                metadata={
                    "dataset_version": "2024-02",
                    "split": "test",
                    "response_url": "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/response.jsonl",
                    "source_info_url": "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/source_info.jsonl",
                    "metrics": metrics,
                    "source_policy": "official_ragtruth_test_split_response_hallucination_rate",
                },
            )

            _, source_run_id, candidates, _ = self._persist_records(adapter, [raw_record])

            candidate_values = {candidate.benchmark_id: round(candidate.value, 3) for candidate in candidates}
            self.assertEqual(
                candidate_values,
                {
                    "ragtruth_hallucination_rate": 9.333,
                    "ragtruth_summary_hallucination_rate": 4.0,
                    "ragtruth_qa_hallucination_rate": 0.667,
                    "ragtruth_data_to_text_hallucination_rate": 23.333,
                },
            )

            overall = self._latest_score("gpt-4-0613", "ragtruth_hallucination_rate")
            data_to_text = self._latest_score("gpt-4-0613", "ragtruth_data_to_text_hallucination_rate")
            self.assertAlmostEqual(float(overall["value"]), 9.333333333333334)
            self.assertAlmostEqual(float(data_to_text["value"]), 23.333333333333332)
            self.assertEqual(overall["source_type"], "primary")
            self.assertEqual(overall["verified"], 1)
            self.assertIn("historical corpus evidence", str(overall["notes"]))

            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(len(raw_rows), 1)
            self.assertEqual(raw_rows[0]["normalized_model_id"], "gpt-4-0613")
            self.assertEqual(raw_rows[0]["source_type"], "primary")
            raw_note = json.loads(str(raw_rows[0]["notes"]))
            self.assertEqual(raw_note["split"], "test")
            self.assertEqual(raw_note["metrics"]["ragtruth_qa_hallucination_rate"]["responses"], 150)

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

    def test_chatbot_arena_listing_does_not_create_unknown_model(self) -> None:
            adapter = ChatbotArenaAdapter(revision="a" * 40)
            with self.engine.begin() as conn:
                conn.execute(
                    model_source_listings_table.insert(),
                    {
                        "source_name": "chatbot_arena",
                        "benchmark_id": "chatbot_arena",
                        "raw_model_name": "previously-listed-model",
                        "raw_model_key": "previously-listed-model",
                        "model_id": None,
                        "listing_status": "listed",
                        "source_revision": "9" * 40,
                        "publication_date": "2098-12-01",
                        "first_seen_at": "2098-12-01T00:00:00Z",
                        "last_seen_at": "2098-12-01T00:00:00Z",
                        "metadata_json": "{}",
                    },
                )
            raw_records = [
                RawSourceRecord(
                    source_id=adapter.source_id,
                    benchmark_id="chatbot_arena",
                    raw_model_name="arena-only-unknown-model",
                    raw_model_key="arena-only-unknown-model",
                    raw_value="1400",
                    source_url=adapter.source_url,
                    collected_at=FUTURE_COLLECTED_AT,
                    payload={"model_name": "arena-only-unknown-model"},
                    metadata={
                        "organization": "Unknown Lab",
                        "license": "Proprietary",
                        "existing_models_only": True,
                        "source_listing_status": "listed",
                        "dataset_revision": "a" * 40,
                        "leaderboard_publish_date": "2099-01-01",
                        "confidence_lower": 1390.0,
                        "confidence_upper": 1410.0,
                        "rank": 1,
                        "category": "overall",
                    },
                )
            ]

            _, source_run_id, _, outcomes = self._persist_records(adapter, raw_records)

            self.assertEqual(outcomes, (0, 0))
            with get_connection(self.engine) as conn:
                model_row = fetch_one(
                    conn,
                    select(models_table).where(models_table.c.name == "arena-only-unknown-model"),
                )
                listing = fetch_one(
                    conn,
                    select(model_source_listings_table).where(
                        model_source_listings_table.c.raw_model_key == "arena-only-unknown-model"
                    ),
                )
                previous_listing = fetch_one(
                    conn,
                    select(model_source_listings_table).where(
                        model_source_listings_table.c.raw_model_key == "previously-listed-model"
                    ),
                )
            self.assertIsNone(model_row)
            self.assertIsNotNone(listing)
            self.assertIsNone(listing["model_id"])
            self.assertEqual(listing["listing_status"], "listed")
            self.assertEqual(previous_listing["listing_status"], "no_longer_listed")
            self.assertEqual(previous_listing["last_seen_at"], "2098-12-01T00:00:00Z")
            raw_rows = update_engine.list_raw_source_records(source_run_id)
            self.assertEqual(raw_rows[0]["resolution_status"], "skipped_unmatched_listing")

    def test_chatbot_arena_audit_blocks_severe_resolution_collapse(self) -> None:
            adapter = ChatbotArenaAdapter(revision="a" * 40)
            required_ids = [
                "chatbot_arena_text_raw",
                "chatbot_arena",
                "chatbot_arena_webdev",
                "chatbot_arena_agent",
                "chatbot_arena_vision",
                "chatbot_arena_document",
                "chatbot_arena_search",
            ]
            raw_records = []
            for index in range(201):
                benchmark_id = required_ids[index] if index < len(required_ids) else "chatbot_arena"
                name = "claude-opus-4-6" if index == 0 else f"arena-collapse-{index}"
                raw_records.append(
                    RawSourceRecord(
                        source_id=adapter.source_id,
                        benchmark_id=benchmark_id,
                        raw_model_name=name,
                        raw_model_key=name,
                        raw_value="1400",
                        source_url=adapter.source_url,
                        collected_at=FUTURE_COLLECTED_AT,
                        payload={"model_name": name},
                        metadata={
                            "existing_models_only": True,
                            "source_listing_status": "listed",
                            "dataset_revision": "a" * 40,
                            "leaderboard_publish_date": "2099-01-01",
                            "confidence_lower": 1390.0,
                            "confidence_upper": 1410.0,
                            "rank": index + 1,
                            "category": "overall",
                        },
                    )
                )
            log_id, _, _, _ = self._persist_records(adapter, raw_records)

            with patch.object(audit_engine, "MIN_EXPECTED_RECORDS", {}):
                audit_result = audit_engine.run_audit(self.engine, log_id)

            findings = [
                finding
                for finding in audit_result["findings"]
                if finding["check_name"] == "arena_identity_contract"
            ]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["details"]["resolved_count"], 1)
            self.assertEqual(findings[0]["details"]["minimum_resolved"], 11)

    def test_chatbot_arena_resolution_floor_rejects_large_nonzero_collapse(self) -> None:
            minimum_resolved = audit_engine._minimum_arena_resolved_rows(3596)

            self.assertEqual(minimum_resolved, 180)
            self.assertLess(20, minimum_resolved)
            self.assertGreaterEqual(377, minimum_resolved)

    def test_audit_allows_optional_provider_catalog_skip_but_blocks_failure(self) -> None:
            skipped_log_id = update_engine._create_update_log("test")
            skipped_run_id = update_engine._start_metadata_source_run(
                skipped_log_id,
                source_name="provider_api_model_discovery",
                benchmark_id="model_discovery:anthropic",
            )
            update_engine._finish_source_run(
                skipped_run_id,
                status="skipped",
                records_found=0,
                error_message="Missing optional ANTHROPIC_API_KEY",
            )
            skipped_audit = audit_engine.run_audit(self.engine, skipped_log_id)
            skipped_checks = {finding["check_name"] for finding in skipped_audit["findings"]}
            self.assertNotIn("source_run_failed", skipped_checks)
            self.assertNotIn("zero_row_source", skipped_checks)

            failed_log_id = update_engine._create_update_log("test")
            failed_run_id = update_engine._start_metadata_source_run(
                failed_log_id,
                source_name="provider_api_model_discovery",
                benchmark_id="model_discovery:google-gemini",
            )
            update_engine._finish_source_run(
                failed_run_id,
                status="failed",
                records_found=0,
                error_message="Provider request failed",
            )
            failed_audit = audit_engine.run_audit(self.engine, failed_log_id)
            failed_checks = {finding["check_name"] for finding in failed_audit["findings"]}
            self.assertIn("source_run_failed", failed_checks)
            self.assertIn("zero_row_source", failed_checks)

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
