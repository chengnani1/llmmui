# -*- coding: utf-8 -*-
import json
import os
import sys
from tqdm import tqdm # type: ignore 
from analy.scene_recognizer_v3 import recognize_scene


def process_single_result_json(result_json_path):
    """
    对单个 result.json 执行场景识别
    """
    with open(result_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []

    for ui_item in tqdm(data, desc=f"识别场景[{os.path.basename(os.path.dirname(result_json_path))}]", ncols=90):
        res = recognize_scene(ui_item)

        granting_files = [g["file"] for g in ui_item.get("ui_granting", [])]

        results.append({
            "files": {
                "before": ui_item["ui_before_grant"]["file"],
                "granting": granting_files,
                "after": ui_item["ui_after_grant"]["file"]
            },
            "scene": res
        })

    # 输出路径
    out_path = os.path.join(os.path.dirname(result_json_path), "results_scene.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"✔ 场景识别完成：{out_path}")


def run_batch(processed_root):
    """
    批量遍历 processed_root 下所有 fastbot-* 目录
    """
    if not os.path.isdir(processed_root):
        print("❌ 输入路径不是目录：", processed_root)
        return

    dirs = [
        os.path.join(processed_root, d)
        for d in os.listdir(processed_root)
        if d.startswith("fastbot-")
    ]

    print(f"\n📂 共检测到 {len(dirs)} 个 fastbot-* 目录\n")
    if len(dirs) == 0:
        return

    for d in tqdm(dirs, desc="批量处理目录", ncols=90):
        result_json = os.path.join(d, "result.json")
        if not os.path.exists(result_json):
            print(f"⚠ 未找到 result.json：{result_json}")
            continue

        print(f"\n➡ 正在处理 {result_json}")
        process_single_result_json(result_json)


if __name__ == "__main__":
    """
    用法示例：

    👉 批量处理整个 processed 目录
       python run_scene_recognition.py /path/to/processed/

    👉 只处理某一个 result.json
       python run_scene_recognition.py /path/to/fastbot-xxx/result.json
    """

    if len(sys.argv) < 2:
        print("用法: python run_scene_recognition.py <路径>")
        sys.exit(1)

    target = sys.argv[1]

    if target.endswith("result.json"):
        process_single_result_json(target)
    else:
        run_batch(target)