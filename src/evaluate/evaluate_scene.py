# -*- coding: utf-8 -*-
"""
evaluate_scene_v5_fixed.py

16 类场景识别评测脚本（路径写死版）
- top1 / top3 / top5 / top7 accuracy
- macro-F1（基于 top1）
- 按 chain_id 严格对齐
"""

import os
import json
from collections import defaultdict
from tqdm import tqdm

# ============================================================
#  写死的数据根目录（只改这里即可）
# ============================================================
PROCESSED_ROOT = "/Users/charon/Downloads/code/llmui/llmmui/data/processed"

PRED_FILENAME = "results_scene_gpt_5.1.json"
LABEL_FILENAME = "labels_scene.json"

OUTFILENAME = "evaluation_scene_gpt_5.1.json"

# ============================================================
#  评估单个 APP
# ============================================================
def evaluate_single_app(app_dir):
    pred_path = os.path.join(app_dir, PRED_FILENAME)
    label_path = os.path.join(app_dir, LABEL_FILENAME)

    if not os.path.exists(pred_path) or not os.path.exists(label_path):
        return None

    preds = json.load(open(pred_path, "r", encoding="utf-8"))
    labels = json.load(open(label_path, "r", encoding="utf-8"))

    # chain_id → item 映射
    pred_map = {p["chain_id"]: p for p in preds}
    label_map = {l["chain_id"]: l for l in labels}

    total = 0
    top1_correct = 0
    top3_correct = 0
    top5_correct = 0
    top7_correct = 0

    # 用于 macro-F1
    per_scene = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    # 混淆矩阵（top1）
    confusion = defaultdict(lambda: defaultdict(int))

    for chain_id, label_item in label_map.items():
        true_scene = label_item.get("true_scene")

        # 跳过无效标签
        if not true_scene or true_scene == "其他":
            continue

        pred_item = pred_map.get(chain_id)
        if not pred_item:
            continue

        pred_top1 = pred_item.get("predicted_scene")
        top3 = pred_item.get("scene_top3", [])
        top5 = pred_item.get("scene_top5", [])
        top7 = pred_item.get("scene_top7", [])

        total += 1

        # ---------- top1 ----------
        if pred_top1 == true_scene:
            top1_correct += 1
            per_scene[true_scene]["tp"] += 1
        else:
            per_scene[true_scene]["fn"] += 1
            per_scene[pred_top1]["fp"] += 1

        confusion[true_scene][pred_top1] += 1

        # ---------- top-k ----------
        if true_scene in top3:
            top3_correct += 1
        if true_scene in top5:
            top5_correct += 1
        if true_scene in top7:
            top7_correct += 1

    if total == 0:
        return None

    # ---------- macro-F1 ----------
    f1_list = []
    for scene, s in per_scene.items():
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        if tp + fp == 0 or tp + fn == 0:
            continue
        precision = tp / (tp + fp)
        recall = tp / (tp + fn)
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
        f1_list.append(f1)

    macro_f1 = sum(f1_list) / len(f1_list) if f1_list else 0

    return {
        "app": os.path.basename(app_dir),
        "total": total,
        "top1_acc": top1_correct / total,
        "top3_acc": top3_correct / total,
        "top5_acc": top5_correct / total,
        "top7_acc": top7_correct / total,
        "macro_f1": macro_f1,
        "confusion": confusion,
    }

# ============================================================
#  批量评测
# ============================================================
def evaluate_all():
    app_dirs = [
        os.path.join(PROCESSED_ROOT, d)
        for d in os.listdir(PROCESSED_ROOT)
        if d.startswith("fastbot-")
    ]

    results = []

    for app_dir in tqdm(app_dirs, desc="评测 APP"):
        r = evaluate_single_app(app_dir)
        if r:
            results.append(r)

    if not results:
        print("❌ 没有可评测的数据")
        return

    total_chains = sum(r["total"] for r in results)

    summary = {
        "total_chains": total_chains,
        "overall_top1_acc": sum(r["top1_acc"] * r["total"] for r in results) / total_chains,
        "overall_top3_acc": sum(r["top3_acc"] * r["total"] for r in results) / total_chains,
        "overall_top5_acc": sum(r["top5_acc"] * r["total"] for r in results) / total_chains,
        "overall_top7_acc": sum(r["top7_acc"] * r["total"] for r in results) / total_chains,
        "overall_macro_f1": sum(r["macro_f1"] for r in results) / len(results),
        "apps": results,
    }

    out_path = os.path.join(PROCESSED_ROOT, OUTFILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n✔ 场景识别评测完成")
    print(f"📄 输出文件: {out_path}")

# ============================================================
#  main
# ============================================================
if __name__ == "__main__":
    evaluate_all()