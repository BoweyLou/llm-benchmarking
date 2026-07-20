# Operations

The private production surface is the Proxmox-hosted LLM Model Tool reachable
over Tailscale. Persistent state lives outside the deployed checkout at
`/var/lib/llm-benchmarking/db.sqlite`.

Deploy with `scripts/deploy_proxmox_review_workbench.sh` only from an integrated
and versioned revision. The deployer preserves the remote database, installs
dependencies, restarts the systemd unit, and checks catalog and UI readiness.

Verify independently with `scripts/verify_proxmox_review_workbench.sh`. It
checks catalog data, the visible version, the one-CSV model-guide archive, unique
model IDs, and the live review URL.

See `docs/deploy/proxmox-review-workbench.md` for bootstrap, rollback, update,
and troubleshooting procedures.
