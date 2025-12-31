import json
import matplotlib.pyplot as plt
import numpy as np

# 假设你的 JSON 存在 mapping.json
with open("../permission_map_en.json", "r", encoding="utf-8") as f:
    data = json.load(f)

allowed_map = data["allowed_map"]
banned_map = data["banned_map"]

scenarios = list(allowed_map.keys())
allowed_counts = [len(allowed_map[s]) for s in scenarios]
banned_counts = [len(banned_map.get(s, [])) for s in scenarios]

# 可以只取前若干个典型场景做图，例如前 12 个
max_scenarios = 120
scenarios_plot = scenarios[:max_scenarios]
allowed_plot = allowed_counts[:max_scenarios]
banned_plot = banned_counts[:max_scenarios]

x = np.arange(len(scenarios_plot))
width = 0.35

plt.figure(figsize=(10, 4))
plt.bar(x - width/2, allowed_plot, width, label="Allowed", hatch="//")
plt.bar(x + width/2, banned_plot, width, label="Banned", hatch="\\\\")  # 不指定颜色，更偏论文风

plt.xticks(x, scenarios_plot, rotation=45, ha="right", fontsize=9)
plt.ylabel("Number of permissions", fontsize=11)
plt.title("Number of allowed vs. banned permissions per scenario", fontsize=12)
plt.legend(fontsize=9)
plt.tight_layout()
plt.savefig("scenario_policy_bar.png", dpi=300)
plt.show()