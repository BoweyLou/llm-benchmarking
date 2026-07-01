# Data Ingest Source Map

This task branch only records the BFCL delta from the broader source map. The
full source map currently lives in the backlog-split task branch until the
operator merges that handoff into `main`.

## BFCL Adapter

The `BfclAdapter` imports the official Berkeley Function Calling Leaderboard V4
overall CSV:

- `https://gorilla.cs.berkeley.edu/data_overall.csv`
- `https://gorilla.cs.berkeley.edu/leaderboard.html`

The first slice emits one benchmark ID:

- `bfcl_overall`

The adapter stores the official `Overall Acc` as the catalog score and preserves
function-calling component evidence in metadata: non-live AST, live AST,
multi-turn, web search, memory, relevance/irrelevance detection, format
sensitivity, cost, latency, organization, license, model link, evaluation mode,
page update date, BFCL eval commit, and BFCL eval package version.

Evaluation mode suffixes such as `(FC)` and `(Prompt)` are stripped from the raw
model name used for catalog resolution and retained as `evaluation_mode`
metadata. This avoids creating separate catalog identities solely from BFCL
prompting/function-calling mode labels.

## Backlog Status

`LBM-026` is implemented in this branch. Additional BFCL category-level
benchmark IDs can be added later if ranking needs distinguish executable,
static, multi-turn, web-search, or memory dimensions separately.
