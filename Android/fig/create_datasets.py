# import matplotlib.pyplot as plt

# labels = [
#     "Live-streaming / Video",
#     "Music / K-song",
#     "Cleaning Utilities",
#     "Browsers / Search Tools",
#     "System Tools / WiFi",
#     "Camera / QR / Flash",
#     "Social / Messaging",
#     "Input Methods",
#     "Finance / Productivity"
# ]

# sizes = [35, 30, 25, 20, 20, 10, 10, 6, 8]

# colors = [
#     "#4E79A7", "#F28E2B", "#59A14F", "#E15759",
#     "#76B7B2", "#EDC948", "#B07AA1", "#FF9DA7",
#     "#9C755F"
# ]

# plt.figure(figsize=(8, 6))

# # Main pie chart
# patches, texts, autotexts = plt.pie(
#     sizes,
#     colors=colors,
#     autopct='%1.1f%%',
#     startangle=140,
#     pctdistance=0.8,
#     textprops={'fontsize': 10}
# )

# # Legend outside
# plt.legend(
#     patches,
#     labels,
#     loc="center left",
#     bbox_to_anchor=(1, 0.5),
#     fontsize=10
# )

# plt.title("Dataset Category Distribution", fontsize=14)
# plt.tight_layout()
# plt.savefig("dataset_pie_chart_pro.png", dpi=300, bbox_inches="tight")
# plt.show()


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