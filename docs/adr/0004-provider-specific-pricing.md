# ADR 0004: Provider-Specific Pricing and Provenance

## Status

Accepted

## Context

The catalog stored one input and output price on a model even though the same
model can be bought directly, through OpenRouter, or through several clouds.
Those routes have different tiers, regions, modalities, billing units, and
publication dates. A scalar price could not say which route it described or
where it came from, and cloud sync discarded numeric SKU detail after building
a display label.

## Decision

Pricing is route evidence, not model identity. `model_pricing_offers` records a
provider route, model identifier, tier, region, currency, constraints, official
source, source run, verification time, and lifecycle state.
`model_pricing_components` records the charge type, modality, amount, unit, and
quantity within that offer.

Official direct-provider pages, the OpenRouter Models API, and the existing
cloud price APIs populate these tables. Each source replacement is
transactional. Empty results, a missing configured canary, or a component count
below 70% of the prior successful refresh reject the replacement and retain the
last-known-good rows. Offers become stale after 30 days: they remain in the API
and database for audit, but do not enter the preview or pricing summary.

The legacy model input/output fields remain for one compatibility release.
They prefer fresh standard direct text-token rates, then OpenRouter standard
rates, and are deprecated for new consumers.

## Consequences

- The review preview can show comparable prices by provider with visible source
  and verification time without inventing one global cheapest price.
- Non-token, multimodal, cached, batch, priority, regional, and conditional
  prices retain their native shape.
- Provider-page drift degrades freshness instead of deleting trusted evidence.
- Review catalog schema version 3 and normalized CSV exports expose pricing
  offers and components.
