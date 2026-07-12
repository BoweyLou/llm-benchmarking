from __future__ import annotations

import unittest

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from backend.sources.chatbot_arena import ChatbotArenaAdapter


REVISION = "a" * 40


def _parquet_bytes(rows: list[dict]) -> bytes:
    sink = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist(rows), sink)
    return sink.getvalue().to_pybytes()


def _rating_row(**overrides):
    row = {
        "model_name": "model-a",
        "organization": "Acme",
        "license": "Proprietary",
        "rating": 1234.5,
        "rating_lower": 1220.0,
        "rating_upper": 1249.0,
        "variance": 42.0,
        "vote_count": 5000,
        "rank": 2,
        "category": "overall",
        "leaderboard_publish_date": "2026-07-10",
    }
    row.update(overrides)
    return row


class ChatbotArenaAdapterTests(unittest.TestCase):
    def test_style_controlled_overall_preserves_legacy_id_and_evidence(self) -> None:
        adapter = ChatbotArenaAdapter(revision=REVISION)
        records = adapter._records_from_parquet(
            _parquet_bytes([_rating_row()]),
            split="text_style_control",
            selections=[("overall", "chatbot_arena", True)],
            parquet_url=adapter._parquet_url("text_style_control", REVISION),
            fetched_at="2026-07-13T00:00:00Z",
            revision=REVISION,
        )
        candidates = adapter.normalize(records)

        self.assertEqual(records[0].benchmark_id, "chatbot_arena")
        self.assertEqual(candidates[0].confidence_lower, 1220.0)
        self.assertEqual(candidates[0].confidence_upper, 1249.0)
        self.assertEqual(candidates[0].vote_count, 5000)
        self.assertEqual(candidates[0].rank, 2)
        self.assertTrue(candidates[0].style_control)
        self.assertFalse(candidates[0].preliminary)
        self.assertEqual(candidates[0].source_metadata["dataset_revision"], REVISION)
        self.assertTrue(records[0].metadata["existing_models_only"])

    def test_selected_text_categories_use_distinct_ids_and_optional_absence_is_safe(self) -> None:
        adapter = ChatbotArenaAdapter(revision=REVISION)
        rows = [
            _rating_row(category="overall"),
            _rating_row(
                model_name="model-b",
                category="coding",
                rating=1210.0,
                rating_lower=1200.0,
                rating_upper=1220.0,
            ),
        ]
        records = adapter._records_from_parquet(
            _parquet_bytes(rows),
            split="text_style_control",
            selections=[
                ("overall", "chatbot_arena", True),
                ("coding", "chatbot_arena_coding", False),
                ("expert", "chatbot_arena_expert", False),
            ],
            parquet_url=adapter._parquet_url("text_style_control", REVISION),
            fetched_at="2026-07-13T00:00:00Z",
            revision=REVISION,
        )
        self.assertEqual(
            {record.benchmark_id for record in records},
            {"chatbot_arena", "chatbot_arena_coding"},
        )

    def test_missing_required_overall_fails_closed(self) -> None:
        adapter = ChatbotArenaAdapter(revision=REVISION)
        with self.assertRaisesRegex(ValueError, "no required overall"):
            adapter._records_from_parquet(
                _parquet_bytes([_rating_row(category="coding")]),
                split="text",
                selections=[("overall", "chatbot_arena_text_raw", True)],
                parquet_url=adapter._parquet_url("text", REVISION),
                fetched_at="2026-07-13T00:00:00Z",
                revision=REVISION,
            )

    def test_schema_and_identity_errors_fail_closed(self) -> None:
        adapter = ChatbotArenaAdapter(revision=REVISION)
        bad_schema = _rating_row()
        bad_schema.pop("rating_upper")
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            adapter._records_from_parquet(
                _parquet_bytes([bad_schema]),
                split="text",
                selections=[("overall", "chatbot_arena_text_raw", True)],
                parquet_url="https://example.test/data.parquet",
                fetched_at="2026-07-13T00:00:00Z",
                revision=REVISION,
            )

        with self.assertRaisesRegex(ValueError, "unsafe or empty model identity"):
            adapter._records_from_parquet(
                _parquet_bytes([_rating_row(model_name="bad\nidentity")]),
                split="text",
                selections=[("overall", "chatbot_arena_text_raw", True)],
                parquet_url="https://example.test/data.parquet",
                fetched_at="2026-07-13T00:00:00Z",
                revision=REVISION,
            )

    def test_agent_schema_maps_official_ips_evidence(self) -> None:
        adapter = ChatbotArenaAdapter(revision=REVISION)
        rows = [{
            "model_name": "Agent A",
            "organization": "Acme",
            "license": "Proprietary",
            "score": 0.25,
            "score_ci_lower": 0.20,
            "score_ci_upper": 0.30,
            "observation_count": 10000,
            "session_count": 500,
            "rank": 1,
            "category": "overall",
            "leaderboard_publish_date": "2026-07-08",
        }]
        records = adapter._records_from_parquet(
            _parquet_bytes(rows),
            split="agent",
            selections=[("overall", "chatbot_arena_agent", True)],
            parquet_url=adapter._parquet_url("agent", REVISION),
            fetched_at="2026-07-13T00:00:00Z",
            revision=REVISION,
        )
        candidate = adapter.normalize(records)[0]
        self.assertEqual(candidate.methodology, "inverse_propensity_scored_agent_success")
        self.assertEqual(candidate.observation_count, 10000)
        self.assertEqual(candidate.session_count, 500)

    def test_no_rendered_page_fallback_exists(self) -> None:
        adapter = ChatbotArenaAdapter(revision=REVISION)
        self.assertFalse(hasattr(adapter, "_extract_entries"))
        self.assertFalse(hasattr(adapter, "_extract_entries_from_table"))


class ChatbotArenaTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_resolves_one_revision_for_every_split(self) -> None:
        revision = "b" * 40
        requests: list[str] = []
        rating_payload = _parquet_bytes([_rating_row()])
        agent_payload = _parquet_bytes([{
            "model_name": "Agent A",
            "organization": "Acme",
            "license": "Proprietary",
            "score": 0.25,
            "score_ci_lower": 0.20,
            "score_ci_upper": 0.30,
            "observation_count": 10000,
            "session_count": 500,
            "rank": 1,
            "category": "overall",
            "leaderboard_publish_date": "2026-07-08",
        }])

        class FakeClient:
            async def get(self, url, **_kwargs):
                requests.append(str(url))
                request = httpx.Request("GET", str(url))
                if "/api/datasets/" in str(url):
                    return httpx.Response(200, request=request, json={"sha": revision})
                content = agent_payload if "/agent/" in str(url) else rating_payload
                return httpx.Response(200, request=request, content=content)

        records = await ChatbotArenaAdapter().fetch_raw(FakeClient())

        self.assertEqual(len(requests), 8)
        self.assertTrue(all(revision in url for url in requests[1:]))
        self.assertEqual(
            {record.benchmark_id for record in records},
            {
                "chatbot_arena_text_raw",
                "chatbot_arena",
                "chatbot_arena_webdev",
                "chatbot_arena_agent",
                "chatbot_arena_vision",
                "chatbot_arena_document",
                "chatbot_arena_search",
            },
        )
        self.assertTrue(all(record.metadata["dataset_revision"] == revision for record in records))


if __name__ == "__main__":
    unittest.main()
