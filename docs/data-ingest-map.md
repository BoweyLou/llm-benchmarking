# Data Ingest Source Map

This task branch records the AILuminate detail-evidence delta from the broader
source map. The full source map currently lives in the backlog-split task branch
until the operator merges that handoff into `main`.

## AILuminate Detail Evidence

`AILuminateAdapter` continues to emit the existing `ailuminate` score using the
same best public-grade policy: higher grade wins first, then AI Systems, then
`en_us` when scores tie. This branch adds companion benchmark IDs for the stable
public dimensions already present in the source pages:

- `ailuminate_en_us`
- `ailuminate_fr_fr`
- `ailuminate_ai_systems`
- `ailuminate_bare_models`

The public page exposes a coarse grade and `data-risk` ordinal. The adapter keeps
that ordinal in raw records and candidate metadata, but this branch does not
invent category-level risk scores from the public grade page. Detail-page risk
breakdowns remain future work unless the source surface is stable enough to test.

Use-case weights are intentionally unchanged in this first branch. The companion
scores are available for review before safety/compliance rankings consume them.

## Backlog Status

`LBM-021` is implemented in this branch. The remaining existing-source wins from
the source-map split are still separate work items: Artificial Analysis
evaluation pages and additional SWE-bench splits.
