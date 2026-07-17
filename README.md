# LLM Benchmarking

LLM Benchmarking is a local backend-only model intelligence workspace. It stores public benchmark scores, model metadata, release-date and age evidence, size-aware catalog discovery fields, provider-origin metadata, license and provenance review fields, use-case approvals, inference-location coverage, and update history in SQLite.

The primary output is now a simple model metadata list:

```bash
python -m backend list-models
```

That command prints a JSON array. Each model item includes scores, source details, model roles, release-date provenance, model-age evidence, model size fields, provider origin, license and provenance policy, inference destinations with provider-specific pricing offers, OpenRouter market metadata, model-card fields, and family/duplicate curation fields.
It also writes spreadsheet-friendly CSV output to `output/model-list.csv` by default, plus normalized companion CSVs for scores, source listings, use-case approvals, inference destinations, pricing offers, provider-origin countries, and source freshness. The pricing sidecar contains one row per price component and retains its route, tier, region, unit, official source URL, verification time, and staleness status.

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
  Creates the schema, repairs local runtime state, seeds reference data, and applies repo-backed provider-origin, model-curation, and model-license baselines. On existing model rows, the model seed upsert owns only the baseline name, provider identity, type, roles, release date, context window, and active flag; it does not replace review decisions, usage policy, catalog status, enrichment, pricing, capabilities, family/discovery metadata, or other non-seed columns with seed defaults. It does not call external metadata services.
- `python -m backend update`
  Runs the benchmark ingestion/update pipeline, refreshes external OpenRouter/catalog-discovery/provider-pricing/model-card/market metadata, and writes update history plus audit results. Full updates run configured model discovery; benchmark-scoped updates skip discovery unless `--refresh-model-discovery` is passed, but still refresh provider pricing.
- `python -m backend list-models`
  Prints or exports the complete active model metadata list and writes a default clean CSV bundle.
- `python -m backend review-export`
  Writes a decision-friendly, AU-first model guide ZIP from the current read-only review catalog.

If you want the older one-shot bootstrap-and-ingest flow, it still exists:

```bash
python -m backend.bootstrap_db
```

## Output

Print a pretty JSON list to stdout:

```bash
python -m backend list-models
```

By default this also writes `output/model-list.csv` and companion files named `model-list-scores.csv`, `model-list-source-listings.csv`, `model-list-use-case-approvals.csv`, `model-list-inference-destinations.csv`, `model-list-pricing-offers.csv`, `model-list-provider-origin-countries.csv`, and `model-list-source-freshness.csv`. The main CSV keeps model-level columns readable and replaces nested JSON blobs with summary columns. Use `--csv-output <path>` to choose another CSV path, `--no-csv-sidecars` to suppress companion files, or `--no-csv` to suppress the CSV bundle when a script needs stdout only.

Benchmark comparisons follow the same server-owned contract in every output.
JSON and JSONL retain each score's nested `display` and `comparison` objects;
the raw CSV retains them inside its score JSON. The clean model CSV adds concise
counts for comparable, limited, leading, and missing relevant results, while
the normalized scores sidecar flattens strict and broad rank, cohort,
percentile, distributions, database coverage, evidence depth, status, and
warnings. When the compatibility `scores` view and `score_configurations`
contain the same latest configured observation, review cards, model-level
counts, and normalized score rows include it once; genuinely different
configurations or evaluation signatures remain separate. Banking exports
inherit the clean model-level summary fields.

The 92 current benchmark definitions are code-owned. Startup upserts that
authoritative set and deactivates database definitions that have been retired
from code without deleting their historical score rows. Presentation policy
coverage is contract-tested against the active code-owned definitions.

LM Arena ingestion reads the official `lmarena-ai/leaderboard-dataset` Parquet
files. Each run resolves one dataset commit SHA and uses it for all selected
subsets, so mixed snapshots cannot enter a run. `chatbot_arena` remains the
backward-compatible style-controlled Text Overall signal; raw Text, selected
Text categories, WebDev, Agent, Vision, Document, and Search have distinct
benchmark IDs and no default ranking weights. Arena listings are evidence only:
they never create or change global model availability.

