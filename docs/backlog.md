# Backlog

Source of truth: repo-local backlog mirror for LLM Benchmarking maintenance.
Repo mirror purpose: local kit selectors, task-packet handoff, and review follow-up.
Stale mirror policy: refresh from current review findings before implementation when
the row is older than 14 days or the backend/API shape has changed.

## Open

- [ ] LBM-016: P1 Promote adapter-fetched metadata into model metadata with source precedence
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: Chatbot Arena and IFEval already fetch useful organization, license, pricing, context, latency, throughput, provider/model ID, and model URL fields, but most of that evidence remains raw-record-only and cannot help catalog review when OpenRouter or Hugging Face data is absent or stale.
  - Scope: `backend/update_engine.py`, `backend/sources/chatbot_arena.py`, `backend/sources/ifeval.py`, `backend/models.py` if response models need new fields, source-precedence docs/tests.
  - Acceptance: define explicit metadata precedence rules; promote only trustworthy fields into model metadata; preserve raw evidence and source URLs; avoid overriding higher-trust first-party, tracked baseline, OpenRouter, or Hugging Face fields without a clear rule.
  - Validation: targeted unit tests for precedence and conflict handling; temp-database update using mocked Chatbot Arena/IFEval records; `python -m backend list-models --no-csv`; `make docs-check`.

- [ ] LBM-017: P2 Add Vectara hallucination companion metrics
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: the Vectara adapter already sees hallucination rate, answer rate, factual consistency, and average summary length, but only factual consistency becomes a catalog score.
  - Scope: `backend/sources/vectara.py`, benchmark seed rows, score normalization, ranking weights if companion metrics are consumed, docs/tests.
  - Acceptance: preserve the existing factual-consistency benchmark while adding explicit hallucination-rate and answer-rate evidence with clear lower-is-better semantics where applicable; do not treat grounded summarization as retrieval relevance.
  - Validation: fixture-backed Vectara normalization tests; ranking regression tests for RAG/document use cases; `PYTHON=python ./scripts/test_inference_suite.sh`; `make docs-check`.

- [ ] LBM-018: P2 Add FaithJudge task-level hallucination metrics
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: FaithJudge raw rows already include FaithBench/RAGTruth subtask rates, but the catalog stores only one hallucination aggregate.
  - Scope: `backend/sources/faithjudge.py`, benchmark seed rows for summarization, QA, and data-to-text subtasks, source-quality docs/tests.
  - Acceptance: add stable task-level benchmark IDs without removing the aggregate; preserve task labels, rank/source URL metadata, and lower-is-better direction.
  - Validation: fixture-backed FaithJudge parser tests; RAG ranking regression tests; `python -m unittest backend.test_source_spot_checks`; `make docs-check`.

- [ ] LBM-019: P2 Add MMMU variant and pro companion metrics
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: MMMU upstream data includes validation/test/pro fields and baselines, but the current adapter only writes validation overall.
  - Scope: `backend/sources/mmmu.py`, benchmark seed rows for stable MMMU-Pro or test/pro result fields, score semantics docs/tests.
  - Acceptance: ingest only stable model-level MMMU variant fields; keep human/random baselines out of model rankings; keep the current validation-overall benchmark unchanged.
  - Validation: fixture-backed MMMU payload tests; multimodal ranking regression tests; `python -m unittest backend.test_source_spot_checks`; `make docs-check`.

- [ ] LBM-020: P2 Preserve Terminal-Bench agent and harness evidence
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: Terminal-Bench rows include agent, version, integration method, date, and stderr details, but the current score collapses harness effects into a single model capability score.
  - Scope: `backend/sources/terminal_bench.py`, raw metadata persistence, companion evidence or benchmark model for agent systems, ranking/docs/tests.
  - Acceptance: preserve model-only ranking compatibility while making agent/harness metadata queryable; document the difference between model capability and best agent system evidence.
  - Validation: fixture-backed Terminal-Bench parsing tests; ranking regression tests for agentic use cases; `python -m unittest backend.test_source_spot_checks`; `make docs-check`.

