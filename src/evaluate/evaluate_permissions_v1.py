# -*- coding: utf-8 -*-
"""
权限识别效果评测脚本

输入：
  processed/
    fastbot-xxx/
      goal_labels.json
      results_permission_rule_only.json
      results_permission_llm_only.json
      results_permission_rule_llm.json

功能：
  - 忽略 true_permissions 为空的链条
  - 对三种方法分别计算：
        Accuracy
        Precision(micro)
        Recall(micro)
        F1(micro)
        FP / FN / TP
        每个权限的详细表现
  - 输出汇总信息
"""

import os
import json
from collections import defaultdict, Counter

EVAL_FILES = {
    "rule_only": "results_permission_rule_only.json",
    "llm_only": "results_permission_llm_only.json",
    "rule_llm": "results_permission_rule_llm.json",
}


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def eval_one_method(gt_labels, pred_results):
    """
    gt_labels: dict(chain_id → true_permissions)
    pred_results: list({chain_id, predicted_permissions})

    返回 metrics 字典
    """
    pred_map = {x["chain_id"]: x["predicted_permissions"] for x in pred_results}

    TP = 0
    FP = 0
    FN = 0

    per_perm = Counter()     # 记录每个权限出现次数
    per_perm_TP = Counter()
    per_perm_FP = Counter()
    per_perm_FN = Counter()

    total = 0  # 参与评测的链条数（排除 true_permissions 为空的）

    for cid, gt_perms in gt_labels.items():

        # 过滤掉 true_permissions == [] 的链条
        if not gt_perms:
            continue

        total += 1
        pred = pred_map.get(cid, [])

        gt_set = set(gt_perms)
        pred_set = set(pred)

        # 统计每个权限出现次数
        for p in gt_set:
            per_perm[p] += 1

        # 计算 TP / FP / FN
        tp_set = gt_set & pred_set
        fp_set = pred_set - gt_set
        fn_set = gt_set - pred_set

        TP += len(tp_set)
        FP += len(fp_set)
        FN += len(fn_set)

        # 每个权限级别
        for p in tp_set:
            per_perm_TP[p] += 1
        for p in fp_set:
            per_perm_FP[p] += 1
        for p in fn_set:
            per_perm_FN[p] += 1

    # 计算指标
    accuracy = TP / (TP + FP + FN + 1e-6)
    precision = TP / (TP + FP + 1e-6)
    recall = TP / (TP + FN + 1e-6)
    f1 = 2 * precision * recall / (precision + recall + 1e-6)

    return {
        "total_evaluated_chains": total,
        "TP": TP,
        "FP": FP,
        "FN": FN,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "per_permission_stats": {
            p: {
                "gt_count": per_perm[p],
                "TP": per_perm_TP[p],
                "FP": per_perm_FP[p],
                "FN": per_perm_FN[p],
                "precision": per_perm_TP[p] / (per_perm_TP[p] + per_perm_FP[p] + 1e-6),
                "recall": per_perm_TP[p] / (per_perm_TP[p] + per_perm_FN[p] + 1e-6),
            }
            for p in per_perm.keys()
        }
    }


def main(processed_root):
    all_apps = [
        d for d in os.listdir(processed_root)
        if d.startswith("fastbot-")
    ]

    print(f"\n📂 找到 {len(all_apps)} 个 app\n")

    # 汇总每种方法的指标
    results_summary = {
        "rule_only": [],
        "llm_only": [],
        "rule_llm": [],
    }

    for app in all_apps:
        app_dir = os.path.join(processed_root, app)

        gt = load_json(os.path.join(app_dir, "goal_labels.json"))
        if gt is None:
            print(f"⚠ 跳过（无真实标签）：{app}")
            continue

        # 构建 gt dict
        gt_map = {item["chain_id"]: item["true_permissions"] for item in gt}

        print(f"\n==============================")
        print(f"📌 评测 APP：{app}")

        for method, filename in EVAL_FILES.items():
            pred = load_json(os.path.join(app_dir, filename))
            if pred is None:
                print(f"  ⚠ {method} 无结果，跳过")
                continue

            metrics = eval_one_method(gt_map, pred)
            results_summary[method].append(metrics)

            print(f"\n🔍 方法：{method}")
            print(f"   参与评测链条数：{metrics['total_evaluated_chains']}")
            print(f"   TP={metrics['TP']}  FP={metrics['FP']}  FN={metrics['FN']}")
            print(f"   Accuracy = {metrics['accuracy']:.4f}")
            print(f"   Precision = {metrics['precision']:.4f}")
            print(f"   Recall = {metrics['recall']:.4f}")
            print(f"   F1 = {metrics['f1']:.4f}")

    # ======== 输出整体平均结果 ========
    print("\n\n==============================")
    print("📊 **最终整体结果（平均 over all apps）**")
    print("==============================\n")

    for method, lst in results_summary.items():
        if not lst:
            continue

        avg = {
            "accuracy": sum(x["accuracy"] for x in lst) / len(lst),
            "precision": sum(x["precision"] for x in lst) / len(lst),
            "recall": sum(x["recall"] for x in lst) / len(lst),
            "f1": sum(x["f1"] for x in lst) / len(lst),
        }

        print(f"\n⭐ 方法：{method}")
        print(f"   Avg Accuracy  = {avg['accuracy']:.4f}")
        print(f"   Avg Precision = {avg['precision']:.4f}")
        print(f"   Avg Recall    = {avg['recall']:.4f}")
        print(f"   Avg F1        = {avg['f1']:.4f}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法： python evaluate_permissions.py <processed_dir>")
        sys.exit(1)

    processed_root = sys.argv[1]
    main(processed_root)