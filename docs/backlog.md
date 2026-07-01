# Backlog

Source of truth: repo-local backlog mirror for LLM Benchmarking maintenance.
Repo mirror purpose: local kit selectors, task-packet handoff, and review follow-up.
Stale mirror policy: refresh from current review findings before implementation when
the row is older than 14 days or the backend/API shape has changed.

## Open

## Done

- [x] LBM-016: P2 Normalize CSV exports for spreadsheet review
  - Source: User CSV cleanup review 2026-07-01.
  - Problem: the default CSV included nested JSON cells for scores, approvals, inference destinations, and related model metadata, which made spreadsheet review unclear.
  - Scope: model-list CSV rendering, CLI export behavior, normalized companion CSVs, raw CSV fallback, docs, and tests.
  - Acceptance: the default CSV is model-level and human-readable; repeated/nested structures are exported as named companion CSV files; legacy JSON-in-cell CSV remains available explicitly.
  - Validation: `python -m unittest backend.test_catalog_export`; `python -m backend list-models --output /tmp/llm-benchmarking-models.json --csv-output /tmp/llm-benchmarking-model-list.csv`.
  - Completed: 2026-07-01. The export now writes a clean model-list CSV plus scores, use-case approvals, inference destinations, provider-origin countries, and source-freshness companion files.

- [x] LBM-015: P1 Add Australian-bank recommendation proposals
  - Source: Product clarification 2026-07-01.
  - Problem: manual `recommended` / `not_recommended` ratings need a generated, auditable proposal layer that reflects regulated Australian-bank deployment considerations.
  - Scope: recommendation proposal schema, policy engine, CLI audit/sync commands, serialized model-list/API fields, docs, and tests.
  - Acceptance: generated proposals are stored separately from manual ratings; list/API payloads expose proposed and effective statuses; the default profile covers license, provenance, catalog, model-card, approved-route, Australian-route, privacy, operational-risk, and benchmark-evidence gates.
  - Validation: recommendation engine unit tests; schema migration tests; `python -m backend recommendation-sync`; `python -m backend list-models --output /tmp/llm-benchmarking-models.json`.
  - Completed: 2026-07-01. The `australian_bank` profile now generates and stores auditable per-model/use-case recommendation proposals and exposes them in model-list exports.

- [x] LBM-005: P2 Turn model-card audit gaps into a governed quality gate
  - Source: Codex repo review 2026-07-01.
  - Problem: current audit reports hundreds of models with missing metadata/license fields and derivative models without training-data summaries.
  - Scope: `backend/model_card_audit.py`, `backend/model_licenses.py`, `backend/model_provenance.py`, review/reporting docs.
  - Acceptance: define thresholds for commercial/production use cases; audit output distinguishes blocker, warning, and backlog-only gaps; remediation rows are easy to generate from the audit.
  - Validation: `python -m backend model-card-audit --json`; tests for threshold classification; `make docs-check`.
  - Completed: 2026-07-01. The audit now emits a `commercial_production` quality gate with blocker, warning, and backlog-only remediation rows, and docs define the threshold meanings.

- [x] LBM-006: P2 Refactor update-engine responsibilities into smaller modules
  - Source: Codex repo review 2026-07-01.
  - Problem: `backend/update_engine.py` owns orchestration, ranking reads, OpenRouter enrichment, model-card refresh, license refresh, curation write paths, and serialization in one very large module.
  - Scope: `backend/update_engine.py` plus new focused backend modules.
  - Acceptance: extract at least orchestration, OpenRouter metadata, model-card refresh, and ranking/read serialization into bounded modules without changing API output.
  - Validation: characterization tests before moves; targeted backend unittest suite; `python -m backend list-models --output /tmp/llm-benchmarking-models.json`.
  - Completed: 2026-07-01. Update orchestration, OpenRouter page parsing, Hugging Face model-card extraction, and ranking response construction now live in focused helper modules while `update_engine.py` keeps the public API surface.

- [x] LBM-007: P2 Replace duplicated ad hoc schema creation with migration-owned schema changes
  - Source: Codex repo review 2026-07-01.
  - Problem: SQLAlchemy table definitions and raw `CREATE TABLE` / `ALTER TABLE` SQL must be manually kept in sync.
  - Scope: `backend/database.py`, schema docs, bootstrap flow.
  - Acceptance: schema evolution has one authoritative path, either through a lightweight migration table or a documented migration tool; bootstrap remains able to initialize a fresh SQLite database.
  - Validation: fresh temp-database bootstrap; upgrade from current `data/db.sqlite` copy; targeted backend unittest suite.
  - Completed: 2026-07-01. SQLite bootstrap now records idempotent schema repairs in `schema_migrations`, and docs direct future schema changes through `SCHEMA_MIGRATIONS`.

