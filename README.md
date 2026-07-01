# LLM Benchmarking

LLM Benchmarking is a local backend-only model intelligence workspace. It stores public benchmark scores, model metadata, provider-origin metadata, license and provenance review fields, use-case approvals, inference-location coverage, and update history in SQLite.

The primary output is now a simple model metadata list:

```bash
python -m backend list-models
```

That command prints a JSON array. Each model item includes the serialized metadata used by the old dashboard, including scores, source details, provider origin, license policy, provenance policy, use-case approvals, inference destinations, OpenRouter market metadata, model-card fields, and family/duplicate curation fields.

## Stack

- FastAPI backend in [backend/main.py](backend/main.py)
- SQLite database at `data/db.sqlite`
- SQLAlchemy Core schema in [backend/database.py](backend/database.py)
- Source adapters in [backend/sources](backend/sources)
- Backend CLI in [backend/cli.py](backend/cli.py)

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
  Prints or exports the complete active model metadata list.

If you want the older one-shot bootstrap-and-ingest flow, it still exists:

```bash
python -m backend.bootstrap_db
```

## Output

Print a pretty JSON list to stdout:

```bash
python -m backend list-models
```

Write the list to a file:

```bash
python -m backend list-models --output output/model-metadata.json
```

Write one complete model object per line:

```bash
python -m backend list-models --format jsonl --output output/model-metadata.jsonl
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

## Current Data Sources

Benchmark adapters:

- Artificial Analysis
- Chatbot Arena
- AILuminate
- GPQA Diamond
- IFEval
- MMMU
- SWE-bench Verified
- Terminal-Bench
- FaithJudge
- Vectara Hallucination

Metadata and catalog enrichments:

- OpenRouter models and market/ranking signals
- Hugging Face model-card metadata
- Hyperscaler inference catalogs for AWS Bedrock, Azure AI Foundry, and Google Vertex AI

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
- `model-card-audit` reports current model-card field coverage plus obvious extraction-quality issues.
- `model-license-sync` fills missing licenses using safe open-weight family propagation, a `Proprietary` fallback for missing proprietary licenses, and tracked exact/family overrides from [backend/model_license_baseline.json](backend/model_license_baseline.json).
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

`aws-bedrock` can run in pricing-only mode without credentials. `azure-ai-foundry` has a public-pricing-only fallback without credentials. `google-vertex-ai` has a published-endpoints-only fallback without credentials.
