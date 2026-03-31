# LLM Benchmarking Intelligence System — Agent Build Specification

## Context for the agent

This spec is self-contained. You have access to a working folder containing:
- `ai_benchmark_report_2026.md` — research document listing all benchmark sources with descriptions and URLs
- `dashboard.html` — a working prototype single-file React app (use this as the frontend reference, do not discard it)
- `UPDATE_GUIDE.md` — update instructions for end users

Your job is to replace the static `dashboard.html` prototype with a full, programmatic system. Everything below defines that system. Read the entire spec before writing a single line of code.

---

## 1. Goal

Build an internal web application that:
1. Stores LLM benchmark scores in a local database with full history
2. Automatically fetches updated scores from live leaderboard sources on demand
3. Serves a React dashboard (adapted from the prototype) via a local HTTP server
4. Allows internal users to look up models, rank by use case, compare side-by-side, and track score changes over time

This is an **internal tool**, not a public product. Optimise for reliability and maintainability over scale. One person triggering an update is the expected concurrency.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                   User's Browser                    │
│              React SPA (port 5173 dev /             │
│               served from /frontend)                │
└──────────────────────┬──────────────────────────────┘
                       │ REST API calls
┌──────────────────────▼──────────────────────────────┐
│              FastAPI Backend (port 8000)             │
│  /api/models    /api/benchmarks    /api/scores       │
│  /api/rankings  /api/update        /api/history      │
└──────────┬───────────────────────┬──────────────────┘
           │                       │
┌──────────▼──────┐    ┌───────────▼──────────────────┐
│   SQLite DB     │    │       Scraper Engine          │
│  (data/db.sqlite│    │  Tiered: static → Playwright  │
│   persists on   │    │  → web search → manual flag   │
│   disk)         │    └──────────────────────────────┘
└─────────────────┘
```

**Single machine deployment. No cloud. No auth required.**

---

## 3. Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python 3.11+ with FastAPI | Fast to build, async, good ecosystem |
| Database | SQLite via SQLAlchemy 2.0 | Zero-infra, file-based, sufficient for this scale |
| Scraping (static) | httpx + BeautifulSoup4 | Lightweight for simple HTML pages |
| Scraping (dynamic) | Playwright (async) | Handles JS-heavy SPAs; more reliable than Selenium |
| Web search fallback | DuckDuckGo search via `duckduckgo-search` library | Free, no API key required |
| Frontend | React 18 + Vite + Tailwind CSS | Adapt the existing prototype; Vite for fast dev |
| Containerisation | Docker + docker-compose | One-command startup for internal deployment |

Do **not** use an ORM that requires migrations for simple schema changes. Use SQLAlchemy Core (not ORM) with explicit `CREATE TABLE IF NOT EXISTS` statements in an `init_db()` function.

---

## 4. File Structure

```
llm-benchmarking/
├── backend/
│   ├── main.py                  # FastAPI app entrypoint
│   ├── database.py              # SQLAlchemy setup, init_db(), schema
│   ├── models.py                # Pydantic response models
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseScraper abstract class
│   │   ├── artificial_analysis.py
│   │   ├── epoch_ai.py          # GPQA Diamond + Terminal-Bench
│   │   ├── swebench.py
│   │   ├── lmarena.py           # Chatbot Arena
│   │   ├── mmmu.py
│   │   ├── ifeval.py
│   │   ├── ailuminate.py        # Manual-flag scraper (see §8)
│   │   └── web_search.py        # DuckDuckGo fallback
│   ├── update_engine.py         # Orchestrates all scrapers, writes to DB
│   ├── seed_data.py             # Seeds DB with initial data from §10
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js           # Proxy /api → localhost:8000
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── data.js              # No longer embedded — fetches from API
│       └── components/
│           ├── Header.jsx
│           ├── TabNav.jsx
│           ├── UseCaseFinder.jsx
│           ├── ModelBrowser.jsx
│           ├── Compare.jsx
│           └── History.jsx
├── data/
│   └── db.sqlite                # Created on first run, gitignored
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
└── README.md
```

---

## 5. Database Schema

Create all tables in `database.py` via `init_db()`. Use `CREATE TABLE IF NOT EXISTS`.

```sql
CREATE TABLE IF NOT EXISTS benchmarks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    short TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL,
    metric TEXT NOT NULL,
    higher_is_better INTEGER NOT NULL DEFAULT 1,
    tier INTEGER NOT NULL DEFAULT 2,
    description TEXT,
    scraper_id TEXT,        -- maps to a scraper class name, e.g. 'ArtificialAnalysisScraper'
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'proprietary',   -- 'proprietary' | 'open_weights'
    release_date TEXT,
    context_window TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL REFERENCES models(id),
    benchmark_id TEXT NOT NULL REFERENCES benchmarks(id),
    value REAL NOT NULL,
    raw_value TEXT,           -- original string as scraped (e.g. "94.1%")
    collected_at TEXT NOT NULL,   -- ISO 8601 datetime
    source_url TEXT,
    source_type TEXT NOT NULL DEFAULT 'primary',  -- 'primary' | 'secondary' | 'manual'
    verified INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS update_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    triggered_by TEXT NOT NULL DEFAULT 'manual',  -- 'manual' | 'api' | 'scheduled'
    status TEXT NOT NULL DEFAULT 'running',       -- 'running' | 'completed' | 'failed'
    scores_added INTEGER DEFAULT 0,
    scores_updated INTEGER DEFAULT 0,
    errors TEXT   -- JSON array of {benchmark_id, model_id, error_message}
);
```

**Important**: The `scores` table is a time-series — never delete or overwrite rows, always INSERT. "Current" score for a model+benchmark is the row with the most recent `collected_at`. Write a SQL view:

```sql
CREATE VIEW IF NOT EXISTS latest_scores AS
SELECT s.*
FROM scores s
INNER JOIN (
    SELECT model_id, benchmark_id, MAX(collected_at) AS max_date
    FROM scores
    GROUP BY model_id, benchmark_id
) latest ON s.model_id = latest.model_id
       AND s.benchmark_id = latest.benchmark_id
       AND s.collected_at = latest.max_date;
