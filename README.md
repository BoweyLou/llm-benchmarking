# LLM Benchmarking

LLM Benchmarking is a local backend-only model intelligence workspace. It stores public benchmark scores, model metadata, release-date and age evidence, size-aware catalog discovery fields, provider-origin metadata, license and provenance review fields, use-case approvals, inference-location coverage, and update history in SQLite.

The primary output is now a simple model metadata list:

```bash
python -m backend list-models
```

That command prints a JSON array. Each model item includes the serialized metadata used by the old dashboard, including scores, source details, model roles, release-date provenance, model-age evidence, model size fields, small-model candidate visibility, provider origin, license policy, provenance policy, use-case approvals, inference destinations, OpenRouter market metadata, model-card fields, and family/duplicate curation fields.
It also writes spreadsheet-friendly CSV output to `output/model-list.csv` by default, plus normalized companion CSVs for scores, source listings, use-case approvals, inference destinations, provider-origin countries, and source freshness. Score exports preserve confidence, sample-size, rank, category, methodology, publication, style-control, preliminary, and source-revision evidence. When recommendation proposals have been synced, use-case approvals include proposed and effective recommendation fields.

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
  Runs the benchmark ingestion/update pipeline, refreshes external OpenRouter/catalog-discovery/model-card/market metadata, and writes update history plus audit results. Full updates run configured model discovery; benchmark-scoped updates skip it unless `--refresh-model-discovery` is passed.
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

By default this also writes `output/model-list.csv` and companion files named `model-list-scores.csv`, `model-list-source-listings.csv`, `model-list-use-case-approvals.csv`, `model-list-inference-destinations.csv`, `model-list-provider-origin-countries.csv`, and `model-list-source-freshness.csv`. The main CSV keeps model-level columns readable and replaces nested JSON blobs with summary columns. Use `--csv-output <path>` to choose another CSV path, `--no-csv-sidecars` to suppress companion files, or `--no-csv` to suppress the CSV bundle when a script needs stdout only.

LM Arena ingestion reads the official `lmarena-ai/leaderboard-dataset` Parquet
files. Each run resolves one dataset commit SHA and uses it for all selected
subsets, so mixed snapshots cannot enter a run. `chatbot_arena` remains the
backward-compatible style-controlled Text Overall signal; raw Text, selected
Text categories, WebDev, Agent, Vision, Document, and Search have distinct
benchmark IDs and no default ranking weights. Arena listings are evidence only:
they never create or change global model availability.

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
- proposal blockers, warnings, reasons, required controls, score, confidence, policy version, and computed timestamp.

Use manual `restricted` when a model is suitable only for a defined group, for
example a cyber-specialist model that should be available only to approved cyber
team members. Store the audience or access condition in recommendation notes.

## LLM Model Tool

For interactive model review, run the FastAPI app locally and open `/review`.
The LLM Model Tool shows the model catalog with provider, provider-origin
country, use-case, general-approval, manual-recommendation, use-case approval,
family, catalog-status, model-role,
small-model, and hyperscaler-availability filters; a sortable model table; family and needs-decision
views; and a detail inspector for model approval plus per-use-case approval
notes, manual ratings, generated blockers, warnings, and required controls.
The `Rankings` view keeps benchmark comparison separate from manual review. It
can show weighted use-case rankings from `/api/rankings` or raw benchmark
leaderboards from the loaded score data. Ranking lanes stay model-role aware:
generator use cases rank generator models, retrieval embeddings rank embedding
models, retrieval reranking ranks reranker models, voice-to-text ranks
speech-to-text models, and text-to-speech ranks synthesis models.
The model table `Release` column shows the best available release indicator:
trusted source release date first, then proxy dates such as Hugging Face
repository creation, OpenRouter addition, or local catalog discovery when an
official release date is not available.
Provider filters use canonical parent providers: for example, Amazon Nova,
AWS, and Amazon Bedrock are shown under Amazon, while Azure, Microsoft Azure,
and Azure AI Foundry are shown under Microsoft. Qwen rows are shown under
Alibaba, Mistral rows are shown under Mistral AI, and ibm-granite rows are
shown under IBM.
Use `Hyperscaler availability` to show models with any hyperscaler route, a
specific route such as AWS Bedrock, Azure AI Foundry, or Google Vertex AI, or no
known hyperscaler route.
Use `Sync now` for a quick reload from the current SQLite catalog. Use
`Run updates` to start the full background update pipeline from the browser; the
workbench shows the active update step, progress count, and score totals as the
update status API advances, then reloads the catalog when the run completes.
Completed update runs also show a change summary under the review tabs,
including new models, changed model metadata, removed active catalog rows,
score changes, source record counts, and any source failures reported by the
update status payload.

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