- [x] LBM-009: P2 Fill repo goal and area contracts for backend, schemas, scripts, and prompt adapters
  - Source: Codex repo review 2026-07-01.
  - Problem: `make goal-check` reports placeholder repo goal text and 153 unknown changed paths because `.agent-workflows/area-contracts.json` only covers `docs/` and `.agent-workflows/`.
  - Scope: `.agent-workflows/area-contracts.json`, `docs/working-rhythm.md` if needed.
  - Acceptance: area contracts cover backend source/tests, scripts, schemas, `.codex/prompts`, `.doc-contract-kit`, GitHub workflow files, and root project metadata; repo goal is specific to LLM Benchmarking.
  - Validation: `make goal-check` reports no unknown paths for the current baseline or documents intentional exceptions.
  - Completed: 2026-07-01. The repo goal now names the LLM benchmarking workspace, and area contracts cover all 185 tracked baseline files with zero unknown paths in a tracked-file goal-check audit.

- [x] LBM-012: P2 Print captured inference-sync smoke output on failure
  - Source: Codex update-script test 2026-07-01.
  - Problem: `scripts/test_inference_sync_smoke.sh` redirects CLI output to a temp JSON file, but `set -e` exits before printing the captured payload when the CLI returns nonzero.
  - Scope: `scripts/test_inference_sync_smoke.sh`.
  - Acceptance: when the inference-sync CLI fails, the smoke script prints the captured JSON or stderr/stdout diagnostic plus the exit code before exiting nonzero; successful runs keep the current concise JSON report.
  - Validation: a failing destination run such as `PYTHON=python ./scripts/test_inference_sync_smoke.sh azure-ai-foundry` prints the destination failure reason; the AWS/Google subset still exits 0 and prints valid JSON.
  - Completed: 2026-07-01. The smoke script now captures stdout/stderr around the CLI, prints diagnostics with the exit code on command failure, and prints the sync JSON payload when validation fails.

- [x] LBM-014: P2 Treat Azure pricing 429 as a retryable smoke-test skip
  - Source: Codex update-script test 2026-07-01.
  - Problem: Azure AI Foundry public pricing returned HTTP 429 during `inference-sync`, causing the all-destination smoke script to fail even though AWS Bedrock pricing-only and Google Vertex published-endpoints fallbacks completed.
  - Scope: `backend/inference_sync.py`, `scripts/test_inference_sync_smoke.sh`, README inference smoke notes.
  - Acceptance: Azure pricing rate limits are represented as a retryable/rate-limited skipped outcome that smoke tests accept with a clear reason; non-rate-limit sync failures still fail the script; docs explain that public pricing can rate-limit.
  - Validation: mocked or live Azure 429 run reports a skipped/rate-limited status; `PYTHON=python ./scripts/test_inference_sync_smoke.sh`; `PYTHON=python ./scripts/test_inference_sync_smoke.sh aws-bedrock google-vertex-ai`.
  - Completed: 2026-07-01. Azure Retail Prices API HTTP 429 now reports a retryable `rate_limited` skipped outcome, smoke tests accept skipped retryable destinations, and docs explain the rate-limit behavior.

- [x] LBM-010: P3 Trim agent instruction debt after kit install
  - Source: Codex repo review 2026-07-01.
  - Problem: `make agent-docs-lint` passes with warnings because `AGENTS.md` exceeds its budget and `.agent-workflows/repo-review.md` has a rule-provenance warning.
  - Scope: `AGENTS.md`, `.agent-workflows/repo-review.md`, scoped docs linked from those files.
  - Acceptance: `AGENTS.md` becomes a shorter route map; detailed rules move to scoped docs or checker-owned config; rule-like bullets have clear provenance/context.
  - Validation: `make agent-docs-lint`; `make docs-check`.
  - Completed: 2026-07-01. `AGENTS.md` is back under budget as a route map, detailed kit/task rules route to scoped workflow docs, and `make agent-docs-lint` passes without warnings.

- [x] LBM-001: P1 Split startup bootstrap from live metadata refresh
  - Source: Codex repo review 2026-07-01.
  - Problem: FastAPI startup calls `bootstrap()`, which can perform live OpenRouter, model-card, license, and market enrichment while hiding refresh failures.
  - Scope: `backend/main.py`, `backend/update_engine.py`, `backend/cli.py`, README/docs for runtime behavior.
  - Acceptance: API startup only creates/repairs local schema and applies local baselines; external refreshes run through explicit CLI/API update paths; refresh failures are logged or stored visibly.
  - Validation: `python -m py_compile backend/*.py backend/sources/*.py`; `python -m unittest backend.test_catalog_export backend.test_rankings`; `python -m backend bootstrap`; `python -m backend model-card-audit --json`; `make docs-check`.
  - Completed: 2026-07-01. `bootstrap()` is now local-only and README/update guide describe explicit refresh paths.

- [x] LBM-002: P1 Add a local admin guard to mutating API routes
  - Source: Codex repo review 2026-07-01.
  - Problem: Provider, approval, curation, manual-score, and update endpoints mutate SQLite state without authentication.
  - Scope: `backend/main.py`, `backend/models.py`, README/API docs.
  - Acceptance: all POST/PATCH/PUT mutation routes require an explicit local admin token or equivalent opt-in guard; read-only routes remain usable without credentials; local-only deployment instructions are documented.
  - Validation: API tests cover authorized and unauthorized mutation attempts; `python -m unittest backend.test_api_auth backend.test_rankings backend.test_catalog_export`; `make docs-check`.
  - Completed: 2026-07-01. Mutating API routes are disabled unless `LLM_BENCHMARKING_ADMIN_TOKEN` is configured, and requests must send the token via header or bearer auth.

