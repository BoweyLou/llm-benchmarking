#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON:-python}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  echo "Set PYTHON=/path/to/python or activate the project environment." >&2
  exit 127
fi

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import importlib.util
import sys

missing = [
    package
    for package in ("httpx", "sqlalchemy", "fastapi")
    if importlib.util.find_spec(package) is None
]
if missing:
    raise SystemExit(
        "Missing project dependencies for "
        f"{sys.executable}: {', '.join(missing)}. "
        "Activate the project environment or run `pip install -r backend/requirements.txt`."
    )
PY

if [[ "$#" -gt 0 ]]; then
  DESTINATIONS=("$@")
else
  DESTINATIONS=(aws-bedrock azure-ai-foundry google-vertex-ai)
fi

TMP_DIR="$(mktemp -d)"
OUTPUT_JSON="$TMP_DIR/inference-sync.json"
OUTPUT_STDERR="$TMP_DIR/inference-sync.stderr"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

set +e
DATABASE_URL="sqlite:///$TMP_DIR/test.sqlite" \
AWS_BEDROCK_REGIONS="${AWS_BEDROCK_REGIONS:-us-east-1}" \
"$PYTHON_BIN" -m backend.cli inference-sync --destinations "${DESTINATIONS[@]}" >"$OUTPUT_JSON" 2>"$OUTPUT_STDERR"
CLI_STATUS=$?
set -e

if [[ "$CLI_STATUS" -ne 0 ]]; then
  echo "inference-sync command failed with exit code $CLI_STATUS" >&2
  if [[ -s "$OUTPUT_JSON" ]]; then
    echo "Captured stdout:" >&2
    cat "$OUTPUT_JSON" >&2
  fi
  if [[ -s "$OUTPUT_STDERR" ]]; then
    echo "Captured stderr:" >&2
    cat "$OUTPUT_STDERR" >&2
  fi
  exit "$CLI_STATUS"
fi

"$PYTHON_BIN" - "$OUTPUT_JSON" "${DESTINATIONS[@]}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
expected = sys.argv[2:]
destinations = payload.get("destinations", {})

def fail(message: str) -> None:
    print(message, file=sys.stderr)
    print("Captured inference-sync payload:", file=sys.stderr)
    print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
    raise SystemExit(1)

missing = [destination for destination in expected if destination not in destinations]
if missing:
    fail(f"Missing sync results for: {', '.join(missing)}")

failed = [
    f"{destination}: {destinations[destination].get('reason', 'unknown failure')}"
    for destination in expected
    if destinations[destination].get("status") == "failed"
]
if failed:
    fail("Inference sync smoke test failed: " + "; ".join(failed))

invalid = [
    f"{destination}: {destinations[destination].get('status')}"
    for destination in expected
    if destinations[destination].get("status") not in {"completed", "skipped"}
]
if invalid:
    fail("Unexpected sync status: " + "; ".join(invalid))

print(json.dumps(payload, indent=2, sort_keys=True))
PY