- [ ] LBM-021: P2 Expand AILuminate locale, system-class, and risk evidence
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: AILuminate currently selects one best public grade per model, losing locale, system-class, and risk-category detail that matters for safety/compliance review.
  - Scope: `backend/sources/ailuminate.py`, benchmark seed rows or companion evidence storage, detail-page parser if stable, safety docs/tests.
  - Acceptance: retain the current public-grade benchmark while preserving per-locale and per-system-class evidence; add risk-category breakdowns only when the source surface is stable enough to test.
  - Validation: fixture-backed AILuminate normalization tests; safety ranking regression tests; `PYTHON=python ./scripts/test_inference_suite.sh`; `make docs-check`.

- [ ] LBM-022: P2 Expand Artificial Analysis ingestion beyond the model leaderboard
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: the current Artificial Analysis adapter only ingests intelligence, speed, and blended cost from the model leaderboard, while AA publishes additional evaluation pages that could fill coding, instruction-following, long-context, safety/openness, and enterprise-agent gaps.
  - Scope: new or generalized AA evaluation adapters under `backend/sources/`, benchmark seed rows, parser tests, source-quality documentation.
  - Acceptance: ingest at least one additional stable AA evaluation page first; record source page, metric, score direction, token/cost data when present, and parser degradation as source-run errors rather than failing unrelated updates.
  - Validation: fixture-backed parser tests; selected temp-database update for the new AA benchmark; `python -m backend update --benchmarks <new-aa-benchmark>` on a temp database when network access is appropriate; `make docs-check`.

- [ ] LBM-023: P2 Expand SWE-bench coverage beyond Verified while preserving scaffold metadata
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: the current SWE-bench adapter only imports the Verified board and collapses harness/scaffold effects into a model score, while official SWE-bench surfaces include other splits such as Lite, Full, Multilingual, and Multimodal.
  - Scope: `backend/sources/swebench.py`, benchmark seed rows, raw metadata persistence, ranking weights if additional SWE-bench splits are consumed, docs.
  - Acceptance: ingest one or more official additional splits with split IDs; preserve submitter, scaffold, agent, date, and single-model policy metadata; keep current Verified behavior stable.
  - Validation: fixture-backed split parsing tests; best-submission selection tests; `python -m unittest backend.test_source_spot_checks`; `make docs-check`.

- [ ] LBM-024: P1 Expose source freshness and degraded-source status in model exports
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: update logs and source runs already know source failures, stale data, and nonfatal OpenRouter market warnings, but `list-models` does not expose enough freshness/degradation context for downstream review.
  - Scope: `backend/update_engine.py`, `backend/catalog_export.py`, API response models if needed, export docs/tests.
  - Acceptance: each exported model or source summary can show latest successful source collection, latest failure/degraded warning, and whether a score or metadata field is stale or missing because a source failed.
  - Validation: unit tests using synthetic update logs/source runs; `python -m backend list-models --format json --no-csv`; catalog export tests; `make docs-check`.

- [ ] LBM-025: P1 Add a LiveBench source adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: LiveBench is designed for contamination-resistant, objectively scored public evaluation with newer/monthly question releases, but the catalog has no LiveBench signal for general reasoning, math, coding, data analysis, language, or instruction-following.
  - Scope: `backend/sources/livebench.py`, benchmark seed rows, name resolution fixtures, source-run/raw-record tests, docs.
  - Acceptance: import LiveBench category-level scores first; include release/version metadata and source URLs; optionally add task-level subscores only after category ingestion is stable.
  - Validation: fixture-backed parser tests; temp-database selected update; ranking coverage check for affected use cases; `make docs-check`.

- [ ] LBM-026: P1 Add a Berkeley Function Calling Leaderboard source adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: the catalog lacks a function-calling/tool-use benchmark even though BFCL is a public executable benchmark for function invocation, multi-turn, and multi-step tool-use behavior.
  - Scope: `backend/sources/bfcl.py`, benchmark seed rows for function-calling categories, source metadata/trust labels, docs/tests.
  - Acceptance: ingest model scores with category, multi-turn/multi-step, executable/static, and source-release metadata; keep BFCL distinct from broader agentic benchmarks such as Terminal-Bench.
  - Validation: parser tests from stable public artifacts; temp-database selected update; ranking tests for agentic/workflow use cases; `make docs-check`.

