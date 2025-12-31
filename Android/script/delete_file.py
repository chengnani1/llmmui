import os

BASE_DIR = "/Volumes/Charon/data/code/llm_ui/code/data/version2.11.5/processed/"

for root, dirs, files in os.walk(BASE_DIR):
    if "results_permission_debug.json" in files:
        file_path = os.path.join(root, "results_permission_debug.json")
        try:
            os.remove(file_path)
            print(f"Deleted: {file_path}")
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")