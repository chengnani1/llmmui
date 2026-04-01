#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from eval_helpers import evaluate_predictions, final_to_binary, relpath_str, write_csv, write_json


def build_outputs(processed_root: Path, output_dir: Path) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = output_dir.parent

    report = evaluate_predictions(processed_root, pred_file="result_final_decision.json", pred_mapper=final_to_binary)
    row = {
        "dataset": "independent",
        "pred_file": "result_final_decision.json",
    }
    row.update(report["confusion"])
    row.update(report["metrics"])

    json_path = output_dir / "generalization.json"
    csv_path = output_dir / "table_generalization.csv"

    write_json(
        json_path,
        {
            "dataset": "independent",
            "report": report,
            "row": row,
        },
    )
    write_csv(
        csv_path,
        [row],
        [
            "dataset",
            "pred_file",
            "evaluated",
            "tp",
            "fp",
            "tn",
            "fn",
            "missing_pred",
            "missing_gt",
            "skipped",
            "accuracy",
            "precision",
            "recall",
            "f1",
            "specificity",
            "balanced_accuracy",
        ],
    )

    return {
        "dataset": "independent",
        "json": relpath_str(json_path, artifact_root),
        "csv": relpath_str(csv_path, artifact_root),
        "report": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the independent generalization dataset.")
    parser.add_argument("processed_root", help="independent processed root")
    parser.add_argument("--output-dir", default="results", help="output directory")
    args = parser.parse_args()

    summary = build_outputs(Path(args.processed_root).resolve(), Path(args.output_dir).resolve())
    print(summary["csv"])


if __name__ == "__main__":
    main()
