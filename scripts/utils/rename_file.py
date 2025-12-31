import os

ROOT_DIR = "/Users/charon/Downloads/llmui/data/processed"

OLD_NAME = "labels.json"      # 原文件名
NEW_NAME = "labels_permission.json"      # 新文件名

for app in sorted(os.listdir(ROOT_DIR)):
    app_dir = os.path.join(ROOT_DIR, app)
    if not os.path.isdir(app_dir):
        continue

    old_path = os.path.join(app_dir, OLD_NAME)
    new_path = os.path.join(app_dir, NEW_NAME)

    if os.path.exists(old_path):
        os.rename(old_path, new_path)
        print(f"✅ {app}: {OLD_NAME} → {NEW_NAME}")
    else:
        print(f"⚠️ {app}: {OLD_NAME} not found")