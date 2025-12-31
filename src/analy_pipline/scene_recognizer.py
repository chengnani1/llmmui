# -*- coding: utf-8 -*-
"""
scene_recognizer_v4.py
在 v3 的基础上加入：
- predicted_permissions 注入
- 权限约束逻辑写入 META
- top5 输出
- 场景 priors（存储 -> 文件管理；相机 -> 拍摄美化；无权限 -> 实用工具）
"""

import json
import re
import requests
from typing import Any, Dict, List, Optional

from scene_config import (
    SCENE_LIST,
    SCENE_PROMPT,
    MAX_WIDGETS,
    MAX_TEXT_LEN,
    MAX_STEPS,
    MAX_TOTAL_LEN,
    MODEL_NAME,
    VLLM_URL,
)

# ================================
# 额外加入权限 → 场景先验映射
# ================================

PERMISSION_SCENE_PRIORS = {
    # 文件类
    "READ_EXTERNAL_STORAGE": "文件管理",
    "WRITE_EXTERNAL_STORAGE": "文件管理",
    "READ_MEDIA_IMAGES": "文件管理",
    "READ_MEDIA_VIDEO": "文件管理",
    # 相机类
    "CAMERA": "拍摄美化",
    # 位置类
    "ACCESS_FINE_LOCATION": "地图导航",
    "ACCESS_COARSE_LOCATION": "地图导航",
}

# ================================
# 原 v3 的关键代码全部保留
# ================================

KEYWORD_WEIGHTS = [
    (["支付", "付款", "钱包", "账单", "收银台", "提现", "余额"], 6),
    (["银行卡", "信用卡", "花呗", "借呗", "理财"], 5),
    (["地图", "定位", "当前位置", "附近", "导航", "路线"], 5),
    (["打车", "网约车", "出租车", "滴滴", "高德打车"], 7),
    (["消息", "会话", "聊天", "好友", "私信"], 4),
    (["语音通话", "视频通话", "拨打电话"], 4),
    (["加入购物车", "立即购买", "确认订单", "提交订单"], 5),
    (["商品详情", "优惠券", "促销", "秒杀"], 3),
    (["播放", "暂停", "全屏", "电视剧", "电影", "直播"], 3),
    (["开始游戏", "继续游戏", "等级", "战斗"], 3),
    (["登录", "注册", "验证码", "账号", "密码"], 4),
    (["文件", "相册", "照片", "图片", "视频", "存储"], 4),
    (["隐私", "个人信息", "手机号", "身份证", "实名认证"], 5),
]

def keyword_score(text: str) -> int:
    score = 0
    for kws, w in KEYWORD_WEIGHTS:
        if any(k in text for k in kws):
            score += w
    return score


def widget_score(w: Dict[str, Any]) -> int:
    score = 0
    text = (w.get("text") or "").strip()
    cls = w.get("class") or ""
    rid = w.get("resource-id") or ""

    if text:
        score += 2
        if len(text) > 4:
            score += 1

    if "permission" in rid.lower():
        score += 4

    if "Text" in cls or "Button" in cls:
        score += 2

    score += keyword_score(text)
    return score


def compress_widgets(widget_list: List[Dict[str, Any]], limit: int = MAX_WIDGETS) -> str:
    if not widget_list:
        return ""
    sorted_widgets = sorted(widget_list, key=widget_score, reverse=True)
    top_widgets = sorted_widgets[:limit]
    texts = [(w.get("text") or "").strip() for w in top_widgets if (w.get("text") or "").strip()]
    return "; ".join(texts)


def compress_step(step: Dict[str, Any]) -> str:
    feature = step.get("feature", {})
    text = (feature.get("text") or "")[:MAX_TEXT_LEN]
    widgets = feature.get("widgets") or []
    widgets_str = compress_widgets(widgets)
    return f"[TEXT]\n{text}\n\n[WIDGETS]\n{widgets_str}"


