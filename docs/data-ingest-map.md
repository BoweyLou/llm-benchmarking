# Data Ingest Map

This page records ingest-source behavior that affects backlog and implementation
choices. It is intentionally compact: detailed source contracts still live in
the adapter code and source spot checks.

## tau-bench

- Adapter: `backend/sources/taubench.py`
- Official page: `https://taubench.com/`
- Official data artifacts:
  - `https://sierra-tau-bench-public.s3.amazonaws.com/submissions/manifest.json`
  - `https://sierra-tau-bench-public.s3.amazonaws.com/submissions/{submission_id}/submission.json`
- Benchmark IDs:
  - `taubench_text_mean`
  - `taubench_text_airline`
  - `taubench_text_retail`
  - `taubench_text_telecom`
  - `taubench_text_banking_knowledge`
  - `taubench_voice_mean`
  - `taubench_voice_airline`
  - `taubench_voice_retail`
  - `taubench_voice_telecom`
- Source note: the adapter reads the current text and voice arrays from the
  official submission manifest. Legacy submissions are intentionally excluded
  from normalized scores.
- Trust note: normalized scores are secondary agent-system evidence. Standard
  single-model submissions produce per-domain pass^1 scores; complete domain
  sets also produce text or voice means. Custom, cascaded, and multi-provider
  submissions remain raw source records with skipped aggregate resolution.

## Backlog Status

- `LBM-030` is implemented in this branch.