```

---

## 6. API Specification

All endpoints under `/api/`. Return JSON. No auth.

### GET /api/models
Returns all active models with their latest scores for all benchmarks.

```json
[{
  "id": "claude-opus-4-6",
  "name": "Claude Opus 4.6",
  "provider": "Anthropic",
  "type": "proprietary",
  "release_date": "2025",
  "context_window": "200k tokens",
  "scores": {
    "aa_intelligence": { "value": 53, "collected_at": "2026-03-31", "source_type": "primary", "verified": true },
    "gpqa_diamond": null
  }
}]
```

### GET /api/benchmarks
Returns all active benchmarks with metadata.

### GET /api/rankings?use_case={id}
Returns models ranked for a given use case. Use case weights are defined in `seed_data.py` (see §10). Score normalisation logic: for each benchmark in the use case's weight map, normalise the model's latest score to 0–100 relative to the min/max across all models that have a score for that benchmark. Apply weights. Return only models with at least one score for the use case's benchmarks.

```json
{
  "use_case": { "id": "coding", "label": "Coding & Engineering" },
  "rankings": [{
    "rank": 1,
    "model": { ... },
    "score": 87.4,
    "coverage": 0.75,
    "breakdown": [
      { "benchmark_id": "swebench_verified", "raw_value": 80.8, "normalised": 95.2, "weight": 0.55 }
    ],
    "missing_benchmarks": ["terminal_bench"]
  }]
}
```

### GET /api/scores/history?model_id={id}&benchmark_id={id}
Returns all historical score rows for a model+benchmark, ordered by `collected_at` DESC.

### GET /api/update/history
Returns all rows from `update_log` ordered by `started_at` DESC.

### POST /api/update
Triggers a full data refresh. Runs all scrapers asynchronously. Returns immediately with a log ID; client polls `/api/update/status/{log_id}`.

```json
// Request body (optional)
{ "benchmarks": ["aa_intelligence", "swebench_verified"] }  // omit to run all

// Response
{ "log_id": 42, "status": "running" }
```

### GET /api/update/status/{log_id}
Returns current status of a running or completed update.

### POST /api/scores/manual
Allows manually entering a score for a model+benchmark. Sets `source_type = 'manual'`.

```json
{
  "model_id": "claude-opus-4-6",
  "benchmark_id": "ailuminate",
  "value": 72.0,
  "raw_value": "Very Good",
  "notes": "Converted from 5-point grade: Poor=0, Fair=25, Good=50, VeryGood=75, Excellent=100"
}
```

---

## 7. Scraper Engine

### Base class (`scrapers/base.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class ScrapeResult:
    model_name: str         # As it appears on the leaderboard
    benchmark_id: str
    value: float
    raw_value: str
    source_url: str
    source_type: str = "primary"   # 'primary' | 'secondary'
    verified: bool = True
    notes: Optional[str] = None

