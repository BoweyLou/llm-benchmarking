# Design QA: General Model Decisions

- Source visual truth: `/Users/yannickbowe/.codex/generated_images/019f59f8-ead5-77f3-8ce2-e977cb152398/exec-b46eac6a-21b4-4822-a61d-6b5848f057ce.png`
- Browser-rendered implementation: `/tmp/lbm-general-model-decisions-review-top-final.png`
- Full-view comparison: `/tmp/lbm-general-model-decisions-comparison-final.png`
- Viewport: browser capture 1487 x 720; source normalized to the same height for comparison
- State: Claude Opus 4.6 selected; general approval `approved`; general recommendation `restricted`; metric evidence loaded

The source visual predates the approved contract change and still contains a
single use-case decision. It is used as the visual hierarchy, density, palette,
and guided-review reference. The user-approved general-decision contract is the
interaction source of truth.

## Findings

No actionable P0, P1, or P2 findings remain.

- Fonts and typography: system sans-serif hierarchy, optical weights, compact
  metadata, and decision labels remain consistent with the source direction.
- Spacing and layout rhythm: the three-column queue/evidence/detail structure,
  section spacing, borders, and compact cards preserve the selected concept's
  density. The decision is visible above the fold after performance evidence.
- Colors and visual tokens: navy brand, blue active state, green approval,
  amber restriction, neutral panels, and border tokens match the source family.
- Image quality and asset fidelity: neither source nor implementation requires
  product imagery or non-standard icons; no placeholder or substitute assets
  are present.
- Copy and content: the UI consistently calls the states general approval and
  general recommendation, and explicitly says suggested use cases are read-only
  evidence rather than approvals or recommendations.

Focused-region comparison was not required because the full-view composite at
original output resolution keeps the metrics, decision controls, state colors,
and copy legible.

## Comparison History

1. Initial browser capture: `/tmp/lbm-general-model-decisions-review.png`
   - Finding: alphabetical queue ordering opened a model with no suggested use
     cases, weakening the evidence-first workflow.
   - Fix: ordered the queue by positive suggested-use-case count and fit score.
2. Second capture: `/tmp/lbm-general-model-decisions-review-v2.png`
   - Finding: the detail panel retained the pre-sort model while the visible
     queue started with a different model.
   - Fix: selected the first model from the sorted, filtered queue.
3. Third capture: `/tmp/lbm-general-model-decisions-review-v3.png`
   - Finding: six expanded suggestions pushed the primary decision below the
     fold.
   - Fix: collapsed suggestions to the top two by default and moved the general
     decision directly after performance evidence.
4. Final evidence: `/tmp/lbm-general-model-decisions-review-top-final.png`
   - Result: selected queue row, metrics, approval, recommendation, rationale,
     and save path are visible without navigating multiple views.

## Interaction and Runtime Checks

- Admin-token dialog opened and stored the token for the tab.
- General approval and recommendation controls selected independently.
- Decision rationale accepted input.
- `Save and next` persisted the general decision and advanced to the next model.
- SQLite verification confirmed the model-level `approved` + `restricted`
  result and shared rationale.
- Browser console errors/warnings checked after load and save: none.

## Follow-up Polish

- P3: expose the full warning/control text in an optional suggestion detail
  disclosure if reviewers later need more than the compact counts.

final result: passed
