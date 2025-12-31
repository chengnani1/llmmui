# -*- coding: utf-8 -*-
"""
强化版权限识别核心模块（规则优先，LLM 兜底）
"""

import json
import re
from typing import Dict, Any, List, Optional
import requests # type: ignore
import os

from permission_config import BASE_PERMISSION_TABLE, ALL_DANGEROUS_PERMS

# ========================= Debug 输出目录 =========================
DEBUG_SAVE = True
DEBUG_FILENAME = "results_permission_debug.json"

# ========================= 本地 LLM 配置 =========================
VLLM_URL = "http://localhost:8001/v1/chat/completions"
MODEL_NAME = "Qwen3-VL-30B-A3B"
LLM_TIMEOUT = 40

# ========================= 工具函数 =========================

def _normalize_text(t: str) -> str:
    if not t:
        return ""
    t = re.sub(r"\s+", "", t)
    return t.lower()


def _extract_widget_all_text(w: Dict[str, Any]) -> List[str]:
    """
    从 UI 控件提取所有可能的文本来源（XML + OCR 混合场景稳一点）
    """
    fields = ["text", "content-desc", "description", "hint_text"]
    out: List[str] = []
    for k in fields:
        t = w.get(k)
        if t and isinstance(t, str):
            out.append(t)
    return out


def _collect_frames_widgets(ui_item: Dict[str, Any],
                            top_k_widgets: int = 5,
                            max_frames: int = 5) -> List[Dict[str, Any]]:
    """
    从 before/granting/after 里面收集部分控件，用于 LLM 分析上下文。
    """
    frames: List[Dict[str, Any]] = []

    def _add(tag: str, feature: Optional[Dict[str, Any]]):
        if not feature:
            return
        ws = feature.get("widgets") or []
        if not ws:
            return
        frames.append({"tag": tag, "widgets": ws[:top_k_widgets]})

    _add("before", ui_item.get("ui_before_grant", {}).get("feature"))

    for i, step in enumerate(ui_item.get("ui_granting", [])):
        if len(frames) >= max_frames - 1:
            break
        _add(f"granting_{i}", step.get("feature"))

    _add("after", ui_item.get("ui_after_grant", {}).get("feature"))

    return frames[:max_frames]


def _collect_texts_for_rule(ui_item: Dict[str, Any]) -> List[str]:
    """
    规则匹配用：**重点从 feature["text"] 里收文本**（你的 result.json 已经预处理好的）。
    """
    texts: List[str] = []

    # before
    bf = ui_item.get("ui_before_grant", {}).get("feature", {}) or {}
    t = bf.get("text", "")
    if isinstance(t, list):
        texts.extend([str(x) for x in t if x])
    elif t:
        texts.append(str(t))

    # granting
    for step in ui_item.get("ui_granting", []):
        ft = step.get("feature", {}) or {}
        t = ft.get("text", "")
        if isinstance(t, list):
            texts.extend([str(x) for x in t if x])
        elif t:
            texts.append(str(t))

    # after
    af = ui_item.get("ui_after_grant", {}).get("feature", {}) or {}
    t = af.get("text", "")
    if isinstance(t, list):
        texts.extend([str(x) for x in t if x])
    elif t:
        texts.append(str(t))

    return texts


def _build_llm_full_text(frames: List[Dict[str, Any]]) -> str:
    """
    LLM 用：尽量拼接控件文本，并保留 frame 标签。
    """
    parts: List[str] = []
    for i, f in enumerate(frames):
        texts: List[str] = []
        for w in f["widgets"]:
            texts.extend(_extract_widget_all_text(w))
        if texts:
            parts.append(f"[{f['tag']} STEP {i}] " + " ".join(texts))
    return " ".join(parts)


# ========================= 调试容器 =========================
LLM_DEBUG_LOG: List[Dict[str, Any]] = []


def _call_llm(prompt: str) -> str:
    try:
        resp = requests.post(
            VLLM_URL,
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
        out = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        out = ""
        print(f"[LLM ERROR] {e}")

    LLM_DEBUG_LOG.append({"prompt": prompt, "output": out})
    return out


def _llm_select_permissions(full_text: str,
                            candidate: List[str]) -> List[str]:
    if not candidate:
        return []

    perm_list = "\n".join(f"- {p}" for p in candidate)

    prompt = f"""
你是一名安卓权限分析专家，基于以下控件文本，从候选权限中选择最可能的权限1个或多个。

候选权限：
{perm_list}

控件文本：
{full_text}

严格按照以下JSON格式输出：
{{"permissions": ["PERM1", "PERM2"]}}
"""

    raw = _call_llm(prompt)
    try:
        obj = json.loads(raw)
        out = obj.get("permissions", [])
    except Exception:
        return []

    cand = set(candidate)
    return [p for p in out if p in cand]


# ========================= 主函数 =========================

def recognize_permission(ui_item: Dict[str, Any],
                         vendor: str = "MI",
                         use_llm: bool = True) -> List[str]:
    """
    优先从控件文本中按规则匹配权限；
    匹配不到 / 多条冲突时，再调用 LLM。
    """

    # ---- 1. 取出 vendor 对应的规则表（永远是 dict）----
    vendor_table = BASE_PERMISSION_TABLE.get(vendor)
    if vendor_table is None:
        # 兜底：未知厂商用小米规则
        vendor_table = BASE_PERMISSION_TABLE["MI"]

    # ---- 2. 收集文本（XML + OCR 都在 feature["text"] 里）----
    raw_texts = _collect_texts_for_rule(ui_item)
    all_texts = [_normalize_text(t) for t in raw_texts if t]

    # ---- 3. 规则匹配 ----
    matches = []
    for zh, perms in vendor_table.items():   # ★ 这里 vendor_table 一定是 dict，不会再是 set
        pat = _normalize_text(zh)
        for t in all_texts:
            if pat and pat in t:
                matches.append((zh, perms))
                break

    # 单规则 → 直接返回
    if len(matches) == 1:
        return sorted(set(matches[0][1]))

    # 多规则 → 用 LLM 决策（候选集只在多规则时才进 LLM）
    if len(matches) > 1:
        candidate = sorted({p for _, ps in matches for p in ps})
        if use_llm:
            frames = _collect_frames_widgets(ui_item)
            full_text = _build_llm_full_text(frames) or " ".join(all_texts)
            chosen = _llm_select_permissions(full_text, candidate)
            return chosen or candidate
        return candidate

    # ---- 4. 完全匹配不到 → 走 LLM fallback ----
    if use_llm:
        frames = _collect_frames_widgets(ui_item)
        full_text = _build_llm_full_text(frames) or " ".join(all_texts)
        return _llm_select_permissions(full_text, ALL_DANGEROUS_PERMS)

    return []


def save_llm_debug(app_dir: str):
    if not DEBUG_SAVE:
        return
    path = os.path.join(app_dir, DEBUG_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(LLM_DEBUG_LOG, f, indent=2, ensure_ascii=False)
    print(f"📝 已保存 LLM 调试日志至 {path}")