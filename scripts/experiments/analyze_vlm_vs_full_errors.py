#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare VLM-Direct vs Full-Pipeline errors against ground truth.

Input files per app dir:
  - label_judge.json (fallback: labels_judge.json)
  - result_vlm_direct_risk.json
  - result_final_decision.json
  - result_chain_semantics.json
  - result_ui_task_scene.json
  - result_rule_screening.json
  - result_llm_review.json

Outputs (under processed root):
  - vlm_correct_full_wrong.csv
  - vlm_wrong_full_correct.csv
  - error_comparison_summary.json
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Tuple


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from judgement_analysis_utils import (  # noqa: E402
    RISKY,
    SAFE,
    iter_app_dirs,
    load_json,
    map_by_chain_id,
    map_final_to_binary,
    map_gt_to_binary,
    normalize_binary_label,
    save_csv,
    save_json,
)


CSV_COLUMNS = [
    "app",
    "chain_id",
    "gt_label",
    "vlm_pred",
    "full_pred",
    "permissions",
    "ui_task_scene",
    "rule_signal",
    "llm_final_decision",
    "task_phrase",
    "intent",
    "page_function",
    "chain_summary",
]


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _first_non_empty(*values: Any) -> Any:
    for v in values:
        if isinstance(v, str):
            if v.strip():
                return v
            continue
        if isinstance(v, list):
            if v:
                return v
            continue
        if isinstance(v, dict):
            if v:
                return v
            continue
        if v is not None:
            return v
    return ""


