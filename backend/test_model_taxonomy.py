from __future__ import annotations

import unittest

from backend.model_taxonomy import infer_model_identity


class ModelTaxonomyTests(unittest.TestCase):
    def test_kimi_decimal_variants_keep_family_and_canonical_order(self) -> None:
        identity = infer_model_identity("Kimi k2.5 Instant", "Moonshot")

        self.assertEqual(identity.family_name, "Kimi K2")
        self.assertEqual(identity.canonical_model_name, "Kimi K2.5 Instant")
        self.assertEqual(identity.canonical_model_id, "kimi::kimi-k2-5-instant")

    def test_generic_variant_number_prefix_stays_in_order(self) -> None:
        identity = infer_model_identity("Mistral Large 3", "Mistral")

        self.assertEqual(identity.family_name, "Mistral Large 3")
        self.assertEqual(identity.canonical_model_name, "Mistral Large 3")

    def test_vendor_prefixes_are_removed_before_parsing(self) -> None:
        identity = infer_model_identity("NVIDIA Nemotron 3 Nano", "NVIDIA")

        self.assertEqual(identity.family_name, "Nemotron 3")
        self.assertEqual(identity.canonical_model_name, "Nemotron 3 Nano")

    def test_provider_wrappers_and_platform_noise_do_not_pollute_names(self) -> None:
        identity = infer_model_identity("Google Gemma 3 27B It Hf Nebius", "Unknown")

        self.assertEqual(identity.family_name, "Gemma 3")
        self.assertEqual(identity.canonical_model_name, "Gemma 3 27B It")

    def test_year_and_month_suffixes_are_dropped(self) -> None:
        identity = infer_model_identity("Phi 3 Mini 4k Instruct June 2024", "Microsoft")

        self.assertEqual(identity.canonical_model_name, "Phi 3 Mini Instruct")

    def test_numeric_suffixes_with_letters_render_as_decimals(self) -> None:
        identity = infer_model_identity("GLM-4.1V w/ Thinking", "Unknown")

        self.assertEqual(identity.family_name, "GLM 4")
        self.assertEqual(identity.canonical_model_name, "GLM 4.1V")

    def test_trailing_build_stamp_collapses_preview_snapshots(self) -> None:
        july = infer_model_identity("Kimi k2 0711 Preview", "Moonshot")
        september = infer_model_identity("Kimi k2 0905 Preview", "Moonshot")

        self.assertEqual(july.canonical_model_name, "Kimi K2")
        self.assertEqual(september.canonical_model_name, "Kimi K2")
        self.assertEqual(july.canonical_model_id, september.canonical_model_id)

    def test_trailing_build_stamp_keeps_variant_but_drops_snapshot_suffix(self) -> None:
        identity = infer_model_identity("Kimi K2-Instruct-0905", "Moonshot AI")

        self.assertEqual(identity.family_name, "Kimi K2")
        self.assertEqual(identity.canonical_model_name, "Kimi K2 Instruct")

    def test_split_date_pair_build_suffix_is_collapsed(self) -> None:
        identity = infer_model_identity("Gemini 2.5 Pro 05-06", "Google")

        self.assertEqual(identity.family_name, "Gemini 2.5")
        self.assertEqual(identity.canonical_model_name, "Gemini 2.5 Pro")

    def test_openai_compact_alphanumeric_versions_stay_in_family(self) -> None:
        identity = infer_model_identity("GPT-4o mini", "OpenAI")

        self.assertEqual(identity.family_name, "GPT 4O")
        self.assertEqual(identity.family_id, "openai::gpt-4o")
        self.assertEqual(identity.canonical_model_name, "GPT 4O Mini")

    def test_openai_vision_variant_does_not_collapse_to_plain_gpt(self) -> None:
        identity = infer_model_identity("GPT-4V(ision) (Playground)", "OpenAI")

        self.assertEqual(identity.family_name, "GPT 4V")
        self.assertEqual(identity.family_id, "openai::gpt-4v")
        self.assertEqual(identity.canonical_model_name, "GPT 4V Playground")

    def test_openai_oss_size_is_part_of_family(self) -> None:
        identity = infer_model_identity("gpt-oss-120B (low)", "OpenAI")

        self.assertEqual(identity.family_name, "GPT OSS 120B")
        self.assertEqual(identity.family_id, "openai::gpt-oss-120b")
        self.assertEqual(identity.canonical_model_name, "GPT OSS 120B Low")


if __name__ == "__main__":
    unittest.main()
