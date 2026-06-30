#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "$#" -gt 0 ]]; then
  DESTINATIONS=("$@")
else
  DESTINATIONS=(aws-bedrock azure-ai-foundry google-vertex-ai)
fi

TMP_DIR="$(mktemp -d)"
OUTPUT_JSON="$TMP_DIR/inference-sync.json"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

DATABASE_URL="sqlite:///$TMP_DIR/test.sqlite" \
AWS_BEDROCK_REGIONS="${AWS_BEDROCK_REGIONS:-us-east-1}" \
python3 -m backend.cli inference-sync --destinations "${DESTINATIONS[@]}" >"$OUTPUT_JSON"

python3 - "$OUTPUT_JSON" "${DESTINATIONS[@]}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
expected = sys.argv[2:]
destinations = payload.get("destinations", {})

missing = [destination for destination in expected if destination not in destinations]
if missing:
    raise SystemExit(f"Missing sync results for: {', '.join(missing)}")

failed = [
    f"{destination}: {destinations[destination].get('reason', 'unknown failure')}"
    for destination in expected
    if destinations[destination].get("status") == "failed"
]
if failed:
    raise SystemExit("Inference sync smoke test failed: " + "; ".join(failed))

invalid = [
    f"{destination}: {destinations[destination].get('status')}"
    for destination in expected
    if destinations[destination].get("status") not in {"completed", "skipped"}
]
if invalid:
    raise SystemExit("Unexpected sync status: " + "; ".join(invalid))

print(json.dumps(payload, indent=2, sort_keys=True))
PY
