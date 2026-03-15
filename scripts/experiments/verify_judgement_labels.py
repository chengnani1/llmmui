#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual risk labeling tool (binary GT).

What this script supports:
1) Interactive labeling (open chain image, label risk/not-risk)
2) Initialize template labels with all chains set to risky (gt_risk=1)
3) Optional reset: delete existing label_judge.json before labeling

Output file (per app):
  label_judge.json

Schema (per chain):
{
  "chain_id": 0,
  "image": "chain_0.png",
  "gt_risk": 1,
  "gt_label": "RISKY",
  "annotator": "",
  "annotated_at": "",
  "note": "",
  "pred": {
    "final_decision": "CLEARLY_RISKY|NEED_REVIEW|CLEARLY_OK",
    "final_risk": "HIGH|MEDIUM|LOW"
  }
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
from typing import Any, Dict, List, Optional, Tuple


PRED_FILENAME = "result_final_decision.json"
LABEL_FILENAME = "label_judge.json"


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def save_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


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

    if os.path.isdir(target) and (
        os.path.exists(os.path.join(target, PRED_FILENAME))
        or any(re.match(r"^chain_\d+\.png$", x) for x in os.listdir(target))
    ):
        return [target]

    out: List[str] = []
    for name in sorted(os.listdir(target)):
        app_dir = os.path.join(target, name)
        if not os.path.isdir(app_dir):
            continue
        has_pred = os.path.exists(os.path.join(app_dir, PRED_FILENAME))
        has_chain = any(re.match(r"^chain_\d+\.png$", x) for x in os.listdir(app_dir))
        if has_pred or has_chain:
            out.append(app_dir)
    return out


def parse_chain_id(name: str) -> int:
    m = re.match(r"^chain_(\d+)\.png$", name)
    return int(m.group(1)) if m else -1


def list_chain_ids_from_images(app_dir: str) -> List[int]:
    ids: List[int] = []
    for name in os.listdir(app_dir):
        cid = parse_chain_id(name)
        if cid >= 0:
            ids.append(cid)
    return sorted(set(ids))


def load_pred_map(app_dir: str) -> Dict[int, Dict[str, str]]:
    path = os.path.join(app_dir, PRED_FILENAME)
    if not os.path.exists(path):
        return {}
    data = as_list(load_json(path))
    out: Dict[int, Dict[str, str]] = {}
    for idx, raw in enumerate(data):
        item = as_dict(raw)
        if not item:
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            cid = idx
        out[cid] = {
            "final_decision": str(item.get("final_decision", "")),
            "final_risk": str(item.get("final_risk", "")),
        }
    return out


def load_existing_map(app_dir: str) -> Dict[int, Dict[str, Any]]:
    path = os.path.join(app_dir, LABEL_FILENAME)
    data = as_list(load_json(path))
    out: Dict[int, Dict[str, Any]] = {}
    for idx, raw in enumerate(data):
        item = as_dict(raw)
        if not item:
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            cid = idx
        gt = item.get("gt_risk")
        if str(gt) in {"0", "1"}:
            gt = int(gt)
        else:
            gt = None
        out[cid] = {
            "chain_id": cid,
            "image": str(item.get("image", f"chain_{cid}.png")),
            "gt_risk": gt,
            "gt_label": "RISKY" if gt == 1 else ("SAFE" if gt == 0 else ""),
            "annotator": str(item.get("annotator", "")),
            "annotated_at": str(item.get("annotated_at", "")),
            "note": str(item.get("note", "")),
            "pred": as_dict(item.get("pred")),
        }
    return out


def reset_label_file(app_dir: str) -> bool:
    path = os.path.join(app_dir, LABEL_FILENAME)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def build_working_records(
    app_dir: str,
    existing_map: Dict[int, Dict[str, Any]],
    pred_map: Dict[int, Dict[str, str]],
) -> List[Dict[str, Any]]:
    chain_ids = sorted(set(list_chain_ids_from_images(app_dir)) | set(pred_map.keys()) | set(existing_map.keys()))
    out: List[Dict[str, Any]] = []
    for cid in chain_ids:
        if cid in existing_map:
            rec = dict(existing_map[cid])
        else:
            rec = {
                "chain_id": cid,
                "image": f"chain_{cid}.png",
                "gt_risk": None,
                "gt_label": "",
                "annotator": "",
                "annotated_at": "",
                "note": "",
                "pred": {},
            }
        rec["chain_id"] = cid
        rec["image"] = f"chain_{cid}.png"
        rec["pred"] = pred_map.get(cid, {})
        out.append(rec)
    out.sort(key=lambda x: int(x["chain_id"]))
    return out


def apply_label(rec: Dict[str, Any], gt_risk: int, annotator: str) -> None:
    rec["gt_risk"] = int(gt_risk)
    rec["gt_label"] = "RISKY" if int(gt_risk) == 1 else "SAFE"
    rec["annotated_at"] = datetime.now().isoformat(timespec="seconds")
    if annotator:
        rec["annotator"] = annotator


def save_records(app_dir: str, records: List[Dict[str, Any]]) -> None:
    path = os.path.join(app_dir, LABEL_FILENAME)
    records = sorted(records, key=lambda x: int(x.get("chain_id", -1)))
    save_json(path, records)


def init_all_risky(app_dir: str, annotator: str, force: bool) -> Tuple[int, int]:
    existing_map = {} if force else load_existing_map(app_dir)
    pred_map = load_pred_map(app_dir)
    records = build_working_records(app_dir, existing_map, pred_map)
    for rec in records:
        apply_label(rec, gt_risk=1, annotator=annotator)
    save_records(app_dir, records)
    return len(records), len(records)


def parse_input(user: str) -> Optional[int]:
    s = user.strip().lower()
    if s == "1":
        return 1
    if s in {"0", ""}:
        return 0
    return None


def interactive_label(app_dir: str, annotator: str, skip_labeled: bool, no_open: bool) -> Tuple[int, int]:
    existing_map = load_existing_map(app_dir)
    pred_map = load_pred_map(app_dir)
    records = build_working_records(app_dir, existing_map, pred_map)
    if not records:
        return 0, 0

    app_name = os.path.basename(app_dir)
    print(f"\n[APP] {app_name} chains={len(records)}")
    print("输入: 1=有风险, 0/回车=无风险(默认), s=跳过, b=上一条, q=退出当前app")

    idx = 0
    while idx < len(records):
        rec = records[idx]
        gt = rec.get("gt_risk")
        if (gt in {0, 1}) and skip_labeled:
            idx += 1
            continue

        cid = int(rec["chain_id"])
        image_path = os.path.join(app_dir, rec.get("image", f"chain_{cid}.png"))
        if (not no_open) and os.path.exists(image_path):
            open_image(image_path)

        old = rec.get("gt_risk")
        old_show = "未标注" if old not in {0, 1} else f"{old} ({rec.get('gt_label', '')})"
        pred = as_dict(rec.get("pred"))
        pred_text = ""
        if pred:
            pred_text = f" pred={pred.get('final_decision','')}/{pred.get('final_risk','')}"

        print(f"\n[{idx + 1}/{len(records)}] chain_id={cid} image={rec.get('image')}{pred_text}")
        print(f"当前标注: {old_show}")

        user = input("label> ").strip().lower()
        if user == "q":
            break
        if user == "b":
            idx = max(0, idx - 1)
            continue
        if user == "s":
            idx += 1
            continue

        gt_risk = parse_input(user)
        if gt_risk is None:
            print("[WARN] 无效输入，请输入 1 / 0 / 回车 / s / b / q")
            continue

        apply_label(rec, gt_risk=gt_risk, annotator=annotator)
        save_records(app_dir, records)
        print(f"[SAVED] chain_id={cid} gt_risk={gt_risk} ({rec['gt_label']})")
        idx += 1

    save_records(app_dir, records)
    labeled = sum(1 for x in records if x.get("gt_risk") in {0, 1})
    return len(records), labeled


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual risk labeling for label_judge.json")
    parser.add_argument(
        "target",
        nargs="?",
        default=os.path.join("data", "processed"),
        help="processed root or one app dir (default: data/processed)",
    )
    parser.add_argument("--annotator", default="", help="annotator name")
    parser.add_argument(
        "--skip-labeled",
        action="store_true",
        help="interactive mode: skip chains already labeled in existing label_judge.json",
    )
    parser.add_argument("--no-open", action="store_true", help="do not open image viewer")
    parser.add_argument(
        "--mode",
        choices=["interactive", "init-all-risky"],
        default="interactive",
        help="interactive=命令行标注; init-all-risky=全部链默认标为有风险(1)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="init-all-risky 模式下忽略已有标注并覆盖",
    )
    parser.add_argument(
        "--reset-existing",
        action="store_true",
        help="先删除每个 app 目录里已有的 label_judge.json",
    )
    args = parser.parse_args()

    app_dirs = iter_app_dirs(args.target)
    if not app_dirs:
        print(f"[WARN] no app dirs found: {args.target}")
        return

    reset_count = 0
    if args.reset_existing:
        for app_dir in app_dirs:
            if reset_label_file(app_dir):
                reset_count += 1
        print(f"[RESET] removed {reset_count} existing {LABEL_FILENAME} files")

    apps_done = 0
    chains_total = 0
    labeled_total = 0

    for app_dir in app_dirs:
        if args.mode == "init-all-risky":
            total, labeled = init_all_risky(app_dir, annotator=args.annotator, force=args.force)
        else:
            total, labeled = interactive_label(
                app_dir=app_dir,
                annotator=args.annotator,
                skip_labeled=args.skip_labeled,
                no_open=args.no_open,
            )

        if total == 0:
            continue
        apps_done += 1
        chains_total += total
        labeled_total += labeled
        print(f"[DONE] app={os.path.basename(app_dir)} labeled={labeled}/{total} file={os.path.join(app_dir, LABEL_FILENAME)}")

    print("\n========== label_judge summary ==========")
    print(f"mode         : {args.mode}")
    print(f"apps_processed: {apps_done}")
    print(f"chains_total  : {chains_total}")
    print(f"labeled_total : {labeled_total}")
    print("========================================")


if __name__ == "__main__":
    main()
