#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run multi-round error-driven knowledge iteration for phase3_v2 backend."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Set


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DATA_ROOT = os.path.join(ROOT, "data", "processed")

STRUCTURED_JSON = os.path.join(ROOT, "src", "configs", "scene_structured_knowledge.json")


def run_cmd(cmd: List[str], env: Dict[str, str]) -> None:
    print("[CMD]", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)} (exit={proc.returncode})")


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_labeled_apps(target: str, app_prefix: str) -> List[str]:
    out: List[str] = []
    for d in sorted(os.listdir(target)) if os.path.isdir(target) else []:
        app_dir = os.path.join(target, d)
        if not os.path.isdir(app_dir):
            continue
        if app_prefix and not d.startswith(app_prefix):
            continue
        if os.path.exists(os.path.join(app_dir, "label_judge.json")):
            out.append(d)
    return out


def collect_error_apps(error_json_path: str) -> Set[str]:
    rows = load_json(error_json_path)
    out: Set[str] = set()
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        app = str(item.get("app", "")).strip()
        if app:
            out.add(app)
    return out


def backup_knowledge(round_dir: str) -> None:
    kb_dir = os.path.join(round_dir, "knowledge_before")
    os.makedirs(kb_dir, exist_ok=True)
    if os.path.exists(STRUCTURED_JSON):
        shutil.copy2(STRUCTURED_JSON, os.path.join(kb_dir, "scene_structured_knowledge.json"))


