#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash run_project.sh <mode> <target> [extra args...]

Modes:
  full
  phase1
  phase2
  phase3_v2
  phase3_v2_compliance
  phase3_v2_final
  phase3_v2_post

Target aliases:
  benchmark     -> data/benchmark_processed
  independent   -> data/independent_processed
  large-scale   -> data/large_scale_processed
  rq1           -> data/benchmark_processed
  rq2           -> data/independent_processed
  rq3           -> data/large_scale_processed

Examples:
  bash run_project.sh phase3_v2 benchmark --force
  bash run_project.sh phase3_v2_compliance independent --app fastbot-xxx --force
  bash run_project.sh full /path/to/apks --raw-root /path/raw --processed-root /path/processed --force
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="$1"
TARGET_RAW="$2"
shift 2
EXTRA_ARGS=("$@")

resolve_target() {
  local raw="$1"
  case "$raw" in
    benchmark|rq1)
      echo "$ROOT_DIR/data/benchmark_processed"
      ;;
    independent|rq2)
      echo "$ROOT_DIR/data/independent_processed"
      ;;
    large-scale|largescale|rq3)
      echo "$ROOT_DIR/data/large_scale_processed"
      ;;
    *)
      echo "$raw"
      ;;
  esac
}

TARGET="$(resolve_target "$TARGET_RAW")"

export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

run_main() {
  local mode="$1"
  echo "[RUN] python3 src/main.py ${mode} ${TARGET} ${EXTRA_ARGS[*]}"
  python3 "$ROOT_DIR/src/main.py" "$mode" "$TARGET" "${EXTRA_ARGS[@]}"
}

case "$MODE" in
  full|phase1|phase2|phase3_v2|phase3_v2_compliance|phase3_v2_final)
    run_main "$MODE"
    ;;
  phase3_v2_post)
    run_main "phase3_v2_compliance"
    run_main "phase3_v2_final"
    ;;
  *)
    echo "[ERROR] Unsupported mode: $MODE"
    usage
    exit 2
    ;;
esac

echo "[DONE] mode=$MODE target=$TARGET"
