# Changelog

## 0.6.0 - 2026-07-14

- Added explicit all-filtered bulk general decisions with a confirmation step, shared rationale, exact selected-model and source-record counts, and responsive mobile controls.
- Combined the general `Discouraged` state into `Not recommended`, including migration and legacy-input normalization, while leaving legacy use-case recommendation states intact for compatibility.
- Combined duplicate review rows only when normalized model name, canonical model ID, and model role agree; ambiguous same-name records remain separate and all underlying source records remain intact.
- Kept the full-catalog queue responsive with cached grouping and progressive 200-row rendering while preserving full all-filtered bulk selection.

## 0.5.0 - 2026-07-14

- Simplified human review to one general approval and one general recommendation per model, replacing the current workbench's use-case decision controls with a guided model-level flow.
- Added metric-derived, read-only suggested use cases with fit score, confidence, reasons, warnings, and required controls.
- Added the `/api/review/model-decisions` contract, durable general recommendation columns, snapshot version 2 support, and general-decision export fields while retaining legacy use-case rows and routes for audit compatibility (LBM-068).

## 0.4.3 - Unreleased

- Renamed the visible review surface and current deployment labels to `LLM Model Tool`, replacing the banking-specific header and subtitle while retaining compatible banking workflow identifiers (LBM-067).

## 0.4.2 - Unreleased

- Restored Artificial Analysis IFBench ingestion after upstream JSON-LD naming changes by supporting both current and legacy dataset names and score/time metric keys (LBM-066).

## 0.4.1 - Unreleased

- Fixed the review workbench freshness labels by separating the configured SQLite database/WAL modification time from the latest update-run timestamp and status, while retaining catalog response-generation time as distinct API metadata.

## 0.4.0 - Unreleased

- Added authenticated provider API catalog discovery for OpenAI, Anthropic, Google Gemini, Mistral, Cohere, and xAI, with credential-safe errors, provisional discovery policy, and non-blocking skipped runs when optional provider keys are absent.
- Added official OpenAI GPT-5.6 Sol, Terra, and Luna catalog discovery rows.
- Added per-run update change summaries so the review workbench shows new models, changed model metadata, removed active catalog rows, source record counts, and score changes after `Run updates`.
- Changed the review workbench default model listing order to newest release first.
- Added an explicit `Pending` use-case approval filter so selected use-case rows without saved approval decisions no longer disappear from review triage.
- Fixed filtered multi-use-case review saves so each selected use case receives the intended decision, and removed misleading Effective/model-level Proposed table and CSV export surfaces (LBM-061).

## 0.3.0 - Unreleased

- Replaced the fragile rendered LM Arena scrape with cross-subset revision-pinned official Parquet ingestion, distinct raw/style-controlled Text and category/WebDev/Agent/Vision/Document/Search benchmarks, generic structured score evidence, first/last-seen listing evidence, no-create identity handling, hardened audits, and a live isolated-database E2E contract.

## 0.2.0 - Unreleased

- Added the FastAPI-served `/review` banking model review workbench with filterable model/use-case/family views, token-guarded review decision APIs, manual model creation, deprecation support, and review snapshot export/import.
- Added review-catalog selection evidence and browser CSV columns for model type, strongest selection signal, ranking score/coverage, cost, speed, hyperscaler availability, and inference-location context.
- Changed the review workbench model table to show the best available release-date indicator instead of the use-case approval update time, and added matching browser CSV columns for that best-date value.
- Added a review workbench `Rankings` view for role-aware use-case rankings and raw benchmark leaderboards, including score breakdowns in the right inspector.
- Added `speech_to_text` model-role support, a `voice_to_text` use case, review-workbench capability filtering, and Hugging Face Open ASR Leaderboard ingestion for non-Whisper voice-to-text coverage.
- Added `text_to_speech` model-role support, Artificial Analysis Text to Speech quality/time/price ingestion, a TTS ranking use case, TTS review filters, and configured provider catalog rows for leading TTS models.
- Added restricted-access provider catalog rows for Claude Mythos 5 and GPT-5.5-Cyber, including trusted-access capability tags and official source links.
- Fixed manual embedding/reranker review curation so browser-added models carry their selected model role and save/bulk actions default to role-compatible use cases instead of a stale generator use case.
- Added a review workbench `Run updates` control that starts the full background update pipeline and shows live step progress from the update status API.
- Added `Unreviewed` as an explicit general-approval triage state in the review workbench and review API.
- Fixed the review workbench inspector tabs so `Controls`, `Activity`, and `Notes` switch to separate usable panels.
- Added RTEB Finance as a finance-domain retrieval benchmark from the official MTEB leaderboard dataset and included it as an optional retrieval-embedding ranking signal.
- Added browser-side CSV export options in the review workbench for all, filtered, and selected model rows.
- Added explicit all-filtered selection in the review workbench so bulk actions can target more than the visible page.
- Split review workbench bulk `Not approved` from `Clear rating` so clearing manual recommendations no longer looks like it clears approval state.
- Improved review workbench tablet layouts and active use-case context so iPad-width review sessions keep filters, tables, inspector details, and save targets reachable.
- Added a separate manual recommendation filter to the review workbench left rail while keeping effective recommendation filtering available.
- Refined blank-use-case manual recommendation filtering so first-cut triage can find generally approved models with no saved manual rating yet.
- Added `restricted` as a manual/effective recommendation status for models limited to specific approved user groups or cohorts.
- Added separate general model approval state and review workbench controls so model-level approval can be saved independently from use-case approval.
- Added a provider-origin country filter to the review workbench left rail.
- Added a hyperscaler availability filter to the review workbench left rail for AWS Bedrock, Azure AI Foundry, Google Vertex AI, any hyperscaler route, and no known hyperscaler route.
- Canonicalized provider aliases so Amazon Nova/AWS/Bedrock roll up to Amazon, Azure/Microsoft Azure/Azure AI Foundry roll up to Microsoft, Qwen rolls up to Alibaba, Mistral rolls up to Mistral AI, and ibm-granite rolls up to IBM in provider facets, exports, and inference matching.
- Added a Proxmox/Tailscale deployment path for the banking review workbench, including a systemd unit, deploy script, persistent remote SQLite location, and deployment runbook.
- Added trusted tailnet write mode so the Proxmox-hosted review workbench can save from Tailscale clients without pasting an admin token.
- Added release-date provenance, computed model-age evidence, Hugging Face repository timestamps, and all-modality OpenRouter discovery coverage to model exports.
- Added curated Hugging Face model discovery for official/provider-owned small model families, including Google Gemma, Microsoft Phi, Meta Llama 3.2 small models, Qwen small models, Mistral/Ministral small models, and IBM Granite generators, so small-model candidates appear in catalog exports even without leaderboard coverage.
- Added configured retrieval-catalog discovery for NVIDIA and IBM, covering provider-owned Hugging Face embedding/reranking repos plus tracked NVIDIA NIM and IBM watsonx Slate catalog rows.
- Added model size metadata fields to the SQLite schema, API/list-models payloads, and clean CSV export.
- Added `python -m backend model-discovery-sync --source configured`, targeted `--source huggingface|catalog`, and `python -m backend update --refresh-model-discovery` for targeted discovery refreshes while keeping benchmark-scoped updates fast by default.
- Preserved `small_model_routing` evidence gates: discovered models are visible in the catalog, but they are not ranked until required cost and speed scores exist.

## 0.1.0 - Unreleased

- Initial local version baseline.
