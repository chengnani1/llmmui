# -*- coding: utf-8 -*-
import json
import os
import sys
from tqdm import tqdm  # type: ignore

# 调用新的 v4 场景识别逻辑
from src.analy.scene_recognizer import recognize_scene


def process_single_result_json(result_json_path):
    """
    对单个 result.json 执行场景识别（v4 版本）
    """
    with open(result_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []

    for idx, ui_item in enumerate(
        tqdm(
            data,
            desc=f"识别场景[{os.path.basename(os.path.dirname(result_json_path))}]",
            ncols=90,
        )
    ):
        # v4 的结果结构：intent + top1 + top3 + top5 + top7
        res = recognize_scene(ui_item) or {}

        before = ui_item.get("ui_before_grant") or {}
        after = ui_item.get("ui_after_grant") or {}
        granting = ui_item.get("ui_granting", []) or []

        granting_files = [
            g.get("file") for g in granting
            if isinstance(g, dict)
        ]

        chain_id = ui_item.get("chain_id", idx)

        # ============================
        # 追加结果（v4 输出字段）
        # ============================
        results.append(
            {
                "chain_id": chain_id,

                # 文件路径
                "files": {
                    "before": before.get("file"),
                    "granting": granting_files,
                    "after": after.get("file"),
                },

                # intent
                "intent": res.get("intent", ""),

                # top1（预测结果）
                "predicted_scene": res.get("top1", "其他"),

                # top3 / top5 / top7
                "scene_top3": res.get("top3", ["其他"]),
                "scene_top5": res.get("top5", ["其他"]),
                "scene_top7": res.get("top7", ["其他"]),
            }
        )

    # 输出路径
    out_path = os.path.join(os.path.dirname(result_json_path), "results_scene_llm.json")
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
    if len(sys.argv) < 2:
        print("用法: python run_scene_recognition_v4.py <路径>")
        sys.exit(1)

    target = sys.argv[1]

    if target.endswith("result.json"):
        process_single_result_json(target)
    else:
        run_batch(target)