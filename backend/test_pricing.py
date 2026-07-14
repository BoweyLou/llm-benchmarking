from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import select, update

from backend import catalog_export, pricing, update_engine
from backend.database import (
    fetch_all,
    get_engine,
    init_db,
    model_pricing_components,
    model_pricing_offers,
    models,
    source_runs,
)


class PricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = init_db(get_engine("sqlite:///:memory:"))
        with self.engine.begin() as conn:
            conn.execute(
                models.insert().values(
                    id="gpt-5-6-sol",
                    name="GPT-5.6 Sol",
                    provider="OpenAI",
                    provider_id=None,
                    canonical_model_id="openai::gpt-5-6-sol",
                    canonical_model_name="GPT-5.6 Sol",
                    openrouter_model_id="openai/gpt-5.6-sol",
                )
            )

    def test_official_table_parser_preserves_cached_and_tier_prices(self) -> None:
        html = """
        <table><tr><th>Model</th><th>Input / 1M tokens</th><th>Cached input / 1M tokens</th><th>Output / 1M tokens</th></tr>
        <tr><td>GPT-5.6 Sol Standard</td><td>$5.00</td><td>$0.50</td><td>$30.00</td></tr></table>
        """
        offers = pricing.parse_official_pricing_html("openai", html)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["service_tier"], "standard")
        self.assertEqual(
            [component["charge_type"] for component in offers[0]["components"]],
            ["input", "cached_input", "output"],
        )
        self.assertEqual(offers[0]["components"][2]["amount"], 30.0)

    def test_openai_live_shape_preserves_short_context_prices_and_legacy_scalars(self) -> None:
        html = """
        <astro-island props='{"tier":[0,"standard"]}'></astro-island><table>
        <tr><th></th><th colspan="4">Short context</th><th colspan="4">Long context</th></tr>
        <tr><th>Model</th><th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th>
        <th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th></tr>
        <tr><td>gpt-5.6-sol</td><td>$5.00</td><td>$0.50</td><td>$6.25</td><td>$30.00</td>
        <td>$10.00</td><td>$1.00</td><td>$12.50</td><td>$45.00</td></tr></table>
        """
        offers = pricing.parse_official_pricing_html("openai", html)
        sol = offers[0]
        self.assertEqual(
            [(item["charge_type"], item["amount"], item["conditions"]["context_band"]) for item in sol["components"]],
            [
                ("input", 5.0, "short"), ("cached_input", 0.5, "short"),
                ("cache_write", 6.25, "short"), ("output", 30.0, "short"),
                ("input", 10.0, "long"), ("cached_input", 1.0, "long"),
                ("cache_write", 12.5, "long"), ("output", 45.0, "long"),
            ],
        )
        result = pricing.persist_parsed_source("openai", offers, engine=self.engine)
        self.assertEqual(result["component_count"], 8)
        with self.engine.begin() as conn:
            row = conn.execute(select(models).where(models.c.id == "gpt-5-6-sol")).mappings().one()
        self.assertEqual(row["price_input_per_mtok"], 5.0)
        self.assertEqual(row["price_output_per_mtok"], 30.0)

    def test_openai_canary_is_checked_in_source_even_when_catalog_has_no_canary_model(self) -> None:
        engine = init_db(get_engine("sqlite:///:memory:"))
        with engine.begin() as conn:
            conn.execute(models.insert().values(id="gpt-5-5", name="GPT 5.5", provider="OpenAI"))
        parsed = [
            {
                "published_model_id": name, "provider_model_id": name, "service_tier": "standard",
                "currency": "USD", "price_status": "published", "constraints": {}, "raw": [name],
                "components": [{"modality": "text", "charge_type": "input", "amount": amount, "billing_unit": "token", "unit_quantity": 1_000_000, "conditions": {}}],
            }
            for name, amount in (("gpt-5.6-sol", 5.0), ("gpt-5.5", 5.0))
        ]
        result = pricing.persist_parsed_source("openai", parsed, engine=engine)
        self.assertEqual(result["offer_count"], 1)
        self.assertEqual(result["unmatched_count"], 1)

    def test_duplicate_components_are_removed_before_insert(self) -> None:
        component = {"modality": "text", "charge_type": "usage", "amount": 0.0, "billing_unit": "token", "unit_quantity": 1_000_000, "conditions": {}}
        parsed = [{
            "published_model_id": "GPT-5.6 Sol", "provider_model_id": "gpt-5.6-sol", "service_tier": "standard",
            "currency": "USD", "price_status": "free", "constraints": {}, "raw": ["duplicate"],
            "components": [component, dict(component)],
        }]
        result = pricing.persist_parsed_source("openai", parsed, engine=self.engine)
        self.assertEqual(result["component_count"], 1)
        with self.engine.begin() as conn:
            rows = fetch_all(conn, select(model_pricing_components))
        self.assertEqual(len(rows), 1)

    def test_google_section_heading_becomes_model_identity(self) -> None:
        html = """
        <h2>Gemini 3.5 Flash</h2><h3>Standard</h3><table>
        <tr><th></th><th>Free Tier</th><th>Paid Tier, per 1M tokens in USD</th></tr>
        <tr><td>Input price</td><td>Free</td><td>$1.50</td></tr>
        <tr><td>Output price (including thinking tokens)</td><td>Free</td><td>$9.00</td></tr>
        </table>
        """
        offers = pricing.parse_official_pricing_html("google", html)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["published_model_id"], "Gemini 3.5 Flash")
        self.assertEqual([item["charge_type"] for item in offers[0]["components"]], ["input", "output"])

    def test_provider_specific_non_token_units_are_preserved(self) -> None:
        google = pricing.parse_official_pricing_html(
            "google",
            """<h2>Gemini 3.5 Flash</h2><h3>Standard</h3><table>
            <tr><th></th><th>Free</th><th>Paid</th></tr>
            <tr><td>Context caching price</td><td>Free</td><td>$0.15$1.00 / 1,000,000 tokens per hour (storage price)</td></tr>
            </table>""",
        )[0]
        self.assertEqual(
            [(item["charge_type"], item["billing_unit"]) for item in google["components"]],
            [("cached_input", "token"), ("cache_storage", "token_hour")],
        )
        mistral = pricing.parse_official_pricing_html(
            "mistral",
            """<mistral-block-card-model><p class="text-h5">Voxtral Mini Transcribe 2</p>
            <p>Audio Input/min</p><mistral-atom-text-price data-prices="{&quot;priceUsd&quot;:0.003}"></mistral-atom-text-price>
            </mistral-block-card-model>""",
        )[0]
        self.assertEqual((mistral["components"][0]["modality"], mistral["components"][0]["billing_unit"]), ("audio", "minute"))
        cohere = pricing.parse_official_pricing_html(
            "cohere",
            '"modelName":"Rerank 4 Fast","per":"1M tokens","pricings":[{"inputLabel":"Cost","inputPrice":2,"outputLabel":"Output","overridePer":"1K searches"}]',
        )[0]
        self.assertEqual((cohere["components"][0]["billing_unit"], cohere["components"][0]["unit_quantity"]), ("search", 1000.0))

    def test_anthropic_live_headers_preserve_cache_and_batch_semantics(self) -> None:
        html = """
        <table><tr><th>Model</th><th>Base Input Tokens</th><th>5m Cache Writes</th>
        <th>1h Cache Writes</th><th>Cache Hits &amp; Refreshes</th><th>Output Tokens</th></tr>
        <tr><td>Claude Opus 4.8</td><td>$5 / MTok</td><td>$6.25 / MTok</td>
        <td>$10 / MTok</td><td>$0.50 / MTok</td><td>$25 / MTok</td></tr></table>
        <table><tr><th>Model</th><th>Batch input</th><th>Batch output</th></tr>
        <tr><td>Claude Opus 4.8</td><td>$2.50 / MTok</td><td>$12.50 / MTok</td></tr></table>
        """
        offers = pricing.parse_official_pricing_html("anthropic", html)
        standard = next(item for item in offers if item["service_tier"] == "standard")
        batch = next(item for item in offers if item["service_tier"] == "batch")
        cache_hit = next(item for item in standard["components"] if item["conditions"].get("cache_operation"))
        self.assertEqual((cache_hit["charge_type"], cache_hit["amount"]), ("cached_input", 0.5))
        self.assertEqual(
            [(item["charge_type"], item["amount"]) for item in batch["components"]],
            [("input", 2.5), ("output", 12.5)],
        )

    def test_xai_live_media_headers_preserve_per_image_rates(self) -> None:
        html = """
        <table><tr><th>Model</th><th>Media Input</th><th>Resolution</th><th>Output</th></tr>
        <tr><td>grok-imagine-image-qualityText, Image → Image</td><td>$0.01 / img</td><td>1K</td><td>$0.05 / img</td></tr>
        <tr><td>2K</td><td>$0.07 / img</td></tr></table>
        """
        offer = pricing.parse_official_pricing_html("xai", html)[0]
        self.assertEqual(offer["published_model_id"], "grok-imagine-image-quality")
        self.assertEqual(
            [(item["modality"], item["charge_type"], item["amount"], item["billing_unit"], item["unit_quantity"]) for item in offer["components"]],
            [
                ("image", "input", 0.01, "image", 1.0),
                ("image", "output", 0.05, "image", 1.0),
                ("image", "output", 0.07, "image", 1.0),
            ],
        )

    def test_xai_capability_and_resolution_rows_are_not_model_identities(self) -> None:
        html = """
        <table><tr><th>Model</th><th>Input / 1M tokens</th><th>Output / image</th></tr>
        <tr><td>grok-imagine-image-qualityText, Image → Image</td><td>$2.00</td><td>$0.07</td></tr>
        <tr><td>2K</td><td>-</td><td>$0.14</td></tr></table>
        """
        offers = pricing.parse_official_pricing_html("xai", html)
        self.assertEqual([item["published_model_id"] for item in offers], ["grok-imagine-image-quality"])
        self.assertEqual(len(offers[0]["components"]), 3)
        self.assertEqual(offers[0]["components"][-1]["conditions"]["resolution"], "2K")

    def test_refresh_is_atomic_and_preserves_last_known_good(self) -> None:
        parsed = [
            {
                "published_model_id": "GPT-5.6 Sol",
                "provider_model_id": "gpt-5.6-sol",
                "service_tier": "standard",
                "currency": "USD",
                "price_status": "published",
                "constraints": {},
                "raw": ["GPT-5.6 Sol", "$5", "$30"],
                "components": [
                    {"modality": "text", "charge_type": "input", "amount": 5.0, "billing_unit": "token", "unit_quantity": 1_000_000, "conditions": {}},
                    {"modality": "text", "charge_type": "output", "amount": 30.0, "billing_unit": "token", "unit_quantity": 1_000_000, "conditions": {}},
                ],
            }
        ]
        result = pricing.persist_parsed_source("openai", parsed, engine=self.engine)
        self.assertEqual(result["component_count"], 2)
        with self.assertRaises(pricing.PricingRefreshRejected):
            pricing.persist_parsed_source("openai", [], engine=self.engine)
        with self.engine.begin() as conn:
            active = fetch_all(conn, select(model_pricing_offers).where(model_pricing_offers.c.active == 1))
            row = conn.execute(select(models).where(models.c.id == "gpt-5-6-sol")).mappings().one()
        self.assertEqual(len(active), 1)
        self.assertEqual(row["price_input_per_mtok"], 5.0)
        self.assertEqual(row["price_output_per_mtok"], 30.0)

    def test_stale_offers_remain_auditable_but_leave_summary(self) -> None:
        self.test_refresh_is_atomic_and_preserves_last_known_good()
        stale_at = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat().replace("+00:00", "Z")
        with self.engine.begin() as conn:
            conn.execute(update(model_pricing_offers).values(verified_at=stale_at))
            offers = pricing.load_pricing_offers(conn, ["gpt-5-6-sol"])["gpt-5-6-sol"]
        payload = pricing.attach_pricing({"id": "gpt-5-6-sol", "inference_destinations": []}, offers)
        self.assertTrue(offers[0]["provenance"]["stale"])
        self.assertEqual(payload["pricing_summary"]["offer_count"], 0)
        self.assertEqual(payload["pricing_summary"]["stale_offer_count"], 1)

    def test_openrouter_and_cloud_components_are_normalized(self) -> None:
        router = pricing.sync_openrouter_items(
            [
                {
                    "id": "openai/gpt-5.6-sol",
                    "name": "OpenAI: GPT-5.6 Sol",
                    "pricing": {
                        "prompt": "0.000005",
                        "completion": "0.00003",
                        "input_cache_read": "0.0000005",
                        "web_search": "0.01",
                    },
                }
            ],
            engine=self.engine,
        )
        self.assertEqual(router["component_count"], 4)
        cloud = pricing.persist_cloud_pricing(
            engine=self.engine,
            destination_id="aws-bedrock",
            source_url="https://example.test/aws-pricing",
            source_label="AWS Price List API",
            records=[
                {
                    "model_id": "gpt-5-6-sol",
                    "catalog_model_id": "gpt-5-6-sol",
                    "_pricing_entries": [
                        {"catalog_model_id": "gpt-5-6-sol", "region": "us-east-1", "price_kind": "input", "price_per_mtok": 5.5, "unit": "1M tokens"},
                        {"catalog_model_id": "gpt-5-6-sol", "region": "us-east-1", "price_kind": "output", "price_per_mtok": 31.0, "unit": "1M tokens"},
                    ],
                }
            ],
        )
        self.assertEqual(cloud["component_count"], 2)
        with self.engine.begin() as conn:
            component_rows = fetch_all(conn, select(model_pricing_components))
        self.assertEqual(len(component_rows), 6)

    def test_openrouter_overrides_and_current_multimodal_fields_are_preserved(self) -> None:
        router = pricing.sync_openrouter_items(
            [
                {
                    "id": "openai/gpt-5.6-sol",
                    "name": "OpenAI: GPT-5.6 Sol",
                    "pricing": {
                        "prompt": "0.000005", "completion": "0.00003",
                        "image_output": "0.00004", "image_token": "0.00005",
                        "input_cache_write_1h": "0.00001",
                        "input_audio_cache": "0.0000003", "audio_output": "0.000002",
                        "overrides": [{"min_prompt_tokens": 272000, "prompt": "0.00001", "completion": "0.000045"}],
                    },
                }
            ],
            engine=self.engine,
        )
        self.assertEqual(router["offer_count"], 2)
        self.assertEqual(router["component_count"], 9)
        with self.engine.begin() as conn:
            offers = pricing.load_pricing_offers(conn, ["gpt-5-6-sol"])["gpt-5-6-sol"]
        override = next(item for item in offers if item["constraints"].get("pricing_override"))
        self.assertEqual(override["constraints"]["pricing_override"]["min_prompt_tokens"], 272000)
        base = next(item for item in offers if not item["constraints"].get("pricing_override"))
        component_index = {(item["modality"], item["charge_type"], tuple(sorted(item["conditions"].items()))): item for item in base["components"]}
        self.assertEqual(component_index[("image", "output", (("source_field", "image_output"),))]["billing_unit"], "token")
        self.assertEqual(component_index[("audio", "cached_input", ())]["amount"], 0.3)
        self.assertEqual(component_index[("text", "cache_write", (("cache_duration", "1h"),))]["amount"], 10.0)

    def test_pricing_csv_is_one_component_per_row_with_provenance(self) -> None:
        self.test_refresh_is_atomic_and_preserves_last_known_good()
        with self.engine.begin() as conn:
            offers = pricing.load_pricing_offers(conn, ["gpt-5-6-sol"])["gpt-5-6-sol"]
        model = pricing.attach_pricing(
            {"id": "gpt-5-6-sol", "name": "GPT-5.6 Sol", "provider": "OpenAI", "inference_destinations": []},
            offers,
        )
        bundle = catalog_export.render_model_metadata_csv_bundle([model])
        csv_text = bundle["pricing-offers"]
        self.assertEqual(len(csv_text.strip().splitlines()), 3)
        self.assertIn("OpenAI API pricing", csv_text)
        self.assertIn("https://developers.openai.com/api/docs/pricing", csv_text)

    def test_canonical_merge_moves_pricing_without_losing_components(self) -> None:
        self.test_refresh_is_atomic_and_preserves_last_known_good()
        with self.engine.begin() as conn:
            conn.execute(models.insert().values(id="canonical-sol", name="Canonical Sol", provider="OpenAI"))
            self.assertTrue(update_engine._merge_model_into_target(conn, "gpt-5-6-sol", "canonical-sol"))
            offers = fetch_all(conn, select(model_pricing_offers).where(model_pricing_offers.c.model_id == "canonical-sol"))
            components = fetch_all(conn, select(model_pricing_components))
        self.assertEqual(len(offers), 1)
        self.assertEqual(len(components), 2)

    def test_canonical_merge_resolves_active_offer_collision_and_preserves_foreign_keys(self) -> None:
        self.test_refresh_is_atomic_and_preserves_last_known_good()
        with self.engine.begin() as conn:
            conn.execute(models.insert().values(id="canonical-sol", name="Canonical Sol", provider="OpenAI"))
            duplicate_offer = conn.execute(
                select(model_pricing_offers).where(model_pricing_offers.c.model_id == "gpt-5-6-sol")
            ).mappings().one()
            copied = {key: value for key, value in duplicate_offer.items() if key != "id"}
            copied["model_id"] = "canonical-sol"
            copied["offer_key"] = "same-route-different-price"
            canonical_offer_id = conn.execute(model_pricing_offers.insert().values(**copied)).inserted_primary_key[0]
            pricing.merge_model_pricing(conn, "gpt-5-6-sol", "canonical-sol")
            self.assertEqual(
                conn.execute(select(model_pricing_offers).where(model_pricing_offers.c.model_id == "gpt-5-6-sol")).all(),
                [],
            )
            offers = fetch_all(conn, select(model_pricing_offers).where(model_pricing_offers.c.model_id == "canonical-sol"))
            components = fetch_all(conn, select(model_pricing_components))
            runs = fetch_all(conn, select(source_runs))
        self.assertEqual(len(offers), 2)
        self.assertEqual(sum(int(item["active"]) for item in offers), 1)
        self.assertEqual(int(next(item for item in offers if item["id"] == canonical_offer_id)["active"]), 1)
        self.assertEqual(len(components), 2)
        self.assertEqual(len(runs), 1)


if __name__ == "__main__":
    unittest.main()