def copy_artifact(src: str, dst: str) -> None:
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 10-round error-driven knowledge iteration")
    parser.add_argument("--target", default=DATA_ROOT, help="processed root")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--app-prefix", default="fastbot-")
    parser.add_argument("--review-as", choices=["risk", "safe", "skip"], default="risk")
    parser.add_argument("--min-support", type=int, default=3)
    parser.add_argument("--apply-min-support", type=int, default=5)
    parser.add_argument("--text-url", default="http://127.0.0.1:29011/v1/chat/completions")
    parser.add_argument("--vl-url", default="http://127.0.0.1:29010/v1/chat/completions")
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    iter_root = os.path.join(target, "knowledge_iterations")
    os.makedirs(iter_root, exist_ok=True)

    env = os.environ.copy()
    env["LLMMUI_VLLM_TEXT_URL"] = args.text_url
    env["LLMMUI_VLLM_VL_URL"] = args.vl_url
    env["LLMMUI_SCENE_STRUCTURED_KNOWLEDGE_FILE"] = STRUCTURED_JSON

    all_apps = iter_labeled_apps(target, app_prefix=args.app_prefix)
    if not all_apps:
        raise SystemExit(f"no labeled apps found under {target} with prefix={args.app_prefix}")

    metrics_by_round: List[Dict[str, Any]] = []
    apps_to_run = set(all_apps)

    for r in range(1, args.rounds + 1):
        round_tag = f"round_{r:02d}"
        round_dir = os.path.join(iter_root, round_tag)
        os.makedirs(round_dir, exist_ok=True)
        print(f"\n========== {round_tag} ==========")
        print(f"apps_to_run={len(apps_to_run)}")

        backup_knowledge(round_dir)
        current_round_apps = sorted(apps_to_run)

        for app in current_round_apps:
            run_cmd(
                [
                    sys.executable,
                    "src/main.py",
                    "phase3_v2_compliance",
                    target,
                    "--app",
                    app,
                    "--force",
                ],
                env=env,
            )
            run_cmd(
                [
                    sys.executable,
                    "src/main.py",
                    "phase3_v2_final",
                    target,
                    "--app",
                    app,
                    "--force",
                ],
                env=env,
            )

        # evaluate current round on full labeled set
        run_cmd(
            [
                sys.executable,
                "scripts/experiments/evaluate_label_judge_binary.py",
                target,
                "--pred-file",
                "result_final_decision.json",
                "--review-as",
                args.review_as,
                "--app-prefix",
                args.app_prefix,
                "--output",
                "judge_binary_metrics.json",
            ],
            env=env,
        )
        eval_path = os.path.join(target, "judge_binary_metrics.json")
        round_eval_path = os.path.join(round_dir, "judge_binary_metrics.json")
        copy_artifact(eval_path, round_eval_path)

        # mine errors + candidates
        run_cmd(
            [
                sys.executable,
                "scripts/experiments/iterate_knowledge_from_errors.py",
                target,
                "--review-as",
                args.review_as,
                "--app-prefix",
                args.app_prefix,
                "--min-support",
                str(args.min_support),
                "--error-json",
                "knowledge_error_cases.json",
                "--cluster-csv",
                "knowledge_error_clusters.csv",
                "--patch-json",
                "knowledge_patch_candidates.json",
            ],
            env=env,
        )

        error_json = os.path.join(target, "knowledge_error_cases.json")
        cluster_csv = os.path.join(target, "knowledge_error_clusters.csv")
        patch_json = os.path.join(target, "knowledge_patch_candidates.json")
        copy_artifact(error_json, os.path.join(round_dir, "knowledge_error_cases.json"))
        copy_artifact(cluster_csv, os.path.join(round_dir, "knowledge_error_clusters.csv"))
        copy_artifact(patch_json, os.path.join(round_dir, "knowledge_patch_candidates.json"))

        # update structured knowledge from current round errors
        structured_update_summary = os.path.join(target, "knowledge_structured_update_summary.json")
        run_cmd(
            [
                sys.executable,
                "scripts/experiments/update_structured_knowledge_from_errors.py",
                "--error-json",
                error_json,
                "--knowledge-json",
                STRUCTURED_JSON,
                "--min-support",
                str(args.apply_min_support),
                "--top-k-cues",
                "4",
                "--max-field-items",
                "16",
                "--summary-json",
                structured_update_summary,
            ],
            env=env,
        )
        run_cmd(
            [
                sys.executable,
                "scripts/experiments/lint_structured_knowledge.py",
                STRUCTURED_JSON,
            ],
            env=env,
        )

        copy_artifact(STRUCTURED_JSON, os.path.join(round_dir, "scene_structured_knowledge.json"))
        copy_artifact(
            structured_update_summary,
            os.path.join(round_dir, "knowledge_structured_update_summary.json"),
        )

        eval_obj = load_json(round_eval_path) or {}
        metrics = (eval_obj.get("metrics") or {}) if isinstance(eval_obj, dict) else {}
        confusion = (eval_obj.get("confusion") or {}) if isinstance(eval_obj, dict) else {}
        error_apps = collect_error_apps(error_json)
        update_obj = load_json(structured_update_summary) or {}
        apps_to_run = error_apps if error_apps else set(all_apps)

        metrics_by_round.append(
            {
                "round": r,
                "round_tag": round_tag,
                "apps_run_count": len(current_round_apps),
                "evaluated_chains": eval_obj.get("evaluated_chains"),
                "tp": confusion.get("tp"),
                "fp": confusion.get("fp"),
                "tn": confusion.get("tn"),
                "fn": confusion.get("fn"),
                "accuracy": metrics.get("accuracy"),
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f1": metrics.get("f1"),
                "balanced_accuracy": metrics.get("balanced_accuracy"),
                "error_apps_for_next_round": len(error_apps),
                "knowledge_updates": {
                    "updated_rules": update_obj.get("updated_rules", 0),
                    "total_field_updates": update_obj.get("total_field_updates", 0),
                },
            }
        )

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target": target,
        "rounds": args.rounds,
        "review_as": args.review_as,
        "app_prefix": args.app_prefix,
        "text_url": args.text_url,
        "vl_url": args.vl_url,
        "metrics_by_round": metrics_by_round,
    }
    summary_path = os.path.join(iter_root, "iteration_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\niteration summary: {summary_path}")


if __name__ == "__main__":
    main()
