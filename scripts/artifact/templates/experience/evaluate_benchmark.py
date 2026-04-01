#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from eval_helpers import evaluate_predictions, final_to_binary, relpath_str, simple_pred_to_binary, vlm_to_binary, write_csv, write_json


def effectiveness_rows(processed_root: Path) -> List[Dict[str, object]]:
    specs = [
        ("PrivUI-Guard", "main", True, "result_final_decision.json", final_to_binary),
        ("Rule-based", "baseline", True, "result_rule_only_keyword.json", simple_pred_to_binary),
        ("LLM (text-only)", "baseline", True, "result_llm_ui.json", simple_pred_to_binary),
        ("VLM (direct reasoning)", "baseline", True, "result_vlm_direct_risk.json", vlm_to_binary),
        ("Knowledge-rule baseline", "auxiliary", False, "result_knowledge_rule_baseline.json", simple_pred_to_binary),
    ]

    rows: List[Dict[str, object]] = []
    for method, group, paper_included, pred_file, mapper in specs:
        report = evaluate_predictions(processed_root, pred_file=pred_file, pred_mapper=mapper)
        row: Dict[str, object] = {
            "method": method,
            "group": group,
            "paper_included": paper_included,
            "pred_file": pred_file,
        }
        row.update(report["confusion"])
        row.update(report["metrics"])
        rows.append(row)
    return rows


def ablation_rows(processed_root: Path) -> List[Dict[str, object]]:
    specs = [
        ("Full model", True, "result_final_decision.json"),
        ("w/o interaction chain", True, "result_final_decision_wo_chain.json"),
        ("w/o semantic modeling", True, "result_final_decision_wo_semantic.json"),
        ("w/o knowledge enhancement", True, "result_final_decision_wo_knowledge.json"),
        ("w/o structured reasoning", True, "result_final_decision_wo_structured_reasoning.json"),
        ("w/o semantic modeling (pure)", False, "result_final_decision_wo_semantic_pure.json"),
    ]

    rows: List[Dict[str, object]] = []
    for setting, paper_included, pred_file in specs:
        report = evaluate_predictions(processed_root, pred_file=pred_file, pred_mapper=final_to_binary)
        row: Dict[str, object] = {
            "setting": setting,
            "paper_included": paper_included,
            "pred_file": pred_file,
        }
        row.update(report["confusion"])
        row.update(report["metrics"])
        rows.append(row)
    return rows


def build_outputs(processed_root: Path, output_dir: Path) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = output_dir.parent

    effectiveness = effectiveness_rows(processed_root)
    ablation = ablation_rows(processed_root)

    effectiveness_json = output_dir / "rq1_effectiveness.json"
    effectiveness_csv = output_dir / "table_rq1_effectiveness.csv"
    ablation_json = output_dir / "rq2_ablation.json"
    ablation_csv = output_dir / "table_rq2_ablation.csv"

    write_json(
        effectiveness_json,
        {
            "dataset": "benchmark",
            "rows": effectiveness,
        },
    )
    write_csv(
        effectiveness_csv,
        effectiveness,
        [
            "method",
            "group",
            "paper_included",
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

    write_json(
        ablation_json,
        {
            "dataset": "benchmark",
            "rows": ablation,
        },
    )
    write_csv(
        ablation_csv,
        ablation,
        [
            "setting",
            "paper_included",
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
        "dataset": "benchmark",
        "effectiveness_json": relpath_str(effectiveness_json, artifact_root),
        "effectiveness_csv": relpath_str(effectiveness_csv, artifact_root),
        "ablation_json": relpath_str(ablation_json, artifact_root),
        "ablation_csv": relpath_str(ablation_csv, artifact_root),
        "effectiveness": effectiveness,
        "ablation": ablation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate benchmark effectiveness and ablation results.")
    parser.add_argument("processed_root", help="benchmark processed root")
    parser.add_argument("--output-dir", default="results", help="output directory")
    args = parser.parse_args()

    summary = build_outputs(Path(args.processed_root).resolve(), Path(args.output_dir).resolve())
    print(summary["effectiveness_csv"])
    print(summary["ablation_csv"])


if __name__ == "__main__":
    main()
