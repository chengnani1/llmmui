# -*- coding: utf-8 -*-
"""
run_scene.py
16 类场景识别主入口（LLM + 权限先验）
"""

# =====================================================
# 路径修正（保证可以 import configs.scene_config）
# =====================================================
import os
import sys

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../")
)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# =====================================================
# 统一配置导入
# =====================================================
from configs.scene_config import (
    SCENE_LIST,
    SCENE_PROMPT,
    MAX_WIDGETS,
    MAX_TEXT_LEN,
    MAX_STEPS,
    MAX_TOTAL_LEN,
    MODEL_NAME,
    VLLM_URL,
)

# =====================================================
# 标准库 & 第三方
# =====================================================
import json
import re
import requests
from typing import Any, Dict, List
from tqdm import tqdm  # type: ignore

# =====================================================
# 权限 → 场景先验（16 类）
# =====================================================
PERMISSION_SCENE_PRIORS = {
    "READ_EXTERNAL_STORAGE": "文件与存储",
    "WRITE_EXTERNAL_STORAGE": "文件与存储",
    "READ_MEDIA_IMAGES": "文件与存储",
    "READ_MEDIA_VIDEO": "文件与存储",
    "CAMERA": "拍摄与相册",
    "ACCESS_FINE_LOCATION": "地图与出行",
    "ACCESS_COARSE_LOCATION": "地图与出行",
    "RECORD_AUDIO": "设备与硬件",
}

# =====================================================
# UI 压缩逻辑
# =====================================================
def widget_score(w: Dict[str, Any]) -> int:
    score = 0
    text = (w.get("text") or "").strip()
    cls = w.get("class") or ""
    rid = w.get("resource-id") or ""

    if text:
        score += 2
        if len(text) > 4:
            score += 1
    if "permission" in rid.lower():
        score += 4
    if "Text" in cls or "Button" in cls:
        score += 2
    return score


def compress_widgets(widgets: List[Dict[str, Any]]) -> str:
    if not widgets:
        return ""
    widgets = sorted(widgets, key=widget_score, reverse=True)[:MAX_WIDGETS]
    texts = [
        (w.get("text") or "").strip()
        for w in widgets
        if (w.get("text") or "").strip()
    ]
    return "; ".join(texts)


def compress_step(step: Dict[str, Any]) -> str:
    f = step.get("feature", {})
    text = (f.get("text") or "")[:MAX_TEXT_LEN]
    widgets = compress_widgets(f.get("widgets") or [])
    return f"[TEXT]\n{text}\n\n[WIDGETS]\n{widgets}"


def compress_ui_sequence(ui_item, before, granting, after) -> str:
    blocks = []
    meta = []

    pkg = ui_item.get("package") or ui_item.get("pkg")
    if pkg:
        meta.append(f"APP package: {pkg}")

    perms = ui_item.get("predicted_permissions") or ui_item.get("true_permissions") or []
    if perms:
        meta.append("Requested permissions: " + ", ".join(perms))
        hints = {
            PERMISSION_SCENE_PRIORS[p]
            for p in perms
            if p in PERMISSION_SCENE_PRIORS
        }
        if hints:
            meta.append("Likely scenes based on permissions: " + ", ".join(hints))

    if meta:
        blocks.append("[META]\n" + "\n".join(meta))

    if before:
        blocks.append("[BEFORE]\n" + compress_step(before))

    granting = granting[: MAX_STEPS * 2]
    if granting:
        blocks.append(
            "[GRANTING]\n"
            + "\n\n---\n\n".join(compress_step(g) for g in granting)
        )

    if after:
        blocks.append("[AFTER]\n" + compress_step(after))

    out = "\n\n======\n\n".join(blocks)
    return out[:MAX_TOTAL_LEN]

# =====================================================
# LLM 调用
# =====================================================
def call_llm(feature: str) -> str:
    scene_list_str = "\n".join(f"- {s}" for s in SCENE_LIST)

    # 不使用 format，手动替换占位符
    prompt = SCENE_PROMPT
    prompt = prompt.replace("{FEATURE}", feature)
    prompt = prompt.replace("{SCENE_LIST}", scene_list_str)

    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }

    r = requests.post(VLLM_URL, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}

    text = re.sub(r"^```.*?\n", "", text, flags=re.S).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s:e+1])
            except Exception:
                pass
    return {}

# =====================================================
# 场景识别核心
# =====================================================
def recognize_scene(ui_item: Dict[str, Any]) -> Dict[str, Any]:
    before = ui_item.get("ui_before_grant")
    granting = ui_item.get("ui_granting", []) or []
    after = ui_item.get("ui_after_grant")

    if not (before or granting or after):
        return {
            "intent": "无法识别",
            "top1": "其他",
            "top3": ["其他"],
            "top5": ["其他"],
            "top7": ["其他"],
        }

    feature = compress_ui_sequence(ui_item, before, granting, after)
    raw = call_llm(feature)
    obj = extract_json(raw)

    intent = obj.get("intent", "未能可靠提取功能意图")
    top1 = obj.get("top1", "其他")
    top3 = obj.get("top3", [])
    top5 = obj.get("top5", [])
    top7 = obj.get("top7", [])

    def clean(lst, fallback):
        out = []
        for x in lst:
            if isinstance(x, str) and x in SCENE_LIST and x not in out:
                out.append(x)
        return out or [fallback]

    top1 = top1 if top1 in SCENE_LIST else "其他"
    top3 = clean(top3, top1)[:3]
    top5 = clean(top5, top1)[:5]
    top7 = clean(top7, top1)[:7]

    # 权限先验补充
    perms = ui_item.get("predicted_permissions") or []
    for p in perms:
        s = PERMISSION_SCENE_PRIORS.get(p)
        if s:
            for lst in (top3, top5, top7):
                if s not in lst:
                    lst.append(s)

    return {
        "intent": intent,
        "top1": top1,
        "top3": top3,
        "top5": top5,
        "top7": top7,
    }

# =====================================================
# 批量处理
# =====================================================
def process_result_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for idx, ui_item in enumerate(
        tqdm(data, desc="场景识别", ncols=90)
    ):
        res = recognize_scene(ui_item)
        results.append({
            "chain_id": ui_item.get("chain_id", idx),
            "intent": res["intent"],
            "predicted_scene": res["top1"],
            "scene_top3": res["top3"],
            "scene_top5": res["top5"],
            "scene_top7": res["top7"],
        })

    out = os.path.join(os.path.dirname(path), "results_scene_llm.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✔ 场景识别完成：{out}")


def run(target: str):
    if target.endswith("result.json"):
        process_result_json(target)
        return

    for d in os.listdir(target):
        if d.startswith("fastbot-"):
            p = os.path.join(target, d, "result.json")
            if os.path.exists(p):
                process_result_json(p)

# =====================================================
# main
# =====================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python run_scene.py <result.json | 目录>")
        sys.exit(1)

    run(sys.argv[1])