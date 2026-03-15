#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate binary risk metrics using:
- prediction: result_final_decision.json (3-class)
- ground truth: label_judge.json (2-class, gt_risk)

3-class -> 2-class mapping:
- CLEARLY_RISKY -> 1
- CLEARLY_OK    -> 0
- NEED_REVIEW   -> configurable via --review-as {risk,safe,skip}
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


PRED_FILENAME = "result_final_decision.json"
GT_FILENAME = "label_judge.json"
DEFAULT_OUT = "judge_binary_metrics.json"


@dataclass
class Counter:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    skipped: int = 0
    missing_pred: int = 0
    missing_gt: int = 0

    @property
    def total_eval(self) -> int:
        return self.tp + self.fp + self.tn + self.fn


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def pred_to_binary(item: Dict[str, Any], review_as: str) -> Optional[int]:
    decision = str(item.get("final_decision", "")).strip().upper()
    if not decision:
        decision = str(item.get("llm_final_decision", "")).strip().upper()
    if decision == "CLEARLY_RISKY":
        return 1
    if decision == "CLEARLY_OK":
        return 0
    if decision == "NON_COMPLIANT":
        return 1
    if decision == "COMPLIANT":
        return 0
    if decision == "NEED_REVIEW":
        if review_as == "skip":
            return None
        return 1 if review_as == "risk" else 0
    if decision == "SUSPICIOUS":
        if review_as == "skip":
            return None
        return 1 if review_as == "risk" else 0

    risk = str(item.get("final_risk", "")).strip().upper()
    if not risk:
        risk = str(item.get("llm_final_risk", "")).strip().upper()
    if risk == "HIGH":
        return 1
    if risk == "LOW":
        return 0
    if risk == "MEDIUM":
        if review_as == "skip":
            return None
        return 1 if review_as == "risk" else 0
    return None


def gt_to_binary(item: Dict[str, Any]) -> Optional[int]:
    if str(item.get("gt_risk")) in {"0", "1"}:
        return int(item.get("gt_risk"))
    if str(item.get("label")) in {"0", "1"}:
        # backward compatibility for old label schema
        return int(item.get("label"))
    text = str(item.get("gt_label", "")).strip().upper()
    if text == "RISKY":
        return 1
    if text == "SAFE":
        return 0
    return None


