from __future__ import annotations

import csv
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient

from backend import cli, main, review_export


EXPORTED_AT = "2026-07-15T05:30:00Z"


def _suggestion(
    use_case_id: str,
    label: str,
    *,
    fit_score: float,
    confidence: float,
) -> dict[str, object]:
    return {
        "use_case_id": use_case_id,
        "label": label,
        "fit_score": fit_score,
        "confidence": confidence,
        "reasons": ["Strong metric fit"],
        "warnings": ["Human review still required"],
        "required_controls": ["Monitor quality"],
        "policy_version": "au-bank-v3",
        "computed_at": "2026-07-15T04:00:00Z",
    }


def _offer(
    offer_id: int,
    *,
    destination_id: str,
    region: str | None,
    amount_input: float | None = 2.0,
    amount_output: float | None = 8.0,
    stale: bool = False,
    price_status: str = "published",
    service_tier: str = "standard",
) -> dict[str, object]:
    components: list[dict[str, object]] = []
    if amount_input is not None:
        components.append(
            {
                "modality": "text",
                "charge_type": "input",
                "amount": amount_input,
                "billing_unit": "token",
                "unit_quantity": 1_000_000,
                "conditions": {"cache": "miss"},
            }
        )
    if amount_output is not None:
        components.append(
            {
                "modality": "text",
                "charge_type": "output",
                "amount": amount_output,
                "billing_unit": "token",
                "unit_quantity": 1_000_000,
                "conditions": {"batch": False},
            }
        )
    return {
        "id": offer_id,
        "destination_id": destination_id,
        "provider_model_id": "provider/alpha",
        "service_tier": service_tier,
        "region": region,
        "currency": "AUD" if region == "ap-southeast-2" else "USD",
        "constraints": {"minimum_commitment": "none"},
        "price_status": price_status,
        "components": components,
        "provenance": {
            "kind": "official_api",
            "label": "Official price API",
            "url": "https://example.com/pricing",
            "verified_at": "2026-07-15T03:00:00Z",
            "stale": stale,
        },
    }


