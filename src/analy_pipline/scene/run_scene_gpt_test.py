# -*- coding: utf-8 -*-
"""
run_scene_gpt_vision_single.py
GPT-5.1 Vision-only 场景识别（使用 base64 本地图片）
"""

import os
import sys
import json
import base64
from typing import Dict, Any
from openai import OpenAI

# =========================
# 基础配置
# =========================
BASE_URL = "https://xiaoai.plus/v1"
API_KEY = "sk-xxx"        # ← 替换为你的 key
MODEL_NAME = "gpt-5.1"

MAX_TOKENS = 400
TEMPERATURE = 0

# =========================
# 场景列表（16 类）
# =========================
SCENE_LIST = [
    "地图与出行",
    "即时通信",
    "音视频内容",
    "拍摄与相册",
    "文件与存储",
    "账号与登录",
    "支付与金融",
    "电商与消费",
    "信息浏览",
    "游戏娱乐",
    "医疗健康",
    "工具与系统",
    "个人信息",
    "设备与硬件",
    "学习教育",
    "其他"
]

# =========================
# OpenAI Client
# =========================
client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY
)

# =========================
# Prompt（Vision-only）
# =========================
def build_prompt() -> str:
    scene_str = "\n".join(f"- {s}" for s in SCENE_LIST)
    return f"""
你是一名【移动应用界面场景识别专家】。

请你【只根据这张 App 截图的视觉信息】判断：

1. 用户当前的使用意图（intent，用一句话描述）
2. 从下面 16 个场景中选择最相关的场景
3. 给出：
   - predicted_scene（top1）
   - scene_top3
   - scene_top5

【候选场景】
{scene_str}

【输出要求】
- 仅输出 JSON
- 不要任何额外说明
- JSON 结构如下：

{{
  "intent": "...",
  "predicted_scene": "...",
  "scene_top3": [...],
  "scene_top5": [...]
}}
""".strip()

# =========================
# 工具：本地图片 → base64 data URL
# =========================
def image_to_data_url(image_path: str) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

# =========================
# GPT Vision 调用
# =========================
def call_gpt_with_image(image_path: str) -> Dict[str, Any]:
    image_data_url = image_to_data_url(image_path)

    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    },
                    {
                        "type": "text",
                        "text": build_prompt()
                    }
                ]
            }
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS
    )

    content = resp.choices[0].message.content

    try:
        return json.loads(content)
    except Exception:
        s, e = content.find("{"), content.rfind("}")
        if s != -1 and e != -1:
            return json.loads(content[s:e + 1])
        raise RuntimeError("GPT 输出无法解析为 JSON")

# =========================
# 主逻辑：单 APK · 单 chain
# =========================
def run_single_apk(apk_dir: str, chain_id: int):
    image_path = os.path.join(apk_dir, f"chain_{chain_id}.png")

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"未找到截图：{image_path}")

    print(f"▶ APK: {apk_dir}")
    print(f"▶ chain_id: {chain_id}")
    print(f"▶ image: {image_path}")

    gpt_res = call_gpt_with_image(image_path)

    result = {
        "chain_id": chain_id,
        "intent": gpt_res.get("intent", ""),
        "predicted_scene": gpt_res.get("predicted_scene", "其他"),
        "scene_top3": gpt_res.get("scene_top3", []),
        "scene_top5": gpt_res.get("scene_top5", []),
    }

    out_path = os.path.join(apk_dir, "result_scene_gpt_5.1_single.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([result], f, ensure_ascii=False, indent=2)

    print(f"✔ 单条 Vision-only 结果已输出：{out_path}")

# =========================
# CLI
# =========================
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python run_scene_gpt_vision_single.py <apk_dir> <chain_id>")
        sys.exit(1)

    run_single_apk(sys.argv[1], int(sys.argv[2]))