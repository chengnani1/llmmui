#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build unified judgement analysis table by merging phase outputs per chain.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from judgement_analysis_utils import (  # noqa: E402
    iter_app_dirs,
    load_json,
    map_by_chain_id,
    map_final_to_binary,
    map_gt_to_binary,
    map_llm_to_binary,
    map_rule_to_binary,
    save_csv,
    save_jsonl,
    split_serialized_list,
    stringify_list,
)


DEFAULT_TABLE_CSV = "judgement_analysis_table.csv"
DEFAULT_TABLE_JSONL = "judgement_analysis_table.jsonl"


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _load_first_available_json(app_dir: str, *filenames: str) -> Any:
    for name in filenames:
        path = os.path.join(app_dir, name)
        data = load_json(path)
        if data is not None:
            return data
    return None


def _first_non_empty(*values: Any) -> Any:
    for v in values:
        if v is None:
            continue
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
        return v
    return ""


def _extract_reason(obj: Dict[str, Any], key: str) -> str:
    raw = _as_dict(obj.get(key))
    return str(raw.get("reason", "") or "").strip()


def _extract_label(obj: Dict[str, Any], key: str) -> str:
    raw = _as_dict(obj.get(key))
    return str(raw.get("label", "") or "").strip()


def _collect_chain_ids(*maps: Dict[int, Dict[str, Any]]) -> List[int]:
    out = set()
    for mp in maps:
        out.update(mp.keys())
    return sorted(out)


def _canonical_scene_top3(scene_obj: Dict[str, Any]) -> Any:
    return _first_non_empty(
        scene_obj.get("ui_task_scene_top3"),
        scene_obj.get("scene_top3"),
    )