def _catalog() -> dict[str, object]:
    alpha_a = {
        "id": "alpha-a",
        "review_entity_id": "alpha-group",
        "name": "Alpha",
        "provider": "Example Provider",
        "canonical_model_id": "example::alpha",
        "model_roles": ["generator"],
        "general_approval_status": "approved",
        "general_approval_notes": "Approved in source A",
        "general_approval_updated_at": "2026-07-14T01:00:00Z",
        "general_recommendation_status": "recommended",
        "general_recommendation_notes": "Recommended in source A",
        "general_recommendation_updated_at": "2026-07-14T02:00:00Z",
        "usage_classification": "standard",
        "usage_classification_notes": "Standard approved use.",
        "usage_classification_updated_at": "2026-07-14T03:00:00Z",
        "suggested_use_cases": [
            _suggestion("customer_support", "Customer support", fit_score=0.91, confidence=0.82)
        ],
        "use_case_approvals": {
            "legacy_case": {
                "approved_for_use": True,
                "recommendation_status": "recommended",
                "recommendation_notes": "LEGACY-DECISION-MUST-NOT-EXPORT",
            }
        },
        "inference_destinations": [
            {
                "id": "aws-bedrock",
                "name": "AWS Bedrock",
                "hyperscaler": "AWS",
                "availability_scope": "Account + region scoped",
                "availability_note": "Synced Bedrock evidence.",
                "location_scope": "Published Bedrock regions",
                "regions": ["us-east-1", "ap-southeast-2"],
                "deployment_modes": ["On-demand"],
                "sources": [{"label": "Catalog API", "url": "https://example.com/aws/catalog"}],
                "availability_evidence_kind": "synced",
                "catalog_model_id": "amazon.alpha-v1",
                "synced_at": "2026-07-15T02:00:00Z",
                "pricing_offers": [
                    _offer(1, destination_id="aws-bedrock", region="ap-southeast-2"),
                    _offer(2, destination_id="aws-bedrock", region="us-east-1", amount_input=1.0, amount_output=4.0),
                    _offer(3, destination_id="aws-bedrock", region=None, amount_input=0.5, amount_output=2.0),
                    _offer(4, destination_id="aws-bedrock", region="ap-southeast-2", stale=True),
                    _offer(
                        5,
                        destination_id="aws-bedrock",
                        region="ap-southeast-2",
                        amount_input=None,
                        amount_output=None,
                        price_status="unavailable",
                    ),
                    _offer(
                        6,
                        destination_id="aws-bedrock",
                        region="ap-southeast-2",
                        amount_input=0,
                        amount_output=0,
                        price_status="free",
                    ),
                ],
            },
            {
                "id": "azure-ai-foundry",
                "name": "Azure AI Foundry",
                "hyperscaler": "Azure",
                "availability_scope": "Account + deployment scoped",
                "availability_note": "Fallback Foundry route.",
                "location_scope": "Common Foundry regions",
                "regions": ["australiaeast"],
                "deployment_modes": ["Serverless"],
                "sources": [{"label": "Catalog docs", "url": "https://example.com/azure/catalog"}],
                "availability_evidence_kind": "curated_fallback",
                "pricing_offers": [],
            },
            {
                "id": "google-vertex-ai",
                "name": "Google Vertex AI",
                "hyperscaler": "Google Cloud",
                "availability_scope": "Project + region scoped",
                "availability_note": "Published Vertex endpoints.",
                "location_scope": "Published Vertex endpoints",
                "regions": ["global", "australia-southeast1"],
                "deployment_modes": ["Publisher endpoint"],
                "sources": [{"label": "Endpoint docs", "url": "https://example.com/vertex/catalog"}],
                "availability_evidence_kind": "curated_fallback",
                "pricing_offers": [
                    _offer(7, destination_id="google-vertex-ai", region="global", amount_input=3.0, amount_output=9.0)
                ],
            },
            {
                "id": "provider-direct",
                "name": "Provider Direct",
                "hyperscaler": "Direct",
                "availability_scope": "Provider account scoped",
                "availability_note": "Provider chooses processing location.",
                "location_scope": "Provider managed",
                "regions": [],
                "deployment_modes": ["API"],
                "sources": [],
                "availability_evidence_kind": "curated_fallback",
                "pricing_offers": [],
            },
            {
                "id": "provider-router",
                "name": "Provider Router",
                "hyperscaler": "Router",
                "availability_scope": "Router account scoped",
                "availability_note": "Router chooses provider.",
                "location_scope": "Provider routed",
                "regions": [],
                "deployment_modes": ["Router API"],
                "sources": [],
                "availability_evidence_kind": "curated_fallback",
                "pricing_offers": [],
            },
            {
                "id": "unknown-route",
                "name": "Unknown Route",
                "hyperscaler": "Provider",
                "availability_scope": "Published route",
                "availability_note": "No region detail.",
                "location_scope": "Account scoped",
                "regions": [],
                "deployment_modes": [],
                "sources": [],
                "availability_evidence_kind": "pricing_only",
                "pricing_offers": [],
            },
        ],
    }
    alpha_b = {
        **alpha_a,
        "id": "alpha-b",
        "provider": "Second Provider",
        "general_approval_status": "not_approved",
        "general_approval_notes": "Not approved in source B",
        "general_recommendation_status": "legacy_supported",
        "general_recommendation_notes": "Legacy supported in source B",
        "usage_classification": "restricted",
        "usage_classification_notes": "Restricted in source B",
        "suggested_use_cases": [
            _suggestion("customer_support", "Customer support", fit_score=0.86, confidence=0.79),
            _suggestion("document_summary", "Document summary", fit_score=0.74, confidence=0.68),
        ],
        "inference_destinations": [],
    }
    beta = {
        "id": "beta-only",
        "review_entity_id": "beta-group",
        "name": "Beta",
        "provider": "Other Provider",
        "canonical_model_id": "other::beta",
        "model_roles": ["embedding"],
        "general_approval_status": "unreviewed",
        "general_recommendation_status": "unrated",
        "usage_classification": "unclassified",
        "suggested_use_cases": [],
        "inference_destinations": [],
    }
    return {
        "schema_version": 6,
        "generated_at": EXPORTED_AT,
        "models": [alpha_a, alpha_b, beta],
    }


def _edge_catalog(destinations: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 6,
        "generated_at": EXPORTED_AT,
        "models": [
            {
                "id": "edge-model",
                "review_entity_id": "edge-model",
                "name": "Edge model",
                "provider": "Example",
                "model_roles": ["generator"],
                "general_approval_status": "approved",
                "general_recommendation_status": "recommended",
                "usage_classification": "standard",
                "suggested_use_cases": [],
                "inference_destinations": destinations,
            }
        ],
    }


