#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilities for judgement analysis experiments.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple


SAFE = "SAFE"
RISKY = "RISKY"

MODE_TO_FIELD = {
    "rule": "pred_rule_binary",
    "llm": "pred_llm_binary",
    "final": "pred_final_binary",
}


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def save_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_csv(path: str, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def load_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as f:
        return [dict(x) for x in csv.DictReader(f)]


def iter_app_dirs(processed_root: str, app_prefix: str = "fastbot-") -> List[str]:
    if os.path.exists(os.path.join(processed_root, "result.json")):
        return [processed_root]
    out = []
    if not os.path.isdir(processed_root):
        return out
    for d in sorted(os.listdir(processed_root)):
        app_dir = os.path.join(processed_root, d)
        if not os.path.isdir(app_dir):
            continue
        if app_prefix and (not d.startswith(app_prefix)):
            continue
        out.append(app_dir)
    return out


def parse_chain_id(item: Dict[str, Any], fallback: int) -> int:
    try:
        return int(item.get("chain_id", fallback))
    except Exception:
        return fallback


def map_by_chain_id(items: Any) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for i, raw in enumerate(items if isinstance(items, list) else []):
        if not isinstance(raw, dict):
            continue
        cid = parse_chain_id(raw, i)
        if cid not in out:
            out[cid] = raw
    return out


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def stringify_list(v: Any, sep: str = ";") -> str:
    arr = []
    for x in as_list(v):
        s = str(x).strip()
        if s:
            arr.append(s)
    seen = set()
    out = []
    for x in arr:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return sep.join(out)


def split_serialized_list(v: Any) -> List[str]:
    s = str(v or "").strip()
    if not s:
        return []
    raw = []
    for part in s.replace(",", ";").split(";"):
        p = part.strip()
        if p:
            raw.append(p)
    seen = set()
    out = []
    for x in raw:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def normalize_binary_label(v: Any) -> str:
    s = str(v or "").strip().upper()
    if not s:
        return ""
    safe_tokens = {
        "SAFE",
        "NO_RISK",
        "LOW",
        "LOW_RISK",
        "COMPLIANT",
        "CLEARLY_OK",
        "0",
        "无风险",
        "低风险",
        "合规",
    }
    risky_tokens = {
        "RISKY",
        "RISK",
        "HIGH",
        "MEDIUM",
        "HIGH_RISK",
        "MEDIUM_RISK",
        "SUSPICIOUS",
        "NON_COMPLIANT",
        "CLEARLY_RISKY",
        "NEED_REVIEW",
        "1",
        "有风险",
        "中风险",
        "高风险",
        "违规",
        "可疑",
    }
    if s in safe_tokens:
        return SAFE
    if s in risky_tokens:
        return RISKY
    return ""


def map_gt_to_binary(label_item: Dict[str, Any]) -> str:
    if str(label_item.get("gt_risk")) in {"0", "1"}:
        return RISKY if int(label_item.get("gt_risk")) == 1 else SAFE
    candidates = [
        label_item.get("gt_label"),
        label_item.get("label_text"),
        label_item.get("label"),
        label_item.get("risk_label"),
    ]
    for c in candidates:
        b = normalize_binary_label(c)
        if b:
            return b
    return ""


def map_rule_to_binary(rule_signal: Any) -> str:
    s = str(rule_signal or "").strip().upper()
    if s == "LOW_RISK":
        return SAFE
    if s in {"MEDIUM_RISK", "HIGH_RISK"}:
        return RISKY
    return ""


def map_llm_to_binary(llm_final_decision: Any, llm_final_risk: Any = None) -> str:
    d = str(llm_final_decision or "").strip().upper()
    if d == "COMPLIANT":
        return SAFE
    if d in {"SUSPICIOUS", "NON_COMPLIANT"}:
        return RISKY
    r = str(llm_final_risk or "").strip().upper()
    if r == "LOW":
        return SAFE
    if r in {"MEDIUM", "HIGH"}:
        return RISKY
    return ""


def map_final_to_binary(
    final_decision: Any,
    final_risk: Any,
    llm_final_decision: Any = None,
    llm_final_risk: Any = None,
) -> str:
    d = str(final_decision or "").strip().upper()
    r = str(final_risk or "").strip().upper()

    if d in {"COMPLIANT", "CLEARLY_OK", "SAFE"}:
        return SAFE
    if d in {"SUSPICIOUS", "NON_COMPLIANT", "CLEARLY_RISKY", "NEED_REVIEW", "RISKY"}:
        return RISKY
    if r == "LOW":
        return SAFE
    if r in {"MEDIUM", "HIGH"}:
        return RISKY

    # fallback to llm-only if final is absent
    return map_llm_to_binary(llm_final_decision, llm_final_risk)


def binary_confusion(gt_pred_pairs: Iterable[Tuple[str, str]]) -> Dict[str, int]:
    tp = fp = tn = fn = 0
    for gt, pred in gt_pred_pairs:
        if gt == RISKY and pred == RISKY:
            tp += 1
        elif gt == SAFE and pred == RISKY:
            fp += 1
        elif gt == SAFE and pred == SAFE:
            tn += 1
        elif gt == RISKY and pred == SAFE:
            fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def confusion_metrics(conf: Dict[str, int]) -> Dict[str, float]:
    tp = int(conf.get("tp", 0))
    fp = int(conf.get("fp", 0))
    tn = int(conf.get("tn", 0))
    fn = int(conf.get("fn", 0))
    total = tp + fp + tn + fn
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    specificity = _safe_div(tn, tn + fp)
    balanced_accuracy = (recall + specificity) / 2 if total else 0.0
    return {
        "accuracy": _safe_div(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": specificity,
        "balanced_accuracy": balanced_accuracy,
    }


def top_counter(counter: Counter, k: int) -> List[Dict[str, Any]]:
    total = sum(counter.values())
    out = []
    for key, count in counter.most_common(k):
        out.append(
            {
                "key": key,
                "count": int(count),
                "ratio": _safe_div(count, total),
            }
        )
    return out


def eval_rows_for_mode(rows: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
    pred_field = MODE_TO_FIELD[mode]
    valid_rows: List[Dict[str, Any]] = []
    missing_pred = 0
    missing_gt = 0
    pairs: List[Tuple[str, str]] = []

    for row in rows:
        gt = normalize_binary_label(row.get("gt_label_binary", ""))
        if not gt:
            missing_gt += 1
            continue
        pred = normalize_binary_label(row.get(pred_field, ""))
        if not pred:
            missing_pred += 1
            continue
        pairs.append((gt, pred))
        valid_rows.append(row)

    conf = binary_confusion(pairs)
    metrics = confusion_metrics(conf)
    return {
        "pred_field": pred_field,
        "valid_rows": valid_rows,
        "pairs": pairs,
        "confusion": conf,
        "metrics": metrics,
        "missing_pred": missing_pred,
        "missing_gt": missing_gt,
    }

