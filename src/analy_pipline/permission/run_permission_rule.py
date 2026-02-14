# -*- coding: utf-8 -*-
"""
Pure rule-based permission recognition (DEBUG / FIXED VERSION)

Input :
  /Volumes/Charon/data/code/llm_ui/code/data/version2.11.5/processed/<app>/result.json

Output:
  /Volumes/Charon/data/code/llm_ui/code/data/version2.11.5/processed/<app>/result_permission_rule.json

One chain -> 0..N permissions
NO LLM involved.
"""

import os
import sys
import json
import re
from typing import Dict, Any, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from configs import settings
from configs.domain.permission_config import BASE_PERMISSION_TABLE


# =========================================================
# 🔒 HARD-CODED CONFIG (DEBUG PURPOSE)
# =========================================================

DEFAULT_ROOT_DIR = settings.DATA_PROCESSED_DIR
VENDOR = os.getenv("PERMISSION_VENDOR", "MI")
WIDGET_SCORE_THRESHOLD = float(os.getenv("WIDGET_SCORE_THRESHOLD", "10.0"))

# =========================================================
# Text normalization
# =========================================================

def normalize_text(t: str) -> str:
    if not t:
        return ""
    t = re.sub(r"\s+", "", str(t))
    return t.lower()

# =========================================================
# Evidence collection
# =========================================================

def collect_texts_from_ui(ui: Dict[str, Any]) -> List[str]:
    """
    Collect textual evidence from one UI item.
    Priority:
      1. widget.text (high confidence)
      2. OCR text     (fallback)
    """
    texts = []

    feature = ui.get("feature", {}) or {}

    # ---- widgets (high confidence) ----
    for w in feature.get("widgets", []):
        score = w.get("score", 0)
        txt = w.get("text", "")
        if txt and score >= WIDGET_SCORE_THRESHOLD:
            texts.append(txt)

    # ---- OCR text (fallback) ----
    ocr_text = feature.get("text", "")
    if isinstance(ocr_text, str) and ocr_text.strip():
        texts.append(ocr_text)

    return texts


def collect_chain_texts(ui_item: Dict[str, Any]) -> List[str]:
    """
    Collect texts from before + granting + after
    """
    texts = []

    texts.extend(collect_texts_from_ui(ui_item.get("ui_before_grant", {})))

    for g in ui_item.get("ui_granting", []):
        texts.extend(collect_texts_from_ui(g))

    texts.extend(collect_texts_from_ui(ui_item.get("ui_after_grant", {})))

    return texts

# =========================================================
# Rule-only permission recognition
# =========================================================

def recognize_permissions_rule_only(ui_item: Dict[str, Any]) -> List[str]:
    perm_table = BASE_PERMISSION_TABLE.get(VENDOR)
    if perm_table is None:
        perm_table = BASE_PERMISSION_TABLE["MI"]

    raw_texts = collect_chain_texts(ui_item)
    norm_texts = [normalize_text(t) for t in raw_texts if t]

    matched = set()

    for zh_keyword, perms in perm_table.items():
        pat = normalize_text(zh_keyword)
        if not pat:
            continue
        for t in norm_texts:
            if pat in t:
                for p in perms:
                    matched.add(p)
                break

    return sorted(matched)

# =========================================================
# Process one app
# =========================================================

def process_one_app(app_dir: str):
    print(f"\n📌 PROCESS APP DIR: {app_dir}")

    result_json = os.path.join(app_dir, "result.json")
    print("  has result.json:", os.path.exists(result_json))

    if not os.path.exists(result_json):
        print("  ❌ skip (no result.json)")
        return

    with open(result_json, "r", encoding="utf-8") as f:
        chains = json.load(f)

    outputs = []

    for idx, ui_item in enumerate(chains):
        chain_id = ui_item.get("chain_id", idx)
        perms = recognize_permissions_rule_only(ui_item)

        outputs.append({
            "chain_id": chain_id,
            "predicted_permissions": perms,
            "files": {
                "before": ui_item["ui_before_grant"]["file"],
                "granting": [g["file"] for g in ui_item.get("ui_granting", [])],
                "after": ui_item["ui_after_grant"]["file"]
            }
        })

        print(f"  [Rule] chain {chain_id}: {perms}")

    out_path = os.path.join(app_dir, "result_permission_rule.json")
    print("  WRITE TO:", out_path)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=2, ensure_ascii=False)

    print("  ✅ WRITE DONE")

# =========================================================
# Main (FORCE RUN)
# =========================================================

def run(root_dir: str):
    print("🚀 RULE-ONLY PERMISSION RECOGNITION")
    print("📂 ROOT_DIR =", root_dir)

    assert os.path.exists(root_dir), f"ROOT_DIR not exist: {root_dir}"

    if os.path.exists(os.path.join(root_dir, "result.json")):
        process_one_app(root_dir)
        print("\n🎉 DONE")
        return

    for d in sorted(os.listdir(root_dir)):
        app_dir = os.path.join(root_dir, d)
        print("\nCHECK:", app_dir)

        if not os.path.isdir(app_dir):
            print("  ❌ not a directory")
            continue

        process_one_app(app_dir)

    print("\n🎉 ALL DONE")

# =========================================================
# Entry
# =========================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rule-only permission recognition")
    parser.add_argument("--root", default=os.getenv("DATA_PROCESSED_DIR", DEFAULT_ROOT_DIR))
    args = parser.parse_args()

    run(args.root)