- `models.general_approved_for_use`, `models.general_approval_notes`, and
  `models.general_approval_updated_at` store model-level approval independent
  of use-case decisions. General approval has three review states: `Approved`,
  `Not approved`, and `Unreviewed`; `Unreviewed` means no timestamped general
  approval decision has been saved yet.
- `model_use_case_approvals` stores use-case approval, manual recommendation
  status, and notes.
- `models.catalog_status` stores listing state such as `tracked`,
  `provisional`, or `deprecated`.
- `model_use_case_recommendation_proposals` remains generated policy output and
  can be regenerated without overwriting manual decisions.

Use-case recommendations are reviewed through the active use case. Switch to
`Use-case review`, choose a use case in the left filter or right inspector, then
use the model table for reviewer-saved `Manual` ratings and separate `Use-case`
approval status. `Pending` means no explicit use-case approval decision has been
saved yet. Generated banking-profile proposals stay in the per-use-case
inspector controls and the use-case approval export rather than being summarized
as model-level recommendation columns.

General model approval is reviewed separately in the top panel of the right
inspector. Use `Approve model` or `Reject model` for model-level decisions, or
set the model back to `Unreviewed` from the inspector when it should return to
the untriaged queue.
Use `Approve use case` or `Not approved use case` only for the active use-case
approval.

Use `Country` to filter by provider-origin country across providers. When a
provider has multiple origin countries, the model appears under each listed
country.

Select a model to review it in the right inspector. Use the inspector tabs to
choose a use case, read blockers/warnings/required controls, review timestamp
activity, or edit notes and manual decisions. Change `Manual rating` and
use-case `Approval` in `Notes`, then save. For many models, filter first, use
`Select all filtered` when needed, and apply the bulk recommendation or approval
action to the exact selected model IDs.
In `Rankings`, select a use-case ranking or a benchmark leaderboard, then select
a ranked row to inspect score, coverage, missing evidence, and raw benchmark
details. Ranking evidence is read-only; use the review tabs for approval and
recommendation decisions.
Use `Restricted` for limited-audience access decisions and record who may use
the model in the recommendation notes.
Use `Manual recommendation` to filter only reviewer-saved ratings, including rows
where the manual rating has been cleared to `Unrated`.
Choose a specific `Use case` and set `Use-case approval = Pending` to find
models that still need an explicit approval decision for that use case.
When `Use case` is left blank, `Manual recommendation = Unrated` finds models
with no saved manual recommendation in any use case. Combine it with
`General approval = Approved` for first-cut triage of approved models that still
need a human rating.

The workbench can export and import a JSON review snapshot. Use that snapshot
when rebuilding a database so manual listings, deprecation markers, and
general model approvals plus use-case approval/recommendation rows can be
restored.

The model table can also export CSV directly from the browser. Choose filtered,
selected, or all rows in the table toolbar, then use `Export CSV`. The CSV
contains the model listing fields, general model approval, active use-case approval,
manual/proposed/effective recommendation, proposal blockers, warnings, and
required controls. It includes `best_release_date`,
`best_release_date_basis`, and `best_release_date_confidence` alongside the raw
official release-date fields. It also includes derived model type and selection
evidence fields: `model_type_primary`, `model_type_tags`,
`evidence_context_use_case_id`, `strongest_signal_kind`,
`strongest_signal_label`, `strongest_signal_value`,
`strongest_signal_source_url`, `ranking_rank`, `ranking_score`,
`ranking_coverage`, `cost_signal`, `speed_signal`, `hyperscaler_signal`, and
`inference_location_signal`. Filter `General approval` to `Approved` before
exporting when you need the model-level approved list; use-case approval remains
a separate field in the same CSV.

