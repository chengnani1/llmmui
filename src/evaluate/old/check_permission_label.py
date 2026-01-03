# -*- coding: utf-8 -*-
"""
check_labels.py

功能：
1. 遍历 processed 目录下所有 fastbot-* 子目录的 goal_labels.json
2. 检查 true_permissions 是否都属于 30 个合法权限集合
3. 将包含 null 的链视为“无权限链”，把 true_permissions 改为空列表 []
4. 输出整体标注情况和权限分布统计，帮助后续做 evaluation

用法示例：
    python check_labels.py /Volumes/Charon/data/work/llm/code/data/version2.11.5/processed
"""

import os
import sys
import json
from collections import Counter, defaultdict

# ===================== 30 个合法权限 =====================
VALID_PERMISSIONS = {
    "READ_CALENDAR",
    "WRITE_CALENDAR",
    "READ_CALL_LOG",
    "WRITE_CALL_LOG",
    "PROCESS_OUTGOING_CALLS",
    "CAMERA",
    "READ_CONTACTS",
    "WRITE_CONTACTS",
    "GET_ACCOUNTS",
    "ACCESS_FINE_LOCATION",
    "ACCESS_COARSE_LOCATION",
    "ACCESS_BACKGROUND_LOCATION",
    "RECORD_AUDIO",
    "READ_PHONE_STATE",
    "READ_PHONE_NUMBERS",
    "CALL_PHONE",
    "ANSWER_PHONE_CALLS",
    "ADD_VOICEMAIL",
    "USE_SIP",
    "ACCEPT_HANDOVER",
    "BODY_SENSORS",
    "SEND_SMS",
    "RECEIVE_SMS",
    "READ_SMS",
    "RECEIVE_WAP_PUSH",
    "RECEIVE_MMS",
    "READ_EXTERNAL_STORAGE",
    "WRITE_EXTERNAL_STORAGE",
    "ACCESS_MEDIA_LOCATION",
    "ACTIVITY_RECOGNITION",
}

# ===================== 主逻辑 =====================

def process_goal_labels(app_dir: str, stats: dict):
    """
    处理单个 fastbot-* 目录下的 goal_labels.json
    - 更新 stats
    - 修改 null 为“无权限”（true_permissions = []）
    """
    label_path = os.path.join(app_dir, "goal_labels.json")
    if not os.path.exists(label_path):
        print(f"⚠ 跳过（无 goal_labels.json）：{app_dir}")
        stats["apps_no_label"] += 1
        return

    with open(label_path, "r", encoding="utf-8") as f:
        try:
            labels = json.load(f)
        except Exception as e:
            print(f"❌ 读取 JSON 失败：{label_path} - {e}")
            stats["apps_bad_json"] += 1
            return

    if not isinstance(labels, list):
        print(f"⚠ goal_labels.json 不是列表：{label_path}")
        stats["apps_bad_json"] += 1
        return

    stats["apps_with_label"] += 1
    stats["chains_total"] += len(labels)

    modified = False

    for idx, item in enumerate(labels):
        if item is None:
            stats["chains_none_label"] += 1
            continue
        if not isinstance(item, dict):
            stats["chains_bad_format"] += 1
            continue

        app_name = os.path.basename(app_dir)
        chain_id = item.get("chain_id", idx)
        perms = item.get("true_permissions", [])

        # 标注为空
        if not perms:
            stats["chains_perm_empty"] += 1
            continue

        # 这里统一保证 perms 是 list[str]
        if not isinstance(perms, list):
            stats["chains_perm_non_list"] += 1
            continue

        # ---- 处理 null→ 无权限链 ----
        if "null" in perms:
            # 直接把该链视为“无权限链”
            stats["chains_with_null"] += 1
            stats["chains_perm_cleared"] += 1
            item["true_permissions"] = []
            modified = True
            # 这类链在统计中作为“无权限”处理，后面不再计入分布
            continue

        # ---- 检查是否都在 VALID_PERMISSIONS 里 ----
        # 有效权限计入统计；非法权限单独收集
        has_valid = False
        for p in perms:
            if p in VALID_PERMISSIONS:
                has_valid = True
                stats["perm_counter"][p] += 1
            else:
                stats["unknown_perm_counter"][p].append(
                    (app_name, chain_id)
                )

        if has_valid:
            stats["chains_with_permission"] += 1
        else:
            stats["chains_perm_unknown_only"] += 1

    # 有修改就回写文件
    if modified:
        with open(label_path, "w", encoding="utf-8") as f:
            json.dump(labels, f, indent=2, ensure_ascii=False)
        print(f"💾 已更新（null→无权限）：{label_path}")


