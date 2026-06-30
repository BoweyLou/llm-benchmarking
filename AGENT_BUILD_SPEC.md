# LLM Benchmarking Backend-Only Build Specification

## Goal

Maintain a local backend system that stores LLM benchmark scores, model metadata, provider-origin metadata, governance approvals, inference-location coverage, update history, and audit output.

The project no longer ships or maintains a frontend. The primary user-facing artifact is a simple serialized model metadata list produced by:

```bash
python -m backend list-models
```

## Architecture

```text
CLI / HTTP client
      |
      v
FastAPI backend + backend CLI
      |
      v
SQLite database at data/db.sqlite
      |
      v
Source adapters, model-card metadata, inference catalog sync, curation baselines
```

Single-machine deployment remains the target. No cloud service or authentication layer is required for local use.

## Output Contract

`python -m backend list-models` returns a JSON array by default. `--format jsonl` returns one complete model object per line.

Each model record should preserve all serialized metadata from `backend.update_engine.list_models()`, including:

- model identity, provider, family, canonical model, and variant fields
- provider origin metadata
- license and commercial-use policy fields
- provenance and derivative-model policy fields
- OpenRouter identifiers, market ranks, and volume fields
- Hugging Face model-card fields
- benchmark scores and source metadata
- use-case approvals and recommendation state
- inference destinations and route approvals
- discovery/update metadata

Do not replace this with a UI-specific summary unless a caller explicitly asks for a reduced projection.

## Supported Runtime Surfaces

- CLI:
  - `python -m backend bootstrap`
  - `python -m backend update`
  - `python -m backend list-models`
  - metadata sync and export commands in `backend/cli.py`
- HTTP:
  - `/` returns the complete model metadata list
  - `/api/models` returns the same model list
  - remaining `/api/*` routes support rankings, updates, audit history, curation, and metadata operations

## Development Rules

- Keep SQLAlchemy Core schema definitions in `backend/database.py`.
- Keep backend response shapes aligned with `backend/models.py`.
- Reuse `backend.update_engine.list_models()` for complete model-list output so CLI and API stay consistent.
- Keep durable manual metadata in repo-backed baseline JSON files when it needs to survive database rebuilds.
- Do not add React, Vite, dashboard export code, or browser-only workflow dependencies back into the default path.

## Verification

Run at least:

```bash
python -m py_compile backend/*.py backend/sources/*.py
python -m unittest backend.test_catalog_export backend.test_rankings
```

Use the inference smoke scripts when changing inference-sync behavior:

```bash
./scripts/test_inference_suite.sh
./scripts/test_inference_sync_smoke.sh
```
