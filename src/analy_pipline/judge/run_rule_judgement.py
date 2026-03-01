# -*- coding: utf-8 -*-
"""
run_rule_judgement.py

批量规则裁决（16 类场景）
【修正版】确保 permissions 不会丢
"""

import os
import sys
import json
from collections import defaultdict
from typing import Dict, List

# =========================
# 路径配置
# =========================

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from configs import settings
from utils.validators import validate_permission_results, validate_scene_results

DEFAULT_PROCESSED_DIR = settings.DATA_PROCESSED_DIR
DEFAULT_RULE_FILE = settings.SCENE_RULE_FILE

# =========================
# 常量
# =========================

CLEARLY_ALLOWED = "CLEARLY_ALLOWED"
CLEARLY_PROHIBITED = "CLEARLY_PROHIBITED"
NEEDS_REVIEW = "NEEDS_REVIEW"

LOW_RISK = "LOW_RISK"
MEDIUM_RISK = "MEDIUM_RISK"
HIGH_RISK = "HIGH_RISK"

# =========================
# 加载规则
# =========================

def load_scene_rules(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# =========================
# 单权限裁决
# =========================

def judge_permission(scene: str, permission: str, rules: Dict) -> str:
    rule = rules.get(scene)
    if not rule:
        return NEEDS_REVIEW

    if permission in rule.get("clearly_allowed", []):
        return CLEARLY_ALLOWED

    if permission in rule.get("clearly_prohibited", []):
        return CLEARLY_PROHIBITED

    if permission in rule.get("needs_review", []):
        return NEEDS_REVIEW

    return NEEDS_REVIEW

# =========================
# chain 级裁决
# =========================

def judge_chain(scene: str, permissions: List[str], rules: Dict):
    decisions = {}
    score = 0

    for p in permissions:
        d = judge_permission(scene, p, rules)
        decisions[p] = d

        if d == CLEARLY_PROHIBITED:
            score += 2
        elif d == NEEDS_REVIEW:
            score += 1

    if score >= 2:
        overall = HIGH_RISK
    elif score == 1:
        overall = MEDIUM_RISK
    else:
        overall = LOW_RISK

    return decisions, overall

# =========================
# 主流程
# =========================
def run(processed_dir: str, rule_file: str):
    rules = load_scene_rules(rule_file)

    total_chains = 0
    missing_perm_chains = 0

    # 🔢 全局统计
    risk_counter = defaultdict(int)
    permission_decision_counter = defaultdict(int)

    def process_app_dir(apk_dir: str):
        nonlocal total_chains, missing_perm_chains

        scene_path = os.path.join(apk_dir, "results_scene_llm.json")
        if not os.path.exists(scene_path):
            scene_path = os.path.join(apk_dir, "results_scene_vllm.json")
        perm_path = os.path.join(apk_dir, "result_permission_rule.json")
        if not os.path.exists(perm_path):
            perm_path = os.path.join(apk_dir, "result_permission_llm.json")

        if not os.path.exists(scene_path) or not os.path.exists(perm_path):
            return

        try:
            with open(scene_path, "r", encoding="utf-8") as f:
                scenes = validate_scene_results(json.load(f))
            with open(perm_path, "r", encoding="utf-8") as f:
                perms = validate_permission_results(json.load(f))
        except ValueError as exc:
            print(f"[WARN] schema validation failed for {apk_dir}: {exc}")
            return

        scene_map = {x["chain_id"]: x for x in scenes}
        perm_map = {x["chain_id"]: x for x in perms}

        results = []

        for chain_id, scene_item in scene_map.items():
            perm_item = perm_map.get(chain_id)

            if not perm_item:
                missing_perm_chains += 1
                continue

            permissions = (
                perm_item.get("predicted_permissions")
                or perm_item.get("true_permissions")
                or []
            )

            scene = scene_item.get("predicted_scene")
            intent = scene_item.get("intent")

            decisions, overall = judge_chain(scene, permissions, rules)

            # 🔢 统计
            risk_counter[overall] += 1
            for d in decisions.values():
                permission_decision_counter[d] += 1

            results.append({
                "chain_id": chain_id,
                "scene": scene,
                "intent": intent,
                "permissions": permissions,
                "permission_decisions": decisions,
                "overall_rule_signal": overall
            })

            total_chains += 1

        out_path = os.path.join(apk_dir, "result_rule_judgement.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    if os.path.exists(os.path.join(processed_dir, "results_scene_llm.json")):
        process_app_dir(processed_dir)
        print("\n✅ 规则裁决完成（单 APK）")
        return

    apk_dirs = [
        d for d in os.listdir(processed_dir)
        if d.startswith("fastbot-") and
        os.path.isdir(os.path.join(processed_dir, d))
    ]

    print(f"📦 检测到 APK 数量: {len(apk_dirs)}")

    for apk in apk_dirs:
        process_app_dir(os.path.join(processed_dir, apk))

    # =========================
    # 📊 最终统计输出
    # =========================
    print("\n========== 规则裁决统计 ==========")
    print(f"总 chain 数量: {total_chains}")
    print(f"缺失 / 空权限 chain 数: {missing_perm_chains}")

    print("\n【整体风险分布】")
    print(f"  LOW_RISK    : {risk_counter[LOW_RISK]}")
    print(f"  MEDIUM_RISK : {risk_counter[MEDIUM_RISK]}")
    print(f"  HIGH_RISK   : {risk_counter[HIGH_RISK]}")

    print("\n【权限裁决分布】")
    print(f"  CLEARLY_ALLOWED   : {permission_decision_counter[CLEARLY_ALLOWED]}")
    print(f"  NEEDS_REVIEW      : {permission_decision_counter[NEEDS_REVIEW]}")
    print(f"  CLEARLY_PROHIBITED: {permission_decision_counter[CLEARLY_PROHIBITED]}")

    print("\n✅ 批量规则裁决完成")
# =========================
# 入口
# =========================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rule-based judgement")
    parser.add_argument("--processed-dir", default=os.getenv("LLMMUI_PROCESSED_DIR", os.getenv("PROCESSED_DIR", DEFAULT_PROCESSED_DIR)))
    parser.add_argument("--rule-file", default=os.getenv("LLMMUI_SCENE_RULE_FILE", os.getenv("RULE_FILE", DEFAULT_RULE_FILE)))
    args = parser.parse_args()

    run(args.processed_dir, rule_file=args.rule_file)
