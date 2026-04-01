#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from eval_helpers import collect_permission_types, collect_ui_scenes, iter_app_dirs, relpath_str, safe_div, summarize_labels, write_csv, write_json


def dataset_row(
    name: str,
    processed_root: Path,
    include_labels: bool,
    extra: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    row: Dict[str, object] = {
        "dataset": name,
        "apps": len(iter_app_dirs(processed_root)),
        "chains": "",
        "risky": "",
        "safe": "",
        "permission_types": "",
        "ui_task_scenarios": "",
    }
    if include_labels:
        labels = summarize_labels(processed_root)
        row["chains"] = labels["chains"]
        row["risky"] = labels["risky"]
        row["safe"] = labels["safe"]
        row["permission_types"] = len(collect_permission_types(processed_root))
        row["ui_task_scenarios"] = len([x for x in collect_ui_scenes(processed_root) if x != "其他"])
    if extra:
        row.update(extra)
    return row


def build_outputs(
    benchmark_root: Path,
    independent_root: Path,
    large_scale_root: Path,
    output_dir: Path,
    large_scale_total_apps: int,
    large_scale_ui_pairs: int,
) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = output_dir.parent

    rows: List[Dict[str, object]] = [
        dataset_row("benchmark", benchmark_root, include_labels=True),
        dataset_row("independent", independent_root, include_labels=True),
        dataset_row(
            "large_scale_processed",
            large_scale_root,
            include_labels=False,
            extra={
                "apps_with_permission_requests": len(iter_app_dirs(large_scale_root)),
                "paper_collected_apps": large_scale_total_apps,
                "paper_ui_xml_png_pairs": large_scale_ui_pairs,
            },
        ),
    ]

    json_path = output_dir / "dataset_summary.json"
    csv_path = output_dir / "table_dataset_summary.csv"

    write_json(
        json_path,
        {
            "rows": rows,
        },
    )
    write_csv(
        csv_path,
        rows,
        [
            "dataset",
            "apps",
            "chains",
            "risky",
            "safe",
            "permission_types",
            "ui_task_scenarios",
            "apps_with_permission_requests",
            "paper_collected_apps",
            "paper_ui_xml_png_pairs",
        ],
    )
    return {
        "json": relpath_str(json_path, artifact_root),
        "csv": relpath_str(csv_path, artifact_root),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize released datasets in the artifact.")
    parser.add_argument("--benchmark-root", required=True)
    parser.add_argument("--independent-root", required=True)
    parser.add_argument("--large-scale-root", required=True)
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--large-scale-total-apps", type=int, default=865)
    parser.add_argument("--large-scale-ui-pairs", type=int, default=657632)
    args = parser.parse_args()

    summary = build_outputs(
        benchmark_root=Path(args.benchmark_root).resolve(),
        independent_root=Path(args.independent_root).resolve(),
        large_scale_root=Path(args.large_scale_root).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        large_scale_total_apps=args.large_scale_total_apps,
        large_scale_ui_pairs=args.large_scale_ui_pairs,
    )
    print(summary["csv"])


if __name__ == "__main__":
    main()