MTEB ingestion probes every listed model and every eligible retrieval and
reranking task file without a per-model or global task cap. Confirmed upstream
`404`/`410` inventory entries are reported as stale rather than treated as
scores; every transient, parse, or other unresolved failure still fails the run.
The adapter selects a coherent accessible revision deterministically, carries
revision, split, and subset metadata into evaluation signatures, and fetches
through bounded batches with retry and backoff. If the RTEB dataset viewer is
temporarily unavailable, a bounded fallback reads all seven finance tasks from
one revision-pinned official Parquet snapshot. A partial run fails closed before
replacing score evidence, so previously imported MTEB scores remain available
for the next clean refresh.

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

### Model decision and inference guide

For a compact export intended for review and procurement conversations, run:

```bash
python -m backend review-export
```

The default output is `output/llm-model-guide-<UTC timestamp>.zip`. Use
`--output <path>` to choose the file and repeat `--model-id`, or pass several
IDs after one flag, to limit the export to exact source records:

```bash
python -m backend review-export \
  --model-id model-id-one model-id-two \
  --output output/shortlist-model-guide.zip
```

The ZIP contains three files:

- `models.csv` has one readable row per server-owned `review_entity_id` group.
  It preserves the stable group ID, source-record count and IDs, general
  approval, general recommendation, usage classification, read-only suggested-use evidence, and an
  AU-first inference summary. `mixed` appears only when the grouped source
  records disagree on the corresponding model-level decision.
- `inference-costs.csv` is the normalized evidence table: one row per source
  record, route, location, offer, and price component. It retains native
  currency, amount, billing unit and quantity, modality, charge type, service
  tier, constraints, conditions, source URL and label, verification time, and
  stale state.
- `README.txt` is a portable legend for the decision and pricing fields and
  their caveats.

Suggested use cases come only from the current metric-derived
`suggested_use_cases` contract. They are positive fit evidence, may include a
candidate that still requires restrictions or controls, and are never a human
approval or general recommendation. The guide does not roll legacy
per-use-case approval rows into this list. Fit, confidence, policy version, and
computed time are retained where the review catalog provides them.

Inference locations sort as Australia, other named countries alphabetically,
Global, provider-managed or provider-routed routes, then unknown location.
Published region identifiers are kept as identifiers; the export does not
invent city names. A price is matched to a listed location only when its region
matches. Non-Australian or regionless price evidence is retained honestly as
price-only evidence and never attached to an Australian route. A price-only
Australian row likewise cannot become a confirmed Australian inference option
or model-summary price. Availability-only and no-known-route rows remain
visible.

The `availability_evidence_kind` field and the bracketed labels in the readable
summary distinguish synced account/project catalog evidence,
`curated_fallback` possibilities, `pricing_only` observations, and
provider-managed or provider-routed paths. A curated fallback is not confirmed
model availability in a named account or region; verify account entitlement,
quota, residency controls, and the cited source before deployment.

Price evidence keeps lifecycle status (`current`, `free`, `unavailable`, or
`custom`) separate from the `pricing_is_stale` freshness flag. No currency
conversion or global cheapest-price calculation is performed. The model-level
Australian price summary includes only fresh, matched, standard-tier text
input/output pairs in their native unit, reports a genuinely free pair as free,
and explicitly distinguishes a confirmed synced Australian route without a
current price from a possible, unconfirmed curated fallback. Use
`inference-costs.csv`, not the summary, for conditional, multimodal, batch,
cached, provisioned, or other non-comparable charges.

The matching read-only API accepts an omitted or `null` `model_ids` field for
the whole catalog, or a non-empty exact source-record list. Empty and unknown
ID scopes are rejected instead of silently exporting all models. It does not
require the admin write token:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/review/exports/model-guide \
  -H 'Content-Type: application/json' \
  --data '{"model_ids":["model-id-one","model-id-two"]}' \
  --output llm-model-guide.zip
