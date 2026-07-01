# Data Ingest Map

This page records ingest-source behavior that affects backlog and implementation
choices. It is intentionally compact: detailed source contracts still live in
the adapter code and source spot checks.

## HELM Capabilities

- Adapter: `backend/sources/helm_capabilities.py`
- Official page: `https://crfm.stanford.edu/helm/capabilities/latest/`
- Official data artifacts:
  - `https://storage.googleapis.com/crfm-helm-public/capabilities/benchmark_output/releases/v1.15.0/summary.json`
  - `https://storage.googleapis.com/crfm-helm-public/capabilities/benchmark_output/releases/v1.15.0/schema.json`
  - `https://storage.googleapis.com/crfm-helm-public/capabilities/benchmark_output/releases/v1.15.0/groups/core_scenarios.json`
- Benchmark IDs:
  - `helm_capabilities_mean`
  - `helm_capabilities_mmlu_pro`
  - `helm_capabilities_gpqa`
  - `helm_capabilities_ifeval`
  - `helm_capabilities_wildbench`
  - `helm_capabilities_omni_math`
- Source note: the adapter reads the official Capabilities release configured
  by the Stanford CRFM static app and extracts the `core_scenarios` Accuracy
  table.
- Trust note: scores are HELM-published primary benchmark evidence. Raw rows
  preserve release, release date, model metadata, metric headers, metric
  descriptions, and run-spec names for traceability.

## Backlog Status

- `LBM-029` is implemented in this branch.
