#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mine judgement error clusters and generate knowledge patch candidates.

Inputs per app dir:
- label_judge.json
- result_final_decision.json
- result_llm_review.json (optional)
- result_semantic_v2.json (optional)
- result_permission.json (optional)
- result_retrieved_knowledge.json (optional)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_TARGET = os.path.join("data", "processed")
DEFAULT_ERROR_JSON = "knowledge_error_cases.json"
DEFAULT_CLUSTER_CSV = "knowledge_error_clusters.csv"
DEFAULT_PATCH_JSON = "knowledge_patch_candidates.json"


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def as_text(v: Any, max_len: int = 400) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def map_by_chain(rows: Any) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for i, raw in enumerate(as_list(rows)):
        item = as_dict(raw)
        if not item:
            continue
        try:
            cid = int(item.get("chain_id", i))
        except Exception:
            continue
        out[cid] = item
    return out


def gt_binary(item: Dict[str, Any]) -> Optional[int]:
    if str(item.get("gt_risk")) in {"0", "1"}:
        return int(item.get("gt_risk"))
    if str(item.get("label")) in {"0", "1"}:
        return int(item.get("label"))
    text = as_text(item.get("gt_label"), 20).upper()
    if text == "RISKY":
        return 1
    if text == "SAFE":
        return 0
    return None


def pred_binary(item: Dict[str, Any], review_as: str) -> Optional[int]:
    decision = as_text(item.get("final_decision"), 40).upper()
    if decision == "CLEARLY_RISKY":
        return 1
    if decision == "CLEARLY_OK":
        return 0
    if decision == "NEED_REVIEW":
        if review_as == "skip":
            return None
        return 1 if review_as == "risk" else 0

    llm_decision = as_text(item.get("llm_final_decision"), 40).upper()
    if llm_decision in {"NON_COMPLIANT", "SUSPICIOUS", "COMPLIANT"}:
        if llm_decision == "NON_COMPLIANT":
            return 1
        if llm_decision == "COMPLIANT":
            return 0
        if review_as == "skip":
            return None
        return 1 if review_as == "risk" else 0

    risk = as_text(item.get("final_risk"), 20).upper()
    if risk == "HIGH":
        return 1
    if risk == "LOW":
        return 0
    if risk == "MEDIUM":
        if review_as == "skip":
            return None
        return 1 if review_as == "risk" else 0
    return None


def split_clauses(text: str) -> List[str]:
    raw = as_text(text, 1200)
    if not raw:
        return []
    parts = re.split(r"[，,。；;、|/\\n]+", raw)
    out: List[str] = []
    for part in parts:
        p = as_text(part, 80)
        if len(p) < 2:
            continue
        out.append(p)
    return out


def dedupe_keep_order(values: Iterable[str], max_items: int = 8) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values:
        key = as_text(v, 80)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= max_items:
            break
    return out


def iter_app_dirs(target: str, app_prefix: str) -> List[str]:
    if os.path.exists(os.path.join(target, "result.json")):
        return [target]
    out: List[str] = []
    if not os.path.isdir(target):
        return out
    for d in sorted(os.listdir(target)):
        app_dir = os.path.join(target, d)
        if not os.path.isdir(app_dir):
            continue
        if app_prefix and not d.startswith(app_prefix):
            continue
        if os.path.exists(os.path.join(app_dir, "label_judge.json")):
            out.append(app_dir)
    return out


def resolve_scene(final_item: Dict[str, Any], llm_item: Dict[str, Any], sem_item: Dict[str, Any]) -> Tuple[str, str]:
    sem_scene = as_dict(sem_item.get("scene"))
    ui = as_text(final_item.get("ui_task_scene"), 80) or as_text(llm_item.get("ui_task_scene"), 80) or as_text(sem_scene.get("ui_task_scene"), 80)
    refined = as_text(final_item.get("refined_scene"), 80) or as_text(llm_item.get("refined_scene"), 80) or as_text(sem_scene.get("refined_scene"), 80)
    return ui, refined or "other"


def resolve_permissions(
    final_item: Dict[str, Any],
    llm_item: Dict[str, Any],
    perm_item: Dict[str, Any],
) -> List[str]:
    out = []
    seen = set()
    for src in [
        as_list(final_item.get("permissions")),
        as_list(llm_item.get("permissions")),
        as_list(perm_item.get("predicted_permissions")),
    ]:
        for p in src:
            perm = as_text(p, 64).upper()
            if not perm or perm in seen:
                continue
            seen.add(perm)
            out.append(perm)
    return out