def _archive_rows(
    *,
    model_ids: list[str] | None = None,
) -> tuple[review_export.ModelGuideArchive, list[dict[str, str]], list[dict[str, str]], str]:
    archive = review_export.build_model_guide_archive(
        catalog=_catalog(),
        model_ids=model_ids,
        exported_at=EXPORTED_AT,
    )
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        models = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
        costs = list(csv.DictReader(io.StringIO(bundle.read("inference-costs.csv").decode("utf-8-sig"))))
        readme = bundle.read("README.txt").decode("utf-8")
    return archive, models, costs, readme


class ReviewModelGuideExportTests(unittest.TestCase):
    def test_archive_has_readable_models_costs_and_legend_members(self) -> None:
        catalog = {
            "schema_version": 6,
            "generated_at": "2026-07-15T05:30:00Z",
            "models": [
                {
                    "id": "alpha-source",
                    "review_entity_id": "alpha-group",
                    "name": "Alpha",
                    "provider": "Example Provider",
                    "model_roles": ["generator"],
                    "general_approval_status": "approved",
                    "general_recommendation_status": "acceptable",
                    "usage_classification": "standard",
                    "suggested_use_cases": [],
                    "inference_destinations": [],
                }
            ],
        }

        archive = review_export.build_model_guide_archive(
            catalog=catalog,
            exported_at=EXPORTED_AT,
        )

        self.assertEqual(archive.filename, "llm-model-guide-20260715T053000Z.zip")
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            self.assertEqual(bundle.namelist(), ["models.csv", "inference-costs.csv", "README.txt"])
            model_rows = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
            cost_rows = list(csv.DictReader(io.StringIO(bundle.read("inference-costs.csv").decode("utf-8-sig"))))
            readme = bundle.read("README.txt").decode("utf-8")

        self.assertEqual(list(model_rows[0]), review_export.MODEL_FIELDS)
        self.assertEqual(list(cost_rows[0]), review_export.INFERENCE_COST_FIELDS)
        self.assertEqual(model_rows[0]["model_group_id"], "alpha-group")
        self.assertEqual(model_rows[0]["general_recommendation_status"], "acceptable")
        self.assertEqual(cost_rows[0]["price_evidence_state"], "no_known_route")
        self.assertIn("Suggested use cases are read-only metric evidence", readme)
        self.assertIn("curated_fallback", readme)
        self.assertIn("possible route, not confirmed model availability", readme)
        self.assertIn("custom", readme)
        self.assertIn("acceptable means okay for normal use", readme)
        self.assertIn("unrated is displayed in the review UI as\nNot Assessed", readme)

    def test_grouped_decisions_are_mixed_only_on_source_disagreement(self) -> None:
        _, models, _, readme = _archive_rows()
        alpha = next(row for row in models if row["model_group_id"] == "alpha-group")
        beta = next(row for row in models if row["model_group_id"] == "beta-group")

        self.assertEqual(alpha["source_record_count"], "2")
        self.assertEqual(alpha["source_record_ids"], "alpha-a; alpha-b")
        self.assertEqual(alpha["provider"], "Multiple providers")
        self.assertEqual(alpha["general_approval_status"], "mixed")
        self.assertEqual(alpha["general_recommendation_status"], "mixed")
        self.assertEqual(alpha["usage_classification"], "mixed")
        self.assertEqual(alpha["usage_classification_notes"], "Standard approved use.; Restricted in source B")
        self.assertEqual(beta["general_approval_status"], "unreviewed")
        self.assertEqual(beta["general_recommendation_status"], "unrated")
        self.assertEqual(beta["usage_classification"], "unclassified")
        self.assertNotEqual(beta["general_approval_status"], "mixed")
        self.assertIn("mixed", readme)
        self.assertIn("usage classification", readme)
        self.assertIn("independent", readme)

    def test_missing_server_owned_review_entity_id_fails_closed(self) -> None:
        catalog = {
            "schema_version": 6,
            "models": [
                {
                    "id": "missing-review-entity",
                    "name": "Missing identity",
                    "provider": "Example",
                    "general_approval_status": "unreviewed",
                    "general_recommendation_status": "unrated",
                    "suggested_use_cases": [],
                    "inference_destinations": [],
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "server-owned review_entity_id"):
            review_export.build_model_guide_archive(
                catalog=catalog,
                exported_at=EXPORTED_AT,
            )

    def test_suggested_use_cases_are_read_only_metric_evidence_not_legacy_decisions(self) -> None:
        _, models, _, _ = _archive_rows()
        alpha = next(row for row in models if row["model_group_id"] == "alpha-group")

        self.assertEqual(alpha["suggested_use_cases_read_only"], "yes - metric evidence only")
        self.assertEqual(alpha["suggested_use_case_count"], "2")
        self.assertEqual(alpha["suggested_use_cases"], "Customer support; Document summary")
        self.assertIn("fit 0.91", alpha["suggested_use_case_evidence"])
        self.assertIn("confidence 0.82", alpha["suggested_use_case_evidence"])
        self.assertIn("policy au-bank-v3", alpha["suggested_use_case_evidence"])
        self.assertIn("computed 2026-07-15T04:00:00Z", alpha["suggested_use_case_evidence"])
        self.assertNotIn("LEGACY-DECISION-MUST-NOT-EXPORT", "\n".join(alpha.values()))

    def test_inference_costs_are_au_first_and_never_borrow_non_au_prices(self) -> None:
        _, _, costs, _ = _archive_rows(model_ids=["alpha-a"])
        ordered_locations = list(dict.fromkeys(row["location_country"] for row in costs))

        self.assertEqual(
            ordered_locations,
            ["Australia", "United States", "Global", "Provider managed", "Provider routed", "Unknown"],
        )
        regionless = next(row for row in costs if row["offer_id"] == "3" and row["charge_type"] == "input")
        self.assertEqual(regionless["location_country"], "Unknown")
        self.assertEqual(regionless["location_evidence"], "price_only")
        self.assertFalse(
            any(
                row["offer_id"] == "3" and row["location_country"] == "Australia"
                for row in costs
            )
        )
        vertex_au = next(
            row
            for row in costs
            if row["destination_id"] == "google-vertex-ai"
            and row["location_region"] == "australia-southeast1"
        )
        self.assertEqual(vertex_au["location_evidence"], "availability_only")
        self.assertEqual(vertex_au["price_evidence_state"], "availability_only")
        self.assertEqual(vertex_au["offer_id"], "")

    def test_inference_costs_preserve_states_native_units_conditions_and_provenance(self) -> None:
        _, _, costs, _ = _archive_rows(model_ids=["alpha-a"])

        current = next(row for row in costs if row["offer_id"] == "1" and row["charge_type"] == "input")
        stale = next(row for row in costs if row["offer_id"] == "4" and row["charge_type"] == "input")
        unavailable = next(row for row in costs if row["offer_id"] == "5")
        free = next(row for row in costs if row["offer_id"] == "6" and row["charge_type"] == "input")
        azure = next(row for row in costs if row["destination_id"] == "azure-ai-foundry")

        self.assertEqual(current["price_evidence_state"], "current")
        self.assertEqual(current["pricing_is_stale"], "False")
        self.assertEqual(stale["price_evidence_state"], "current")
        self.assertEqual(stale["pricing_is_stale"], "True")
        self.assertEqual(unavailable["price_evidence_state"], "unavailable")
        self.assertEqual(unavailable["pricing_is_stale"], "False")
        self.assertEqual(free["price_evidence_state"], "free")
        self.assertEqual(free["pricing_is_stale"], "False")
        self.assertEqual(current["currency"], "AUD")
        self.assertEqual(current["amount"], "2.0")
        self.assertEqual(current["billing_unit"], "token")
        self.assertEqual(current["unit_quantity"], "1000000")
        self.assertEqual(current["constraints"], '{"minimum_commitment":"none"}')
        self.assertEqual(current["conditions"], '{"cache":"miss"}')
        self.assertEqual(current["source_kind"], "official_api")
        self.assertEqual(current["source_label"], "Official price API")
        self.assertEqual(current["source_url"], "https://example.com/pricing")
        self.assertEqual(current["verified_at"], "2026-07-15T03:00:00Z")
        self.assertEqual(current["availability_evidence_kind"], "synced")
        self.assertEqual(current["availability_catalog_model_id"], "amazon.alpha-v1")
        self.assertEqual(current["availability_synced_at"], "2026-07-15T02:00:00Z")
        self.assertEqual(azure["location_evidence"], "availability_only")
        self.assertEqual(azure["availability_evidence_kind"], "curated_fallback")

    def test_stale_is_independent_from_free_unavailable_and_custom_lifecycle_states(self) -> None:
        destination = {
            "id": "aws-bedrock",
            "name": "AWS Bedrock",
            "hyperscaler": "AWS",
            "availability_scope": "Account + region scoped",
            "availability_note": "Matched Australian route.",
            "location_scope": "Published Bedrock regions",
            "regions": ["ap-southeast-2"],
            "deployment_modes": ["On-demand"],
            "sources": [],
            "availability_evidence_kind": "synced",
            "pricing_offers": [
                _offer(
                    40,
                    destination_id="aws-bedrock",
                    region="ap-southeast-2",
                    amount_input=0,
                    amount_output=0,
                    stale=True,
                    price_status="free",
                ),
                _offer(
                    41,
                    destination_id="aws-bedrock",
                    region="ap-southeast-2",
                    amount_input=None,
                    amount_output=None,
                    stale=True,
                    price_status="unavailable",
                ),
                _offer(
                    42,
                    destination_id="aws-bedrock",
                    region="ap-southeast-2",
                    amount_input=None,
                    amount_output=None,
                    stale=True,
                    price_status="custom",
                ),
            ],
        }
        archive = review_export.build_model_guide_archive(
            catalog=_edge_catalog([destination]),
            exported_at=EXPORTED_AT,
        )
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            rows = list(
                csv.DictReader(io.StringIO(bundle.read("inference-costs.csv").decode("utf-8-sig")))
            )

        lifecycle_by_offer = {
            row["offer_id"]: (row["price_evidence_state"], row["pricing_is_stale"])
            for row in rows
        }
        self.assertEqual(lifecycle_by_offer["40"], ("free", "True"))
        self.assertEqual(lifecycle_by_offer["41"], ("unavailable", "True"))
        self.assertEqual(lifecycle_by_offer["42"], ("custom", "True"))

    def test_model_summary_uses_only_current_au_standard_text_input_output_pairs(self) -> None:
        _, models, _, _ = _archive_rows(model_ids=["alpha-a"])
        alpha = models[0]

        self.assertIn("AWS Bedrock", alpha["australia_current_pricing"])
        self.assertIn("AUD 2", alpha["australia_current_pricing"])
        self.assertIn("input", alpha["australia_current_pricing"])
        self.assertIn("AUD 8", alpha["australia_current_pricing"])
        self.assertIn("output", alpha["australia_current_pricing"])
        self.assertNotIn("USD 1", alpha["australia_current_pricing"])
        self.assertNotIn("USD 0.5", alpha["australia_current_pricing"])
        self.assertIn("[synced]", alpha["australia_inference_options"])
        self.assertIn("[curated fallback]", alpha["australia_inference_options"])

    def test_price_only_au_evidence_does_not_create_readable_au_route_or_price(self) -> None:
        destination = {
            "id": "aws-bedrock",
            "name": "AWS Bedrock",
            "hyperscaler": "AWS",
            "availability_scope": "Account + region scoped",
            "availability_note": "Only a US availability route is confirmed.",
            "location_scope": "Published Bedrock regions",
            "regions": ["us-east-1"],
            "deployment_modes": ["On-demand"],
            "sources": [],
            "availability_evidence_kind": "synced",
            "pricing_offers": [
                _offer(
                    50,
                    destination_id="aws-bedrock",
                    region="ap-southeast-2",
                )
            ],
        }
        archive = review_export.build_model_guide_archive(
            catalog=_edge_catalog([destination]),
            exported_at=EXPORTED_AT,
        )
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            models = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
            costs = list(
                csv.DictReader(io.StringIO(bundle.read("inference-costs.csv").decode("utf-8-sig")))
            )

        au_price_rows = [row for row in costs if row["location_country"] == "Australia"]
        self.assertTrue(au_price_rows)
        self.assertEqual({row["location_evidence"] for row in au_price_rows}, {"price_only"})
        self.assertEqual(models[0]["australia_inference_options"], "")
        self.assertEqual(
            models[0]["australia_current_pricing"],
            "No known Australian inference route.",
        )

    def test_pricing_only_destination_regions_never_become_availability(self) -> None:
        destination = {
            "id": "aws-bedrock",
            "name": "AWS Bedrock",
            "hyperscaler": "AWS",
            "availability_scope": "Region scoped via live pricing",
            "availability_note": "Public pricing does not confirm account access.",
            "location_scope": "Live Bedrock pricing regions",
            "regions": ["ap-southeast-2"],
            "deployment_modes": ["On-demand"],
            "sources": [],
            "availability_evidence_kind": "pricing_only",
            "pricing_offers": [
                _offer(
                    55,
                    destination_id="aws-bedrock",
                    region="ap-southeast-2",
                )
            ],
        }
        archive = review_export.build_model_guide_archive(
            catalog=_edge_catalog([destination]),
            exported_at=EXPORTED_AT,
        )
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            models = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
            costs = list(
                csv.DictReader(io.StringIO(bundle.read("inference-costs.csv").decode("utf-8-sig")))
            )

        self.assertEqual({row["location_country"] for row in costs}, {"Australia"})
        self.assertEqual({row["location_evidence"] for row in costs}, {"price_only"})
        self.assertEqual(models[0]["australia_inference_options"], "")
        self.assertEqual(models[0]["australia_current_pricing"], "No known Australian inference route.")

    def test_misnested_offer_cannot_cross_attach_to_another_destination(self) -> None:
        destination = {
            "id": "aws-bedrock",
            "name": "AWS Bedrock",
            "hyperscaler": "AWS",
            "availability_scope": "Account + region scoped",
            "availability_note": "Confirmed AWS route.",
            "location_scope": "Live Bedrock regions",
            "regions": ["ap-southeast-2"],
            "deployment_modes": ["On-demand"],
            "sources": [],
            "availability_evidence_kind": "synced",
            "pricing_offers": [
                _offer(
                    56,
                    destination_id="azure-ai-foundry",
                    region="ap-southeast-2",
                )
            ],
        }
        archive = review_export.build_model_guide_archive(
            catalog=_edge_catalog([destination]),
            exported_at=EXPORTED_AT,
        )
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            models = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
            costs = list(
                csv.DictReader(io.StringIO(bundle.read("inference-costs.csv").decode("utf-8-sig")))
            )

        self.assertEqual(len(costs), 1)
        self.assertEqual(costs[0]["destination_id"], "aws-bedrock")
        self.assertEqual(costs[0]["location_evidence"], "availability_only")
        self.assertEqual(costs[0]["offer_id"], "")
        self.assertEqual(
            models[0]["australia_current_pricing"],
            "AU route available; no current AU-specific standard text input/output pricing.",
        )

    def test_regionless_provider_scopes_keep_availability_separate_from_unknown_price(self) -> None:
        destinations = []
        for offer_id, destination_id, name, scope in (
            (60, "provider-direct", "Provider Direct", "Provider managed"),
            (61, "provider-router", "Provider Router", "Provider routed"),
        ):
            destinations.append(
                {
                    "id": destination_id,
                    "name": name,
                    "hyperscaler": "Direct",
                    "availability_scope": "Provider account scoped",
                    "availability_note": "Provider controls processing location.",
                    "location_scope": scope,
                    "regions": [],
                    "deployment_modes": ["API"],
                    "sources": [],
                    "availability_evidence_kind": "curated_fallback",
                    "pricing_offers": [
                        _offer(
                            offer_id,
                            destination_id=destination_id,
                            region=None,
                        )
                    ],
                }
            )
        archive = review_export.build_model_guide_archive(
            catalog=_edge_catalog(destinations),
            exported_at=EXPORTED_AT,
        )
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            models = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
            costs = list(
                csv.DictReader(io.StringIO(bundle.read("inference-costs.csv").decode("utf-8-sig")))
            )

        for country, destination_id, offer_id in (
            ("Provider managed", "provider-direct", "60"),
            ("Provider routed", "provider-router", "61"),
        ):
            availability = [
                row
                for row in costs
                if row["destination_id"] == destination_id
                and row["location_country"] == country
            ]
            self.assertEqual(len(availability), 1)
            self.assertEqual(availability[0]["location_evidence"], "availability_only")
            self.assertEqual(availability[0]["offer_id"], "")
            price_rows = [row for row in costs if row["offer_id"] == offer_id]
            self.assertEqual({row["location_country"] for row in price_rows}, {"Unknown"})
            self.assertEqual({row["location_evidence"] for row in price_rows}, {"price_only"})
        self.assertIn("Provider Direct (Provider managed)", models[0]["other_inference_options"])
        self.assertIn("Provider Router (Provider routed)", models[0]["other_inference_options"])

    def test_fresh_free_au_standard_pair_has_an_honest_free_summary(self) -> None:
        destination = {
            "id": "aws-bedrock",
            "name": "AWS Bedrock",
            "hyperscaler": "AWS",
            "availability_scope": "Account + region scoped",
            "availability_note": "Matched Australian route.",
            "location_scope": "Published Bedrock regions",
            "regions": ["ap-southeast-2"],
            "deployment_modes": ["On-demand"],
            "sources": [],
            "availability_evidence_kind": "synced",
            "pricing_offers": [
                _offer(
                    70,
                    destination_id="aws-bedrock",
                    region="ap-southeast-2",
                    amount_input=0,
                    amount_output=0,
                    price_status="free",
                )
            ],
        }
        archive = review_export.build_model_guide_archive(
            catalog=_edge_catalog([destination]),
            exported_at=EXPORTED_AT,
        )
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            model = next(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))

        summary = model["australia_current_pricing"]
        self.assertIn("Free", summary)
        self.assertIn("AUD 0 input", summary)
        self.assertIn("AUD 0 output", summary)
        self.assertNotIn("no current", summary.casefold())

    def test_model_id_scope_limits_source_records_and_groups(self) -> None:
        _, models, costs, _ = _archive_rows(model_ids=["beta-only"])

        self.assertEqual([row["model_group_id"] for row in models], ["beta-group"])
        self.assertEqual(models[0]["source_record_ids"], "beta-only")
        self.assertEqual(len(costs), 1)
        self.assertEqual(costs[0]["price_evidence_state"], "no_known_route")

    def test_csv_cells_are_safe_for_spreadsheets_and_zip_bytes_are_deterministic(self) -> None:
        catalog = _catalog()
        malicious = catalog["models"][0]
        malicious["name"] = " \t=WEBSERVICE(\"https://example.invalid\")"
        malicious["provider"] = "+SUM(1,1)"
        catalog["models"][1]["provider"] = "+SUM(1,1)"
        malicious["general_approval_notes"] = "\n@cmd"
        malicious["general_recommendation_notes"] = "\u202e=HIDDEN_FORMULA"
        malicious["suggested_use_cases"][0]["label"] = "-Danger"

        first = review_export.build_model_guide_archive(catalog=catalog, exported_at=EXPORTED_AT)
        second = review_export.build_model_guide_archive(catalog=catalog, exported_at=EXPORTED_AT)

        self.assertEqual(first.content, second.content)
        with zipfile.ZipFile(io.BytesIO(first.content)) as bundle:
            self.assertEqual(
                [item.date_time for item in bundle.infolist()],
                [(2026, 7, 15, 5, 30, 0)] * 3,
            )
            rows = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
        alpha = next(row for row in rows if row["model_group_id"] == "alpha-group")
        self.assertTrue(alpha["model_name"].lstrip().startswith("'="))
        self.assertTrue(alpha["provider"].startswith("'+"))
        self.assertIn("'@cmd", alpha["general_approval_notes"])
        self.assertIn("\u202e'=HIDDEN_FORMULA", alpha["general_recommendation_notes"])
        self.assertIn("'-Danger", alpha["suggested_use_cases"])

    def test_au_route_without_fresh_au_specific_pair_is_explicit(self) -> None:
        catalog = {
            "schema_version": 6,
            "models": [
                {
                    "id": "au-no-price",
                    "review_entity_id": "au-no-price",
                    "name": "AU no current price",
                    "provider": "Example",
                    "general_approval_status": "approved",
                    "general_recommendation_status": "recommended",
                    "suggested_use_cases": [],
                    "inference_destinations": [
                        {
                            "id": "azure-ai-foundry",
                            "name": "Azure AI Foundry",
                            "availability_scope": "Account + deployment scoped",
                            "availability_note": "Available in Australia.",
                            "location_scope": "Configured regions",
                            "regions": ["australiaeast"],
                            "deployment_modes": ["Serverless"],
                            "sources": [],
                            "availability_evidence_kind": "synced",
                            "pricing_offers": [
                                _offer(
                                    99,
                                    destination_id="azure-ai-foundry",
                                    region="eastus2",
                                    amount_input=1,
                                    amount_output=4,
                                )
                            ],
                        }
                    ],
                }
            ],
        }
        archive = review_export.build_model_guide_archive(catalog=catalog, exported_at=EXPORTED_AT)
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            row = next(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))

        self.assertEqual(
            row["australia_current_pricing"],
            "AU route available; no current AU-specific standard text input/output pricing.",
        )

    def test_curated_au_fallback_is_described_as_possible_not_available(self) -> None:
        destination = {
            "id": "azure-ai-foundry",
            "name": "Azure AI Foundry",
            "hyperscaler": "Azure",
            "availability_scope": "Account + deployment scoped",
            "availability_note": "Curated provider route only.",
            "location_scope": "Common Foundry regions",
            "regions": ["australiaeast"],
            "deployment_modes": ["Serverless"],
            "sources": [],
            "availability_evidence_kind": "curated_fallback",
            "pricing_offers": [],
        }
        archive = review_export.build_model_guide_archive(
            catalog=_edge_catalog([destination]),
            exported_at=EXPORTED_AT,
        )
        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            row = next(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))

        self.assertIn("[curated fallback]", row["australia_inference_options"])
        self.assertEqual(
            row["australia_current_pricing"],
            "Possible AU route (curated fallback); availability is not confirmed and no current AU-specific pricing is available.",
        )

    def test_api_export_is_read_only_zip_without_admin_requirement(self) -> None:
        original_token = os.environ.pop(main.ADMIN_TOKEN_ENV_VAR, None)
        try:
            with (
                patch("backend.main.bootstrap"),
                patch("backend.review_export.build_review_catalog", return_value=_catalog()) as build_catalog,
                patch("backend.main.apply_model_decisions") as mutate_decisions,
            ):
                response = TestClient(main.app).post(
                    "/api/review/exports/model-guide",
                    json={"model_ids": ["beta-only"]},
                )
        finally:
            if original_token is not None:
                os.environ[main.ADMIN_TOKEN_ENV_VAR] = original_token

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertRegex(
            response.headers["content-disposition"],
            r'^attachment; filename="llm-model-guide-\d{8}T\d{6}Z\.zip"$',
        )
        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
            rows = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
        self.assertEqual([row["source_record_ids"] for row in rows], ["beta-only"])
        build_catalog.assert_called_once_with()
        mutate_decisions.assert_not_called()

    def test_cli_review_export_supports_output_override_and_model_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            output = Path(tempdir) / "guide.zip"
            stdout = io.StringIO()
            with (
                patch("backend.review_export.build_review_catalog", return_value=_catalog()),
                redirect_stdout(stdout),
            ):
                exit_code = cli.main(
                    ["review-export", "--output", str(output), "--model-id", "beta-only"]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.is_file())
            self.assertIn("Exported 1 model group", stdout.getvalue())
            with zipfile.ZipFile(output) as bundle:
                rows = list(csv.DictReader(io.StringIO(bundle.read("models.csv").decode("utf-8-sig"))))
            self.assertEqual([row["source_record_ids"] for row in rows], ["beta-only"])

    def test_cli_review_export_uses_timestamped_output_directory_default(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            prior_cwd = Path.cwd()
            try:
                os.chdir(tempdir)
                with (
                    patch("backend.review_export.build_review_catalog", return_value=_catalog()),
                    redirect_stdout(io.StringIO()),
                ):
                    exit_code = cli.main(["review-export"])
            finally:
                os.chdir(prior_cwd)

            self.assertEqual(exit_code, 0)
            outputs = list((Path(tempdir) / "output").glob("llm-model-guide-*.zip"))
            self.assertEqual(len(outputs), 1)

    def test_cli_review_export_reports_expected_scope_error_without_traceback(self) -> None:
        stderr = io.StringIO()
        with (
            patch(
                "backend.cli.export_model_guide",
                side_effect=ValueError("Model not found: definitely-missing"),
            ),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(
                ["review-export", "--model-id", "definitely-missing"]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(
            stderr.getvalue(),
            "review-export: Model not found: definitely-missing\n",
        )
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
