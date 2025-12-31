# -*- coding: utf-8 -*-
import json
import re
import requests  # type: ignore
from typing import Any, Dict, List, Optional

from scene_config_v2 import (
    SCENE_LIST,
    SCENE_PROMPT,
    MAX_WIDGETS,
    MAX_TEXT_LEN,
    MAX_STEPS,
    MAX_TOTAL_LEN,
    MODEL_NAME,
    VLLM_URL,
)

# ==================================================
# 工具：压缩 widgets（text + 权重排序）
# ==================================================

KEYWORD_WEIGHTS = [
    # 支付 / 金融类
    (["支付", "付款", "钱包", "账单", "收银台", "提现", "余额"], 6),
    (["银行卡", "信用卡", "花呗", "借呗", "理财"], 5),

    # 地图 / 打车 / 位置
    (["地图", "定位", "当前位置", "附近", "导航", "路线"], 5),
    (["打车", "网约车", "出租车", "滴滴", "高德打车"], 7),

    # 聊天 / 社交 / 通话
    (["消息", "会话", "聊天", "好友", "私信"], 4),
    (["语音通话", "视频通话", "拨打电话"], 4),

    # 购物 / 订单
    (["加入购物车", "立即购买", "确认订单", "提交订单"], 5),
    (["商品详情", "优惠券", "促销", "秒杀"], 3),

    # 影音 / 游戏 / 娱乐
    (["播放", "暂停", "全屏", "电视剧", "电影", "直播"], 3),
    (["开始游戏", "继续游戏", "等级", "战斗"], 3),
]


def keyword_score(text: str) -> int:
    score = 0
    for kws, w in KEYWORD_WEIGHTS:
        if any(k in text for k in kws):
            score += w
    return score


def widget_score(w: Dict[str, Any]) -> int:
    score = 0
    text = w.get("text", "") or ""
    cls = w.get("class", "") or ""
    rid = w.get("resource-id", "") or ""

    # 有文字本身就比较重要
    if text.strip():
        score += 2
        if len(text) > 4:
            score += 1

    # permission 相关 id
    if "permission" in rid.lower():
        score += 4

    # 按钮 / 文本控件
    if "Text" in cls or "Button" in cls:
        score += 2

    # 关键词额外加权
    score += keyword_score(text)

    return score


def compress_widgets(widget_list: List[Dict[str, Any]], limit: int = MAX_WIDGETS) -> str:
    """
    对 widgets 按权重排序，截断，拼接为字符串
    """
    if not widget_list:
        return ""

    sorted_widgets = sorted(widget_list, key=widget_score, reverse=True)
    top_widgets = sorted_widgets[:limit]

    texts = []
    for w in top_widgets:
        t = (w.get("text") or "").strip()
        if t:
            texts.append(t)

    return "; ".join(texts)


# ==================================================
# 压缩一个 step（文本 + widgets）
# ==================================================
def compress_step(step: Dict[str, Any]) -> str:
    """
    输入：单个 UI step dict（来自 Phase2）
    输出：可输入 LLM 的字符串
    """
    feature = step.get("feature", {})
    text = (feature.get("text") or "")[:MAX_TEXT_LEN]

    widgets = feature.get("widgets") or []
    widgets_str = compress_widgets(widgets)

    return f"[TEXT]\n{text}\n\n[WIDGETS]\n{widgets_str}"


# ==================================================
# 构造 UI 序列 + 元信息
# ==================================================
def compress_ui_sequence(
    ui_item: Dict[str, Any],
    before_step: Optional[Dict[str, Any]],
    granting_steps: List[Dict[str, Any]],
    after_step: Optional[Dict[str, Any]],
) -> str:
    """
    构造最终输入：Meta 信息 + before + granting + after
    并进行长度控制
    """
    seq: List[str] = []

    # -------- Meta 信息：APP / 权限 先验 --------
    meta_parts = []

    pkg = ui_item.get("package") or ui_item.get("pkg")
    if pkg:
        meta_parts.append(f"APP package: {pkg}")

    # 尝试从 ui_item 中拿权限信息（有则用，没有就忽略）
    perms = (
        ui_item.get("true_permissions")
        or ui_item.get("predicted_permissions")
        or ui_item.get("permissions")
        or []
    )
    if isinstance(perms, list) and perms:
        meta_parts.append("Requested permissions: " + ", ".join(perms))

    if meta_parts:
        seq.append("[META]\n" + "\n".join(meta_parts))

    # -------- BEFORE / GRANTING / AFTER --------
    if before_step:
        seq.append("[BEFORE]\n" + compress_step(before_step))

    # granting 步骤往往承载权限解释文本，可视为最重要
    granting_steps = granting_steps[: MAX_STEPS * 2]  # 先粗筛一步，避免过长
    granting_blocks: List[str] = []
    for g in granting_steps:
        granting_blocks.append(compress_step(g))
    if granting_blocks:
        seq.append("[GRANTING]\n" + "\n\n------\n\n".join(granting_blocks))

    if after_step:
        seq.append("[AFTER]\n" + compress_step(after_step))

    combined = "\n\n======\n\n".join(seq)

    # 如果太长，再裁剪一次：保留 before + 前几帧 granting + after
    if len(combined) > MAX_TOTAL_LEN:
        new_seq: List[str] = []
        if meta_parts:
            new_seq.append("[META]\n" + "\n".join(meta_parts))

        if before_step:
            new_seq.append("[BEFORE]\n" + compress_step(before_step))

        top_granting = granting_steps[:MAX_STEPS]
        if top_granting:
            new_seq.append(
                "[GRANTING]\n" + "\n\n------\n\n".join(compress_step(g) for g in top_granting)
            )

        if after_step:
            new_seq.append("[AFTER]\n" + compress_step(after_step))

        combined = "\n\n======\n\n".join(new_seq)
        combined = combined[:MAX_TOTAL_LEN]

    return combined


