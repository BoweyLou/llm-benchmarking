# Data Ingest Source Map

This task branch only records the LiveCodeBench delta from the broader source
map. The full source map currently lives in the backlog-split task branch until
the operator merges that handoff into `main`.

## LiveCodeBench Adapter

The `LiveCodeBenchAdapter` imports the official LiveCodeBench code-generation
leaderboard JSON:

- `https://livecodebench.github.io/performances_generation.json`

The adapter mirrors the public leaderboard default window: when at least 13 date
marks exist, the start date is `date_marks[15]`; otherwise it falls back to
`date_marks[4]`. Scores are one-decimal mean `pass@1` values across the selected
window, matching the public page behavior.

The first slice emits one benchmark ID:

- `livecodebench_codegen`

Raw metadata keeps the source window, problem count, difficulty-level means,
platform counts, model release date, model link/style, artifact URL, and artifact
SHA-256. Models released during or after the selected window are still imported
but flagged with `contaminated_by_window` so ranking policy can decide how to
use them later.

Use-case weights are intentionally unchanged in this first branch. The new score
history is available for review first; coding weights can be adjusted after
coverage and contamination behavior are inspected.

## Backlog Status

`LBM-027` is implemented in this branch. The remaining new-source adapters from
the source-map split are still separate work items: BigCodeBench, HELM,
tau-bench, RAGTruth, and conditional MTEB.
