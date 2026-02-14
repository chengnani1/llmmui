

import matplotlib.pyplot as plt
import numpy as np

labels = [
    "Live-streaming", "Music", "Cleaning", "Browser",
    "Sys/WiFi", "Camera/QR", "Social", "Input", "Finance"
]

sizes = [35, 30, 25, 20, 20, 10, 10, 6, 8]

colors = "#4E79A7"  # Single professional color

plt.figure(figsize=(9, 5))
x = np.arange(len(labels))

plt.bar(x, sizes, color=colors)
plt.xticks(x, labels, rotation=45, ha="right", fontsize=10)
plt.ylabel("Number of Apps", fontsize=12)
plt.title("Dataset Category Distribution (Bar Chart)", fontsize=14)

plt.tight_layout()
plt.savefig("dataset_bar_chart.png", dpi=300)
plt.show()