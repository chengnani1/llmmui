# -*- coding: utf-8 -*-
"""
Phase3 Step2: rule-based permission recognition.

Input:
  <processed>/<app>/result.json

Output:
  <processed>/<app>/result_permission.json
"""

import os
import sys
import json
import re
from typing import Dict, Any, List, Optional, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.schema_utils import (  # noqa: E402
    normalize_permission_name,
    validate_permission_results,
)
from configs import settings  # noqa: E402
from configs.domain.permission_config import BASE_PERMISSION_TABLE  # noqa: E402
from utils.validators import validate_result_json_chains  # noqa: E402


DEFAULT_ROOT_DIR = settings.DATA_PROCESSED_DIR
VENDOR = os.getenv("PERMISSION_VENDOR", "MI")
WIDGET_SCORE_THRESHOLD = float(os.getenv("WIDGET_SCORE_THRESHOLD", "10.0"))
OUTPUT_FILENAME = "result_permission.json"

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

    normalized = [normalize_permission_name(x) for x in matched]
    normalized = sorted(set(normalized))
    return normalized

# =========================================================
# Process one app
# =========================================================

def process_one_app(app_dir: str, chain_ids: Optional[Set[int]] = None) -> Tuple[int, int]:
    print(f"[Permission-Rule] start app={app_dir}")

    result_json = os.path.join(app_dir, "result.json")
    print("  has result.json:", os.path.exists(result_json))

    if not os.path.exists(result_json):
        print("  ❌ skip (no result.json)")
        return 0, 0

    with open(result_json, "r", encoding="utf-8") as f:
        chains = validate_result_json_chains(json.load(f))

    outputs = []
    invalid_outputs = 0

    for idx, ui_item in enumerate(chains):
        chain_id = ui_item.get("chain_id", idx)
        try:
            chain_id = int(chain_id)
        except Exception:
            chain_id = idx
        if chain_ids is not None and chain_id not in chain_ids:
            continue
        try:
            perms = recognize_permissions_rule_only(ui_item)
        except Exception as exc:
            perms = []
            invalid_outputs += 1
            print(f"[Permission-Rule][WARN] chain failed chain_id={chain_id}: {exc}")

        outputs.append({
            "chain_id": chain_id,
            "predicted_permissions": perms,
            "permission_source": "rule",
            "files": {
                "before": ((ui_item.get("ui_before_grant") or {}).get("file") or ""),
                "granting": [g.get("file", "") for g in ui_item.get("ui_granting", []) if isinstance(g, dict)],
                "after": ((ui_item.get("ui_after_grant") or {}).get("file") or ""),
            }
        })

        print(f"  [Rule] chain {chain_id}: {perms}")

    normalized, dropped = validate_permission_results(outputs)
    invalid_outputs += dropped

    out_path = os.path.join(app_dir, OUTPUT_FILENAME)
    print("  WRITE TO:", out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    print(
        f"[Permission-Rule] finish app={app_dir} chains={len(chains)} "
        f"written={len(normalized)} invalid={invalid_outputs} out={out_path}"
    )
    return len(normalized), invalid_outputs

# =========================================================
# Main (FORCE RUN)
# =========================================================

def run(root_dir: str, chain_ids: Optional[List[int]] = None):
    print(f"[Permission-Rule] start target={root_dir}")

    assert os.path.exists(root_dir), f"ROOT_DIR not exist: {root_dir}"

    chain_filter: Optional[Set[int]] = None
    if chain_ids:
        chain_filter = {int(x) for x in chain_ids}

    if os.path.exists(os.path.join(root_dir, "result.json")):
        process_one_app(root_dir, chain_ids=chain_filter)
        print("[Permission-Rule] all_done")
        return

    total = 0
    invalid = 0
    for d in sorted(os.listdir(root_dir)):
        app_dir = os.path.join(root_dir, d)
        print(f"[Permission-Rule] scan app={app_dir}")

        if not os.path.isdir(app_dir):
            print("[Permission-Rule] skip non-dir")
            continue

        try:
            c, i = process_one_app(app_dir, chain_ids=chain_filter)
            total += c
            invalid += i
        except Exception as exc:
            print(f"[Permission-Rule][WARN] app failed {app_dir}: {exc}")

    print(f"[Permission-Rule] all_done chains={total} invalid={invalid}")

# =========================================================
# Entry
# =========================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rule-only permission recognition")
    parser.add_argument("--root", default=os.getenv("LLMMUI_PROCESSED_DIR", os.getenv("DATA_PROCESSED_DIR", DEFAULT_ROOT_DIR)))
    parser.add_argument("--chain-ids", default="", help="comma-separated chain ids, e.g. 1,3,9")
    args = parser.parse_args()
    chain_ids: List[int] = []
    if args.chain_ids.strip():
        for seg in args.chain_ids.split(","):
            seg = seg.strip()
            if not seg:
                continue
            try:
                chain_ids.append(int(seg))
            except Exception:
                continue
    run(args.root, chain_ids=chain_ids or None)
