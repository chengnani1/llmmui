import os
import json

PROCESSED_DIR = "/Volumes/Charon/data/work/llm/code/data/version2.11.5/processed"
OUTPUT_FILE = "unrecognized_chains.json"


def normalize_permission(item):
    """统一返回权限列表"""
    if "permissions" in item:
        return item["permissions"]
    if "predicted_permission" in item:
        return item["predicted_permission"]
    return []

def process_app(app_path):
    result_file = os.path.join(app_path, "result.json")
    perm_file = os.path.join(app_path, "results_permission.json")

    if not os.path.exists(result_file):
        return None

    # 读取 result.json
    with open(result_file, "r", encoding="utf-8") as f:
        result_chains = json.load(f)

    # 读取权限结果
    perm_chains = []
    if os.path.exists(perm_file):
        with open(perm_file, "r", encoding="utf-8") as f:
            perm_chains = json.load(f)

    # 建立 chain_id → permission_item 的映射
    perm_map = {item.get("chain_id"): item for item in perm_chains}

    unrecognized = []
    recognized = 0

    for chain in result_chains:
        cid = chain.get("chain_id")

        # ① chain_id 缺失 —— 必须计入未识别
        if cid is None:
            unrecognized.append({
                "chain_id": None,
                "raw_item": chain,
                "reason": "missing_chain_id"
            })
            continue

        # ② chain_id 找不到对应权限 —— 未识别
        if cid not in perm_map:
            unrecognized.append({
                "chain_id": cid,
                "raw_item": chain,
                "reason": "not_found_in_results_permission"
            })
            continue

        # ③ 有权限项但为空 —— 未识别
        perm_item = perm_map[cid]
        perms = normalize_permission(perm_item)

        if not perms:
            unrecognized.append({
                "chain_id": cid,
                "raw_item": perm_item,
                "reason": "empty_permission"
            })
        else:
            recognized += 1

    return len(result_chains), recognized, unrecognized

def batch_process(processed_dir):
    result_all = {}
    total = 0
    recognized = 0

    for name in os.listdir(processed_dir):
        sub = os.path.join(processed_dir, name)
        if not os.path.isdir(sub):
            continue
        if not name.startswith("fastbot-"):
            continue

        r = process_app(sub)
        if not r:
            continue
        
        t, rec, unrec = r
        total += t
        recognized += rec

        print(f"{name}  总链={t}  识别={rec}  未识别={len(unrec)}")

        if unrec:
            result_all[name] = unrec

    print("\n========== 总体统计 ==========")
    print("所有链条总数:", total)
    print("识别链条数:", recognized)
    print("识别率: %.2f%%" % (recognized / total * 100))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result_all, f, ensure_ascii=False, indent=4)

    print("未识别链条已写入", OUTPUT_FILE)


if __name__ == "__main__":
    batch_process(PROCESSED_DIR)