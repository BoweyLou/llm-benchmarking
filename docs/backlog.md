# Backlog

Source of truth: repo-local backlog mirror for LLM Benchmarking maintenance.
Repo mirror purpose: local kit selectors, task-packet handoff, and review follow-up.
Stale mirror policy: refresh from current review findings before implementation when
the row is older than 14 days or the backend/API shape has changed.

## Open

- [ ] LBM-034: P2 Add authoritative retrieval-model taxonomy and enterprise-default signals
  - Source: Codex request 2026-07-02 after reviewing embedding/reranker export coverage.
  - Problem: the catalog now includes embedding and reranking models through MTEB and provider-owned discovery lanes, but downstream users still have to infer "sentence transformers", TEI-deployable models, and corporate-mainstay retrieval defaults from names, providers, and benchmark IDs.
  - Scope: authoritative retrieval-source config, model taxonomy/export fields, MTEB enrichment, official provider catalogs for OpenAI/Cohere/Voyage/Jina, official Hugging Face org discovery for Sentence Transformers/BAAI/intfloat/Alibaba-NLP/Jina/Nomic/Snowflake, deployment-support signals from Hugging Face Text Embeddings Inference where stable, and default-candidate rationale across already-discovered NVIDIA/IBM retrieval rows.
  - Acceptance: exported models expose explicit retrieval taxonomy fields such as retrieval role, retrieval family, official/provider-owned status, hosted API availability, self-hostability, TEI support, dimensions/context where available, and an evidence-backed enterprise retrieval default candidate flag with source URL and rationale.
  - Validation: fixture-backed source tests for provider catalogs and official HF org discovery; export/API tests for new fields; ranking regression proving generator, embedding, and reranker use cases remain separated; `PYTHON=python ./scripts/test_inference_suite.sh`; `make docs-check`; `make version-check` if schema/API output changes.

## Done

- [x] LBM-051: P2 Expand small-model generator discovery beyond Gemma
  - Source: Human request 2026-07-02 after seeing the small-model filter mostly show Gemma rows while obvious small families such as Phi were missing.
  - Problem: configured provider-owned Hugging Face discovery only covered Google Gemma for generator small-model rows, so Microsoft Phi and other common small/open generator families did not appear as small-model candidates unless another source happened to discover them.
  - Scope: add curated provider-owned discovery lanes for Microsoft Phi, Meta Llama 3.2 small models, Qwen small models, Mistral/Ministral small models, and IBM Granite generators; preserve metadata-only discovery semantics; add a conservative curated fallback for Phi rows whose official HF metadata lacks numeric parameter counts; canonicalize Qwen/Alibaba and Mistral/Mistral AI provider facets.
  - Acceptance: `model-discovery-sync --source configured` imports additional provider-owned small generator rows, marks Phi rows as small candidates where configured, does not create benchmark scores, keeps community fine-tunes excluded unless trusted mirrors are configured, and avoids split Qwen/Mistral provider filters.
  - Validation: baseline coverage tests, Phi discovery regression, live configured discovery sync, full backend tests, docs/version checks, local and Proxmox catalog verification.
  - Completed: 2026-07-02. The small-model filter now includes common provider-owned small generator families beyond Gemma.

- [x] LBM-050: P2 Add restricted recommendation status
  - Source: Human request 2026-07-02 for limited-audience models such as cyber-specialist models that should only be available to certain people.
  - Problem: manual recommendation state could distinguish recommended, not recommended, and discouraged models, but it could not mark a model as approved only for a restricted group.
  - Scope: add `restricted` as an accepted manual/effective recommendation status across review APIs, CLI, CSV exports, family aggregation, and review-workbench filters/actions while keeping access details in recommendation notes.
  - Acceptance: reviewers can mark selected, filtered, family, or individual use-case decisions as `restricted`; the state persists in `model_use_case_approvals`, appears in exports/API payloads, and can be filtered separately from recommended/not recommended/discouraged.
  - Validation: focused API/CLI/export/ranking tests, full backend tests, and docs/version checks.
  - Completed: 2026-07-02. Restricted recommendation status is available for limited-audience review decisions.

