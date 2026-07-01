# Data Ingest Source Map

This task branch only records the FaithJudge task-metric delta from the broader
source map. The full source map currently lives in the backlog-split task branch
until the operator merges that handoff into `main`.

## FaithJudge Task Metrics

`FaithJudgeAdapter` already parsed the aggregate FaithJudge hallucination rate
and task-level columns from the public README table. This branch keeps the
existing aggregate `rag_task_faithfulness` benchmark and emits four additional
lower-is-better task benchmark IDs:

- `faithjudge_faithbench_summarization`
- `faithjudge_ragtruth_summarization`
- `faithjudge_ragtruth_question_answering`
- `faithjudge_ragtruth_data_to_text`

Each metric preserves the source rank, organization, parameters, model URL, and
full aggregate/task-rate metadata on the raw record. The benchmark descriptions
keep these scoped to hallucination and RAG faithfulness; they are not retrieval
relevance signals.

Use-case weights are intentionally unchanged in this first branch. The task
scores are available for review before the RAG preview ranking consumes them.

## Backlog Status

`LBM-018` is implemented in this branch. The remaining existing-source wins from
the source-map split are still separate work items: MMMU variants,
Terminal-Bench harness evidence, AILuminate detail, Artificial Analysis
evaluation pages, and additional SWE-bench splits.
