# -*- coding: utf-8 -*-
import os
import json
from collections import Counter, defaultdict
from tqdm import tqdm #type: ignore

def load_true_scenes(label_path):
    """读取 goal_labels.json，返回 true_scene 列表"""
    data = json.load(open(label_path, "r", encoding="utf-8"))
    scenes = []
    for item in data:
        if not item:
            continue
        s = item.get("true_scene")
        if s:
            scenes.append(s)
    return scenes


def load_pred_scenes(pred_path):
    """读取 results_scene_llm.json，返回 predicted_scene 列表"""
    data = json.load(open(pred_path, "r", encoding="utf-8"))
    scenes = []
    for item in data:
        if not item:
            continue
        s = item.get("predicted_scene")
        if s:
            scenes.append(s)
    return scenes


def stat_all(processed_root):
    true_counter = Counter()
    pred_counter = Counter()

    app_dirs = [
        os.path.join(processed_root, d)
        for d in os.listdir(processed_root)
        if d.startswith("fastbot-")
    ]

    for app in tqdm(app_dirs, desc="扫描 APP"):
        label_path = os.path.join(app, "goal_labels.json")
        pred_path = os.path.join(app, "results_scene_llm.json")

        if not os.path.exists(label_path) or not os.path.exists(pred_path):
            continue

        true_scenes = load_true_scenes(label_path)
        pred_scenes = load_pred_scenes(pred_path)

        true_counter.update(true_scenes)
        pred_counter.update(pred_scenes)

    return true_counter, pred_counter


def compare_distributions(true_counter, pred_counter):
    """对比真实分布与预测分布"""
    scenes = set(true_counter.keys()) | set(pred_counter.keys())
    comparison = []

    for s in sorted(scenes):
        true_cnt = true_counter.get(s, 0)
        pred_cnt = pred_counter.get(s, 0)

        diff = pred_cnt - true_cnt

        comparison.append({
            "scene": s,
            "true": true_cnt,
            "pred": pred_cnt,
            "diff": diff
        })

    return comparison


def save_results(true_counter, pred_counter, comparison, root):
    output = {
        "true_distribution": dict(true_counter),
        "pred_distribution": dict(pred_counter),
        "compare": comparison
    }

    out_path = os.path.join(root, "scene_distribution.json")
    json.dump(output, open(out_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"\n✔ 统计完成：{out_path}")

    # 额外输出 Markdown 方便阅读
    md_path = os.path.join(root, "scene_distribution.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("| 场景 | 真实数量 | 预测数量 | 差值（预测-真实） |\n")
        f.write("|------|-----------|-----------|--------------------|\n")
        for item in comparison:
            f.write(f"| {item['scene']} | {item['true']} | {item['pred']} | {item['diff']} |\n")

    print(f"✔ Markdown 输出：{md_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python scene_distribution_stat.py <processed目录>")
        sys.exit(1)

    processed_root = sys.argv[1]

    true_counter, pred_counter = stat_all(processed_root)
    comparison = compare_distributions(true_counter, pred_counter)

    save_results(true_counter, pred_counter, comparison, processed_root)