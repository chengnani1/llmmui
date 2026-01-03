import os
import json

ROOT = "/Volumes/Charon/data/work/llm/code/data/version2.11.5/processed"
#ROOT = "/Volumes/Charon/data/work/llm/code/data/version2.11/raw"
OUTPUT = "result.json"

result = {}
sum_png = 0
sum_chain = 0

for current_dir, sub_dirs, files in os.walk(ROOT):
    # 只统计最底层 fastbot-* 目录（含 result.json 的目录）
    if "result.json" not in files and "tupleOfPermissions.json" not in files:
        continue

    relative_path = os.path.relpath(current_dir, ROOT)
    if relative_path == ".":
        relative_path = os.path.basename(ROOT)

    # ① PNG 数量统计
    png_count = sum(1 for f in files if f.lower().endswith(".png"))
    sum_png += png_count

    # ② 权限链条数量统计
    chain_count = 0
    tuple_file = os.path.join(current_dir, "tupleOfPermissions.json")

    if os.path.exists(tuple_file):
        try:
            with open(tuple_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                chain_count = len(data)
        except Exception as e:
            print(f"⚠ tupleOfPermissions.json 解析失败: {tuple_file}, 错误: {e}")

    sum_chain += chain_count

    result[relative_path] = {
        "png_count": png_count,
        "chain_count": chain_count
    }

# 总计
result["sum_png"] = sum_png
result["sum_chain"] = sum_chain

# 写入文件
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=4)

print(f"统计完成，结果写入: {OUTPUT}")