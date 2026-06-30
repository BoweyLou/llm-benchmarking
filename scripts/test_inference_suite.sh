#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m py_compile backend/*.py backend/sources/*.py
python3 -m unittest \
  backend.test_inference_catalog \
  backend.test_inference_sync \
  backend.test_rankings \
  backend.test_model_taxonomy
