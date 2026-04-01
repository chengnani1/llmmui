#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/run_incremental_phase23.sh <raw_root> <processed_root> [poll_seconds]

Example:
  bash scripts/run_incremental_phase23.sh \
    /Volumes/Charon/data/code/llm_ui/code/data/0320/rawdata \
    /Volumes/Charon/data/code/llm_ui/code/data/0320/processeddata \
    1800

Behavior:
  1. Scan raw_root for completed fastbot-* dirs (tupleOfPermissions.json exists)
  2. Run phase2 only for apps not yet processed
  3. Scan processed_root for apps with result.json but without result_final_decision.json
  4. Run phase3_v2 incrementally for those apps
  5. Sleep and repeat

Assumptions:
  - Run this script inside the activated llmui conda env
  - Do not start multiple copies of this script on the same dataset
EOF
}

if [[ "${1:-}" == "" || "${2:-}" == "" ]]; then
  usage
  exit 1
fi

RAW_ROOT="$1"
PROCESSED_ROOT="$2"
POLL_SECONDS="${3:-1800}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOCK_DIR="${TMPDIR:-/tmp}/llmui_incremental_phase23.lock"

if [[ ! -d "$RAW_ROOT" ]]; then
  echo "[ERROR] raw_root not found: $RAW_ROOT"
  exit 1
fi

mkdir -p "$PROCESSED_ROOT"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[ERROR] another incremental phase2/phase3 worker is already running: $LOCK_DIR"
  exit 1
fi

cleanup() {
  rm -rf "$LOCK_DIR"
}
trap cleanup EXIT

run_phase2_one() {
  local raw_app_dir="$1"
  local app_name
  local tmp_root
  local status=0

  app_name="$(basename "$raw_app_dir")"
  tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/llmui_phase2_${app_name}.XXXXXX")"

  ln -s "$raw_app_dir" "$tmp_root/$app_name"

  echo "[PHASE2] $(date '+%F %T') app=$app_name"
  if (
    cd "$REPO_ROOT"
    "$PYTHON_BIN" -u src/main.py phase2 "$tmp_root" --processed-root "$PROCESSED_ROOT"
  ); then
    status=0
  else
    status=$?
  fi

  rm -rf "$tmp_root"
  return "$status"
}

run_phase3_one() {
  local processed_app_dir="$1"
  local app_name
  local status=0

  app_name="$(basename "$processed_app_dir")"
  echo "[PHASE3] $(date '+%F %T') app=$app_name"
  if (
    cd "$REPO_ROOT"
    "$PYTHON_BIN" -u src/main.py phase3_v2 "$processed_app_dir"
  ); then
    status=0
  else
    status=$?
  fi
  return "$status"
}

scan_and_run() {
  local phase2_count=0
  local phase3_count=0
  local raw_app_dir=""
  local processed_app_dir=""

  while IFS= read -r raw_app_dir; do
    [[ -d "$raw_app_dir" ]] || continue

    local app_name
    local processed_app

    app_name="$(basename "$raw_app_dir")"
    processed_app="$PROCESSED_ROOT/$app_name"

    [[ -f "$raw_app_dir/tupleOfPermissions.json" ]] || continue
    [[ -f "$processed_app/result.json" ]] && continue

    if run_phase2_one "$raw_app_dir"; then
      phase2_count=$((phase2_count + 1))
    else
      echo "[WARN] phase2 failed: $app_name"
    fi
  done < <(find "$RAW_ROOT" -maxdepth 1 -mindepth 1 -type d -name 'fastbot-*' | sort)

  while IFS= read -r processed_app_dir; do
    [[ -d "$processed_app_dir" ]] || continue
    [[ -f "$processed_app_dir/result.json" ]] || continue
    [[ -f "$processed_app_dir/result_final_decision.json" ]] && continue

    if run_phase3_one "$processed_app_dir"; then
      phase3_count=$((phase3_count + 1))
    else
      echo "[WARN] phase3 failed: $(basename "$processed_app_dir")"
    fi
  done < <(find "$PROCESSED_ROOT" -maxdepth 1 -mindepth 1 -type d -name 'fastbot-*' | sort)

  echo "[ROUND] $(date '+%F %T') phase2_new=$phase2_count phase3_new=$phase3_count"
}

echo "[START] raw_root=$RAW_ROOT processed_root=$PROCESSED_ROOT poll_seconds=$POLL_SECONDS"

while true; do
  scan_and_run
  echo "[SLEEP] $(date '+%F %T') sleep=${POLL_SECONDS}s"
  sleep "$POLL_SECONDS"
done
