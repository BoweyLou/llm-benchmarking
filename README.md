# LLM Benchmarking

LLM Benchmarking is a local backend-only model intelligence workspace. It stores public benchmark scores, model metadata, size-aware catalog discovery fields, provider-origin metadata, license and provenance review fields, use-case approvals, inference-location coverage, and update history in SQLite.

The primary output is now a simple model metadata list:

```bash
python -m backend list-models
```

That command prints a JSON array. Each model item includes the serialized metadata used by the old dashboard, including scores, source details, model roles, model size fields, small-model candidate visibility, provider origin, license policy, provenance policy, use-case approvals, inference destinations, OpenRouter market metadata, model-card fields, and family/duplicate curation fields.
It also writes spreadsheet-friendly CSV output to `output/model-list.csv` by default, plus normalized companion CSVs for scores, use-case approvals, inference destinations, provider-origin countries, and source freshness. When recommendation proposals have been synced, use-case approvals include proposed and effective recommendation fields.

## Stack

- FastAPI backend in [backend/main.py](backend/main.py)
- SQLite database at `data/db.sqlite`
- SQLAlchemy Core schema in [backend/database.py](backend/database.py)
- Source adapters in [backend/sources](backend/sources)
- Backend CLI in [backend/cli.py](backend/cli.py)
- Update support modules split orchestration, OpenRouter metadata parsing, curated Hugging Face model discovery, Hugging Face model-card extraction, and ranking response construction out of [backend/update_engine.py](backend/update_engine.py).

## Quick Start

```bash
git clone https://github.com/BoweyLou/llm-benchmarking.git
cd llm-benchmarking

python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

python -m backend bootstrap
python -m backend update
python -m backend list-models --output output/model-metadata.json
```

What those commands do:

- `python -m backend bootstrap`
  Creates the schema, repairs local runtime state, seeds reference data, and applies repo-backed provider-origin, model-curation, and model-license baselines. It does not call external metadata services.
- `python -m backend update`
  Runs the benchmark ingestion/update pipeline, refreshes external OpenRouter/catalog-discovery/model-card/market metadata, and writes update history plus audit results. Full updates run curated model discovery; benchmark-scoped updates skip it unless `--refresh-model-discovery` is passed.
- `python -m backend list-models`
  Prints or exports the complete active model metadata list and writes a default clean CSV bundle.

If you want the older one-shot bootstrap-and-ingest flow, it still exists:

```bash
python -m backend.bootstrap_db
```

## Output

Print a pretty JSON list to stdout:

```bash
python -m backend list-models
```

By default this also writes `output/model-list.csv` and companion files named `model-list-scores.csv`, `model-list-use-case-approvals.csv`, `model-list-inference-destinations.csv`, `model-list-provider-origin-countries.csv`, and `model-list-source-freshness.csv`. The main CSV keeps model-level columns readable and replaces nested JSON blobs with summary columns. Use `--csv-output <path>` to choose another CSV path, `--no-csv-sidecars` to suppress companion files, or `--no-csv` to suppress the CSV bundle when a script needs stdout only.

Write the list to a file:

```bash
python -m backend list-models --output output/model-metadata.json
```

Write one complete model object per line:

```bash
python -m backend list-models --format jsonl --output output/model-metadata.jsonl
```

Write only CSV:

```bash
python -m backend list-models --format csv --output output/model-metadata.csv
```

Write the legacy one-row-per-model CSV with nested JSON cells:

```bash
python -m backend list-models --format raw-csv --output output/model-metadata-raw.csv
```

## Recommendation Proposals

Manual use-case recommendation ratings remain the source of human approval. The recommendation proposal engine adds a separate, auditable policy layer that can be regenerated from the current catalog:

```bash
python -m backend recommendation-audit
python -m backend recommendation-sync
python -m backend list-models --output output/model-metadata.json
```

