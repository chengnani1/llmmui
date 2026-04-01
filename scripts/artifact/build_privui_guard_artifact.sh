#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE_ROOT="$REPO_ROOT/scripts/artifact/templates"
TARGET_ROOT="${1:-/Volumes/Charon/data/code/llm_ui/code/data/artifact/PrivUI-Guard_artifact}"

SRC_RQ1="/Volumes/Charon/data/code/llm_ui/code/data/rq1/processed"
SRC_RQ2="/Volumes/Charon/data/code/llm_ui/code/data/rq2/processed"
SRC_RQ3="/Volumes/Charon/data/code/llm_ui/code/data/rq3/processed"

copy_tree() {
  local src="$1"
  local dst="$2"
  mkdir -p "$dst"
  rsync -a --delete \
    --exclude '._*' \
    --exclude '.DS_Store' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "$src"/ "$dst"/
}

copy_file() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "$dst")"
  install -m 0644 "$src" "$dst"
}

copy_exec() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "$dst")"
  install -m 0755 "$src" "$dst"
}

sanitize_dataset_root() {
  local dataset_root="$1"
  local child=""

  find "$dataset_root" -maxdepth 1 -type f -delete

  for child in "$dataset_root"/*; do
    if [[ ! -e "$child" ]]; then
      continue
    fi
    if [[ -d "$child" ]]; then
      case "$(basename "$child")" in
        fastbot-*)
          ;;
        *)
          rm -rf "$child"
          ;;
      esac
    fi
  done
}

cleanup_target() {
  local rel
  local remove_list=(
    "README.md"
    "requirements.txt"
    "environment.yml"
    "ANONYMITY.md"
    "configs"
    "prompts"
    "scripts"
    "src"
    "lib"
    "docs"
    "data"
    "results"
    "experience"
    "run_eval.sh"
    "run_project.sh"
    "run_full_pipeline.sh"
  )
  for rel in "${remove_list[@]}"; do
    rm -rf "$TARGET_ROOT/$rel"
  done
}

main() {
  mkdir -p "$TARGET_ROOT"

  cleanup_target

  mkdir -p \
    "$TARGET_ROOT/data" \
    "$TARGET_ROOT/results" \
    "$TARGET_ROOT/docs" \
    "$TARGET_ROOT/experience"

  copy_tree "$REPO_ROOT/src" "$TARGET_ROOT/src"
  copy_tree "$REPO_ROOT/lib" "$TARGET_ROOT/lib"
  copy_tree "$REPO_ROOT/docs" "$TARGET_ROOT/docs"

  copy_tree "$SRC_RQ1" "$TARGET_ROOT/data/benchmark_processed"
  copy_tree "$SRC_RQ2" "$TARGET_ROOT/data/independent_processed"
  copy_tree "$SRC_RQ3" "$TARGET_ROOT/data/large_scale_processed"

  sanitize_dataset_root "$TARGET_ROOT/data/benchmark_processed"
  sanitize_dataset_root "$TARGET_ROOT/data/independent_processed"
  sanitize_dataset_root "$TARGET_ROOT/data/large_scale_processed"

  copy_tree "$TEMPLATE_ROOT/experience" "$TARGET_ROOT/experience"
  copy_file "$TEMPLATE_ROOT/README.md" "$TARGET_ROOT/README.md"
  copy_exec "$TEMPLATE_ROOT/run_eval.sh" "$TARGET_ROOT/run_eval.sh"
  copy_exec "$TEMPLATE_ROOT/run_project.sh" "$TARGET_ROOT/run_project.sh"
  copy_exec "$REPO_ROOT/run_full_pipeline.sh" "$TARGET_ROOT/run_full_pipeline.sh"
  copy_file "$REPO_ROOT/requirements.txt" "$TARGET_ROOT/requirements.txt"

  cat >"$TARGET_ROOT/data/DATASET_MAPPING.md" <<'EOF'
# Dataset Mapping

The artifact packages three processed datasets and names them by paper role:

- `data/benchmark_processed`: benchmark dataset for effectiveness and ablation
- `data/independent_processed`: held-out dataset for generalization
- `data/large_scale_processed`: large-scale dataset for real-world analysis

This file intentionally avoids machine-specific source paths.
EOF

  find "$TARGET_ROOT" -name '._*' -exec rm -f {} + 2>/dev/null || true
  find "$TARGET_ROOT" -name '.DS_Store' -exec rm -f {} + 2>/dev/null || true

  echo "[DONE] Artifact rebuilt at: $TARGET_ROOT"
  echo "[INFO] Benchmark data      -> $TARGET_ROOT/data/benchmark_processed"
  echo "[INFO] Independent data    -> $TARGET_ROOT/data/independent_processed"
  echo "[INFO] Large-scale data    -> $TARGET_ROOT/data/large_scale_processed"
  echo "[INFO] Project code        -> $TARGET_ROOT/src"
  echo "[INFO] Fastbot libraries   -> $TARGET_ROOT/lib"
  echo "[INFO] Experiment scripts  -> $TARGET_ROOT/experience"
}

main "$@"
