# LLM Benchmarking

LLM Benchmarking is a local benchmarking dashboard for comparing AI models across public benchmark sources.

The current stack is:

- FastAPI backend for model, benchmark, ranking, update, and audit APIs
- React + Vite frontend for browsing, comparing, and tracking models
- SQLite for local storage
- Source adapters for public benchmark ingestion

## Clean Clone Setup

After cloning the repo:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend
npm install
cd ..
python -m backend.bootstrap_db
```

That last command creates the SQLite schema and runs a full Phase 1 ingest so the cloned repo has data without needing the API server first.

## Run Locally

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

The backend bootstraps its schema on startup. SQLite files are intentionally not committed, and `python -m backend.bootstrap_db` is the supported first-run populate command.

## Current scope

- Phase 1 benchmark ingestion for Artificial Analysis, Chatbot Arena, AILuminate, GPQA Diamond, IFEval, MMMU, and SWE-bench Verified
- Audit checks after each update run
- Family and exact-variant views in the frontend catalog
- Phase 2 starts with Terminal-Bench investigation and ingestion policy design

## Key docs

- `AGENT_BUILD_SPEC.md`
- `ai_benchmark_report_2026.md`
- `UPDATE_GUIDE.md`
