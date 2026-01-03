# -*- coding: utf-8 -*-
"""
run_rule_judgement_batch.py

批量规则裁决（16 类场景）：
- 遍历 processed 下所有 fastbot-* APK
- 对每个 chain 做规则初判
- 输出 result_rule_judgement.json
- 最后打印整体统计
"""

import os
import json
from collections import defaultdict
from typing import Dict, List

# =========================
# 路径配置（按你真实环境）
# =========================

PROCESSED_DIR = "/Users/charon/Downloads/code/llmui/llmmui/data/processed"
RULE_FILE = "configs/scene_permission_rules_16.json"

# =========================
# 常量定义
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

def judge_chain(scene: str, permissions: List[str], rules: Dict) -> Dict:
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

def main():
    rules = load_scene_rules(RULE_FILE)

    # 全局统计
    total_chains = 0
    risk_counter = defaultdict(int)
    permission_counter = defaultdict(int)

    apk_dirs = [
        d for d in os.listdir(PROCESSED_DIR)
        if d.startswith("fastbot-") and
        os.path.isdir(os.path.join(PROCESSED_DIR, d))
    ]

    print(f"📦 检测到 APK 数量: {len(apk_dirs)}\n")

    for apk in apk_dirs:
        apk_dir = os.path.join(PROCESSED_DIR, apk)

        scene_path = os.path.join(apk_dir, "results_scene_llm.json")
        perm_path = os.path.join(apk_dir, "result_permission_rule.json")

        if not os.path.exists(scene_path) or not os.path.exists(perm_path):
            continue

        scenes = json.load(open(scene_path, "r", encoding="utf-8"))
        perms = json.load(open(perm_path, "r", encoding="utf-8"))

        scene_map = {x["chain_id"]: x for x in scenes}
        perm_map = {x["chain_id"]: x for x in perms}

        results = []

        for chain_id, scene_item in scene_map.items():
            perm_item = perm_map.get(chain_id)
            if not perm_item:
                continue

            scene = scene_item.get("predicted_scene")
            permissions = perm_item.get("predicted_permissions", [])

            decisions, overall = judge_chain(scene, permissions, rules)

            results.append({
                "chain_id": chain_id,
                "scene": scene,
                "intent": scene_item.get("intent"),
                "permissions": permissions,
                "permission_decisions": decisions,
                "overall_rule_signal": overall
            })

            # ===== 统计 =====
            total_chains += 1
            risk_counter[overall] += 1
            for d in decisions.values():
                permission_counter[d] += 1

        # 写 APK 内结果
        out_path = os.path.join(apk_dir, "result_rule_judgement.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # =========================
    # 打印统计结果
    # =========================

    print("========== 规则裁决统计 ==========")
    print(f"总 chain 数量: {total_chains}\n")

    print("【整体风险分布】")
    for k in [LOW_RISK, MEDIUM_RISK, HIGH_RISK]:
        print(f"  {k:<12}: {risk_counter[k]}")

    print("\n【权限裁决分布】")
    for k in [CLEARLY_ALLOWED, NEEDS_REVIEW, CLEARLY_PROHIBITED]:
        print(f"  {k:<18}: {permission_counter[k]}")

    print("\n✅ 批量规则裁决完成")

# =========================
# 入口
# =========================

if __name__ == "__main__":
    main()