```

## Recommendation Proposals

Human review now records one general approval and one general recommendation per model. The recommendation proposal engine remains a separate, auditable use-case fit layer that can be regenerated from the current catalog:

```bash
python -m backend recommendation-audit
python -m backend recommendation-sync
python -m backend list-models --output output/model-metadata.json
```

`recommendation-audit` is read-only and prints a summary by default; pass `--json` for the full proposal payload. `recommendation-sync` stores proposal rows in SQLite under `model_use_case_recommendation_proposals`. Both commands support `--use-case <id>` to limit the run.

The first profile is `australian_bank`. It applies conservative gates for regulated banking use: commercial license and unverified derivative provenance blockers, tracked-catalog requirements for governed use cases, model-card requirements, bank-approved inference-route requirements, Australian-route requirements for customer or personal-information use cases, and benchmark score/confidence thresholds. The profile was shaped around official guidance from [APRA CPS 230](https://www.apra.gov.au/standards/cps-230), [APRA CPS 234 cyber security guidance](https://www.apra.gov.au/cyber-security), [OAIC commercial AI privacy guidance](https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/guidance-on-privacy-and-the-use-of-commercially-available-ai-products), and [ASIC AI governance observations](https://www.asic.gov.au/about-asic/news-centre/find-a-media-release/2024-releases/24-238mr-asic-warns-governance-gap-could-emerge-in-first-report-on-ai-adoption-by-licensees/).

Legacy use-case records can still carry the following compatibility fields, but
the current review UI does not expose them as human decisions:

- `recommendation_status`: manual human rating.
- `auto_recommendation_status`: existing automatic hard blockers from license/provenance overlays.
- `proposed_recommendation_status`: generated profile proposal.
- proposal blockers, warnings, reasons, required controls, score, confidence, policy version, and computed timestamp.

Use manual `restricted` when a model is suitable only for a defined group, for
example a cyber-specialist model that should be available only to approved cyber
team members. Store the audience or access condition in recommendation notes.

## LLM Model Tool

For interactive model review, run the FastAPI app locally and open `/review`.
The LLM Model Tool presents a focused queue with provider, general approval,
recommendation, usage-classification, and needs-decision filters. Selecting a
model puts its benchmark position, independent recommendation and governance
decisions, read-only suggested use cases, and reference facts in one detail view. The section is labelled
**Benchmark position — How this model compares with similar scored models in
this database.** It leads with four Key benchmarks selected by active use-case
relevance or role defaults, then tier and provenance, rather than by the most
flattering percentile. An expandable complete list groups all benchmark results
by category. Missing relevant evidence follows the active use case's positively
weighted and required benchmarks, falling back to role defaults only when that
context declares none.

Each benchmark card shows the formatted value and direction, its position among
strictly comparable models, broader same-role database context when available,
distribution and coverage context, evidence depth, provenance, and warnings.
Strict cohorts require a compatible role, evaluation configuration, and the
benchmark's available evaluation signature; broad cohorts relax the latter
constraints and explicitly warn when configurations or task sets are mixed.
Ranks, percentiles, and position labels describe only evidence currently
imported into this database. They are not universal quality ratings or
production-approval decisions, and a Verified source is not a claim of
independent reproduction. Competition ranks and ties use the stored normalized
numeric values before presentation rounding or unit conversion, so two values
that merely render the same are not treated as tied.

The queue combines duplicate source records only when normalized name,
non-empty canonical model ID, and model role all agree; ambiguous same-name
records remain separate. Combined rows merge complementary benchmark evidence.
When duplicate observations compete for the same canonical evaluation, the
server chooses by provenance, recency, evidence depth, and stable identity—not
by whichever score is numerically most favorable. Exact compatibility
duplicates of the latest configured observation are suppressed in review and
flat exports, while distinct configuration or evaluation-signature evidence is
preserved.
Release-date ordering uses the trusted source release date first, then proxy
dates such as Hugging Face repository creation, OpenRouter addition, or local
catalog discovery when an official release date is not available.
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
  of use cases. General approval has three review states: `Approved`,
  `Not approved`, and `Unreviewed`; `Unreviewed` means no timestamped general
  approval decision has been saved yet.
- `models.general_recommendation_status`,
  `models.general_recommendation_notes`, and
  `models.general_recommendation_updated_at` store one general recommendation:
  `Recommended`, `Acceptable`, `Legacy Supported`, `Not recommended`, or
  `Not Assessed`. `Acceptable` means okay for normal use but not the preferred
  option. `Legacy Supported` means a model remains usable if necessary but
  should be replaced by a recommended option. The stored/API value for
  `Not Assessed` remains `unrated` for compatibility and means no recommendation
  decision has been saved. Upgrades and legacy API inputs normalize general
  `Discouraged` to `Not recommended`.
- `models.usage_classification`, `models.usage_classification_notes`, and
  `models.usage_classification_updated_at` store the independent governance
  classification: `Standard`, `Restricted`, `Prohibited`, or `Unclassified`.
  `Restricted` and `Prohibited` describe permission or controls, not model
  preference or suitability.
- `models.catalog_status` stores listing state such as `tracked`,
  `provisional`, or `deprecated`.
- `model_use_case_recommendation_proposals` remains generated policy output and
  is transformed into read-only `suggested_use_cases` entries with fit score,
  confidence, reasons, warnings, and required controls. Suggestions never write
  approval or recommendation state.
- `model_use_case_approvals` is retained as a legacy audit/backward-
  compatibility table. The current review UI does not read or write it as a
  decision surface.

Select a model, review its Key benchmark position, expandable evidence, and
metric-derived suggested use cases, then save one general approval and one
general recommendation plus one usage classification. Use `Needs a decision`
to find models whose approval is still `Unreviewed`, recommendation is still
`Not Assessed`, or usage classification is still `Unclassified`. Recommendation and
usage classification do not rewrite one another; record any access boundary in
the shared decision rationale.

For bulk review, choose `Select`, optionally narrow the queue with filters, and
use `Select all filtered`. The fixed action bar shows both the number of visible
model groups and the exact underlying source-record count. The confirmation
dialog changes only the selected general approval, recommendation, and/or usage
classification fields; fields set to `Leave unchanged` and all suggested-use-case evidence are left
untouched. A decision on a combined row writes to every listed source record.
The queue renders results in progressive 200-row batches for responsiveness;
`Select all filtered` still targets the complete filtered result, including
rows not yet rendered.

The header `Export` control downloads the same model-guide ZIP without changing
review state. Choose `All models`, `Current filtered list`, or `Selected
models`. Filtered export includes every underlying source ID in every matching
review group, including groups beyond the current 200-row render batch.
Selected export includes every source ID in the selected groups and stays
disabled with clear guidance when nothing is selected. Export is read-only, so
it does not use the admin token.

The workbench can export and import a JSON review snapshot. Use that snapshot
when rebuilding a database so manual listings, deprecation markers, and
general model decisions can be restored. Version 3 snapshots also include model
usage-policy fields, version 2 snapshots include the general recommendation
fields, and version 1 snapshots remain importable. Benchmark comparisons are
generated from current score evidence and are not stored as review decisions.

Clean CSV exports include general approval, general recommendation,
`suggested_use_case_count` / `suggested_use_case_ids`, and model-level benchmark
comparison counts. The normalized CSV bundle adds `suggested-use-cases.csv`
with the metric fit evidence and expands `scores.csv` with strict and broad
comparison fields. The legacy `use-case-approvals.csv` sidecar remains
available for audit compatibility.

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

The backend bootstraps local schema and repo-backed baselines on startup if
needed. Model seed rows refresh only their eight seed-owned baseline fields;
the seed upsert leaves all other existing model columns untouched. Later
repo-backed baselines and migrations retain their documented authority.
Benchmark definitions remain code-owned and authoritative during their seed
upsert. Startup does not perform network metadata refreshes; use the explicit
CLI or API update paths for that work.

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

Review catalog schema version 4 keeps response-build time in `generated_at`
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

The current human review contract is intentionally model-level:

- general approval, general recommendation, and usage classification are separate fields on each model
- use-case recommendation proposals are regenerated metric evidence, not human authorization
- legacy per-use-case approval and recommendation rows remain available only for compatibility and audit
- inference-route approval can be stored per `model x use case x provider x location`
- bulk model-level decisions write through to exact model IDs rather than using hidden inheritance
- new models discovered in updates can be surfaced for review
- provider-origin and model-curation state can be exported back to repo-backed baselines

## Data Durability

SQLite is the runtime store, but important manual metadata is also kept in tracked repo baselines so it does not get lost on rebuilds:

- provider origin baseline: [backend/provider_origin_baseline.json](backend/provider_origin_baseline.json)
- model discovery baseline: [backend/model_discovery_baseline.json](backend/model_discovery_baseline.json)
- model curation baseline: [backend/model_curation_baseline.json](backend/model_curation_baseline.json)
- model license baseline: [backend/model_license_baseline.json](backend/model_license_baseline.json)

Those baselines are applied during bootstrap and can be re-exported from the
live DB. Repeated bootstrap does not replace existing model decisions, policy,
catalog lifecycle, provenance, prices, capabilities, family identity, or
discovery metadata with seed defaults. Network-backed metadata refreshes are
intentionally kept out of bootstrap so API startup stays local and predictable.

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
python -m backend pricing-sync --providers openai openrouter aws-bedrock
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
- `pricing-sync` refreshes official direct-provider, router, and cloud prices. Supported provider keys are `openai`, `anthropic`, `google`, `mistral`, `cohere`, `xai`, `openrouter`, `aws-bedrock`, `azure-ai-foundry`, and `google-vertex-ai`. Set `GOOGLE_CLOUD_BILLING_API_KEY` to ingest Google Vertex AI prices from the Cloud Billing Catalog API; `GCP_BILLING_API_KEY` is accepted as a compatibility alias. `GOOGLE_CLOUD_ACCESS_TOKEN` (or `GCP_ACCESS_TOKEN`) remains optional and is used separately for project- and region-scoped Vertex publisher-model discovery. Each source refresh is atomic: zero results, a missing configured canary, or component coverage below 70% records a failed source run and preserves the last-known-good offers. Prices remain auditable indefinitely, but offers older than 30 days are excluded from the review preview and model pricing summary.
- `model-card-sync` backfills Hugging Face-backed model-card metadata such as license, docs URL, repo URL, paper URL, languages, capabilities, intended use, and limitations.
- `model-card-audit` reports current model-card field coverage, extraction-quality issues, and a `commercial_production` quality gate. The gate treats missing license metadata, generic license markers, and incomplete derivative provenance as blockers; missing source URLs or suspicious extraction output as warnings; and richer model-card enrichment as backlog-only cleanup.
- `recommendation-audit` previews generated use-case recommendation proposals. `recommendation-sync` persists them so `list-models`, CSV export, and the API include proposed/effective recommendation fields.
- `/review` is the interactive LLM Model Tool for single and all-filtered bulk model-level decisions. A model can also carry configuration-level usage controls: a maximum permitted reasoning effort (`none` through `max`) and restricted `pro` or `ultra` product modes. For example, GPT-5.6 Sol can be approved and recommended while being allowed only through `high` with `ultra` restricted. It can also start `/api/update` and show live progress from `/api/update/status/{log_id}`. `banking-review export` writes the review-friendly combined CSV from the CLI; legacy `banking-review set` and `banking-review deprecate` commands remain available for compatibility workflows.
- `model-license-sync` fills missing licenses using safe open-weight family propagation, a `Proprietary` fallback for missing proprietary licenses, and tracked exact/family overrides from [backend/model_license_baseline.json](backend/model_license_baseline.json).
- `list-models` writes a clean CSV bundle to `output/model-list*.csv` by default in addition to the requested stdout/file format; pass `--no-csv` when you do not want the bundle, or `--no-csv-sidecars` when you only want the main model CSV.
- `provider-origin-export` and `model-curation-export` push live curation back into the tracked baseline JSON files.

## API Surface

The core API is in [backend/main.py](backend/main.py). High-level groups:

Benchmark meaning is defined by the backend registry and returned by
`/api/benchmarks` as presentation metadata plus aggregate distributions. Every
non-null score exposed by the root catalog, `/api/models`,
`/api/review/catalog`, and ranking breakdowns carries a formatted `display`
object and a compact `comparison` object with strict and broad cohorts,
coverage, evidence depth, warnings, and an `as_of` timestamp. Comparison status
is one of `comparable`, `limited`, `unavailable`, or `invalid`. Review catalog
schema version 4 adds this data without changing stored review decisions or the
version 3 review-snapshot schema. Benchmark position remains contextual
evidence and is not folded into the weighted use-case ranking score.

- model list: `/` and `/api/models`
- catalog metadata: `/api/providers`, `/api/benchmarks`, `/api/use-cases`
- rankings: `/api/rankings`
- LLM Model Tool: `/review`, `/api/review/catalog`, `/api/review/model-decisions` (general approval, recommendation, reasoning-effort ceiling, and restricted product modes), the compatibility routes `/api/review/model-approvals` and `/api/review/decisions`, `/api/review/models`, `/api/review/snapshots/export`, and `/api/review/snapshots/import`
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

`aws-bedrock` can run in pricing-only mode without credentials. `azure-ai-foundry` has a public-pricing-only fallback without credentials. With `GOOGLE_CLOUD_BILLING_API_KEY`, `google-vertex-ai` combines Cloud Billing SKU prices with its published endpoint footprint without requiring an OAuth access token. Adding `GOOGLE_CLOUD_ACCESS_TOKEN` enables the live publisher-model catalog; with neither credential, Vertex retains its published-endpoints-only fallback.
