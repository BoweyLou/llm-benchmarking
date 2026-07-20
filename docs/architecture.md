# Architecture

LLM Benchmarking is a Python and SQLite model-intelligence service. Source
adapters collect provider, benchmark, pricing, model-card, provenance, and
availability evidence. The update engine normalizes that evidence into the
SQLite catalog. FastAPI, the backend CLI, CSV/JSON exports, and the private LLM
Model Tool browser interface are read and review surfaces over that catalog.

Human approval, recommendation, and usage classification are independent of
metric-derived suggested uses. Model identity is server-owned through
`review_entity_id`. Route availability and published pricing are likewise
independent evidence: a price can exist without confirmed access to a model in
a region.

Production runs privately on Proxmox over Tailscale. The persistent database is
owned by the service host and is never replaced by deployment sync.

See `docs/data-ingest-map.md` for the detailed pipeline and evidence contracts.