- [x] LBM-049: P2 Make blank-use-case manual-rating triage usable
  - Source: Human request 2026-07-02 after trying to run a first-cut pass over approved models that had not been manually rated.
  - Problem: leaving `Use case` blank still let the workbench evaluate manual/effective/approval filters through the active use case, so reviewers could not reliably find generally approved models with no saved manual rating yet.
  - Scope: adjust review-workbench filtering so blank-use-case manual `Unrated` means no manual recommendation is saved in any use case, keep selected-use-case filters unchanged, update browser CSV use-case fields for matching approvals, and document the first-cut filter combination.
  - Acceptance: `General approval = Approved`, blank `Use case`, and `Manual recommendation = Unrated` returns approved models that still need a human manual recommendation pass.
  - Validation: static workbench coverage, rendered workbench smoke, docs/version checks, and live catalog count comparison.
  - Completed: 2026-07-02. Blank-use-case manual-rating triage now supports the first-cut review workflow.

- [x] LBM-048: P1 Canonicalize provider product/platform aliases
  - Source: Human request 2026-07-02 after seeing Amazon and Amazon Nova, plus Microsoft and Azure, as separate provider filters in the review workbench.
  - Problem: product/platform labels from sources and the provider-origin baseline could become active provider rows, splitting provider facets and provider-origin review.
  - Scope: add canonical provider aliases for Amazon Nova/AWS/Bedrock to Amazon and Azure/Microsoft Azure/Azure AI Foundry to Microsoft, repair existing model/provider rows during bootstrap, remove duplicate baseline provider rows, and keep inference destination matching compatible with old alias labels.
  - Acceptance: review/catalog provider facets show Amazon and Microsoft as parent providers while existing models, families, and inference destinations continue to resolve.
  - Validation: provider-directory repair regression, taxonomy alias regression, inference-catalog alias regression, full backend tests, docs/version checks, local and Proxmox catalog verification.
  - Completed: 2026-07-02. Provider alias canonicalization now runs during bootstrap and update paths.

- [x] LBM-047: P1 Add NVIDIA and IBM retrieval catalog discovery
  - Source: Human request 2026-07-02 after noticing NVIDIA and IBM embedding catalog gaps in the banking review workbench.
  - Problem: MTEB surfaced only some NVIDIA/IBM retrieval rows and did not cover provider-hosted catalog models such as NVIDIA NIM EmbedQA/RerankQA or IBM watsonx Slate; Hugging Face discovery also forced discovered rows into generator roles.
  - Scope: add role-aware Hugging Face discovery, add static provider catalog discovery rows, expand the tracked discovery baseline for NVIDIA retrieval/NIM and IBM watsonx/Granite retrieval models, update CLI/docs/tests, and verify discovery plus recommendation-sync.
  - Acceptance: `model-discovery-sync --source configured` imports provider-owned NVIDIA and IBM embedding/reranker/multimodal embedding rows with correct model roles and raw source records, without creating benchmark scores.
  - Validation: focused discovery/ranking tests, live configured discovery, model-card sync, and `recommendation-sync --profile australian_bank`.
  - Completed: 2026-07-02. Configured discovery added NVIDIA and IBM retrieval catalog coverage while leaving ranking evidence gates intact.

- [x] LBM-046: P2 Add country filtering to review workbench
  - Source: Human request 2026-07-02 while using the Proxmox-hosted banking review workbench.
  - Problem: reviewers could filter by provider but not by provider-origin country, making country-specific review passes too manual.
  - Scope: add provider-origin country facets to `/api/review/catalog`, add a left-rail `Country` filter, filter loaded models by `provider_origin_countries` with provider country fallback, update static coverage and user docs, redeploy Proxmox workbench, and verify in browser.
  - Acceptance: reviewers can select a country in the left rail and the table narrows to models whose provider origin includes that country.
  - Validation: inline script parse, review workbench tests, full backend suite, docs/version checks, browser smoke, live Proxmox HTML/API checks, and service health check.
  - Completed: 2026-07-02. Provider-origin country filtering is available in the banking review workbench.

- [x] LBM-045: P1 Separate general model approval from use-case approval in review workbench
  - Source: Human request 2026-07-02 after clarifying that reviewers need to approve a model in general and then approve individual use cases separately.
  - Problem: the review workbench exposed use-case approval clearly, but model-level approval was still ambiguous and the legacy `models.approved_for_use` column is synchronized from use-case rows.
  - Scope: add durable `models.general_*` approval fields, review API endpoint, snapshot export/import support, review-workbench general approval filter/table column/inspector panel/bulk actions, browser CSV columns, docs, and focused persistence tests.
  - Acceptance: reviewers can approve or reject selected, filtered, or family-visible models generally without changing `model_use_case_approvals`; use-case approval remains a separate active-use-case action.
  - Validation: inline script parse, review workbench tests, full backend suite, docs/version checks, browser smoke, live Proxmox HTML/API checks, and service health check.
  - Completed: 2026-07-02. General model approval is separate from use-case approval in storage, API, snapshots, exports, and UI.