class BaseScraper(ABC):
    benchmark_ids: list[str]  # which benchmarks this scraper handles

    @abstractmethod
    async def scrape(self) -> list[ScrapeResult]:
        """Fetch and return all available scores. Never raises — catch internally and return partial results."""
        pass
```

### Scraper specifications

Implement one scraper per source file. Each must follow these rules:
- Never crash the update engine — catch all exceptions, log them, return whatever was collected
- Use `async/await` throughout
- Use Playwright only when httpx fails or returns empty/JS-rendered content
- Try the primary URL first; fall back to web search if blocked or broken
- Model name matching: scrapers return raw leaderboard names (e.g. `"Claude Opus 4.6"`). The update engine resolves these to `model_id` via a fuzzy name match against the models table. Implement a `resolve_model_name(raw_name: str, models: list) -> Optional[str]` utility function using simple substring/ratio matching (use `rapidfuzz` library).

| Scraper file | Benchmarks | Primary URL | Approach | Fallback |
|---|---|---|---|---|
| `artificial_analysis.py` | `aa_intelligence`, `aa_speed`, `aa_cost` | https://artificialanalysis.ai/leaderboards/models | Playwright — wait for table to render, extract rows | Web search: `"artificial analysis intelligence index leaderboard site:artificialanalysis.ai"` |
| `epoch_ai.py` | `gpqa_diamond` | https://epoch.ai/benchmarks/gpqa-diamond | Playwright — extract table | Web search fallback |
| `swebench.py` | `swebench_verified` | https://www.swebench.com/ | Playwright — extract verified leaderboard tab | Web search fallback |
| `lmarena.py` | `chatbot_arena` | https://lmarena.ai/ | Playwright — Gradio app; wait for leaderboard table | Web search: `"chatbot arena leaderboard ELO scores"` + parse |
| `mmmu.py` | `mmmu` | https://mmmu-benchmark.github.io/ | httpx first (GitHub Pages is static HTML) | Playwright fallback |
| `ifeval.py` | `ifeval` | https://llm-stats.com/benchmarks/ifeval | httpx + BeautifulSoup (likely static render) | HuggingFace Space fallback |
| `terminal_bench.py` | `terminal_bench` | https://www.tbench.ai/leaderboard/terminal-bench/2.0 | Playwright | Web search fallback |
| `ailuminate.py` | `ailuminate` | https://ailuminate.mlcommons.org/benchmarks/ | **Flag as manual only.** Return empty results. Log a warning: `"AILuminate requires manual score entry — use POST /api/scores/manual. Grade mapping: Poor=0, Fair=25, Good=50, VeryGood=75, Excellent=100"` |
| `web_search.py` | Any | DuckDuckGo | Used as fallback by other scrapers. Takes a query string, returns top 3 result snippets. Caller parses for scores. |

### Playwright setup notes
- Use `playwright.async_api`
- Launch headless Chromium
- Set a realistic user agent
- Wait for network idle before extracting
- Timeout: 30 seconds per page
- Do not install Playwright system deps in Docker — use the `mcr.microsoft.com/playwright/python` base image

### Update engine (`update_engine.py`)
- Instantiates all scrapers and runs them concurrently with `asyncio.gather`
- After all scrapers complete, resolves model names and writes scores to DB
- A score is written if: (a) it's new (no existing row for this model+benchmark today), or (b) the value differs from the most recent existing score by more than 0.1
- Creates and updates an `update_log` row throughout the run
- Emits structured logs: `{"event": "scraper_complete", "scraper": "SwebenchScraper", "scores_found": 12, "duration_ms": 4200}`

---

## 8. AILuminate — Special Handling

AILuminate uses a 5-point categorical grade system (Poor / Fair / Good / Very Good / Excellent) per hazard category, with an overall grade. Individual model results are not publicly available in machine-readable form — they are accessed through the official AILuminate portal and published PDFs.

The `ailuminate.py` scraper should:
1. Return no scores
2. Log a clear warning explaining why and giving the manual entry endpoint
3. Store the grade-to-number mapping in `seed_data.py`: `Poor=0, Fair=25, Good=50, VeryGood=75, Excellent=100`

When displaying AILuminate scores in the frontend, render the reverse mapping as a label (e.g. `75 → "Very Good"`) rather than a raw number.

---

## 9. Frontend Requirements

Migrate the prototype `dashboard.html` into the Vite + React project. The component structure and logic are defined in the prototype — use it as the direct reference. The key change is: **replace all embedded `DATA` constants with API calls**.

### Data fetching
- On app load: fetch `/api/models`, `/api/benchmarks` in parallel
- Use-case rankings: fetch `/api/rankings?use_case={id}` when a use case is selected (not preloaded)
- History tab: fetch `/api/update/history` on tab activation
- Score history for a model+benchmark: fetch on expand in Model Browser

Use `fetch()` directly — no need for React Query or SWR for this scale. Show a skeleton loader while data is loading. Show an error state if the API is unreachable.

### Update trigger UI
Add an **"Update Now"** button to the Header. On click:
1. POST to `/api/update`
2. Show a progress toast: "Update running…"
3. Poll `/api/update/status/{log_id}` every 3 seconds
4. On completion, re-fetch models and show a summary: "Update complete — 34 scores refreshed, 2 errors"
5. On error, show the error list

### Manual score entry
Add a small form to the History tab: "Enter score manually". Fields: model (dropdown), benchmark (dropdown), value (number input), raw value (text, e.g. "Very Good"), notes. POSTs to `/api/scores/manual`.

### Score source indicators
In all score displays, show a small icon:
- ✓ (green) = `verified: true`, `source_type: 'primary'`
- ~ (amber) = `source_type: 'secondary'` (came from web search fallback)
- ✎ (grey) = `source_type: 'manual'`

All other UI behaviour, scoring logic, and layout should match the prototype exactly.

---

## 10. Seed Data

Run `seed_data.py` on first startup (if DB is empty). Populate the following.

### Benchmarks (seed these 10)

```python
BENCHMARKS = [
  { "id": "aa_intelligence", "name": "AA Intelligence Index", "short": "AA Intel",
    "source": "Artificial Analysis", "url": "https://artificialanalysis.ai/leaderboards/models",
    "category": "General Quality", "metric": "Index Score", "higher_is_better": True, "tier": 1,
    "scraper_id": "ArtificialAnalysisScraper",
    "description": "Composite quality index. Best single number for overall capability. Independent of model providers." },
  { "id": "gpqa_diamond", "name": "GPQA Diamond", "short": "GPQA-D",
    "source": "Epoch AI", "url": "https://epoch.ai/benchmarks/gpqa-diamond",
    "category": "Reasoning & Math", "metric": "Accuracy %", "higher_is_better": True, "tier": 2,
    "scraper_id": "EpochAiScraper",
    "description": "198 graduate-level science questions. Highly resistant to contamination." },
  { "id": "mmmu", "name": "MMMU", "short": "MMMU",
    "source": "MMMU team", "url": "https://mmmu-benchmark.github.io/",
    "category": "Multimodal", "metric": "Accuracy %", "higher_is_better": True, "tier": 2,
    "scraper_id": "MmmuScraper",
    "description": "11.5k college-level multimodal questions across 30 subjects." },
  { "id": "swebench_verified", "name": "SWE-bench Verified", "short": "SWE-V",
    "source": "SWE-bench team", "url": "https://www.swebench.com/",
    "category": "Coding", "metric": "% Issues Resolved", "higher_is_better": True, "tier": 1,
    "scraper_id": "SwebenchScraper",
    "description": "Real GitHub issue resolution. Best coding benchmark for production relevance." },
  { "id": "ifeval", "name": "IFEval", "short": "IFEval",
    "source": "Google Research", "url": "https://llm-stats.com/benchmarks/ifeval",
    "category": "Instruction Following", "metric": "Prompt Accuracy %", "higher_is_better": True, "tier": 2,
    "scraper_id": "IfevalScraper",
    "description": "Machine-scoreable instruction constraints. Predictive of enterprise reliability." },
  { "id": "terminal_bench", "name": "Terminal-Bench 2.0", "short": "Term-B",
    "source": "tbench.ai", "url": "https://www.tbench.ai/leaderboard/terminal-bench/2.0",
    "category": "Agentic & Tool Use", "metric": "% Tasks Resolved", "higher_is_better": True, "tier": 2,
    "scraper_id": "TerminalBenchScraper",
    "description": "89 real workflow terminal tasks. ICLR 2026 published." },
  { "id": "ailuminate", "name": "AILuminate", "short": "Safety",
    "source": "MLCommons", "url": "https://ailuminate.mlcommons.org/benchmarks/",
    "category": "Safety & Compliance", "metric": "Grade (0–100)", "higher_is_better": True, "tier": 1,
    "scraper_id": "AILuminateScraper",
    "description": "12 hazard categories. Private test sets. Manual entry required — see grade mapping." },
  { "id": "aa_speed", "name": "Output Speed", "short": "Speed",
    "source": "Artificial Analysis", "url": "https://artificialanalysis.ai/leaderboards/models",
    "category": "Latency & Cost", "metric": "Tokens/sec", "higher_is_better": True, "tier": 1,
    "scraper_id": "ArtificialAnalysisScraper",
    "description": "Output tokens per second." },
  { "id": "aa_cost", "name": "Cost (blended)", "short": "Cost",
    "source": "Artificial Analysis", "url": "https://artificialanalysis.ai/leaderboards/models",
    "category": "Latency & Cost", "metric": "$/1M tokens", "higher_is_better": False, "tier": 1,
    "scraper_id": "ArtificialAnalysisScraper",
    "description": "Blended 3:1 input-output pricing." },
  { "id": "chatbot_arena", "name": "Chatbot Arena", "short": "Arena ELO",
    "source": "LMSYS", "url": "https://lmarena.ai/",
    "category": "General Quality", "metric": "ELO Score", "higher_is_better": True, "tier": 1,
    "scraper_id": "LmarenaScraper",
    "description": "ELO from millions of blind human preference votes." },
]
```

### Use case weights (seed into a `use_cases` table or hardcode in `seed_data.py`)

```python
USE_CASES = [
  { "id": "general_reasoning",    "label": "General Reasoning",     "icon": "🧠",
    "weights": { "aa_intelligence": 0.40, "gpqa_diamond": 0.35, "chatbot_arena": 0.25 } },
  { "id": "coding",               "label": "Coding & Engineering",   "icon": "💻",
    "weights": { "swebench_verified": 0.55, "aa_intelligence": 0.25, "terminal_bench": 0.20 } },
  { "id": "agentic",              "label": "Agentic & Tool Use",     "icon": "🤖",
    "weights": { "terminal_bench": 0.50, "swebench_verified": 0.25, "aa_intelligence": 0.25 } },
  { "id": "safety_compliance",    "label": "Safety & Compliance",    "icon": "🛡️",
    "weights": { "ailuminate": 0.70, "aa_intelligence": 0.30 } },
  { "id": "cost_efficiency",      "label": "Cost Efficiency",        "icon": "💰",
    "weights": { "aa_cost": 0.60, "aa_speed": 0.25, "aa_intelligence": 0.15 } },
  { "id": "multimodal",           "label": "Multimodal",             "icon": "🖼️",
    "weights": { "mmmu": 0.65, "aa_intelligence": 0.35 } },
  { "id": "instruction_following","label": "Instruction Following",  "icon": "📋",
    "weights": { "ifeval": 0.75, "chatbot_arena": 0.25 } },
  { "id": "speed",                "label": "Speed / Latency",        "icon": "⚡",
    "weights": { "aa_speed": 0.80, "aa_intelligence": 0.20 } },
]
```

### Models + initial scores (seed from verified research data, March 2026)

```python
MODELS = [
  { "id": "gemini-3-1-pro",    "name": "Gemini 3.1 Pro Preview",          "provider": "Google",        "type": "proprietary",  "release_date": "2026-Q1", "context_window": "1M tokens" },
  { "id": "gpt-5-4",           "name": "GPT-5.4 (xhigh)",                 "provider": "OpenAI",        "type": "proprietary",  "release_date": "2026-Q1", "context_window": "128k tokens" },
  { "id": "gpt-5-3-codex",     "name": "GPT-5.3 Codex (xhigh)",           "provider": "OpenAI",        "type": "proprietary",  "release_date": "2026-Q1", "context_window": "128k tokens" },
  { "id": "claude-opus-4-6",   "name": "Claude Opus 4.6",                 "provider": "Anthropic",     "type": "proprietary",  "release_date": "2025",    "context_window": "200k tokens" },
  { "id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6",               "provider": "Anthropic",     "type": "proprietary",  "release_date": "2025",    "context_window": "200k tokens" },
  { "id": "o4-mini-high",      "name": "o4 Mini High",                    "provider": "OpenAI",        "type": "proprietary",  "release_date": "2025",    "context_window": "128k tokens" },
  { "id": "glm-5",             "name": "GLM-5 (Reasoning)",               "provider": "Zhipu AI",      "type": "open_weights", "release_date": "2026-Q1", "context_window": "128k tokens" },
  { "id": "gemini-2-5-flash",  "name": "Gemini 2.5 Flash-Lite (Reasoning)","provider": "Google",       "type": "proprietary",  "release_date": "2025",    "context_window": "1M tokens" },
  { "id": "mercury-2",         "name": "Mercury 2",                       "provider": "Inception Labs","type": "proprietary",  "release_date": "2026-Q1", "context_window": "32k tokens" },
  { "id": "gemma-3n-e4b",      "name": "Gemma 3n E4B Instruct",           "provider": "Google",        "type": "open_weights", "release_date": "2026-Q1", "context_window": "8k tokens" },
]