def resolve_text(final_item: Dict[str, Any], llm_item: Dict[str, Any], sem_item: Dict[str, Any], key: str, max_len: int) -> str:
    return (
        as_text(final_item.get(key), max_len)
        or as_text(llm_item.get(key), max_len)
        or as_text(sem_item.get(key), max_len)
    )


def build_error_records(target: str, app_prefix: str, review_as: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for app_dir in iter_app_dirs(target, app_prefix=app_prefix):
        app_name = os.path.basename(app_dir)
        gt_map = map_by_chain(load_json(os.path.join(app_dir, "label_judge.json")))
        final_map = map_by_chain(load_json(os.path.join(app_dir, "result_final_decision.json")))
        llm_map = map_by_chain(load_json(os.path.join(app_dir, "result_llm_review.json")))
        sem_map = map_by_chain(load_json(os.path.join(app_dir, "result_semantic_v2.json")))
        perm_map = map_by_chain(load_json(os.path.join(app_dir, "result_permission.json")))
        retrieval_map = map_by_chain(load_json(os.path.join(app_dir, "result_retrieved_knowledge.json")))

        chain_ids = sorted(set(gt_map.keys()) | set(final_map.keys()))
        for cid in chain_ids:
            gt_item = gt_map.get(cid)
            final_item = final_map.get(cid, {})
            if not gt_item or not final_item:
                continue
            g = gt_binary(gt_item)
            p = pred_binary(final_item, review_as=review_as)
            if g is None or p is None or g == p:
                continue

            llm_item = llm_map.get(cid, {})
            sem_item = sem_map.get(cid, {})
            perm_item = perm_map.get(cid, {})
            retrieval_item = retrieval_map.get(cid, {})

            ui_scene, refined_scene = resolve_scene(final_item, llm_item, sem_item)
            permissions = resolve_permissions(final_item, llm_item, perm_item)
            page_description = resolve_text(final_item, llm_item, sem_item, "page_description", 1000)
            page_function = resolve_text(final_item, llm_item, sem_item, "page_function", 300)
            user_goal = resolve_text(final_item, llm_item, sem_item, "user_goal", 300)
            err_type = "FP" if (g == 0 and p == 1) else "FN"

            row = {
                "app": app_name,
                "chain_id": cid,
                "error_type": err_type,
                "gt_binary": g,
                "pred_binary": p,
                "ui_task_scene": ui_scene,
                "refined_scene": refined_scene or "other",
                "permissions": permissions,
                "page_description": page_description,
                "page_function": page_function,
                "user_goal": user_goal,
                "llm_final_decision": as_text(llm_item.get("final_decision"), 40),
                "llm_final_risk": as_text(llm_item.get("final_risk"), 20),
                "final_decision": as_text(final_item.get("final_decision"), 40),
                "final_risk": as_text(final_item.get("final_risk"), 20),
                "retrieved_knowledge": as_dict(retrieval_item.get("retrieved_knowledge")),
            }
            rows.append(row)
    return rows


def cluster_errors(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    cluster: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in rows:
        perms = row.get("permissions") or ["<NONE>"]
        for perm in perms:
            key = (row["error_type"], row.get("refined_scene") or "other", perm)
            if key not in cluster:
                cluster[key] = {
                    "error_type": key[0],
                    "scene": key[1],
                    "permission": key[2],
                    "count": 0,
                    "apps": Counter(),
                    "page_function": Counter(),
                    "user_goal": Counter(),
                    "description_clauses": Counter(),
                }
            slot = cluster[key]
            slot["count"] += 1
            slot["apps"][row["app"]] += 1
            pf = as_text(row.get("page_function"), 180)
            ug = as_text(row.get("user_goal"), 180)
            if pf:
                slot["page_function"][pf] += 1
            if ug:
                slot["user_goal"][ug] += 1
            for clause in split_clauses(as_text(row.get("page_description"), 800)):
                slot["description_clauses"][clause] += 1
    return cluster


def top_counter(counter: Counter, top_k: int) -> List[Dict[str, Any]]:
    total = sum(counter.values())
    out: List[Dict[str, Any]] = []
    for key, cnt in counter.most_common(top_k):
        out.append({"key": key, "count": cnt, "ratio": (cnt / total) if total else 0.0})
    return out


def build_candidates(cluster: Dict[Tuple[str, str, str], Dict[str, Any]], min_support: int, top_k_cues: int) -> Dict[str, Any]:
    case_candidates: List[Dict[str, Any]] = []
    pattern_candidates: List[Dict[str, Any]] = []

    for item in sorted(cluster.values(), key=lambda x: x["count"], reverse=True):
        if item["count"] < min_support:
            continue

        err_type = item["error_type"]
        scene = item["scene"]
        permission = item["permission"]
        case_type = "compliant" if err_type == "FP" else "risky"

        cues = dedupe_keep_order(
            [x["key"] for x in top_counter(item["page_function"], top_k_cues)]
            + [x["key"] for x in top_counter(item["user_goal"], top_k_cues)]
            + [x["key"] for x in top_counter(item["description_clauses"], top_k_cues)],
            max_items=8,
        )

        case_candidates.append(
            {
                "scene": scene,
                "permission": permission,
                "case_type": case_type,
                "support_count": item["count"],
                "evidence": cues[:6],
                "reason": f"Derived from {item['count']} {err_type} errors in current run.",
                "source": "error_mining_candidate",
            }
        )

        pos = cues[:6] if err_type == "FP" else []
        neg = cues[:6] if err_type == "FN" else []
        pattern_candidates.append(
            {
                "scene": scene,
                "permission": permission,
                "support_count": item["count"],
                "positive_cues": pos,
                "negative_cues": neg,
                "decision_hint": f"Derived from {item['count']} {err_type} errors in current run.",
                "source": "error_mining_candidate",
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "min_support": min_support,
        "top_k_cues": top_k_cues,
        "scene_case_candidates": case_candidates,
        "scene_pattern_candidates": pattern_candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine knowledge candidates from label_judge mismatch errors")
    parser.add_argument("target", nargs="?", default=DEFAULT_TARGET, help="processed root or one app dir")
    parser.add_argument("--app-prefix", default="fastbot-", help="only include apps with this prefix")
    parser.add_argument("--review-as", choices=["risk", "safe", "skip"], default="risk", help="mapping for NEED_REVIEW")
    parser.add_argument("--min-support", type=int, default=3, help="minimum cluster count to output candidate")
    parser.add_argument("--top-k-cues", type=int, default=4, help="top cues per source counter")
    parser.add_argument("--error-json", default=DEFAULT_ERROR_JSON, help="error records output filename")
    parser.add_argument("--cluster-csv", default=DEFAULT_CLUSTER_CSV, help="cluster summary csv output filename")
    parser.add_argument("--patch-json", default=DEFAULT_PATCH_JSON, help="knowledge candidates output filename")
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    rows = build_error_records(target=target, app_prefix=args.app_prefix, review_as=args.review_as)
    cluster = cluster_errors(rows)
    candidates = build_candidates(cluster, min_support=args.min_support, top_k_cues=args.top_k_cues)

    error_path = os.path.join(target, args.error_json)
    with open(error_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    csv_path = os.path.join(target, args.cluster_csv)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "error_type",
                "scene",
                "permission",
                "count",
                "top_page_function",
                "top_user_goal",
                "top_description_clause",
                "top_apps",
            ],
        )
        writer.writeheader()
        for item in sorted(cluster.values(), key=lambda x: x["count"], reverse=True):
            writer.writerow(
                {
                    "error_type": item["error_type"],
                    "scene": item["scene"],
                    "permission": item["permission"],
                    "count": item["count"],
                    "top_page_function": "; ".join([x["key"] for x in top_counter(item["page_function"], 3)]),
                    "top_user_goal": "; ".join([x["key"] for x in top_counter(item["user_goal"], 3)]),
                    "top_description_clause": "; ".join([x["key"] for x in top_counter(item["description_clauses"], 3)]),
                    "top_apps": "; ".join([x["key"] for x in top_counter(item["apps"], 3)]),
                }
            )

    patch_path = os.path.join(target, args.patch_json)
    with open(patch_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    print(f"errors={len(rows)} clusters={len(cluster)}")
    print(f"error_json={error_path}")
    print(f"cluster_csv={csv_path}")
    print(f"patch_json={patch_path}")


if __name__ == "__main__":
    main()
