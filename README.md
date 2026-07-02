# LLM Benchmarking

LLM Benchmarking is a local backend-only model intelligence workspace. It stores public benchmark scores, model metadata, release-date and age evidence, size-aware catalog discovery fields, provider-origin metadata, license and provenance review fields, use-case approvals, inference-location coverage, and update history in SQLite.

The primary output is now a simple model metadata list:

```bash
python -m backend list-models
```

That command prints a JSON array. Each model item includes the serialized metadata used by the old dashboard, including scores, source details, model roles, release-date provenance, model-age evidence, model size fields, small-model candidate visibility, provider origin, license policy, provenance policy, use-case approvals, inference destinations, OpenRouter market metadata, model-card fields, and family/duplicate curation fields.
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

## Banking Review Workbench

For interactive banking review, run the FastAPI app locally and open
`/review`. The workbench shows the model catalog with provider, use-case,
effective-recommendation, manual-recommendation, approval, family,
catalog-status, model-role, and small-model filters; a sortable model table;
family and needs-decision views; and a detail inspector for per-use-case
approval notes, manual ratings, generated blockers, warnings, and required
controls.

On tablet-width screens, the workbench keeps the filters and table usable first
and moves the inspector below the table so review controls remain reachable.

```bash
uvicorn backend.main:app --reload --port 8000
open http://127.0.0.1:8000/review
```

Review writes use the same admin guard as the other mutation routes. For local
development, set `LLM_BENCHMARKING_ADMIN_TOKEN` before starting the server, then
paste that value into the workbench token field. Without a token or trusted
tailnet mode, the workbench can read the catalog but cannot save decisions.
Saved decisions write to SQLite:

- `model_use_case_approvals` stores use-case approval, manual recommendation
  status, and notes.
- `models.catalog_status` stores listing state such as `tracked`,
  `provisional`, or `deprecated`.
- `model_use_case_recommendation_proposals` remains generated policy output and
  can be regenerated without overwriting manual decisions.

Use-case recommendations are reviewed through the active use case. Switch to
`Use-case review`, choose a use case in the left filter or right inspector, then
read the table columns as:

- `Proposed`: generated banking-profile recommendation.
- `Manual`: the reviewer override saved in SQLite.
- `Effective`: the value used by review/export surfaces. Manual wins when set,
  otherwise hard blockers win, otherwise the generated proposal is used.
- `Approval`: the separate approved/not-approved decision for that model and use
  case.

Select a model to review blockers, warnings, required controls, and notes in the
right inspector. Change `Manual rating` and `Approval`, then save. For many
models, filter first, use `Select all filtered` when needed, and apply the bulk
recommendation or approval action to the exact selected model IDs.
Use `Effective recommendation` to filter the final status shown in exports and
use `Manual recommendation` to filter only reviewer-saved overrides, including
rows where the manual rating has been cleared to `Unrated`.

The workbench can export and import a JSON review snapshot. Use that snapshot
when rebuilding a database so manual listings, deprecation markers, and
approval/recommendation rows can be restored.

The model table can also export CSV directly from the browser. Choose filtered,
selected, or all rows in the table toolbar, then use `Export CSV`. The CSV
contains the model listing fields plus the active use-case approval,
manual/proposed/effective recommendation, proposal blockers, warnings, and
required controls.

Bulk review actions can target the current visible page with the table checkbox
or the full filtered result set with `Select all filtered`. Selecting all
filtered rows replaces the current selection with the exact filtered model IDs
before a bulk action is saved.
Use `Not approved` to clear approval state in bulk. Use `Clear rating` only when
you want to reset the manual recommendation rating to `unrated` while leaving
approval state unchanged.

To run the workbench on the Proxmox tailnet host, use the deploy script:

```bash
scripts/deploy_proxmox_review_workbench.sh
```

The deploy binds the service to the host's Tailscale IPv4 address, enables
token-free writes for Tailscale clients with
`LLM_BENCHMARKING_TRUSTED_TAILNET_WRITES=1`, preserves the remote SQLite
database at `/var/lib/llm-benchmarking/db.sqlite`, and keeps an admin-token
fallback in `/etc/llm-benchmarking.env`. See
[docs/deploy/proxmox-review-workbench.md](docs/deploy/proxmox-review-workbench.md)
for service operations, fallback-token retrieval, and backup notes.

