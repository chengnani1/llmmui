# -*- coding: utf-8 -*-
import json
import requests #type: ignore
from scene_config_v2 import SCENE_LIST, SCENE_PROMPT,MAX_WIDGETS,MAX_TEXT_LEN,MAX_STEPS,MAX_TOTAL_LEN,MODEL_NAME,VLLM_URL

# ==================================================
# 工具：压缩 widgets（text + 权重排序）
# ==================================================
def compress_widgets(widget_list, limit=MAX_WIDGETS):
    """
    对 widgets 按权重排序，截断，拼接为字符串
    """
    if not widget_list:
        return ""

    def widget_score(w):
        score = 0
        text = w.get("text", "")
        cls = w.get("class", "")
        rid = w.get("resource-id", "")

        if text:
            score += 2
            if len(text) > 4:
                score += 1
        if "permission" in rid:
            score += 3
        if "Text" in cls or "Button" in cls:
            score += 2
        return score

    sorted_widgets = sorted(widget_list, key=widget_score, reverse=True)
    top_widgets = sorted_widgets[:limit]

    return "; ".join([w["text"] for w in top_widgets if w["text"]])


# ==================================================
# 压缩一个 step（文本 + widgets）
# ==================================================
def compress_step(step):
    """
    输入：单个 UI step dict（来自 Phase2）
    输出：可输入 LLM 的字符串
    """
    text = step["feature"]["text"][:MAX_TEXT_LEN]
    widgets = compress_widgets(step["feature"]["widgets"])
    return f"[TEXT] {text}\n[WIDGETS] {widgets}"


# ==================================================
# 压缩整个 UI sequence
# ==================================================
def compress_ui_sequence(before_step, granting_steps, after_step):
    """
    构造最终输入：before + granting + after
    并进行长度控制
    """

    seq = []

    # 1. BEFORE（权重最低，但有用）
    if before_step:
        seq.append(compress_step(before_step))

    # 2. GRANTING（最关键）
    for g in granting_steps[:MAX_STEPS]:
        seq.append(compress_step(g))

    # 3. AFTER（辅助信号）
    if after_step:
        seq.append(compress_step(after_step))

    combined = "\n\n------\n\n".join(seq)

    # 4. 总长度超限 → 自动裁剪 granting（保留最重要的前几个）
    if len(combined) > MAX_TOTAL_LEN:
        # 优先保留：before + 前 3 个 granting + after
        new_seq = []
        if before_step:
            new_seq.append(compress_step(before_step))

        new_seq.extend([compress_step(g) for g in granting_steps[:3]])

        if after_step:
            new_seq.append(compress_step(after_step))

        combined = "\n\n------\n\n".join(new_seq)
        combined = combined[:MAX_TOTAL_LEN]

    return combined


# ==================================================
# 调用本地 vLLM
# ==================================================
def call_llm(prompt):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0
    }

    try:
        r = requests.post(VLLM_URL, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print("LLM 调用错误：", e)
        return ""


# ==================================================
# 场景识别主逻辑
# ==================================================
def recognize_scene(ui_item):
    """
    输入：Phase2 的单条 UI 记录
    输出：Top1 + Top3 场景
    """

    before = ui_item.get("ui_before_grant")
    granting = ui_item.get("ui_granting", [])
    after = ui_item.get("ui_after_grant")

    if not granting and not before and not after:
        return {"top1": "其他", "top3": ["其他"]}

    # 构造 LLM 输入序列
    ui_str = compress_ui_sequence(before, granting, after)

    # 构造 prompt（已安全处理）
    prompt = SCENE_PROMPT.replace("{FEATURE}", ui_str)\
                         .replace("{SCENE_LIST}", "\n".join([f"- {s}" for s in SCENE_LIST]))

    llm_output = call_llm(prompt)

    # 尝试解析 JSON
    try:
        obj = json.loads(llm_output)
        return {
            "top1": obj.get("top1", "其他"),
            "top3": obj.get("top3", ["其他"])
        }
    except:
        return {"top1": "其他", "top3": ["其他"]}


# ==================================================
# 批量处理 单个 result.json
# ==================================================
def run_scene_file(input_path):
    data = json.load(open(input_path, "r"))

    results = []
    for item in data:
        res = recognize_scene(item)
        results.append({
            "files": {
                "before": item["ui_before_grant"]["file"],
                "granting": [g["file"] for g in item["ui_granting"]],
                "after": item["ui_after_grant"]["file"]
            },
            "scene": res
        })

    out_path = input_path.replace("result.json", "results_scene.json")
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=2)
    print(f"[OK] 场景识别完成：{out_path}")