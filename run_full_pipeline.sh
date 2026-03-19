#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash run_full_pipeline.sh <mode> <target> [extra args...]

Modes (mapped to src/main.py):
  full                 run phase1 + phase2 + phase3_v2
  phase1               data collection only
  phase2               data processing only
  phase3_v2            permission + semantic + retrieval+llm + final
  phase3_v2_compliance retrieval+llm only (reuse semantic+permission)
  phase3_v2_final      final mapping only (reuse llm output)
  phase3_v2_post       compliance + final (skip semantic)

Examples:
  bash run_full_pipeline.sh phase3_v2 /path/to/processed --app APP --force
  bash run_full_pipeline.sh phase3_v2_compliance /path/to/processed --chain-ids 0,1,2 --force
  bash run_full_pipeline.sh phase3_v2_post /path/to/processed --app APP --force
  bash run_full_pipeline.sh full /path/to/apk_dir --raw-root /path/raw --processed-root /path/processed --force
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

MODE="$1"
TARGET="$2"
shift 2
EXTRA_ARGS=("$@")

# Local tunnel / loopback endpoints are common for this project.
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

run_main() {
  local mode="$1"
  echo "[RUN] python3 src/main.py ${mode} ${TARGET} ${EXTRA_ARGS[*]}"
  python3 src/main.py "${mode}" "${TARGET}" "${EXTRA_ARGS[@]}"
}

case "${MODE}" in
  full|phase1|phase2|phase3_v2|phase3_v2_compliance|phase3_v2_final)
    run_main "${MODE}"
    ;;
  phase3_v2_post)
    run_main "phase3_v2_compliance"
    run_main "phase3_v2_final"
    ;;
  *)
    echo "[ERROR] Unsupported mode: ${MODE}"
    usage
    exit 2
    ;;
esac

echo "[DONE] mode=${MODE}"