# Seed scores — all source_type='primary', verified=True unless noted
SEED_SCORES = [
  # AA Intelligence Index
  { "model_id": "gemini-3-1-pro",    "benchmark_id": "aa_intelligence", "value": 57.0,  "raw_value": "57" },
  { "model_id": "gpt-5-4",           "benchmark_id": "aa_intelligence", "value": 57.0,  "raw_value": "57" },
  { "model_id": "gpt-5-3-codex",     "benchmark_id": "aa_intelligence", "value": 54.0,  "raw_value": "54" },
  { "model_id": "claude-opus-4-6",   "benchmark_id": "aa_intelligence", "value": 53.0,  "raw_value": "53" },
  { "model_id": "claude-sonnet-4-6", "benchmark_id": "aa_intelligence", "value": 52.0,  "raw_value": "52" },
  { "model_id": "glm-5",             "benchmark_id": "aa_intelligence", "value": 50.0,  "raw_value": "50" },
  # GPQA Diamond
  { "model_id": "gemini-3-1-pro",    "benchmark_id": "gpqa_diamond",    "value": 94.1,  "raw_value": "94.1%" },
  { "model_id": "gpt-5-4",           "benchmark_id": "gpqa_diamond",    "value": 92.0,  "raw_value": "92.0%" },
  { "model_id": "gpt-5-3-codex",     "benchmark_id": "gpqa_diamond",    "value": 91.5,  "raw_value": "91.5%" },
  { "model_id": "claude-opus-4-6",   "benchmark_id": "gpqa_diamond",    "value": 91.3,  "raw_value": "~91.3%", "source_type": "secondary", "verified": False, "notes": "From aggregator — verify against primary" },
  # MMMU
  { "model_id": "o4-mini-high",      "benchmark_id": "mmmu",            "value": 79.2,  "raw_value": "79.2%" },
  { "model_id": "gpt-5-4",           "benchmark_id": "mmmu",            "value": 79.1,  "raw_value": "79.1%" },
  # SWE-bench Verified
  { "model_id": "claude-opus-4-6",   "benchmark_id": "swebench_verified","value": 80.8, "raw_value": "80.8%", "source_type": "secondary", "verified": False },
  { "model_id": "gemini-3-1-pro",    "benchmark_id": "swebench_verified","value": 80.6, "raw_value": "80.6%", "source_type": "secondary", "verified": False },
  { "model_id": "claude-sonnet-4-6", "benchmark_id": "swebench_verified","value": 79.6, "raw_value": "79.6%", "source_type": "secondary", "verified": False },
  { "model_id": "glm-5",             "benchmark_id": "swebench_verified","value": 77.8, "raw_value": "77.8%", "source_type": "secondary", "verified": False },
  # Terminal-Bench 2.0
  { "model_id": "gemini-3-1-pro",    "benchmark_id": "terminal_bench",  "value": 78.4,  "raw_value": "78.4%", "source_type": "secondary", "verified": False },
  { "model_id": "gpt-5-3-codex",     "benchmark_id": "terminal_bench",  "value": 77.3,  "raw_value": "77.3%", "source_type": "secondary", "verified": False },
  { "model_id": "claude-opus-4-6",   "benchmark_id": "terminal_bench",  "value": 74.7,  "raw_value": "74.7%", "source_type": "secondary", "verified": False },
  # IFEval
  { "model_id": "glm-5",             "benchmark_id": "ifeval",          "value": 88.0,  "raw_value": "88.0%", "source_type": "secondary", "verified": False },
  # Chatbot Arena ELO
  { "model_id": "glm-5",             "benchmark_id": "chatbot_arena",   "value": 1451.0,"raw_value": "1451",  "source_type": "secondary", "verified": False },
  # Output Speed
  { "model_id": "mercury-2",         "benchmark_id": "aa_speed",        "value": 789.2, "raw_value": "789.2 t/s" },
  { "model_id": "gemini-2-5-flash",  "benchmark_id": "aa_speed",        "value": 386.1, "raw_value": "386.1 t/s" },
  # Cost
  { "model_id": "gemma-3n-e4b",      "benchmark_id": "aa_cost",         "value": 0.03,  "raw_value": "$0.03/1M" },
]
```

---

## 11. Deployment

### docker-compose.yml

```yaml
version: "3.9"
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data     # SQLite persists here
    environment:
      - DATABASE_URL=sqlite:////app/data/db.sqlite

  frontend:
    build:
      context: ./frontend
      dockerfile: ../Dockerfile.frontend
    ports:
      - "5173:80"
    depends_on:
      - backend
