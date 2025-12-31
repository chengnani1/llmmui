import sys
import time
import os
from tqdm import tqdm # type: ignore

import configs.config as config
import src.utils.utils as utils
from scripts.data_analyze import DataAnalyzeAgent
from src.data.data_collect import DataCollectAgent
from data_process_v1 import DataProcessAgent


# =========================================================
# Utils
# =========================================================
def list_valid_apks(directory):
    files = os.listdir(directory)
    apk_files = []

    for f in files:
        full_path = os.path.join(directory, f)
        if f.endswith(".apk") and not f.startswith("._") and os.path.getsize(full_path) > 1024:
            apk_files.append(f)

    return apk_files


def list_raw_dirs(directory):
    dirs = []
    for d in os.listdir(directory):
        full = os.path.join(directory, d)
        if os.path.isdir(full) and d.startswith("fastbot-"):
            dirs.append(full)
    return dirs


def list_processed_dirs(directory):
    dirs = []
    for d in os.listdir(directory):
        full = os.path.join(directory, d)
        if os.path.isdir(full):
            dirs.append(full)
    return dirs


# =========================================================
# Main
# =========================================================
def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py [path] [mode]")
        print("mode = collect_only / process_only / analyze_only / full")
        return

    target_path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "full"
    mode = mode.lower()

    # =====================================================
    # MODE: Phase1 Only
    # =====================================================
    if mode == "collect_only":
        print("[INFO] Running: Phase1 collect_only")

        if os.path.isdir(target_path):
            apk_files = list_valid_apks(target_path)

            print(f"[INFO] Found {len(apk_files)} APKs.")
            for apk in tqdm(apk_files, desc="Phase1 Collecting"):
                full_apk_path = os.path.join(target_path, apk)
                try:
                    DataCollectAgent(full_apk_path, time=config.TIME_LIMIT).run(skip_if_result_exist=True)
                except Exception as e:
                    print(f"[ERROR] Phase1 failed for {apk}: {e}")
        else:
            DataCollectAgent(target_path, time=config.TIME_LIMIT).run(skip_if_result_exist=True)

        print("[INFO] Phase1 complete.")
        return

    # =====================================================
    # MODE: Phase2 Only
    # =====================================================
    if mode == "process_only":
        print("[INFO] Running: Phase2 process_only")

        if os.path.isdir(target_path):
            raw_dirs = list_raw_dirs(target_path)

            print(f"[INFO] Found {len(raw_dirs)} raw dirs.")
            for raw_dir in tqdm(raw_dirs, desc="Phase2 Processing"):
                try:
                    DataProcessAgent(raw_dir).run(skip_if_result_exist=True)
                except Exception as e:
                    print(f"[ERROR] Phase2 failed for {raw_dir}: {e}")
        else:
            DataProcessAgent(target_path).run(skip_if_result_exist=True)

        print("[INFO] Phase2 complete.")
        return

    # =====================================================
    # MODE: Phase3 Only
    # =====================================================
    if mode == "analyze_only":
        print("[INFO] Running: Phase3 analyze_only")

        if os.path.isdir(target_path):
            processed_dirs = list_processed_dirs(target_path)

            print(f"[INFO] Found {len(processed_dirs)} processed dirs.")
            for p_dir in tqdm(processed_dirs, desc="Phase3 Analyzing"):
                try:
                    DataAnalyzeAgent(p_dir, use_api=False).run(skip_if_result_exist=True)
                except Exception as e:
                    print(f"[ERROR] Phase3 failed for {p_dir}: {e}")
        else:
            DataAnalyzeAgent(target_path, use_api=False).run(skip_if_result_exist=True)

        print("[INFO] Phase3 complete.")
        return

    # =====================================================
    # MODE: full pipeline
    # =====================================================
    if mode == "full":
        print("[INFO] Running: full pipeline")

        if os.path.isdir(target_path):
            apk_files = list_valid_apks(target_path)

            print(f"[INFO] Found {len(apk_files)} APKs.")
            for apk in tqdm(apk_files, desc="Running Full Pipeline"):
                run_full(os.path.join(target_path, apk))
        else:
            run_full(target_path)

        return


# =========================================================
# Run full pipeline for one APK
# =========================================================
def run_full(apk_path):
    start_time = time.time()
    print(f"\n[INFO] Running FULL pipeline for {apk_path}")

    # Phase1 ---------------
    collector = DataCollectAgent(apk_path, time=config.TIME_LIMIT)
    collector.run(skip_if_result_exist=True)

    # Prepare paths
    raw_dir = os.path.join(config.DATA_RAW_DIR, collector.fastbot_output_dir)
    processed_dir = os.path.join(config.DATA_PROCESSED_DIR, collector.fastbot_output_dir)

    # Phase2 ---------------
    DataProcessAgent(raw_dir).run(skip_if_result_exist=True)

    # Phase3 ---------------
    DataAnalyzeAgent(processed_dir, use_api=False).run(skip_if_result_exist=True)

    duration = time.time() - start_time
    print(f"[INFO] Done. Total time {duration:.2f}s")


if __name__ == "__main__":
    main()