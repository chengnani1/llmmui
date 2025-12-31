# -*- coding: utf-8 -*-
"""
权限识别效果评测 + Rule 错误样本导出（增强版）

新增：
✔ 在 mismatch log 中记录 chain PNG 信息
"""

import os
import json

# =====================================================
# 自动定位项目根目录
# =====================================================

def find_project_root(start_path: str) -> str:
    cur = os.path.abspath(start_path)
    while cur != "/":
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        cur = os.path.dirname(cur)
    raise RuntimeError("❌ 无法定位项目根目录（未找到 .git）")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = find_project_root(SCRIPT_DIR)

PROCESSED_ROOT = os.path.join(PROJECT_ROOT, "data", "processed")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs", "permission")
os.makedirs(LOG_DIR, exist_ok=True)

# =====================================================
# 文件名配置
# =====================================================

GT_FILE = "labels_permission.json"

EVAL_FILES = {
    "rule_only": "result_permission_rule.json",
    "llm_only": "result_permission_llm.json",
    "rule_llm": "result_permission_rule_llm.json",
}

# =====================================================
# Utils
# =====================================================

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# =====================================================
# Rule mismatch collection（增强版）
# =====================================================

def collect_rule_mismatches(app_name, app_dir, gt_map, rule_preds):
    """
    收集 rule_only 与 GT 不一致的链条，并记录对应 PNG
    """

    pred_map = {
        item["chain_id"]: item.get("predicted_permissions", [])
        for item in rule_preds
        if isinstance(item, dict)
    }

    mismatches = []

    for cid, gt_perms in gt_map.items():
        if not gt_perms:
            continue

        pred = pred_map.get(cid, [])

        gt_set = set(gt_perms)
        pred_set = set(pred)

        if gt_set == pred_set:
            continue

        img_name = f"chain_{cid}.png"
        img_abs = os.path.join(app_dir, img_name)

        mismatches.append({
            "chain_id": cid,

            # === PNG 信息 ===
            "chain_image": img_name,
            "chain_image_path": os.path.relpath(img_abs, PROJECT_ROOT),

            # === 权限信息 ===
            "true_permissions": sorted(gt_set),
            "predicted_permissions": sorted(pred_set),
            "missing_permissions": sorted(gt_set - pred_set),
            "extra_permissions": sorted(pred_set - gt_set),
        })

    return mismatches

# =====================================================
# Core evaluation
# =====================================================

def eval_one_method(gt_map, pred_results):

    pred_map = {
        item["chain_id"]: item.get("predicted_permissions", [])
        for item in pred_results
        if isinstance(item, dict)
    }

    TP = FP = FN = 0

    for cid, gt_perms in gt_map.items():
        if not gt_perms:
            continue

        pred = pred_map.get(cid, [])

        gt_set = set(gt_perms)
        pred_set = set(pred)

        TP += len(gt_set & pred_set)
        FP += len(pred_set - gt_set)
        FN += len(gt_set - pred_set)

    if TP + FP + FN == 0:
        return None

    precision = TP / (TP + FP + 1e-6)
    recall = TP / (TP + FN + 1e-6)
    f1 = 2 * precision * recall / (precision + recall + 1e-6)
    accuracy = TP / (TP + FP + FN + 1e-6)

    return {
        "TP": TP,
        "FP": FP,
        "FN": FN,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }

# =====================================================
# Main
# =====================================================

def main():

    print("🚀 Permission Evaluation Tool")
    print("📁 Project root :", PROJECT_ROOT)
    print("📁 Processed dir:", PROCESSED_ROOT)
    print("📁 Log dir      :", LOG_DIR)

    apps = sorted([
        d for d in os.listdir(PROCESSED_ROOT)
        if d.startswith("fastbot-")
        and os.path.isdir(os.path.join(PROCESSED_ROOT, d))
    ])

    summary = {k: [] for k in EVAL_FILES}

    for app in apps:
        app_dir = os.path.join(PROCESSED_ROOT, app)

        gt_raw = load_json(os.path.join(app_dir, GT_FILE))
        if gt_raw is None:
            continue

        gt_map = {
            item["chain_id"]: item.get("true_permissions", [])
            for item in gt_raw
            if isinstance(item, dict)
        }

        print(f"\n==============================")
        print(f"📌 APP: {app}")

        for method, fname in EVAL_FILES.items():
            pred = load_json(os.path.join(app_dir, fname))
            if pred is None:
                continue

            metrics = eval_one_method(gt_map, pred)
            if metrics is None:
                continue

            summary[method].append(metrics)

            print(
                f"  🔍 {method:8s} | "
                f"Acc={metrics['accuracy']:.4f}  "
                f"P={metrics['precision']:.4f}  "
                f"R={metrics['recall']:.4f}  "
                f"F1={metrics['f1']:.4f}"
            )

            # ===== Rule mismatch 导出（含 PNG）=====
            if method == "rule_only":
                mismatches = collect_rule_mismatches(
                    app, app_dir, gt_map, pred
                )
                if mismatches:
                    out_path = os.path.join(
                        LOG_DIR,
                        f"rule_mismatch_{app}.json"
                    )
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(mismatches, f, indent=2, ensure_ascii=False)
        # =================================================
    # Global (micro) evaluation summary
    # =================================================

    print("\n==============================")
    print("📊 Global Evaluation Summary")
    print("==============================")

    for method, lst in summary.items():
        if not lst:
            continue

        TP = sum(x["TP"] for x in lst)
        FP = sum(x["FP"] for x in lst)
        FN = sum(x["FN"] for x in lst)

        precision = TP / (TP + FP + 1e-6)
        recall = TP / (TP + FN + 1e-6)
        f1 = 2 * precision * recall / (precision + recall + 1e-6)
        accuracy = TP / (TP + FP + FN + 1e-6)

        print(f"\n⭐ Method: {method}")
        print(f"   TP={TP}  FP={FP}  FN={FN}")
        print(f"   Accuracy = {accuracy:.4f}")
        print(f"   Precision= {precision:.4f}")
        print(f"   Recall   = {recall:.4f}")
        print(f"   F1       = {f1:.4f}")
    print("\n✅ Done. Rule mismatches saved with PNG info.")

if __name__ == "__main__":
    main()