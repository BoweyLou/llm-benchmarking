#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-proxmox}"
REMOTE_APP_DIR="/opt/llm-benchmarking/current"
REMOTE_STATE_DIR="/var/lib/llm-benchmarking"
REMOTE_DB_PATH="$REMOTE_STATE_DIR/db.sqlite"
REMOTE_ENV_FILE="/etc/llm-benchmarking.env"
REMOTE_SERVICE="llm-benchmarking.service"
REMOTE_USER="llm-benchmarking"
REMOTE_PORT="${REMOTE_PORT:-8766}"
TAILNET_TRUSTED_WRITES="${TAILNET_TRUSTED_WRITES:-1}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  }
}

require_command ssh
require_command rsync
require_command curl
require_command python3

cd "$ROOT_DIR"

TAILSCALE_IP="${TAILSCALE_IP:-$(ssh -o BatchMode=yes "$REMOTE_HOST" 'tailscale ip -4 | head -n 1')}"
if [[ -z "$TAILSCALE_IP" ]]; then
  printf 'Could not resolve a Tailscale IPv4 address on %s.\n' "$REMOTE_HOST" >&2
  exit 1
fi

ssh -o BatchMode=yes "$REMOTE_HOST" "mkdir -p '$REMOTE_APP_DIR' '$REMOTE_STATE_DIR'"

REMOTE_DB_EXISTS="$(ssh -o BatchMode=yes "$REMOTE_HOST" "test -f '$REMOTE_DB_PATH' && printf yes || printf no")"
SEED_UPLOADED="no"
if [[ "$REMOTE_DB_EXISTS" != "yes" && -f "$ROOT_DIR/data/db.sqlite" ]]; then
  rsync -az "$ROOT_DIR/data/db.sqlite" "$REMOTE_HOST:$REMOTE_STATE_DIR/db.sqlite.seed"
  SEED_UPLOADED="yes"
fi

rsync -az --delete \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.DS_Store' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.playwright-cli/' \
  --exclude 'data/*.sqlite' \
  --exclude 'data/*.sqlite.*' \
  --exclude 'data/*.db' \
  --exclude 'data/*.bak' \
  --exclude 'backend/*.db' \
  --exclude 'output/' \
  "$ROOT_DIR/" "$REMOTE_HOST:$REMOTE_APP_DIR/"

ssh -o BatchMode=yes "$REMOTE_HOST" \
  "REMOTE_APP_DIR='$REMOTE_APP_DIR' REMOTE_STATE_DIR='$REMOTE_STATE_DIR' REMOTE_DB_PATH='$REMOTE_DB_PATH' REMOTE_ENV_FILE='$REMOTE_ENV_FILE' REMOTE_SERVICE='$REMOTE_SERVICE' REMOTE_USER='$REMOTE_USER' REMOTE_PORT='$REMOTE_PORT' TAILSCALE_IP='$TAILSCALE_IP' TAILNET_TRUSTED_WRITES='$TAILNET_TRUSTED_WRITES' ADMIN_TOKEN='${ADMIN_TOKEN:-}' bash -s" <<'REMOTE'
set -euo pipefail

if ! getent passwd "$REMOTE_USER" >/dev/null; then
  useradd --system --user-group --home "$REMOTE_STATE_DIR" --shell /usr/sbin/nologin "$REMOTE_USER"
fi

mkdir -p "$REMOTE_STATE_DIR" "$REMOTE_APP_DIR/data"
if [[ -f "$REMOTE_STATE_DIR/db.sqlite.seed" && ! -f "$REMOTE_DB_PATH" ]]; then
  mv "$REMOTE_STATE_DIR/db.sqlite.seed" "$REMOTE_DB_PATH"
fi
rm -f "$REMOTE_STATE_DIR/db.sqlite.seed"
chown -R "$REMOTE_USER:$REMOTE_USER" "$REMOTE_STATE_DIR"
chmod 0750 "$REMOTE_STATE_DIR"

