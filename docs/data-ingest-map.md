# Data Ingest Source Map

This task branch records the Terminal-Bench harness-evidence delta from the
broader source map. The full source map currently lives in the backlog-split task
branch until the operator merges that handoff into `main`.

## Terminal-Bench Harness Evidence

`TerminalBenchAdapter` continues to emit the existing `terminal_bench` score as a
model-capability signal from the best verified single-model submission. The score
is intentionally not converted into a separate agent leaderboard in this branch.

Terminal-Bench raw records now carry explicit agent-system evidence markers in
their stored metadata:

- `agent`
- `agent_name`
- `agent_version`
- `agent_organization`
- `integration_method`
- `leaderboard_date`
- `stderr`
- `rank`
- `single_model`
- `aggregate_submission`
- `agent_system_evidence`
- `score_scope`

Single-model rows stay resolved to their model so current ranking compatibility
is unchanged. Aggregate or multi-model rows are retained in `raw_source_records`
with `resolution_status=skipped_aggregate`, making harness evidence queryable
without creating misleading model scores.

## Backlog Status

`LBM-020` is implemented in this branch. The remaining existing-source wins from
the source-map split are still separate work items: AILuminate detail,
Artificial Analysis evaluation pages, and additional SWE-bench splits.
