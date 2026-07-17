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

Human review has three model-level decisions:

- general approval: `approved`, `not_approved`, or `unreviewed`;
- general recommendation: `recommended`, `legacy_supported`,
  `not_recommended`, or `unrated`. `legacy_supported` means the model remains
  usable when necessary while migration to a recommended option is preferred;
- usage classification: `standard`, `restricted`, `prohibited`, or
  `unclassified`.

Recommendation describes preference or suitability. Usage classification
describes permission and governance. The axes are independent: saving one does
not infer or rewrite the other. `Prohibited` therefore does not imply
`not_recommended`, and `not_recommended` does not imply `prohibited`.

Legacy general `discouraged` values are normalized to `not_recommended`; the
legacy use-case contract remains unchanged and continues to accept
`restricted`. Existing configuration-level reasoning-effort ceilings,
restricted modes, and usage-policy fields also remain unchanged.

The schema migration maps an existing general `restricted` decision to usage
classification `restricted`, copies its notes and timestamp, and resets the
general recommendation to `unrated`. Other rows begin as `unclassified`.

The `/api/review/model-decisions` endpoint saves any supplied model-level
decision fields on the `models` row. It does not create or update model/use-case
decision rows.

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

- Reviewers make one approval, one recommendation, and one usage classification
  per model.
- Reviewers can select all models matching the current filters and confirm one
  general decision for the explicit underlying model-ID set.
- Safe duplicate groups reduce queue noise without hiding ambiguous records or
  changing source data.
- Suggested use cases explain likely fit without implying authorization.
- New databases and upgraded databases gain usage-classification columns.
- Review snapshot schema 4 includes both axes; imports accept schemas 1 through
  4, and older general `restricted` snapshots receive the migration mapping.
- Clean exports expose both axes and suggested-use-case summaries; the
  legacy use-case approval sidecar remains available for audit compatibility.
- Legacy clients continue to work, but new integrations should use
  `/api/review/model-decisions`.
