
# -*- coding: utf-8 -*-
"""
run_scene_task13.py

基于固定任务场景 taxonomy 的权限交互链场景识别脚本：
- 读取 processed 目录下各 APK 文件夹中的 chain_*.png
- 将整条权限交互链图片发送给 GPT
- 在固定 taxonomy 中选择最合适的场景
- 输出每条 chain 的 scene / task_phrase / intent / top3 / confidence
- 统计整体场景分布，便于后续人工审核与 ground truth 构建

用法：
python run_scene_task13.py /Users/charon/Downloads/llmui/data/processed
"""

import os
import re
import json
import time
import base64
from io import BytesIO
from typing import Dict, Any, List
from collections import Counter

from tqdm import tqdm
from PIL import Image
from openai import OpenAI, OpenAIError

# =========================
# 配置
# =========================

BASE_URL = "https://xiaoai.plus/v1"
API_KEY = "sk-mN0nqS4Otdeke5sH1MVWKOW29jlXqYcLOdUazBmQIyfGCymI"   # 你的 key
MODEL_NAME = "gpt-4o"

MAX_HEIGHT = 1400
MAX_WIDTH = 2400
MAX_TOKENS = 500
TEMPERATURE = 0

RETRY_TIMES = 3
RETRY_SLEEP = 8
REQUEST_INTERVAL = 1.0

LOW_CONF_TH = 0.6

OUTPUT_FILENAME = "results_scene_task13.json"
SUMMARY_FILENAME = "scene_task13_summary.json"

CHAIN_RE = re.compile(r"chain_(\d+)\.png$")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# =========================
# 固定 taxonomy（收敛后版本）
# =========================

SCENE_LIST = [
    "账号与身份认证",
    "地图与位置服务",
    "内容浏览与搜索",
    "社交互动与通信",
    "媒体拍摄与扫码",
    "相册选择与媒体上传",
    "商品浏览与消费",
    "支付与金融交易",
    "文件与数据管理",
    "设备清理与系统优化",
    "网络连接与设备管理",
    "用户反馈与客服",
    "其他",
]

SCENE_DEFINITIONS = {
    "账号与身份认证": [
        "登录、注册、找回密码、验证码验证、实名校验、账号绑定、扫码登录等身份确认任务。"
    ],
    "地图与位置服务": [
        "查看当前位置、地图展示、附近门店/景点/服务、路线导航、位置发现等与地理位置直接相关的任务。"
    ],
    "内容浏览与搜索": [
        "浏览新闻、帖子、网页、推荐流、搜索内容、查看信息、弱交互内容消费等任务。"
    ],
    "社交互动与通信": [
        "聊天、群聊、私信、语音交流、好友互动、社交发现、语音房等社交与通信任务。"
    ],
    "媒体拍摄与扫码": [
        "拍照、录像、二维码/条码扫描、图像采集、拍摄识别等直接调用相机的任务。"
    ],
    "相册选择与媒体上传": [
        "从相册选择图片/视频、上传头像、上传截图、发送媒体内容、保存或分享图片视频等任务。"
    ],
    "商品浏览与消费": [
        "浏览商品、查看优惠、下单前浏览、服务购买、会员订购等消费类任务。"
    ],
    "支付与金融交易": [
        "支付、转账、钱包、订单结算、金融交易、收付款等资金处理任务。"
    ],
    "文件与数据管理": [
        "浏览文件、恢复文档、导入导出文件、管理 PDF/DOC/ZIP、数据恢复、文件保存等任务。"
    ],
    "设备清理与系统优化": [
        "清理存储空间、缓存清理、垃圾清理、内存优化、设备加速、系统优化等任务。"
    ],
    "网络连接与设备管理": [
        "查看 WiFi、连接网络、网络检测、蓝牙连接、设备配对、设备管理、网络设置等任务。"
    ],
    "用户反馈与客服": [
        "提交意见反馈、问题报告、上传问题截图、联系客服、咨询与售后等任务。"
    ],
    "其他": [
        "仅在页面语义严重不足、无法可靠判断当前任务时使用。"
    ],
}

SCENE_DECISION_RULES = [
    "以用户当前页面任务为最高优先级，不按 APP 名称或行业类别进行分类。",
    "你要识别的是用户原本正在执行的任务，而不是系统权限请求本身。",
    "如果页面任务可以判断，则不要输出“其他”。",
    "“设备清理与系统优化”仅用于明确的清理、缓存、内存、性能优化类任务。",
    "“网络连接与设备管理”用于 WiFi、蓝牙、网络设置、设备连接与管理类任务。",
    "“媒体拍摄与扫码”与“相册选择与媒体上传”需要区分：前者是调用相机/扫码/拍摄，后者是选择已有图片视频进行上传、保存或分享。",
    "“文件与数据管理”优先用于 PDF、文档、压缩包、恢复文件、导入导出等文件对象管理任务。",
    "“内容浏览与搜索”用于信息浏览、推荐内容、搜索结果、网页和弱交互消费，不用于商品支付、地图定位或系统工具。",
]