def _build_one_row(
    app_name: str,
    chain_id: int,
    label_item: Dict[str, Any],
    sem: Dict[str, Any],
    ui_scene: Dict[str, Any],
    perm: Dict[str, Any],
    reg: Dict[str, Any],
    rule: Dict[str, Any],
    llm: Dict[str, Any],
    final: Dict[str, Any],
) -> Dict[str, Any]:
    gt_label_raw = str(
        _first_non_empty(
            label_item.get("gt_label"),
            label_item.get("label_text"),
            label_item.get("label"),
            label_item.get("risk_label"),
            label_item.get("gt_risk"),
        )
        or ""
    ).strip()
    gt_label_binary = map_gt_to_binary(label_item) if label_item else ""

    task_phrase = str(
        _first_non_empty(
            sem.get("task_phrase"),
            ui_scene.get("task_phrase"),
            reg.get("task_phrase"),
            rule.get("task_phrase"),
            llm.get("task_phrase"),
            final.get("task_phrase"),
        )
        or ""
    ).strip()
    intent = str(
        _first_non_empty(
            sem.get("intent"),
            ui_scene.get("intent"),
            reg.get("intent"),
            rule.get("intent"),
            llm.get("intent"),
            final.get("intent"),
        )
        or ""
    ).strip()
    page_function = str(
        _first_non_empty(
            sem.get("page_function"),
            ui_scene.get("page_function"),
            rule.get("page_function"),
            llm.get("page_function"),
            final.get("page_function"),
        )
        or ""
    ).strip()
    trigger_action = str(_first_non_empty(sem.get("trigger_action")) or "").strip()
    chain_summary = str(
        _first_non_empty(
            sem.get("chain_summary"),
            ui_scene.get("chain_summary"),
            reg.get("chain_summary"),
            rule.get("chain_summary"),
            llm.get("chain_summary"),
            final.get("chain_summary"),
        )
        or ""
    ).strip()

    ui_task_scene = str(
        _first_non_empty(
            ui_scene.get("ui_task_scene"),
            ui_scene.get("predicted_scene"),
            reg.get("ui_task_scene"),
            rule.get("ui_task_scene"),
            llm.get("ui_task_scene"),
            final.get("ui_task_scene"),
            rule.get("scene"),
        )
        or ""
    ).strip()
    ui_task_scene_top3 = stringify_list(
        _canonical_scene_top3(ui_scene) or reg.get("ui_task_scene_top3") or rule.get("ui_task_scene_top3")
    )
    regulatory_scene_top1 = str(
        _first_non_empty(
            reg.get("regulatory_scene_top1"),
            rule.get("regulatory_scene_top1"),
            llm.get("regulatory_scene_top1"),
            final.get("regulatory_scene_top1"),
        )
        or ""
    ).strip()
    regulatory_scene_top3 = stringify_list(
        _first_non_empty(
            reg.get("regulatory_scene_top3"),
            rule.get("regulatory_scene_top3"),
            llm.get("regulatory_scene_top3"),
            final.get("regulatory_scene_top3"),
        )
    )

    permissions = stringify_list(
        _first_non_empty(
            perm.get("predicted_permissions"),
            rule.get("permissions"),
            reg.get("permissions"),
            final.get("permissions"),
            llm.get("permissions"),
            _as_dict(sem.get("permission_event")).get("permissions"),
        )
    )
    permission_count = len(split_serialized_list(permissions))
    allowed_permissions = stringify_list(
        _first_non_empty(
            rule.get("allowed_permissions"),
            reg.get("allowed_permissions"),
            llm.get("allowed_permissions"),
            final.get("allowed_permissions"),
        )
    )
    banned_permissions = stringify_list(
        _first_non_empty(
            rule.get("banned_permissions"),
            reg.get("banned_permissions"),
            llm.get("banned_permissions"),
            final.get("banned_permissions"),
        )
    )

    rule_signal = str(
        _first_non_empty(
            rule.get("overall_rule_signal"),
            rule.get("rule_signal"),
            final.get("rule_signal"),
            llm.get("rule_signal"),
        )
        or ""
    ).strip()

    llm_final_decision = str(
        _first_non_empty(llm.get("llm_final_decision"), final.get("llm_final_decision")) or ""
    ).strip()
    llm_final_risk = str(
        _first_non_empty(llm.get("llm_final_risk"), final.get("llm_final_risk")) or ""
    ).strip()
    llm_explanation = str(_first_non_empty(llm.get("llm_explanation")) or "").strip()
    necessity_label = _extract_label(llm, "necessity_analysis")
    necessity_reason = _extract_reason(llm, "necessity_analysis")
    consistency_label = _extract_label(llm, "consistency_analysis")
    consistency_reason = _extract_reason(llm, "consistency_analysis")
    minimality_label = _extract_label(llm, "minimality_analysis")
    minimality_reason = _extract_reason(llm, "minimality_analysis")

    final_decision = str(_first_non_empty(final.get("final_decision")) or "").strip()
    final_risk = str(_first_non_empty(final.get("final_risk")) or "").strip()
    rollback = str(_first_non_empty(final.get("rollback")) or "").strip()
    rollback_reason = str(_first_non_empty(final.get("rollback_reason")) or "").strip()

    pred_rule_binary = map_rule_to_binary(rule_signal)
    pred_llm_binary = map_llm_to_binary(llm_final_decision, llm_final_risk)
    pred_final_binary = map_final_to_binary(
        final_decision,
        final_risk,
        llm_final_decision=llm_final_decision,
        llm_final_risk=llm_final_risk,
    )

    return {
        "app": app_name,
        "chain_id": chain_id,
        "gt_label_raw": gt_label_raw,
        "gt_label_binary": gt_label_binary,
        "task_phrase": task_phrase,
        "intent": intent,
        "page_function": page_function,
        "trigger_action": trigger_action,
        "chain_summary": chain_summary,
        "ui_task_scene": ui_task_scene,
        "ui_task_scene_top3": ui_task_scene_top3,
        "regulatory_scene_top1": regulatory_scene_top1,
        "regulatory_scene_top3": regulatory_scene_top3,
        "permissions": permissions,
        "permission_count": permission_count,
        "rule_signal": rule_signal,
        "allowed_permissions": allowed_permissions,
        "banned_permissions": banned_permissions,
        "necessity_label": necessity_label,
        "necessity_reason": necessity_reason,
        "consistency_label": consistency_label,
        "consistency_reason": consistency_reason,
        "minimality_label": minimality_label,
        "minimality_reason": minimality_reason,
        "llm_final_decision": llm_final_decision,
        "llm_final_risk": llm_final_risk,
        "llm_explanation": llm_explanation,
        "final_decision": final_decision,
        "final_risk": final_risk,
        "rollback": rollback,
        "rollback_reason": rollback_reason,
        "pred_rule_binary": pred_rule_binary,
        "pred_llm_binary": pred_llm_binary,
        "pred_final_binary": pred_final_binary,
    }