Bulk review actions can target the current visible page with the table checkbox
or the full filtered result set with `Select all filtered`. Selecting all
filtered rows replaces the current selection with the exact filtered model IDs
before a bulk action is saved.
Use `Reject model` to clear model-level approval in bulk. Use `Not approved use
case` to clear approval for the active use case. Use `Clear rating` only when you
want to reset the manual recommendation rating to `unrated` while leaving
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

Manual curation commands write SQLite review state for the configured
`DATABASE_URL`; in a local shell this defaults to the repo-local database, while
the Proxmox service uses `/var/lib/llm-benchmarking/db.sqlite`. `add-model`
defaults to `generator`, so include `--model-role` for embedding, reranker,
speech-to-text, or text-to-speech rows:

```bash
python -m backend banking-review add-model --name "Vendor Model" --provider "Vendor"
python -m backend banking-review add-model --name "NVIDIA Embedder v2" --provider "NVIDIA" --model-role embedding
python -m backend banking-review set --model-id vendor-model --use-case customer_support --approval approved --recommendation recommended --notes "Approved for pilot."
python -m backend banking-review set --model-id chatgpt-5-5-cyber --use-case safety_compliance --recommendation restricted --recommendation-notes "Approved cyber team only."
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

- LLM Model Tool: `http://127.0.0.1:8000/review`
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
rankings. Speech-recognition and transcription models use `speech_to_text`, so
voice-to-text models can be filtered and ranked separately from general text
generators. Speech-synthesis models use `text_to_speech`, including rows
inferred from OpenRouter `text->speech` or `speech-output` capabilities,
Hugging Face `text-to-speech` pipeline tags, and trusted provider catalog
metadata.

The review catalog derives `model_type_primary` and `model_type_tags` for
export and triage. Tags include roles such as `generator`, `embedding`, and
`reranker`, deployment or ownership signals such as `open_weights`,
`proprietary`, `local_sml`, `hyperscaler_available`, and `australia_route`, and
the `frontier` tag for generator models that are not marked as small-model
candidates.

Review catalog schema version 2 keeps response-build time in `generated_at`
and exposes two separate operational timestamps. `database_updated_at` is the
newest UTC modification time of the configured SQLite database file or its WAL,
so it covers database writes outside the update runner. `last_sync_at`,
`last_sync_status`, and `last_sync_log_id` identify the newest `update_log`
run. The workbench displays both values as full local date-and-time labels and
uses explicit `Never` or `Unavailable` states when no trustworthy value exists.

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
- Artificial Analysis Text to Speech
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
- MTEB retrieval/reranking and RTEB Finance
- Open ASR Leaderboard
- RAGTruth
- SWE-bench Verified, Lite, Full, Multilingual, and Multimodal
- tau-bench
- Terminal-Bench
- FaithJudge
- Vectara Hallucination

Metadata and catalog enrichments:

- Curated Hugging Face model discovery for official/provider-owned repos,
  including selected text-to-speech repos such as Kokoro and Chatterbox
- OpenRouter models and market/ranking signals
  Recent OpenRouter models from the last 60 days are imported as provisional rows when no exact OpenRouter ID or canonical slug is already represented.
- Configured provider catalog rows for OpenAI, Google, ElevenLabs, Cartesia,
  Deepgram, Amazon Polly, Azure Speech, PlayHT, Resemble, and selected
  open-weight text-to-speech models, plus official frontier rows such as
  OpenAI GPT-5.6 Sol, Terra, and Luna and restricted-access frontier/cyber
  rows such as Claude Mythos 5 and GPT-5.5-Cyber when official provider
  documentation exists.
- Hugging Face repository creation and modification timestamps from curated model discovery
- Hugging Face model-card metadata
- Hyperscaler inference catalogs for AWS Bedrock, Azure AI Foundry, and Google Vertex AI

## Governance Model

The approval model is more than a global allow-list:

