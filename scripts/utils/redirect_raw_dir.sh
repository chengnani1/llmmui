#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEFAULT_RAW_DIR="${REPO_ROOT}/data/raw"

usage() {
  echo "Usage: $0 <target_raw_dir> [source_raw_dir]"
  echo "Example: $0 /Volumes/Charon/data/code/llm_ui/code/data/0320/rawdata"
}

if [[ "${1:-}" == "" ]]; then
  usage
  exit 1
fi

TARGET_RAW_DIR="$1"
SOURCE_RAW_DIR="${2:-$DEFAULT_RAW_DIR}"

mkdir -p "$TARGET_RAW_DIR"

if [[ -L "$SOURCE_RAW_DIR" ]]; then
  CURRENT_TARGET="$(readlink "$SOURCE_RAW_DIR")"
  echo "source is already a symlink: $SOURCE_RAW_DIR -> $CURRENT_TARGET"
  exit 0
fi

if [[ -d "$SOURCE_RAW_DIR" ]]; then
  echo "sync existing data from $SOURCE_RAW_DIR -> $TARGET_RAW_DIR"
  rsync -a "$SOURCE_RAW_DIR"/ "$TARGET_RAW_DIR"/

  BACKUP_DIR="${SOURCE_RAW_DIR}.bak.$(date +%Y%m%d_%H%M%S)"
  echo "move original directory to backup: $BACKUP_DIR"
  mv "$SOURCE_RAW_DIR" "$BACKUP_DIR"
else
  mkdir -p "$(dirname "$SOURCE_RAW_DIR")"
fi

echo "create symlink: $SOURCE_RAW_DIR -> $TARGET_RAW_DIR"
ln -s "$TARGET_RAW_DIR" "$SOURCE_RAW_DIR"

echo "done"
echo "raw dir now points to: $(readlink "$SOURCE_RAW_DIR")"