def _dedup(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        s = str(x).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _split_to_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return _dedup([str(x) for x in v])
    if isinstance(v, str):
        raw = []
        for part in v.replace(",", ";").split(";"):
            p = part.strip()
            if p:
                raw.append(p)
        return _dedup(raw)
    return []


def _join_list(v: List[str]) -> str:
    return ";".join(_dedup(v))


def _resolve_gt_path(app_dir: str) -> str:
    p = os.path.join(app_dir, "label_judge.json")
    if os.path.exists(p):
        return p
    p2 = os.path.join(app_dir, "labels_judge.json")
    if os.path.exists(p2):
        return p2
    return p


def _map_vlm_to_binary(vlm_item: Dict[str, Any]) -> str:
    v = vlm_item.get("pred_risk")
    if str(v) in {"0", "1"}:
        return RISKY if int(v) == 1 else SAFE

    for key in ("pred_label", "pred", "risk_label", "label"):
        b = normalize_binary_label(vlm_item.get(key))
        if b:
            return b
    return ""


def _extract_permissions(
    sem_item: Dict[str, Any],
    rule_item: Dict[str, Any],
    llm_item: Dict[str, Any],
    final_item: Dict[str, Any],
) -> List[str]:
    out: List[str] = []
    out.extend(_split_to_list(rule_item.get("permissions")))
    out.extend(_split_to_list(final_item.get("permissions")))
    out.extend(_split_to_list(llm_item.get("permissions")))
    out.extend(_split_to_list(_as_dict(sem_item.get("permission_event")).get("permissions")))
    return _dedup(out)


def _ui_task_scene(scene_item: Dict[str, Any], rule_item: Dict[str, Any]) -> str:
    return str(
        _first_non_empty(
            scene_item.get("ui_task_scene"),
            scene_item.get("predicted_scene"),
            rule_item.get("ui_task_scene"),
            rule_item.get("scene"),
        )
        or ""
    ).strip()


def _build_detail_row(
    app: str,
    chain_id: int,
    gt: str,
    vlm_pred: str,
    full_pred: str,
    sem_item: Dict[str, Any],
    scene_item: Dict[str, Any],
    rule_item: Dict[str, Any],
    llm_item: Dict[str, Any],
    final_item: Dict[str, Any],
) -> Dict[str, Any]:
    permissions = _extract_permissions(sem_item, rule_item, llm_item, final_item)
    rule_signal = str(_first_non_empty(rule_item.get("overall_rule_signal"), rule_item.get("rule_signal")) or "").strip()
    llm_final_decision = str(_first_non_empty(llm_item.get("llm_final_decision"), final_item.get("llm_final_decision")) or "").strip()

    task_phrase = str(
        _first_non_empty(
            sem_item.get("task_phrase"),
            scene_item.get("task_phrase"),
            rule_item.get("task_phrase"),
            llm_item.get("task_phrase"),
            final_item.get("task_phrase"),
        )
        or ""
    ).strip()
    intent = str(
        _first_non_empty(
            sem_item.get("intent"),
            scene_item.get("intent"),
            rule_item.get("intent"),
            llm_item.get("intent"),
            final_item.get("intent"),
        )
        or ""
    ).strip()
    page_function = str(
        _first_non_empty(
            sem_item.get("page_function"),
            scene_item.get("page_function"),
            rule_item.get("page_function"),
            llm_item.get("page_function"),
            final_item.get("page_function"),
        )
        or ""
    ).strip()
    chain_summary = str(
        _first_non_empty(
            sem_item.get("chain_summary"),
            scene_item.get("chain_summary"),
            rule_item.get("chain_summary"),
            llm_item.get("chain_summary"),
            final_item.get("chain_summary"),
        )
        or ""
    ).strip()

    return {
        "app": app,
        "chain_id": chain_id,
        "gt_label": gt,
        "vlm_pred": vlm_pred,
        "full_pred": full_pred,
        "permissions": _join_list(permissions),
        "ui_task_scene": _ui_task_scene(scene_item, rule_item),
        "rule_signal": rule_signal,
        "llm_final_decision": llm_final_decision,
        "task_phrase": task_phrase,
        "intent": intent,
        "page_function": page_function,
        "chain_summary": chain_summary,
    }


def _counter_rows(counter: Counter, total: int, top_k: int | None = None) -> List[Dict[str, Any]]:
    pairs = counter.most_common(top_k)
    out = []
    for key, cnt in pairs:
        out.append(
            {
                "key": str(key),
                "count": int(cnt),
                "ratio": (float(cnt) / float(total)) if total else 0.0,
            }
        )
    return out


def _add_multi_counter(counter: Counter, serialized_items: str) -> None:
    for x in _split_to_list(serialized_items):
        counter[x] += 1


def _analyze_rows(rows: List[Dict[str, Any]], app_top_k: int = 20) -> Dict[str, Any]:
    perm_counter = Counter()
    scene_counter = Counter()
    rule_counter = Counter()
    llm_counter = Counter()
    app_counter = Counter()

    for r in rows:
        _add_multi_counter(perm_counter, r.get("permissions", ""))
        scene = str(r.get("ui_task_scene", "")).strip() or "UNKNOWN"
        rule_signal = str(r.get("rule_signal", "")).strip() or "UNKNOWN"
        llm_decision = str(r.get("llm_final_decision", "")).strip() or "UNKNOWN"
        app = str(r.get("app", "")).strip() or "UNKNOWN"

        scene_counter[scene] += 1
        rule_counter[rule_signal] += 1
        llm_counter[llm_decision] += 1
        app_counter[app] += 1

    total = len(rows)
    return {
        "count": total,
        "permission_distribution": _counter_rows(perm_counter, total),
        "ui_task_scene_distribution": _counter_rows(scene_counter, total),
        "rule_signal_distribution": _counter_rows(rule_counter, total),
        "llm_final_decision_distribution": _counter_rows(llm_counter, total),
        "app_distribution_top20": _counter_rows(app_counter, total, top_k=app_top_k),
    }


def run(processed_root: str, app_prefix: str = "") -> Dict[str, Any]:
    app_dirs = iter_app_dirs(processed_root, app_prefix=app_prefix)

    totals = {
        "apps_total": len(app_dirs),
        "chains_total": 0,
        "evaluated_chains": 0,
        "missing_gt": 0,
        "missing_vlm_pred": 0,
        "missing_full_pred": 0,
        "invalid_gt": 0,
        "invalid_vlm_pred": 0,
        "invalid_full_pred": 0,
    }

    set_counts = {
        "both_correct": 0,            # A
        "both_wrong": 0,              # B
        "vlm_correct_full_wrong": 0,  # C
        "vlm_wrong_full_correct": 0,  # D
    }

    c_rows: List[Dict[str, Any]] = []
    d_rows: List[Dict[str, Any]] = []

    for app_dir in app_dirs:
        app = os.path.basename(app_dir)

        gt_map = map_by_chain_id(load_json(_resolve_gt_path(app_dir)))
        vlm_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_vlm_direct_risk.json")))
        final_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_final_decision.json")))

        sem_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_chain_semantics.json")))
        scene_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_ui_task_scene.json")))
        rule_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_rule_screening.json")))
        llm_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_llm_review.json")))

        chain_ids = sorted(set(gt_map.keys()) | set(vlm_map.keys()) | set(final_map.keys()))
        totals["chains_total"] += len(chain_ids)

        for cid in chain_ids:
            gt_item = _as_dict(gt_map.get(cid))
            vlm_item = _as_dict(vlm_map.get(cid))
            final_item = _as_dict(final_map.get(cid))

            if not gt_item:
                totals["missing_gt"] += 1
                continue
            if not vlm_item:
                totals["missing_vlm_pred"] += 1
                continue
            if not final_item:
                totals["missing_full_pred"] += 1
                continue

            gt = map_gt_to_binary(gt_item)
            vlm_pred = _map_vlm_to_binary(vlm_item)
            full_pred = map_final_to_binary(
                final_item.get("final_decision"),
                final_item.get("final_risk"),
                llm_final_decision=final_item.get("llm_final_decision"),
                llm_final_risk=final_item.get("llm_final_risk"),
            )

            if not gt:
                totals["invalid_gt"] += 1
                continue
            if not vlm_pred:
                totals["invalid_vlm_pred"] += 1
                continue
            if not full_pred:
                totals["invalid_full_pred"] += 1
                continue

            totals["evaluated_chains"] += 1

            vlm_ok = (vlm_pred == gt)
            full_ok = (full_pred == gt)

            if vlm_ok and full_ok:
                set_counts["both_correct"] += 1
                continue
            if (not vlm_ok) and (not full_ok):
                set_counts["both_wrong"] += 1
                continue

            sem_item = _as_dict(sem_map.get(cid))
            scene_item = _as_dict(scene_map.get(cid))
            rule_item = _as_dict(rule_map.get(cid))
            llm_item = _as_dict(llm_map.get(cid))

            row = _build_detail_row(
                app=app,
                chain_id=cid,
                gt=gt,
                vlm_pred=vlm_pred,
                full_pred=full_pred,
                sem_item=sem_item,
                scene_item=scene_item,
                rule_item=rule_item,
                llm_item=llm_item,
                final_item=final_item,
            )

            if vlm_ok and (not full_ok):
                set_counts["vlm_correct_full_wrong"] += 1
                c_rows.append(row)
            elif (not vlm_ok) and full_ok:
                set_counts["vlm_wrong_full_correct"] += 1
                d_rows.append(row)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "processed_root": os.path.abspath(processed_root),
        "totals": totals,
        "sets": set_counts,
        "analysis": {
            "vlm_correct_full_wrong": _analyze_rows(c_rows, app_top_k=20),
            "vlm_wrong_full_correct": _analyze_rows(d_rows, app_top_k=20),
        },
    }

    return {
        "summary": summary,
        "rows_c": c_rows,
        "rows_d": d_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze VLM-Direct vs Full-Pipeline errors by chain")
    parser.add_argument("processed_root", nargs="?", default=os.path.join("data", "processed"))
    parser.add_argument("--app-prefix", default="", help="optional app prefix filter")
    parser.add_argument("--out-summary", default="error_comparison_summary.json")
    parser.add_argument("--out-csv-c", default="vlm_correct_full_wrong.csv")
    parser.add_argument("--out-csv-d", default="vlm_wrong_full_correct.csv")
    args = parser.parse_args()

    processed_root = os.path.abspath(args.processed_root)
    if not os.path.isdir(processed_root):
        raise SystemExit(f"processed_root not found: {processed_root}")

    result = run(processed_root=processed_root, app_prefix=args.app_prefix)

    summary_path = os.path.join(processed_root, args.out_summary)
    csv_c_path = os.path.join(processed_root, args.out_csv_c)
    csv_d_path = os.path.join(processed_root, args.out_csv_d)

    save_json(summary_path, result["summary"])
    save_csv(csv_c_path, result["rows_c"], CSV_COLUMNS)
    save_csv(csv_d_path, result["rows_d"], CSV_COLUMNS)

    sets = result["summary"]["sets"]
    totals = result["summary"]["totals"]
    print("========== VLM vs Full Error Comparison ==========")
    print(f"apps_total               : {totals['apps_total']}")
    print(f"chains_total             : {totals['chains_total']}")
    print(f"evaluated_chains         : {totals['evaluated_chains']}")
    print(f"both_correct (A)         : {sets['both_correct']}")
    print(f"both_wrong (B)           : {sets['both_wrong']}")
    print(f"vlm_correct_full_wrong(C): {sets['vlm_correct_full_wrong']}")
    print(f"vlm_wrong_full_correct(D): {sets['vlm_wrong_full_correct']}")
    print(f"summary                  : {summary_path}")
    print(f"csv C                    : {csv_c_path}")
    print(f"csv D                    : {csv_d_path}")
    print("==================================================")


if __name__ == "__main__":
    main()

