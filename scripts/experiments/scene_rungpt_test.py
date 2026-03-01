# -*- coding: utf-8 -*-
"""
test_scene_api_debug_fixed.py
固定路径版本 · 逐级排查 503 问题
"""

import base64
from openai import OpenAI
from PIL import Image
import traceback

# =========================
# 固定配置（自己改这里）
# =========================
BASE_URL = "https://xiaoai.plus/v1"
API_KEY = "sk-mN0nqS4Otdeke5sH1MVWKOW29jlXqYcLOdUazBmQIyfGCymI"    
MODEL_NAME = "gpt-4o"   # ⚠️ 先用 gpt-4o 测试，不要用 gpt-5.1

IMAGE_PATH = "/Users/charon/Downloads/code/llmmui/data/processed-214/fastbot-com.yinhe.music.yhmusic--running-minutes-20/chain_1.png"


client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


# =============================
# Step 1: 测试模型列表
# =============================
def test_model_list():
    print("\n=== 测试 1: 获取模型列表 ===")
    try:
        models = client.models.list()
        print("✔ 模型列表成功:")
        for m in models.data:
            print(" -", m.id)
    except Exception as e:
        print("❌ 模型列表失败:")
        traceback.print_exc()


# =============================
# Step 2: 纯文本测试
# =============================
def test_text():
    print("\n=== 测试 2: 纯文本测试 ===")
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": "请回答：1+1等于多少？"}],
            temperature=0,
        )
        print("✔ 文本成功:")
        print(resp.choices[0].message.content)
    except Exception:
        print("❌ 文本调用失败:")
        traceback.print_exc()


# =============================
# Step 3: 小图 Vision 测试
# =============================
def test_small_image():
    print("\n=== 测试 3: 小图 Vision 测试 ===")

    try:
        img = Image.open(IMAGE_PATH)
    except Exception:
        print("❌ 图片路径错误:")
        traceback.print_exc()
        return

    # 强制缩小图片到 512px 高度
    w, h = img.size
    ratio = 512 / h
    new_w = int(w * ratio)
    img = img.resize((new_w, 512))

    tmp = "tmp_test_small.png"
    img.save(tmp)

    with open(tmp, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}"
                            },
                        },
                        {
                            "type": "text",
                            "text": "请简要描述这张图片的内容。"
                        }
                    ]
                }
            ]
        )

        print("✔ Vision 成功:")
        print(resp.choices[0].message.content)

    except Exception:
        print("❌ Vision 调用失败:")
        traceback.print_exc()


# =============================
# 主入口
# =============================
if __name__ == "__main__":
    test_model_list()
    test_text()
    test_small_image()