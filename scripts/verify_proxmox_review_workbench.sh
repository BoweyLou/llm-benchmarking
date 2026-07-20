#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-proxmox}"
REMOTE_PORT="${REMOTE_PORT:-8766}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

for command in ssh curl python3; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'Missing required command: %s\n' "$command" >&2
    exit 1
  }
done

LOCAL_VERSION="$(PYTHONPATH="$ROOT_DIR" python3 - <<'PY'
from backend.versioning import read_app_version

print(read_app_version())
PY
)"
TAILSCALE_IP="${TAILSCALE_IP:-$(ssh -o BatchMode=yes "$REMOTE_HOST" 'tailscale ip -4 | head -n 1')}"
BASE_URL="http://$TAILSCALE_IP:$REMOTE_PORT"
CATALOG_JSON="$(mktemp)"
REVIEW_HTML="$(mktemp)"
MODEL_GUIDE="$(mktemp)"
trap 'rm -f "$CATALOG_JSON" "$REVIEW_HTML" "$MODEL_GUIDE"' EXIT

curl --fail --silent --show-error "$BASE_URL/api/review/catalog" -o "$CATALOG_JSON"
curl --fail --silent --show-error "$BASE_URL/review" -o "$REVIEW_HTML"
curl --fail --silent --show-error -X POST \
  "$BASE_URL/api/review/exports/model-guide" \
  -H 'Content-Type: application/json' \
  --data '{}' \
  -o "$MODEL_GUIDE"

python3 - "$CATALOG_JSON" "$REVIEW_HTML" "$MODEL_GUIDE" "$LOCAL_VERSION" <<'PY'
import csv
import io
import json
from pathlib import Path
import sys
import zipfile

catalog_path, review_path, archive_path, expected_version = sys.argv[1:]
catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
summary = catalog.get("summary") or {}
if not summary.get("model_count"):
    raise SystemExit("review catalog returned no models")

page = Path(review_path).read_text(encoding="utf-8")
expected = f'<span id="appVersion">Version {expected_version}</span>'
if expected not in page:
    raise SystemExit(f"review UI did not report version {expected_version}")

with zipfile.ZipFile(archive_path) as archive:
    if archive.namelist() != ["model-guide.csv", "README.txt"]:
        raise SystemExit(f"unexpected model-guide members: {archive.namelist()}")
    rows = list(
        csv.DictReader(
            io.StringIO(archive.read("model-guide.csv").decode("utf-8-sig"))
        )
    )

model_ids = [row.get("Model ID", "") for row in rows]
if not rows or any(not model_id for model_id in model_ids):
    raise SystemExit("model-guide CSV contains missing model IDs")
if len(model_ids) != len(set(model_ids)):
    raise SystemExit("model-guide CSV contains duplicate model IDs")

print(
    f"Verified version {expected_version}: {summary['model_count']} catalog models, "
    f"{len(rows)} exported review entities"
)
PY

printf 'Verified LLM Model Tool: %s/review\n' "$BASE_URL"
