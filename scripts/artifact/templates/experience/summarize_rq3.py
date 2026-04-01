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

from eval_helpers import as_dict, as_list, derived_medium_bucket, iter_app_dirs, load_json, relpath_str, safe_div, write_csv, write_json


def build_outputs(processed_root: Path, output_dir: Path) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = output_dir.parent

    chain_counts = {
        "LOW": 0,
        "MEDIUM-consistent": 0,
        "MEDIUM-over": 0,
        "HIGH": 0,
    }
    app_counts = {
        "Clearly risky": 0,
        "Potentially risky": 0,
        "Clearly safe": 0,
    }

    chains_total = 0
    apps_total = 0

    for app_dir in iter_app_dirs(processed_root):
        final_path = app_dir / "result_final_decision.json"
        if not final_path.exists():
            continue

        apps_total += 1
        rows = as_list(load_json(final_path))
        app_max_risk = "LOW"
        for raw in rows:
            row = as_dict(raw)
            if not row:
                continue
            bucket = derived_medium_bucket(row)
            if bucket in chain_counts:
                chain_counts[bucket] += 1
                chains_total += 1

            risk = str(row.get("final_risk", "")).strip().upper()
            if risk == "HIGH":
                app_max_risk = "HIGH"
            elif risk == "MEDIUM" and app_max_risk != "HIGH":
                app_max_risk = "MEDIUM"

        if app_max_risk == "HIGH":
            app_counts["Clearly risky"] += 1
        elif app_max_risk == "MEDIUM":
            app_counts["Potentially risky"] += 1
        else:
            app_counts["Clearly safe"] += 1

    chain_rows: List[Dict[str, object]] = []
    for label in ["LOW", "MEDIUM-over", "MEDIUM-consistent", "HIGH"]:
        count = chain_counts[label]
        chain_rows.append(
            {
                "bucket": label,
                "count": count,
                "ratio": round(safe_div(count, chains_total), 4),
                "percentage": round(safe_div(count, chains_total) * 100, 1),
            }
        )

    app_rows: List[Dict[str, object]] = []
    for label in ["Clearly risky", "Potentially risky", "Clearly safe"]:
        count = app_counts[label]
        app_rows.append(
            {
                "bucket": label,
                "count": count,
                "ratio": round(safe_div(count, apps_total), 4),
                "percentage": round(safe_div(count, apps_total) * 100, 1),
            }
        )

    json_path = output_dir / "rq3_summary.json"
    chain_csv = output_dir / "table_rq3_chain_risk_breakdown.csv"
    app_csv = output_dir / "table_rq3_app_risk_breakdown.csv"

    write_json(
        json_path,
        {
            "dataset": "large_scale_processed",
            "apps_total": apps_total,
            "chains_total": chains_total,
            "chain_rows": chain_rows,
            "app_rows": app_rows,
        },
    )
    write_csv(chain_csv, chain_rows, ["bucket", "count", "ratio", "percentage"])
    write_csv(app_csv, app_rows, ["bucket", "count", "ratio", "percentage"])

    return {
        "dataset": "large_scale_processed",
        "json": relpath_str(json_path, artifact_root),
        "chain_csv": relpath_str(chain_csv, artifact_root),
        "app_csv": relpath_str(app_csv, artifact_root),
        "apps_total": apps_total,
        "chains_total": chains_total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize large-scale RQ3 results.")
    parser.add_argument("processed_root", help="large-scale processed root")
    parser.add_argument("--output-dir", default="results", help="output directory")
    args = parser.parse_args()

    summary = build_outputs(Path(args.processed_root).resolve(), Path(args.output_dir).resolve())
    print(summary["chain_csv"])
    print(summary["app_csv"])


if __name__ == "__main__":
    main()
