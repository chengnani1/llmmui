# -*- coding: utf-8 -*-
"""
批量合并 processed/*/results_permission_debug.json
并输出到 log 目录，随后删除原文件。
"""

import os
import json
import shutil

# 根路径
PROCESSED_DIR = "/Volumes/Charon/data/work/llm/code/data/version2.11.5/processed"
LOG_DIR = "/Volumes/Charon/data/work/llm/code/data/version2.11.5/log"

# 输出文件
MERGED_LOG_FILE = os.path.join(LOG_DIR, "merged_results_permission_debug.json")


def main():
    # 确保 log 目录存在
    os.makedirs(LOG_DIR, exist_ok=True)

    merged_logs = []

    # 遍历所有 fastbot 目录
    for d in sorted(os.listdir(PROCESSED_DIR)):
        app_dir = os.path.join(PROCESSED_DIR, d)
        if not os.path.isdir(app_dir):
            continue
        if not d.startswith("fastbot-"):
            continue

        debug_file = os.path.join(app_dir, "results_permission_debug.json")

        if os.path.exists(debug_file):
            print(f"📖 发现调试日志：{debug_file}")

            try:
                with open(debug_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 只有非空才合并
                if isinstance(data, list) and len(data) > 0:
                    merged_logs.extend(data)
                    print(f"  → 合并 {len(data)} 条日志")

                # 删除原文件
                os.remove(debug_file)
                print("  ✓ 已删除原调试日志文件")

            except Exception as e:
                print(f"  ⚠️ 无法读取或删除 {debug_file}: {e}")

    # 保存合并日志
    with open(MERGED_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(merged_logs, f, indent=2, ensure_ascii=False)

    print("\n============================")
    print(f"🎉 合并完成！共 {len(merged_logs)} 条日志")
    print(f"📁 输出文件：{MERGED_LOG_FILE}")
    print("============================")


if __name__ == "__main__":
    main()