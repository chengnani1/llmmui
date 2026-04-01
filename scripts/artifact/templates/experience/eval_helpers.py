#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


JsonDict = Dict[str, Any]


def as_dict(value: Any) -> JsonDict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def write_csv(path: Path, rows: List[JsonDict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def relpath_str(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except Exception:
        return path.name


def iter_app_dirs(processed_root: Path) -> List[Path]:
    return [
        child
        for child in sorted(processed_root.iterdir())
        if child.is_dir() and child.name.startswith("fastbot-")
    ]


def map_by_chain(items: Any) -> Dict[int, JsonDict]:
    out: Dict[int, JsonDict] = {}
    for idx, raw in enumerate(as_list(items)):
        item = as_dict(raw)
        if not item:
            continue
        try:
            chain_id = int(item.get("chain_id", idx))
        except Exception:
            chain_id = idx
        if chain_id not in out:
            out[chain_id] = item
    return out


def gt_to_binary(item: JsonDict) -> Optional[int]:
    if str(item.get("gt_risk")) in {"0", "1"}:
        return int(item["gt_risk"])
    if str(item.get("label")) in {"0", "1"}:
        return int(item["label"])
    text = str(item.get("gt_label", "")).strip().upper()
    if text == "RISKY":
        return 1
    if text == "SAFE":
        return 0
    return None


def final_to_binary(item: JsonDict) -> Optional[int]:
    decision = str(item.get("final_decision", "") or item.get("llm_final_decision", "")).strip().upper()
    if decision in {"CLEARLY_RISKY", "NON_COMPLIANT", "RISKY", "NEED_REVIEW", "SUSPICIOUS"}:
        return 1
    if decision in {"CLEARLY_OK", "COMPLIANT", "SAFE"}:
        return 0

    risk = str(item.get("final_risk", "") or item.get("llm_final_risk", "")).strip().upper()
    if risk == "HIGH":
        return 1
    if risk == "LOW":
        return 0
    if risk == "MEDIUM":
        return 1
    return None


def simple_pred_to_binary(item: JsonDict) -> Optional[int]:
    pred = str(item.get("pred", "")).strip().lower()
    if pred == "risky":
        return 1
    if pred == "safe":
        return 0
    return None


def vlm_to_binary(item: JsonDict) -> Optional[int]:
    value = item.get("pred_risk")
    if str(value) in {"0", "1"}:
        return int(value)
    label = str(item.get("pred_label", "")).strip().lower()
    if label == "risky":
        return 1
    if label == "safe":
        return 0
    return None


def binary_metrics(tp: int, fp: int, tn: int, fn: int) -> JsonDict:
    total = tp + fp + tn + fn
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    specificity = safe_div(tn, tn + fp)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return {
        "evaluated": total,
        "accuracy": round(safe_div(tp + tn, total), 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "specificity": round(specificity, 4),
        "balanced_accuracy": round((recall + specificity) / 2 if total else 0.0, 4),
    }


def evaluate_predictions(
    processed_root: Path,
    pred_file: str,
    pred_mapper: Callable[[JsonDict], Optional[int]],
    gt_file: str = "label_judge.json",
) -> JsonDict:
    tp = fp = tn = fn = 0
    missing_pred = missing_gt = skipped = 0
    per_app: List[JsonDict] = []

    for app_dir in iter_app_dirs(processed_root):
        pred_path = app_dir / pred_file
        gt_path = app_dir / gt_file
        if not pred_path.exists():
            per_app.append(
                {
                    "app": app_dir.name,
                    "pred_exists": False,
                    "gt_exists": gt_path.exists(),
                    "evaluated": 0,
                }
            )
            continue

        pred_map = map_by_chain(load_json(pred_path))
        gt_map = map_by_chain(load_json(gt_path)) if gt_path.exists() else {}

        app_tp = app_fp = app_tn = app_fn = app_missing_pred = app_missing_gt = app_skipped = 0
        for chain_id in sorted(set(pred_map) | set(gt_map)):
            pred_item = pred_map.get(chain_id)
            gt_item = gt_map.get(chain_id)
            if pred_item is None:
                missing_pred += 1
                app_missing_pred += 1
                continue
            if gt_item is None:
                missing_gt += 1
                app_missing_gt += 1
                continue

            pred_value = pred_mapper(pred_item)
            gt_value = gt_to_binary(gt_item)
            if pred_value is None:
                skipped += 1
                app_skipped += 1
                continue
            if gt_value is None:
                missing_gt += 1
                app_missing_gt += 1
                continue

            if pred_value == 1 and gt_value == 1:
                tp += 1
                app_tp += 1
            elif pred_value == 1 and gt_value == 0:
                fp += 1
                app_fp += 1
            elif pred_value == 0 and gt_value == 0:
                tn += 1
                app_tn += 1
            else:
                fn += 1
                app_fn += 1

        per_app.append(
            {
                "app": app_dir.name,
                "pred_exists": True,
                "gt_exists": gt_path.exists(),
                "evaluated": app_tp + app_fp + app_tn + app_fn,
                "tp": app_tp,
                "fp": app_fp,
                "tn": app_tn,
                "fn": app_fn,
                "missing_pred": app_missing_pred,
                "missing_gt": app_missing_gt,
                "skipped": app_skipped,
            }
        )

    metrics = binary_metrics(tp, fp, tn, fn)
    return {
        "pred_file": pred_file,
        "apps_total": len(iter_app_dirs(processed_root)),
        "confusion": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "missing_pred": missing_pred,
            "missing_gt": missing_gt,
            "skipped": skipped,
        },
        "metrics": metrics,
        "per_app": per_app,
    }


def summarize_labels(processed_root: Path) -> JsonDict:
    risky = safe = chains = 0
    for app_dir in iter_app_dirs(processed_root):
        gt_path = app_dir / "label_judge.json"
        if not gt_path.exists():
            continue
        for item in as_list(load_json(gt_path)):
            label = gt_to_binary(as_dict(item))
            if label is None:
                continue
            chains += 1
            if label == 1:
                risky += 1
            else:
                safe += 1
    return {"chains": chains, "risky": risky, "safe": safe}


def collect_permission_types(processed_root: Path) -> List[str]:
    permissions = set()
    candidate_files = ["result_final_decision.json", "result_permission.json", "labels_permission.json"]
    for app_dir in iter_app_dirs(processed_root):
        for name in candidate_files:
            path = app_dir / name
            if not path.exists():
                continue
            for item in as_list(load_json(path)):
                row = as_dict(item)
                values: Iterable[Any] = []
                if isinstance(row.get("permissions"), list):
                    values = row["permissions"]
                elif isinstance(row.get("predicted_permissions"), list):
                    values = row["predicted_permissions"]
                for permission in values:
                    text = str(permission).strip()
                    if text:
                        permissions.add(text)
            break
    return sorted(permissions)


def collect_ui_scenes(processed_root: Path) -> List[str]:
    scenes = set()
    for app_dir in iter_app_dirs(processed_root):
        path = app_dir / "result_semantic_v2.json"
        if not path.exists():
            continue
        for item in as_list(load_json(path)):
            row = as_dict(item)
            scene_obj = as_dict(row.get("scene"))
            text = str(scene_obj.get("ui_task_scene", "") or row.get("ui_task_scene", "")).strip()
            if text:
                scenes.add(text)
    return sorted(scenes)


def derived_medium_bucket(row: JsonDict) -> str:
    risk = str(row.get("final_risk", "")).strip().upper()
    if risk == "LOW":
        return "LOW"
    if risk == "HIGH":
        return "HIGH"
    if risk != "MEDIUM":
        return "UNKNOWN"

    over_scope = str(as_dict(row.get("over_scope")).get("label", "")).strip()
    if over_scope in {"potentially_over_scoped", "over_scoped"}:
        return "MEDIUM-over"
    return "MEDIUM-consistent"
