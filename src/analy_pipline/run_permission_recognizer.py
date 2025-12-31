# -*- coding: utf-8 -*-
"""
rule + llm 混合权限识别（优先规则，LLM 兜底）
输出格式对齐 goal_labels.json
输出文件：results_permission_rule_llm.json
"""

import os
import sys
import json

from permission_recognizer import recognize_permission, save_llm_debug, LLM_DEBUG_LOG


def process_one_app(
    app_dir: str,
    vendor: str = "MI",
    use_llm: bool = True,
):
    """
    对单个 app 目录执行权限识别（rule_llm 模式）
    """
    result_json = os.path.join(app_dir, "result.json")
    if not os.path.exists(result_json):
        print(f"❌ 跳过（没有 result.json）：{app_dir}")
        return

    print(f"\n============================================")
    print(f"📌 处理应用（rule_llm）：{os.path.basename(app_dir)}")

    # 每个 app 重新清空一次 LLM 调试日志
    LLM_DEBUG_LOG.clear()

    with open(result_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    outputs = []
    total = len(data)

    for idx, ui_item in enumerate(data):
        print(f"\n🔗 链条 {idx}/{total-1}")

        # 混合模式（rule + llm）识别权限
        perms = recognize_permission(ui_item, vendor=vendor, use_llm=use_llm)

        chain_id = ui_item.get("chain_id", idx)

        # 输出格式对齐 goal_labels.json
        out_entry = {
            "chain_id": chain_id,
            "files": {
                "before": ui_item["ui_before_grant"]["file"],
                "after": ui_item["ui_after_grant"]["file"],
            },
            "predicted_permissions": perms,
        }

        outputs.append(out_entry)

        print(f" → 权限识别：{perms}")

    # 保存输出（修改文件名！）
    out_path = os.path.join(app_dir, "results_permission_rule_llm.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 已输出混合识别结果：{out_path}")

    # 保存本 app 的 LLM 调试日志
    #save_llm_debug(app_dir)


def main(processed_root: str, vendor="MI"):
    """
    遍历 processed/ 目录下的所有 fastbot-* 目录
    """
    if not os.path.exists(processed_root):
        print("❌ 输入路径不存在！")
        return

    app_dirs = [
        os.path.join(processed_root, d)
        for d in os.listdir(processed_root)
        if d.startswith("fastbot-") and os.path.isdir(os.path.join(processed_root, d))
    ]

    print(f"\n📂 在 {processed_root} 中找到 {len(app_dirs)} 个 app\n")

    for app in sorted(app_dirs):
        process_one_app(app, vendor=vendor, use_llm=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法： python run_permission_rule_llm.py <processed_dir> [MI/HUAWEI]")
        sys.exit(1)

    root = sys.argv[1]
    vendor = sys.argv[2] if len(sys.argv) > 2 else "MI"

    main(root, vendor)