- general model approval is stored separately from use-case approval
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
python -m backend model-discovery-sync --source configured
python -m backend model-discovery-sync --source huggingface --family nvidia-embedding
python -m backend model-discovery-sync --source catalog --family ibm-watsonx-retrieval
python -m backend model-discovery-sync --source provider-api --family openai
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

- Full `update` runs configured model discovery before model-card refresh. `update --benchmarks ...` skips that discovery phase unless `--refresh-model-discovery` is passed.
- `model-discovery-sync` runs only the curated metadata discovery lane. `--source configured` runs static provider catalog rows, provider-owned Hugging Face discovery, and authenticated provider API catalogs when their keys are present; use `--source huggingface`, `--source catalog`, or `--source provider-api` to narrow the run. Provider API discovery currently supports OpenAI (`OPENAI_API_KEY`), Anthropic (`ANTHROPIC_API_KEY`), Google Gemini (`GEMINI_API_KEY` or `GOOGLE_API_KEY`), Mistral (`MISTRAL_API_KEY`), Cohere (`COHERE_API_KEY`), and xAI (`XAI_API_KEY`). Missing provider keys are recorded as skipped source runs rather than hard failures. Dynamically discovered rows are provisional unless the provider marks them deprecated; matching curated tracked rows remain tracked. The repo-backed baseline covers small generator families such as Google Gemma, Microsoft Phi, Meta Llama 3.2 small models, Qwen small models, Mistral/Ministral small models, and IBM Granite generators, plus NVIDIA retrieval, IBM watsonx Slate, and IBM Granite retrieval entries. It intentionally excludes community quantizations/fine-tunes unless a trusted mirror is configured.
- OpenRouter model refresh requests all output modalities so non-text-capable catalog rows are not hidden by the provider default.
- `inference-sync` supports destination subsets.
- `model-card-sync` backfills Hugging Face-backed model-card metadata such as license, docs URL, repo URL, paper URL, languages, capabilities, intended use, and limitations.
- `model-card-audit` reports current model-card field coverage, extraction-quality issues, and a `commercial_production` quality gate. The gate treats missing license metadata, generic license markers, and incomplete derivative provenance as blockers; missing source URLs or suspicious extraction output as warnings; and richer model-card enrichment as backlog-only cleanup.
- `recommendation-audit` previews generated use-case recommendation proposals. `recommendation-sync` persists them so `list-models`, CSV export, and the API include proposed/effective recommendation fields.
- `/review` is the interactive LLM Model Tool and can export all, filtered, or selected model rows to CSV from the browser. It can also start `/api/update` and show live progress from `/api/update/status/{log_id}`. `banking-review export` writes the review-friendly combined CSV from the CLI. `banking-review set` and `banking-review deprecate` apply model- or family-scoped manual approval and recommendation decisions from the CLI.
- `model-license-sync` fills missing licenses using safe open-weight family propagation, a `Proprietary` fallback for missing proprietary licenses, and tracked exact/family overrides from [backend/model_license_baseline.json](backend/model_license_baseline.json).
- `list-models` writes a clean CSV bundle to `output/model-list*.csv` by default in addition to the requested stdout/file format; pass `--no-csv` when you do not want the bundle, or `--no-csv-sidecars` when you only want the main model CSV.
- `provider-origin-export` and `model-curation-export` push live curation back into the tracked baseline JSON files.

## API Surface

The core API is in [backend/main.py](backend/main.py). High-level groups:

- model list: `/` and `/api/models`
- catalog metadata: `/api/providers`, `/api/benchmarks`, `/api/use-cases`
- rankings: `/api/rankings`
- LLM Model Tool: `/review`, `/api/review/catalog`, `/api/review/decisions`, `/api/review/model-approvals`, `/api/review/models`, `/api/review/snapshots/export`, and `/api/review/snapshots/import`
- admin edits for provider metadata, approvals, inference-route approvals, manual benchmark scores, and model curation
- update operations: `/api/update`, `/api/update/status/{log_id}`, `/api/update/history`, source-run detail, raw source records, audit output, and per-run catalog change summaries
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