existing_token=""
if [[ -f "$REMOTE_ENV_FILE" ]]; then
  existing_token="$(sed -n 's/^LLM_BENCHMARKING_ADMIN_TOKEN=//p' "$REMOTE_ENV_FILE" | tail -n 1)"
fi

token="${ADMIN_TOKEN:-$existing_token}"
if [[ -z "$token" ]]; then
  token="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
fi

tmp_env="$(mktemp)"
if [[ -f "$REMOTE_ENV_FILE" ]]; then
  grep -Ev '^(DATABASE_URL|LLM_BENCHMARKING_ADMIN_TOKEN|LLM_BENCHMARKING_HOST|LLM_BENCHMARKING_PORT|LLM_BENCHMARKING_TRUSTED_TAILNET_WRITES)=' "$REMOTE_ENV_FILE" > "$tmp_env" || true
fi
{
  cat "$tmp_env"
  printf 'DATABASE_URL=sqlite:///%s\n' "$REMOTE_DB_PATH"
  printf 'LLM_BENCHMARKING_ADMIN_TOKEN=%s\n' "$token"
  printf 'LLM_BENCHMARKING_HOST=%s\n' "$TAILSCALE_IP"
  printf 'LLM_BENCHMARKING_PORT=%s\n' "$REMOTE_PORT"
  printf 'LLM_BENCHMARKING_TRUSTED_TAILNET_WRITES=%s\n' "$TAILNET_TRUSTED_WRITES"
} > "$REMOTE_ENV_FILE"
rm -f "$tmp_env"
chown "root:$REMOTE_USER" "$REMOTE_ENV_FILE"
chmod 0640 "$REMOTE_ENV_FILE"

cd "$REMOTE_APP_DIR"
if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  rm -rf .venv
  if ! python3 -m venv .venv; then
    if command -v apt-get >/dev/null 2>&1; then
      python_venv_package="$(python3 - <<'PY'
import sys
print(f"python{sys.version_info.major}.{sys.version_info.minor}-venv")
PY
)"
      DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv || \
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$python_venv_package"
      rm -rf .venv
      python3 -m venv .venv
    else
      printf 'python3 -m venv failed and apt-get is not available on this host.\n' >&2
      exit 1
    fi
  fi
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt

install -m 0644 deploy/systemd/llm-benchmarking.service "/etc/systemd/system/$REMOTE_SERVICE"
systemctl daemon-reload
systemctl enable "$REMOTE_SERVICE" >/dev/null
systemctl restart "$REMOTE_SERVICE"
sleep 2
systemctl is-active --quiet "$REMOTE_SERVICE"
REMOTE

CATALOG_JSON="$(mktemp)"
catalog_ready="no"
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error "http://$TAILSCALE_IP:$REMOTE_PORT/api/review/catalog" -o "$CATALOG_JSON"; then
    catalog_ready="yes"
    break
  fi
  sleep 1
done
if [[ "$catalog_ready" != "yes" ]]; then
  printf 'Review catalog did not become ready at http://%s:%s/api/review/catalog.\n' "$TAILSCALE_IP" "$REMOTE_PORT" >&2
  rm -f "$CATALOG_JSON"
  exit 1
fi
python3 - "$CATALOG_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
summary = payload.get("summary") or {}
if not summary.get("model_count"):
    raise SystemExit("review catalog returned no models")
print(
    "Verified review catalog: "
    f"{summary.get('model_count')} models, "
    f"{summary.get('provider_count')} providers, "
    f"{summary.get('family_count')} families"
)
PY
rm -f "$CATALOG_JSON"

printf 'Deployed LLM Model Tool: http://%s:%s/review\n' "$TAILSCALE_IP" "$REMOTE_PORT"
printf 'Trusted tailnet writes: %s\n' "$TAILNET_TRUSTED_WRITES"
printf 'Admin token fallback is stored on %s:%s\n' "$REMOTE_HOST" "$REMOTE_ENV_FILE"
printf 'Remote DB seed uploaded: %s\n' "$SEED_UPLOADED"
