#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive judge-label annotation tool.

Behavior:
- Traverse one app dir or processed root
- Open each chain_*.png
- Annotate in terminal:
    1 = COMPLIANT (合规)
    0 = NON_COMPLIANT (不合规)
- Save/update per-app labels_judge.json immediately

Output schema (per chain):
{
  "chain_id": 0,
  "image": "chain_0.png",
  "label": 1,
  "label_text": "COMPLIANT",
  "annotator": "",
  "annotated_at": "2026-03-12T20:00:00",
  "note": ""
}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple

LABEL_FILENAME = "labels_judge.json"


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def parse_chain_id_from_name(filename: str) -> int:
    m = re.match(r"chain_(\d+)\.png$", filename)
    return int(m.group(1)) if m else -1


def parse_chain_id(item: Dict[str, Any], fallback: int) -> int:
    try:
        return int(item.get("chain_id", fallback))
    except Exception:
        return fallback


def open_image(path: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path])
        elif sys.platform == "win32":
            subprocess.Popen(["start", path], shell=True)
    except Exception as exc:
        print(f"[WARN] failed to open image: {exc}")


def iter_app_dirs(target: str) -> List[str]:
    if not os.path.exists(target):
        return []

    # single app mode
    if any(name.startswith("chain_") and name.endswith(".png") for name in os.listdir(target) if os.path.isfile(os.path.join(target, name))):
        return [target]

    out: List[str] = []
    for name in sorted(os.listdir(target)):
        app_dir = os.path.join(target, name)
        if not os.path.isdir(app_dir):
            continue
        if any(
            filename.startswith("chain_") and filename.endswith(".png")
            for filename in os.listdir(app_dir)
            if os.path.isfile(os.path.join(app_dir, filename))
        ):
            out.append(app_dir)
    return out


def list_chain_images(app_dir: str) -> List[Tuple[int, str]]:
    pairs: List[Tuple[int, str]] = []
    for name in os.listdir(app_dir):
        cid = parse_chain_id_from_name(name)
        if cid >= 0:
            pairs.append((cid, name))
    pairs.sort(key=lambda x: x[0])
    return pairs


def normalize_existing_record(item: Dict[str, Any], fallback_chain_id: int, fallback_image: str) -> Dict[str, Any]:
    chain_id = parse_chain_id(item, fallback_chain_id)
    image = str(item.get("image", fallback_image))

    # compatible conversion from old schema
    if "label" in item and str(item.get("label")) in {"0", "1"}:
        label = int(item.get("label"))
    elif isinstance(item.get("gt_is_violation"), bool):
        # old meaning: True=violation -> non-compliant(0), False=compliant(1)
        label = 0 if item.get("gt_is_violation") else 1
    else:
        label = None

    label_text = ""
    if label == 1:
        label_text = "COMPLIANT"
    elif label == 0:
        label_text = "NON_COMPLIANT"

    return {
        "chain_id": chain_id,
        "image": image,
        "label": label,
        "label_text": label_text,
        "annotator": str(item.get("annotator", "")),
        "annotated_at": str(item.get("annotated_at", "")),
        "note": str(item.get("note", "")),
    }


def load_existing_map(app_dir: str) -> Dict[int, Dict[str, Any]]:
    path = os.path.join(app_dir, LABEL_FILENAME)
    data = as_list(load_json(path))
    out: Dict[int, Dict[str, Any]] = {}
    for idx, raw in enumerate(data):
        item = as_dict(raw)
        if not item:
            continue
        cid = parse_chain_id(item, idx)
        img = str(item.get("image", f"chain_{cid}.png"))
        out[cid] = normalize_existing_record(item, cid, img)
    return out


def save_labels(app_dir: str, records: List[Dict[str, Any]]) -> None:
    path = os.path.join(app_dir, LABEL_FILENAME)
    records = sorted(records, key=lambda x: int(x.get("chain_id", -1)))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def ensure_record(existing_map: Dict[int, Dict[str, Any]], chain_id: int, image_name: str) -> Dict[str, Any]:
    if chain_id in existing_map:
        rec = dict(existing_map[chain_id])
        rec["chain_id"] = chain_id
        rec["image"] = image_name
        if "label" not in rec:
            rec["label"] = None
        if "label_text" not in rec:
            rec["label_text"] = ""
        if "annotator" not in rec:
            rec["annotator"] = ""
        if "annotated_at" not in rec:
            rec["annotated_at"] = ""
        if "note" not in rec:
            rec["note"] = ""
        return rec

    return {
        "chain_id": chain_id,
        "image": image_name,
        "label": None,
        "label_text": "",
        "annotator": "",
        "annotated_at": "",
        "note": "",
    }


