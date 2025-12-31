import os
import json
from collections import Counter

root = "/Volumes/Charon/data/work/llm/code/data/version2.11.5/processed"

scene_counter = Counter()

for dirpath, dirnames, filenames in os.walk(root):
    if "goal_labels.json" in filenames:
        json_path = os.path.join(dirpath, "goal_labels.json")

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                print(f"⚠ 非列表结构，跳过: {json_path}")
                continue

            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    continue

                scene = item.get("true_scene")
                if scene is not None:
                    scene_counter[scene] += 1

        except Exception as e:
            print(f"⚠ 读取失败 {json_path}: {e}")

# 输出统计结果
print("\n========================")
print(" true_scene 统计结果")
print("========================")

for scene, count in scene_counter.most_common():
    print(f"{scene}: {count}")

print("\n总类别数量:", len(scene_counter))
print("总计场景标注数:", sum(scene_counter.values()))