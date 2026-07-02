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

Set `REMOTE_HOST`, `REMOTE_PORT`, `TAILSCALE_IP`, or `ADMIN_TOKEN` in the local
environment when a deploy needs different connection details or a preselected
admin token:

```bash
ADMIN_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)" scripts/deploy_proxmox_review_workbench.sh
```

The first deploy seeds the remote persistent database from local `data/db.sqlite`
when that file exists. Later deploys preserve the remote database and token so
manual review decisions survive code updates.

On Debian-based Proxmox hosts, the script installs `python3-venv` or the
matching versioned package, such as `python3.11-venv`, if the base Python
runtime cannot create a virtual environment.

## Use

Open the workbench from any device on the tailnet:

```text
http://<proxmox-tailscale-ip>:8766/review
```

Read-only browsing does not need credentials. To save decisions, paste the admin
token from the Proxmox environment file into the workbench token field:

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
