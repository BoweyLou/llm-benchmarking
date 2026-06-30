# How to Update the LLM Metadata List

## Trigger a Data Refresh

From the project root:

```bash
source .venv/bin/activate
python -m backend update
```

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
