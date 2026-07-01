# Data Ingest Source Map

This task branch records the Artificial Analysis IFBench delta from the broader
source map. The full source map currently lives in the backlog-split task branch
until the operator merges that handoff into `main`.

## Artificial Analysis IFBench

The existing `ArtificialAnalysisAdapter` remains focused on the model leaderboard
and continues to emit:

- `aa_intelligence`
- `aa_speed`
- `aa_cost`

This branch adds `ArtificialAnalysisIfbenchAdapter` as a separate source run for
the public Artificial Analysis IFBench evaluation page. Keeping it separate means
an IFBench page-shape break does not fail the existing model-leaderboard ingest.

The new adapter parses the page's `application/ld+json` datasets and emits:

- `aa_ifbench`
- `aa_ifbench_output_tokens`
- `aa_ifbench_cost`
- `aa_ifbench_time`

The raw record keeps the source page, model details URL, source dataset names,
score fraction, score percent, answer/reasoning token components, cost
components, total cost per task, and time per task. Use-case weights are
intentionally unchanged in this first branch.

## Backlog Status

`LBM-022` is implemented in this branch for one additional stable Artificial
Analysis evaluation page. The remaining existing-source win from the source-map
split is additional SWE-bench split coverage.
