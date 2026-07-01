# Data Ingest Source Map

This task branch only records the LiveBench delta from the broader source map.
The full source map currently lives in the backlog-split task branch until the
operator merges that handoff into `main`.

## LiveBench Adapter

The `LiveBenchAdapter` imports the latest public static LiveBench leaderboard
release from the official LiveBench site artifacts:

- `https://livebench.ai/table_2026_01_08.csv`
- `https://livebench.ai/categories_2026_01_08.json`

The CSV contains one row per model and task score columns. The JSON maps display
categories to those task columns. The adapter derives category averages from the
JSON-defined task groups, derives an overall score from the category averages,
and preserves the original task scores in raw metadata.

The first slice emits these benchmark IDs:

- `livebench_overall`
- `livebench_reasoning`
- `livebench_coding`
- `livebench_agentic_coding`
- `livebench_math`
- `livebench_data_analysis`
- `livebench_language`
- `livebench_instruction_following`

Use-case weights are intentionally unchanged in this first branch. The new
benchmark rows and score history are available for review first; ranking weights
can be adjusted after the source has enough matched model coverage.

## Backlog Status

`LBM-025` is implemented in this branch. The remaining new-source adapters from
the source-map split are still separate work items: BFCL, LiveCodeBench,
BigCodeBench, HELM, tau-bench, RAGTruth, and conditional MTEB.