def build_rows(processed_root: str, app_prefix: str = "fastbot-") -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    rows: List[Dict[str, Any]] = []
    stats = {
        "apps_total": 0,
        "apps_with_label": 0,
        "chains_total": 0,
        "chains_with_gt": 0,
    }

    app_dirs = iter_app_dirs(processed_root, app_prefix=app_prefix)
    stats["apps_total"] = len(app_dirs)

    for app_dir in app_dirs:
        app_name = os.path.basename(app_dir)
        result_map = map_by_chain_id(load_json(os.path.join(app_dir, "result.json")))
        label_map = map_by_chain_id(load_json(os.path.join(app_dir, "label_judge.json")))
        sem_map = map_by_chain_id(
            _load_first_available_json(
                app_dir,
                "result_semantic_v2.json",
                "result_chain_semantics.json",
            )
        )
        ui_scene_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_ui_task_scene.json")))
        perm_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_permission.json")))
        reg_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_regulatory_scene.json")))
        rule_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_rule_screening.json")))
        llm_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_llm_review.json")))
        final_map = map_by_chain_id(load_json(os.path.join(app_dir, "result_final_decision.json")))

        chain_ids = _collect_chain_ids(
            result_map,
            label_map,
            sem_map,
            ui_scene_map,
            perm_map,
            reg_map,
            rule_map,
            llm_map,
            final_map,
        )
        if label_map:
            stats["apps_with_label"] += 1
        stats["chains_total"] += len(chain_ids)

        for cid in chain_ids:
            row = _build_one_row(
                app_name=app_name,
                chain_id=cid,
                label_item=_as_dict(label_map.get(cid)),
                sem=_as_dict(sem_map.get(cid)),
                ui_scene=_as_dict(ui_scene_map.get(cid)),
                perm=_as_dict(perm_map.get(cid)),
                reg=_as_dict(reg_map.get(cid)),
                rule=_as_dict(rule_map.get(cid)),
                llm=_as_dict(llm_map.get(cid)),
                final=_as_dict(final_map.get(cid)),
            )
            if row.get("gt_label_binary"):
                stats["chains_with_gt"] += 1
            rows.append(row)

    rows.sort(key=lambda x: (str(x.get("app", "")), int(x.get("chain_id", -1))))
    return rows, stats


def write_outputs(processed_root: str, rows: List[Dict[str, Any]], csv_name: str, jsonl_name: str) -> Tuple[str, str]:
    fieldnames = [
        "app",
        "chain_id",
        "gt_label_raw",
        "gt_label_binary",
        "task_phrase",
        "intent",
        "page_function",
        "trigger_action",
        "chain_summary",
        "ui_task_scene",
        "ui_task_scene_top3",
        "regulatory_scene_top1",
        "regulatory_scene_top3",
        "permissions",
        "permission_count",
        "rule_signal",
        "allowed_permissions",
        "banned_permissions",
        "necessity_label",
        "necessity_reason",
        "consistency_label",
        "consistency_reason",
        "minimality_label",
        "minimality_reason",
        "llm_final_decision",
        "llm_final_risk",
        "llm_explanation",
        "final_decision",
        "final_risk",
        "rollback",
        "rollback_reason",
        "pred_rule_binary",
        "pred_llm_binary",
        "pred_final_binary",
    ]
    csv_path = os.path.join(processed_root, csv_name)
    jsonl_path = os.path.join(processed_root, jsonl_name)
    save_csv(csv_path, rows, fieldnames=fieldnames)
    save_jsonl(jsonl_path, rows)
    return csv_path, jsonl_path


def build_and_save(
    processed_root: str,
    app_prefix: str = "fastbot-",
    csv_name: str = DEFAULT_TABLE_CSV,
    jsonl_name: str = DEFAULT_TABLE_JSONL,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], str, str]:
    rows, stats = build_rows(processed_root=processed_root, app_prefix=app_prefix)
    csv_path, jsonl_path = write_outputs(
        processed_root=processed_root,
        rows=rows,
        csv_name=csv_name,
        jsonl_name=jsonl_name,
    )
    return rows, stats, csv_path, jsonl_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unified judgement analysis table for error analysis.")
    parser.add_argument(
        "processed_root",
        nargs="?",
        default=os.path.join("data", "processed"),
        help="processed root directory",
    )
    parser.add_argument(
        "--app-prefix",
        default="fastbot-",
        help="only include app dirs with this prefix",
    )
    parser.add_argument(
        "--csv-name",
        default=DEFAULT_TABLE_CSV,
        help="output CSV filename under processed_root",
    )
    parser.add_argument(
        "--jsonl-name",
        default=DEFAULT_TABLE_JSONL,
        help="output JSONL filename under processed_root",
    )
    args = parser.parse_args()

    processed_root = os.path.abspath(args.processed_root)
    if not os.path.isdir(processed_root):
        raise SystemExit(f"processed_root not found: {processed_root}")

    rows, stats, csv_path, jsonl_path = build_and_save(
        processed_root=processed_root,
        app_prefix=args.app_prefix,
        csv_name=args.csv_name,
        jsonl_name=args.jsonl_name,
    )
    print("\n========== Build Judgement Analysis Table ==========")
    print(f"generated_at    : {datetime.now().isoformat(timespec='seconds')}")
    print(f"apps_total      : {stats['apps_total']}")
    print(f"apps_with_label : {stats['apps_with_label']}")
    print(f"chains_total    : {stats['chains_total']}")
    print(f"chains_with_gt  : {stats['chains_with_gt']}")
    print(f"rows_written    : {len(rows)}")
    print(f"csv             : {csv_path}")
    print(f"jsonl           : {jsonl_path}")
    print("===================================================\n")


if __name__ == "__main__":
    main()
