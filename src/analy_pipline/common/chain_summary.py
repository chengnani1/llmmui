# -*- coding: utf-8 -*-
"""
Build compact chain summaries for LLM prompts.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from utils.validators import validate_result_json_chains


def _safe_text(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _collect_widgets(ui_part: Dict[str, Any], max_widgets: int = 8) -> List[str]:
    feature = ui_part.get("feature", {}) if isinstance(ui_part, dict) else {}
    widgets = feature.get("widgets", []) if isinstance(feature, dict) else []
    if not isinstance(widgets, list):
        return []

    ranked = []
    for w in widgets:
        if not isinstance(w, dict):
            continue
        txt = _safe_text(w.get("text"))
        if not txt:
            continue
        score = w.get("score", 0)
        try:
            score = float(score)
        except Exception:
            score = 0
        ranked.append((score, txt))
    ranked.sort(key=lambda x: x[0], reverse=True)

    out: List[str] = []
    seen = set()
    for _, txt in ranked:
        if txt in seen:
            continue
        seen.add(txt)
        out.append(txt)
        if len(out) >= max_widgets:
            break
    return out


def build_chain_summary(
    chain: Dict[str, Any],
    permissions: List[str] | None = None,
    text_limit: int = 240,
    max_widgets: int = 8,
) -> Dict[str, Any]:
    before = chain.get("ui_before_grant", {}) if isinstance(chain, dict) else {}
    granting = chain.get("ui_granting", []) if isinstance(chain, dict) else []
    after = chain.get("ui_after_grant", {}) if isinstance(chain, dict) else {}

    before_text = _truncate(_safe_text(before.get("feature", {}).get("text", "")), text_limit)
    after_text = _truncate(_safe_text(after.get("feature", {}).get("text", "")), text_limit)

    granting_texts = []
    for g in granting if isinstance(granting, list) else []:
        g_text = _safe_text(g.get("feature", {}).get("text", ""))
        if g_text:
            granting_texts.append(g_text)
    granting_text = _truncate(" | ".join(granting_texts), text_limit)

    widgets = []
    widgets.extend(_collect_widgets(before, max_widgets=max_widgets))
    for g in granting if isinstance(granting, list) else []:
        widgets.extend(_collect_widgets(g, max_widgets=max_widgets))
    widgets.extend(_collect_widgets(after, max_widgets=max_widgets))

    dedup_widgets = []
    seen = set()
    for w in widgets:
        if w in seen:
            continue
        seen.add(w)
        dedup_widgets.append(w)
        if len(dedup_widgets) >= max_widgets:
            break

    return {
        "chain_id": chain.get("chain_id", -1),
        "chain_summary": {
            "before_text": before_text,
            "granting_text": granting_text,
            "after_text": after_text,
            "top_widgets": dedup_widgets,
            "permissions": permissions or [],
        },
    }


def load_chain_summary_map(result_json_path: str, permissions_map: Dict[int, List[str]] | None = None) -> Dict[int, Dict[str, Any]]:
    with open(result_json_path, "r", encoding="utf-8") as f:
        chains = validate_result_json_chains(json.load(f))

    out: Dict[int, Dict[str, Any]] = {}
    for idx, chain in enumerate(chains):
        try:
            chain_id = int(chain.get("chain_id", idx))
        except Exception:
            chain_id = idx
        perms = (permissions_map or {}).get(chain_id, [])
        out[chain_id] = build_chain_summary(chain, permissions=perms)
    return out
