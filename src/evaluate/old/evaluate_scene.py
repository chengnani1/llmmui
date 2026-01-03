# -*- coding: utf-8 -*-
import os
import json
import sys
from collections import defaultdict
from tqdm import tqdm

# ============================================================
#  评估单个 APP
# ============================================================
def evaluate_single_app(app_dir):
    """
    对一个 APP 的场景识别进行评测（适配 v4 字段：top1, top3, top5, top7）
    """

    pred_path = os.path.join(app_dir, "results_scene_llm.json")
    label_path = os.path.join(app_dir, "goal_labels.json")

    if not os.path.exists(pred_path) or not os.path.exists(label_path):
        print(f"⚠ 缺少预测或标签文件：{app_dir}")
        return None

    preds = json.load(open(pred_path, "r", encoding="utf-8"))
    labels = json.load(open(label_path, "r", encoding="utf-8"))

    if len(preds) != len(labels):
        print(f"⚠ 链条数量不一致：pred={len(preds)}, label={len(labels)} @ {app_dir}")

    # 全局计数
    total = 0
    top1_correct = 0
    top3_correct = 0
    top5_correct = 0
    top7_correct = 0

    # 每个场景的统计（支持 Macro-F1）
    per_scene_stats = defaultdict(lambda: {
        "total": 0,
        "top1": 0,
        "top3": 0,
        "top5": 0,
        "top7": 0,
        "fp": 0,     # top1 错误命中（用于 F1）
    })

    # 混淆矩阵（top1）
    confusion = defaultdict(lambda: defaultdict(int))

    # 遍历每条 chain
    for label_item, pred_item in zip(labels, preds):

        if label_item is None or pred_item is None:
            continue

        true_scene = label_item.get("true_scene")

        # 跳过 “其他”
        if true_scene is None or true_scene == "其他":
            continue

        pred_top1 = pred_item.get("predicted_scene")
        top3_list = pred_item.get("scene_top3", [])
        top5_list = pred_item.get("scene_top5", [])
        top7_list = pred_item.get("scene_top7", [])

        if pred_top1 is None or not isinstance(top3_list, list):
            continue

        total += 1
        per_scene_stats[true_scene]["total"] += 1

        # -------- top1 --------
        if pred_top1 == true_scene:
            top1_correct += 1
            per_scene_stats[true_scene]["top1"] += 1
        else:
            per_scene_stats[pred_top1]["fp"] += 1  # 假阳性

        # 混淆矩阵（top1）
        confusion[true_scene][pred_top1] += 1

        # -------- top3 --------
        if true_scene in top3_list:
            top3_correct += 1
            per_scene_stats[true_scene]["top3"] += 1

        # -------- top5 --------
        if true_scene in top5_list:
            top5_correct += 1
            per_scene_stats[true_scene]["top5"] += 1

        # -------- top7 --------
        if true_scene in top7_list:
            top7_correct += 1
            per_scene_stats[true_scene]["top7"] += 1

    if total == 0:
        return None

    # =========================
    # 计算 Macro-F1
    # =========================
    f1_list = []
    for scene, stats in per_scene_stats.items():
        if stats["total"] == 0:
            continue

        tp = stats["top1"]
        fn = stats["total"] - tp
        fp = stats["fp"]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / stats["total"] if stats["total"] > 0 else 0

        if (precision + recall) > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0

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
        "per_scene": per_scene_stats,
        "confusion": confusion,
    }


# ============================================================
#  批量评估
# ============================================================
def evaluate_all(processed_root):

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
        print("❌ 没有可评测的数据")
        return

    # 综合指标
    total_chains = sum(r["total"] for r in all_results)
    top1 = sum(r["top1_acc"] * r["total"] for r in all_results)
    top3 = sum(r["top3_acc"] * r["total"] for r in all_results)
    top5 = sum(r["top5_acc"] * r["total"] for r in all_results)
    top7 = sum(r["top7_acc"] * r["total"] for r in all_results)

    macro_f1 = sum(r["macro_f1"] for r in all_results) / len(all_results)

    output = {
        "total_chains": total_chains,
        "overall_top1_acc": top1 / total_chains,
        "overall_top3_acc": top3 / total_chains,
        "overall_top5_acc": top5 / total_chains,
        "overall_top7_acc": top7 / total_chains,
        "overall_macro_f1": macro_f1,
        "apps": all_results,
    }

    out_path = os.path.join(processed_root, "evaluation_scene_4.json")
    json.dump(output, open(out_path, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    print(f"✔ 场景识别评测完成，输出：{out_path}")


# ============================================================
#  主入口
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python evaluate_scene_v5.py <processed目录路径>")
        sys.exit(1)

    evaluate_all(sys.argv[1])