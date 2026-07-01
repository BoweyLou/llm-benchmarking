# Data Ingest Source Map

This task branch only records the MMMU companion-metric delta from the broader
source map. The full source map currently lives in the backlog-split task branch
until the operator merges that handoff into `main`.

## MMMU Companion Metrics

`MmmuAdapter` previously imported only validation overall and stored test/pro
overall values as raw metadata. This branch keeps `mmmu` unchanged for validation
overall and adds companion benchmark IDs:

- `mmmu_test`
- `mmmu_pro`

Rows are now imported when validation, test, or pro overall exists. Human expert
and random/frequent baselines remain excluded from model scoring. Source/date/
size and validation/test/pro source metadata stay attached to the raw record.

Use-case weights are intentionally unchanged in this first branch. The companion
scores are available for review before multimodal or document-operation rankings
consume them.

## Backlog Status

`LBM-019` is implemented in this branch. The remaining existing-source wins from
the source-map split are still separate work items: Terminal-Bench harness
evidence, AILuminate detail, Artificial Analysis evaluation pages, and
additional SWE-bench splits.
