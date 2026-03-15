#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate direct VLM risk predictions against label_judge.json.

Prediction file per app:
  result_vlm_direct_risk.json

Ground-truth file per app:
  label_judge.json (or labels_judge.json as fallback)
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_PRED_FILE = "result_vlm_direct_risk.json"
DEFAULT_GT_FILE = "label_judge.json"
DEFAULT_OUT_FILE = "vlm_direct_risk_eval.json"


@dataclass
class Counter:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    missing_pred: int = 0
    missing_gt: int = 0
    skipped: int = 0

    @property
    def evaluated(self) -> int:
        return self.tp + self.fp + self.tn + self.fn


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _map_by_chain(items: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for idx, raw in enumerate(items):
        item = _as_dict(raw)
        if not item:
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            cid = idx
        if cid not in out:
            out[cid] = item
    return out


def _pred_to_binary(item: Dict[str, Any]) -> Optional[int]:
    v = item.get("pred_risk")
    if str(v) in {"0", "1"}:
        return int(v)

    label = str(item.get("pred_label", "")).strip().upper()
    if label == "SAFE":
        return 0
    if label == "RISKY":
        return 1
    return None


def _gt_to_binary(item: Dict[str, Any]) -> Optional[int]:
    for key in ("gt_risk", "label"):
        v = item.get(key)
        if str(v) in {"0", "1"}:
            return int(v)

    text = str(item.get("gt_label", "")).strip().upper()
    if text in {"SAFE", "无风险"}:
        return 0
    if text in {"RISKY", "有风险"}:
        return 1
    return None


def _merge_counter(a: Counter, b: Counter) -> Counter:
    return Counter(
        tp=a.tp + b.tp,
        fp=a.fp + b.fp,
        tn=a.tn + b.tn,
        fn=a.fn + b.fn,
        missing_pred=a.missing_pred + b.missing_pred,
        missing_gt=a.missing_gt + b.missing_gt,
        skipped=a.skipped + b.skipped,
    )


def _resolve_gt_path(app_dir: str, gt_file: str) -> str:
    p0 = os.path.join(app_dir, gt_file)
    if os.path.exists(p0):
        return p0
    if gt_file == "label_judge.json":
        p1 = os.path.join(app_dir, "labels_judge.json")
        if os.path.exists(p1):
            return p1
    return p0


def eval_app(app_dir: str, pred_file: str, gt_file: str) -> Tuple[Counter, Dict[str, Any]]:
    pred_path = os.path.join(app_dir, pred_file)
    gt_path = _resolve_gt_path(app_dir, gt_file)

    pred_map = _map_by_chain(_as_list(_load_json(pred_path)))
    gt_map = _map_by_chain(_as_list(_load_json(gt_path)))

    c = Counter()
    chain_ids = sorted(set(pred_map.keys()) | set(gt_map.keys()))
    fp_chain_ids: List[int] = []
    fn_chain_ids: List[int] = []

    for cid in chain_ids:
        pred_item = pred_map.get(cid)
        gt_item = gt_map.get(cid)
        if pred_item is None:
            c.missing_pred += 1
            continue
        if gt_item is None:
            c.missing_gt += 1
            continue

        pred = _pred_to_binary(pred_item)
        gt = _gt_to_binary(gt_item)
        if gt is None:
            c.missing_gt += 1
            continue
        if pred is None:
            c.skipped += 1
            continue

        if pred == 1 and gt == 1:
            c.tp += 1
        elif pred == 1 and gt == 0:
            c.fp += 1
            fp_chain_ids.append(cid)
        elif pred == 0 and gt == 0:
            c.tn += 1
        else:
            c.fn += 1
            fn_chain_ids.append(cid)

    evaluated = c.evaluated
    precision = _safe_div(c.tp, c.tp + c.fp)
    recall = _safe_div(c.tp, c.tp + c.fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    accuracy = _safe_div(c.tp + c.tn, evaluated)
    specificity = _safe_div(c.tn, c.tn + c.fp)
    balanced_accuracy = (recall + specificity) / 2 if evaluated else 0.0

    detail = {
        "app": os.path.basename(app_dir),
        "pred_file": pred_file,
        "gt_file": os.path.basename(gt_path),
        "pred_exists": os.path.exists(pred_path),
        "gt_exists": os.path.exists(gt_path),
        "chains_pred": len(pred_map),
        "chains_gt": len(gt_map),
        "evaluated": evaluated,
        "tp": c.tp,
        "fp": c.fp,
        "tn": c.tn,
        "fn": c.fn,
        "missing_pred": c.missing_pred,
        "missing_gt": c.missing_gt,
        "skipped": c.skipped,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": specificity,
        "balanced_accuracy": balanced_accuracy,
        "fp_chain_ids": fp_chain_ids,
        "fn_chain_ids": fn_chain_ids,
    }
    return c, detail


def _iter_app_dirs(target: str, app_prefix: str) -> Tuple[List[str], str]:
    if os.path.exists(os.path.join(target, "result.json")):
        return [target], target
    out = [
        os.path.join(target, d)
        for d in sorted(os.listdir(target))
        if os.path.isdir(os.path.join(target, d)) and d.startswith(app_prefix)
    ]
    return out, target


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate direct VLM risk results against label_judge.json")
    parser.add_argument("target", nargs="?", default=os.path.join("data", "processed"))
    parser.add_argument("--pred-file", default=DEFAULT_PRED_FILE)
    parser.add_argument("--gt-file", default=DEFAULT_GT_FILE)
    parser.add_argument("--output", default=DEFAULT_OUT_FILE)
    parser.add_argument("--app-prefix", default="fastbot-")
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    if not os.path.exists(target):
        raise SystemExit(f"target not found: {target}")

    app_dirs, out_dir = _iter_app_dirs(target, args.app_prefix)
    if not app_dirs:
        raise SystemExit(f"no app dirs found under: {target}")

    total = Counter()
    per_app: List[Dict[str, Any]] = []
    for app_dir in app_dirs:
        c, detail = eval_app(app_dir, pred_file=args.pred_file, gt_file=args.gt_file)
        total = _merge_counter(total, c)
        per_app.append(detail)

    evaluated = total.evaluated
    precision = _safe_div(total.tp, total.tp + total.fp)
    recall = _safe_div(total.tp, total.tp + total.fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    accuracy = _safe_div(total.tp + total.tn, evaluated)
    specificity = _safe_div(total.tn, total.tn + total.fp)
    balanced_accuracy = (recall + specificity) / 2 if evaluated else 0.0

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target": target,
        "pred_file": args.pred_file,
        "gt_file": args.gt_file,
        "apps_total": len(app_dirs),
        "evaluated_chains": evaluated,
        "confusion": {
            "tp": total.tp,
            "fp": total.fp,
            "tn": total.tn,
            "fn": total.fn,
            "missing_pred": total.missing_pred,
            "missing_gt": total.missing_gt,
            "skipped": total.skipped,
        },
        "metrics": {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "specificity": specificity,
            "balanced_accuracy": balanced_accuracy,
        },
        "per_app": per_app,
    }

    out_path = os.path.join(out_dir, args.output)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("========== VLM Direct Risk Evaluation ==========")
    print(f"apps_total     : {len(app_dirs)}")
    print(f"evaluated      : {evaluated}")
    print(f"tp/fp/tn/fn    : {total.tp}/{total.fp}/{total.tn}/{total.fn}")
    print(f"missing_pred   : {total.missing_pred}")
    print(f"missing_gt     : {total.missing_gt}")
    print(f"skipped        : {total.skipped}")
    print(f"accuracy       : {accuracy:.4f}")
    print(f"precision      : {precision:.4f}")
    print(f"recall         : {recall:.4f}")
    print(f"f1             : {f1:.4f}")
    print(f"specificity    : {specificity:.4f}")
    print(f"balanced_acc   : {balanced_accuracy:.4f}")
    print(f"report         : {out_path}")
    print("===============================================")


if __name__ == "__main__":
    main()
