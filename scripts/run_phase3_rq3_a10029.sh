#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/Users/charon/Downloads/code/llmmui"
PROCESSED_ROOT="/Volumes/Charon/data/code/llm_ui/code/data/rq3/processed-neeed"

# a100-29 default forwarded endpoints
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export LLMMUI_VLLM_VL_URL="${LLMMUI_VLLM_VL_URL:-http://127.0.0.1:29010/v1/chat/completions}"
export LLMMUI_VLLM_TEXT_URL="${LLMMUI_VLLM_TEXT_URL:-http://127.0.0.1:29011/v1/chat/completions}"
export LLMMUI_VLLM_VL_MODEL="${LLMMUI_VLLM_VL_MODEL:-qwen-vl-model}"
export LLMMUI_VLLM_TEXT_MODEL="${LLMMUI_VLLM_TEXT_MODEL:-qwen-text-model}"

cd "$PROJECT_ROOT"

echo "[INFO] project_root=$PROJECT_ROOT"
echo "[INFO] processed_root=$PROCESSED_ROOT"
echo "[INFO] vl_url=$LLMMUI_VLLM_VL_URL"
echo "[INFO] text_url=$LLMMUI_VLLM_TEXT_URL"

python3 scripts/experiments/test_vllm_connectivity.py
bash run_full_pipeline.sh phase3_v2 "$PROCESSED_ROOT" --force
