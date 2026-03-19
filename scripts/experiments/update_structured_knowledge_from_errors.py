#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Update structured scene knowledge from error cases (FP/FN driven)."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple


UI_SCENE_MAP = {
    "login_verification": "账号与身份认证",
    "profile_or_identity_update": "账号与身份认证",
    "file_management": "文件与数据管理",
    "file_recovery": "文件与数据管理",
    "system_cleanup": "设备清理与系统优化",
    "album_selection": "相册选择与媒体上传",
    "media_upload": "相册选择与媒体上传",
    "media_capture_or_recording": "图像视频拍摄与扫码",
    "map_navigation": "地图与位置服务",
    "nearby_service_or_wifi_scan": "网络连接与设备管理",
    "content_browsing": "内容浏览与搜索",
    "customer_support": "用户反馈与客服",
    "social_chat_or_share": "社交互动与通信",
    "other": "其他",
}


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def as_text(v: Any, max_len: int = 200) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def split_clauses(text: str) -> List[str]:
    raw = as_text(text, 1200)
    if not raw:
        return []
    segs = re.split(r"[，。；;、,.\n]+", raw)
    out: List[str] = []
    for seg in segs:
        s = as_text(seg, 48)
        if not s:
            continue
        if len(s) < 2:
            continue
        if re.fullmatch(r"[A-Za-z0-9_\-]+", s):
            continue
        out.append(s)
    return out


def dedupe_keep(values: List[str], max_items: int = 16, max_len: int = 48) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in values:
        s = as_text(x, max_len)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def top_keys(counter: Counter, top_k: int) -> List[str]:
    return [k for k, _ in counter.most_common(top_k)]