- [x] LBM-044: P2 Add manual recommendation filtering to review workbench
  - Source: Human request 2026-07-02 after clarifying that `Clear rating` affects manual recommendation but not approval state.
  - Problem: the left-rail recommendation filter only targeted effective recommendation status, so reviewers could not directly find rows by saved manual override or cleared manual rating.
  - Scope: rename the existing recommendation filter to `Effective recommendation`, add a separate `Manual recommendation` filter, wire frontend filtering to `model_use_case_approvals.recommendation_status`, add static review-app coverage, update README/changelog/backlog, redeploy Proxmox workbench, and verify in browser.
  - Acceptance: reviewers can filter by manual `recommended`, `restricted`, `not_recommended`, `discouraged`, and `unrated` independently of effective recommendation and approval state.
  - Validation: inline script parse, review workbench tests, docs/version checks, browser smoke, live Proxmox HTML check, and service health check.
  - Completed: 2026-07-02. Manual recommendation filtering is available in the review workbench left rail.

- [x] LBM-043: P2 Improve review workbench iPad layout and use-case context
  - Source: Human request 2026-07-02 after using the deployed workbench on an iPad-resolution device and asking how use-case recommendations should be used.
  - Problem: the review workbench retained desktop column assumptions at tablet widths, making filters, table actions, inspector controls, and save context hard to fit or understand on iPad-sized screens.
  - Scope: responsive review-workbench CSS, wrapped table/bulk controls, tablet/portrait grid layouts, active use-case context in the table and save status, click-through use-case selection syncing, README workflow notes, changelog entry, live Proxmox redeploy, and browser smoke verification.
  - Acceptance: iPad-width layouts keep the filter rail, model table, inspector, and bottom actions reachable; use-case card selection makes the active save target explicit; docs explain Proposed, Manual, Effective, and Approval.
  - Validation: inline script parse, backend review tests, docs/version checks, in-app browser smoke at iPad landscape and portrait widths, live Proxmox HTML check, and service health check.
  - Completed: 2026-07-02. Tablet layouts and active use-case review context are clearer in the banking review workbench.

- [x] LBM-042: P1 Split bulk approval clearing from recommendation clearing in the review workbench
  - Source: Human bug report 2026-07-02 after a bulk clear operation appeared to sync but approved rows remained approved after reload.
  - Problem: the frontend `Clear` bulk action only sent `recommendation_status=unrated`; it did not send `approved_for_use=false`, so the API correctly saved a recommendation clear while leaving approval state unchanged.
  - Scope: add explicit `Not approved` bulk action, rename ambiguous `Clear` to `Clear rating`, preserve existing clear-rating behavior, add API regression coverage for `approved_for_use=false`, update README/backlog/changelog, redeploy Proxmox workbench, and verify live HTML.
  - Acceptance: reviewers can bulk clear approval state with `Not approved`; `Clear rating` only clears manual recommendation; false approval writes persist through the review API.
  - Validation: targeted review tests, full backend suite, docs/version checks, inline script parse, live Proxmox HTML check, and service health check.
  - Completed: 2026-07-02. Bulk approval clearing is now a distinct action and the ambiguous clear label is removed.

- [x] LBM-041: P2 Make all-filtered selection explicit for review bulk operations
  - Source: Human request 2026-07-02 after using bulk operations in the review workbench.
  - Problem: the page checkbox selected only the visible 50 rows, making it unclear how to bulk-apply a decision to every row matching the current filters.
  - Scope: table-toolbar `Select all filtered` action, count-labelled filtered selection, exact replacement of selected IDs with the filtered result set, page checkbox indeterminate state, README docs, changelog entry, Proxmox redeploy, and smoke verification.
  - Acceptance: reviewers can select all rows matching the current filters, not just the visible page; the selection count reflects the full filtered list; bulk operations still write explicit selected model IDs.
  - Validation: inline script parse, backend tests, docs/version checks, live Proxmox HTML check, and service health check.
  - Completed: 2026-07-02. Bulk selection can now target the full filtered result set from the workbench toolbar.

