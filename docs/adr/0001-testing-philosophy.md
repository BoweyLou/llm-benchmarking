# ADR 0001: Testing Philosophy

## Status

Accepted

## Context

Agent-heavy development can produce code that appears plausible without proving behavior. Documentation guardrails reduce drift, but behavior still needs executable evidence.

## Decision

This repository uses a test-first and executable-specification bias.

For new behavior, start with a failing behavior test when practical. Select the outermost reliable automated boundary that proves the behavior: unit, integration, contract, CLI e2e, API e2e, UI e2e, runtime e2e, or another explicit boundary. For bug fixes, capture the bug with a regression test before changing production code. For refactors, add characterization tests around current behavior before restructuring. For public contracts, use contract tests. For logic with large input spaces or invariants, prefer property or invariant tests when they add value.

E2E is required when user-visible, multi-component, stateful, deployment/runtime, browser/UI, or external-tool behavior cannot be proven by a smaller boundary. E2E is not a universal gate; the selected boundary and rationale must be recorded so reviewers can judge whether the evidence matches the risk.

TDD is the default posture, not a dogma. The repository may skip tests for docs-only, comment-only, generated, emergency, or clearly mechanical changes when the PR explains why.

## Consequences

- Reviewers can ask for executable proof when behavior changes.
- Refactors should be smaller and safer.
- Tests become part of the documentation system.
- Receipts record the selected boundary, rationale, and e2e evidence or skip reason when e2e is required.
- Contributors should avoid brittle tests that only assert implementation details.
- The PR should explain test coverage or why tests were not useful.