def collect_clusters(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    cluster: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in rows:
        err = as_text(row.get("error_type"), 8).upper()
        if err not in {"FP", "FN"}:
            continue
        scene = as_text(row.get("refined_scene"), 64).lower() or "other"
        perms = [as_text(p, 64).upper() for p in as_list(row.get("permissions")) if as_text(p, 64)]
        if not perms:
            continue

        cues = []
        pf = as_text(row.get("page_function"), 120)
        ug = as_text(row.get("user_goal"), 120)
        if pf:
            cues.append(pf)
        if ug:
            cues.append(ug)
        cues.extend(split_clauses(as_text(row.get("page_description"), 800)))

        for perm in perms:
            key = (scene, perm, err)
            if key not in cluster:
                cluster[key] = {
                    "scene": scene,
                    "permission": perm,
                    "error_type": err,
                    "count": 0,
                    "cues": Counter(),
                }
            slot = cluster[key]
            slot["count"] += 1
            for c in cues:
                if c:
                    slot["cues"][c] += 1
    return cluster


def build_index(knowledge: List[Dict[str, Any]]) -> Dict[Tuple[str, str], int]:
    idx: Dict[Tuple[str, str], int] = {}
    for i, item in enumerate(knowledge):
        scene = as_text(item.get("refined_scene"), 64).lower()
        perms = [as_text(p, 64).upper() for p in as_list(item.get("permissions")) if as_text(p, 64)]
        for perm in perms:
            idx[(scene, perm)] = i
    return idx


def apply_updates(
    knowledge: List[Dict[str, Any]],
    clusters: Dict[Tuple[str, str, str], Dict[str, Any]],
    min_support: int,
    top_k_cues: int,
    max_field_items: int,
) -> Dict[str, Any]:
    idx = build_index(knowledge)
    updated_rules = 0
    total_field_updates = 0
    details: List[Dict[str, Any]] = []

    for (scene, perm, err), item in sorted(clusters.items(), key=lambda kv: kv[1]["count"], reverse=True):
        support = int(item.get("count", 0) or 0)
        if support < min_support:
            continue

        rule_idx = idx.get((scene, perm))
        if rule_idx is None:
            # create minimal new rule for uncovered pair
            new_id = f"AUTO_{len(knowledge)+1:03d}"
            new_rule = {
                "id": new_id,
                "scene": UI_SCENE_MAP.get(scene, "其他"),
                "refined_scene": scene,
                "permissions": [perm],
                "allow_if": ["业务入口明确"],
                "deny_if": ["业务证据不足"],
                "boundary_if_missing": ["关键业务入口"],
                "positive_evidence": ["页面存在明确功能入口"],
                "negative_evidence": ["仅系统或无关文本"],
                "source_type": "pattern",
                "notes": "auto-created from iteration",
            }
            knowledge.append(new_rule)
            rule_idx = len(knowledge) - 1
            idx[(scene, perm)] = rule_idx

        rule = knowledge[rule_idx]
        cues = top_keys(item["cues"], top_k_cues)
        cues = dedupe_keep(cues, max_items=top_k_cues, max_len=48)
        if not cues:
            continue

        touched_fields: List[str] = []

        if err == "FP":
            # predicted risky but gt safe => strengthen allow-side evidence
            before_allow = list(as_list(rule.get("allow_if")))
            before_pos = list(as_list(rule.get("positive_evidence")))
            rule["allow_if"] = dedupe_keep(before_allow + cues, max_items=max_field_items)
            rule["positive_evidence"] = dedupe_keep(before_pos + cues, max_items=max_field_items)
            if rule["allow_if"] != before_allow:
                touched_fields.append("allow_if")
            if rule["positive_evidence"] != before_pos:
                touched_fields.append("positive_evidence")
        else:
            # FN: predicted safe but gt risky => strengthen deny-side evidence
            before_deny = list(as_list(rule.get("deny_if")))
            before_neg = list(as_list(rule.get("negative_evidence")))
            rule["deny_if"] = dedupe_keep(before_deny + cues, max_items=max_field_items)
            rule["negative_evidence"] = dedupe_keep(before_neg + cues, max_items=max_field_items)
            if rule["deny_if"] != before_deny:
                touched_fields.append("deny_if")
            if rule["negative_evidence"] != before_neg:
                touched_fields.append("negative_evidence")

        if touched_fields:
            updated_rules += 1
            total_field_updates += len(touched_fields)
            details.append(
                {
                    "scene": scene,
                    "permission": perm,
                    "error_type": err,
                    "support_count": support,
                    "rule_id": as_text(rule.get("id"), 48),
                    "touched_fields": touched_fields,
                    "applied_cues": cues,
                }
            )

    return {
        "updated_rules": updated_rules,
        "total_field_updates": total_field_updates,
        "update_details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Update structured knowledge from error cases")
    parser.add_argument("--error-json", required=True)
    parser.add_argument("--knowledge-json", required=True)
    parser.add_argument("--min-support", type=int, default=3)
    parser.add_argument("--top-k-cues", type=int, default=4)
    parser.add_argument("--max-field-items", type=int, default=16)
    parser.add_argument("--summary-json", required=True)
    args = parser.parse_args()

    errors = load_json(args.error_json)
    knowledge_obj = load_json(args.knowledge_json)

    if not isinstance(errors, list):
        raise SystemExit(f"invalid error json: {args.error_json}")
    if not isinstance(knowledge_obj, dict) or not isinstance(knowledge_obj.get("knowledge"), list):
        raise SystemExit(f"invalid structured knowledge json: {args.knowledge_json}")

    knowledge = knowledge_obj.get("knowledge", [])
    clusters = collect_clusters(errors)
    result = apply_updates(
        knowledge=knowledge,
        clusters=clusters,
        min_support=args.min_support,
        top_k_cues=args.top_k_cues,
        max_field_items=args.max_field_items,
    )

    knowledge_obj["knowledge"] = knowledge
    save_json(args.knowledge_json, knowledge_obj)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "error_json": os.path.abspath(args.error_json),
        "knowledge_json": os.path.abspath(args.knowledge_json),
        "min_support": args.min_support,
        "top_k_cues": args.top_k_cues,
        "max_field_items": args.max_field_items,
        "cluster_count": len(clusters),
        **result,
    }
    save_json(args.summary_json, summary)

    print(
        f"clusters={len(clusters)} updated_rules={result['updated_rules']} "
        f"field_updates={result['total_field_updates']} summary={os.path.abspath(args.summary_json)}"
    )


if __name__ == "__main__":
    main()