- [x] LBM-040: P2 Add browser CSV export scopes to the banking review workbench
  - Source: Human request 2026-07-02 after using the deployed interactive review workbench.
  - Problem: reviewers needed quick CSV exports from the front end for the whole catalog, the current filtered list, or selected rows without dropping back to the CLI.
  - Scope: workbench table toolbar export scope selector, client-side CSV generation, model/review/proposal columns for the active use case, README docs, changelog entry, live Proxmox redeploy, and smoke verification.
  - Acceptance: `/review` can export all rows, filtered rows, or selected rows to CSV; filtered export uses the same filter/sort state as the visible table; selected export preserves explicit row selection; export requires no admin token because it only serializes loaded catalog data.
  - Validation: backend suite remains green, docs/version checks pass, deployed HTML contains the export control, and live catalog export smoke verifies the updated app is served from Proxmox.
  - Completed: 2026-07-02. Browser CSV exports are available from the review workbench toolbar.

- [x] LBM-039: P1 Allow token-free review saves from trusted Tailscale clients
  - Source: Human request 2026-07-02 after trying to save from the deployed workbench and hitting the admin-token prompt.
  - Problem: the Proxmox workbench needed to be usable from any Tailscale device without manually copying an admin token into each browser session.
  - Scope: explicit trusted-tailnet write mode, loopback/Tailscale source-IP guard, auth tests, deploy-script environment wiring, README and deployment docs, live Proxmox redeploy, and tokenless write-route verification.
  - Acceptance: local/dev mutation routes remain token-protected by default; `LLM_BENCHMARKING_TRUSTED_TAILNET_WRITES=1` allows mutation requests from loopback or Tailscale clients without a token; the Proxmox deploy enables that mode by default while retaining the admin-token fallback.
  - Validation: auth tests, review workbench tests, full backend test suite, docs/version checks, live no-token snapshot export from `http://100.82.249.6:8766`, and token fallback check before closeout.
  - Completed: 2026-07-02. The Proxmox-hosted banking review workbench now supports token-free saves from trusted Tailscale clients.

- [x] LBM-038: P1 Deploy banking review workbench on the Proxmox tailnet host
  - Source: Human request 2026-07-02 after validating the local interactive review workbench.
  - Problem: the workbench needed to be available from any device on the Tailscale network without depending on a local development server.
  - Scope: Proxmox deploy script, systemd service unit, dedicated runtime user, tailnet-only bind address, persistent remote SQLite path, token-preserving environment file, README link, deployment runbook, and live service verification.
  - Acceptance: `scripts/deploy_proxmox_review_workbench.sh` deploys the current app to `proxmox`, seeds the remote DB only when missing, preserves `/var/lib/llm-benchmarking/db.sqlite` and `/etc/llm-benchmarking.env` across code updates, restarts `llm-benchmarking.service`, and verifies `/api/review/catalog` over the Proxmox Tailscale IP.
  - Validation: deploy script live run against Proxmox, systemd active check, tailnet HTTP catalog check, docs checks, backend tests, and version check before closeout.
  - Completed: 2026-07-02. The banking review workbench now has a repeatable Proxmox/Tailscale deployment path with durable remote state.

- [x] LBM-037: P1 Add interactive banking model review workbench
  - Source: Human request 2026-07-02 after the backend-only banking review utility proved insufficient for interactive model review.
  - Problem: reviewers needed to see the live model catalog, switch between filtered views, make decisions on individual models or concrete filtered lists, and persist determinations back to SQLite across normal catalog and recommendation updates.
  - Scope: FastAPI-served `/review` workbench, review catalog/read API, token-guarded decision/model/snapshot write APIs, explicit bulk model-id decisions, manual model creation, deprecation markers, snapshot export/import, README docs, and focused API/persistence tests.
  - Acceptance: `/review` shows filterable model, use-case, family, needs-decision, and deprecated views; selected or filtered actions write exact `model_use_case_approvals` and `models.catalog_status` rows; snapshot export/import restores manual listings and decisions after DB rebuild; write routes remain disabled unless `LLM_BENCHMARKING_ADMIN_TOKEN` is configured.
  - Validation: `python -m unittest backend.test_review_workbench backend.test_banking_review backend.test_api_auth backend.test_recommendation_engine`; browser smoke and full docs/version checks before closeout.
  - Completed: 2026-07-02. The local FastAPI app now includes an interactive banking model review workbench backed by durable SQLite decision rows and review snapshots.

