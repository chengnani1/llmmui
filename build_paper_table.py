#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import os
from typing import Any, Dict, List


COLUMNS = [
    ("Method", "method"),
    ("Accuracy", "accuracy"),
    ("Precision", "precision"),
    ("Recall", "recall"),
    ("F1", "f1"),
    ("Specificity", "specificity"),
    ("Balanced Acc", "balanced_accuracy"),
]


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fmt(x: Any) -> str:
    if isinstance(x, (int, float)):
        return f"{x:.4f}"
    return str(x)


def build_rows(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    methods = summary.get("methods", {}) if isinstance(summary.get("methods"), dict) else {}
    rows: List[Dict[str, Any]] = []
    order = ["Rule-Keyword", "LLM-UI", "VLM-Direct", "Full-Pipeline"]

    for name in order:
        item = methods.get(name)
        if not isinstance(item, dict):
            continue
        rows.append({
            "method": name,
            "accuracy": float(item.get("accuracy", 0.0)),
            "precision": float(item.get("precision", 0.0)),
            "recall": float(item.get("recall", 0.0)),
            "f1": float(item.get("f1", 0.0)),
            "specificity": float(item.get("specificity", 0.0)),
            "balanced_accuracy": float(item.get("balanced_accuracy", 0.0)),
        })

    for name, item in methods.items():
        if name in order or not isinstance(item, dict):
            continue
        rows.append({
            "method": name,
            "accuracy": float(item.get("accuracy", 0.0)),
            "precision": float(item.get("precision", 0.0)),
            "recall": float(item.get("recall", 0.0)),
            "f1": float(item.get("f1", 0.0)),
            "specificity": float(item.get("specificity", 0.0)),
            "balanced_accuracy": float(item.get("balanced_accuracy", 0.0)),
        })

    return rows


def write_markdown(path: str, rows: List[Dict[str, Any]]) -> None:
    headers = [c[0] for c in COLUMNS]
    with open(path, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
        for row in rows:
            values = [fmt(row.get(key, "")) for _, key in COLUMNS]
            f.write("| " + " | ".join(values) + " |\n")


def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    headers = [c[0] for c in COLUMNS]
    keys = [c[1] for c in COLUMNS]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in rows:
            w.writerow([fmt(row.get(k, "")) for k in keys])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build paper table from results_summary.json")
    parser.add_argument("summary_json", nargs="?", default=os.path.join("data", "processed", "results_summary.json"))
    parser.add_argument("--md", default="paper_table.md")
    parser.add_argument("--csv", default="paper_table.csv")
    args = parser.parse_args()

    summary_path = os.path.abspath(args.summary_json)
    if not os.path.exists(summary_path):
        raise SystemExit(f"summary_json not found: {summary_path}")

    summary = load_json(summary_path)
    rows = build_rows(summary)

    out_dir = os.path.dirname(summary_path)
    md_path = os.path.join(out_dir, args.md)
    csv_path = os.path.join(out_dir, args.csv)

    write_markdown(md_path, rows)
    write_csv(csv_path, rows)

    print(f"[DONE] markdown={md_path}")
    print(f"[DONE] csv={csv_path}")


if __name__ == "__main__":
    main()
