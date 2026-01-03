# -*- coding: utf-8 -*-
"""
VL UI 权限识别（Rule / LLM / Rule+LLM）
基于 Qwen3-VL-30B-A3B-Instruct + vLLM

输入：
  fastbot-xxx/
    result.json
    chain_{id}.png

输出：
  results_permission_rule_only.json
  results_permission_llm_only.json
  results_permission_rule_llm.json
"""

import os
import sys
import json
import re
import base64
import io
from typing import Dict, Any, List

import requests  # type: ignore
from PIL import Image  # pip install pillow

# ========================= vLLM 配置 =========================

VLLM_URL = "http://localhost:8001/v1/chat/completions"
MODEL_NAME = "Qwen3-VL-30B-A3B"
LLM_TIMEOUT = 120

# ========================= 权限规则表 =========================

BASE_PERMISSION_TABLE = {
    "MI": {
        "存储": ["READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"],
        "文件": ["READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"],
        "照片": ["READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"],
        "位置": ["ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"],
        "定位": ["ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"],
        "相机": ["CAMERA"],
        "拍照": ["CAMERA"],
        "录音": ["RECORD_AUDIO"],
        "麦克风": ["RECORD_AUDIO"],
        "拨打电话": ["CALL_PHONE"],
        "联系人": ["READ_CONTACTS", "WRITE_CONTACTS"],
    }
}

ALL_DANGEROUS_PERMS = sorted({
    p for v in BASE_PERMISSION_TABLE["MI"].values() for p in v
})

# ========================= 工具函数 =========================

def _normalize_text(t: str) -> str:
    return re.sub(r"\s+", "", t.lower()) if t else ""


def _collect_texts_for_rule(ui_item: Dict[str, Any]) -> List[str]:
    texts: List[str] = []

    def _pull(block):
        t = block.get("feature", {}).get("text", "")
        if isinstance(t, list):
            texts.extend([str(x) for x in t if x])
        elif isinstance(t, str) and t:
            texts.append(t)

    _pull(ui_item.get("ui_before_grant", {}))
    for step in ui_item.get("ui_granting", []):
        _pull(step)
    _pull(ui_item.get("ui_after_grant", {}))

    return texts


# ========================= 图像 → base64（vLLM 必须） =========================

def _image_to_base64(path: str, max_side: int = 1024) -> str:
    """
    读取图片，等比缩放（防止 VL OOM），转 base64
    """
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _build_multimodal_message(prompt: str, image_path: str):
    content = [{"type": "text", "text": prompt}]

    if os.path.exists(image_path):
        b64 = _image_to_base64(image_path)
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64}"
            }
        })

    return [{"role": "user", "content": content}]


def _call_vl_llm(prompt: str, image_path: str) -> str:
    messages = _build_multimodal_message(prompt, image_path)
    try:
        resp = requests.post(
            VLLM_URL,
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "temperature": 0,
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[LLM ERROR] {e}")
        return ""


# ========================= LLM 权限判断 =========================

def llm_only_permission(
    full_text: str,
    image_path: str,
    candidate: List[str]
) -> List[str]:

    perm_list = "\n".join(f"- {p}" for p in candidate)

    prompt = f"""
你是一名【安卓系统权限识别专家】。
请结合【UI 截图】判断该界面请求的安卓危险权限。

规则：
1. 这是整条权限请求流程合成后的截图
2. 重点识别系统权限弹窗（包含“允许 / 拒绝”）
3. 常见图标含义：
   - 📁 文件 / 照片 → READ/WRITE_EXTERNAL_STORAGE
   - 📍 位置 → ACCESS_FINE / COARSE_LOCATION
   - 📷 相机 → CAMERA
   - 🎤 麦克风 → RECORD_AUDIO
4. 通常只请求 1~2 个权限，避免过多输出

【候选权限】
{perm_list}

【UI 文本（OCR，仅供参考）】
{full_text}

严格输出 JSON：
{{"permissions": ["PERMISSION_A"]}}
"""

    raw = _call_vl_llm(prompt, image_path)
    try:
        obj = json.loads(raw)
        return [p for p in obj.get("permissions", []) if p in candidate]
    except Exception:
        return []


# ========================= 三种模式 =========================

def rule_only(ui_item: Dict[str, Any], vendor="MI") -> List[str]:
    vendor_table = BASE_PERMISSION_TABLE[vendor]
    texts = [_normalize_text(t) for t in _collect_texts_for_rule(ui_item)]

    hits = []
    for zh, perms in vendor_table.items():
        pat = _normalize_text(zh)
        if any(pat in t for t in texts):
            hits.extend(perms)

    return sorted(set(hits))


def rule_llm(ui_item, image_path, vendor="MI") -> List[str]:
    rule_res = rule_only(ui_item, vendor)
    if rule_res:
        return rule_res

    texts = " ".join(_collect_texts_for_rule(ui_item))
    return llm_only_permission(texts, image_path, ALL_DANGEROUS_PERMS)


# ========================= 主处理 =========================

def process_one_app(app_dir: str, vendor="MI"):
    result_json = os.path.join(app_dir, "result.json")
    if not os.path.exists(result_json):
        return

    with open(result_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    out_rule = []
    out_llm = []
    out_rule_llm = []

    for idx, ui_item in enumerate(data):
        chain_id = ui_item.get("chain_id", idx)
        chain_img = os.path.join(app_dir, f"chain_{chain_id}.png")

        texts = " ".join(_collect_texts_for_rule(ui_item))

        r = rule_only(ui_item, vendor)
        l = llm_only_permission(texts, chain_img, ALL_DANGEROUS_PERMS)
        rl = rule_llm(ui_item, chain_img, vendor)

        out_rule.append({
            "chain_id": chain_id,
            "predicted_permissions": r
        })
        out_llm.append({
            "chain_id": chain_id,
            "predicted_permissions": l
        })
        out_rule_llm.append({
            "chain_id": chain_id,
            "predicted_permissions": rl
        })

        print(
            f"[{os.path.basename(app_dir)} | chain {chain_id}] "
            f"rule={r}  llm={l}  rule+llm={rl}"
        )

    def dump(name, obj):
        with open(os.path.join(app_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)

    dump("results_permission_rule_only.json", out_rule)
    dump("results_permission_llm_only.json", out_llm)
    dump("results_permission_rule_llm.json", out_rule_llm)


def main(root: str, vendor="MI"):
    apps = [
        os.path.join(root, d)
        for d in os.listdir(root)
        if d.startswith("fastbot-") and os.path.isdir(os.path.join(root, d))
    ]

    for app in sorted(apps):
        print(f"\n📱 Processing {os.path.basename(app)}")
        process_one_app(app, vendor)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python permission_vl_rule_llm_full.py <processed_dir> [MI]")
        sys.exit(1)

    root = sys.argv[1]
    vendor = sys.argv[2] if len(sys.argv) > 2 else "MI"
    main(root, vendor)