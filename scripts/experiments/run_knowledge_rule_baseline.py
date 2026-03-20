#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Knowledge-rule baseline (no LLM):
Use result_retrieved_knowledge.json and apply deterministic rules.

Input per app:
  - result_retrieved_knowledge.json
Output per app:
  - result_knowledge_rule_baseline.json
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

OUT_FILE = "result_knowledge_rule_baseline.json"
IN_FILE = "result_retrieved_knowledge.json"


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _score_record(item: Dict[str, Any]) -> Dict[str, Any]:
    rk = _as_dict(item.get("retrieved_knowledge"))
    rules = _as_list(rk.get("retrieved_rules"))

    if not rules:
        return {
            "pred": "risky",
            "reason": "no_matched_rule",
            "stats": {
                "rule_count": 0,
                "pos": 0,
                "neg": 0,
                "boundary_missing": 0,
                "max_conflict": 0.0,
                "max_score": 0.0,
            },
        }

    pos = 0
    neg = 0
    boundary_missing = 0
    max_conflict = 0.0
    max_score = -1e9

    for r in rules:
        rd = _as_dict(r)
        pos += _as_int(rd.get("matched_pos_count"), 0)
        neg += _as_int(rd.get("matched_neg_count"), 0)
        boundary_missing += len(_as_list(rd.get("boundary_missing")))
        max_conflict = max(max_conflict, _as_float(rd.get("conflict_ratio"), 0.0))
        max_score = max(max_score, _as_float(rd.get("retrieval_score"), -1e9))

    # Deterministic boundary-aware decision
    if neg > pos and neg >= 1:
        pred, reason = "risky", "negative_evidence_dominant"
    elif boundary_missing >= 1 and pos == 0:
        pred, reason = "risky", "boundary_missing_no_positive"
    elif pos >= 2 and neg == 0 and boundary_missing == 0 and max_conflict < 0.45 and max_score >= 8.0:
        pred, reason = "safe", "positive_evidence_clear"
    else:
        pred, reason = "risky", "insufficient_or_conflicting_evidence"

    return {
        "pred": pred,
        "reason": reason,
        "stats": {
            "rule_count": len(rules),
            "pos": pos,
            "neg": neg,
            "boundary_missing": boundary_missing,
            "max_conflict": round(max_conflict, 3),
            "max_score": round(max_score, 3),
        },
    }


def _iter_app_dirs(target: str, app_prefix: str, app: str) -> List[str]:
    if os.path.isfile(os.path.join(target, "result.json")):
        return [target]
    if not os.path.isdir(target):
        return []
    if app:
        p = os.path.join(target, app)
        return [p] if os.path.isdir(p) else []

    out: List[str] = []
    for d in sorted(os.listdir(target)):
        p = os.path.join(target, d)
        if not os.path.isdir(p):
            continue
        if app_prefix and not d.startswith(app_prefix):
            continue
        out.append(p)
    return out


def run_one_app(app_dir: str, force: bool = False) -> int:
    in_path = os.path.join(app_dir, IN_FILE)
    out_path = os.path.join(app_dir, OUT_FILE)

    if not os.path.exists(in_path):
        print(f"[SKIP] {os.path.basename(app_dir)} missing {IN_FILE}")
        return 0

    if (not force) and os.path.exists(out_path):
        try:
            rows = json.load(open(out_path, "r", encoding="utf-8"))
            n = len(rows) if isinstance(rows, list) else 0
        except Exception:
            n = 0
        print(f"[SKIP] {os.path.basename(app_dir)} output exists ({n})")
        return n

    try:
        rows = json.load(open(in_path, "r", encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] {os.path.basename(app_dir)} read failed: {exc}")
        return 0

    out: List[Dict[str, Any]] = []
    for i, raw in enumerate(_as_list(rows)):
        item = _as_dict(raw)
        try:
            chain_id = int(item.get("chain_id", i))
        except Exception:
            chain_id = i

        decision = _score_record(item)
        out.append(
            {
                "chain_id": chain_id,
                "pred": decision["pred"],
                "reason": decision["reason"],
                "stats": decision["stats"],
            }
        )

    out.sort(key=lambda x: int(x.get("chain_id", -1)))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[DONE] {os.path.basename(app_dir)} chains={len(out)} -> {OUT_FILE}")
    return len(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run knowledge-rule baseline from retrieval outputs")
    parser.add_argument("target", nargs="?", default=os.path.join("data", "processed"))
    parser.add_argument("--app-prefix", default="fastbot-")
    parser.add_argument("--app", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    app_dirs = _iter_app_dirs(target, app_prefix=args.app_prefix, app=args.app)
    if not app_dirs:
        raise SystemExit(f"no app dirs found: {target}")

    total = 0
    for app_dir in app_dirs:
        total += run_one_app(app_dir, force=args.force)

    print(f"[SUMMARY] apps={len(app_dirs)} chains={total} out={OUT_FILE}")


if __name__ == "__main__":
    main()