- [x] LBM-035: P1 Add banking review export and manual curation utility
  - Source: Human request 2026-07-02.
  - Problem: the banking model review workflow could export generated recommendation proposals, but applying manual approvals, recommendation ratings, whole-family decisions, and deprecation markers still required low-level API calls or direct SQLite edits.
  - Scope: backend-only `banking-review` CLI, combined model/use-case CSV export, manual model addition, model/family approval and recommendation updates, deprecation markers, README examples, and focused tests.
  - Acceptance: `python -m backend banking-review export` writes a combined banking review CSV after syncing `australian_bank` proposals by default; `banking-review set` can target model ids or family ids; `banking-review add-model` can add a manual listing row; `banking-review deprecate` keeps deprecated rows visible in exports and can also mark them not recommended.
  - Validation: `python -m unittest backend.test_banking_review backend.test_catalog_export backend.test_recommendation_engine`; `make docs-check`.
  - Completed: 2026-07-02. The backend CLI now supports local banking review export and simple manual curation without reintroducing a frontend workflow.

- [x] LBM-036: P2 Improve model-age data with release-date provenance and proxy age evidence
  - Source: User request 2026-07-02 after reviewing sparse model-age coverage.
  - Problem: the catalog had only sparse `release_date` values and did not distinguish official/source-asserted release dates from proxy timestamps such as repository creation, OpenRouter addition, or local discovery.
  - Scope: model schema/API/export fields for release-date provenance and computed model-age evidence; Artificial Analysis and IFEval release-date promotion; Hugging Face repository timestamps; all-modality OpenRouter refresh; docs and tests.
  - Acceptance: exports expose release date precision, confidence, source URL, verification timestamp, computed age days, age basis/confidence, and Hugging Face timestamps without treating proxy timestamps as official release dates.
  - Validation: targeted unit/source/migration tests; docs checks; version check.
  - Completed: 2026-07-02. Model exports now include explicit release-date provenance, computed model-age evidence, Hugging Face repo timestamps, and all-modality OpenRouter discovery coverage.

- [x] LBM-032: P3 Add MTEB retrieval/reranking support after model taxonomy can distinguish generator vs embedding models
  - Source: Data ingest source map 2026-07-01, conditional new source adapter.
  - Problem: MTEB is relevant for embedding and reranking model selection, especially RAG retrieval sorting and document operations, but the current catalog is primarily generator-model oriented.
  - Scope: model taxonomy changes for embedding/reranking model kinds, `backend/sources/mteb.py`, retrieval/reranking benchmark seed rows, export/ranking docs/tests.
  - Acceptance: do not ingest MTEB into the current generator ranking model until schema and taxonomy explicitly represent non-generator models; once supported, import task/category scores with language/task metadata.
  - Validation: taxonomy tests; fixture-backed MTEB import tests; export tests showing generator and embedding/reranking models are not mixed incorrectly; `make docs-check`.
  - Completed: 2026-07-01. MTEB now imports retrieval, reranking, and blended retrieval/reranking averages from official result files, while `model_roles` keeps embedding/reranker rankings separate from generator-model rankings.

- [x] LBM-016: P1 Promote adapter-fetched metadata into model metadata with source precedence
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: Chatbot Arena and IFEval already fetch useful organization, license, pricing, context, latency, throughput, provider/model ID, and model URL fields, but most of that evidence remains raw-record-only and cannot help catalog review when OpenRouter or Hugging Face data is absent or stale.
  - Scope: `backend/update_engine.py`, `backend/sources/chatbot_arena.py`, `backend/sources/ifeval.py`, `backend/models.py` if response models need new fields, source-precedence docs/tests.
  - Acceptance: define explicit metadata precedence rules; promote only trustworthy fields into model metadata; preserve raw evidence and source URLs; avoid overriding higher-trust first-party, tracked baseline, OpenRouter, or Hugging Face fields without a clear rule.
  - Validation: targeted unit tests for precedence and conflict handling; temp-database update using mocked Chatbot Arena/IFEval records; `python -m backend list-models --no-csv`; `make docs-check`.
  - Completed: 2026-07-01. Adapter-fetched metadata now flows into model metadata through explicit source-precedence rules while preserving raw evidence and higher-trust overrides.