def main(root_dir: str):
    # 统计信息容器
    stats = {
        "apps_scanned": 0,
        "apps_with_label": 0,
        "apps_no_label": 0,
        "apps_bad_json": 0,

        "chains_total": 0,
        "chains_none_label": 0,
        "chains_bad_format": 0,
        "chains_perm_non_list": 0,

        "chains_perm_empty": 0,          # true_permissions 为空列表
        "chains_with_permission": 0,     # true_permissions 中包含 >=1 个合法权限
        "chains_with_null": 0,  # 含 null 的链
        "chains_perm_cleared": 0,        # 被我们清空权限的链
        "chains_perm_unknown_only": 0,   # 只有未知权限的链

        "perm_counter": Counter(),                     # 每个合法权限的出现次数
        "unknown_perm_counter": defaultdict(list),     # 未知权限 -> [(app, chain_id), ...]
    }

    if not os.path.isdir(root_dir):
        print("❌ root_dir 不是目录：", root_dir)
        return

    # 遍历 fastbot-* 目录
    for d in sorted(os.listdir(root_dir)):
        if not d.startswith("fastbot-"):
            continue
        app_dir = os.path.join(root_dir, d)
        if not os.path.isdir(app_dir):
            continue

        stats["apps_scanned"] += 1
        process_goal_labels(app_dir, stats)

    # ============ 输出汇总结果 ============
    print("\n================= 标注检查结果汇总 =================")
    print(f"📂 扫描根目录：{root_dir}")
    print(f"📦 发现 fastbot-* 目录数：{stats['apps_scanned']}")
    print(f"  - 其中有 goal_labels.json 的：{stats['apps_with_label']}")
    print(f"  - 无 goal_labels.json 的：{stats['apps_no_label']}")
    print(f"  - goal_labels.json 解析失败的：{stats['apps_bad_json']}")

    print("\n📊 链条级统计：")
    print(f"  总链条数（labels 条目）：{stats['chains_total']}")
    print(f"  - None / 空标签条目：{stats['chains_none_label']}")
    print(f"  - 非 dict 格式条目：{stats['chains_bad_format']}")
    print(f"  - true_permissions 不是 list 的条目：{stats['chains_perm_non_list']}")

    print(f"\n  - true_permissions 为空（无权限链）：{stats['chains_perm_empty']}")
    print(f"  - 含合法权限的链条数：{stats['chains_with_permission']}")
    print(f"  - 含 null 的链（已被置为空）：{stats['chains_with_null']}")
    print(f"  - 本次脚本清空权限的链条数：{stats['chains_perm_cleared']}")
    print(f"  - 仅包含未知权限（不在 30 个列表里）的链条数：{stats['chains_perm_unknown_only']}")

    # 权限分布
    print("\n📌 合法权限分布（按出现次数排序）：")
    if stats["perm_counter"]:
        for perm, cnt in stats["perm_counter"].most_common():
            print(f"  {perm:25s} : {cnt:4d}")
    else:
        print("  （暂无合法权限标注统计，可能都是空或未知权限）")

    # 未知权限
    print("\n⚠ 未知权限统计（不在那 30 个列表里的）：")
    if stats["unknown_perm_counter"]:
        for perm, occ in stats["unknown_perm_counter"].items():
            print(f"\n  ❗ 未知权限：{perm}")
            print(f"     出现次数：{len(occ)}")
            # 打印前几个样例，方便你回头人工检查
            for app_name, chain_id in occ[:5]:
                print(f"       - {app_name} / chain_id={chain_id}")
            if len(occ) > 5:
                print(f"       ... 等共 {len(occ)} 条")
    else:
        print("  ✅ 所有 true_permissions 均在 30 个合法权限集合中（除 null 已被清空）。")

    print("\n✅ 检查完成，可据此设计 evaluation 统计。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python check_labels.py <processed_root_dir>")
        sys.exit(1)

    root = sys.argv[1]
    main(root)