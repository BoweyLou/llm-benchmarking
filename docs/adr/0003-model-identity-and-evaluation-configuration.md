# ADR 0003: Separate Model Identity, Evaluation Configuration, and Usage Policy

## Status

Accepted

## Context

Benchmark sources can publish several observations for one provider model by
changing reasoning effort or a product mode. Treating those labels as model
names caused GPT-5.6 Sol, Terra, and Luna to be renamed after whichever source
arrived first. A later best-score reduction then discarded sibling effort
observations. Third-party catalog aliases also appeared as duplicate models.

Reviewers still need to approve a model generally while limiting expensive or
more autonomous configurations, such as allowing Sol through High while
restricting Ultra.

## Decision

Provider model identity, evaluation configuration, and usage policy are three
separate concepts:

- GPT-5.6 catalog identity is exactly Sol, Terra, or Luna.
- Score observations may carry a `configuration_key` and
  `configuration_value`. Reasoning efforts survive independently; the legacy
  flat score view chooses a deterministic representative.
- A model-level usage policy may set a reasoning-effort ceiling and restrict
  the `pro` or `ultra` product modes. It extends the general model decision and
  does not create use-case approvals.

Official curated/provider metadata has precedence over marketplace enrichment.
Product modes and reasoning efforts do not enter the active catalog as
provisional models. Legacy malformed rows are retained as inactive deprecated
audit records while their source evidence is reattached to the stable base
identity. Ambiguous legacy scores remain unconfigured rather than being
mislabelled from an unreliable row name.

## Consequences

- All six GPT-5.6 effort observations per tier can coexist.
- Rankings and existing consumers retain one deterministic flat score per
  model and benchmark.
- Reviewers can express configuration restrictions without returning to
  per-use-case decisions.
- Snapshot schema version 3 and model/CSV APIs include usage policy fields.
- Source adapters must preserve configuration-bearing labels before generic
  name normalization or best-score selection.
