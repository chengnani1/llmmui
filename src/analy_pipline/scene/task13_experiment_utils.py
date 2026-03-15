# -*- coding: utf-8 -*-
"""
Utilities for task13 (12+1) scene inference experiments.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List


CONF_LEVELS = {"low", "medium", "high"}


def extract_json_obj(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    text = re.sub(r"^```(?:json)?\n", "", text, flags=re.I)
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except Exception:
                return {}
    return {}


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v).strip()


def normalize_task13_record(
    chain_id: int,
    obj: Dict[str, Any],
    scene_list: List[str],
    rerun: bool,
    rerun_reason: str,
    fallback_task_phrase: str = "",
    fallback_intent: str = "",
    error: str = "",
) -> Dict[str, Any]:
    predicted = _safe_str(obj.get("predicted_scene") or obj.get("top1"), default="其他")
    if predicted not in scene_list:
        predicted = "其他"

    top3_raw = obj.get("scene_top3") or obj.get("top3") or []
    top3 = [x for x in _as_list(top3_raw) if isinstance(x, str) and x in scene_list]
    dedup = []
    seen = set()
    for x in top3:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    top3 = dedup
    if predicted not in top3:
        top3 = [predicted] + top3
    for candidate in scene_list:
        if len(top3) >= 3:
            break
        if candidate not in top3:
            top3.append(candidate)
    top3 = top3[:3]

    task_phrase = _safe_str(obj.get("task_phrase"), default=fallback_task_phrase)
    intent = _safe_str(obj.get("intent"), default=fallback_intent)
    confidence = _safe_str(obj.get("confidence"), default="").lower()
    if confidence not in CONF_LEVELS:
        confidence = "low" if predicted == "其他" else "medium"

    rec = {
        "chain_id": int(chain_id),
        "task_phrase": task_phrase,
        "intent": intent,
        "predicted_scene": predicted,
        "scene_top3": top3,
        "confidence": confidence,
        "rerun": bool(rerun),
        "rerun_reason": _safe_str(rerun_reason),
    }
    if error:
        rec["error"] = _safe_str(error)
    return rec


def should_rerun(record: Dict[str, Any], scene_list: List[str]) -> str:
    predicted = record.get("predicted_scene")
    top3 = record.get("scene_top3") or []
    confidence = record.get("confidence")
    if predicted not in scene_list:
        return "scene_not_in_taxonomy"
    if not predicted:
        return "missing_scene"
    if not isinstance(top3, list) or len(top3) < 3:
        return "scene_top3_incomplete"
    if predicted == "其他" and confidence == "low":
        return "other_low_confidence"
    return ""


def build_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    scene_counter = Counter()
    low_counter = Counter()
    rerun_reason_counter = Counter()
    rerun_scene_counter = Counter()
    phrase_counter = Counter()

    for rec in records:
        scene = str(rec.get("predicted_scene", "其他"))
        conf = str(rec.get("confidence", "low"))
        phrase = str(rec.get("task_phrase", "")).strip()
        rerun = bool(rec.get("rerun", False))
        rerun_reason = str(rec.get("rerun_reason", "")).strip()

        scene_counter[scene] += 1
        if conf == "low":
            low_counter[scene] += 1
        if rerun:
            rerun_scene_counter[scene] += 1
        if rerun_reason:
            rerun_reason_counter[rerun_reason] += 1
        if phrase:
            phrase_counter[phrase] += 1

    scene_distribution = []
    for scene, count in scene_counter.most_common():
        low_count = low_counter[scene]
        rerun_count = rerun_scene_counter[scene]
        scene_distribution.append(
            {
                "scene": scene,
                "count": count,
                "ratio": round(count / total, 4) if total else 0.0,
                "low_conf_count": low_count,
                "low_conf_ratio": round(low_count / count, 4) if count else 0.0,
                "rerun_count": rerun_count,
                "rerun_ratio": round(rerun_count / count, 4) if count else 0.0,
            }
        )

    low_conf_distribution = [
        {"scene": scene, "count": count}
        for scene, count in low_counter.most_common()
    ]
    rerun_distribution = [
        {"reason": reason, "count": count}
        for reason, count in rerun_reason_counter.most_common()
    ]
    top_task_phrases = [
        {"task_phrase": phrase, "count": count}
        for phrase, count in phrase_counter.most_common(20)
    ]

    return {
        "total_chains": total,
        "scene_distribution": scene_distribution,
        "top_task_phrases": top_task_phrases,
        "low_conf_distribution": low_conf_distribution,
        "rerun_distribution": rerun_distribution,
    }
