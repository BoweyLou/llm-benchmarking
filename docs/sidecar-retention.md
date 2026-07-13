# Sidecar Retention

repo-contract-kit sidecar state is local operator evidence. It is outside the target repository and is never deleted by default.

## Default Policy

- Default retention window: 90 days for routine receipts, task packets, review artifacts, feedback, and automation handoffs.
- Privacy labels: `public-ok`, `internal`, `private-local`, `sensitive-local`.
- Default label: `private-local`.
- Hosted model sharing: do not upload sidecar receipts, feedback, private context, or task packets to a hosted model unless a human explicitly approves the specific content.
- Purge behavior: `kit retention --json` only previews candidates. It does not delete files.

## Safe Archive Guidance

Archive receipts that support release decisions, migration proof, rollback decisions, or accepted findings before purging local state. Keep enough evidence to reconstruct why a task was selected, which mode was used, what validation ran, and what human approval existed.

## Purge Preview

Use `kit retention --json` to list sidecar directories, privacy labels, retention windows, and candidate counts. Review the preview manually before deleting anything with external tools.

## Supervised Learning Events

When an installed enabled target-owned supervised-learning policy is present,
`kit learn event record` writes a schema-valid approved event only to
`<sidecar>/learning/events/`. It requires explicit bounded CLI input and
`--approved`; rejected, unapproved, invalid, disabled, and unenrolled attempts
write no sidecar, target, or global state. `kit learn event list` and `kit
calibration` are read-only; calibration reports an explicitly derived and
caveated count. Do not copy or reinterpret the separate `kit feedback` ledger,
conversations, or thread history as learning records.

## Approved Learning Context

`kit learn context build --decision-id <dec-id>` writes a context only after
the enabled target-owned policy accepts an existing schema-valid local approved
decision and its linked valid approved proposal. The sidecar context contains
only stable decision/proposal IDs, proposal classification/scope/recommended
change, privacy label, retention expiry, and the no-execution guarantee. It
does not contain raw event/evidence, feedback, rationale, decider, follow-up,
or conversation content.

`kit learn context list` and `make agent-context-bundle` read only contexts
whose decision/proposal lineage still validates for this repository. Bundle
contexts are bounded sidecar-only guidance, not target instructions. `kit
task-packet --learning-decision <dec-id>` may retain validated approved
decision IDs as packet lineage without changing target task files or receipt
mechanics. `kit retention --json` reports learning and upstream-candidate counts and context expiry
preview only; Kit has no learning deletion command in this phase.

`kit learn thread-summary import --input <file> --approved` may write one
derived event under `<sidecar>/learning/events/` only from a strict bounded,
explicitly redacted aggregate file while the target policy is active and
supervised. It does not read runtime history, transcripts, feedback, or raw
events, and it never contacts a network. Invalid, unapproved, unredacted,
oversized, private, or unsupported files write nothing.

`kit learn upstream export` writes a portable candidate under
`<sidecar>/learning/upstream-candidates/` only after a human confirms redaction
and selects `public-ok` or `internal` for a currently approved decision and
linked proposal. Candidate records contain no raw summary/event/evidence/
feedback/context content or target path. `kit learn upstream list`, `kit learn
upstream reconcile`, and `kit learn evaluate` are read-only and skip stale or
tampered candidates whose current decision/proposal lineage no longer proves
approval. Reconcile never performs `kit self update`, source update, target
update, or deletion.