def map_by_chain(items: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for i, raw in enumerate(items):
        item = as_dict(raw)
        if not item:
            continue
        try:
            cid = int(item.get("chain_id", i))
        except Exception:
            cid = i
        if cid not in out:
            out[cid] = item
    return out


def eval_app(app_dir: str, review_as: str, pred_file: str) -> Tuple[Counter, Dict[str, Any]]:
    pred_path = os.path.join(app_dir, pred_file)
    gt_path = os.path.join(app_dir, GT_FILENAME)

    counter = Counter()
    detail = {
        "app": os.path.basename(app_dir),
        "pred_exists": os.path.exists(pred_path),
        "gt_exists": os.path.exists(gt_path),
        "chains_pred": 0,
        "chains_gt": 0,
        "evaluated": 0,
        "tp": 0,
        "fp": 0,
        "tn": 0,
        "fn": 0,
        "skipped": 0,
        "missing_pred": 0,
        "missing_gt": 0,
        "accuracy": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }

    pred_map = map_by_chain(as_list(load_json(pred_path)))
    gt_map = map_by_chain(as_list(load_json(gt_path)))
    detail["chains_pred"] = len(pred_map)
    detail["chains_gt"] = len(gt_map)

    chain_ids = sorted(set(pred_map.keys()) | set(gt_map.keys()))
    for cid in chain_ids:
        pred_item = pred_map.get(cid)
        gt_item = gt_map.get(cid)
        if pred_item is None:
            counter.missing_pred += 1
            continue
        if gt_item is None:
            counter.missing_gt += 1
            continue

        p = pred_to_binary(pred_item, review_as=review_as)
        g = gt_to_binary(gt_item)
        if g is None:
            counter.missing_gt += 1
            continue
        if p is None:
            counter.skipped += 1
            continue

        if p == 1 and g == 1:
            counter.tp += 1
        elif p == 1 and g == 0:
            counter.fp += 1
        elif p == 0 and g == 0:
            counter.tn += 1
        elif p == 0 and g == 1:
            counter.fn += 1

    detail["evaluated"] = counter.total_eval
    detail["tp"] = counter.tp
    detail["fp"] = counter.fp
    detail["tn"] = counter.tn
    detail["fn"] = counter.fn
    detail["skipped"] = counter.skipped
    detail["missing_pred"] = counter.missing_pred
    detail["missing_gt"] = counter.missing_gt

    detail["accuracy"] = safe_div(counter.tp + counter.tn, counter.total_eval)
    detail["precision"] = safe_div(counter.tp, counter.tp + counter.fp)
    detail["recall"] = safe_div(counter.tp, counter.tp + counter.fn)
    detail["f1"] = safe_div(2 * detail["precision"] * detail["recall"], detail["precision"] + detail["recall"])
    return counter, detail


def merge(a: Counter, b: Counter) -> Counter:
    return Counter(
        tp=a.tp + b.tp,
        fp=a.fp + b.fp,
        tn=a.tn + b.tn,
        fn=a.fn + b.fn,
        skipped=a.skipped + b.skipped,
        missing_pred=a.missing_pred + b.missing_pred,
        missing_gt=a.missing_gt + b.missing_gt,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate binary risk metrics from label_judge.json")
    parser.add_argument(
        "target",
        nargs="?",
        default=os.path.join("data", "processed"),
        help="processed root or one app dir",
    )
    parser.add_argument(
        "--review-as",
        choices=["risk", "safe", "skip"],
        default="risk",
        help="how to map NEED_REVIEW to binary class",
    )
    parser.add_argument(
        "--pred-file",
        default=PRED_FILENAME,
        help="prediction filename in each app dir (e.g. result_final_decision.json or result_llm_review.json)",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUT,
        help="output filename under target root (or next to app dir)",
    )
    parser.add_argument(
        "--app-prefix",
        default="fastbot-",
        help="only evaluate app dirs with this prefix (root mode)",
    )
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    if not os.path.exists(target):
        raise SystemExit(f"target not found: {target}")

    if os.path.exists(os.path.join(target, args.pred_file)) or os.path.exists(os.path.join(target, GT_FILENAME)):
        app_dirs = [target]
        out_dir = target
    else:
        app_dirs = [
            os.path.join(target, d)
            for d in sorted(os.listdir(target))
            if os.path.isdir(os.path.join(target, d)) and d.startswith(args.app_prefix)
        ]
        out_dir = target

    total = Counter()
    per_app: List[Dict[str, Any]] = []
    for app_dir in app_dirs:
        c, detail = eval_app(app_dir, review_as=args.review_as, pred_file=args.pred_file)
        total = merge(total, c)
        per_app.append(detail)

    evaluated = total.total_eval
    accuracy = safe_div(total.tp + total.tn, evaluated)
    precision = safe_div(total.tp, total.tp + total.fp)
    recall = safe_div(total.tp, total.tp + total.fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    specificity = safe_div(total.tn, total.tn + total.fp)
    balanced_accuracy = (recall + specificity) / 2 if evaluated else 0.0

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target": target,
        "pred_file": args.pred_file,
        "review_as": args.review_as,
        "apps_total": len(app_dirs),
        "evaluated_chains": evaluated,
        "confusion": {
            "tp": total.tp,
            "fp": total.fp,
            "tn": total.tn,
            "fn": total.fn,
            "skipped": total.skipped,
            "missing_pred": total.missing_pred,
            "missing_gt": total.missing_gt,
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

    print("========== Binary Risk Evaluation ==========")
    print(f"apps_total     : {len(app_dirs)}")
    print(f"evaluated      : {evaluated}")
    print(f"tp/fp/tn/fn    : {total.tp}/{total.fp}/{total.tn}/{total.fn}")
    print(f"skipped        : {total.skipped}")
    print(f"missing_pred   : {total.missing_pred}")
    print(f"missing_gt     : {total.missing_gt}")
    print(f"accuracy       : {accuracy:.4f}")
    print(f"precision      : {precision:.4f}")
    print(f"recall         : {recall:.4f}")
    print(f"f1             : {f1:.4f}")
    print(f"specificity    : {specificity:.4f}")
    print(f"balanced_acc   : {balanced_accuracy:.4f}")
    print(f"report         : {out_path}")
    print("===========================================")


if __name__ == "__main__":
    main()
