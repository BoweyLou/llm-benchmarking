# Releasing

`VERSION` is the single SemVer source and `CHANGELOG.md` records user-visible
changes. Runtime-affecting releases must start from the exact integrated
revision, pass the merge checks declared in `.codex/project.toml`, and retain a
rollback path for the current Proxmox service and database.

The release sequence is:

1. Finalize the version and changelog on the protected task head.
2. Complete governed integration through the declared private Forgejo route.
3. Deploy the exact integrated revision with
   `scripts/deploy_proxmox_review_workbench.sh`.
4. Run `scripts/verify_proxmox_review_workbench.sh` and complete browser
   acceptance when UI behavior changed.
5. Reconcile the Obsidian Backlog and Delivery Log and retain closeout evidence.

Do not deploy an unintegrated worktree or publish a release from the legacy
GitHub remote during governance adoption.