# =========================
# 图像处理
# =========================

def preprocess_chain_image(image_path: str) -> str:
    """
    保留整条 chain，不裁剪。
    只做最长边限制。
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    scale = min(MAX_WIDTH / w, MAX_HEIGHT / h, 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

# =========================
# Prompt
# =========================

def build_prompt(force_no_other: bool = False) -> str:
    scene_lines = []
    for idx, s in enumerate(SCENE_LIST, 1):
        defs = " ".join(SCENE_DEFINITIONS[s])
        scene_lines.append(f"{idx}. {s}：{defs}")

    rule_lines = [f"{i+1}. {r}" for i, r in enumerate(SCENE_DECISION_RULES)]

    extra_constraint = ""
    if force_no_other:
        extra_constraint = (
            "本次重试中，除非页面信息几乎完全缺失，否则禁止输出“其他”。"
        )

    return f"""
你是一名移动应用权限界面分析专家。

输入是一张“整条权限申请交互链”图片，通常由多个连续页面横向拼接而成，代表：
- 权限申请前页面
- 系统权限弹窗
- 权限处理后页面

你的任务是识别：用户原本正在执行的页面任务。
注意：
- 不要把“权限请求/授权”本身当成场景。
- 不要按 APP 名称或行业做粗分类。
- 必须根据当前页面任务判断。
- 如果能判断任务，就不要输出“其他”。

【可选场景】
{chr(10).join(scene_lines)}

【判定规则】
{chr(10).join(rule_lines)}

{extra_constraint}