- [x] LBM-017: P2 Add Vectara hallucination companion metrics
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: the Vectara adapter already sees hallucination rate, answer rate, factual consistency, and average summary length, but only factual consistency becomes a catalog score.
  - Scope: `backend/sources/vectara.py`, benchmark seed rows, score normalization, ranking weights if companion metrics are consumed, docs/tests.
  - Acceptance: preserve the existing factual-consistency benchmark while adding explicit hallucination-rate and answer-rate evidence with clear lower-is-better semantics where applicable; do not treat grounded summarization as retrieval relevance.
  - Validation: fixture-backed Vectara normalization tests; ranking regression tests for RAG/document use cases; `PYTHON=python ./scripts/test_inference_suite.sh`; `make docs-check`.
  - Completed: 2026-07-01. Vectara now emits hallucination-rate and answer-rate companion metrics alongside factual consistency, with lower-is-better semantics for hallucination rate.

- [x] LBM-018: P2 Add FaithJudge task-level hallucination metrics
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: FaithJudge raw rows already include FaithBench/RAGTruth subtask rates, but the catalog stores only one hallucination aggregate.
  - Scope: `backend/sources/faithjudge.py`, benchmark seed rows for summarization, QA, and data-to-text subtasks, source-quality docs/tests.
  - Acceptance: add stable task-level benchmark IDs without removing the aggregate; preserve task labels, rank/source URL metadata, and lower-is-better direction.
  - Validation: fixture-backed FaithJudge parser tests; RAG ranking regression tests; `python -m unittest backend.test_source_spot_checks`; `make docs-check`.
  - Completed: 2026-07-01. FaithJudge now emits task-level FaithBench/RAGTruth summarization, QA, and data-to-text hallucination metrics without removing the aggregate.

- [x] LBM-019: P2 Add MMMU variant and pro companion metrics
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: MMMU upstream data includes validation/test/pro fields and baselines, but the current adapter only writes validation overall.
  - Scope: `backend/sources/mmmu.py`, benchmark seed rows for stable MMMU-Pro or test/pro result fields, score semantics docs/tests.
  - Acceptance: ingest only stable model-level MMMU variant fields; keep human/random baselines out of model rankings; keep the current validation-overall benchmark unchanged.
  - Validation: fixture-backed MMMU payload tests; multimodal ranking regression tests; `python -m unittest backend.test_source_spot_checks`; `make docs-check`.
  - Completed: 2026-07-01. MMMU now preserves stable test and MMMU-Pro companion metrics while keeping validation overall and skipping human/random baselines.

- [x] LBM-020: P2 Preserve Terminal-Bench agent and harness evidence
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: Terminal-Bench rows include agent, version, integration method, date, and stderr details, but the current score collapses harness effects into a single model capability score.
  - Scope: `backend/sources/terminal_bench.py`, raw metadata persistence, companion evidence or benchmark model for agent systems, ranking/docs/tests.
  - Acceptance: preserve model-only ranking compatibility while making agent/harness metadata queryable; document the difference between model capability and best agent system evidence.
  - Validation: fixture-backed Terminal-Bench parsing tests; ranking regression tests for agentic use cases; `python -m unittest backend.test_source_spot_checks`; `make docs-check`.
  - Completed: 2026-07-01. Terminal-Bench raw records and notes preserve agent, harness, version, integration, date, and stderr evidence while keeping model-score compatibility.

- [x] LBM-021: P2 Expand AILuminate locale, system-class, and risk evidence
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: AILuminate currently selects one best public grade per model, losing locale, system-class, and risk-category detail that matters for safety/compliance review.
  - Scope: `backend/sources/ailuminate.py`, benchmark seed rows or companion evidence storage, detail-page parser if stable, safety docs/tests.
  - Acceptance: retain the current public-grade benchmark while preserving per-locale and per-system-class evidence; add risk-category breakdowns only when the source surface is stable enough to test.
  - Validation: fixture-backed AILuminate normalization tests; safety ranking regression tests; `PYTHON=python ./scripts/test_inference_suite.sh`; `make docs-check`.
  - Completed: 2026-07-01. AILuminate now preserves locale and system-class evidence as companion benchmark rows while retaining the public-grade aggregate.

