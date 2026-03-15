#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash run_full_pipeline.sh <processed_root> [--app APP] [--scene-mode text|vision] [--force] [--chain-ids 1,2,3]"
  exit 1
fi

PROCESSED_ROOT="$1"
shift

APP_NAME=""
SCENE_MODE="text"
FORCE_FLAG=""
CHAIN_IDS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      APP_NAME="${2:-}"
      shift 2
      ;;
    --scene-mode)
      SCENE_MODE="${2:-text}"
      shift 2
      ;;
    --force)
      FORCE_FLAG="--force"
      shift
      ;;
    --chain-ids)
      CHAIN_IDS="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1"
      exit 1
      ;;
  esac
done

COMMON_ARGS=()
if [[ -n "$APP_NAME" ]]; then
  COMMON_ARGS+=("--app" "$APP_NAME")
fi
if [[ -n "$FORCE_FLAG" ]]; then
  COMMON_ARGS+=("$FORCE_FLAG")
fi
if [[ -n "$CHAIN_IDS" ]]; then
  COMMON_ARGS+=("--chain-ids" "$CHAIN_IDS")
fi

echo "[RUN] phase3_semantics"
cmd=(python3 src/main.py phase3_semantics "$PROCESSED_ROOT")
if (( ${#COMMON_ARGS[@]} > 0 )); then
  cmd+=("${COMMON_ARGS[@]}")
fi
"${cmd[@]}"

echo "[RUN] phase3_scene"
cmd=(python3 src/main.py phase3_scene "$PROCESSED_ROOT" --scene-mode "$SCENE_MODE")
if (( ${#COMMON_ARGS[@]} > 0 )); then
  cmd+=("${COMMON_ARGS[@]}")
fi
"${cmd[@]}"

echo "[RUN] phase3_rule"
cmd=(python3 src/main.py phase3_rule "$PROCESSED_ROOT")
if (( ${#COMMON_ARGS[@]} > 0 )); then
  cmd+=("${COMMON_ARGS[@]}")
fi
"${cmd[@]}"

echo "[RUN] phase3_llm"
cmd=(python3 src/main.py phase3_llm "$PROCESSED_ROOT")
if (( ${#COMMON_ARGS[@]} > 0 )); then
  cmd+=("${COMMON_ARGS[@]}")
fi
"${cmd[@]}"

echo "[RUN] phase3_final"
cmd=(python3 src/main.py phase3_final "$PROCESSED_ROOT")
if (( ${#COMMON_ARGS[@]} > 0 )); then
  cmd+=("${COMMON_ARGS[@]}")
fi
"${cmd[@]}"

echo "[DONE] full pipeline finished"
