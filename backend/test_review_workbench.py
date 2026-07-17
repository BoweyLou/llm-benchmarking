from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import catalog_export, main, recommendation_engine, review_workbench, update_engine
from backend.versioning import read_app_version
from backend.database import (
    get_engine,
    init_db,
    model_inference_destinations as model_inference_destinations_table,
    model_use_case_approvals as model_use_case_approvals_table,
    model_use_case_recommendation_proposals as recommendation_proposals_table,
    models as models_table,
    scores as scores_table,
    source_runs as source_runs_table,
    sqlite_database_updated_at,
    update_log as update_log_table,
)
from backend.seed_data import seed_reference_data


class ReviewWorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.engine = get_engine(f"sqlite:///{Path(self.tempdir.name) / 'test.sqlite'}")
        init_db(self.engine)
        with self.engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

        self.original_engine = update_engine.ENGINE
        self.original_bootstrapped = update_engine.BOOTSTRAPPED
        self.original_token = os.environ.get(main.ADMIN_TOKEN_ENV_VAR)
        self.original_trusted_tailnet_writes = os.environ.get(main.TRUSTED_TAILNET_WRITES_ENV_VAR)
        update_engine.ENGINE = self.engine
        update_engine.BOOTSTRAPPED = True
        os.environ.pop(main.ADMIN_TOKEN_ENV_VAR, None)
        os.environ.pop(main.TRUSTED_TAILNET_WRITES_ENV_VAR, None)

    def tearDown(self) -> None:
        update_engine.ENGINE = self.original_engine
        update_engine.BOOTSTRAPPED = self.original_bootstrapped
        if self.original_token is None:
            os.environ.pop(main.ADMIN_TOKEN_ENV_VAR, None)
        else:
            os.environ[main.ADMIN_TOKEN_ENV_VAR] = self.original_token
        if self.original_trusted_tailnet_writes is None:
            os.environ.pop(main.TRUSTED_TAILNET_WRITES_ENV_VAR, None)
        else:
            os.environ[main.TRUSTED_TAILNET_WRITES_ENV_VAR] = self.original_trusted_tailnet_writes
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_review_app_and_catalog_are_readable(self) -> None:
        self._insert_review_model(
            "catalog-model",
            family_id="provider::catalog-family",
            release_date="2026-01-15",
            release_date_confidence="high",
        )
        self._insert_review_model(
            "speech-catalog-model",
            model_roles=["speech_to_text"],
            capabilities=["automatic-speech-recognition"],
            include_default_scores=False,
        )
        self._insert_review_model(
            "tts-catalog-model",
            model_roles=["text_to_speech"],
            capabilities=["text-to-speech"],
            include_default_scores=False,
        )
        self._insert_inference_destination("catalog-model", "azure-ai-foundry", "Azure AI Foundry")

        with patch("backend.main.bootstrap"):
            client = TestClient(main.app)
            app_response = client.get("/review")
            catalog_response = client.get("/api/review/catalog")

        self.assertEqual(app_response.status_code, 200)
        self.assertEqual(main.app.version, read_app_version())
        self.assertIn("<title>LLM Model Tool</title>", app_response.text)
        self.assertIn('<div class="brand-mark">LLM</div>', app_response.text)
        self.assertIn("<h1>Model Tool</h1>", app_response.text)
        self.assertIn("General model review", app_response.text)
        self.assertIn(f'<span id="appVersion">Version {main.app.version}</span>', app_response.text)
        self.assertNotIn("{{APP_VERSION}}", app_response.text)
        self.assertIn("Suggested use cases", app_response.text)
        self.assertIn("These are not approvals or recommendations", app_response.text)
        self.assertIn("Your model decisions", app_response.text)
        self.assertIn("Record model-level decisions", app_response.text)
        self.assertIn("then record model-level decisions", app_response.text)
        self.assertIn("Reasoning effort limit", app_response.text)
        self.assertIn("Restricted product modes", app_response.text)
        self.assertIn("Recommendation", app_response.text)
        self.assertIn("Usage Classification", app_response.text)
        self.assertIn('id="usageClassificationFilter"', app_response.text)
        self.assertIn('id="bulkUsageClassification"', app_response.text)
        self.assertIn("Acceptable", app_response.text)
        self.assertIn("Legacy Supported", app_response.text)
        self.assertIn("Not Assessed", app_response.text)
        self.assertNotIn(">Unrated<", app_response.text)
        self.assertEqual(app_response.text.count('value="acceptable"'), 2)
        self.assertEqual(app_response.text.count('value="legacy_supported"'), 2)
        self.assertIn(
            '["recommended", "acceptable", "legacy_supported", "not_recommended", "unrated"]',
            app_response.text,
        )
        self.assertIn('function recommendationLabel(value) { return value === "unrated" ? "Not Assessed"', app_response.text)
        self.assertIn('recommendation_status: state.draft.recommendation', app_response.text)
        self.assertIn('payload.recommendation_status = recommendation', app_response.text)
        self.assertIn(
            '["standard", "restricted", "prohibited", "unclassified"]',
            app_response.text,
        )
        self.assertIn('usage_classification: state.draft.usageClassification', app_response.text)
        self.assertIn('payload.usage_classification = usageClassificationValue', app_response.text)
        self.assertIn('usageClassification: "", needsDecision: false', app_response.text)
        self.assertIn("Restricted", app_response.text)
        self.assertNotIn("Discouraged", app_response.text)
        self.assertIn("Select all", app_response.text)
        self.assertIn("Apply model decisions", app_response.text)
        self.assertIn("Why are these the right model decisions?", app_response.text)
        self.assertIn("Reference details that can affect model decisions", app_response.text)
        self.assertIn("Model decisions saved", app_response.text)
        self.assertNotIn("then make one general decision", app_response.text)
        self.assertNotIn("Apply general decision", app_response.text)
        self.assertNotIn("right general decision", app_response.text)
        self.assertNotIn("affect a general decision", app_response.text)
        self.assertNotIn("General decision saved", app_response.text)
        self.assertIn("selectedGroupIds", app_response.text)
        self.assertIn("reviewGroups", app_response.text)
        self.assertIn("Pricing by provider", app_response.text)
        self.assertIn("pricing_offers", app_response.text)
        self.assertIn("visibleLimit: 200", app_response.text)
        self.assertIn("Show next", app_response.text)
        self.assertIn("Benchmark position", app_response.text)
        self.assertIn("How this model compares with similar scored models in this database.", app_response.text)
        self.assertIn("Show all", app_response.text)
        self.assertIn("mergeBenchmarkEvidence", app_response.text)
        self.assertIn("evaluationSignatureKey", app_response.text)
        self.assertIn("benchmark_evidence", app_response.text)
        self.assertIn("scoreDisplayUnit", app_response.text)
        self.assertIn("safeHttpUrl", app_response.text)
        self.assertIn("review_entity_id", app_response.text)
        self.assertIn("Source verification confirms the record", app_response.text)
        self.assertIn('/api/review/model-decisions', app_response.text)
        self.assertNotIn('/api/review/decisions', app_response.text)
        self.assertNotIn("Manual recommendation", app_response.text)
        self.assertNotIn("useCaseApprovalStatus", app_response.text)
        self.assertNotIn("bulkUseCaseTargetsForModels", app_response.text)
        self.assertIn("runUpdates", app_response.text)
        self.assertIn("Run updates", app_response.text)
        self.assertIn('id="openExport"', app_response.text)
        self.assertIn("Export review data", app_response.text)
        self.assertIn('value="all"', app_response.text)
        self.assertIn('value="filtered"', app_response.text)
        self.assertIn('value="selected" disabled', app_response.text)
        self.assertIn('id="exportStatus" role="status" aria-live="polite"', app_response.text)
        export_dialog_start = app_response.text.index('id="exportDialog"')
        export_dialog_end = app_response.text.index("</dialog>", export_dialog_start)
        export_status = app_response.text.index('id="exportStatus"')
        self.assertLess(export_dialog_start, export_status)
        self.assertLess(export_status, export_dialog_end)
        self.assertIn('/api/review/exports/model-guide', app_response.text)
        self.assertIn("completeExportModelIds", app_response.text)
        self.assertIn("response.blob()", app_response.text)
        self.assertIn('response.headers.get("Content-Disposition")', app_response.text)
        self.assertIn("URL.revokeObjectURL", app_response.text)
        self.assertIn("preventExportDialogCancel", app_response.text)
        self.assertIn('id="databaseUpdated">Database updated:', app_response.text)
        self.assertIn('id="lastSynced">Last sync:', app_response.text)
        self.assertIn("toLocaleString()", app_response.text)
        self.assertIn("/api/update/status/", app_response.text)
        self.assertIn("Unreviewed", app_response.text)
        self.assertEqual(catalog_response.status_code, 200)
        payload = catalog_response.json()
        self.assertEqual(payload["schema_version"], 6)
        self.assertIsNotNone(payload["database_updated_at"])
        self.assertIsNone(payload["last_sync_at"])
        self.assertIsNone(payload["last_sync_status"])
        self.assertIsNone(payload["last_sync_log_id"])
        self.assertGreaterEqual(payload["summary"]["model_count"], 1)
        self.assertIn("models", payload)
        self.assertIn("benchmarks", payload)
        self.assertTrue(payload["benchmarks"])
        self.assertIn("families", payload)
        self.assertIn("facets", payload)
        self.assertNotIn("recommendations", payload["facets"])
        self.assertIn("general_recommendations", payload["facets"])
        self.assertNotIn(
            "discouraged",
            {item["id"] for item in payload["facets"]["general_recommendations"]},
        )
        self.assertIn(
            "legacy_supported",
            {item["id"] for item in payload["facets"]["general_recommendations"]},
        )
        self.assertIn(
            "acceptable",
            {item["id"] for item in payload["facets"]["general_recommendations"]},
        )
        self.assertEqual(
            [item["id"] for item in payload["facets"]["general_recommendations"]],
            ["recommended", "acceptable", "legacy_supported", "not_recommended", "unrated"],
        )
        self.assertNotIn(
            "restricted",
            {item["id"] for item in payload["facets"]["general_recommendations"]},
        )
        self.assertEqual(
            {item["id"] for item in payload["facets"]["usage_classifications"]},
            {"standard", "restricted", "prohibited", "unclassified"},
        )
        self.assertIn("countries", payload["facets"])
        self.assertTrue(payload["facets"]["countries"])
        self.assertIn("hyperscalers", payload["facets"])
        capability_counts = {item["id"]: item["count"] for item in payload["facets"]["capabilities"]}
        self.assertGreaterEqual(capability_counts.get("automatic-speech-recognition", 0), 1)
        self.assertGreaterEqual(capability_counts.get("text-to-speech", 0), 1)
        role_counts = {item["id"]: item["count"] for item in payload["facets"]["model_roles"]}
        self.assertGreaterEqual(role_counts.get("speech_to_text", 0), 1)
        self.assertGreaterEqual(role_counts.get("text_to_speech", 0), 1)
        general_approval_counts = {item["id"]: item["count"] for item in payload["facets"]["general_approvals"]}
        self.assertGreaterEqual(general_approval_counts.get("unreviewed", 0), 1)
        hyperscaler_names = {item["name"] for item in payload["facets"]["hyperscalers"]}
        self.assertIn("Any hyperscaler", hyperscaler_names)
        self.assertIn("Azure AI Foundry", hyperscaler_names)
        self.assertIn("No hyperscaler route", hyperscaler_names)
        model = next(model for model in payload["models"] if model["id"] == "catalog-model")
        self.assertTrue(model["review_entity_id"])
        self.assertFalse(model["general_approved_for_use"])
        self.assertEqual(model["general_approval_status"], "unreviewed")
        self.assertIn("Azure AI Foundry", model["inference_summary"]["platform_names"])
        self.assertEqual(model["release_date"], "2026-01-15")
        self.assertEqual(model["release_date_confidence"], "high")
        self.assertEqual(model["model_age_basis"], "release_date")
        self.assertEqual(model["model_type_primary"], "frontier")
        self.assertIn("frontier", model["model_type_tags"])
        self.assertIn("hyperscaler_available", model["model_type_tags"])
        self.assertEqual(model["strongest_signal_kind"], "hyperscaler")
        self.assertEqual(model["hyperscaler_signal"], "Azure AI Foundry")
        speech_model = next(model for model in payload["models"] if model["id"] == "speech-catalog-model")
        self.assertEqual(speech_model["model_type_primary"], "speech_to_text")
        self.assertEqual(speech_model["evidence_context_use_case_id"], "voice_to_text")
        tts_model = next(model for model in payload["models"] if model["id"] == "tts-catalog-model")
        self.assertEqual(tts_model["model_type_primary"], "text_to_speech")
        self.assertEqual(tts_model["evidence_context_use_case_id"], "text_to_speech")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the review UI behavior contract")
    def test_review_benchmark_helpers_preserve_signatures_and_enforce_display_rules(self) -> None:
        script = main.REVIEW_APP_PATH.read_text(encoding="utf-8")
        harness = r"""
const source = process.env.REVIEW_SOURCE;
function section(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  if (from < 0 || to < 0) throw new Error(`Missing section: ${start}`);
  return source.slice(from, to);
}
eval(section("    function label", "    function normalizedName"));
if (recommendationLabel("acceptable") !== "Acceptable") throw new Error("Acceptable recommendation label was not rendered");
if (recommendationLabel("unrated") !== "Not Assessed") throw new Error("Unrated recommendation was not rendered as Not Assessed");
const benchmark = {presentation: {comparison_dimensions: ["source_metadata.task_names"], value_kind: "elo", unit: "Elo"}};
function benchmarkLookup() { return {mteb_retrieval: benchmark}; }
eval(section("    function scoreSelectionRank", "    function reviewGroups"));
const score = (value, task, id) => ({
  value, verified: true, source_type: "primary", collected_at: "2026-07-15T00:00:00Z",
  source_metadata: {task_names: [task]}, display: {formatted: String(value), unit: "Elo", direction_label: "Higher is better"},
  comparison: {selected_for_entity: true, contributor_model_id: id}
});
const merged = mergeBenchmarkEvidence([
  {id: "alias-a", name: "Alias A", scores: {mteb_retrieval: score(70, "Task A", "alias-a")}},
  {id: "alias-b", name: "Alias B", scores: {mteb_retrieval: score(71, "Task B", "alias-b")}}
]);
if (merged.benchmarkEvidence.length !== 2) throw new Error("Distinct evaluation signatures were collapsed");
const configuredScore = {...score(70, "Task A", "alias-a"), configuration_key: "reasoning_effort", configuration_value: "high"};
const duplicate = mergeBenchmarkEvidence([{
  id: "alias-a", name: "Alias A", scores: {mteb_retrieval: configuredScore},
  score_configurations: [{benchmark_id: "mteb_retrieval", ...configuredScore}]
}]);
if (duplicate.benchmarkEvidence.length !== 1) throw new Error("Latest configured observation was rendered twice");
function escapeHtml(value) { return String(value ?? ""); }
function percentileLabel(value) { return `${Math.round(Number(value))}th percentile`; }
eval(section("    function formatBenchmarkValue", "    function renderBenchmarkCard"));
if (percentileTrack({percentile: 80, cohort_size: 19}) !== "") throw new Error("Small cohort rendered a percentile track");
if (!percentileTrack({percentile: 80, cohort_size: 20})) throw new Error("Large cohort omitted its percentile track");
if (scoreDisplayUnit({display: {unit: "Elo"}}, benchmark) !== "Elo") throw new Error("Elo unit was omitted");
if (scoreDisplayUnit({display: {unit: "%"}}, {presentation: {value_kind: "percentage", unit: "%"}}) !== "") throw new Error("Percentage unit was duplicated");
if (safeHttpUrl("javascript:alert(1)") !== null) throw new Error("Unsafe source URL was accepted");
if (!safeHttpUrl("https://example.com/source")) throw new Error("HTTPS source URL was rejected");
function benchmarkRecords() { return []; }
function relevantUseCase() { return {weights: {context_metric: 1}, required_benchmarks: ["required_metric"]}; }
function label(value) { return String(value); }
eval(section("    function benchmarkEvidence", "    function formatBenchmarkValue"));
const missing = benchmarkEvidence({relevant_benchmark_ids: ["role_metric"]}).missing.map((item) => item.id).sort();
if (JSON.stringify(missing) !== JSON.stringify(["context_metric", "required_metric"])) throw new Error("Missing evidence ignored active use-case relevance");
"""
        completed = subprocess.run(
            ["node", "-e", harness],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "REVIEW_SOURCE": script},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the review export UI contract")
    def test_review_export_ui_uses_complete_group_membership_and_revokes_blob_url(self) -> None:
        script = main.REVIEW_APP_PATH.read_text(encoding="utf-8")
        harness = r"""
const source = process.env.REVIEW_SOURCE;
function section(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  if (from < 0 || to < 0) throw new Error(`Missing section: ${start}`);
  return source.slice(from, to);
}
eval(section("    function safeDownloadFilename", "    function escapeHtml"));
if (safeDownloadFilename('attachment; filename="llm-model-guide-20260715T050000Z.zip"') !== "llm-model-guide-20260715T050000Z.zip") throw new Error("Safe export filename was rejected");
if (safeDownloadFilename('attachment; filename="../../escape.zip"') !== null) throw new Error("Unsafe path filename was accepted");
if (safeDownloadFilename('attachment; filename="model-guide.exe"') !== null) throw new Error("Non-ZIP filename was accepted");

const groups = [
  {group_id: "visible-entity", member_ids: ["visible-direct", "visible-provider-variant"]},
  {group_id: "hidden-selected-entity", member_ids: ["hidden-direct", "hidden-provider-variant"]}
];
const state = {selectedGroupIds: new Set(["hidden-selected-entity"]), exporting: false};
function reviewGroups() { return groups; }
function filteredGroups() { return [groups[0]]; }
function toast() {}
const els = {
  exportAllMeta: {textContent: ""}, exportFilteredMeta: {textContent: ""}, exportSelectedMeta: {textContent: ""},
  exportScopeAll: {disabled: false, checked: false}, exportScopeFiltered: {disabled: false, checked: true},
  exportScopeSelected: {disabled: false, checked: false}, cancelExport: {disabled: false},
  downloadExport: {disabled: false, textContent: ""}, exportStatus: {textContent: ""},
  exportDialog: {closed: false, close() { this.closed = true; }, showModal() {}}
};
eval(section("    function selectedGroups", "    function renderBulkBar"));

const filteredIds = modelIdsForExportScope("filtered");
if (JSON.stringify(filteredIds) !== JSON.stringify(["visible-direct", "visible-provider-variant"])) throw new Error("Filtered export omitted grouped provider membership");
const selectedIds = modelIdsForExportScope("selected");
if (JSON.stringify(selectedIds) !== JSON.stringify(["hidden-direct", "hidden-provider-variant"])) throw new Error("Selected export lost a group hidden by current filters");
if (modelIdsForExportScope("all") !== null) throw new Error("All-model export should use an unscoped request");

state.selectedGroupIds.clear();
els.exportScopeSelected.checked = true;
els.exportScopeFiltered.checked = false;
updateExportOptions();
if (!els.exportScopeSelected.disabled) throw new Error("Empty Selected export remained enabled");
if (!els.exportScopeAll.checked) throw new Error("Empty Selected scope did not fall back to All");

state.exporting = true;
let cancelPrevented = false;
preventExportDialogCancel({preventDefault() { cancelPrevented = true; }});
if (!cancelPrevented) throw new Error("Escape was allowed to close an in-progress export");
if (!els.exportStatus.textContent.includes("still being prepared")) throw new Error("In-progress Escape was not announced");
state.exporting = false;

let fetchCall = null;
let revokedUrl = null;
let clicked = false;
let appended = false;
const anchor = {href: "", download: "", click() { clicked = true; }, remove() {}};
global.FormData = class { get() { return "filtered"; } };
global.fetch = async (url, options) => {
  fetchCall = {url, options};
  return {
    ok: true,
    status: 200,
    headers: {get(name) { return name === "Content-Disposition" ? 'attachment; filename="llm-model-guide-20260715T050000Z.zip"' : null; }},
    blob: async () => ({size: 42})
  };
};
global.URL = {
  createObjectURL() { return "blob:model-guide"; },
  revokeObjectURL(value) { revokedUrl = value; }
};
global.document = {
  createElement(tag) { if (tag !== "a") throw new Error("Unexpected download element"); return anchor; },
  body: {appendChild(value) { if (value !== anchor) throw new Error("Unexpected download anchor"); appended = true; }}
};

(async () => {
  await downloadModelGuide({preventDefault() {}});
  if (fetchCall?.url !== "/api/review/exports/model-guide") throw new Error("Wrong export endpoint");
  const payload = JSON.parse(fetchCall.options.body);
  if (JSON.stringify(payload.model_ids) !== JSON.stringify(["visible-direct", "visible-provider-variant"])) throw new Error("Download request omitted complete filtered membership");
  if (fetchCall.options.headers["Content-Type"] !== "application/json") throw new Error("Export request omitted JSON content type");
  if (!appended || !clicked) throw new Error("ZIP download was not triggered");
  if (anchor.download !== "llm-model-guide-20260715T050000Z.zip") throw new Error("Content-Disposition filename was not used");
  if (revokedUrl !== "blob:model-guide") throw new Error("Blob URL was not revoked");
  if (!els.exportDialog.closed) throw new Error("Export dialog did not close after download");
  if (state.exporting) throw new Error("Export busy state was not cleared");
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
        completed = subprocess.run(
            ["node", "-e", harness],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "REVIEW_SOURCE": script},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_review_catalog_adds_ranked_benchmark_selection_evidence(self) -> None:
        self._insert_review_model("ranked-generator")
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": "ranked-generator",
                        "benchmark_id": "aa_intelligence",
                        "value": 55.0,
                        "raw_value": "55.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_url": "https://example.com/aa",
                        "source_type": "primary",
                        "verified": 1,
                    },
                    {
                        "model_id": "ranked-generator",
                        "benchmark_id": "gpqa_diamond",
                        "value": 80.0,
                        "raw_value": "80.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_url": "https://example.com/gpqa",
                        "source_type": "primary",
                        "verified": 1,
                    }
                ],
            )

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "ranked-generator")

        self.assertEqual(model["model_type_primary"], "frontier")
        self.assertEqual(model["evidence_context_use_case_id"], "general_reasoning")
        self.assertEqual(model["strongest_signal_kind"], "benchmark")
        self.assertEqual(model["strongest_signal_label"], "AA Intel")
        self.assertIsNotNone(model["ranking_rank"])
        self.assertGreater(model["ranking_score"], 0)
        self.assertEqual(model["cost_signal"], "Cost: 0.2")
        self.assertEqual(model["speed_signal"], "Speed: 120.0")
        self.assertIn("general_reasoning", model["selection_evidence_by_use_case"])

    def test_review_catalog_adds_embedding_reranker_and_local_sml_types(self) -> None:
        self._insert_review_model("embedding-model", model_roles=["embedding"], include_default_scores=False)
        self._insert_review_model("reranker-model", model_roles=["reranker"], include_default_scores=False)
        self._insert_review_model("tts-model", model_roles=["text_to_speech"], include_default_scores=False)
        self._insert_review_model(
            "local-small-model",
            model_type="open_weights",
            model_roles=["generator"],
            small_model_candidate=True,
            model_size_class="small",
            parameter_count_b=4.0,
            include_default_scores=False,
        )
        with self.engine.begin() as conn:
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": "embedding-model",
                        "benchmark_id": "mteb_retrieval",
                        "value": 70.0,
                        "raw_value": "70.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_type": "primary",
                        "verified": 1,
                    },
                    {
                        "model_id": "reranker-model",
                        "benchmark_id": "mteb_reranking",
                        "value": 72.0,
                        "raw_value": "72.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_type": "primary",
                        "verified": 1,
                    },
                    {
                        "model_id": "tts-model",
                        "benchmark_id": "aa_tts_quality_elo",
                        "value": 1213.0,
                        "raw_value": "1213.0",
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_type": "primary",
                        "verified": 1,
                    },
                ],
            )

        models = {model["id"]: model for model in review_workbench.build_review_catalog()["models"]}

        self.assertEqual(models["embedding-model"]["model_type_primary"], "embedding")
        self.assertEqual(models["embedding-model"]["evidence_context_use_case_id"], "retrieval_embeddings")
        self.assertEqual(models["embedding-model"]["strongest_signal_kind"], "benchmark")
        self.assertEqual(models["reranker-model"]["model_type_primary"], "reranker")
        self.assertEqual(models["reranker-model"]["evidence_context_use_case_id"], "retrieval_reranking")
        self.assertEqual(models["reranker-model"]["strongest_signal_kind"], "benchmark")
        self.assertEqual(models["tts-model"]["model_type_primary"], "text_to_speech")
        self.assertEqual(models["tts-model"]["evidence_context_use_case_id"], "text_to_speech")
        self.assertEqual(models["tts-model"]["strongest_signal_kind"], "benchmark")
        self.assertEqual(models["local-small-model"]["model_type_primary"], "local_sml")
        self.assertIn("local_sml", models["local-small-model"]["model_type_tags"])
        self.assertEqual(models["local-small-model"]["strongest_signal_kind"], "local_sml")
        self.assertEqual(models["local-small-model"]["strongest_signal_value"], "4.0B parameters")

    def test_review_catalog_prefers_approved_route_before_hyperscaler_fallback(self) -> None:
        self._insert_review_model("approved-route-model", include_default_scores=False)
        self._insert_inference_destination(
            "approved-route-model",
            "azure-ai-foundry",
            "Azure AI Foundry",
            regions=["ap-southeast-2"],
        )
        update_engine.update_model_use_case_inference_approval(
            "approved-route-model",
            "customer_support",
            "azure-ai-foundry",
            "Australia",
            True,
            "Approved Australian route.",
        )

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "approved-route-model")

        self.assertEqual(model["strongest_signal_kind"], "approved_inference_route")
        self.assertIn("Approved route: Azure AI Foundry", model["strongest_signal_label"])
        self.assertEqual(model["strongest_signal_notes"], "Approved Australian route.")

    def test_review_catalog_uses_australia_route_fallback(self) -> None:
        self._insert_review_model("australia-route-model", include_default_scores=False, model_card_url=None)
        self._insert_inference_destination(
            "australia-route-model",
            "aws-bedrock",
            "AWS Bedrock",
            hyperscaler="AWS",
            regions=["ap-southeast-2", "us-east-1"],
        )

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "australia-route-model")

        self.assertEqual(model["strongest_signal_kind"], "inference_location")
        self.assertEqual(model["strongest_signal_label"], "Australia inference route")
        self.assertIn("australia_route", model["model_type_tags"])
        self.assertIn("ap-southeast-2", model["inference_location_signal"])

    def test_review_catalog_marks_models_without_selection_evidence(self) -> None:
        self._insert_review_model("no-evidence-model", include_default_scores=False, model_card_url=None)

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "no-evidence-model")

        self.assertEqual(model["strongest_signal_kind"], "insufficient_evidence")
        self.assertEqual(model["strongest_signal_label"], "Insufficient evidence")

    def test_review_decision_route_requires_admin_token(self) -> None:
        self._insert_review_model("guard-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={"model_ids": ["guard-model"], "use_case_ids": ["customer_support"], "recommendation_status": "recommended"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn(main.ADMIN_TOKEN_ENV_VAR, response.json()["detail"])

    def test_review_decision_route_saves_bulk_decisions_and_catalog_status(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("bulk-a", family_id="provider::bulk-family")
        self._insert_review_model("bulk-b", family_id="provider::bulk-family")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={
                    "model_ids": ["bulk-a", "bulk-b"],
                    "use_case_ids": ["customer_support"],
                    "approved_for_use": True,
                    "recommendation_status": "recommended",
                    "approval_notes": "Approved by workbench.",
                    "recommendation_notes": "Preferred for this review.",
                    "catalog_status": "deprecated",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["updated_count"], 2)
        self.assertEqual(payload["catalog_status_updated_count"], 2)
        with self.engine.begin() as conn:
            approval_rows = conn.execute(
                model_use_case_approvals_table.select().where(
                    model_use_case_approvals_table.c.model_id.in_(["bulk-a", "bulk-b"])
                )
            ).mappings().all()
            model_rows = conn.execute(
                models_table.select().where(models_table.c.id.in_(["bulk-a", "bulk-b"]))
            ).mappings().all()
        self.assertEqual({row["recommendation_status"] for row in approval_rows}, {"recommended"})
        self.assertEqual({row["approved_for_use"] for row in approval_rows}, {1})
        self.assertEqual({row["catalog_status"] for row in model_rows}, {"deprecated"})

    def test_review_decision_route_saves_restricted_recommendation(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("restricted-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={
                    "model_ids": ["restricted-model"],
                    "use_case_ids": ["safety_compliance"],
                    "recommendation_status": "restricted",
                    "recommendation_notes": "Cyber model limited to approved cyber team members.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        model = next(model for model in update_engine.list_models() if model["id"] == "restricted-model")
        approval = model["use_case_approvals"]["safety_compliance"]
        self.assertEqual(approval["recommendation_status"], "restricted")
        self.assertEqual(approval["effective_recommendation_status"], "restricted")
        self.assertEqual(approval["recommendation_notes"], "Cyber model limited to approved cyber team members.")

    def test_legacy_supported_is_not_accepted_by_legacy_use_case_route(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("general-only-status-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={
                    "model_ids": ["general-only-status-model"],
                    "use_case_ids": ["customer_support"],
                    "recommendation_status": "legacy_supported",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 422)

    def test_acceptable_is_not_accepted_by_legacy_use_case_route(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("general-acceptable-only-status-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={
                    "model_ids": ["general-acceptable-only-status-model"],
                    "use_case_ids": ["customer_support"],
                    "recommendation_status": "acceptable",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 422)

    def test_restricted_is_rejected_by_general_model_decision_route(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("general-restricted-invalid")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/model-decisions",
                json={
                    "model_ids": ["general-restricted-invalid"],
                    "recommendation_status": "restricted",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 422)

    def test_review_decision_route_overwrites_restricted_recommendation(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("restricted-to-not-recommended")
        client = TestClient(main.app)

        with patch("backend.main.bootstrap"):
            restricted_response = client.post(
                "/api/review/decisions",
                json={
                    "model_ids": ["restricted-to-not-recommended"],
                    "use_case_ids": ["safety_compliance"],
                    "recommendation_status": "restricted",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )
            not_recommended_response = client.post(
                "/api/review/decisions",
                json={
                    "model_ids": ["restricted-to-not-recommended"],
                    "use_case_ids": ["safety_compliance"],
                    "recommendation_status": "not_recommended",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(restricted_response.status_code, 200)
        self.assertEqual(not_recommended_response.status_code, 200)
        model = next(model for model in update_engine.list_models() if model["id"] == "restricted-to-not-recommended")
        approval = model["use_case_approvals"]["safety_compliance"]
        self.assertEqual(approval["recommendation_status"], "not_recommended")
        self.assertEqual(approval["effective_recommendation_status"], "not_recommended")

    def test_review_decision_route_can_clear_approval_boolean(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("unapprove-model")
        review_workbench.apply_review_decisions(
            model_ids=["unapprove-model"],
            use_case_ids=["customer_support"],
            approved_for_use=True,
            recommendation_status="recommended",
        )

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/decisions",
                json={
                    "model_ids": ["unapprove-model"],
                    "use_case_ids": ["customer_support"],
                    "approved_for_use": False,
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 1)
        model = next(model for model in update_engine.list_models() if model["id"] == "unapprove-model")
        approval = model["use_case_approvals"]["customer_support"]
        self.assertFalse(approval["approved_for_use"])
        self.assertEqual(approval["recommendation_status"], "recommended")

    def test_review_model_approval_route_updates_general_state_only(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("general-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/model-approvals",
                json={
                    "model_ids": ["general-model"],
                    "approved_for_use": True,
                    "approval_notes": "Generally approved for model catalog use.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 1)
        with self.engine.begin() as conn:
            model_row = conn.execute(
                models_table.select().where(models_table.c.id == "general-model")
            ).mappings().one()
            approval_rows = conn.execute(
                model_use_case_approvals_table.select().where(
                    model_use_case_approvals_table.c.model_id == "general-model"
                )
            ).mappings().all()
        self.assertEqual(model_row["general_approved_for_use"], 1)
        self.assertEqual(model_row["general_approval_notes"], "Generally approved for model catalog use.")
        self.assertEqual(approval_rows, [])

        review_workbench.apply_review_decisions(
            model_ids=["general-model"],
            use_case_ids=["customer_support"],
            approved_for_use=False,
            recommendation_status="not_recommended",
        )
        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "general-model")
        self.assertTrue(model["general_approved_for_use"])
        self.assertFalse(model["use_case_approvals"]["customer_support"]["approved_for_use"])

    def test_review_model_decision_route_saves_general_approval_and_recommendation_only(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("general-decision-model")
        self._insert_review_model("general-decision-model-alias")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/model-decisions",
                json={
                    "model_ids": ["general-decision-model", "general-decision-model-alias"],
                    "approval_status": "approved",
                    "approval_notes": "Approved after general review.",
                    "recommendation_status": "legacy_supported",
                    "recommendation_notes": "Use when necessary while migrating to a recommended model.",
                    "usage_classification": "restricted",
                    "usage_classification_notes": "Limited to the approved migration team.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 2)
        self.assertEqual(response.json()["approval_status"], "approved")
        self.assertEqual(response.json()["recommendation_status"], "legacy_supported")
        self.assertEqual(response.json()["usage_classification"], "restricted")
        with self.engine.begin() as conn:
            model_rows = conn.execute(
                models_table.select().where(
                    models_table.c.id.in_(["general-decision-model", "general-decision-model-alias"])
                )
            ).mappings().all()
            legacy_rows = conn.execute(
                model_use_case_approvals_table.select().where(
                    model_use_case_approvals_table.c.model_id.in_(
                        ["general-decision-model", "general-decision-model-alias"]
                    )
                )
            ).mappings().all()
        self.assertEqual({row["general_approved_for_use"] for row in model_rows}, {1})
        self.assertEqual({row["general_recommendation_status"] for row in model_rows}, {"legacy_supported"})
        self.assertEqual(
            {row["general_recommendation_notes"] for row in model_rows},
            {"Use when necessary while migrating to a recommended model."},
        )
        self.assertEqual({row["usage_classification"] for row in model_rows}, {"restricted"})
        self.assertEqual(
            {row["usage_classification_notes"] for row in model_rows},
            {"Limited to the approved migration team."},
        )
        self.assertEqual(legacy_rows, [])
        catalog = review_workbench.build_review_catalog()
        saved_model = next(model for model in catalog["models"] if model["id"] == "general-decision-model")
        self.assertEqual(saved_model["general_recommendation_status"], "legacy_supported")
        self.assertEqual(saved_model["usage_classification"], "restricted")
        facet_counts = {item["id"]: item["count"] for item in catalog["facets"]["general_recommendations"]}
        self.assertEqual(facet_counts["legacy_supported"], 2)
        classification_counts = {item["id"]: item["count"] for item in catalog["facets"]["usage_classifications"]}
        self.assertEqual(classification_counts["restricted"], 2)

    def test_recommendation_and_usage_classification_update_independently(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("independent-governance-model")
        client = TestClient(main.app)

        with patch("backend.main.bootstrap"):
            initial = client.post(
                "/api/review/model-decisions",
                json={
                    "model_ids": ["independent-governance-model"],
                    "recommendation_status": "recommended",
                    "recommendation_notes": "Preferred for new work.",
                    "usage_classification": "restricted",
                    "usage_classification_notes": "Approved users only.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )
            recommendation_only = client.post(
                "/api/review/model-decisions",
                json={
                    "model_ids": ["independent-governance-model"],
                    "recommendation_status": "legacy_supported",
                    "recommendation_notes": "Migrate when practical.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(recommendation_only.status_code, 200)
        model = next(
            model for model in review_workbench.build_review_catalog()["models"]
            if model["id"] == "independent-governance-model"
        )
        self.assertEqual(model["general_recommendation_status"], "legacy_supported")
        self.assertEqual(model["general_recommendation_notes"], "Migrate when practical.")
        self.assertEqual(model["usage_classification"], "restricted")
        self.assertEqual(model["usage_classification_notes"], "Approved users only.")

        review_workbench.apply_model_decisions(
            model_ids=["independent-governance-model"],
            usage_classification="unclassified",
            usage_classification_notes="This must be cleared.",
        )
        reset = next(
            model for model in review_workbench.build_review_catalog()["models"]
            if model["id"] == "independent-governance-model"
        )
        self.assertEqual(reset["general_recommendation_status"], "legacy_supported")
        self.assertEqual(reset["usage_classification"], "unclassified")
        self.assertIsNone(reset["usage_classification_notes"])
        self.assertIsNone(reset["usage_classification_updated_at"])
        self.assertTrue(review_workbench._model_needs_decision(reset))

    def test_acceptable_is_completed_and_unrated_clears_recommendation_decision(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("acceptable-model")
        client = TestClient(main.app)

        with patch("backend.main.bootstrap"):
            acceptable_response = client.post(
                "/api/review/model-decisions",
                json={
                    "model_ids": ["acceptable-model"],
                    "approval_status": "approved",
                    "recommendation_status": "acceptable",
                    "recommendation_notes": "Okay for normal use; prefer the recommended option.",
                    "usage_classification": "standard",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(acceptable_response.status_code, 200)
        self.assertEqual(acceptable_response.json()["recommendation_status"], "acceptable")
        catalog = review_workbench.build_review_catalog()
        model = next(item for item in catalog["models"] if item["id"] == "acceptable-model")
        self.assertEqual(model["general_recommendation_status"], "acceptable")
        self.assertEqual(
            model["general_recommendation_notes"],
            "Okay for normal use; prefer the recommended option.",
        )
        self.assertIsNotNone(model["general_recommendation_updated_at"])
        self.assertFalse(review_workbench._model_needs_decision(model))
        facet_counts = {item["id"]: item["count"] for item in catalog["facets"]["general_recommendations"]}
        self.assertEqual(facet_counts["acceptable"], 1)

        with patch("backend.main.bootstrap"):
            unrated_response = client.post(
                "/api/review/model-decisions",
                json={
                    "model_ids": ["acceptable-model"],
                    "recommendation_status": "unrated",
                    "recommendation_notes": "This must be discarded.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(unrated_response.status_code, 200)
        cleared = next(
            item for item in review_workbench.build_review_catalog()["models"]
            if item["id"] == "acceptable-model"
        )
        self.assertEqual(cleared["general_recommendation_status"], "unrated")
        self.assertIsNone(cleared["general_recommendation_notes"])
        self.assertIsNone(cleared["general_recommendation_updated_at"])
        self.assertTrue(review_workbench._model_needs_decision(cleared))

    def test_model_decision_policy_round_trips_through_catalog_snapshot_and_csv(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("gpt-5-6-sol")
        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/model-decisions",
                json={
                    "model_ids": ["gpt-5-6-sol"],
                    "approval_status": "approved",
                    "recommendation_status": "recommended",
                    "usage_classification": "restricted",
                    "usage_classification_notes": "Approved team access only.",
                    "reasoning_effort_ceiling": "high",
                    "restricted_modes": ["ultra"],
                    "usage_policy_notes": "Allowed through High; Ultra requires separate review.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendation_status"], "recommended")
        self.assertEqual(response.json()["usage_classification"], "restricted")
        self.assertEqual(response.json()["reasoning_effort_ceiling"], "high")
        self.assertEqual(response.json()["restricted_modes"], ["ultra"])

        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "gpt-5-6-sol")
        self.assertEqual(model["reasoning_effort_ceiling"], "high")
        self.assertEqual(model["restricted_modes"], ["ultra"])
        self.assertEqual(model["general_recommendation_status"], "recommended")
        self.assertEqual(model["usage_classification"], "restricted")
        snapshot = review_workbench.export_review_snapshot()
        self.assertEqual(snapshot["schema_version"], 5)
        policy_row = next(row for row in snapshot["model_approvals"] if row["id"] == "gpt-5-6-sol")
        self.assertEqual(policy_row["usage_classification"], "restricted")
        self.assertEqual(policy_row["usage_classification_notes"], "Approved team access only.")
        self.assertEqual(policy_row["reasoning_effort_ceiling"], "high")
        self.assertEqual(json.loads(policy_row["restricted_modes_json"]), ["ultra"])
        csv_text = catalog_export.render_model_metadata_list([model], output_format="csv")
        self.assertIn("reasoning_effort_ceiling", csv_text.splitlines()[0])
        self.assertIn("restricted_modes", csv_text.splitlines()[0])
        self.assertIn("usage_classification", csv_text.splitlines()[0])

        with self.engine.begin() as conn:
            conn.execute(models_table.update().where(models_table.c.id == "gpt-5-6-sol").values(
                usage_classification="unclassified", usage_classification_notes=None,
                usage_classification_updated_at=None, reasoning_effort_ceiling=None,
                restricted_modes_json="[]", usage_policy_notes=None,
            ))
        review_workbench.import_review_snapshot(snapshot)
        restored = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "gpt-5-6-sol")
        self.assertEqual(restored["reasoning_effort_ceiling"], "high")
        self.assertEqual(restored["restricted_modes"], ["ultra"])
        self.assertEqual(restored["usage_classification"], "restricted")
        self.assertEqual(restored["usage_classification_notes"], "Approved team access only.")

    def test_skipped_source_run_serializes_in_update_history(self) -> None:
        with self.engine.begin() as conn:
            log_id = conn.execute(update_log_table.insert().values(
                started_at="2026-07-14T00:00:00Z", completed_at="2026-07-14T00:00:01Z",
                triggered_by="manual", status="completed",
            )).inserted_primary_key[0]
            conn.execute(source_runs_table.insert().values(
                update_log_id=log_id, source_name="model_discovery:openai",
                started_at="2026-07-14T00:00:00Z", completed_at="2026-07-14T00:00:01Z",
                status="skipped", records_found=0, error_message="Missing OPENAI_API_KEY",
            ))
        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).get(f"/api/update/history/{log_id}/sources")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["status"], "skipped")

    def test_general_model_decision_normalizes_discouraged_to_not_recommended(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("discouraged-alias-model")

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/model-decisions",
                json={
                    "model_ids": ["discouraged-alias-model"],
                    "recommendation_status": "discouraged",
                    "recommendation_notes": "Legacy discouraged decision.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendation_status"], "not_recommended")
        with self.engine.begin() as conn:
            model_row = conn.execute(
                models_table.select().where(models_table.c.id == "discouraged-alias-model")
            ).mappings().one()
        self.assertEqual(model_row["general_recommendation_status"], "not_recommended")

    def test_catalog_lists_positive_metric_use_case_fits_without_decision_statuses(self) -> None:
        self._insert_review_model("suggested-use-model")
        with self.engine.begin() as conn:
            conn.execute(
                recommendation_proposals_table.insert(),
                [
                    {
                        "profile_id": "australian_bank",
                        "model_id": "suggested-use-model",
                        "use_case_id": "customer_support",
                        "proposed_status": "recommended",
                        "score": 87.5,
                        "confidence": 0.82,
                        "blockers_json": "[]",
                        "warnings_json": '["Monitor hallucinations."]',
                        "reasons_json": '["Strong instruction following."]',
                        "required_controls_json": '["Human escalation"]',
                        "policy_version": "test-policy",
                        "computed_at": "2026-07-14T00:00:00Z",
                        "source_profile_json": "{}",
                    },
                    {
                        "profile_id": "australian_bank",
                        "model_id": "suggested-use-model",
                        "use_case_id": "high_risk_decisions",
                        "proposed_status": "not_recommended",
                        "score": 91.0,
                        "confidence": 0.9,
                        "blockers_json": '["High risk."]',
                        "warnings_json": "[]",
                        "reasons_json": "[]",
                        "required_controls_json": "[]",
                        "policy_version": "test-policy",
                        "computed_at": "2026-07-14T00:00:00Z",
                        "source_profile_json": "{}",
                    },
                ],
            )

        model = next(
            model for model in review_workbench.build_review_catalog()["models"]
            if model["id"] == "suggested-use-model"
        )

        self.assertEqual(len(model["suggested_use_cases"]), 1)
        suggestion = model["suggested_use_cases"][0]
        self.assertEqual(suggestion["use_case_id"], "customer_support")
        self.assertEqual(suggestion["fit_score"], 87.5)
        self.assertNotIn("recommendation_status", suggestion)
        self.assertNotIn("approved_for_use", suggestion)

    def test_review_model_approval_route_tracks_unreviewed_state(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        self._insert_review_model("triage-model")

        with patch("backend.main.bootstrap"):
            client = TestClient(main.app)
            not_approved_response = client.post(
                "/api/review/model-approvals",
                json={
                    "model_ids": ["triage-model"],
                    "approval_status": "not_approved",
                    "approval_notes": "Reviewed and rejected for general use.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(not_approved_response.status_code, 200)
        self.assertEqual(not_approved_response.json()["approval_status"], "not_approved")
        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "triage-model")
        self.assertFalse(model["general_approved_for_use"])
        self.assertEqual(model["general_approval_status"], "not_approved")
        self.assertIsNotNone(model["general_approval_updated_at"])

        with patch("backend.main.bootstrap"):
            unreviewed_response = TestClient(main.app).post(
                "/api/review/model-approvals",
                json={
                    "model_ids": ["triage-model"],
                    "approval_status": "unreviewed",
                    "approval_notes": "Should be cleared.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(unreviewed_response.status_code, 200)
        self.assertEqual(unreviewed_response.json()["approval_status"], "unreviewed")
        with self.engine.begin() as conn:
            row = conn.execute(models_table.select().where(models_table.c.id == "triage-model")).mappings().one()
        self.assertEqual(row["general_approved_for_use"], 0)
        self.assertIsNone(row["general_approval_notes"])
        self.assertIsNone(row["general_approval_updated_at"])
        model = next(model for model in review_workbench.build_review_catalog()["models"] if model["id"] == "triage-model")
        self.assertEqual(model["general_approval_status"], "unreviewed")

    def test_seed_reapply_preserves_general_model_approval(self) -> None:
        review_workbench.apply_model_approvals(
            model_ids=["gpt-5-4"],
            approved_for_use=True,
            approval_notes="General approval survives seed refresh.",
        )

        with self.engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

        model = next(model for model in update_engine.list_models() if model["id"] == "gpt-5-4")
        self.assertTrue(model["general_approved_for_use"])
        self.assertEqual(model["general_approval_notes"], "General approval survives seed refresh.")

    def test_add_model_route_creates_manual_listing(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"

        with patch("backend.main.bootstrap"):
            response = TestClient(main.app).post(
                "/api/review/models",
                json={
                    "name": "Manual Workbench Model",
                    "provider": "Manual Provider",
                    "model_roles": "embedding",
                    "catalog_status": "provisional",
                    "notes": "Added in the review workbench.",
                },
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_id"], "manual-workbench-model")
        model = next(model for model in update_engine.list_models() if model["id"] == "manual-workbench-model")
        self.assertEqual(model["catalog_status"], "provisional")
        self.assertEqual(model["model_roles"], ["embedding"])
        self.assertEqual(model["metadata_source_name"], "manual")

    def test_manual_decision_survives_bootstrap_and_recommendation_sync(self) -> None:
        self._insert_review_model("persistence-model")

        review_workbench.apply_review_decisions(
            model_ids=["persistence-model"],
            use_case_ids=["customer_support"],
            approved_for_use=True,
            recommendation_status="recommended",
            recommendation_notes="Human decision survives generated proposals.",
        )
        update_engine.BOOTSTRAPPED = False
        update_engine.bootstrap()
        recommendation_engine.sync_recommendation_proposals()

        model = next(model for model in update_engine.list_models() if model["id"] == "persistence-model")
        approval = model["use_case_approvals"]["customer_support"]
        self.assertTrue(approval["approved_for_use"])
        self.assertEqual(approval["recommendation_status"], "recommended")
        self.assertEqual(approval["effective_recommendation_status"], "recommended")

    def test_snapshot_export_import_restores_manual_models_statuses_and_decisions(self) -> None:
        os.environ[main.ADMIN_TOKEN_ENV_VAR] = "secret-token"
        review_workbench.add_review_model(
            name="Snapshot Manual Model",
            provider="Snapshot Provider",
            model_id="snapshot-manual-model",
            catalog_status="deprecated",
            notes="Manual snapshot model.",
        )
        review_workbench.apply_review_decisions(
            model_ids=["snapshot-manual-model"],
            use_case_ids=["customer_support"],
            approved_for_use=True,
            recommendation_status="not_recommended",
            recommendation_notes="Snapshot decision.",
        )
        review_workbench.apply_model_decisions(
            model_ids=["snapshot-manual-model"],
            approval_status="approved",
            approval_notes="Snapshot general model approval.",
            recommendation_status="acceptable",
            recommendation_notes="Snapshot acceptable recommendation.",
            usage_classification="prohibited",
            usage_classification_notes="Do not deploy in production.",
        )

        with patch("backend.main.bootstrap"):
            client = TestClient(main.app)
            export_response = client.post(
                "/api/review/snapshots/export",
                json={},
                headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
            )
        self.assertEqual(export_response.status_code, 200)
        snapshot = export_response.json()
        self.assertEqual(len(snapshot["model_approvals"]), 1)
        self.assertEqual(snapshot["model_approvals"][0]["approval_status"], "approved")
        self.assertEqual(snapshot["schema_version"], 5)
        self.assertEqual(snapshot["model_approvals"][0]["general_recommendation_status"], "acceptable")
        self.assertEqual(snapshot["model_approvals"][0]["usage_classification"], "prohibited")

        second_tempdir = tempfile.TemporaryDirectory()
        second_engine = get_engine(f"sqlite:///{Path(second_tempdir.name) / 'import.sqlite'}")
        init_db(second_engine)
        with second_engine.begin() as conn:
            seed_reference_data(conn, include_seed_scores=False)

        active_engine = update_engine.ENGINE
        active_bootstrapped = update_engine.BOOTSTRAPPED
        try:
            update_engine.ENGINE = second_engine
            update_engine.BOOTSTRAPPED = True
            with patch("backend.main.bootstrap"):
                import_response = TestClient(main.app).post(
                    "/api/review/snapshots/import",
                    json=snapshot,
                    headers={main.ADMIN_TOKEN_HEADER: "secret-token"},
                )
            self.assertEqual(import_response.status_code, 200)
            self.assertEqual(import_response.json()["created_manual_model_count"], 1)
            self.assertEqual(import_response.json()["model_approval_updated_count"], 1)
            imported_model = next(
                model for model in update_engine.list_models() if model["id"] == "snapshot-manual-model"
            )
            self.assertEqual(imported_model["catalog_status"], "deprecated")
            self.assertTrue(imported_model["general_approved_for_use"])
            self.assertEqual(imported_model["general_approval_notes"], "Snapshot general model approval.")
            self.assertEqual(imported_model["general_recommendation_status"], "acceptable")
            self.assertEqual(
                imported_model["general_recommendation_notes"],
                "Snapshot acceptable recommendation.",
            )
            self.assertEqual(imported_model["usage_classification"], "prohibited")
            self.assertEqual(
                imported_model["usage_classification_notes"],
                "Do not deploy in production.",
            )
            approval = imported_model["use_case_approvals"]["customer_support"]
            self.assertTrue(approval["approved_for_use"])
            self.assertEqual(approval["recommendation_status"], "not_recommended")
        finally:
            update_engine.ENGINE = active_engine
            update_engine.BOOTSTRAPPED = active_bootstrapped
            second_engine.dispose()
            second_tempdir.cleanup()

    def test_snapshot_v3_import_maps_general_restricted_to_usage_classification(self) -> None:
        self._insert_review_model("snapshot-v3-restricted")
        snapshot = {
            "schema_version": 3,
            "model_approvals": [
                {
                    "id": "snapshot-v3-restricted",
                    "general_recommendation_status": "restricted",
                    "general_recommendation_notes": "Legacy controlled access.",
                    "general_recommendation_updated_at": "2026-07-16T03:04:05Z",
                }
            ],
        }

        result = review_workbench.import_review_snapshot(snapshot)
        model = next(
            model for model in review_workbench.build_review_catalog()["models"]
            if model["id"] == "snapshot-v3-restricted"
        )

        self.assertEqual(result["schema_version"], 5)
        self.assertEqual(result["model_approval_updated_count"], 1)
        self.assertEqual(model["general_recommendation_status"], "unrated")
        self.assertIsNone(model["general_recommendation_notes"])
        self.assertIsNone(model["general_recommendation_updated_at"])
        self.assertEqual(model["usage_classification"], "restricted")
        self.assertEqual(model["usage_classification_notes"], "Legacy controlled access.")
        self.assertEqual(model["usage_classification_updated_at"], "2026-07-16T03:04:05Z")

    def test_snapshot_import_accepts_versions_one_through_five(self) -> None:
        for schema_version in range(1, 6):
            with self.subTest(schema_version=schema_version):
                result = review_workbench.import_review_snapshot({"schema_version": schema_version})
                self.assertEqual(result["schema_version"], 5)

        with self.assertRaisesRegex(ValueError, "Unsupported review snapshot schema version"):
            review_workbench.import_review_snapshot({"schema_version": 6})

    def test_latest_sync_metadata_uses_started_at_for_running_run(self) -> None:
        self._insert_update_log(
            started_at="2026-07-13T01:00:00Z",
            completed_at="2026-07-13T01:05:00Z",
            status="completed",
        )
        running_id = self._insert_update_log(
            started_at="2026-07-13T02:00:00Z",
            completed_at=None,
            status="running",
        )

        metadata = review_workbench._latest_sync_metadata()

        self.assertEqual(metadata["last_sync_at"], "2026-07-13T02:00:00Z")
        self.assertEqual(metadata["last_sync_status"], "running")
        self.assertEqual(metadata["last_sync_log_id"], running_id)

    def test_latest_sync_metadata_uses_terminal_completion_time_and_stable_ordering(self) -> None:
        self._insert_update_log(
            started_at="2026-07-13T01:00:00Z",
            completed_at="2026-07-13T01:10:00Z",
            status="completed",
        )
        failed_id = self._insert_update_log(
            started_at="2026-07-13T02:00:00Z",
            completed_at="2026-07-13T02:07:00Z",
            status="failed",
        )

        metadata = review_workbench._latest_sync_metadata()

        self.assertEqual(metadata["last_sync_at"], "2026-07-13T02:07:00Z")
        self.assertEqual(metadata["last_sync_status"], "failed")
        self.assertEqual(metadata["last_sync_log_id"], failed_id)

        completed_id = self._insert_update_log(
            started_at="2026-07-13T02:00:00Z",
            completed_at="2026-07-13T02:09:00Z",
            status="completed",
        )
        metadata = review_workbench._latest_sync_metadata()
        self.assertEqual(metadata["last_sync_at"], "2026-07-13T02:09:00Z")
        self.assertEqual(metadata["last_sync_status"], "completed")
        self.assertEqual(metadata["last_sync_log_id"], completed_id)

    def test_sqlite_database_updated_at_uses_newest_database_or_wal_mtime(self) -> None:
        database_path = Path(self.tempdir.name) / "mtime.sqlite"
        wal_path = Path(f"{database_path}-wal")
        database_path.touch()
        wal_path.touch()
        os.utime(database_path, (1_700_000_000, 1_700_000_000))
        os.utime(wal_path, (1_700_001_000, 1_700_001_000))
        mtime_engine = get_engine(f"sqlite:///{database_path}")
        try:
            self.assertEqual(sqlite_database_updated_at(mtime_engine), "2023-11-14T22:30:00Z")
        finally:
            mtime_engine.dispose()

    def _insert_update_log(self, *, started_at: str, completed_at: str | None, status: str) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                update_log_table.insert(),
                {
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "triggered_by": "test",
                    "status": status,
                },
            )
            return int(result.inserted_primary_key[0])

    def _insert_review_model(
        self,
        model_id: str,
        *,
        family_id: str = "provider::review-model",
        family_name: str = "Review Model",
        release_date: str | None = None,
        release_date_confidence: str | None = None,
        model_type: str = "proprietary",
        model_roles: list[str] | None = None,
        small_model_candidate: bool = False,
        model_size_class: str | None = None,
        parameter_count_b: float | None = None,
        include_default_scores: bool = True,
        model_card_url: str | None = "https://example.com/model-card",
        capabilities: list[str] | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                models_table.insert(),
                {
                    "id": model_id,
                    "name": model_id,
                    "provider": "Bank Test Provider",
                    "type": model_type,
                    "catalog_status": "tracked",
                    "family_id": family_id,
                    "family_name": family_name,
                    "canonical_model_id": family_id,
                    "canonical_model_name": family_name,
                    "model_roles_json": json.dumps(model_roles or ["generator"], ensure_ascii=True),
                    "model_card_url": model_card_url,
                    "model_card_verified_at": "2026-07-01T00:00:00Z" if model_card_url else None,
                    "release_date": release_date,
                    "release_date_precision": "day" if release_date else None,
                    "release_date_confidence": release_date_confidence,
                    "release_date_source_name": "test-fixture" if release_date else None,
                    "release_date_source_url": "https://example.com/release" if release_date else None,
                    "release_date_verified_at": "2026-07-01T00:00:00Z" if release_date else None,
                    "parameter_count_b": parameter_count_b,
                    "model_size_class": model_size_class,
                    "small_model_candidate": 1 if small_model_candidate else 0,
                    "model_size_source_name": "test-fixture" if parameter_count_b is not None or model_size_class else None,
                    "model_size_source_url": "https://example.com/model-size" if parameter_count_b is not None or model_size_class else None,
                    "model_size_verified_at": "2026-07-01T00:00:00Z" if parameter_count_b is not None or model_size_class else None,
                    "license_id": "apache-2.0",
                    "license_name": "Apache 2.0",
                    "training_data_summary": "Reviewed public and licensed data.",
                    "capabilities_json": json.dumps(capabilities or [], ensure_ascii=True),
                    "active": 1,
                },
            )
            if not include_default_scores:
                return
            conn.execute(
                scores_table.insert(),
                [
                    {
                        "model_id": model_id,
                        "benchmark_id": benchmark_id,
                        "value": value,
                        "raw_value": str(value),
                        "collected_at": "2026-07-01T00:00:00Z",
                        "source_type": "primary",
                        "verified": 1,
                    }
                    for benchmark_id, value in (
                        ("chatbot_arena", 1400.0),
                        ("aa_cost", 0.20),
                        ("aa_speed", 120.0),
                        ("ifeval", 82.0),
                        ("ailuminate", 75.0),
                    )
                ],
            )

    def _insert_inference_destination(
        self,
        model_id: str,
        destination_id: str,
        name: str,
        *,
        hyperscaler: str = "Azure",
        regions: list[str] | None = None,
    ) -> None:
        resolved_regions = regions or ["eastus2"]
        with self.engine.begin() as conn:
            conn.execute(
                model_inference_destinations_table.insert(),
                {
                    "model_id": model_id,
                    "destination_id": destination_id,
                    "name": name,
                    "hyperscaler": hyperscaler,
                    "availability_scope": "Configured account",
                    "availability_note": "Live from configured hyperscaler catalog.",
                    "location_scope": "Configured account regions",
                    "regions_json": json.dumps(resolved_regions, ensure_ascii=True),
                    "region_count": len(resolved_regions),
                    "deployment_modes_json": '["Provisioned"]',
                    "pricing_label": "Configured account pricing",
                    "pricing_note": "Pricing depends on configured account.",
                    "sources_json": "[]",
                    "catalog_model_id": model_id,
                    "synced_at": "2026-07-01T00:00:00Z",
                },
            )


if __name__ == "__main__":
    unittest.main()
