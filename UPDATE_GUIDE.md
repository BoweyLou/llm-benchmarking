# How to Update the LLM Dashboard

## Trigger a data refresh

Open a Claude session (Cowork or Claude.ai) with access to this folder, then say:

> **"Update the LLM dashboard with the latest benchmark scores. Use the research in `ai_benchmark_report_2026.md` as your source list, verify scores against the live leaderboards, and rewrite the DATA section of `dashboard.html`."**

Claude will:
1. Visit the Tier 1 benchmark sources (Artificial Analysis, LMSYS Arena, Epoch AI, SWE-bench, etc.)
2. Pull current scores for each tracked model
3. Rewrite the `DATA` block inside `dashboard.html`
4. Append an entry to the `history` array so the change is logged

## What gets updated

- Model scores for all tracked benchmarks
- Any new models that have appeared on Tier 1 leaderboards
- The `meta.last_updated` field and `meta.version`
- A new entry in `history[]` with the date and a brief note

## How to add a new model

Tell Claude:

> **"Add [model name] by [provider] to the dashboard. Research its scores on our tracked benchmarks and add it to the DATA section of `dashboard.html`."**

## How to add a new benchmark

1. First add it to `ai_benchmark_report_2026.md` (so it's documented)
2. Then tell Claude:

> **"Add [benchmark name] to the dashboard as a tracked benchmark. Populate current model scores where available."**

## Viewing the dashboard

Just open `dashboard.html` in any browser — no server needed. Works offline.

To share it with your team, share the HTML file directly (email, Slack, shared drive). Anyone can open it locally.

## Recommended update cadence

| Frequency | Rationale |
|---|---|
| Monthly | Sufficient for most enterprise decision-making |
| After a major model release | GPT-5.x, Gemini, Claude, or Llama releases |
| Before a model procurement decision | Always refresh before committing |

## Notes on data quality

- Scores marked `verified: true` come from official leaderboard pages or primary papers
- `verified: false` means the score is estimated or from a secondary source
- Models with <40% benchmark coverage should not be used for final decisions — trigger an update first
- The benchmark contamination caveat in `ai_benchmark_report_2026.md` applies to all scores here