def compress_ui_sequence(ui_item, before, granting, after) -> str:
    seq = []
    meta_parts = []

    pkg = ui_item.get("package") or ui_item.get("pkg")
    if pkg:
        meta_parts.append(f"APP package: {pkg}")

    perms = ui_item.get("predicted_permissions") or ui_item.get("true_permissions") or []
    if perms:
        meta_parts.append("Requested permissions: " + ", ".join(perms))

        # 权限 → 场景提示写入 meta，提高模型稳定性
        prior_hints = []
        for p in perms:
            if p in PERMISSION_SCENE_PRIORS:
                prior_hints.append(PERMISSION_SCENE_PRIORS[p])
        if prior_hints:
            meta_parts.append("Likely scenes based on permissions: " + ", ".join(set(prior_hints)))

    if meta_parts:
        seq.append("[META]\n" + "\n".join(meta_parts))

    # ==== UI 内容 ====
    if before:
        seq.append("[BEFORE]\n" + compress_step(before))

    granting = granting[: MAX_STEPS * 2]
    if granting:
        blocks = [compress_step(g) for g in granting]
        seq.append("[GRANTING]\n" + "\n\n------\n\n".join(blocks))

    if after:
        seq.append("[AFTER]\n" + compress_step(after))

    combined = "\n\n======\n\n".join(seq)
    return combined[:MAX_TOTAL_LEN]


def call_llm(feature_str: str) -> str:
    scene_list_str = "\n".join(f"- {s}" for s in SCENE_LIST)
    prompt = SCENE_PROMPT.format(FEATURE=feature_str, SCENE_LIST=scene_list_str)

    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }

    try:
        r = requests.post(VLLM_URL, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("LLM 调用失败：", e)
        return ""


def extract_json_block(text: str):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*", "", text)
    text = re.sub(r"```$", "", text).strip()

    # 直接解析
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except:
        pass

    # 截取 { ... }
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            snippet = json.loads(text[s:e+1])
            return snippet if isinstance(snippet, dict) else None
        except:
            return None
    return None


# ================================
# 核心识别逻辑（加入 top5 + 权限先验）
# ================================
def recognize_scene(ui_item: Dict[str, Any]) -> Dict[str, Any]:
    before = ui_item.get("ui_before_grant")
    granting = ui_item.get("ui_granting", []) or []
    after = ui_item.get("ui_after_grant")

    if not before and not granting and not after:
        return {
            "intent": "无法识别",
            "top1": "其他",
            "top3": ["其他"],
            "top5": ["其他"],
            "top7": ["其他"],
        }

    ui_str = compress_ui_sequence(ui_item, before, granting, after)
    llm_raw = call_llm(ui_str)
    obj = extract_json_block(llm_raw) or {}

    intent = obj.get("intent") or "未能可靠提取功能意图"
    top1 = obj.get("top1") or "其他"
    top3 = obj.get("top3") or []
    top7 = obj.get("top7") or []
    top5 = obj.get("top5") or []

    # 确保合法
    def clean(lst, k):
        out = []
        seen = set()
        for s in lst:
            if isinstance(s, str) and s in SCENE_LIST and s not in seen:
                out.append(s)
                seen.add(s)
        if not out:
            out = [k]
        return out

    top1 = top1 if top1 in SCENE_LIST else "其他"
    top3 = clean(top3, top1)[:3]
    top5 = clean(top5, top1)[:5]
    top7 = clean(top7, top1)[:7]

    # 权限强 prior：如果 top1 不符合权限特征，自动修正候选
    perms = ui_item.get("predicted_permissions") or []
    for p in perms:
        if p in PERMISSION_SCENE_PRIORS:
            expected = PERMISSION_SCENE_PRIORS[p]
            if expected not in top3:
                top3.append(expected)
            if expected not in top5:
                top5.append(expected)
            if expected not in top7:
                top7.append(expected)

    return {
        "intent": intent,
        "top1": top1,
        "top3": top3,
        "top5": top5,
        "top7": top7,
    }