- [x] LBM-022: P2 Expand Artificial Analysis ingestion beyond the model leaderboard
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: the current Artificial Analysis adapter only ingests intelligence, speed, and blended cost from the model leaderboard, while AA publishes additional evaluation pages that could fill coding, instruction-following, long-context, safety/openness, and enterprise-agent gaps.
  - Scope: new or generalized AA evaluation adapters under `backend/sources/`, benchmark seed rows, parser tests, source-quality documentation.
  - Acceptance: ingest at least one additional stable AA evaluation page first; record source page, metric, score direction, token/cost data when present, and parser degradation as source-run errors rather than failing unrelated updates.
  - Validation: fixture-backed parser tests; selected temp-database update for the new AA benchmark; `python -m backend update --benchmarks <new-aa-benchmark>` on a temp database when network access is appropriate; `make docs-check`.
  - Completed: 2026-07-01. Artificial Analysis ingestion now includes IFBench score, cost, output-token, and latency metrics through a dedicated AA evaluation adapter.

- [x] LBM-023: P2 Expand SWE-bench coverage beyond Verified while preserving scaffold metadata
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: the current SWE-bench adapter only imports the Verified board and collapses harness/scaffold effects into a model score, while official SWE-bench surfaces include other splits such as Lite, Full, Multilingual, and Multimodal.
  - Scope: `backend/sources/swebench.py`, benchmark seed rows, raw metadata persistence, ranking weights if additional SWE-bench splits are consumed, docs.
  - Acceptance: ingest one or more official additional splits with split IDs; preserve submitter, scaffold, agent, date, and single-model policy metadata; keep current Verified behavior stable.
  - Validation: fixture-backed split parsing tests; best-submission selection tests; `python -m unittest backend.test_source_spot_checks`; `make docs-check`.
  - Completed: 2026-07-01. SWE-bench now imports Lite, Full, Multilingual, and Multimodal companion split scores while preserving submitter/scaffold metadata.

- [x] LBM-024: P1 Expose source freshness and degraded-source status in model exports
  - Source: Data ingest source map 2026-07-01, existing-source win.
  - Problem: update logs and source runs already know source failures, stale data, and nonfatal OpenRouter market warnings, but `list-models` does not expose enough freshness/degradation context for downstream review.
  - Scope: `backend/update_engine.py`, `backend/catalog_export.py`, API response models if needed, export docs/tests.
  - Acceptance: each exported model or source summary can show latest successful source collection, latest failure/degraded warning, and whether a score or metadata field is stale or missing because a source failed.
  - Validation: unit tests using synthetic update logs/source runs; `python -m backend list-models --format json --no-csv`; catalog export tests; `make docs-check`.
  - Completed: 2026-07-01. Model exports now carry source freshness and degraded-source context derived from source-run/update-log history.

- [x] LBM-025: P1 Add a LiveBench source adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: LiveBench is designed for contamination-resistant, objectively scored public evaluation with newer/monthly question releases, but the catalog has no LiveBench signal for general reasoning, math, coding, data analysis, language, or instruction-following.
  - Scope: `backend/sources/livebench.py`, benchmark seed rows, name resolution fixtures, source-run/raw-record tests, docs.
  - Acceptance: import LiveBench category-level scores first; include release/version metadata and source URLs; optionally add task-level subscores only after category ingestion is stable.
  - Validation: fixture-backed parser tests; temp-database selected update; ranking coverage check for affected use cases; `make docs-check`.
  - Completed: 2026-07-01. LiveBench now imports official static leaderboard overall and category scores with release and task-score metadata.

- [x] LBM-026: P1 Add a Berkeley Function Calling Leaderboard source adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: the catalog lacks a function-calling/tool-use benchmark even though BFCL is a public executable benchmark for function invocation, multi-turn, and multi-step tool-use behavior.
  - Scope: `backend/sources/bfcl.py`, benchmark seed rows for function-calling categories, source metadata/trust labels, docs/tests.
  - Acceptance: ingest model scores with category, multi-turn/multi-step, executable/static, and source-release metadata; keep BFCL distinct from broader agentic benchmarks such as Terminal-Bench.
  - Validation: parser tests from stable public artifacts; temp-database selected update; ranking tests for agentic/workflow use cases; `make docs-check`.
  - Completed: 2026-07-01. BFCL now imports official function-calling overall scores while preserving component, cost, latency, organization, license, and evaluation-mode metadata.

