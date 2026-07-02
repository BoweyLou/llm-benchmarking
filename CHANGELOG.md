# Changelog

## 0.2.0 - Unreleased

- Added the FastAPI-served `/review` banking model review workbench with filterable model/use-case/family views, token-guarded review decision APIs, manual model creation, deprecation support, and review snapshot export/import.
- Changed the review workbench model table to show the best available release-date indicator instead of the use-case approval update time, and added matching browser CSV columns for that best-date value.
- Added a review workbench `Rankings` view for role-aware use-case rankings and raw benchmark leaderboards, including score breakdowns in the right inspector.
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
