# -*- coding: utf-8 -*-
"""
run_scene_vllm.py
vLLM + Qwen3-VL 场景识别（修复 400 错误）
- 使用 vLLM 原生 images 参数
- 强制读取 chain_{chain_id}.png
- 仅输出 top1 / top3 / top5
"""

# =====================================================
# 路径修正
# =====================================================
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# =====================================================
# 配置导入
# =====================================================
from configs.scene_config import (
    SCENE_LIST,
    SCENE_PROMPT,
    MAX_WIDGETS,
    MAX_TEXT_LEN,
    MAX_STEPS,
    MAX_TOTAL_LEN,
)

MODEL_NAME = "Qwen3-VL-8B"
VLLM_URL = "http://localhost:8002/v1/chat/completions"

# =====================================================
# 标准库
# =====================================================
import json
import re
import base64
import requests
from typing import Any, Dict, List, Optional
from tqdm import tqdm

# =====================================================
# 权限 → 场景先验
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
# UI 压缩逻辑（不变）
# =====================================================
def widget_score(w):
    score = 0
    text = (w.get("text") or "").strip()
    if text:
        score += 2
        if len(text) > 4:
            score += 1
    if "permission" in (w.get("resource-id") or "").lower():
        score += 4
    if "Text" in (w.get("class") or "") or "Button" in (w.get("class") or ""):
        score += 2
    return score


def compress_widgets(widgets):
    widgets = sorted(widgets, key=widget_score, reverse=True)[:MAX_WIDGETS]
    return "; ".join(
        (w.get("text") or "").strip()
        for w in widgets
        if (w.get("text") or "").strip()
    )


def compress_step(step):
    f = step.get("feature", {})
    return f"[TEXT]\n{(f.get('text') or '')[:MAX_TEXT_LEN]}\n\n[WIDGETS]\n{compress_widgets(f.get('widgets') or [])}"


def compress_ui_sequence(ui_item, before, granting, after):
    blocks = []
    if before:
        blocks.append("[BEFORE]\n" + compress_step(before))
    if granting:
        blocks.append("[GRANTING]\n" + "\n\n---\n\n".join(compress_step(g) for g in granting[: MAX_STEPS * 2]))
    if after:
        blocks.append("[AFTER]\n" + compress_step(after))
    return "\n\n======\n\n".join(blocks)[:MAX_TOTAL_LEN]

# =====================================================
# 图像 → base64（不带 data:image 前缀）
# =====================================================
def encode_image_base64(image_path: str) -> Optional[str]:
    if not image_path or not os.path.exists(image_path):
        return None
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# =====================================================
# vLLM 正确调用方式（关键修复点）
# =====================================================
def call_vllm_vl(prompt: str, image_path: Optional[str]) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0,
    }

    image_b64 = encode_image_base64(image_path)
    if image_b64:
        payload["images"] = [image_b64]

    r = requests.post(VLLM_URL, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# =====================================================
# JSON 提取
# =====================================================
def extract_json(text: str) -> Dict[str, Any]:
    text = re.sub(r"^```.*?\n", "", text, flags=re.S).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s:e+1]) if s != -1 and e != -1 else {}

# =====================================================
# 场景识别
# =====================================================
def recognize_scene(ui_item: Dict[str, Any], result_json_path: str, idx: int):
    feature = compress_ui_sequence(
        ui_item,
        ui_item.get("ui_before_grant"),
        ui_item.get("ui_granting") or [],
        ui_item.get("ui_after_grant"),
    )

    prompt = SCENE_PROMPT.replace("{FEATURE}", feature)
    prompt = prompt.replace("{SCENE_LIST}", "\n".join(f"- {s}" for s in SCENE_LIST))

    chain_id = ui_item.get("chain_id", idx)
    image_path = os.path.join(os.path.dirname(result_json_path), f"chain_{chain_id}.png")

    try:
        raw = call_vllm_vl(prompt, image_path)
    except Exception as e:
        print(f"[WARN] vLLM 调用失败 chain_id={chain_id}: {e}")
        return {"intent": "失败", "top1": "其他", "top3": ["其他"], "top5": ["其他"]}

    obj = extract_json(raw)
    top1 = obj.get("top1", "其他")
    top3 = [x for x in obj.get("top3", []) if x in SCENE_LIST][:3]
    top5 = [x for x in obj.get("top5", []) if x in SCENE_LIST][:5]

    return {
        "intent": obj.get("intent", ""),
        "top1": top1 if top1 in SCENE_LIST else "其他",
        "top3": top3 or ["其他"],
        "top5": top5 or ["其他"],
    }

# =====================================================
# 批处理
# =====================================================
def process_result_json(path: str):
    data = json.load(open(path, "r", encoding="utf-8"))
    out = []

    for idx, ui_item in enumerate(tqdm(data, desc="VL 场景识别")):
        res = recognize_scene(ui_item, path, idx)
        out.append({
            "chain_id": ui_item.get("chain_id", idx),
            "predicted_scene": res["top1"],
            "scene_top3": res["top3"],
            "scene_top5": res["top5"],
        })

    save_path = os.path.join(os.path.dirname(path), "results_scene_vllm.json")
    json.dump(out, open(save_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✔ 完成：{save_path}")

# =====================================================
# main
# =====================================================
def run(target: str):
    if target.endswith("result.json"):
        process_result_json(target)
    else:
        for d in os.listdir(target):
            p = os.path.join(target, d, "result.json")
            if os.path.exists(p):
                process_result_json(p)

if __name__ == "__main__":
    run(sys.argv[1])