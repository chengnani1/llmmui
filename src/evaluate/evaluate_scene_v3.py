# -*- coding: utf-8 -*-
import os
import json
from collections import defaultdict
from tqdm import tqdm  # type: ignore
import sys


def evaluate_single_app(app_dir):
    """
    对一个 APP 的场景识别进行评测（适配新版 JSON 字段）
    """

    pred_path = os.path.join(app_dir, "results_scene_llm.json")
    label_path = os.path.join(app_dir, "goal_labels.json")

    # 必须两个文件都存在
    if not os.path.exists(pred_path) or not os.path.exists(label_path):
        print(f"⚠ 缺少预测或标签文件：{app_dir}")
        return None

    preds = json.load(open(pred_path, "r", encoding="utf-8"))
    labels = json.load(open(label_path, "r", encoding="utf-8"))

    # 安全检查：长度不一致打印警告
    if len(preds) != len(labels):
        print(f"⚠ 链条数量不一致：pred={len(preds)}, label={len(labels)} @ {app_dir}")

    total = 0
    top1_correct = 0
    top3_correct = 0

    # 每个场景的统计
    per_scene_stats = defaultdict(lambda: {"total": 0, "top1": 0, "top3": 0})

    # 遍历链条
    for label_item, pred_item in zip(labels, preds):

        if label_item is None or pred_item is None:
            continue

        # 标签场景
        true_scene = label_item.get("true_scene")

        # 不评测：true_scene 缺失 or 为 "其他"
        if true_scene is None or true_scene == "其他":
            continue

        # ----------- 新版字段 -----------
        pred_top1 = pred_item.get("predicted_scene")
        pred_top3 = pred_item.get("scene_top3")

        # 跳过异常预测
        if pred_top1 is None or not isinstance(pred_top3, list):
            continue

        total += 1
        per_scene_stats[true_scene]["total"] += 1

        # top1 命中
        if pred_top1 == true_scene:
            top1_correct += 1
            per_scene_stats[true_scene]["top1"] += 1

        # top3 命中
        if true_scene in pred_top3:
            top3_correct += 1
            per_scene_stats[true_scene]["top3"] += 1

    if total == 0:
        return None

    return {
        "app": os.path.basename(app_dir),
        "total": total,
        "top1_acc": top1_correct / total,
        "top3_acc": top3_correct / total,
        "per_scene": per_scene_stats,
    }


def evaluate_all(processed_root):
    """
    遍历所有 fastbot-* 目录进行评测
    """

    app_dirs = [
        os.path.join(processed_root, d)
        for d in os.listdir(processed_root)
        if d.startswith("fastbot-")
    ]

    all_results = []

    for app_dir in tqdm(app_dirs, desc="评测 APP"):
        r = evaluate_single_app(app_dir)
        if r:
            all_results.append(r)

    if len(all_results) == 0:
        print("❌ 没有任何有效评测结果（可能 true_scene 均为 '其他'）")
        return

    # 汇总 overall
    total_chains = sum(r["total"] for r in all_results)
    top1 = sum(r["top1_acc"] * r["total"] for r in all_results)
    top3 = sum(r["top3_acc"] * r["total"] for r in all_results)

    overall = {
        "total_chains": total_chains,
        "overall_top1_acc": top1 / total_chains,
        "overall_top3_acc": top3 / total_chains,
        "apps": all_results,
    }

    # 输出文件
    output_path = os.path.join(processed_root, "evaluation_scene.json")
    json.dump(overall, open(output_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"✔ 场景识别评测完成，输出：{output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python evaluate_scene.py <processed目录路径>")
        sys.exit(1)

    target_dir = sys.argv[1]
    evaluate_all(target_dir)