请只输出 JSON，不要输出其他任何内容：
{{
  "task_phrase": "一个尽量具体的任务短语，例如 清理手机存储空间 / 登录账号 / 查看附近门店 / 扫码",
  "intent": "一句话说明用户当前目的，不能包含 权限/授权/请求权限 等字样",
  "predicted_scene": "必须从给定场景列表中选择一个",
  "scene_top3": ["候选1", "候选2", "候选3"],
  "confidence": 0.0,
  "other_reason": ""
}}
""".strip()

# =========================
# GPT 调用
# =========================

def extract_json(content: str) -> Dict[str, Any]:
    content = content.strip()
    s = content.find("{")
    e = content.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return {}
    try:
        return json.loads(content[s:e+1])
    except Exception:
        return {}

def validate_scene(scene: str) -> str:
    if scene in SCENE_LIST:
        return scene
    return "其他"

def normalize_top3(top3: Any) -> List[str]:
    if not isinstance(top3, list):
        return []
    cleaned = []
    for x in top3:
        s = str(x).strip()
        if s in SCENE_LIST and s not in cleaned:
            cleaned.append(s)
    return cleaned[:3]

def call_gpt_once(image_path: str, force_no_other: bool = False) -> Dict[str, Any]:
    image_data_url = preprocess_chain_image(image_path)
    prompt = build_prompt(force_no_other=force_no_other)

    for attempt in range(RETRY_TIMES):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            content = resp.choices[0].message.content.strip()
            data = extract_json(content)
            if data:
                data["_raw"] = content
                return data

            if attempt < RETRY_TIMES - 1:
                time.sleep(RETRY_SLEEP)
                continue

            return {"_error": "invalid_json", "_raw": content}

        except OpenAIError as exc:
            if attempt < RETRY_TIMES - 1:
                print(f"⚠ GPT失败 {attempt+1}/{RETRY_TIMES}: {exc}")
                time.sleep(RETRY_SLEEP)
            else:
                return {"_error": str(exc), "_raw": ""}

def call_gpt(image_path: str) -> Dict[str, Any]:
    """
    先正常分类；如果输出“其他”且低置信，则再强制禁止“其他”重试一次。
    """
    first = call_gpt_once(image_path, force_no_other=False)

    if "_error" in first:
        return first

    scene = validate_scene(str(first.get("predicted_scene", "")).strip())
    try:
        conf = float(first.get("confidence", 0.0))
    except Exception:
        conf = 0.0

    need_retry = (scene == "其他" and conf < LOW_CONF_TH)

    if not need_retry:
        first["rerun"] = False
        first["rerun_reason"] = ""
        return first

    second = call_gpt_once(image_path, force_no_other=True)
    if "_error" in second:
        first["rerun"] = True
        first["rerun_reason"] = "other_low_confidence_but_retry_failed"
        return first

    second["rerun"] = True
    second["rerun_reason"] = "other_low_confidence"
    return second

# =========================
# 单 APK 处理
# =========================

def load_existing(out_path: str) -> Dict[int, Dict[str, Any]]:
    if not os.path.exists(out_path):
        return {}
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            rows = json.load(f)
        return {int(r["chain_id"]): r for r in rows}
    except Exception:
        return {}

def normalize_result(chain_id: int, img_name: str, res: Dict[str, Any]) -> Dict[str, Any]:
    task_phrase = str(res.get("task_phrase", "")).strip()
    intent = str(res.get("intent", "")).strip()
    predicted_scene = validate_scene(str(res.get("predicted_scene", "")).strip())
    scene_top3 = normalize_top3(res.get("scene_top3", []))
    other_reason = str(res.get("other_reason", "")).strip()

    try:
        confidence = float(res.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    if not scene_top3:
        scene_top3 = [predicted_scene] if predicted_scene else ["其他"]

    if predicted_scene == "其他" and not other_reason:
        other_reason = "模型无法从当前页面可靠判断任务"

    return {
        "chain_id": chain_id,
        "image_file": img_name,
        "task_phrase": task_phrase,
        "intent": intent,
        "predicted_scene": predicted_scene,
        "scene_top3": scene_top3,
        "confidence": confidence,
        "other_reason": other_reason,
        "rerun": bool(res.get("rerun", False)),
        "rerun_reason": str(res.get("rerun_reason", "")),
        "error": str(res.get("_error", "")),
        "raw_output": str(res.get("_raw", "")),
    }

def process_apk_dir(apk_dir: str) -> List[Dict[str, Any]]:
    images = sorted(
        f for f in os.listdir(apk_dir)
        if CHAIN_RE.match(f)
    )
    if not images:
        return []

    out_path = os.path.join(apk_dir, OUTPUT_FILENAME)
    done = load_existing(out_path)
    results = list(done.values())

    for img in tqdm(images, desc=os.path.basename(apk_dir), ncols=100):
        m = CHAIN_RE.match(img)
        if not m:
            continue
        chain_id = int(m.group(1))

        if chain_id in done:
            continue

        image_path = os.path.join(apk_dir, img)
        res = call_gpt(image_path)
        row = normalize_result(chain_id, img, res)
        results.append(row)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sorted(results, key=lambda x: x["chain_id"]), f, ensure_ascii=False, indent=2)

        time.sleep(REQUEST_INTERVAL)

    return sorted(results, key=lambda x: x["chain_id"])

# =========================
# 汇总统计
# =========================

def summarize(all_results: List[Dict[str, Any]], root: str):
    scene_counter = Counter()
    task_counter = Counter()
    low_conf_counter = Counter()
    rerun_counter = Counter()
    other_reason_counter = Counter()

    total = len(all_results)

    for r in all_results:
        scene = r.get("predicted_scene", "其他") or "其他"
        task = r.get("task_phrase", "").strip() or "EMPTY"
        conf = float(r.get("confidence", 0.0) or 0.0)
        rerun = bool(r.get("rerun", False))
        other_reason = r.get("other_reason", "").strip()

        scene_counter[scene] += 1
        task_counter[task] += 1
        if conf < LOW_CONF_TH:
            low_conf_counter[scene] += 1
        if rerun:
            rerun_counter[scene] += 1
        if scene == "其他" and other_reason:
            other_reason_counter[other_reason] += 1

    summary = {
        "total_chains": total,
        "scene_distribution": [],
        "top_task_phrases": [],
        "other_reasons": [],
    }

    for scene in SCENE_LIST:
        count = scene_counter.get(scene, 0)
        summary["scene_distribution"].append({
            "scene": scene,
            "count": count,
            "ratio": round(count / total, 4) if total else 0.0,
            "low_conf_count": low_conf_counter.get(scene, 0),
            "low_conf_ratio": round(low_conf_counter.get(scene, 0) / count, 4) if count else 0.0,
            "rerun_count": rerun_counter.get(scene, 0),
            "rerun_ratio": round(rerun_counter.get(scene, 0) / count, 4) if count else 0.0,
        })

    summary["scene_distribution"].sort(key=lambda x: -x["count"])

    for task, count in task_counter.most_common(100):
        summary["top_task_phrases"].append({
            "task_phrase": task,
            "count": count,
            "ratio": round(count / total, 4) if total else 0.0,
        })

    for reason, count in other_reason_counter.most_common():
        summary["other_reasons"].append({
            "reason": reason,
            "count": count,
            "ratio": round(count / total, 4) if total else 0.0,
        })

    out_path = os.path.join(root, SUMMARY_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n✔ 汇总统计完成: {out_path}")

# =========================
# 批量运行
# =========================

def run(processed_root: str):
    all_results = []

    for d in sorted(os.listdir(processed_root)):
        apk_dir = os.path.join(processed_root, d)
        if not os.path.isdir(apk_dir):
            continue
        all_results.extend(process_apk_dir(apk_dir))

    summarize(all_results, processed_root)

# =========================
# CLI
# =========================

if __name__ == "__main__":
    import sys

    default_root = "/Users/charon/Downloads/llmui/data/processed"
    processed_root = sys.argv[1] if len(sys.argv) > 1 else default_root

    if not os.path.isdir(processed_root):
        raise SystemExit(f"目录不存在: {processed_root}")

    run(processed_root)