# -*- coding: utf-8 -*-
"""
count_llm_analy.py

统计 LLM 合规分析结果整体情况
"""

import os
import json
from collections import defaultdict

# =========================================================
# 路径配置
# =========================================================

PROCESSED_DIR = "/Users/charon/Downloads/code/llmui/llmmui/data/processed"

# =========================================================
# 主统计逻辑
# =========================================================

def main():
    total_chains = 0

    # LLM 输出统计
    compliance_counter = defaultdict(int)
    risk_counter = defaultdict(int)

    # 规则 × LLM 对齐统计
    rule_vs_llm = defaultdict(lambda: defaultdict(int))

    apk_dirs = [
        os.path.join(PROCESSED_DIR, d)
        for d in os.listdir(PROCESSED_DIR)
        if d.startswith("fastbot-")
    ]

    analyzed_apks = 0

    for apk_dir in apk_dirs:
        llm_path = os.path.join(apk_dir, "result_llm_compliance.json")
        if not os.path.exists(llm_path):
            continue

        analyzed_apks += 1
        data = json.load(open(llm_path, "r", encoding="utf-8"))

        for item in data:
            total_chains += 1

            rule_signal = item.get("rule_signal", "UNKNOWN")
            llm_res = item.get("llm_compliance", {})

            compliance = llm_res.get("compliance_result", "UNKNOWN")
            risk = llm_res.get("risk_level", "UNKNOWN")

            compliance_counter[compliance] += 1
            risk_counter[risk] += 1

            rule_vs_llm[rule_signal][compliance] += 1

    # =====================================================
    # 打印统计结果
    # =====================================================

    print("\n========== LLM 合规分析统计 ==========")
    print(f"分析 APK 数量      : {analyzed_apks}")
    print(f"分析 chain 数量    : {total_chains}")
    print("------------------------------------")

    print("\n【合规结论分布】")
    for k, v in compliance_counter.items():
        print(f"  {k:15s}: {v}")

    print("\n【LLM 风险等级分布】")
    for k, v in risk_counter.items():
        print(f"  {k:15s}: {v}")

    print("\n【规则裁决 vs LLM 合规结论】")
    for rule, stats in rule_vs_llm.items():
        print(f"\n  ▶ 规则信号: {rule}")
        for comp, cnt in stats.items():
            print(f"     {comp:15s}: {cnt}")

    print("\n=====================================")


# =========================================================
# main
# =========================================================

if __name__ == "__main__":
    main()