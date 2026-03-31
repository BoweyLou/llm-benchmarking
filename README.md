# LLM Benchmarking

LLM Benchmarking is a local benchmarking dashboard for comparing AI models across public benchmark sources.

The current stack is:

- FastAPI backend for model, benchmark, ranking, update, and audit APIs
- React + Vite frontend for browsing, comparing, and tracking models
- SQLite for local storage
- Source adapters for public benchmark ingestion

## Run locally

Backend:

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The backend bootstraps its schema on startup. SQLite files are intentionally not committed.

## Current scope

- Phase 1 benchmark ingestion for Artificial Analysis, Chatbot Arena, AILuminate, GPQA Diamond, IFEval, MMMU, and SWE-bench Verified
- Audit checks after each update run
- Family and exact-variant views in the frontend catalog

## Key docs

- `AGENT_BUILD_SPEC.md`
- `ai_benchmark_report_2026.md`
- `UPDATE_GUIDE.md`
