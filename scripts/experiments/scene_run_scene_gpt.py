# -*- coding: utf-8 -*-
"""
run_scene_gpt_vision_batch.py
GPT-5.1 Vision-only 场景识别（批量 · 抗 503 · 可恢复）
"""

import os
import json
import base64
import time
from typing import Dict, Any, List
from tqdm import tqdm
from openai import OpenAI, OpenAIError

# =========================
# 基础配置
# =========================
BASE_URL = "https://xiaoai.plus/v1"
API_KEY = "sk-mN0nqS4Otdeke5sH1MVWKOW29jlXqYcLOdUazBmQIyfGCymI"          # ← 替换
MODEL_NAME = "gpt-5.1"

MAX_TOKENS = 400
TEMPERATURE = 0

RETRY_TIMES = 3
RETRY_SLEEP = 30  # seconds

# =========================
# 场景列表
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
# Prompt
# =========================
def build_prompt() -> str:
    scene_str = "\n".join(f"- {s}" for s in SCENE_LIST)
    return f"""
你是一名【移动应用界面场景识别专家】。

请你【只根据这张 App 截图的视觉信息】判断：
1. 用户当前的使用意图（intent）
2. 最相关的使用场景

请输出：
- predicted_scene（top1）
- scene_top3
- scene_top5

【候选场景】
{scene_str}

【仅输出 JSON】
""".strip()

# =========================
# 图片 → base64
# =========================
def image_to_data_url(image_path: str) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

# =========================
# GPT 调用（带重试）
# =========================
def call_gpt_with_retry(image_path: str) -> Dict[str, Any]:
    image_data_url = image_to_data_url(image_path)

    for attempt in range(1, RETRY_TIMES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url}
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
            s, e = content.find("{"), content.rfind("}")
            if s != -1 and e != -1:
                return json.loads(content[s:e + 1])
            return {}

        except OpenAIError as e:
            print(f"⚠ GPT 调用失败（attempt {attempt}/{RETRY_TIMES}）：{e}")
            if attempt < RETRY_TIMES:
                print(f"⏳ 等待 {RETRY_SLEEP}s 后重试...")
                time.sleep(RETRY_SLEEP)
            else:
                return {"_error": str(e)}

# =========================
# 处理单个 APK
# =========================
def process_apk_dir(apk_dir: str):
    images = sorted(
        f for f in os.listdir(apk_dir)
        if f.startswith("chain_") and f.endswith(".png")
    )
    if not images:
        return

    out_path = os.path.join(apk_dir, "results_scene_gpt_5.1.json")

    # 断点恢复
    done = {}
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            for r in json.load(f):
                done[r["chain_id"]] = r

    results = list(done.values())

    for img in tqdm(images, desc=f"Vision {os.path.basename(apk_dir)}", ncols=90):
        chain_id = int(img.replace("chain_", "").replace(".png", ""))
        if chain_id in done:
            continue

        image_path = os.path.join(apk_dir, img)
        gpt_res = call_gpt_with_retry(image_path)

        if "_error" in gpt_res:
            print(f"❌ 跳过 chain_{chain_id}.png")
            continue

        results.append({
            "chain_id": chain_id,
            "intent": gpt_res.get("intent", ""),
            "predicted_scene": gpt_res.get("predicted_scene", "其他"),
            "scene_top3": gpt_res.get("scene_top3", []),
            "scene_top5": gpt_res.get("scene_top5", []),
        })

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sorted(results, key=lambda x: x["chain_id"]),
                      f, ensure_ascii=False, indent=2)

    print(f"✔ 完成：{out_path}")

# =========================
# 主入口
# =========================
def run(processed_root: str):
    for d in os.listdir(processed_root):
        apk_dir = os.path.join(processed_root, d)
        if os.path.isdir(apk_dir):
            process_apk_dir(apk_dir)

# =========================
# CLI
# =========================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python run_scene_gpt_vision_batch.py <processed_dir>")
        sys.exit(1)

    run(sys.argv[1])