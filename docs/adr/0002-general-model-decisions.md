# ADR 0002: General Model Decisions and Suggested Use Cases

## Status

Accepted

## Context

The review workbench stored approval and manual recommendation independently
for every model/use-case pair. That contract spread into filters, bulk actions,
exports, snapshot behavior, recommendation precedence, and the inspector. A
reviewer who only needed to decide whether a model was generally suitable had
to understand several overlapping states before acting.

The repository already had a durable general model approval. Generated
recommendation proposals also already contain weighted metric score,
confidence, reasons, warnings, and controls for each use case.

## Decision

Human review has two model-level decisions:

- general approval: `approved`, `not_approved`, or `unreviewed`;
- general recommendation: `recommended`, `restricted`, `not_recommended`, or
  `unrated`. Legacy general `discouraged` values are normalized to
  `not_recommended`; the legacy use-case contract remains unchanged.

The `/api/review/model-decisions` endpoint saves either or both decisions on the
`models` row. It does not create or update model/use-case decision rows.

Use cases are read-only evidence. Positive generated proposals are exposed as
`suggested_use_cases`, ordered by metric fit score and confidence. Each
suggestion carries reasons, warnings, and required controls, but no human
approval or recommendation status.

Existing `model_use_case_approvals` data and write routes remain available as a
legacy compatibility/audit surface. Existing rows are not rolled up into the
new general recommendation because multiple use-case decisions can conflict.
The current review UI does not read or write the legacy decision surface.

The review queue may combine source records for presentation only when their
normalized display name, non-empty canonical model ID, and model role agree.
The database rows are never merged or deleted. A decision on a combined row is
written explicitly to every represented model ID. Same-name rows that do not
meet all three conditions stay separate.

## Consequences

- Reviewers make one approval and one recommendation per model.
- Reviewers can select all models matching the current filters and confirm one
  general decision for the explicit underlying model-ID set.
- Safe duplicate groups reduce queue noise without hiding ambiguous records or
  changing source data.
- Suggested use cases explain likely fit without implying authorization.
- New databases and upgraded databases gain general recommendation columns.
- Review snapshots include general recommendations while version 1 imports
  remain supported.
- Clean exports expose general decisions and suggested-use-case summaries; the
  legacy use-case approval sidecar remains available for audit compatibility.
- Legacy clients continue to work, but new integrations should use
  `/api/review/model-decisions`.
