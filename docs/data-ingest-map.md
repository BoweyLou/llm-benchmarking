# Data Ingest Map

This page records ingest-source behavior that affects backlog and implementation
choices. It is intentionally compact: detailed source contracts still live in
the adapter code and source spot checks.

## SWE-bench

- Adapter: `backend/sources/swebench.py`
- Official data artifact: `https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json`
- Official page family: `https://www.swebench.com/`
- Benchmark IDs:
  - `swebench_verified`
  - `swebench_full`
  - `swebench_lite`
  - `swebench_multilingual`
  - `swebench_multimodal`
- Source note: the official JSON uses the `Test` leaderboard name for the
  website's Full board. The adapter stores that split as `swebench_full` and
  preserves the original source leaderboard name in raw metadata.
- Trust note: SWE-bench scores are still treated as secondary agent-system
  evidence. The adapter keeps the best single-model submission per model and
  split, preserves submission and scaffold metadata, and does not alter ranking
  weights.

## Backlog Status

- `LBM-023` is implemented in this branch.
