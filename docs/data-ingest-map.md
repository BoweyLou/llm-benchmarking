# Data Ingest Map

This page records ingest-source behavior that affects backlog and implementation
choices. It is intentionally compact: detailed source contracts still live in
the adapter code and source spot checks.

## BigCodeBench

- Adapter: `backend/sources/bigcodebench.py`
- Official page: `https://bigcode-bench.github.io/`
- Official data artifacts:
  - `https://bigcode-bench.github.io/results.json`
  - `https://bigcode-bench.github.io/results-hard.json`
- Benchmark IDs:
  - `bigcodebench_full`
  - `bigcodebench_full_instruct`
  - `bigcodebench_full_complete`
  - `bigcodebench_hard`
  - `bigcodebench_hard_instruct`
  - `bigcodebench_hard_complete`
- Source note: the Full board is exposed as `results.json`; the Hard subset is
  exposed as `results-hard.json`. The page's Average view is calculated only
  when both instruct and complete values are present.
- Trust note: scores are official BigCodeBench Pass@1 leaderboard values using
  greedy decoding. Raw rows preserve model link, open-data level, size, active
  parameter count, date, prompted, MoE, and prefill fields.

## Backlog Status

- `LBM-028` is implemented in this branch.
