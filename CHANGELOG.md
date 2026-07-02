# Changelog

## 0.2.0 - Unreleased

- Added the FastAPI-served `/review` banking model review workbench with filterable model/use-case/family views, token-guarded review decision APIs, manual model creation, deprecation support, and review snapshot export/import.
- Added browser-side CSV export options in the review workbench for all, filtered, and selected model rows.
- Added explicit all-filtered selection in the review workbench so bulk actions can target more than the visible page.
- Split review workbench bulk `Not approved` from `Clear rating` so clearing manual recommendations no longer looks like it clears approval state.
- Improved review workbench tablet layouts and active use-case context so iPad-width review sessions keep filters, tables, inspector details, and save targets reachable.
- Added a separate manual recommendation filter to the review workbench left rail while keeping effective recommendation filtering available.
- Added separate general model approval state and review workbench controls so model-level approval can be saved independently from use-case approval.
- Added a provider-origin country filter to the review workbench left rail.
- Added a Proxmox/Tailscale deployment path for the banking review workbench, including a systemd unit, deploy script, persistent remote SQLite location, and deployment runbook.
- Added trusted tailnet write mode so the Proxmox-hosted review workbench can save from Tailscale clients without pasting an admin token.
- Added release-date provenance, computed model-age evidence, Hugging Face repository timestamps, and all-modality OpenRouter discovery coverage to model exports.
- Added curated Hugging Face model discovery for official/provider-owned model families, starting with Google Gemma, so small-model candidates appear in catalog exports even without leaderboard coverage.
- Added model size metadata fields to the SQLite schema, API/list-models payloads, and clean CSV export.
- Added `python -m backend model-discovery-sync --source huggingface --family gemma` and `python -m backend update --refresh-model-discovery` for targeted discovery refreshes while keeping benchmark-scoped updates fast by default.
- Preserved `small_model_routing` evidence gates: discovered models are visible in the catalog, but they are not ranked until required cost and speed scores exist.

## 0.1.0 - Unreleased

- Initial local version baseline.
