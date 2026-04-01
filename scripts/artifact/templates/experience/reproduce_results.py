#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from evaluate_benchmark import build_outputs as build_benchmark_outputs
from evaluate_generalization import build_outputs as build_generalization_outputs
from summarize_datasets import build_outputs as build_dataset_outputs
from summarize_rq3 import build_outputs as build_rq3_outputs
from eval_helpers import relpath_str, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce all released artifact results.")
    parser.add_argument("--artifact-root", default=".", help="artifact root directory")
    parser.add_argument("--large-scale-total-apps", type=int, default=865)
    parser.add_argument("--large-scale-ui-pairs", type=int, default=657632)
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root).resolve()
    benchmark_root = artifact_root / "data" / "benchmark_processed"
    independent_root = artifact_root / "data" / "independent_processed"
    large_scale_root = artifact_root / "data" / "large_scale_processed"
    results_root = artifact_root / "results"
    results_root.mkdir(parents=True, exist_ok=True)

    dataset_summary = build_dataset_outputs(
        benchmark_root=benchmark_root,
        independent_root=independent_root,
        large_scale_root=large_scale_root,
        output_dir=results_root,
        large_scale_total_apps=args.large_scale_total_apps,
        large_scale_ui_pairs=args.large_scale_ui_pairs,
    )
    benchmark_summary = build_benchmark_outputs(benchmark_root, results_root)
    generalization_summary = build_generalization_outputs(independent_root, results_root)
    rq3_summary = build_rq3_outputs(large_scale_root, results_root)

    repro_summary_path = results_root / "repro_summary.json"
    write_json(
        repro_summary_path,
        {
            "dataset_summary": dataset_summary,
            "benchmark_summary": benchmark_summary,
            "generalization_summary": generalization_summary,
            "rq3_summary": rq3_summary,
        },
    )

    print(f"[DONE] Dataset summary      -> {dataset_summary['csv']}")
    print(f"[DONE] RQ1 effectiveness    -> {benchmark_summary['effectiveness_csv']}")
    print(f"[DONE] RQ2 ablation         -> {benchmark_summary['ablation_csv']}")
    print(f"[DONE] Generalization       -> {generalization_summary['csv']}")
    print(f"[DONE] RQ3 chain summary    -> {rq3_summary['chain_csv']}")
    print(f"[DONE] RQ3 app summary      -> {rq3_summary['app_csv']}")
    print(f"[DONE] Combined summary     -> {relpath_str(repro_summary_path, artifact_root)}")


if __name__ == "__main__":
    main()
