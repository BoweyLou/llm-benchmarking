# Proxmox Tailnet Review Workbench Deployment

The banking model review workbench can run as a private FastAPI service on the
Proxmox host and bind only to the host's Tailscale IPv4 address.

## Deploy

From the repository root:

```bash
scripts/deploy_proxmox_review_workbench.sh
```

Defaults:

- SSH host: `proxmox`
- Service URL: `http://<proxmox-tailscale-ip>:8766/review`
- App checkout: `/opt/llm-benchmarking/current`
- Persistent SQLite database: `/var/lib/llm-benchmarking/db.sqlite`
- Systemd unit: `/etc/systemd/system/llm-benchmarking.service`
- Environment file: `/etc/llm-benchmarking.env`
- Runtime user: `llm-benchmarking`
- Trusted tailnet writes: enabled with
  `LLM_BENCHMARKING_TRUSTED_TAILNET_WRITES=1`

Set `REMOTE_HOST`, `REMOTE_PORT`, `TAILSCALE_IP`,
`TAILNET_TRUSTED_WRITES`, or `ADMIN_TOKEN` in the local environment when a
deploy needs different connection details, tokenless-write behavior, or a
preselected admin token:

```bash
ADMIN_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)" scripts/deploy_proxmox_review_workbench.sh
```

The first deploy seeds the remote persistent database from local `data/db.sqlite`
when that file exists. Later deploys preserve the remote database and token
fallback so manual review decisions survive code updates.

On Debian-based Proxmox hosts, the script installs `python3-venv` or the
matching versioned package, such as `python3.11-venv`, if the base Python
runtime cannot create a virtual environment.

## Use

Open the workbench from any device on the tailnet:

```text
http://<proxmox-tailscale-ip>:8766/review
```

Devices on the Tailscale network can browse and save decisions without pasting
an admin token. The service still keeps an admin-token fallback for non-tailnet
operations or if trusted tailnet writes are disabled:

```bash
ssh proxmox "sed -n 's/^LLM_BENCHMARKING_ADMIN_TOKEN=//p' /etc/llm-benchmarking.env"
```

## Operate

Check the service:

```bash
ssh proxmox "systemctl status llm-benchmarking.service --no-pager"
```

Read recent logs:

```bash
ssh proxmox "journalctl -u llm-benchmarking.service -n 100 --no-pager"
```

Restart after manual environment changes:

```bash
ssh proxmox "systemctl restart llm-benchmarking.service"
```

Back up review decisions before rebuilding the database by using the workbench
snapshot export, or by copying `/var/lib/llm-benchmarking/db.sqlite` from the
Proxmox host.
