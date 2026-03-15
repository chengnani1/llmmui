#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze binary judgement errors for one mode: rule / llm / final.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from build_judgement_analysis_table import build_and_save  # noqa: E402
from judgement_analysis_utils import (  # noqa: E402
    MODE_TO_FIELD,
    SAFE,
    RISKY,
    binary_confusion,
    confusion_metrics,
    eval_rows_for_mode,
    load_csv,
    normalize_binary_label,
    save_csv,
    save_json,
    split_serialized_list,
    top_counter,
)


PERMISSION_SPECIAL = [
    "READ_EXTERNAL_STORAGE",
    "WRITE_EXTERNAL_STORAGE",
    "ACCESS_FINE_LOCATION",
    "CAMERA",
    "RECORD_AUDIO",
]


def _norm_key(v: Any, empty: str = "<EMPTY>") -> str:
    s = str(v or "").strip()
    return s if s else empty


def _counter_scalar(rows: List[Dict[str, Any]], field: str, empty: str = "<EMPTY>") -> Counter:
    c = Counter()
    for row in rows:
        c[_norm_key(row.get(field), empty=empty)] += 1
    return c


def _counter_list(rows: List[Dict[str, Any]], field: str, empty: str = "<NONE>") -> Counter:
    c = Counter()
    for row in rows:
        arr = split_serialized_list(row.get(field))
        if not arr:
            c[empty] += 1
            continue
        for x in arr:
            c[x] += 1
    return c


def _subset_rows(valid_rows: List[Dict[str, Any]], pred_field: str, gt: str, pred: str) -> List[Dict[str, Any]]:
    out = []
    for row in valid_rows:
        g = normalize_binary_label(row.get("gt_label_binary", ""))
        p = normalize_binary_label(row.get(pred_field, ""))
        if g == gt and p == pred:
            out.append(row)
    return out


def _permission_special_stats(valid_rows: List[Dict[str, Any]], pred_field: str) -> List[Dict[str, Any]]:
    out = []
    for perm in PERMISSION_SPECIAL:
        pairs = []
        for row in valid_rows:
            perms = set(split_serialized_list(row.get("permissions", "")))
            if perm not in perms:
                continue
            gt = normalize_binary_label(row.get("gt_label_binary", ""))
            pred = normalize_binary_label(row.get(pred_field, ""))
            if not gt or not pred:
                continue
            pairs.append((gt, pred))
        conf = binary_confusion(pairs)
        metrics = confusion_metrics(conf)
        out.append(
            {
                "permission": perm,
                "total": len(pairs),
                "tp": conf["tp"],
                "fp": conf["fp"],
                "tn": conf["tn"],
                "fn": conf["fn"],
                "accuracy": metrics["accuracy"],
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": metrics["f1"],
                "specificity": metrics["specificity"],
                "balanced_accuracy": metrics["balanced_accuracy"],
            }
        )
    return out


def _flatten_csv_rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    overall = report["overall"]
    confusion = overall["confusion"]
    metrics = overall["metrics"]

    for k, v in overall["counts"].items():
        rows.append({"section": "overall_count", "key": k, "count": v})
    for k, v in confusion.items():
        rows.append({"section": "overall_confusion", "key": k, "count": v})
    for k, v in metrics.items():
        rows.append({"section": "overall_metric", "key": k, "value": v})

    def add_top(section: str, items: List[Dict[str, Any]]) -> None:
        for item in items:
            rows.append(
                {
                    "section": section,
                    "key": item.get("key", ""),
                    "count": item.get("count", 0),
                    "ratio": item.get("ratio", 0.0),
                }
            )

    fp = report["false_positive"]
    fn = report["false_negative"]
    add_top("fp_permissions", fp["by_permissions"])
    add_top("fp_ui_task_scene", fp["by_ui_task_scene"])
    add_top("fp_regulatory_scene_top1", fp["by_regulatory_scene_top1"])
    add_top("fp_llm_final_decision", fp["by_llm_final_decision"])
    add_top("fp_necessity_label", fp["by_necessity_label"])
    add_top("fp_consistency_label", fp["by_consistency_label"])
    add_top("fp_minimality_label", fp["by_minimality_label"])
    add_top("fp_app", fp["by_app"])

    add_top("fn_permissions", fn["by_permissions"])
    add_top("fn_ui_task_scene", fn["by_ui_task_scene"])
    add_top("fn_regulatory_scene_top1", fn["by_regulatory_scene_top1"])
    add_top("fn_rule_signal", fn["by_rule_signal"])
    add_top("fn_llm_final_decision", fn["by_llm_final_decision"])
    add_top("fn_app", fn["by_app"])

    sus = report["suspicious_analysis"]
    for k, v in sus.items():
        rows.append({"section": "suspicious", "key": k, "value": v})

    for item in report["permission_special_stats"]:
        rows.append(
            {
                "section": "permission_special",
                "key": item["permission"],
                "count": item["total"],
                "tp": item["tp"],
                "fp": item["fp"],
                "tn": item["tn"],
                "fn": item["fn"],
                "accuracy": item["accuracy"],
                "precision": item["precision"],
                "recall": item["recall"],
                "f1": item["f1"],
                "specificity": item["specificity"],
                "balanced_accuracy": item["balanced_accuracy"],
            }
        )
    return rows


