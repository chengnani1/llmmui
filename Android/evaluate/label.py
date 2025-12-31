# -*- coding: utf-8 -*-
import os
import json
import sys
import subprocess
import re
import hashlib
from typing import Dict, Any, List
from PIL import Image # type: ignore
from label_config import SCENE_LIST, PERMISSION_CANDIDATES


# ---------------------------------------------------------
# 打开图片
# ---------------------------------------------------------
def open_image(path: str):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path])
        elif sys.platform == "win32":
            subprocess.Popen(["start", path], shell=True)
        else:
            Image.open(path).show()
    except Exception as e:
        print("⚠ 打开图片失败:", e)


# ---------------------------------------------------------
# 拼接整条链为一张图
# ---------------------------------------------------------
def merge_images_horizontally_strict(img_paths, output_path):
    imgs = []
    for p in img_paths:
        if os.path.exists(p):
            try:
                imgs.append(Image.open(p).convert("RGB"))
            except:
                pass

    if not imgs:
        raise RuntimeError("❌ 图片无法读取：" + str(img_paths))

    min_h = min(im.height for im in imgs)
    resized = [im.resize((int(im.width * min_h / im.height), min_h)) for im in imgs]

    total_width = sum(im.width for im in resized)
    merged = Image.new("RGB", (total_width, min_h), (255, 255, 255))

    x = 0
    for im in resized:
        merged.paste(im, (x, 0))
        x += im.width

    merged.save(output_path)
    return output_path


# ---------------------------------------------------------
# 指纹：用于不同 app 链条去重
# ---------------------------------------------------------
def _normalize_text(t: str) -> str:
    t = re.sub(r"\s+", "", t or "")
    return t.lower()


def compute_chain_fingerprint(item: Dict[str, Any]) -> str:
    before = item["ui_before_grant"]["feature"].get("text", "")
    grant = item["ui_granting"][0]["feature"].get("text", "") if item.get("ui_granting") else ""
    after = item["ui_after_grant"]["feature"].get("text", "")
    key = "|".join([_normalize_text(before), _normalize_text(grant), _normalize_text(after)])
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------
# 生成 chain_id.png（不依赖 tuple 文件）
# ---------------------------------------------------------
def generate_chain_images(app_dir: str):
    result_json = os.path.join(app_dir, "result.json")
    if not os.path.exists(result_json):
        print("❌ 找不到 result.json：", app_dir)
        return

    data = json.load(open(result_json, "r", encoding="utf-8"))
    print(f"🧩 生成 chain 图：{app_dir}")

    for idx, item in enumerate(data):
        chain_id = item.get("chain_id", idx)
        out_name = f"chain_{chain_id}.png"
        out_path = os.path.join(app_dir, out_name)

        if os.path.exists(out_path):
            continue

        before = os.path.join(app_dir, item["ui_before_grant"]["file"])
        after = os.path.join(app_dir, item["ui_after_grant"]["file"])
        granting = [os.path.join(app_dir, g["file"]) for g in item.get("ui_granting", [])]

        try:
            merge_images_horizontally_strict([before] + granting + [after], out_path)
        except Exception as e:
            print(f"⚠ 生成 {out_name} 失败：{e}")


# ---------------------------------------------------------
# 打印菜单
# ---------------------------------------------------------
def print_scene_menu():
    print("\n====== 请选择真实场景（1-44）======")
    for i, s in enumerate(SCENE_LIST, start=1):
        print(f"{i:2d}. {s}")
    print("b 回退, s 跳过, q 退出\n")


def print_permission_menu():
    print("\n====== 请选择权限（支持多选）======")
    for i, p in enumerate(PERMISSION_CANDIDATES, start=1):
        print(f"{i:2d}. {p}")
    print("\n输入示例：1,3,7 或 CAMERA, READ_CALL_LOG\n")


# ---------------------------------------------------------
# 多选权限解析
# ---------------------------------------------------------
def parse_multi_permissions(user_input: str) -> List[str]:
    user_input = user_input.strip()
    if not user_input:
        return []

    parts = [p.strip() for p in user_input.split(",")]

    result = []
    for p in parts:
        if p.isdigit():  # 编号
            n = int(p)
            if 1 <= n <= len(PERMISSION_CANDIDATES):
                perm = PERMISSION_CANDIDATES[n - 1]
                if perm == "OTHER":
                    custom = input("请输入具体权限名：").strip()
                    result.append(custom if custom else "OTHER")
                else:
                    result.append(perm)
        else:  # 文本权限
            result.append(p)

    return list(dict.fromkeys(result))


