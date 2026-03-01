# -*- coding: utf-8 -*-
"""
run_scene_task14.py
14类任务驱动场景识别（稳定 + 分布统计）
"""

import os
import json
import time
import base64
from io import BytesIO
from typing import Dict, Any, List
from collections import defaultdict
from tqdm import tqdm
from PIL import Image
from openai import OpenAI, OpenAIError

# =========================
# 配置
# =========================
BASE_URL = "https://xiaoai.plus/v1"
API_KEY = "sk-mN0nqS4Otdeke5sH1MVWKOW29jlXqYcLOdUazBmQIyfGCymI"  
MODEL_NAME = "gpt-4o"

MAX_HEIGHT = 1536
MAX_TOKENS = 350
TEMPERATURE = 0

RETRY_TIMES = 3
RETRY_SLEEP = 10
REQUEST_INTERVAL = 1.0

LOW_CONF_TH = 0.6

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# =========================
# 新14类 taxonomy
# =========================
SCENE_LIST = [
    "账号注册或登录",
    "即时通信与社交互动",
    "内容浏览与信息消费",
    "内容发布与创作",
    "拍照或视频录制",
    "文件与存储管理",
    "支付或金融交易",
    "商品购买或服务下单",
    "地图与位置服务",
    "系统工具与设备管理",
    "媒体播放与音视频娱乐",
    "游戏场景",
    "广告或推广页面",
    "其他"
]

# =========================
# 图像预处理（裁剪后半 + resize）
# =========================
def preprocess_image(image_path: str) -> str:
    img = Image.open(image_path)
    w, h = img.size

    # 取后半段
    img = img.crop((0, h // 2, w, h))
    w, h = img.size

    # resize
    if h > MAX_HEIGHT:
        ratio = MAX_HEIGHT / h
        new_w = int(w * ratio)
        img = img.resize((new_w, MAX_HEIGHT))

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

# =========================
# Prompt
# =========================
def build_prompt() -> str:
    scene_str = "\n".join(f"- {s}" for s in SCENE_LIST)

    return f"""
你是一名移动应用界面场景识别专家。

这是一张App截图（已裁剪至关键操作区域）。

如果截图包含系统权限弹窗，
请忽略“请求权限/授权”行为本身，
推断用户原本正在执行的任务。

intent 不得包含“权限”“授权”“请求”等字样。

从下列候选场景中选择最匹配的一项，并给出top3和置信度。

【候选场景】
{scene_str}

仅输出JSON：
{{
  "intent": "...",
  "predicted_scene": "...",
  "scene_top3": ["...", "...", "..."],
  "confidence": 0.0-1.0
}}
不要输出其他内容。
""".strip()

# =========================
# GPT 调用
# =========================
def call_gpt(image_path: str) -> Dict[str, Any]:
    image_data_url = preprocess_image(image_path)
    prompt = build_prompt()

    for attempt in range(RETRY_TIMES):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            )

            content = resp.choices[0].message.content.strip()
            s = content.find("{")
            e = content.rfind("}")
            if s != -1 and e != -1:
                return json.loads(content[s:e+1])
            return {}

        except OpenAIError as e:
            print(f"⚠ GPT失败 {attempt+1}/{RETRY_TIMES}: {e}")
            if attempt < RETRY_TIMES - 1:
                time.sleep(RETRY_SLEEP)
            else:
                return {"_error": str(e)}

# =========================
# 处理单个APK目录
# =========================
def process_apk_dir(apk_dir: str) -> List[Dict[str, Any]]:
    images = sorted(
        f for f in os.listdir(apk_dir)
        if f.startswith("chain_") and f.endswith(".png")
    )
    if not images:
        return []

    out_path = os.path.join(apk_dir, "results_scene_task14.json")

    done = {}
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            for r in json.load(f):
                done[r["chain_id"]] = r

    results = list(done.values())

    for img in tqdm(images, desc=os.path.basename(apk_dir), ncols=90):
        chain_id = int(img.replace("chain_", "").replace(".png", ""))

        if chain_id in done:
            continue

        image_path = os.path.join(apk_dir, img)
        res = call_gpt(image_path)

        if "_error" in res:
            print(f"❌ 跳过 chain_{chain_id}")
            continue

        results.append({
            "chain_id": chain_id,
            "intent": res.get("intent", ""),
            "predicted_scene": res.get("predicted_scene", "其他"),
            "scene_top3": res.get("scene_top3", []),
            "confidence": float(res.get("confidence", 0.0))
        })

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sorted(results, key=lambda x: x["chain_id"]),
                      f, ensure_ascii=False, indent=2)

        time.sleep(REQUEST_INTERVAL)

    return results

# =========================
# 统计分布
# =========================
def summarize(all_results: List[Dict[str, Any]], root: str):
    cnt = defaultdict(int)
    conf_sum = defaultdict(float)
    low_cnt = defaultdict(int)

    for r in all_results:
        scene = r["predicted_scene"]
        c = r["confidence"]
        cnt[scene] += 1
        conf_sum[scene] += c
        if c < LOW_CONF_TH:
            low_cnt[scene] += 1

    summary = []
    total = len(all_results)

    for scene in SCENE_LIST:
        n = cnt.get(scene, 0)
        avg_conf = conf_sum.get(scene, 0)/n if n else 0
        low_ratio = low_cnt.get(scene, 0)/n if n else 0

        summary.append({
            "scene": scene,
            "count": n,
            "ratio": round(n/total, 4) if total else 0,
            "avg_confidence": round(avg_conf, 4),
            "low_conf_ratio": round(low_ratio, 4)
        })

    summary.sort(key=lambda x: -x["count"])

    out_path = os.path.join(root, "scene_task14_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n✔ 分布统计完成: {out_path}")

# =========================
# 批量入口
# =========================
def run(processed_root: str):
    all_results = []

    for d in os.listdir(processed_root):
        apk_dir = os.path.join(processed_root, d)
        if os.path.isdir(apk_dir):
            all_results.extend(process_apk_dir(apk_dir))

    summarize(all_results, processed_root)

# =========================
# CLI
# =========================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python run_scene_task14.py <processed_dir>")
        exit(1)

    run(sys.argv[1])