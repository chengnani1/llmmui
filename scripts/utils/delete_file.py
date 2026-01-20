import os

BASE_DIR = "/Users/charon/Downloads/code/llmui/llmmui/data/processed"
file_name = "results_scene_vllm.json"
for root, dirs, files in os.walk(BASE_DIR):
    if file_name in files:
        file_path = os.path.join(root, file_name)
        try:
            os.remove(file_path)
            print(f"Deleted: {file_path}")
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")