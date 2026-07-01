# LLM Benchmarking

LLM Benchmarking is a local backend-only model intelligence workspace. It stores public benchmark scores, model metadata, provider-origin metadata, license and provenance review fields, use-case approvals, inference-location coverage, and update history in SQLite.

The primary output is now a simple model metadata list:

```bash
python -m backend list-models
```

That command prints a JSON array. Each model item includes the serialized metadata used by the old dashboard, including scores, source details, provider origin, license policy, provenance policy, use-case approvals, inference destinations, OpenRouter market metadata, model-card fields, and family/duplicate curation fields.
It also writes a CSV sidecar to `output/model-list.csv` by default for spreadsheet review.

## Stack

- FastAPI backend in [backend/main.py](backend/main.py)
- SQLite database at `data/db.sqlite`
- SQLAlchemy Core schema in [backend/database.py](backend/database.py)
- Source adapters in [backend/sources](backend/sources)
- Backend CLI in [backend/cli.py](backend/cli.py)
- Update support modules split orchestration, OpenRouter metadata parsing, Hugging Face model-card extraction, and ranking response construction out of [backend/update_engine.py](backend/update_engine.py).

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
  Runs the benchmark ingestion/update pipeline, refreshes external OpenRouter/model-card/market metadata, and writes update history plus audit results.
- `python -m backend list-models`
  Prints or exports the complete active model metadata list and writes a default CSV sidecar.

If you want the older one-shot bootstrap-and-ingest flow, it still exists:

```bash
python -m backend.bootstrap_db
```

## Output

Print a pretty JSON list to stdout:

```bash
python -m backend list-models
```

By default this also writes `output/model-list.csv`. Use `--csv-output <path>` to choose another CSV path, or `--no-csv` to suppress the sidecar when a script needs stdout only.

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

## Current Data Sources

Benchmark adapters:

- Artificial Analysis
- Chatbot Arena
- AILuminate
- GPQA Diamond
- IFEval
- LiveBench
- MMMU
- SWE-bench Verified
- Terminal-Bench
- FaithJudge
- Vectara Hallucination

Metadata and catalog enrichments:

- OpenRouter models and market/ranking signals
  Recent OpenRouter models from the last 60 days are imported as provisional rows when no exact OpenRouter ID or canonical slug is already represented.
- Hugging Face model-card metadata
- Hyperscaler inference catalogs for AWS Bedrock, Azure AI Foundry, and Google Vertex AI

The LiveBench adapter imports the latest public static LiveBench leaderboard
release from the official site artifacts, currently `2026-01-08`, and stores
overall plus category-level scores. Task-level LiveBench scores remain raw
metadata until a use case needs that granularity.

## Governance Model

The approval model is more than a global allow-list:

- approval is stored per `model x use case`
- recommendation is stored separately from approval
- inference-route approval can be stored per `model x use case x provider x location`
- family bulk approval actions write through to exact models rather than using hidden inheritance
- new models discovered in updates can be surfaced for review
- provider-origin and model-curation state can be exported back to repo-backed baselines

## Data Durability

SQLite is the runtime store, but important manual metadata is also kept in tracked repo baselines so it does not get lost on rebuilds:

- provider origin baseline: [backend/provider_origin_baseline.json](backend/provider_origin_baseline.json)
- model curation baseline: [backend/model_curation_baseline.json](backend/model_curation_baseline.json)
- model license baseline: [backend/model_license_baseline.json](backend/model_license_baseline.json)

Those baselines are applied during bootstrap and can be re-exported from the live DB. Network-backed metadata refreshes are intentionally kept out of bootstrap so API startup stays local and predictable.

## CLI Reference

Common commands:

```bash
python -m backend bootstrap
python -m backend update
python -m backend update --benchmarks terminal_bench swebench_verified
python -m backend list-models
python -m backend list-models --format jsonl --output output/model-metadata.jsonl
python -m backend list-models --format csv --output output/model-metadata.csv
python -m backend inference-sync
python -m backend inference-sync --destinations aws-bedrock azure-ai-foundry
python -m backend model-card-sync
python -m backend model-card-audit
python -m backend model-license-sync
python -m backend model-license-sync --refresh-model-cards
python -m backend provider-origin-export
python -m backend model-curation-export
```

Notes:

- `inference-sync` supports destination subsets.
- `model-card-sync` backfills Hugging Face-backed model-card metadata such as license, docs URL, repo URL, paper URL, languages, capabilities, intended use, and limitations.
- `model-card-audit` reports current model-card field coverage, extraction-quality issues, and a `commercial_production` quality gate. The gate treats missing license metadata, generic license markers, and incomplete derivative provenance as blockers; missing source URLs or suspicious extraction output as warnings; and richer model-card enrichment as backlog-only cleanup.
- `model-license-sync` fills missing licenses using safe open-weight family propagation, a `Proprietary` fallback for missing proprietary licenses, and tracked exact/family overrides from [backend/model_license_baseline.json](backend/model_license_baseline.json).
- `list-models` writes `output/model-list.csv` by default in addition to the requested stdout/file format; pass `--no-csv` when you do not want the sidecar.
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
