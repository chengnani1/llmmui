#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare binary risk performance across rule / llm / final modes.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Any, Dict, List


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from build_judgement_analysis_table import build_and_save  # noqa: E402
from judgement_analysis_utils import eval_rows_for_mode, load_csv, save_csv, save_json  # noqa: E402


def _ensure_table(processed_root: str, table_csv: str, app_prefix: str) -> str:
    if os.path.exists(table_csv):
        return table_csv
    _, _, csv_path, _ = build_and_save(processed_root=processed_root, app_prefix=app_prefix)
    return csv_path


def compare_modes(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for mode in ["rule", "llm", "final"]:
        eval_info = eval_rows_for_mode(rows, mode=mode)
        conf = eval_info["confusion"]
        metrics = eval_info["metrics"]
        out.append(
            {
                "mode": mode,
                "pred_field": eval_info["pred_field"],
                "evaluated": len(eval_info["valid_rows"]),
                "missing_pred": eval_info["missing_pred"],
                "missing_gt": eval_info["missing_gt"],
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare binary judgement metrics across rule/llm/final modes.")
    parser.add_argument(
        "processed_root",
        nargs="?",
        default=os.path.join("data", "processed"),
        help="processed root directory",
    )
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
    table_csv = _ensure_table(processed_root=processed_root, table_csv=table_csv, app_prefix=args.app_prefix)
    rows = load_csv(table_csv)
    if not rows:
        raise SystemExit(f"no rows in table: {table_csv}")

    mode_rows = compare_modes(rows)
    json_out = os.path.join(processed_root, "judgement_mode_comparison.json")
    csv_out = os.path.join(processed_root, "judgement_mode_comparison.csv")

    save_json(
        json_out,
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "processed_root": processed_root,
            "table_csv": table_csv,
            "rows_total": len(rows),
            "modes": mode_rows,
        },
    )
    save_csv(
        csv_out,
        mode_rows,
        fieldnames=[
            "mode",
            "pred_field",
            "evaluated",
            "missing_pred",
            "missing_gt",
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

    print("\n========== Judgement Mode Comparison ==========")
    print(f"table           : {table_csv}")
    print(f"rows_total      : {len(rows)}")
    for x in mode_rows:
        print(
            f"[{x['mode']}] eval={x['evaluated']} "
            f"tp/fp/tn/fn={x['tp']}/{x['fp']}/{x['tn']}/{x['fn']} "
            f"acc={x['accuracy']:.4f} f1={x['f1']:.4f} bal_acc={x['balanced_accuracy']:.4f}"
        )
    print(f"json_out        : {json_out}")
    print(f"csv_out         : {csv_out}")
    print("===============================================\n")


if __name__ == "__main__":
    main()

