# -*- coding: utf-8 -*-
import os
import re
import sys

def delete_chain_pngs(app_dir):
    """
    删除 app_dir 下 0.png / 1.png / 2.png 这种 chain 图，
    但保留所有 step-xxx.png 文件。
    """
    removed = 0

    for f in os.listdir(app_dir):
        file_path = os.path.join(app_dir, f)

        # 仅处理 png 文件
        if not f.lower().endswith(".png"):
            continue

        # 匹配纯数字文件名，例如 "0.png"、"12.png"
        if re.fullmatch(r"\d+\.png", f):
            try:
                os.remove(file_path)
                removed += 1
                print(f"🗑 删除 chain 图：{file_path}")
            except Exception as e:
                print(f"⚠ 删除失败 {file_path}: {e}")

    return removed


def main(root_dir):
    """
    遍历 processed/ 根目录下所有 fastbot- 开头的文件夹
    """
    total_deleted = 0

    for d in sorted(os.listdir(root_dir)):
        if d.startswith("fastbot-"):
            app_dir = os.path.join(root_dir, d)
            if os.path.isdir(app_dir):
                print(f"\n📂 处理目录：{app_dir}")
                count = delete_chain_pngs(app_dir)
                total_deleted += count
                print(f"✅ 删除 {count} 个 chain png")

    print("\n🎉 完成，总计删除：", total_deleted)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python delete_chain_pngs.py <processed目录>")
        sys.exit(1)

    root = sys.argv[1]
    main(root)