def _ensure_table(processed_root: str, table_csv: str, app_prefix: str) -> str:
    if os.path.exists(table_csv):
        return table_csv
    _, _, csv_path, _ = build_and_save(processed_root=processed_root, app_prefix=app_prefix)
    return csv_path


def analyze_mode(rows: List[Dict[str, Any]], mode: str, top_k: int) -> Dict[str, Any]:
    eval_info = eval_rows_for_mode(rows, mode=mode)
    pred_field = eval_info["pred_field"]
    valid_rows = eval_info["valid_rows"]
    conf = eval_info["confusion"]
    metrics = eval_info["metrics"]

    fp_rows = _subset_rows(valid_rows, pred_field, gt=SAFE, pred=RISKY)
    fn_rows = _subset_rows(valid_rows, pred_field, gt=RISKY, pred=SAFE)

    gt_safe_count = 0
    gt_risky_count = 0
    for row in rows:
        g = normalize_binary_label(row.get("gt_label_binary", ""))
        if g == SAFE:
            gt_safe_count += 1
        elif g == RISKY:
            gt_risky_count += 1

    suspicious_rows = [
        row
        for row in rows
        if str(row.get("llm_final_decision", "")).strip().upper() == "SUSPICIOUS"
        and normalize_binary_label(row.get("gt_label_binary", ""))
    ]
    suspicious_safe = sum(1 for r in suspicious_rows if normalize_binary_label(r.get("gt_label_binary")) == SAFE)
    suspicious_risky = sum(1 for r in suspicious_rows if normalize_binary_label(r.get("gt_label_binary")) == RISKY)
    suspicious_total = len(suspicious_rows)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "pred_field": pred_field,
        "top_k": top_k,
        "overall": {
            "counts": {
                "rows_total": len(rows),
                "evaluated": len(valid_rows),
                "missing_pred": eval_info["missing_pred"],
                "missing_gt": eval_info["missing_gt"],
                "gt_safe_count": gt_safe_count,
                "gt_risky_count": gt_risky_count,
            },
            "confusion": conf,
            "metrics": metrics,
        },
        "false_positive": {
            "count": len(fp_rows),
            "by_permissions": top_counter(_counter_list(fp_rows, "permissions"), top_k),
            "by_ui_task_scene": top_counter(_counter_scalar(fp_rows, "ui_task_scene"), top_k),
            "by_regulatory_scene_top1": top_counter(_counter_scalar(fp_rows, "regulatory_scene_top1"), top_k),
            "by_llm_final_decision": top_counter(_counter_scalar(fp_rows, "llm_final_decision"), top_k),
            "by_necessity_label": top_counter(_counter_scalar(fp_rows, "necessity_label"), top_k),
            "by_consistency_label": top_counter(_counter_scalar(fp_rows, "consistency_label"), top_k),
            "by_minimality_label": top_counter(_counter_scalar(fp_rows, "minimality_label"), top_k),
            "by_app": top_counter(_counter_scalar(fp_rows, "app"), top_k),
        },
        "false_negative": {
            "count": len(fn_rows),
            "by_permissions": top_counter(_counter_list(fn_rows, "permissions"), top_k),
            "by_ui_task_scene": top_counter(_counter_scalar(fn_rows, "ui_task_scene"), top_k),
            "by_regulatory_scene_top1": top_counter(_counter_scalar(fn_rows, "regulatory_scene_top1"), top_k),
            "by_rule_signal": top_counter(_counter_scalar(fn_rows, "rule_signal"), top_k),
            "by_llm_final_decision": top_counter(_counter_scalar(fn_rows, "llm_final_decision"), top_k),
            "by_app": top_counter(_counter_scalar(fn_rows, "app"), top_k),
        },
        "suspicious_analysis": {
            "suspicious_total": suspicious_total,
            "suspicious_gt_safe_count": suspicious_safe,
            "suspicious_gt_risky_count": suspicious_risky,
            "suspicious_safe_ratio": (suspicious_safe / suspicious_total) if suspicious_total else 0.0,
            "suspicious_risky_ratio": (suspicious_risky / suspicious_total) if suspicious_total else 0.0,
        },
        "permission_special_stats": _permission_special_stats(valid_rows, pred_field=pred_field),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze binary judgement errors for one mode (rule/llm/final).")
    parser.add_argument(
        "processed_root",
        nargs="?",
        default=os.path.join("data", "processed"),
        help="processed root directory",
    )
    parser.add_argument("--mode", choices=["rule", "llm", "final"], default="final", help="analysis mode")
    parser.add_argument("--top-k", type=int, default=20, help="top-k for ranked distributions")
    parser.add_argument(
        "--table-csv",
        default="",
        help="path to judgement_analysis_table.csv; if empty, use processed_root/judgement_analysis_table.csv",
    )
    parser.add_argument(
        "--app-prefix",
        default="fastbot-",
        help="app dir prefix used when auto-building table",
    )
    args = parser.parse_args()

    processed_root = os.path.abspath(args.processed_root)
    if not os.path.isdir(processed_root):
        raise SystemExit(f"processed_root not found: {processed_root}")

    table_csv = os.path.abspath(args.table_csv) if args.table_csv else os.path.join(processed_root, "judgement_analysis_table.csv")
    table_csv = _ensure_table(processed_root, table_csv, app_prefix=args.app_prefix)
    rows = load_csv(table_csv)
    if not rows:
        raise SystemExit(f"no rows in table: {table_csv}")

    report = analyze_mode(rows, mode=args.mode, top_k=args.top_k)
    json_out = os.path.join(processed_root, f"judgement_error_analysis_{args.mode}.json")
    csv_out = os.path.join(processed_root, f"judgement_error_analysis_{args.mode}.csv")
    save_json(json_out, report)

    csv_rows = _flatten_csv_rows(report)
    save_csv(
        csv_out,
        csv_rows,
        fieldnames=[
            "section",
            "key",
            "count",
            "ratio",
            "value",
            "tp",
            "fp",
            "tn",
            "fn",
            "accuracy",
            "precision",
            "recall",
            "f1",
            "specificity",
            "balanced_accuracy",
        ],
    )

    c = report["overall"]["confusion"]
    m = report["overall"]["metrics"]
    print("\n========== Judgement Error Analysis ==========")
    print(f"mode            : {args.mode}")
    print(f"table           : {table_csv}")
    print(f"rows_total      : {report['overall']['counts']['rows_total']}")
    print(f"evaluated       : {report['overall']['counts']['evaluated']}")
    print(f"tp/fp/tn/fn     : {c['tp']}/{c['fp']}/{c['tn']}/{c['fn']}")
    print(f"accuracy        : {m['accuracy']:.4f}")
    print(f"precision       : {m['precision']:.4f}")
    print(f"recall          : {m['recall']:.4f}")
    print(f"f1              : {m['f1']:.4f}")
    print(f"specificity     : {m['specificity']:.4f}")
    print(f"balanced_acc    : {m['balanced_accuracy']:.4f}")
    print(f"json_out        : {json_out}")
    print(f"csv_out         : {csv_out}")
    print("==============================================\n")


if __name__ == "__main__":
    main()

