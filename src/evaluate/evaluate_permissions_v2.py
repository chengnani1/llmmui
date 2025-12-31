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
        · 每个 app 的 Accuracy / Precision / Recall / F1
        · 全局汇总：有效 app 数、有效权限链数、TP / FP / FN、全局 Accuracy / Precision / Recall / F1
"""

import os
import json
from collections import Counter

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

    返回 metrics 字典（单个 app 级别）
    """
    pred_map = {x["chain_id"]: x["predicted_permissions"] for x in pred_results}

    TP = 0
    FP = 0
    FN = 0

    per_perm = Counter()
    per_perm_TP = Counter()
    per_perm_FP = Counter()
    per_perm_FN = Counter()

    total = 0  # 参与评测的链条数（排除 true_permissions 为空的）

    for cid, gt_perms in gt_labels.items():

        # 过滤掉 true_permissions 为空的链条
        if not gt_perms:
            continue

        total += 1
        pred = pred_map.get(cid, [])

        gt_set = set(gt_perms)
        pred_set = set(pred)

        for p in gt_set:
            per_perm[p] += 1

        tp_set = gt_set & pred_set
        fp_set = pred_set - gt_set
        fn_set = gt_set - pred_set

        TP += len(tp_set)
        FP += len(fp_set)
        FN += len(fn_set)

        for p in tp_set:
            per_perm_TP[p] += 1
        for p in fp_set:
            per_perm_FP[p] += 1
        for p in fn_set:
            per_perm_FN[p] += 1

    accuracy = TP / (TP + FP + FN + 1e-6) if (TP + FP + FN) > 0 else 0.0
    precision = TP / (TP + FP + 1e-6) if (TP + FP) > 0 else 0.0
    recall = TP / (TP + FN + 1e-6) if (TP + FN) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall + 1e-6) if (precision + recall) > 0 else 0.0

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
        if d.startswith("fastbot-") and os.path.isdir(os.path.join(processed_root, d))
    ]

    print(f"\n📂 找到 {len(all_apps)} 个 app\n")

    # 每种方法：收集每个 app 的 metrics
    results_summary = {
        "rule_only": [],
        "llm_only": [],
        "rule_llm": [],
    }

    for app in sorted(all_apps):
        app_dir = os.path.join(processed_root, app)

        gt = load_json(os.path.join(app_dir, "goal_labels.json"))
        if gt is None:
            print(f"⚠ 跳过（无真实标签）：{app}")
            continue

        # 构建 gt dict
        gt_map = {
            item["chain_id"]: item.get("true_permissions", [])
            for item in gt
            if isinstance(item, dict)
        }

        print(f"\n==============================")
        print(f"📌 评测 APP：{app}")

        for method, filename in EVAL_FILES.items():
            pred = load_json(os.path.join(app_dir, filename))
            if pred is None:
                print(f"  ⚠ {method} 无结果，跳过")
                continue

            metrics = eval_one_method(gt_map, pred)

            # 如果该 app 在这个方法下没有有效链条，就不计入统计
            if metrics["total_evaluated_chains"] == 0:
                print(f"  ⚠ {method} 在该 APP 下无有效链条（全部 true_permissions 为空），跳过")
                continue

            results_summary[method].append(metrics)

            print(f"\n  🔍 方法：{method}")
            print(f"     参与评测链条数：{metrics['total_evaluated_chains']}")
            print(f"     TP={metrics['TP']}  FP={metrics['FP']}  FN={metrics['FN']}")
            print(f"     Accuracy = {metrics['accuracy']:.4f}")
            print(f"     Precision = {metrics['precision']:.4f}")
            print(f"     Recall = {metrics['recall']:.4f}")
            print(f"     F1 = {metrics['f1']:.4f}")

    # ======== 输出整体平均结果 + 全局汇总 ========
    print("\n\n==============================")
    print("📊 **最终整体结果（平均 over all apps + 全局统计）**")
    print("==============================\n")

    for method, lst in results_summary.items():
        if not lst:
            continue

        # 1) 按 app 平均的指标（你现在已经在看的那一组）
        avg_acc = sum(x["accuracy"] for x in lst) / len(lst)
        avg_prec = sum(x["precision"] for x in lst) / len(lst)
        avg_rec = sum(x["recall"] for x in lst) / len(lst)
        avg_f1 = sum(x["f1"] for x in lst) / len(lst)

        # 2) 全局汇总（所有 app 的 TP / FP / FN 加起来）
        total_TP = sum(x["TP"] for x in lst)
        total_FP = sum(x["FP"] for x in lst)
        total_FN = sum(x["FN"] for x in lst)
        total_chains = sum(x["total_evaluated_chains"] for x in lst)
        valid_apps = len(lst)

        global_acc = total_TP / (total_TP + total_FP + total_FN + 1e-6) if (total_TP + total_FP + total_FN) > 0 else 0.0
        global_prec = total_TP / (total_TP + total_FP + 1e-6) if (total_TP + total_FP) > 0 else 0.0
        global_rec = total_TP / (total_TP + total_FN + 1e-6) if (total_TP + total_FN) > 0 else 0.0
        global_f1 = 2 * global_prec * global_rec / (global_prec + global_rec + 1e-6) if (global_prec + global_rec) > 0 else 0.0

        print(f"\n⭐ 方法：{method}")
        print(f"   ▶ 有效参与评测的 APP 数：{valid_apps}")
        print(f"   ▶ 有效权限链总数（true_permissions 非空）：{total_chains}")
        print(f"   ▶ 全局 TP={total_TP}  FP={total_FP}  FN={total_FN}")

        print(f"   —— 按 app 平均指标 ——")
        print(f"      Avg Accuracy  = {avg_acc:.4f}")
        print(f"      Avg Precision = {avg_prec:.4f}")
        print(f"      Avg Recall    = {avg_rec:.4f}")
        print(f"      Avg F1        = {avg_f1:.4f}")

        print(f"   —— 全局 micro 指标（所有样本一起算） ——")
        print(f"      Global Accuracy  = {global_acc:.4f}")
        print(f"      Global Precision = {global_prec:.4f}")
        print(f"      Global Recall    = {global_rec:.4f}")
        print(f"      Global F1        = {global_f1:.4f}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法： python evaluate_permissions.py <processed_dir>")
        sys.exit(1)

    processed_root = sys.argv[1]
    main(processed_root)