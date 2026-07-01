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

"$PYTHON_BIN" -m py_compile backend/*.py backend/sources/*.py
"$PYTHON_BIN" -m unittest discover -s backend -t .