# ==================================================
# 调用本地 vLLM
# ==================================================
def call_llm(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": SCENE_PROMPT.replace("{FEATURE}", prompt).replace(
                    "{SCENE_LIST}", "\n".join(f"- {s}" for s in SCENE_LIST)
                ),
            }
        ],
        "temperature": 0,
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
# 解析 LLM 输出中的 JSON（更稳健）
# ==================================================
def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """
    尝试从 LLM 输出中抽取 JSON：
    - 自动忽略 ```json ... ``` 包裹
    - 从第一个 { 到最后一个 } 截断解析
    """
    if not text:
        return None

    # 去掉 ```json ``` 之类的包裹
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*", "", text)
    text = re.sub(r"```$", "", text).strip()

    # 尝试直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 尝试截取第一个 { 和最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        try:
            obj = json.loads(snippet)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None

    return None


# ==================================================
# 场景识别主逻辑
# ==================================================
def recognize_scene(ui_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    输入：Phase2 的单条 UI 记录
    输出：
        {
          "top1": "<场景名称>",
          "top3": ["...", "...", "..."]
        }
    """

    before = ui_item.get("ui_before_grant")
    granting = ui_item.get("ui_granting", []) or []
    after = ui_item.get("ui_after_grant")

    if not granting and not before and not after:
        return {"top1": "其他", "top3": ["其他"]}

    ui_str = compress_ui_sequence(ui_item, before, granting, after)
    llm_raw = call_llm(ui_str)

    obj = extract_json_block(llm_raw)
    if not isinstance(obj, dict):
        return {"top1": "其他", "top3": ["其他"]}

    top1 = obj.get("top1") or "其他"
    top3 = obj.get("top3") or ["其他"]

    if not isinstance(top3, list) or not top3:
        top3 = [top1]

    # 兜底：如果 top1 不在 SCENE_LIST，就映射为 "其他"
    if top1 not in SCENE_LIST:
        top1 = "其他"

    # 清洗 top3：保证都在 SCENE_LIST，否则替换为 "其他"
    cleaned_top3: List[str] = []
    for s in top3:
        if isinstance(s, str) and s in SCENE_LIST:
            cleaned_top3.append(s)
    if not cleaned_top3:
        cleaned_top3 = [top1]

    return {
        "top1": top1,
        "top3": cleaned_top3,
    }


# ==================================================
# 批量处理 单个 result.json
# 并在同目录下输出 results_scene_llm.json
# ==================================================
def run_scene_file(input_path: str) -> None:
    """
    输入：
        input_path: Phase2 生成的 result.json 路径
    输出：
        同目录下生成 results_scene_llm.json，格式示例：
        [
          {
            "chain_id": 0,
            "files": {
              "before": "...png",
              "granting": ["...png", "...png"],
              "after": "...png"
            },
            "predicted_scene": "打车服务",
            "scene_candidates": ["打车服务", "地图导航", "其他"]
          },
          ...
        ]
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results: List[Dict[str, Any]] = []

    for idx, item in enumerate(data):
        scene_res = recognize_scene(item)

        before_file = None
        after_file = None
        granting_files: List[str] = []

        if item.get("ui_before_grant"):
            before_file = item["ui_before_grant"].get("file")
        if item.get("ui_after_grant"):
            after_file = item["ui_after_grant"].get("file")
        for g in item.get("ui_granting", []) or []:
            if isinstance(g, dict):
                granting_files.append(g.get("file"))

        chain_id = item.get("chain_id", idx)

        results.append(
            {
                "chain_id": chain_id,
                "files": {
                    "before": before_file,
                    "granting": granting_files,
                    "after": after_file,
                },
                "predicted_scene": scene_res["top1"],
                "scene_candidates": scene_res["top3"],
            }
        )

    out_path = input_path.replace("result.json", "results_scene_llm.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[OK] 场景识别完成：{out_path}")


# ==================================================
# 可选：命令行直接跑
# python scene_recognizer_llm.py /path/to/result.json
# ==================================================
if __name__ == "__main__":
    import sys
    import os

    if len(sys.argv) != 2:
        print("用法: python scene_recognizer_llm.py /path/to/result.json 或 /path/to/dir")
        sys.exit(1)

    target = sys.argv[1]

    if os.path.isdir(target):
        # 如果给的是目录，就在目录下找所有 result.json
        for root, dirs, files in os.walk(target):
            if "result.json" in files:
                path = os.path.join(root, "result.json")
                run_scene_file(path)
    else:
        # 单文件
        run_scene_file(target)