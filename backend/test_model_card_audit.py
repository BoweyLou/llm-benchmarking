from __future__ import annotations

import unittest

from sqlalchemy import insert

from backend.database import get_engine, init_db, models as models_table
from backend.model_card_audit import build_model_card_audit_summary, format_model_card_audit_summary


class ModelCardAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = init_db(get_engine("sqlite:///:memory:"))
        rows = [
            {
                "id": "rich-model",
                "name": "Rich Model",
                "provider": "OpenAI",
                "type": "open_weights",
                "huggingface_repo_id": "openai/rich-model",
                "metadata_source_name": "openrouter",
                "metadata_source_url": "https://openrouter.ai/api/v1/models",
                "metadata_verified_at": "2026-04-09T00:00:00Z",
                "model_card_url": "https://huggingface.co/openai/rich-model",
                "model_card_source": "huggingface",
                "model_card_verified_at": "2026-04-09T00:00:00Z",
                "documentation_url": "https://example.com/docs",
                "repo_url": "https://github.com/openai/rich-model",
                "paper_url": "https://arxiv.org/abs/2601.12345",
                "license_id": "apache-2.0",
                "license_name": "Apache 2.0",
                "license_url": "https://example.com/license",
                "base_models_json": '["openai/base-model"]',
                "supported_languages_json": '["en"]',
                "capabilities_json": '["chat"]',
                "intended_use_short": "General assistant use.",
                "limitations_short": "May hallucinate.",
                "training_data_summary": "Mixed public and licensed data.",
                "training_cutoff": "January 2026",
            },
            {
                "id": "suspicious-model",
                "name": "Suspicious Model",
                "provider": "Mistral",
                "type": "open_weights",
                "huggingface_repo_id": "mistral/suspicious-model",
                "metadata_source_name": "openrouter",
                "metadata_source_url": "https://openrouter.ai/api/v1/models",
                "metadata_verified_at": "2026-04-09T00:00:00Z",
                "model_card_url": "https://huggingface.co/mistral/suspicious-model",
                "model_card_source": "huggingface",
                "model_card_verified_at": "2026-04-09T00:00:00Z",
                "documentation_url": "https://github.com/vllm-project/vllm/blob/main/Dockerfile",
                "repo_url": "https://github.com/acme/repo/blob/main/paper.pdf",
                "paper_url": None,
                "license_id": None,
                "license_name": None,
                "license_url": None,
                "base_models_json": "[]",
                "supported_languages_json": "[]",
                "capabilities_json": '["text-generation"]',
                "intended_use_short": "```python\nprint('hi')\n```",
                "limitations_short": None,
                "training_data_summary": "```json\n{}\n```",
                "training_cutoff": None,
            },
            {
                "id": "missing-card-model",
                "name": "Missing Card Model",
                "provider": "Microsoft",
                "type": "proprietary",
                "huggingface_repo_id": "microsoft/missing-card-model",
                "metadata_source_name": "openrouter",
                "metadata_source_url": "https://openrouter.ai/api/v1/models",
                "metadata_verified_at": "2026-04-09T00:00:00Z",
                "model_card_url": None,
                "model_card_source": None,
                "model_card_verified_at": None,
                "documentation_url": None,
                "repo_url": None,
                "paper_url": None,
                "license_id": None,
                "license_name": None,
                "license_url": None,
                "base_models_json": "[]",
                "supported_languages_json": "[]",
                "capabilities_json": "[]",
                "intended_use_short": None,
                "limitations_short": None,
                "training_data_summary": None,
                "training_cutoff": None,
            },
            {
                "id": "no-metadata-model",
                "name": "No Metadata Model",
                "provider": "Unknown",
                "type": "proprietary",
                "huggingface_repo_id": None,
                "metadata_source_name": None,
                "metadata_source_url": None,
                "metadata_verified_at": None,
                "model_card_url": None,
                "model_card_source": None,
                "model_card_verified_at": None,
                "documentation_url": None,
                "repo_url": None,
                "paper_url": None,
                "license_id": None,
                "license_name": None,
                "license_url": None,
                "base_models_json": "[]",
                "supported_languages_json": "[]",
                "capabilities_json": "[]",
                "intended_use_short": None,
                "limitations_short": None,
                "training_data_summary": None,
                "training_cutoff": None,
            },
        ]
        with self.engine.begin() as conn:
            for row in rows:
                conn.execute(insert(models_table).values(**row))

    def test_build_model_card_audit_summary_reports_expected_counts(self) -> None:
        summary = build_model_card_audit_summary(self.engine)

        self.assertEqual(summary["active_model_count"], 4)
        field_coverage = {entry["field"]: entry for entry in summary["field_coverage"]}
        self.assertEqual(field_coverage["huggingface_repo_id"]["filled_count"], 3)
        self.assertEqual(field_coverage["model_card_url"]["filled_count"], 2)
        self.assertEqual(field_coverage["intended_use_short"]["filled_count"], 2)

        self.assertEqual(summary["metadata_source_counts"], {"openrouter": 3, "<null>": 1})
        self.assertEqual(summary["model_card_source_counts"], {"huggingface": 2, "<null>": 2})

        self.assertEqual(summary["gap_counts"]["models_without_any_model_metadata"], 1)
        self.assertEqual(summary["gap_counts"]["huggingface_repo_without_model_card_url"], 1)
        self.assertEqual(summary["gap_counts"]["huggingface_repo_without_rich_text_sections"], 1)
        self.assertEqual(summary["gap_counts"]["model_card_without_license"], 1)
        self.assertEqual(summary["gap_counts"]["model_card_without_base_models_or_languages"], 1)
        self.assertEqual(summary["gap_counts"]["models_with_generic_license_marker"], 0)
        self.assertEqual(summary["gap_counts"]["models_with_license_but_no_license_url"], 0)
        self.assertEqual(summary["derivative_provenance"]["derivative_models"], 1)
        self.assertEqual(summary["derivative_provenance"]["review_only"], 1)
        self.assertEqual(summary["derivative_provenance"]["production_blocked"], 0)
        self.assertEqual(summary["derivative_provenance"]["missing_training_data_summary"], 0)

        self.assertEqual(summary["suspicious_value_counts"]["intended_use_contains_code_fence"], 1)
        self.assertEqual(summary["suspicious_value_counts"]["repo_url_points_to_non_repo_asset"], 1)
        self.assertEqual(summary["suspicious_value_counts"]["documentation_url_points_to_code_file"], 1)
        self.assertEqual(summary["suspicious_value_counts"]["training_data_contains_code_fence"], 1)
        self.assertEqual(len(summary["suspicious_examples"]), 1)
        self.assertEqual(summary["suspicious_examples"][0]["name"], "Suspicious Model")

    def test_format_model_card_audit_summary_includes_key_sections(self) -> None:
        summary = build_model_card_audit_summary(self.engine)

        output = format_model_card_audit_summary(summary)

        self.assertIn("Active models: 4", output)
        self.assertIn("Field coverage:", output)
        self.assertIn("Gap counts:", output)
        self.assertIn("Derivative provenance:", output)
        self.assertIn("Suspicious value counts:", output)
        self.assertIn("Suspicious Model [Mistral]", output)


if __name__ == "__main__":
    unittest.main()