- [x] LBM-008: P1 Establish a clean initial Git baseline
  - Source: Codex repo review 2026-07-01.
  - Problem: the repo now has a `.git` directory but no commits; every project file is untracked, so diff-based kit gates, docs-impact checks, and future reviews cannot distinguish baseline from change.
  - Scope: repository root, `.gitignore`, generated/runtime artifacts, first commit plan.
  - Acceptance: tracked source/docs/config files are intentionally staged; ignored runtime artifacts remain ignored; an initial baseline commit exists before feature work starts.
  - Validation: `git status --short`; `make docs-check`; `python -m unittest backend.test_api_auth backend.test_catalog_export backend.test_rankings`; `kit start --no-update --json`.
  - Completed: 2026-07-01. Local baseline commits now track source/docs/config files, generated runtime artifacts remain ignored, and kit sees a clean target-installed repo.

- [x] LBM-011: P1 Make inference scripts use the active project Python
  - Source: Codex update-script test 2026-07-01.
  - Problem: `scripts/test_inference_suite.sh` and `scripts/test_inference_sync_smoke.sh` hard-code `python3`; on this machine that resolves to Homebrew Python 3.14 without project dependencies, while `python` resolves to the dependency-bearing project environment.
  - Scope: `scripts/test_inference_suite.sh`, `scripts/test_inference_sync_smoke.sh`, README contributor workflow.
  - Acceptance: scripts honor an explicit `PYTHON` override and otherwise use the active environment interpreter; dependency/import failures identify the interpreter path and next setup command; README examples match the script behavior.
  - Validation: `PYTHON=python ./scripts/test_inference_suite.sh`; `PYTHON=python ./scripts/test_inference_sync_smoke.sh aws-bedrock google-vertex-ai`; README contributor command copy/paste check.
  - Completed: 2026-07-01. Inference scripts now use `PYTHON=${PYTHON:-python}` and preflight core project dependencies with the resolved interpreter path in failure output.

- [x] LBM-013: P1 Harden OpenRouter ranking refresh when `rankingData` is absent
  - Source: Codex update-script test 2026-07-01.
  - Problem: `python -m backend update` and selected benchmark updates add scores but exit failed because the OpenRouter rankings page no longer exposes `rankingData`; the market refresh failure is coupled to otherwise successful benchmark ingestion.
  - Scope: `backend/update_engine.py`, OpenRouter market/ranking parser tests, update-history/audit reporting.
  - Acceptance: missing or changed OpenRouter ranking-page data is recorded as a visible degraded/skipped source result without failing unrelated benchmark updates; parser coverage includes the current page shape or a graceful fallback when the expected variable is absent.
  - Validation: temp-database `python -m backend update`; temp-database `python -m backend update --benchmarks terminal_bench swebench_verified`; `python -m backend list-models --output /tmp/llm-benchmarking-models.json`; targeted parser tests for missing `rankingData`.
  - Completed: 2026-07-01. Missing OpenRouter ranking payloads now record nonfatal `openrouter_market` warnings, full and selected temp updates complete, and list export wrote 826 models.

- [x] LBM-003: P2 Make update execution single-flight and crash-aware
  - Source: Codex repo review 2026-07-01.
  - Problem: `/api/update` starts daemon-thread update work; concurrent requests can queue ambiguous running jobs, and process exit can abandon work mid-run.
  - Scope: `backend/update_engine.py`, `backend/main.py`, update history tests.
  - Acceptance: only one update can run at a time; duplicate update requests return the active log or a clear conflict; interrupted updates are recoverable and reported with a precise status.
  - Validation: tests cover concurrent scheduling, active-log response, and interrupted update recovery; targeted backend unittest suite.
  - Completed: 2026-07-01. Update scheduling now reuses an existing running log id, starts only one worker, and recovery marks interrupted running logs failed with a precise error.

- [x] LBM-004: P2 Normalize Python test entrypoints and package discovery
  - Source: Codex repo review 2026-07-01.
  - Problem: targeted `python -m unittest ...` passes, but `python -m unittest discover backend` imports `backend/sources` as top-level `sources`; inference scripts hard-code `python3`, which resolves to an interpreter without deps on this machine.
  - Scope: `scripts/test_inference_suite.sh`, `scripts/test_inference_sync_smoke.sh`, README contributor workflow, unittest discovery/package layout.
  - Acceptance: documented test commands and scripts use the active environment interpreter; broad discovery either passes or is replaced by a documented canonical test command that cannot drift.
  - Validation: `PYTHON=python ./scripts/test_inference_suite.sh`; `PYTHON=python ./scripts/test_inference_sync_smoke.sh`; README contributor command copy/paste check.
  - Completed: 2026-07-01. The suite script now runs `python -m unittest discover -s backend -t .` and README warns against the broken `discover backend` import root.
