# How to Update the LLM Metadata List

## Trigger a Data Refresh

From the project root:

```bash
source .venv/bin/activate
python -m backend update
```

`python -m backend bootstrap` is local-only: it creates or repairs schema state,
seeds reference rows, and reapplies tracked baselines. It does not call
OpenRouter, Hugging Face, cloud pricing APIs, or other external metadata
services. Run an explicit update or metadata sync command when the list needs a
network refresh.

Schema repairs are recorded in SQLite `schema_migrations`. Future schema changes
should add an idempotent entry to `SCHEMA_MIGRATIONS` in `backend/database.py`
so existing database upgrades are auditable.

To refresh only selected benchmark adapters:

```bash
python -m backend update --benchmarks aa_intelligence swebench_verified
```

## Export the Current List

Print the complete active model metadata list:

```bash
python -m backend list-models
```

Write JSON to a file:

```bash
python -m backend list-models --output output/model-metadata.json
```

Write JSON Lines:

```bash
python -m backend list-models --format jsonl --output output/model-metadata.jsonl
```

## What Gets Updated

- model scores for all refreshed benchmarks
- newly discovered models from tracked source catalogs
- OpenRouter market and ranking metadata when available
- Hugging Face model-card metadata when `model-card-sync` is run
- update history, source-run detail, and audit output

OpenRouter market/ranking pages are optional enrichment sources. If their page
shape changes and expected payloads such as `rankingData` are absent, the update
log records a non-fatal `openrouter_market` warning while unrelated benchmark
ingestion can still complete.

Only one update runs at a time. If an update is already `running`, another CLI
or API update request returns the active update log id instead of starting a
second worker. On startup, any update left `running` by a process crash is marked
`failed` with an interruption error in the update log.

## How to Add Manual Metadata

Use the existing backend commands and baselines:

```bash
python -m backend model-card-sync
python -m backend model-license-sync
python -m backend provider-origin-export
python -m backend model-curation-export
```

Manual curation should be written back to the tracked baseline JSON files when it needs to survive database rebuilds.

## Recommended Update Cadence

| Frequency | Rationale |
|---|---|
| Monthly | Sufficient for most enterprise decision-making |
| After a major model release | Refreshes new models and changed leaderboard positions |
| Before a model procurement decision | Always refresh before committing |

## Notes on Data Quality

- Scores marked `verified: true` come from official leaderboard pages or primary papers.
- `verified: false` means the score is estimated or from a secondary source.
- Models with sparse benchmark coverage should not be used for final decisions without checking the latest source state.
- The benchmark contamination caveat in `ai_benchmark_report_2026.md` applies to all scores.
- `python -m backend model-card-audit --json` includes a `quality_gate` object for the `commercial_production` profile. Blockers mean affected models should not be approved for commercial or production use until the remediation row is addressed; warnings require review but do not automatically block the whole catalog; backlog-only rows are enrichment work that can be scheduled without stopping updates.
- Quality-gate remediation rows are generated from explicit thresholds. Missing license metadata, generic license markers, and incomplete derivative provenance must be zero for commercial/production approval. Missing license URLs, missing metadata sources, missing Hugging Face model-card links, and suspicious extraction values must be reviewed. Missing rich text, external links, base-model lineage, or supported languages are backlog-only cleanup.