def parse_label_input(user_input: str) -> int | None:
    s = user_input.strip()
    if s in {"0", "1"}:
        return int(s)
    return None


def label_one_app(app_dir: str, annotator: str = "", relabel: bool = False, no_open: bool = False) -> Tuple[int, int]:
    app_name = os.path.basename(app_dir)
    chain_pairs = list_chain_images(app_dir)
    if not chain_pairs:
        return 0, 0

    existing_map = load_existing_map(app_dir)
    working: Dict[int, Dict[str, Any]] = {}

    for chain_id, image_name in chain_pairs:
        working[chain_id] = ensure_record(existing_map, chain_id, image_name)

    idx = 0
    total = len(chain_pairs)
    print(f"\n[APP] {app_name} chains={total}")
    print("输入: 1=合规, 0=不合规, s=跳过, b=上一条, q=退出当前app")

    while idx < total:
        chain_id, image_name = chain_pairs[idx]
        rec = working[chain_id]

        if (rec.get("label") in {0, 1}) and (not relabel):
            idx += 1
            continue

        image_path = os.path.join(app_dir, image_name)
        if not no_open:
            open_image(image_path)

        old_label = rec.get("label")
        old_show = "未标注" if old_label not in {0, 1} else f"{old_label} ({rec.get('label_text', '')})"
        print(f"\n[{idx + 1}/{total}] chain_id={chain_id} image={image_name} 当前={old_show}")

        user = input("label> ").strip().lower()
        if user == "q":
            break
        if user == "b":
            idx = max(0, idx - 1)
            continue
        if user == "s" or user == "":
            idx += 1
            continue

        label = parse_label_input(user)
        if label is None:
            print("[WARN] 无效输入，请输入 1 / 0 / s / b / q")
            continue

        rec["label"] = label
        rec["label_text"] = "COMPLIANT" if label == 1 else "NON_COMPLIANT"
        rec["annotated_at"] = datetime.now().isoformat(timespec="seconds")
        if annotator and not str(rec.get("annotator", "")).strip():
            rec["annotator"] = annotator

        save_labels(app_dir, list(working.values()))
        print(f"[SAVED] chain_id={chain_id} label={label} ({rec['label_text']})")
        idx += 1

    save_labels(app_dir, list(working.values()))

    labeled = sum(1 for x in working.values() if x.get("label") in {0, 1})
    return total, labeled


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive labeling tool for compliance judgement (0/1)")
    parser.add_argument(
        "target",
        nargs="?",
        default=os.path.join("data", "processed"),
        help="processed root or one app dir (default: data/processed)",
    )
    parser.add_argument("--annotator", default="", help="annotator name")
    parser.add_argument("--relabel", action="store_true", help="relabel chains even if already labeled")
    parser.add_argument("--no-open", action="store_true", help="do not open image viewer")
    args = parser.parse_args()

    app_dirs = iter_app_dirs(args.target)
    if not app_dirs:
        print(f"[WARN] no app dirs found: {args.target}")
        return

    apps_done = 0
    chains_total = 0
    labeled_total = 0

    for app_dir in app_dirs:
        total, labeled = label_one_app(
            app_dir=app_dir,
            annotator=args.annotator,
            relabel=args.relabel,
            no_open=args.no_open,
        )
        if total == 0:
            continue

        apps_done += 1
        chains_total += total
        labeled_total += labeled
        print(f"[DONE] app={os.path.basename(app_dir)} labeled={labeled}/{total} file={os.path.join(app_dir, LABEL_FILENAME)}")

    print("\n========== labels_judge interactive summary ==========")
    print(f"apps_processed: {apps_done}")
    print(f"chains_total  : {chains_total}")
    print(f"labeled_total : {labeled_total}")
    print("====================================================")


if __name__ == "__main__":
    main()
