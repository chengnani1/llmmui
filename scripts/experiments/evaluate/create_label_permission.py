# -*- coding: utf-8 -*-
"""
Manual permission labeling for permission chains (PNG-based).

Input directory:
  /Users/charon/Downloads/llmui/processed/<app>/
    ├── chain_0.png
    ├── chain_1.png
    ├── ...

Output file (per app):
  permission_labels.json

One chain -> 0..N permissions
"""

import os
import sys
import json
import subprocess
import re
from typing import List
from src.configs.label_config import PERMISSION_CANDIDATES
# =========================================================
# CONFIG
# =========================================================

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


def print_permission_menu():
    print("\n====== Permission Candidates ======")
    for i, p in enumerate(PERMISSION_CANDIDATES, start=1):
        print(f"{i:2d}. {p}")
    print("\nInput examples:")
    print("  1,3,5")
    print("  RECORD_AUDIO,CAMERA")
    print("  <empty>  (no permission)")
    print("  b        (back)")
    print("  q        (quit)\n")


def parse_permissions(user_input: str) -> List[str]:
    user_input = user_input.strip()
    if not user_input:
        return []

    parts = [p.strip() for p in user_input.split(",")]
    results = []

    for p in parts:
        if p.isdigit():
            idx = int(p)
            if 1 <= idx <= len(PERMISSION_CANDIDATES):
                results.append(PERMISSION_CANDIDATES[idx - 1])
        else:
            results.append(p)

    # deduplicate, keep order
    return list(dict.fromkeys(results))

# =========================================================
# Core labeling logic
# =========================================================

def label_one_app(app_dir: str):
    print(f"\n📌 Labeling app: {os.path.basename(app_dir)}")

    chain_imgs = [
        f for f in os.listdir(app_dir)
        if re.match(r"chain_\d+\.png", f)
    ]

    if not chain_imgs:
        print("⚠ No chain_*.png found, skip.")
        return

    chain_imgs.sort(key=parse_chain_id)

    label_path = os.path.join(app_dir, "labels.json")
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
        print_permission_menu()

        user_input = input("Permissions: ").strip()

        if user_input == "q":
            break
        if user_input == "b":
            idx = max(0, idx - 1)
            continue

        perms = parse_permissions(user_input)

        labels.append({
            "chain_id": chain_id,
            "image": img,
            "true_permissions": perms
        })

        json.dump(labels, open(label_path, "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)

        print(f"✅ Saved: {perms}")
        idx += 1

    print(f"\n🎉 Permission labeling done: {label_path}")

# =========================================================
# Main
# =========================================================

def main():
    print("🚀 Permission Chain Labeling Tool")
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