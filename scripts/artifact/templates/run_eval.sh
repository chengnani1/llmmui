#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$ROOT_DIR/experience/reproduce_results.py" --artifact-root "$ROOT_DIR" "$@"

find "$ROOT_DIR/results" -name '._*' -delete
find "$ROOT_DIR/results" -name '.DS_Store' -delete

echo "[DONE] Reproduced evaluation outputs under results/"
