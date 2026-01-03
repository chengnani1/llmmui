# -*- coding: utf-8 -*-
"""
run_permission_compliance.py

基于：
- LLM 场景识别结果
- 实际请求权限
- 法规黑白名单

进行权限合规判定
"""

import os
import json
from typing import Dict, List

# ============================================================
# 写死路径（按你当前工程）
# ============================================================
PROJECT_ROOT = "/Users/charon/Downloads/code/llmui/llmmui"
PROCESSED_ROOT = os.path.join(PROJECT_ROOT, "data/processed")

RULE_PATH = os.path.join(
    PROJECT_ROOT,
    "src/configs/permission_map.json"
)

SCENE_RESULT_FILE = "results_scene_llm.json"
RAW_RESULT_FILE = "result.json"
OUTPUT_FILE = "results_permission_compliance.json"

# ============================================================
# 加载规则
# ============================================================
with open(RULE_PATH, "r", encoding="utf-8") as f:
    RULES = json.load(f)

ALLOWED_MAP = RULES.get("allowed_map", {})
BANNED_MAP = RULES.get("banned_map", {})

# ============================================================
# 判定函数（核心）
# ============================================================
def judge_permission(scene: str, permission: str) -> Dict:
    """
    返回单个权限的合规判定结果
    """
    if permission in BANNED_MAP.get(scene, []):
        return {
            "permission": permission,
            "decision": "VIOLATION",
            "rule_source": "banned_map"
        }

    if permission in ALLOWED_MAP.get(scene, []):
        return {
            "permission": permission,
            "decision": "ALLOWED",
            "rule_source": "allowed_map"
        }

    return {
        "permission": permission,
        "decision": "GREY",
        "rule_source": "unspecified"
    }

# ============================================================
# 单个 APP 处理
# ============================================================
def process_single_app(app_dir: str):
    scene_path = os.path.join(app_dir, SCENE_RESULT_FILE)
    raw_path = os.path.join(app_dir, RAW_RESULT_FILE)

    if not os.path.exists(scene_path) or not os.path.exists(raw_path):
        return None

    scene_results = json.load(open(scene_path, "r", encoding="utf-8"))
    raw_results = json.load(open(raw_path, "r", encoding="utf-8"))

    raw_map = {
        item.get("chain_id"): item
        for item in raw_results
    }

    outputs = []

    for scene_item in scene_results:
        chain_id = scene_item.get("chain_id")
        scene = scene_item.get("predicted_scene")
        intent = scene_item.get("intent", "")

        raw_item = raw_map.get(chain_id, {})
        permissions = raw_item.get("predicted_permissions") \
            or raw_item.get("true_permissions") \
            or []

        permission_results = [
            judge_permission(scene, p)
            for p in permissions
        ]

        # 整体判定
        decisions = {p["decision"] for p in permission_results}
        if "VIOLATION" in decisions:
            overall = "VIOLATION"
        elif "GREY" in decisions:
            overall = "GREY"
        else:
            overall = "ALLOWED"

        outputs.append({
            "chain_id": chain_id,
            "scene": scene,
            "intent": intent,
            "permissions": permission_results,
            "overall_decision": overall
        })

    out_path = os.path.join(app_dir, OUTPUT_FILE)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=2, ensure_ascii=False)

    print(f"✔ 合规分析完成: {out_path}")

# ============================================================
# 批量处理
# ============================================================
def run_all():
    app_dirs = [
        os.path.join(PROCESSED_ROOT, d)
        for d in os.listdir(PROCESSED_ROOT)
        if d.startswith("fastbot-")
    ]

    for app_dir in app_dirs:
        process_single_app(app_dir)

    print("\n🎉 所有 APP 合规分析完成")

# ============================================================
# main
# ============================================================
if __name__ == "__main__":
    run_all()