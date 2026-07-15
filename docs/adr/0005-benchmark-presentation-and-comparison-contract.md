# ADR 0005: Server-Owned Benchmark Presentation and Comparison

## Status

Accepted

## Context

The catalog imports benchmark results whose raw numbers have different meanings.
`73.14` may be percentage points, a fraction, an Elo rating, latency, cost, word
error rate, or another metric. Direction also varies: higher retrieval quality
is better, while lower latency, cost, and error rates are better. Showing only
the number makes it impossible to interpret consistently or compare with other
models in the database.

Client-side benchmark-name heuristics would duplicate policy across the review
UI, APIs, and exports, and would silently drift when a source or benchmark is
added. A global leaderboard would create a different error: rows can use
different model roles, task sets, dataset revisions, splits, methodologies,
agent scaffolds, and evaluation configurations. Source aliases can also make one
canonical model appear multiple times or cause complementary evidence to be
discarded.

Benchmark position is contextual evidence. It must remain distinct from the
weighted use-case ranking score and from a human production-approval decision.

## Decision

The backend owns the authoritative benchmark definitions and one typed policy
for every active definition—92 at the time of this decision. Bootstrap upserts
that code-owned set and deactivates database definitions retired from code while
retaining their historical scores. A contract test fails if an active benchmark
has no policy or more than one policy. JavaScript and export code consume this
contract and do not infer semantics from benchmark names.

Each policy declares the metric kind, unit, decimal precision, whether higher or
lower is better, valid range, compatible model roles, evidence-count label, and
comparison dimensions. Supported presentation includes percentage points,
fractions rendered as percentages where declared, Elo, grades, indices,
currency with its price basis, latency, throughput, counts, word error rate,
real-time factors, and task aggregates. Raw stored values do not change;
formatted display values are additive. Validation is policy-specific, so the
0–100 SWE-bench range does not become an incorrect global bound for WER.

Comparison is calculated over canonical review entities and evaluation
configurations. Aliases are deduplicated and complementary evidence is merged.
When observations conflict for the same canonical evaluation, selection is
deterministic: verified primary, verified secondary, verified manual, then
equivalent unverified sources; remaining ties use collection date, evidence
depth, and stable model ID. The numerically most favorable result is never the
selection rule.

Every valid score may receive two cohorts:

- **Strict/comparable:** same benchmark, compatible model role, evaluation
  configuration, and every available policy-declared evaluation-signature
  dimension. Signature dimensions include data such as MTEB task set and
  dataset revision/split, Arena category and methodology, or system scaffold.
- **Broad context:** same benchmark and compatible model role. When strict
  dimensions differ or are unavailable, this cohort carries an explicit mixed
  configurations/task sets warning.

For each cohort the server calculates competition rank as `1 + number of better
results`, respecting metric direction, and reports tie count, cohort size, a
tie-aware percentile with the best position at 100 and the worst at 0, plus
min, p10, p25, median, p75, p90, and max. Database coverage is the number of
valid scored canonical models divided by active compatible canonical models.
Rank, tie, percentile, and distribution calculations use stored normalized
numeric values before display rounding or unit conversion; equal rendered
strings do not create a tie. Every comparison carries an `as_of` timestamp.

Cohort size limits the presentation:

- At least 20 models: rank, percentile, distribution track, and a descriptive
  position band.
- 5–19 models: rank and percentile with `Small cohort`; no position band.
- 2–4 models: rank with `Very small cohort`.
- One model: `Only scored comparable model`.
- Invalid, non-finite, or out-of-policy values: excluded from cohorts and marked
  `Data check needed`.

Position bands are descriptive database positions, not quality verdicts:
Leading at or above the 90th percentile, Strong at or above the 75th, Mid-pack
at or above the 25th, Below most at or above the 10th, and Trailing below the
10th. Source verification is shown separately from evidence depth and does not
claim independent reproduction or production approval.

One cached comparison index serves catalog, review, ranking, and export
generation and is invalidated after benchmark or compatible-catalog updates.
This prevents a database query per model or benchmark card.

`BenchmarkOut` exposes presentation metadata and aggregate distributions. Every
non-null `ScoreOut`, including configured scores, exposes a formatted `display`
object and a `comparison` object with status, strict and broad cohorts, coverage,
structured evidence depth, warnings, and `as_of`. Status is `comparable`,
`limited`, `unavailable`, or `invalid`. The root catalog,
`/api/models`, `/api/review/catalog`, and ranking breakdowns carry the compact
form; `/api/benchmarks` carries the complete policy. Review catalog schema
version 4 is additive. Stored review decisions and review snapshot schema
version 3 remain unchanged, so no database migration is required.

JSON and JSONL retain nested comparison objects. Normalized score CSV flattens
strict and broad position, distributions, coverage, evidence, status, and
warnings. Clean model CSV summarizes comparable, limited, leading, and missing
relevant results; raw and banking bundles retain the fields appropriate to their
existing shape. Because the compatibility score view may expose the latest
configured observation in both `scores` and `score_configurations`, review
cards, model-level counts, and normalized score rows suppress that exact
duplicate. Distinct configurations and policy-declared evaluation signatures
remain separate evidence.

The LLM Model Tool labels the section `Benchmark position` and explains that it
compares with similar scored models in this database. It shows four Key
benchmarks selected by active use-case relevance or role defaults, then
benchmark tier and provenance—not by highest percentile. The complete benchmark
list is expandable and grouped by category, with missing relevant evidence
separate. Missing evidence uses the active use case's positively weighted and
required benchmarks, falling back to role defaults only when no relevant IDs
exist in that context. Cards include textual alternatives to visual tracks,
semantic disclosure controls, keyboard focus, and no color-only meaning. Internal-view
benchmarks suppress comparison; roles with no imported benchmarks receive an
honest empty state.

MTEB source collection probes every listed model and every eligible
retrieval/reranking task file without a per-model or global task cap. Confirmed
`404`/`410` paths are retained in run coverage as stale upstream inventory, not
silently counted as results. Multiple accessible upstream revisions are resolved
to one coherent deterministic revision set; revision, split, and subset metadata
participate in strict signatures. Fetches use bounded concurrency with retry and
backoff. An unresolved task-file or RTEB Finance page makes the source run fail
closed before replacement. When every RTEB dataset-viewer failure is transient,
the adapter may instead consume a size-bounded, revision-pinned official Parquet
snapshot, but only if all seven configured tasks are complete. This preserves
the prior MTEB scores rather than publishing a partial aggregate.

## Consequences

Benchmark formatting and comparison semantics are consistent across every
consumer, and new benchmarks cannot become active without declaring their
meaning. Reviewers gain a useful reference point while retaining the distinction
between comparable evidence, broad context, weighted ranking, provenance, and
approval.

API responses and exports become larger, and cohort positions may change after
any data refresh. Consumers must therefore treat comparison fields as an
`as_of` snapshot and tolerate additive fields. The shared cache and explicit
invalidation are required to keep response generation bounded.

Source adapters must provide structured evaluation metadata where available.
When that metadata is missing, the system reports limited broad context instead
of inventing strict comparability. Existing invalid bounded observations remain
excluded until a targeted source refresh replaces them.
