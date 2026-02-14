# -*- coding: utf-8 -*-
"""
Manual scene labeling for permission chains (PNG-based).

Input directory:
  data/processed/<app>/
    ├── chain_0.png
    ├── chain_1.png
    ├── ...

Output file (per app):
  labels_scene.json

One chain -> exactly ONE scene (from 16-class taxonomy)
"""

import os
import sys
import json
import subprocess
import re

# =========================================================
# CONFIG
# =========================================================

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

ROOT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..",
        "data",
        "processed"
    )
)

# =========================================================
# Utils
# =========================================================

def open_image(path: str):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path])
        elif sys.platform == "win32":
            subprocess.Popen(["start", path], shell=True)
        else:
            print(f"⚠ Unsupported platform: {sys.platform}")
    except Exception as e:
        print("⚠ Failed to open image:", e)


def parse_chain_id(filename: str) -> int:
    m = re.match(r"chain_(\d+)\.png", filename)
    return int(m.group(1)) if m else -1


def print_scene_menu():
    print("\n====== Scene Candidates (16-class) ======")
    for i, s in enumerate(SCENE_LIST, start=1):
        print(f"{i:2d}. {s}")
    print("\nInput examples:")
    print("  3            (choose one by number)")
    print("  音视频内容     (choose by name)")
    print("  b            (back)")
    print("  q            (quit)\n")


def parse_scene(user_input: str) -> str:
    user_input = user_input.strip()
    if not user_input:
        return ""

    if user_input.isdigit():
        idx = int(user_input)
        if 1 <= idx <= len(SCENE_LIST):
            return SCENE_LIST[idx - 1]
    else:
        if user_input in SCENE_LIST:
            return user_input

    return ""

# =========================================================
# Core labeling logic
# =========================================================

def label_one_app(app_dir: str):
    print(f"\n📌 Scene labeling app: {os.path.basename(app_dir)}")

    chain_imgs = [
        f for f in os.listdir(app_dir)
        if re.match(r"chain_\d+\.png", f)
    ]

    if not chain_imgs:
        print("⚠ No chain_*.png found, skip.")
        return

    chain_imgs.sort(key=parse_chain_id)

    label_path = os.path.join(app_dir, "labels_scene.json")
    if os.path.exists(label_path):
        labels = json.load(open(label_path, "r", encoding="utf-8"))
    else:
        labels = []

    labeled_ids = {item["chain_id"] for item in labels}

    idx = 0
    while idx < len(chain_imgs):
        img = chain_imgs[idx]
        chain_id = parse_chain_id(img)

        if chain_id in labeled_ids:
            idx += 1
            continue

        img_path = os.path.join(app_dir, img)
        open_image(img_path)

        print(f"\n🔗 Chain {chain_id} ({idx + 1}/{len(chain_imgs)})")
        print_scene_menu()

        user_input = input("Scene: ").strip()

        if user_input == "q":
            break
        if user_input == "b":
            idx = max(0, idx - 1)
            continue

        scene = parse_scene(user_input)
        if not scene:
            print("❌ Invalid input, please select ONE valid scene.")
            continue

        labels.append({
            "chain_id": chain_id,
            "image": img,
            "true_scene": scene
        })

        json.dump(
            labels,
            open(label_path, "w", encoding="utf-8"),
            indent=2,
            ensure_ascii=False
        )

        print(f"✅ Saved scene: {scene}")
        idx += 1

    print(f"\n🎉 Scene labeling done: {label_path}")

# =========================================================
# Main
# =========================================================

def main():
    print("🚀 Scene Chain Labeling Tool (16-class)")
    print("📂 ROOT =", ROOT_DIR)

    if not os.path.isdir(ROOT_DIR):
        print("❌ ROOT_DIR not found")
        return

    for d in sorted(os.listdir(ROOT_DIR)):
        app_dir = os.path.join(ROOT_DIR, d)
        if not os.path.isdir(app_dir):
            continue
        if not d.startswith("fastbot-"):
            continue

        label_one_app(app_dir)

    print("\n✅ ALL APPS DONE")

if __name__ == "__main__":
    main()