- [x] LBM-027: P1 Add a LiveCodeBench source adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: coding rankings currently depend heavily on SWE-bench, Terminal-Bench, and Artificial Analysis aggregate intelligence, but not a contamination-resistant coding benchmark focused on fresh competition problems, self-repair, and execution.
  - Scope: `backend/sources/livecodebench.py`, benchmark seed rows, coding use-case weights, source-quality docs/tests.
  - Acceptance: ingest score plus variant metadata such as pass@1, easy/medium/hard, self-repair/execution dimensions when available, release window, and source URL.
  - Validation: fixture-backed parser tests; temp-database selected update; coding ranking regression tests; `make docs-check`.
  - Completed: 2026-07-01. LiveCodeBench now imports code-generation pass@1 for the default window and preserves difficulty, platform, release-window, and contamination metadata.

- [x] LBM-028: P2 Add a BigCodeBench source adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: the catalog has limited pure code-generation evidence beyond agent/harness-driven coding boards; BigCodeBench provides practical programming tasks with Hard/Full and Complete/Instruct variants.
  - Scope: `backend/sources/bigcodebench.py`, benchmark seed rows for variant scores, parser fixtures, docs/tests.
  - Acceptance: ingest BigCodeBench scores without collapsing Hard/Full and Complete/Instruct variants into one opaque score; record recommendation/size/view metadata when available.
  - Validation: fixture-backed parser tests; temp-database selected update; coding ranking regression tests; `make docs-check`.
  - Completed: 2026-07-01. BigCodeBench now imports Full/Hard aggregate and Instruct/Complete variant scores as separate benchmark IDs.

- [x] LBM-029: P2 Add a HELM published-leaderboard snapshot adapter
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: HELM provides transparent and reproducible capability, safety, and vision-language leaderboards that can triangulate general, safety, instruction-following, and multimodal decisions, but the repo has no HELM import path.
  - Scope: `backend/sources/helm.py`, benchmark seed rows for selected HELM surfaces, release/version metadata, docs/tests.
  - Acceptance: import published snapshots with explicit HELM release/version and maintenance/freshness metadata; treat HELM as triangulation rather than the freshest primary signal.
  - Validation: fixture-backed snapshot parsing tests; selected update against a stable snapshot; docs note HELM maintenance-mode caveat; `make docs-check`.
  - Completed: 2026-07-01. HELM Capabilities now imports the core-scenarios mean plus MMLU-Pro, GPQA, IFEval, WildBench, and Omni-MATH component scores with release metadata.

- [x] LBM-030: P2 Add a tau-bench result ingest lane
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: enterprise support/workflow rankings lack realistic customer-service, tool-policy, knowledge/RAG, and voice-agent evaluation signals from tau2/tau3-bench domains.
  - Scope: a tau-bench adapter or local-result import module, benchmark seed rows, result schema for domain/mode/task metadata, docs/tests.
  - Acceptance: support ingesting public leaderboard data if stable, or local tau-bench result artifacts if the public leaderboard is not machine-readable; preserve domain, mode, policy/tool, user-simulator, and run metadata.
  - Validation: fixture-backed result import tests; schema validation for local result artifacts; ranking tests for customer-support/workflow use cases; `make docs-check`.
  - Completed: 2026-07-01. tau-bench now imports standard text and voice domain scores, preserves domain/retrieval metadata, and skips aggregate/custom systems where appropriate.

- [x] LBM-031: P2 Add a RAGTruth direct evidence adapter or local-result import
  - Source: Data ingest source map 2026-07-01, new source adapter.
  - Problem: current RAG evidence uses Vectara and FaithJudge aggregates, but RAGTruth has direct word-level hallucination annotations across QA, data-to-text, and summarization that could improve RAG and document-operation suitability decisions.
  - Scope: `backend/sources/ragtruth.py` or local-result import module, benchmark seed rows for task-level hallucination metrics, docs/tests.
  - Acceptance: ingest only curated published model results unless a local evaluation harness is explicitly added; preserve task type, label granularity, split, and source-response metadata.
  - Validation: fixture-backed parser/import tests; RAG ranking regression tests; source-quality docs; `make docs-check`.
  - Completed: 2026-07-01. RAGTruth now imports overall and task-level hallucination rates for the published held-out corpus with split and metric metadata.

- [x] LBM-033: P2 Normalize CSV exports for spreadsheet review
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
