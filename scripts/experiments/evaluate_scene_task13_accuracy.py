#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate scene recognition accuracy against per-app task13 ground truth.

Default:
- GT file in each app dir: results_scene_task13.json
- Prediction file in each app dir: result_scene_text.json
- Aggregated output: <processed_root>/scene_task13_accuracy_report.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


SCENE_ALIAS_MAP: Dict[str, str] = {
    # Old -> task13
    "登录与账号验证": "账号与身份认证",
    "登录与身份验证": "账号与身份认证",
    "地图定位与附近服务": "地图与位置服务",
    "拍摄扫码与内容采集": "媒体拍摄与扫码",
    "文件选择与存储管理": "文件与数据管理",
    "即时通信与社交互动": "社交互动与通信",
    "支付与交易": "支付与金融交易",
    "系统工具与辅助功能": "设备清理与系统优化",
}


def safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def load_json_list(path: Path) -> List[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def normalize_scene(scene: Any) -> str:
    if not isinstance(scene, str):
        return ""
    return scene.strip()


def canonical_scene(scene: str, use_alias_map: bool) -> str:
    if not scene:
        return ""
    if not use_alias_map:
        return scene
    return SCENE_ALIAS_MAP.get(scene, scene)


def get_scene_from_item(item: Dict[str, Any], is_gt: bool, use_alias_map: bool) -> str:
    if is_gt:
        keys = ("true_scene", "ground_truth_scene", "label_scene", "predicted_scene", "scene")
    else:
        keys = ("predicted_scene", "scene", "top1")
    for key in keys:
        scene = normalize_scene(item.get(key))
        if scene:
            return canonical_scene(scene, use_alias_map)
    return ""


def get_top3(item: Dict[str, Any], pred_scene: str, use_alias_map: bool) -> List[str]:
    top3_raw = item.get("scene_top3", [])
    top3: List[str] = []
    if isinstance(top3_raw, list):
        top3 = [
            canonical_scene(normalize_scene(x), use_alias_map)
            for x in top3_raw
            if normalize_scene(x)
        ]
    elif isinstance(top3_raw, str):
        top3 = [
            canonical_scene(normalize_scene(x), use_alias_map)
            for x in top3_raw.split(",")
            if normalize_scene(x)
        ]

    if pred_scene and pred_scene not in top3:
        top3 = [pred_scene] + top3
    return top3[:3]


def key_by_chain(items: Iterable[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    out: Dict[Any, Dict[str, Any]] = {}
    for item in items:
        cid = item.get("chain_id")
        if cid is None:
            continue
        if cid not in out:
            out[cid] = item
    return out


def evaluate_one_app(
    app_dir: Path, pred_file: str, gt_file: str, use_alias_map: bool
) -> Dict[str, Any]:
    gt_path = app_dir / gt_file
    pred_path = app_dir / pred_file

    app_result: Dict[str, Any] = {
        "app": app_dir.name,
        "gt_file_exists": gt_path.exists(),
        "pred_file_exists": pred_path.exists(),
        "gt_chains": 0,
        "valid_gt_chains": 0,
        "compared_chains": 0,
        "missing_predictions": 0,
        "invalid_gt_scene": 0,
        "invalid_pred_scene": 0,
        "top1_correct": 0,
        "top3_correct": 0,
        "top1_accuracy": 0.0,
        "top3_accuracy": 0.0,
        "confusion": {},
    }

    if not gt_path.exists():
        return app_result

    gt_items = load_json_list(gt_path)
    pred_items = load_json_list(pred_path) if pred_path.exists() else []

    gt_map = key_by_chain(gt_items)
    pred_map = key_by_chain(pred_items)

    app_result["gt_chains"] = len(gt_map)

    confusion: Dict[str, Counter[str]] = defaultdict(Counter)

    for chain_id, gt_item in gt_map.items():
        gt_scene = get_scene_from_item(gt_item, is_gt=True, use_alias_map=use_alias_map)
        if not gt_scene:
            app_result["invalid_gt_scene"] += 1
            continue

        app_result["valid_gt_chains"] += 1
        pred_item = pred_map.get(chain_id)
        if pred_item is None:
            app_result["missing_predictions"] += 1
            continue

        pred_scene = get_scene_from_item(pred_item, is_gt=False, use_alias_map=use_alias_map)
        if not pred_scene:
            app_result["invalid_pred_scene"] += 1
            continue

        app_result["compared_chains"] += 1
        if pred_scene == gt_scene:
            app_result["top1_correct"] += 1

        top3 = get_top3(pred_item, pred_scene, use_alias_map)
        if gt_scene in top3:
            app_result["top3_correct"] += 1

        confusion[gt_scene][pred_scene] += 1

    app_result["top1_accuracy"] = safe_div(
        app_result["top1_correct"], app_result["compared_chains"]
    )
    app_result["top3_accuracy"] = safe_div(
        app_result["top3_correct"], app_result["compared_chains"]
    )
    app_result["confusion"] = {
        gt: dict(sorted(preds.items(), key=lambda x: (-x[1], x[0])))
        for gt, preds in sorted(confusion.items(), key=lambda x: x[0])
    }
    return app_result


def merge_confusion(per_app: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    merged: Dict[str, Counter[str]] = defaultdict(Counter)
    for app in per_app:
        app_conf = app.get("confusion", {})
        if not isinstance(app_conf, dict):
            continue
        for gt_scene, pred_map in app_conf.items():
            if not isinstance(pred_map, dict):
                continue
            for pred_scene, cnt in pred_map.items():
                if isinstance(cnt, int):
                    merged[gt_scene][pred_scene] += cnt
    return {
        gt: dict(sorted(preds.items(), key=lambda x: (-x[1], x[0])))
        for gt, preds in sorted(merged.items(), key=lambda x: x[0])
    }


def calc_per_scene_metrics(confusion: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    all_scenes = set(confusion.keys())
    for pred_map in confusion.values():
        all_scenes.update(pred_map.keys())

    rows: List[Dict[str, Any]] = []
    for scene in sorted(all_scenes):
        tp = confusion.get(scene, {}).get(scene, 0)
        fp = sum(confusion.get(gt, {}).get(scene, 0) for gt in all_scenes if gt != scene)
        fn = sum(confusion.get(scene, {}).get(pred, 0) for pred in all_scenes if pred != scene)
        support = tp + fn
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        rows.append(
            {
                "scene": scene,
                "support": support,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "top1_accuracy": recall,
            }
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Evaluate scene task13 accuracy")
    parser.add_argument(
        "--processed-root",
        type=Path,
        default=project_root / "data" / "processed",
        help="Processed root directory",
    )
    parser.add_argument(
        "--pred-file",
        default="result_scene_text.json",
        help="Prediction filename in each app folder",
    )
    parser.add_argument(
        "--gt-file",
        default="results_scene_task13.json",
        help="Ground truth filename in each app folder",
    )
    parser.add_argument(
        "--output-file",
        default="scene_task13_accuracy_report.json",
        help="Output filename under processed-root",
    )
    parser.add_argument(
        "--app-prefix",
        default="fastbot-",
        help="Only evaluate folders with this prefix",
    )
    parser.add_argument(
        "--no-alias-map",
        action="store_true",
        help="Disable old->new scene label alias mapping",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    processed_root: Path = args.processed_root.resolve()
    output_path = (processed_root / args.output_file).resolve()

    app_dirs = [
        p
        for p in sorted(processed_root.iterdir(), key=lambda x: x.name)
        if p.is_dir() and p.name.startswith(args.app_prefix)
    ]

    use_alias_map = not args.no_alias_map
    per_app = [
        evaluate_one_app(app_dir, args.pred_file, args.gt_file, use_alias_map=use_alias_map)
        for app_dir in app_dirs
    ]

    apps_total = len(app_dirs)
    apps_with_gt = sum(1 for r in per_app if r["gt_file_exists"])
    apps_with_pred = sum(1 for r in per_app if r["pred_file_exists"])
    apps_evaluated = sum(1 for r in per_app if r["compared_chains"] > 0)
    apps_missing_pred = sum(
        1 for r in per_app if r["gt_file_exists"] and not r["pred_file_exists"]
    )

    total_gt = sum(r["gt_chains"] for r in per_app)
    total_valid_gt = sum(r["valid_gt_chains"] for r in per_app)
    total_compared = sum(r["compared_chains"] for r in per_app)
    total_missing_pred = sum(r["missing_predictions"] for r in per_app)
    total_invalid_gt = sum(r["invalid_gt_scene"] for r in per_app)
    total_invalid_pred = sum(r["invalid_pred_scene"] for r in per_app)
    total_top1_correct = sum(r["top1_correct"] for r in per_app)
    total_top3_correct = sum(r["top3_correct"] for r in per_app)

    confusion = merge_confusion(per_app)
    per_scene_metrics = calc_per_scene_metrics(confusion)
    macro_f1 = safe_div(
        sum(r["f1"] for r in per_scene_metrics if r["support"] > 0),
        sum(1 for r in per_scene_metrics if r["support"] > 0),
    )

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "processed_root": str(processed_root),
        "pred_file": args.pred_file,
        "gt_file": args.gt_file,
        "alias_map_enabled": use_alias_map,
        "scene_alias_map": SCENE_ALIAS_MAP if use_alias_map else {},
        "apps_total": apps_total,
        "apps_with_gt": apps_with_gt,
        "apps_with_pred": apps_with_pred,
        "apps_evaluated": apps_evaluated,
        "apps_missing_pred_file": apps_missing_pred,
        "total_chains_gt": total_gt,
        "total_chains_gt_valid": total_valid_gt,
        "total_chains_compared": total_compared,
        "total_missing_predictions": total_missing_pred,
        "total_invalid_gt_scene": total_invalid_gt,
        "total_invalid_pred_scene": total_invalid_pred,
        "overall_top1_accuracy": safe_div(total_top1_correct, total_compared),
        "overall_top3_accuracy": safe_div(total_top3_correct, total_compared),
        "overall_macro_f1": macro_f1,
        "per_scene_metrics": per_scene_metrics,
        "confusion_matrix": confusion,
        "per_app": per_app,
    }

    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[DONE] Scene accuracy report saved: {output_path}")
    print(
        "[STATS] compared={compared} top1={top1:.4f} top3={top3:.4f}".format(
            compared=total_compared,
            top1=safe_div(total_top1_correct, total_compared),
            top3=safe_div(total_top3_correct, total_compared),
        )
    )


if __name__ == "__main__":
    main()