# ---------------------------------------------------------
# 主标注函数（支持 full / scene / perm）
# ---------------------------------------------------------
def label_app(app_dir: str, mode: str = "full"):
    assert mode in ("full", "scene", "perm")

    result_json = os.path.join(app_dir, "result.json")
    if not os.path.exists(result_json):
        print("❌ 没找到 result.json")
        return

    # 先生成所有 chain_id.png
    generate_chain_images(app_dir)

    data = json.load(open(result_json, "r", encoding="utf-8"))
    label_path = os.path.join(app_dir, "goal_labels.json")

    labels = json.load(open(label_path, "r", encoding="utf-8")) if os.path.exists(label_path) else [None] * len(data)
    while len(labels) < len(data):
        labels.append(None)

    fp2idx = {}
    for i, item in enumerate(data):
        if labels[i] is not None:
            fp2idx[compute_chain_fingerprint(item)] = i

    idx = 0
    while idx < len(data):
        item = data[idx]
        chain_id = item.get("chain_id", idx)
        chain_img = os.path.join(app_dir, f"chain_{chain_id}.png")

        # 复用标签
        fp = compute_chain_fingerprint(item)
        if fp in fp2idx and labels[idx] is None:
            labels[idx] = labels[fp2idx[fp]]
            print(f"🔁 自动复用：{idx} → {labels[idx]}")
            idx += 1
            continue

        # 打开链条图
        if os.path.exists(chain_img):
            open_image(chain_img)

        print(f"\n🔗 链条 {idx} / {len(data)-1}")

        old = labels[idx] or {}
        true_scene = old.get("true_scene")
        true_perms = old.get("true_permissions", [])

        # 场景标注
        if mode in ("full", "scene"):
            print_scene_menu()
            s = input("场景编号： ").strip()
            if s == "q": break
            if s == "b":
                idx = max(0, idx - 1); labels[idx] = None; continue
            if s != "s":
                if s.isdigit() and 1 <= int(s) <= len(SCENE_LIST):
                    true_scene = SCENE_LIST[int(s) - 1]
                else:
                    print("⚠ 输入错误"); continue

        # 权限标注
        if mode in ("full", "perm"):
            print_permission_menu()
            p = input("权限输入： ").strip()
            if p == "q": break
            if p == "b":
                idx = max(0, idx - 1); labels[idx] = None; continue
            if p != "s":
                true_perms = parse_multi_permissions(p)

        labels[idx] = {
            "chain_id": chain_id,
            "files": {
                "before": item["ui_before_grant"]["file"],
                "after": item["ui_after_grant"]["file"],
            },
            "true_scene": true_scene,
            "true_permissions": true_perms,
        }

        json.dump(labels, open(label_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"✅ 完成：场景={true_scene} 权限={true_perms}")
        idx += 1

    print("🎉 标注完成：", label_path)


# ---------------------------------------------------------
# none 模式：只生成 chain_id.png
# ---------------------------------------------------------
def generate_only_mode(app_dir: str):
    print(f"🖼 仅生成 chain_id.png：{app_dir}")
    generate_chain_images(app_dir)


# ---------------------------------------------------------
# main
# ---------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python label.py <app目录或processed目录> [full|scene|perm|none]")
        sys.exit(1)

    target = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "full"

    if mode not in ("full", "scene", "perm", "none"):
        print("⚠ 错误模式：必须是 full/scene/perm/none")
        sys.exit(1)

    if os.path.isdir(target) and os.path.basename(target).startswith("fastbot-"):
        if mode == "none":
            generate_only_mode(target)
        else:
            label_app(target, mode)
    else:
        for d in sorted(os.listdir(target)):
            if d.startswith("fastbot-"):
                app_dir = os.path.join(target, d)
                if mode == "none":
                    generate_only_mode(app_dir)
                else:
                    label_app(app_dir, mode)