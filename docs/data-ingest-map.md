# Data Ingest Map

This page records ingest-source behavior that affects backlog and implementation
choices. It is intentionally compact: detailed source contracts still live in
the adapter code and source spot checks.

## RAGTruth

- Adapter: `backend/sources/ragtruth.py`
- Official page: `https://github.com/ParticleMedia/RAGTruth`
- Official data artifacts:
  - `https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/response.jsonl`
  - `https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/source_info.jsonl`
- Benchmark IDs:
  - `ragtruth_hallucination_rate`
  - `ragtruth_summary_hallucination_rate`
  - `ragtruth_qa_hallucination_rate`
  - `ragtruth_data_to_text_hallucination_rate`
- Source note: the adapter joins response rows to source metadata and aggregates
  only the held-out `test` split by model and task.
- Trust note: scores are official corpus-derived response-level hallucination
  rates, with lower values better. The corpus covers older model families, so
  the signal is useful for historical RAG faithfulness context rather than
  current frontier-model ranking coverage.

## Backlog Status

- `LBM-031` is implemented in this branch.
