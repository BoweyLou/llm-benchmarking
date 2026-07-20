# LLM Benchmarking project route

- Start with `.codex/project.toml`, then retrieve the linked Obsidian Overview,
  Backlog, relevant Decisions, and Delivery Log.
- Use practical TDD for behaviour changes. Keep one writer per worktree and
  preserve unrelated work in other checkouts.
- Keep model identity, human decisions, inferred use cases, route availability,
  and price evidence semantically distinct across APIs, UI, and exports.
- Treat Proxmox over Tailscale as the private production surface. Release and
  deploy only from an integrated revision, then run the declared live verifier.
- Reconcile durable backlog and delivery outcomes in Obsidian at closeout.