`recommendation-audit` is read-only and prints a summary by default; pass `--json` for the full proposal payload. `recommendation-sync` stores proposal rows in SQLite under `model_use_case_recommendation_proposals`. Both commands support `--use-case <id>` to limit the run.

The first profile is `australian_bank`. It applies conservative gates for regulated banking use: commercial license and unverified derivative provenance blockers, tracked-catalog requirements for governed use cases, model-card requirements, bank-approved inference-route requirements, Australian-route requirements for customer or personal-information use cases, and benchmark score/confidence thresholds. The profile was shaped around official guidance from [APRA CPS 230](https://www.apra.gov.au/standards/cps-230), [APRA CPS 234 cyber security guidance](https://www.apra.gov.au/cyber-security), [OAIC commercial AI privacy guidance](https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/guidance-on-privacy-and-the-use-of-commercially-available-ai-products), and [ASIC AI governance observations](https://www.asic.gov.au/about-asic/news-centre/find-a-media-release/2024-releases/24-238mr-asic-warns-governance-gap-could-emerge-in-first-report-on-ai-adoption-by-licensees/).

Each use-case approval can then carry:

- `recommendation_status`: manual human rating.
- `auto_recommendation_status`: existing automatic hard blockers from license/provenance overlays.
- `proposed_recommendation_status`: generated profile proposal.
- `effective_recommendation_status`: manual rating when present, otherwise automatic hard blocker, otherwise proposal.
- proposal blockers, warnings, reasons, required controls, score, confidence, policy version, and computed timestamp.

## Banking Review Utility

For spreadsheet review, use the local banking-review utility. It regenerates
the `australian_bank` recommendation proposals by default, then writes a
combined `model x use case` CSV with the normalized model-list columns and the
manual/proposed/effective recommendation fields:

```bash
python -m backend banking-review export
```

The default output is
`output/banking-model-list-with-recommendations.csv`. Use `--output <path>` to
choose another file, or `--skip-sync` when you need to export the current
database state without refreshing proposal rows.

Manual curation commands write local SQLite review state:

```bash
python -m backend banking-review add-model --name "Vendor Model" --provider "Vendor"
python -m backend banking-review set --model-id vendor-model --use-case customer_support --approval approved --recommendation recommended --notes "Approved for pilot."
python -m backend banking-review set --family-id openai::gpt-5 --use-case coding --approval approved --recommendation recommended
python -m backend banking-review deprecate --model-id old-model --mark-not-recommended --all-use-cases --notes "Deprecated from banking review."
```

`set` accepts repeatable `--model-id`, repeatable `--family-id`, repeatable
`--use-case`, or `--all-use-cases`. `deprecate` sets
`catalog_status=deprecated` and keeps the row active so it remains visible in
exports; add `--mark-not-recommended` when the deprecation should also become a
manual recommendation rating.

## Run Locally

```bash
source .venv/bin/activate
export LLM_BENCHMARKING_ADMIN_TOKEN="$(python - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
uvicorn backend.main:app --reload --port 8000
```

Useful local URLs:

- Root model list: `http://127.0.0.1:8000/`
- Model list API: `http://127.0.0.1:8000/api/models`
- API docs: `http://127.0.0.1:8000/docs`

The backend bootstraps local schema and repo-backed baselines on startup if needed. Startup does not perform network metadata refreshes; use the explicit CLI or API update paths for that work.

Read-only routes do not require credentials. Write routes are disabled unless
`LLM_BENCHMARKING_ADMIN_TOKEN` is set in the server environment. Send that value
with local mutation requests by using either
`X-LLM-Benchmarking-Admin-Token: <token>` or `Authorization: Bearer <token>`.
For local operation, bind the server to loopback or another trusted private
interface rather than exposing the admin token on a public network.

## Schema Migrations

Fresh SQLite databases are initialized from the current schema in [backend/database.py](backend/database.py). Upgrade and repair work is tracked in the `schema_migrations` table, and new schema changes should be added to the `SCHEMA_MIGRATIONS` list instead of standalone bootstrap-time `ALTER TABLE` blocks.

Models carry explicit `model_roles` in exports and API responses. Existing
generator models default to `["generator"]`; embedding and reranker models use
separate roles so MTEB retrieval/reranking scores do not enter generator-model
rankings.

Models also carry size-aware catalog fields in exports and API responses:
`parameter_count_b`, `active_parameter_count_b`, `model_size_class`,
`small_model_candidate`, `model_size_source_name`, `model_size_source_url`, and
`model_size_verified_at`. These fields make small-model candidates visible in
the catalog without changing evidence-gated ranking semantics.

## Current Data Sources

For a detailed source-by-source data-flow diagram, source inventory, and
recommended ingest gaps, see [docs/data-ingest-map.md](docs/data-ingest-map.md).

Benchmark adapters:

- Artificial Analysis
- Artificial Analysis IFBench
- Chatbot Arena
- AILuminate
- Berkeley Function Calling Leaderboard
- BigCodeBench
- GPQA Diamond
- HELM Capabilities
- IFEval
- LiveBench
- LiveCodeBench
- MMMU
- MTEB retrieval/reranking
- RAGTruth
- SWE-bench Verified, Lite, Full, Multilingual, and Multimodal
- tau-bench
- Terminal-Bench
- FaithJudge
- Vectara Hallucination

Metadata and catalog enrichments:

- Curated Hugging Face model discovery for official/provider-owned repos
- OpenRouter models and market/ranking signals
  Recent OpenRouter models from the last 60 days are imported as provisional rows when no exact OpenRouter ID or canonical slug is already represented.
- Hugging Face model-card metadata
- Hyperscaler inference catalogs for AWS Bedrock, Azure AI Foundry, and Google Vertex AI

## Governance Model

The approval model is more than a global allow-list:

- approval is stored per `model x use case`
- recommendation is stored separately from approval
- recommendation proposals are regenerated policy output stored separately from manual ratings
- inference-route approval can be stored per `model x use case x provider x location`
- family bulk approval actions write through to exact models rather than using hidden inheritance
- new models discovered in updates can be surfaced for review
- provider-origin and model-curation state can be exported back to repo-backed baselines

## Data Durability

SQLite is the runtime store, but important manual metadata is also kept in tracked repo baselines so it does not get lost on rebuilds:

- provider origin baseline: [backend/provider_origin_baseline.json](backend/provider_origin_baseline.json)
- model discovery baseline: [backend/model_discovery_baseline.json](backend/model_discovery_baseline.json)
- model curation baseline: [backend/model_curation_baseline.json](backend/model_curation_baseline.json)
- model license baseline: [backend/model_license_baseline.json](backend/model_license_baseline.json)

Those baselines are applied during bootstrap and can be re-exported from the live DB. Network-backed metadata refreshes are intentionally kept out of bootstrap so API startup stays local and predictable.

## CLI Reference

Common commands:

```bash
python -m backend bootstrap
python -m backend update
python -m backend update --benchmarks terminal_bench swebench_verified
python -m backend update --benchmarks aa_cost aa_speed --refresh-model-discovery
python -m backend model-discovery-sync --source huggingface --family gemma
python -m backend list-models
python -m backend list-models --format jsonl --output output/model-metadata.jsonl
python -m backend list-models --format csv --output output/model-metadata.csv
python -m backend list-models --format raw-csv --output output/model-metadata-raw.csv
python -m backend inference-sync
python -m backend inference-sync --destinations aws-bedrock azure-ai-foundry
python -m backend model-card-sync
python -m backend model-card-audit
python -m backend recommendation-audit
python -m backend recommendation-sync
python -m backend banking-review export
python -m backend banking-review set --model-id gpt-5-4 --use-case customer_support --approval approved --recommendation recommended
python -m backend banking-review set --family-id openai::gpt-5 --use-case coding --approval approved
python -m backend banking-review deprecate --model-id old-model --mark-not-recommended --all-use-cases
python -m backend model-license-sync
python -m backend model-license-sync --refresh-model-cards
python -m backend provider-origin-export
python -m backend model-curation-export
```

Notes:

- Full `update` runs curated Hugging Face model discovery before model-card refresh. `update --benchmarks ...` skips that discovery phase unless `--refresh-model-discovery` is passed.
- `model-discovery-sync` runs only the curated metadata discovery lane. The v1 repo-backed baseline covers official Google Gemma discovery and intentionally excludes community quantizations/fine-tunes unless a trusted mirror is configured.
- `inference-sync` supports destination subsets.
- `model-card-sync` backfills Hugging Face-backed model-card metadata such as license, docs URL, repo URL, paper URL, languages, capabilities, intended use, and limitations.
- `model-card-audit` reports current model-card field coverage, extraction-quality issues, and a `commercial_production` quality gate. The gate treats missing license metadata, generic license markers, and incomplete derivative provenance as blockers; missing source URLs or suspicious extraction output as warnings; and richer model-card enrichment as backlog-only cleanup.
- `recommendation-audit` previews generated use-case recommendation proposals. `recommendation-sync` persists them so `list-models`, CSV export, and the API include proposed/effective recommendation fields.
- `banking-review export` writes the review-friendly combined CSV. `banking-review set` and `banking-review deprecate` apply model- or family-scoped manual approval and recommendation decisions.
- `model-license-sync` fills missing licenses using safe open-weight family propagation, a `Proprietary` fallback for missing proprietary licenses, and tracked exact/family overrides from [backend/model_license_baseline.json](backend/model_license_baseline.json).
- `list-models` writes a clean CSV bundle to `output/model-list*.csv` by default in addition to the requested stdout/file format; pass `--no-csv` when you do not want the bundle, or `--no-csv-sidecars` when you only want the main model CSV.
- `provider-origin-export` and `model-curation-export` push live curation back into the tracked baseline JSON files.

## API Surface

The core API is in [backend/main.py](backend/main.py). High-level groups:

- model list: `/` and `/api/models`
- catalog metadata: `/api/providers`, `/api/benchmarks`, `/api/use-cases`
- rankings: `/api/rankings`
- admin edits for provider metadata, approvals, inference-route approvals, manual benchmark scores, and model curation
- update operations: `/api/update`, `/api/update/status/{log_id}`, `/api/update/history`, source-run detail, raw source records, and audit output
- market snapshots: `/api/market-snapshots`

All POST/PATCH/PUT mutation routes require the local admin token described in
the run instructions above. GET routes remain read-only and unauthenticated.

## Contributor Workflow

Backend checks:

```bash
PYTHON=python ./scripts/test_inference_suite.sh
```

The suite script compiles backend modules and runs package-aware unittest
discovery with `python -m unittest discover -s backend -t .`. Do not use
`python -m unittest discover backend`; that treats `backend/` as the import root
and imports `backend/sources` as a top-level `sources` package.

Inference sync smoke checks:

```bash
PYTHON=python ./scripts/test_inference_sync_smoke.sh
```

The smoke script accepts a subset, for example:

```bash
PYTHON=python ./scripts/test_inference_sync_smoke.sh aws-bedrock
PYTHON=python ./scripts/test_inference_sync_smoke.sh azure-ai-foundry google-vertex-ai
```

If `inference-sync` exits nonzero, the smoke script prints the captured stdout,
stderr, and exit code before failing. If JSON validation fails after a command
completes, it prints the captured sync payload with the failing reason.
Azure public retail pricing can rate-limit with HTTP 429; that destination is
reported as a retryable skipped result and accepted by smoke checks, while
non-rate-limit sync failures still fail the script.

`aws-bedrock` can run in pricing-only mode without credentials. `azure-ai-foundry` has a public-pricing-only fallback without credentials. `google-vertex-ai` has a published-endpoints-only fallback without credentials.
