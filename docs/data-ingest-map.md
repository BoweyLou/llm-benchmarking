# Data Ingest Source Map

This task branch only records the Vectara companion-metric delta from the
broader source map. The full source map currently lives in the backlog-split
task branch until the operator merges that handoff into `main`.

## Vectara Companion Metrics

`VectaraHallucinationAdapter` already parsed hallucination rate, factual
consistency, answer rate, and average summary length from the public Vectara
hallucination leaderboard. This branch keeps the existing `rag_groundedness`
factual-consistency benchmark and emits two additional score candidates from the
same raw row:

- `rag_hallucination_rate` with `higher_is_better = 0`
- `rag_answer_rate` with `higher_is_better = 1`

Average summary length remains raw metadata because it is evidence context, not
an obvious suitability score. The README and benchmark descriptions explicitly
keep these metrics scoped to grounded summarization faithfulness and answer
coverage; they are not retrieval relevance signals.

Use-case weights are intentionally unchanged in this first branch. The companion
scores are available for review before the RAG preview ranking consumes them.

## Backlog Status

`LBM-017` is implemented in this branch. The remaining existing-source wins from
the source-map split are still separate work items: FaithJudge task-level
metrics, MMMU variants, Terminal-Bench harness evidence, AILuminate detail,
Artificial Analysis evaluation pages, and additional SWE-bench splits.