- [ ] LBM-027: P1 Add a LiveCodeBench source adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: coding rankings currently depend heavily on SWE-bench, Terminal-Bench, and Artificial Analysis aggregate intelligence, but not a contamination-resistant coding benchmark focused on fresh competition problems, self-repair, and execution.
  - Scope: `backend/sources/livecodebench.py`, benchmark seed rows, coding use-case weights, source-quality docs/tests.
  - Acceptance: ingest score plus variant metadata such as pass@1, easy/medium/hard, self-repair/execution dimensions when available, release window, and source URL.
  - Validation: fixture-backed parser tests; temp-database selected update; coding ranking regression tests; `make docs-check`.

- [ ] LBM-028: P2 Add a BigCodeBench source adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: the catalog has limited pure code-generation evidence beyond agent/harness-driven coding boards; BigCodeBench provides practical programming tasks with Hard/Full and Complete/Instruct variants.
  - Scope: `backend/sources/bigcodebench.py`, benchmark seed rows for variant scores, parser fixtures, docs/tests.
  - Acceptance: ingest BigCodeBench scores without collapsing Hard/Full and Complete/Instruct variants into one opaque score; record recommendation/size/view metadata when available.
  - Validation: fixture-backed parser tests; temp-database selected update; coding ranking regression tests; `make docs-check`.

- [ ] LBM-029: P2 Add a HELM published-leaderboard snapshot adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: HELM provides transparent and reproducible capability, safety, and vision-language leaderboards that can triangulate general, safety, instruction-following, and multimodal decisions, but the repo has no HELM import path.
  - Scope: `backend/sources/helm.py`, benchmark seed rows for selected HELM surfaces, release/version metadata, docs/tests.
  - Acceptance: import published snapshots with explicit HELM release/version and maintenance/freshness metadata; treat HELM as triangulation rather than the freshest primary signal.
  - Validation: fixture-backed snapshot parsing tests; selected update against a stable snapshot; docs note HELM maintenance-mode caveat; `make docs-check`.

- [ ] LBM-030: P2 Add a tau-bench result ingest lane
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: enterprise support/workflow rankings lack realistic customer-service, tool-policy, knowledge/RAG, and voice-agent evaluation signals from tau2/tau3-bench domains.
  - Scope: a tau-bench adapter or local-result import module, benchmark seed rows, result schema for domain/mode/task metadata, docs/tests.
  - Acceptance: support ingesting public leaderboard data if stable, or local tau-bench result artifacts if the public leaderboard is not machine-readable; preserve domain, mode, policy/tool, user-simulator, and run metadata.
  - Validation: fixture-backed result import tests; schema validation for local result artifacts; ranking tests for customer-support/workflow use cases; `make docs-check`.

- [ ] LBM-031: P2 Add a RAGTruth direct evidence adapter or local-result import
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: current RAG evidence uses Vectara and FaithJudge aggregates, but RAGTruth has direct word-level hallucination annotations across QA, data-to-text, and summarization that could improve RAG and document-operation suitability decisions.
  - Scope: `backend/sources/ragtruth.py` or local-result import module, benchmark seed rows for task-level hallucination metrics, docs/tests.
  - Acceptance: ingest only curated published model results unless a local evaluation harness is explicitly added; preserve task type, label granularity, split, and source-response metadata.
  - Validation: fixture-backed parser/import tests; RAG ranking regression tests; source-quality docs; `make docs-check`.

- [ ] LBM-032: P3 Add MTEB retrieval/reranking support after model taxonomy can distinguish generator vs embedding models
  - Source: Data ingest source map 2026-07-01, conditional new source adapter.
  - Problem: MTEB is relevant for embedding and reranking model selection, especially RAG retrieval sorting and document operations, but the current catalog is primarily generator-model oriented.
  - Scope: model taxonomy changes for embedding/reranking model kinds, `backend/sources/mteb.py`, retrieval/reranking benchmark seed rows, export/ranking docs/tests.
  - Acceptance: do not ingest MTEB into the current generator ranking model until schema and taxonomy explicitly represent non-generator models; once supported, import task/category scores with language/task metadata.
  - Validation: taxonomy tests; fixture-backed MTEB import tests; export tests showing generator and embedding/reranking models are not mixed incorrectly; `make docs-check`.

## Done

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
