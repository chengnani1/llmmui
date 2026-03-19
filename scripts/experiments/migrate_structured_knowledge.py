#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate legacy prior/pattern/case knowledge into structured boundary schema."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Tuple

REFINED_ALIASES = {
    "profile_or_identity_upload": "profile_or_identity_update",
    "wifi_scan_or_nearby_devices": "nearby_service_or_wifi_scan",
}

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

TARGET_PAIRS = {
    ("system_cleanup", "READ_EXTERNAL_STORAGE"),
    ("system_cleanup", "WRITE_EXTERNAL_STORAGE"),
    ("content_browsing", "READ_EXTERNAL_STORAGE"),
    ("content_browsing", "WRITE_EXTERNAL_STORAGE"),
    ("social_chat_or_share", "READ_EXTERNAL_STORAGE"),
    ("social_chat_or_share", "WRITE_EXTERNAL_STORAGE"),
    ("map_navigation", "ACCESS_FINE_LOCATION"),
    ("map_navigation", "ACCESS_COARSE_LOCATION"),
    ("media_capture_or_recording", "CAMERA"),
    ("media_capture_or_recording", "RECORD_AUDIO"),
}

DEFAULT_BOUNDARY = {
    ("system_cleanup", "READ_EXTERNAL_STORAGE"): ["扫描对象", "待清理项列表"],
    ("system_cleanup", "WRITE_EXTERNAL_STORAGE"): ["删除或清理执行入口", "清理结果变化"],
    ("content_browsing", "READ_EXTERNAL_STORAGE"): ["本地文件选择入口"],
    ("content_browsing", "WRITE_EXTERNAL_STORAGE"): ["下载或保存入口"],
    ("social_chat_or_share", "READ_EXTERNAL_STORAGE"): ["媒体附件入口"],
    ("social_chat_or_share", "WRITE_EXTERNAL_STORAGE"): ["保存或下载动作入口"],
    ("map_navigation", "ACCESS_FINE_LOCATION"): ["定位触发入口", "位置更新状态"],
    ("map_navigation", "ACCESS_COARSE_LOCATION"): ["城市级或附近定位任务"],
    ("media_capture_or_recording", "CAMERA"): ["相机采集入口"],
    ("media_capture_or_recording", "RECORD_AUDIO"): ["录音入口或录制状态"],
}


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def as_text(v: Any, max_len: int = 80) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def norm_scene(scene: Any) -> str:
    raw = as_text(scene, 80).strip().lower()
    return REFINED_ALIASES.get(raw, raw)


def dedupe(values: List[Any], max_items: int = 8, max_len: int = 48) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in values:
        v = as_text(x, max_len)
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
        if len(out) >= max_items:
            break
    return out


def iter_prior_rows(prior: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for scene_key, perm_map in prior.items():
        if not isinstance(perm_map, dict):
            continue
        for perm, obj in perm_map.items():
            if not isinstance(obj, dict):
                continue
            rows.append(
                {
                    "scene": norm_scene(scene_key),
                    "permission": as_text(perm, 64).upper(),
                    "positive_cues": as_list(obj.get("positive_cues")),
                    "negative_cues": as_list(obj.get("negative_cues")),
                    "source_type": "prior",
                }
            )
    return rows


def iter_rows(data: Any, key: str, source_type: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    src = data.get(key, []) if isinstance(data, dict) else data
    for item in as_list(src):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "scene": norm_scene(item.get("scene")),
                "permission": as_text(item.get("permission"), 64).upper(),
                "positive_cues": as_list(item.get("positive_cues")),
                "negative_cues": as_list(item.get("negative_cues")),
                "evidence": as_list(item.get("evidence")),
                "source_type": source_type,
            }
        )
    return rows


def build_structured_entry(rule_id: str, scene: str, perm: str, rows: List[Dict[str, Any]], source_type: str) -> Dict[str, Any]:
    pos: List[str] = []
    neg: List[str] = []
    for r in rows:
        pos.extend(as_list(r.get("positive_cues")))
        pos.extend(as_list(r.get("evidence")))
        neg.extend(as_list(r.get("negative_cues")))

    allow_if = dedupe(pos, max_items=8)
    deny_if = dedupe(neg, max_items=8)
    boundary = DEFAULT_BOUNDARY.get((scene, perm), [])

    return {
        "id": rule_id,
        "scene": UI_SCENE_MAP.get(scene, "其他"),
        "refined_scene": scene,
        "permissions": [perm],
        "allow_if": allow_if,
        "deny_if": deny_if,
        "boundary_if_missing": boundary,
        "positive_evidence": allow_if[:4],
        "negative_evidence": deny_if[:4],
        "source_type": source_type,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy knowledge to structured schema")
    parser.add_argument("--prior", default="src/configs/scene_prior_knowledge.json")
    parser.add_argument("--pattern", default="src/configs/scene_pattern_knowledge.json")
    parser.add_argument("--case", dest="case_file", default="src/configs/scene_case_knowledge.json")
    parser.add_argument("--output", default="src/configs/scene_structured_knowledge.migrated.json")
    args = parser.parse_args()

    prior = load_json(args.prior)
    pattern = load_json(args.pattern)
    case_data = load_json(args.case_file)

    rows = []
    rows.extend(iter_prior_rows(prior if isinstance(prior, dict) else {}))
    rows.extend(iter_rows(pattern, "patterns", "pattern"))
    rows.extend(iter_rows(case_data, "cases", "case"))

    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        scene = row.get("scene")
        perm = row.get("permission")
        source_type = row.get("source_type")
        if (scene, perm) not in TARGET_PAIRS:
            continue
        key = (scene, perm, source_type)
        grouped.setdefault(key, []).append(row)

    out_rules: List[Dict[str, Any]] = []
    idx = 1
    for (scene, perm, source_type), items in sorted(grouped.items()):
        out_rules.append(build_structured_entry(f"M{idx:03d}", scene, perm, items, source_type))
        idx += 1

    payload = {"version": "v1_structured_boundary_migrated", "knowledge": out_rules}
    save_json(args.output, payload)
    print(f"migrated_rules={len(out_rules)} output={os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
