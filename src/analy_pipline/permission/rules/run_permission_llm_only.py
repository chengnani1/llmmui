# -*- coding: utf-8 -*-
"""
LLM-only permission recognition (PERMISSION-AWARE VERSION)

Input :
  /Users/charon/Downloads/code/processed/<app>/result.json

Output:
  /Users/charon/Downloads/code/processed/<app>/result_permission_llm.json

LLM is ONLY used for semantic permission reasoning.
NO rule-based final decision.
"""

import os
import json
import requests
from typing import List, Dict, Any

from permission_config import ALL_DANGEROUS_PERMS

# =========================================================
# CONFIG
# =========================================================

ROOT_DIR = "/Users/charon/Downloads/code/processed"

VLLM_URL = "http://localhost:8003/v1/chat/completions"
MODEL_NAME = "Qwen2.5-7B"
TIMEOUT = 40

# =========================================================
# Permission-aware feature extraction
# =========================================================

PERMISSION_RID_KEYS = [
    "permission_group_title",
    "permission_allow",
    "permission_deny",
    "permissioncontroller",
    "miui"
]

ACTION_WORDS = ["允许", "拒绝"]

SCENE_HINT_WORDS = [
    "录制", "音频", "拍摄", "相机", "视频",
    "文件", "保存", "读取", "本地"
]


def extract_permission_dialogs(ui_granting: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dialogs = []

    for step in ui_granting:
        widgets = step.get("feature", {}).get("widgets", [])
        title = None
        actions = []
        app = None

        for w in widgets:
            rid = (w.get("resource-id") or "").lower()
            txt = (w.get("text") or "").strip()

            if "permission_group_title" in rid and txt:
                title = txt

            if any(a in txt for a in ACTION_WORDS):
                actions.append(txt)

            if "permission_applicant" in rid and txt:
                app = txt

        if title:
            dialogs.append({
                "title": title,
                "actions": list(set(actions)),
                "app": app or ""
            })

    return dialogs


def extract_scene_keywords(ui_part: Dict[str, Any], max_k: int = 5) -> List[str]:
    kws = []
    widgets = ui_part.get("feature", {}).get("widgets", [])

    for w in widgets:
        txt = (w.get("text") or "").strip()
        if any(k in txt for k in SCENE_HINT_WORDS):
            kws.append(txt)
        if len(kws) >= max_k:
            break

    return kws


def build_semantic_summary(ui_item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "permission_dialogs": extract_permission_dialogs(
            ui_item.get("ui_granting", [])
        ),
        "before_scene_keywords": extract_scene_keywords(
            ui_item.get("ui_before_grant", {})
        ),
        "after_scene_keywords": extract_scene_keywords(
            ui_item.get("ui_after_grant", {})
        )
    }

# =========================================================
# LLM call
# =========================================================

def call_llm(prompt: str) -> str:
    try:
        resp = requests.post(
            VLLM_URL,
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[LLM ERROR] {e}")
        return ""


def llm_predict_permissions(summary: Dict[str, Any]) -> List[str]:
    cand_text = "\n".join(f"- {p}" for p in ALL_DANGEROUS_PERMS)

    prompt = f"""
你是一名安卓权限分析专家。

下面是一次权限申请链的结构化信息（已去除无关 UI 内容）：

权限弹窗：
{json.dumps(summary["permission_dialogs"], ensure_ascii=False)}

权限前场景关键词：
{summary["before_scene_keywords"]}

权限后场景关键词：
{summary["after_scene_keywords"]}

候选危险权限列表：
{cand_text}

请判断该权限申请最可能涉及的权限。
如果无法确定，请返回空数组。

严格按 JSON 输出：
{{"permissions": ["PERM1", "PERM2"]}}
"""

    raw = call_llm(prompt)

    try:
        obj = json.loads(raw)
        perms = obj.get("permissions", [])
        return [p for p in perms if p in ALL_DANGEROUS_PERMS]
    except Exception:
        return []

# =========================================================
# Process one app
# =========================================================

def process_one_app(app_dir: str):
    print(f"\n📌 LLM-only PROCESS APP: {app_dir}")

    path = os.path.join(app_dir, "result.json")
    if not os.path.exists(path):
        print("  ❌ skip (no result.json)")
        return

    data = json.load(open(path, "r", encoding="utf-8"))
    outputs = []

    for idx, ui_item in enumerate(data):
        chain_id = ui_item.get("chain_id", idx)

        summary = build_semantic_summary(ui_item)
        perms = llm_predict_permissions(summary)

        outputs.append({
            "chain_id": chain_id,
            "predicted_permissions": perms,
            "files": {
                "before": ui_item["ui_before_grant"]["file"],
                "granting": [g["file"] for g in ui_item.get("ui_granting", [])],
                "after": ui_item["ui_after_grant"]["file"]
            }
        })

        print(f"  [LLM] chain {chain_id}: {perms}")

    out_path = os.path.join(app_dir, "result_permission_llm.json")
    json.dump(outputs, open(out_path, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    print(f"  ✅ WRITE DONE: {out_path}")

# =========================================================
# Main
# =========================================================

def main():
    print("🚀 LLM-only Permission Recognition (Permission-aware)")
    print("📂 ROOT_DIR =", ROOT_DIR)

    for d in sorted(os.listdir(ROOT_DIR)):
        app_dir = os.path.join(ROOT_DIR, d)
        if not os.path.isdir(app_dir):
            continue
        process_one_app(app_dir)

    print("\n🎉 ALL DONE")

if __name__ == "__main__":
    main()