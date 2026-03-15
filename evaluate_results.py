#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


METHOD_FILES = {
    "Rule-Keyword": ["result_rule_only_keyword.json"],
    "LLM-UI": ["result_llm_ui.json"],
    "VLM-Direct": ["result_vlm_direct.json", "result_vlm_direct_risk.json"],
    "Full-Pipeline": ["result_final.json", "result_final_decision.json"],
}


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


def map_by_chain(items: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for idx, raw in enumerate(items):
        item = as_dict(raw)
        if not item:
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            cid = idx
        if cid not in out:
            out[cid] = item
    return out


def gt_to_binary(item: Dict[str, Any]) -> Optional[int]:
    for key in ("gt_risk", "label"):
        v = item.get(key)
        if str(v) in {"0", "1"}:
            return int(v)

    t = str(item.get("gt_label", "")).strip().upper()
    if t in {"SAFE", "无风险"}:
        return 0
    if t in {"RISKY", "有风险"}:
        return 1
    return None


def parse_pred_simple(item: Dict[str, Any]) -> Optional[int]:
    if str(item.get("pred_risk")) in {"0", "1"}:
        return int(item.get("pred_risk"))

    pred = str(item.get("pred", "")).strip().lower()
    if pred == "safe":
        return 0
    if pred == "risky":
        return 1

    pred_label = str(item.get("pred_label", "")).strip().upper()
    if pred_label == "SAFE":
        return 0
    if pred_label == "RISKY":
        return 1
    return None


def parse_pred_final(item: Dict[str, Any]) -> Optional[int]:
    d = str(item.get("final_decision", "")).strip().upper()
    if not d:
        d = str(item.get("llm_final_decision", "")).strip().upper()

    if d in {"CLEARLY_OK", "COMPLIANT"}:
        return 0
    if d in {"CLEARLY_RISKY", "NON_COMPLIANT", "NEED_REVIEW", "SUSPICIOUS"}:
        return 1

    r = str(item.get("final_risk", "")).strip().upper()
    if not r:
        r = str(item.get("llm_final_risk", "")).strip().upper()

    if r == "LOW":
        return 0
    if r in {"MEDIUM", "HIGH"}:
        return 1
    return None


def pred_to_binary(method: str, item: Dict[str, Any]) -> Optional[int]:
    if method == "Full-Pipeline":
        return parse_pred_final(item)
    return parse_pred_simple(item)


def merge_counter(a: Counter, b: Counter) -> Counter:
    return Counter(
        tp=a.tp + b.tp,
        fp=a.fp + b.fp,
        tn=a.tn + b.tn,
        fn=a.fn + b.fn,
        missing_pred=a.missing_pred + b.missing_pred,
        missing_gt=a.missing_gt + b.missing_gt,
        skipped=a.skipped + b.skipped,
    )


def resolve_pred_path(app_dir: str, candidates: List[str]) -> str:
    for name in candidates:
        p = os.path.join(app_dir, name)
        if os.path.exists(p):
            return p
    return os.path.join(app_dir, candidates[0])


def resolve_gt_path(app_dir: str) -> str:
    p = os.path.join(app_dir, "label_judge.json")
    if os.path.exists(p):
        return p
    p2 = os.path.join(app_dir, "labels_judge.json")
    if os.path.exists(p2):
        return p2
    return p


def eval_method(processed_root: str, method: str, pred_candidates: List[str], app_prefix: str) -> Dict[str, Any]:
    app_dirs = [
        os.path.join(processed_root, d)
        for d in sorted(os.listdir(processed_root))
        if os.path.isdir(os.path.join(processed_root, d)) and (not app_prefix or d.startswith(app_prefix))
    ]

    total = Counter()
    for app_dir in app_dirs:
        pred_path = resolve_pred_path(app_dir, pred_candidates)
        gt_path = resolve_gt_path(app_dir)

        pred_map = map_by_chain(as_list(load_json(pred_path)))
        gt_map = map_by_chain(as_list(load_json(gt_path)))

        c = Counter()
        for cid in sorted(set(pred_map.keys()) | set(gt_map.keys())):
            p_item = pred_map.get(cid)
            g_item = gt_map.get(cid)
            if p_item is None:
                c.missing_pred += 1
                continue
            if g_item is None:
                c.missing_gt += 1
                continue

            p = pred_to_binary(method, p_item)
            g = gt_to_binary(g_item)
            if g is None:
                c.missing_gt += 1
                continue
            if p is None:
                c.skipped += 1
                continue

            if p == 1 and g == 1:
                c.tp += 1
            elif p == 1 and g == 0:
                c.fp += 1
            elif p == 0 and g == 0:
                c.tn += 1
            else:
                c.fn += 1

        total = merge_counter(total, c)

    evaluated = total.evaluated
    accuracy = safe_div(total.tp + total.tn, evaluated)
    precision = safe_div(total.tp, total.tp + total.fp)
    recall = safe_div(total.tp, total.tp + total.fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    specificity = safe_div(total.tn, total.tn + total.fp)
    balanced_acc = (recall + specificity) / 2 if evaluated else 0.0

    return {
        "method": method,
        "pred_candidates": pred_candidates,
        "apps_total": len(app_dirs),
        "evaluated": evaluated,
        "tp": total.tp,
        "fp": total.fp,
        "tn": total.tn,
        "fn": total.fn,
        "missing_pred": total.missing_pred,
        "missing_gt": total.missing_gt,
        "skipped": total.skipped,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": specificity,
        "balanced_accuracy": balanced_acc,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate multiple methods and write unified results_summary.json")
    parser.add_argument("processed_root", nargs="?", default=os.path.join("data", "processed"))
    parser.add_argument("--out", default="results_summary.json")
    parser.add_argument("--app-prefix", default="")
    args = parser.parse_args()

    processed_root = os.path.abspath(args.processed_root)
    if not os.path.isdir(processed_root):
        raise SystemExit(f"processed_root not found: {processed_root}")

    results: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "processed_root": processed_root,
        "methods": {},
    }

    for method, files in METHOD_FILES.items():
        results["methods"][method] = eval_method(
            processed_root=processed_root,
            method=method,
            pred_candidates=files,
            app_prefix=args.app_prefix,
        )

    out_path = os.path.join(processed_root, args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[DONE] summary={out_path}")
    for method, item in results["methods"].items():
        print(
            f"{method}: acc={item['accuracy']:.4f} f1={item['f1']:.4f} "
            f"bal_acc={item['balanced_accuracy']:.4f} "
            f"tp/fp/tn/fn={item['tp']}/{item['fp']}/{item['tn']}/{item['fn']}"
        )


if __name__ == "__main__":
    main()
