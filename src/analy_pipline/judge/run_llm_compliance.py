# -*- coding: utf-8 -*-
"""
run_llm_compliance_v3.py

【强约束版】
三段式 LLM 合规分析：
1. 权限必要性分析（仅限已申请权限）
2. 场景-权限一致性分析（禁止脑补权限）
3. 最终合规裁决（允许纠偏规则）
"""

import os
import json
import requests
from typing import Dict, List
from tqdm import tqdm

# =========================================================
# 路径配置（写死，避免歧义）
# =========================================================

PROCESSED_DIR = "/Users/charon/Downloads/code/llmui/llmmui/data/processed"
PROMPT_DIR = "/Users/charon/Downloads/code/llmui/llmmui/src/configs/prompt"

PROMPT_NECESSITY = os.path.join(PROMPT_DIR, "permission_necessity.txt")
PROMPT_CONSISTENCY = os.path.join(PROMPT_DIR, "scene_consistency.txt")
PROMPT_FINAL = os.path.join(PROMPT_DIR, "finaly_analy.txt")

# LLM 配置
VLLM_URL = "http://localhost:8003/v1/chat/completions"
MODEL_NAME = "Qwen2.5-7B"

TARGET_RISK = {"HIGH_RISK", "MEDIUM_RISK"}

# =========================================================
# 工具函数
# =========================================================

def load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def safe_json_load(text: str) -> Dict:
    """
    尽最大可能从 LLM 输出中解析 JSON
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").replace("json", "").strip()

    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e != -1:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                pass

    return {"_parse_error": text}


def call_llm(prompt: str) -> Dict:
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0
    }
    try:
        r = requests.post(VLLM_URL, json=payload, timeout=90)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return safe_json_load(content)
    except Exception as e:
        return {"_error": f"LLM call failed: {e}"}


def fill_prompt(template: str, **kwargs) -> str:
    """
    严格填充 prompt，占位符只做字符串替换
    """
    prompt = template
    for k, v in kwargs.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False, indent=2)
        prompt = prompt.replace(f"{{{k}}}", str(v))
    return prompt


def detect_permission_hallucination(
    original_perms: List[str],
    analysis: Dict
) -> List[str]:
    """
    检测 LLM 是否分析了未申请的权限
    """
    hallucinated = []

    per_list = analysis.get("per_permission", [])
    for item in per_list:
        p = item.get("permission")
        if p and p not in original_perms:
            hallucinated.append(p)

    return hallucinated

# =========================================================
# 三段式分析（单 chain）
# =========================================================

def analyze_chain(chain: Dict, prompts: Dict) -> Dict:
    scene = chain.get("scene")
    intent = chain.get("intent")
    permissions = chain.get("permissions", [])
    rule_signal = chain.get("overall_rule_signal")

    # ===============================
    # Stage 1: 权限必要性分析
    # ===============================
    p1 = fill_prompt(
        prompts["necessity"],
        scene=scene,
        intent=intent,
        permissions=permissions
    )
    necessity_res = call_llm(p1)

    hallucinated_1 = detect_permission_hallucination(
        permissions,
        necessity_res
    )

    # ===============================
    # Stage 2: 场景一致性分析
    # ===============================
    p2 = fill_prompt(
        prompts["consistency"],
        scene=scene,
        intent=intent,
        permissions=permissions
    )
    consistency_res = call_llm(p2)

    # ===============================
    # Stage 3: 最终合规裁决
    # ===============================
    p3 = fill_prompt(
        prompts["final"],
        scene=scene,
        intent=intent,
        permissions=permissions,
        rule_signal=rule_signal,
        necessity_json=necessity_res,
        consistency_json=consistency_res
    )
    final_res = call_llm(p3)

    return {
        "chain_id": chain.get("chain_id"),
        "scene": scene,
        "intent": intent,
        "permissions": permissions,
        "rule_signal": rule_signal,

        "necessity_analysis": necessity_res,
        "consistency_analysis": consistency_res,
        "final_compliance": final_res,

        # 🔴 关键质量控制字段
        "llm_permission_hallucination": {
            "necessity_stage": hallucinated_1
        }
    }

# =========================================================
# 主流程（批量）
# =========================================================

def main():
    prompts = {
        "necessity": load_prompt(PROMPT_NECESSITY),
        "consistency": load_prompt(PROMPT_CONSISTENCY),
        "final": load_prompt(PROMPT_FINAL),
    }

    apk_dirs = [
        os.path.join(PROCESSED_DIR, d)
        for d in os.listdir(PROCESSED_DIR)
        if d.startswith("fastbot-")
    ]

    total_chains = 0
    analyzed_apks = 0

    for apk_dir in tqdm(apk_dirs, desc="LLM 合规分析（强约束）"):
        rule_path = os.path.join(apk_dir, "result_rule_judgement.json")
        if not os.path.exists(rule_path):
            continue

        chains = json.load(open(rule_path, "r", encoding="utf-8"))
        results = []

        for chain in chains:
            if chain.get("overall_rule_signal") not in TARGET_RISK:
                continue

            res = analyze_chain(chain, prompts)
            results.append(res)
            total_chains += 1

        if results:
            out_path = os.path.join(apk_dir, "result_llm_compliance_v3.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            analyzed_apks += 1

    print("\n========== LLM 合规分析完成（强约束版） ==========")
    print(f"处理 APK 数量: {analyzed_apks}")
    print(f"分析 chain 数量: {total_chains}")
    print("=================================================")

# =========================================================
# 入口
# =========================================================

if __name__ == "__main__":
    main()