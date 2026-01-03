# -*- coding: utf-8 -*-
"""
analyze_rule_fn_all_apps.py

功能：
遍历 processed/ 下所有 fastbot-* 目录，
对比：
  - goal_labels.json
  - results_permission_rule_only.json

统计【规则漏检（FN）】：
1. 全局每个权限的 FN 次数
2. 每个权限 FN 出现在哪些 app / chain
3. 每个 app 的规则 Recall

用法：
python analyze_rule_fn_all_apps.py <processed_root>
"""

import os
import sys
import json
from collections import Counter, defaultdict


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(processed_root: str):
    global_fn_counter = Counter()
    global_fn_details = defaultdict(list)

    app_recall = {}
    total_eval_chains = 0
    total_fn = 0

    apps = [
        d for d in os.listdir(processed_root)
        if d.startswith("fastbot-") and
        os.path.isdir(os.path.join(processed_root, d))
    ]

    print(f"\n📂 发现 fastbot-* 目录数：{len(apps)}")

    for app in sorted(apps):
        app_dir = os.path.join(processed_root, app)

        gt_path = os.path.join(app_dir, "goal_labels.json")
        rule_path = os.path.join(app_dir, "results_permission_rule_only.json")

        if not os.path.exists(gt_path) or not os.path.exists(rule_path):
            continue

        gt = load_json(gt_path)
        rule = load_json(rule_path)

        gt_map = {
            item["chain_id"]: item.get("true_permissions", [])
            for item in gt
            if isinstance(item, dict)
        }

        rule_map = {
            item["chain_id"]: item.get("predicted_permissions", [])
            for item in rule
            if isinstance(item, dict)
        }

        app_tp = 0
        app_fn = 0

        for cid, gt_perms in gt_map.items():
            if not gt_perms:
                continue

            total_eval_chains += 1
            gt_set = set(gt_perms)
            pred_set = set(rule_map.get(cid, []))

            fn = gt_set - pred_set
            if fn:
                for p in fn:
                    global_fn_counter[p] += 1
                    global_fn_details[p].append((app, cid))
                    app_fn += 1
                    total_fn += 1
            else:
                app_tp += 1

        denom = app_tp + app_fn
        if denom > 0:
            app_recall[app] = app_tp / denom

    # ===================== 输出结果 =====================

    print("\n================ 全局规则漏检（FN）统计 ================\n")

    print(f"📊 参与评测链条总数：{total_eval_chains}")
    print(f"❌ 规则漏检总数（FN）：{total_fn}\n")

    print("🔻 各权限 FN 次数（从多到少）：")
    for perm, cnt in global_fn_counter.most_common():
        print(f"  {perm:25s} : {cnt:4d}")

    print("\n================ 各权限漏检详情 =================\n")
    for perm, occ in global_fn_details.items():
        print(f"\n🔴 权限：{perm}")
        print(f"   漏检次数：{len(occ)}")
        for app, cid in occ[:10]:
            print(f"     - {app} / chain_id={cid}")
        if len(occ) > 10:
            print(f"     ... 等共 {len(occ)} 条")

    print("\n================ 各 App 规则 Recall =================\n")
    for app, rec in sorted(app_recall.items(), key=lambda x: x[1]):
        flag = " ❗" if rec < 0.8 else ""
        print(f"  {app:55s} : Recall = {rec:.3f}{flag}")

    print("\n======================================================")
    print("✅ 规则漏检分析完成")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法：python analyze_rule_fn_all_apps.py <processed_root>")
        sys.exit(1)

    main(sys.argv[1])