import os

root = "/Volumes/Charon/data/work/llm/code/data/lable_app"
log_path = "app_list.log"

apk_files = []

with open(log_path, "w", encoding="utf-8") as f:
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.lower().endswith(".apk") and not name.startswith("."):
                full_path = os.path.join(name)
                f.write(full_path + "\n")
                apk_files.append(full_path)

print(f"Found {len(apk_files)} APKs. Saved to {log_path}")