For spreadsheet review, the local `banking-review` utility remains available. It
regenerates the `australian_bank` recommendation proposals by default, then
writes a combined `model x use case` CSV with the normalized model-list columns
and the manual/proposed/effective recommendation fields:

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

- Banking review workbench: `http://127.0.0.1:8000/review`
- Root model list: `http://127.0.0.1:8000/`
- Model list API: `http://127.0.0.1:8000/api/models`
- API docs: `http://127.0.0.1:8000/docs`

The backend bootstraps local schema and repo-backed baselines on startup if needed. Startup does not perform network metadata refreshes; use the explicit CLI or API update paths for that work.

Read-only routes do not require credentials. Write routes are disabled unless
`LLM_BENCHMARKING_ADMIN_TOKEN` is set in the server environment or
`LLM_BENCHMARKING_TRUSTED_TAILNET_WRITES=1` is set and the client source address
is loopback or a Tailscale address. Send the admin-token fallback with local
mutation requests by using either
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

Models also carry release and age evidence in exports and API responses:
`release_date`, `release_date_precision`, `release_date_confidence`,
`release_date_source_name`, `release_date_source_url`,
`release_date_verified_at`, `model_age_days`, `model_age_basis`,
`model_age_confidence`, `model_age_source_name`, `model_age_source_url`,
`model_age_reference_date`, `huggingface_created_at`, and
`huggingface_last_modified_at`. Exact release dates from trusted sources are
kept separate from proxy age signals such as Hugging Face repository creation,
OpenRouter addition, or local discovery timestamps.

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
- Hugging Face repository creation and modification timestamps from curated model discovery
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

Banking review decisions are runtime SQLite state by default. Export a review
snapshot from `/review` or `POST /api/review/snapshots/export` before rebuilding
a DB; import it with `/review` or `POST /api/review/snapshots/import` after
bootstrap.

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
- OpenRouter model refresh requests all output modalities so non-text-capable catalog rows are not hidden by the provider default.
- `inference-sync` supports destination subsets.
- `model-card-sync` backfills Hugging Face-backed model-card metadata such as license, docs URL, repo URL, paper URL, languages, capabilities, intended use, and limitations.
- `model-card-audit` reports current model-card field coverage, extraction-quality issues, and a `commercial_production` quality gate. The gate treats missing license metadata, generic license markers, and incomplete derivative provenance as blockers; missing source URLs or suspicious extraction output as warnings; and richer model-card enrichment as backlog-only cleanup.
- `recommendation-audit` previews generated use-case recommendation proposals. `recommendation-sync` persists them so `list-models`, CSV export, and the API include proposed/effective recommendation fields.
- `/review` is the interactive banking model review workbench and can export all, filtered, or selected model rows to CSV from the browser. `banking-review export` writes the review-friendly combined CSV from the CLI. `banking-review set` and `banking-review deprecate` apply model- or family-scoped manual approval and recommendation decisions from the CLI.
- `model-license-sync` fills missing licenses using safe open-weight family propagation, a `Proprietary` fallback for missing proprietary licenses, and tracked exact/family overrides from [backend/model_license_baseline.json](backend/model_license_baseline.json).
- `list-models` writes a clean CSV bundle to `output/model-list*.csv` by default in addition to the requested stdout/file format; pass `--no-csv` when you do not want the bundle, or `--no-csv-sidecars` when you only want the main model CSV.
- `provider-origin-export` and `model-curation-export` push live curation back into the tracked baseline JSON files.

## API Surface

The core API is in [backend/main.py](backend/main.py). High-level groups:

- model list: `/` and `/api/models`
- catalog metadata: `/api/providers`, `/api/benchmarks`, `/api/use-cases`
- rankings: `/api/rankings`
- review workbench: `/review`, `/api/review/catalog`, `/api/review/decisions`, `/api/review/models`, `/api/review/snapshots/export`, and `/api/review/snapshots/import`
- admin edits for provider metadata, approvals, inference-route approvals, manual benchmark scores, and model curation
- update operations: `/api/update`, `/api/update/status/{log_id}`, `/api/update/history`, source-run detail, raw source records, and audit output
- market snapshots: `/api/market-snapshots`

POST/PATCH/PUT mutation routes require either the local admin token described in
the run instructions above, or trusted tailnet mode for loopback/Tailscale
clients. GET routes remain read-only and unauthenticated.

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
