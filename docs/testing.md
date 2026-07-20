# Testing

Use the declared commands in `.codex/project.toml`. They run in an isolated `uv`
environment hydrated from `backend/requirements.txt`, so a clean worktree does
not depend on the primary checkout's virtualenv.

- Commit: focused model-guide tests plus Python compilation.
- Merge: the full backend unittest discovery suite plus commit checks.
- UI-affecting work: real browser acceptance against the intended runtime.
- Runtime-affecting work: deploy only from the integrated revision, then run
  `scripts/verify_proxmox_review_workbench.sh`.

Tests that need a database should use temporary SQLite state unless explicitly
performing a read-only production verification. Never use the persistent live
database as a disposable test fixture.