```

### Dockerfile.backend

Use `mcr.microsoft.com/playwright/python:v1.44.0-jammy` as the base image (includes Playwright browsers). Install Python deps from `requirements.txt`. Run `uvicorn main:app --host 0.0.0.0 --port 8000`.

### Dockerfile.frontend

Multi-stage: stage 1 — `node:20-alpine`, run `npm install && npm run build`. Stage 2 — `nginx:alpine`, copy build output, serve on port 80. Include an `nginx.conf` that proxies `/api/` to `http://backend:8000/api/`.

### One-command startup

```bash
docker compose up --build
```

Frontend at http://localhost:5173. API at http://localhost:8000. API docs at http://localhost:8000/docs (FastAPI auto-generates Swagger).

---

## 12. requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
httpx==0.27.0
beautifulsoup4==4.12.3
playwright==1.44.0
duckduckgo-search==6.2.0
rapidfuzz==3.9.0
pydantic==2.7.1
python-multipart==0.0.9
```

---

## 13. Acceptance Criteria

The build is complete when all of the following are true:

1. `docker compose up --build` starts both services with no errors
2. `GET /api/models` returns 10 models with their seeded scores
3. `GET /api/rankings?use_case=coding` returns a ranked list with at least 3 models scored
4. `POST /api/update` returns a log ID; polling the status endpoint shows `"completed"` within 120 seconds; at least 2 scrapers return results (accepting that some sites may be blocked or slow)
5. The frontend loads at http://localhost:5173 and all 4 tabs render without JS errors
6. The "Update Now" button triggers an update and shows a completion toast
7. Selecting "Coding & Engineering" in the Use Case Finder shows a ranked model list with score bars
8. Adding 2 models in the Compare tab shows a side-by-side table with ★ markers on winners
9. The History tab shows at least the seed entry and the update log from criterion 4
10. Score source indicators (✓ / ~ / ✎) display correctly in the Model Browser

---

## 14. Known Constraints & Gotchas

- **Playwright on Docker**: use the Microsoft Playwright base image — do not attempt to install Chromium manually, it breaks on headless Linux
- **Chatbot Arena (lmarena.ai)**: this is a Gradio app and is the hardest to scrape reliably. The web search fallback is acceptable; do not over-invest in making the Playwright scraper perfect for this one
- **AILuminate**: never attempt to scrape this. Manual entry only (see §8)
- **Artificial Analysis blocks automated scrapers**: if Playwright is blocked, fall through immediately to web search; do not retry more than once
- **SWE-bench contamination note**: OpenAI has stopped self-reporting SWE-bench Verified due to contamination concerns. Scores for GPT models may be absent or outdated — handle gracefully (null score is correct, not an error)
- **Model name matching**: leaderboard names vary wildly (e.g. "claude-opus-4-6-20251101", "Claude Opus 4.6 (Adaptive Reasoning)", "Anthropic Claude Opus 4.6"). The `resolve_model_name` fuzzy match is critical — test it carefully against all known variants
- **Score freshness**: the `collected_at` timestamp is when the scraper ran, not when the leaderboard last updated. Do not imply more precision than you have
- **No authentication**: this is an internal tool. Do not add auth. Do not expose to the internet
