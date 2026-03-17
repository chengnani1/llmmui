# -*- coding: utf-8 -*-
"""Lightweight scene-conditioned knowledge retrieval for phase3_llm."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

REFINED_SCENE_LIST = [
    "login_verification",
    "profile_or_identity_upload",
    "file_management",
    "file_recovery",
    "system_cleanup",
    "album_selection",
    "media_upload",
    "map_navigation",
    "wifi_scan_or_nearby_devices",
    "content_browsing",
    "customer_support",
    "social_chat_or_share",
]
REFINED_SCENE_SET = set(REFINED_SCENE_LIST)
UI_TO_REFINED_FALLBACK = {
    "账号与身份认证": "login_verification",
    "地图与位置服务": "map_navigation",
    "内容浏览与搜索": "content_browsing",
    "社交互动与通信": "social_chat_or_share",
    "媒体拍摄与扫码": "media_upload",
    "相册选择与媒体上传": "album_selection",
    "商品浏览与消费": "content_browsing",
    "支付与金融交易": "login_verification",
    "文件与数据管理": "file_management",
    "设备清理与系统优化": "system_cleanup",
    "网络连接与设备管理": "wifi_scan_or_nearby_devices",
    "用户反馈与客服": "customer_support",
    "其他": "content_browsing",
}


def _as_text(v: Any, max_len: int = 320) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _norm(v: Any, max_len: int = 120) -> str:
    return _as_text(v, max_len).lower()


def _resolve_scene(refined_scene: str, ui_task_scene: str) -> str:
    rs = _norm(refined_scene, 64)
    if rs in REFINED_SCENE_SET:
        return rs
    return UI_TO_REFINED_FALLBACK.get(_as_text(ui_task_scene, 40), "content_browsing")


def _dedup_text_list(values: Any, max_items: int = 12, max_len: int = 80) -> List[str]:
    out: List[str] = []
    for x in _as_list(values):
        v = _as_text(x, max_len)
        if not v or v in out:
            continue
        out.append(v)
        if len(out) >= max_items:
            break
    return out


def _safe_load_json(path: str) -> Any:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _to_pattern_entry(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    scene = _norm(raw.get("scene"), 64)
    permission = _as_text(raw.get("permission"), 64).upper()
    if not scene or not permission:
        return None
    return {
        "scene": scene,
        "permission": permission,
        "positive_cues": _dedup_text_list(raw.get("positive_cues"), max_items=12, max_len=80),
        "negative_cues": _dedup_text_list(raw.get("negative_cues"), max_items=12, max_len=80),
        "decision_hint": _as_text(raw.get("decision_hint"), 320),
    }


def _to_prior_entry(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    scene = _norm(raw.get("scene"), 64)
    permission = _as_text(raw.get("permission"), 64).upper()
    if not scene or not permission:
        return None
    return {
        "scene": scene,
        "permission": permission,
        "positive_cues": _dedup_text_list(raw.get("positive_cues"), max_items=12, max_len=80),
        "negative_cues": _dedup_text_list(raw.get("negative_cues"), max_items=12, max_len=80),
        "decision_hint": _as_text(raw.get("decision_hint"), 320),
        "source": _as_text(raw.get("source"), 80) or "scene_prior_knowledge",
    }


def _to_case_entry(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    scene = _norm(raw.get("scene"), 64)
    permission = _as_text(raw.get("permission"), 64).upper()
    if not scene or not permission:
        return None
    return {
        "scene": scene,
        "permission": permission,
        "case_type": _norm(raw.get("case_type"), 32) or "risky",
        "evidence": _dedup_text_list(raw.get("evidence"), max_items=12, max_len=80),
        "reason": _as_text(raw.get("reason"), 320),
    }


def _to_skill_entry(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    scene = _norm(raw.get("scene"), 64)
    if not scene:
        return None

    permissions: List[str] = []
    perm_values = raw.get("permissions")
    if isinstance(perm_values, list):
        for x in perm_values:
            p = _as_text(x, 64).upper()
            if p and p not in permissions:
                permissions.append(p)
    single_perm = _as_text(raw.get("permission"), 64).upper()
    if single_perm and single_perm not in permissions:
        permissions.append(single_perm)

    return {
        "scene": scene,
        "permissions": permissions[:4],
        "rule_prior": _norm(raw.get("rule_prior"), 24),
        "regulatory_scene": _as_text(raw.get("regulatory_scene"), 80),
        "skill_name": _as_text(raw.get("skill_name"), 80),
        "skill_type": _norm(raw.get("skill_type"), 32) or "guidance",
        "positive_cues": _dedup_text_list(raw.get("positive_cues"), max_items=14, max_len=80),
        "negative_cues": _dedup_text_list(raw.get("negative_cues"), max_items=14, max_len=80),
        "guidance": _as_text(raw.get("guidance"), 360),
        "usage_note": _as_text(raw.get("usage_note"), 220),
        "origin": _as_text(raw.get("origin"), 80),
    }


def load_pattern_knowledge_entries(path: str) -> List[Dict[str, Any]]:
    raw = _safe_load_json(path)
    rows: List[Any]
    if isinstance(raw, dict):
        rows = raw.get("patterns", [])
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    out: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        entry = _to_pattern_entry(item)
        if entry:
            out.append(entry)
    return out


def load_prior_knowledge_entries(path: str) -> List[Dict[str, Any]]:
    raw = _safe_load_json(path)
    rows: List[Any] = []

    if isinstance(raw, dict) and isinstance(raw.get("prior_patterns"), list):
        rows = raw.get("prior_patterns", [])
    elif isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        # legacy scene_prior_knowledge schema:
        # { "<scene>": { "<permission>": {positive_cues, negative_cues, decision_hint} } }
        for scene_key, perm_map in raw.items():
            if not isinstance(scene_key, str) or not isinstance(perm_map, dict):
                continue
            for perm, pattern in perm_map.items():
                if not isinstance(perm, str) or not isinstance(pattern, dict):
                    continue
                rows.append(
                    {
                        "scene": scene_key,
                        "permission": perm,
                        "positive_cues": pattern.get("positive_cues", []),
                        "negative_cues": pattern.get("negative_cues", []),
                        "decision_hint": pattern.get("decision_hint", ""),
                        "source": "scene_prior_knowledge",
                    }
                )

    out: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        entry = _to_prior_entry(item)
        if entry:
            out.append(entry)
    return out


def load_case_knowledge_entries(path: str) -> List[Dict[str, Any]]:
    raw = _safe_load_json(path)
    rows: List[Any]
    if isinstance(raw, dict):
        rows = raw.get("cases", [])
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    out: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        entry = _to_case_entry(item)
        if entry:
            out.append(entry)
    return out


def load_skill_knowledge_entries(path: str) -> List[Dict[str, Any]]:
    raw = _safe_load_json(path)
    rows: List[Any]
    if isinstance(raw, dict):
        rows = raw.get("skills", [])
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    out: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        entry = _to_skill_entry(item)
        if entry:
            out.append(entry)
    return out


def _build_retrieval_context(
    user_intent: str,
    trigger_action: str,
    page_observation: str,
    visual_evidence: List[Any],
    structured_cues: Optional[Dict[str, List[Any]]],
) -> Tuple[str, Set[str]]:
    cue_dict = _as_dict(structured_cues)
    cue_values: List[str] = []
    for v in cue_dict.values():
        cue_values.extend([_as_text(x, 80) for x in _as_list(v) if _as_text(x, 80)])

    visual_values = [_as_text(x, 80) for x in _as_list(visual_evidence) if _as_text(x, 80)]

    blob_parts = [
        _as_text(user_intent, 320),
        _as_text(trigger_action, 200),
        _as_text(page_observation, 500),
        " ".join(visual_values[:16]),
        " ".join(cue_values[:24]),
    ]
    blob = " ".join([x for x in blob_parts if x]).lower()

    # Keep exact cue/evidence terms for precise overlap checks.
    term_set = {_norm(x, 80) for x in (visual_values + cue_values) if _norm(x, 80)}

    # Add lightweight tokenization for english words; Chinese matching uses substring in blob.
    for tok in re.findall(r"[a-z0-9_\-]{3,}", blob):
        term_set.add(tok)

    return blob, term_set


def _match_terms(candidates: List[str], context_blob: str, context_terms: Set[str]) -> List[str]:
    matched: List[str] = []
    seen_keys: Set[str] = set()
    for cue in candidates:
        key = _norm(cue, 80)
        if not key:
            continue
        if key in seen_keys:
            continue
        if key in context_blob or key in context_terms:
            matched.append(cue)
            seen_keys.add(key)
    return matched


def _sort_ranked(rows: List[Tuple[int, int, Dict[str, Any]]], top_k: int) -> List[Dict[str, Any]]:
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out: List[Dict[str, Any]] = []
    for score, overlap_count, item in rows[: max(top_k, 0)]:
        entry = dict(item)
        entry["retrieval_score"] = score
        entry["retrieval_overlap_count"] = overlap_count
        out.append(entry)
    return out


def _is_compliant_case(case_type: str) -> bool:
    t = _norm(case_type, 32)
    return t in {"compliant", "safe", "expected", "allowed", "ok"}


def retrieve_scene_conditioned_knowledge(
    pattern_entries: List[Dict[str, Any]],
    case_entries: List[Dict[str, Any]],
    refined_scene: str,
    ui_task_scene: str,
    permissions: List[Any],
    user_intent: str,
    trigger_action: str,
    page_observation: str,
    visual_evidence: List[Any],
    prior_entries: Optional[List[Dict[str, Any]]] = None,
    skill_entries: Optional[List[Dict[str, Any]]] = None,
    rule_prior: str = "",
    regulatory_scene: str = "",
    structured_cues: Optional[Dict[str, List[Any]]] = None,
    top_k_patterns: int = 2,
    top_k_cases: int = 2,
    top_k_risky_cases: int = 2,
    top_k_compliant_cases: int = 2,
    top_k_skills: int = 2,
) -> Dict[str, Any]:
    target_scene = _resolve_scene(refined_scene=refined_scene, ui_task_scene=ui_task_scene)
    permission_set = {
        _as_text(x, 64).upper() for x in _as_list(permissions) if _as_text(x, 64)
    }
    normalized_rule_prior = _norm(rule_prior, 24)
    normalized_regulatory_scene = _as_text(regulatory_scene, 80)
    context_blob, context_terms = _build_retrieval_context(
        user_intent=user_intent,
        trigger_action=trigger_action,
        page_observation=page_observation,
        visual_evidence=visual_evidence,
        structured_cues=structured_cues,
    )

    # Step 1: filter by resolved scene first.
    prior_pool = list(prior_entries or [])
    scene_prior_patterns = [x for x in prior_pool if _norm(x.get("scene"), 64) == target_scene]
    scene_patterns = [x for x in pattern_entries if _norm(x.get("scene"), 64) == target_scene]
    scene_cases = [x for x in case_entries if _norm(x.get("scene"), 64) == target_scene]

    # Fallback when scene key is missing in current lightweight KB.
    if not scene_prior_patterns:
        scene_prior_patterns = prior_pool
    if not scene_patterns:
        scene_patterns = list(pattern_entries)
    if not scene_cases:
        scene_cases = list(case_entries)

    # Step 2: filter by permission.
    if permission_set:
        perm_prior_patterns = [x for x in scene_prior_patterns if _as_text(x.get("permission"), 64).upper() in permission_set]
        perm_patterns = [x for x in scene_patterns if _as_text(x.get("permission"), 64).upper() in permission_set]
        perm_cases = [x for x in scene_cases if _as_text(x.get("permission"), 64).upper() in permission_set]
        if perm_prior_patterns:
            scene_prior_patterns = perm_prior_patterns
        if perm_patterns:
            scene_patterns = perm_patterns
        if perm_cases:
            scene_cases = perm_cases

    # Step 3: cue/keyword overlap scoring.
    ranked_prior_patterns: List[Tuple[int, int, Dict[str, Any]]] = []
    for item in scene_prior_patterns:
        matched_pos = _match_terms(_dedup_text_list(item.get("positive_cues"), max_items=12), context_blob, context_terms)
        matched_neg = _match_terms(_dedup_text_list(item.get("negative_cues"), max_items=12), context_blob, context_terms)
        perm_hit = _as_text(item.get("permission"), 64).upper() in permission_set

        score = 0
        if _norm(item.get("scene"), 64) == target_scene:
            score += 5
        if perm_hit:
            score += 4
        score += len(matched_pos) * 3
        score += len(matched_neg) * 2
        overlap_count = len(matched_pos) + len(matched_neg)

        ranked_prior_patterns.append(
            (
                score,
                overlap_count,
                {
                    "scene": _as_text(item.get("scene"), 64),
                    "permission": _as_text(item.get("permission"), 64).upper(),
                    "positive_cues": _dedup_text_list(item.get("positive_cues"), max_items=10),
                    "negative_cues": _dedup_text_list(item.get("negative_cues"), max_items=10),
                    "decision_hint": _as_text(item.get("decision_hint"), 320),
                    "source": _as_text(item.get("source"), 80) or "scene_prior_knowledge",
                    "matched_positive_cues": matched_pos[:6],
                    "matched_negative_cues": matched_neg[:6],
                },
            )
        )

    ranked_patterns: List[Tuple[int, int, Dict[str, Any]]] = []
    for item in scene_patterns:
        matched_pos = _match_terms(_dedup_text_list(item.get("positive_cues"), max_items=12), context_blob, context_terms)
        matched_neg = _match_terms(_dedup_text_list(item.get("negative_cues"), max_items=12), context_blob, context_terms)
        perm_hit = _as_text(item.get("permission"), 64).upper() in permission_set

        score = 0
        if _norm(item.get("scene"), 64) == target_scene:
            score += 5
        if perm_hit:
            score += 4
        score += len(matched_pos) * 3
        score += len(matched_neg) * 2
        overlap_count = len(matched_pos) + len(matched_neg)

        ranked_patterns.append(
            (
                score,
                overlap_count,
                {
                    "scene": _as_text(item.get("scene"), 64),
                    "permission": _as_text(item.get("permission"), 64).upper(),
                    "positive_cues": _dedup_text_list(item.get("positive_cues"), max_items=10),
                    "negative_cues": _dedup_text_list(item.get("negative_cues"), max_items=10),
                    "decision_hint": _as_text(item.get("decision_hint"), 320),
                    "matched_positive_cues": matched_pos[:6],
                    "matched_negative_cues": matched_neg[:6],
                },
            )
        )

    ranked_cases: List[Tuple[int, int, Dict[str, Any]]] = []
    for item in scene_cases:
        evidence = _dedup_text_list(item.get("evidence"), max_items=12)
        matched_evidence = _match_terms(evidence, context_blob, context_terms)
        perm_hit = _as_text(item.get("permission"), 64).upper() in permission_set

        score = 0
        if _norm(item.get("scene"), 64) == target_scene:
            score += 5
        if perm_hit:
            score += 4
        score += len(matched_evidence) * 3
        overlap_count = len(matched_evidence)

        ranked_cases.append(
            (
                score,
                overlap_count,
                {
                    "scene": _as_text(item.get("scene"), 64),
                    "permission": _as_text(item.get("permission"), 64).upper(),
                    "case_type": _norm(item.get("case_type"), 32) or "risky",
                    "evidence": evidence[:10],
                    "reason": _as_text(item.get("reason"), 320),
                    "matched_evidence": matched_evidence[:6],
                },
            )
        )

    ranked_skills: List[Tuple[int, int, Dict[str, Any]]] = []
    skill_pool = list(skill_entries or [])
    scene_skills = [x for x in skill_pool if _norm(x.get("scene"), 64) == target_scene]
    if not scene_skills:
        scene_skills = skill_pool

    if permission_set:
        perm_skills = []
        for x in scene_skills:
            item_perms = {_as_text(p, 64).upper() for p in _as_list(x.get("permissions")) if _as_text(p, 64)}
            if not item_perms or (item_perms & permission_set):
                perm_skills.append(x)
        if perm_skills:
            scene_skills = perm_skills

    for item in scene_skills:
        item_perms = [_as_text(p, 64).upper() for p in _as_list(item.get("permissions")) if _as_text(p, 64)]
        perm_overlap = len(set(item_perms) & permission_set)
        matched_pos = _match_terms(_dedup_text_list(item.get("positive_cues"), max_items=14), context_blob, context_terms)
        matched_neg = _match_terms(_dedup_text_list(item.get("negative_cues"), max_items=14), context_blob, context_terms)

        skill_rule_prior = _norm(item.get("rule_prior"), 24)
        skill_regulatory_scene = _as_text(item.get("regulatory_scene"), 80)
        rule_prior_hit = bool(skill_rule_prior) and skill_rule_prior == normalized_rule_prior
        regulatory_scene_hit = bool(skill_regulatory_scene) and skill_regulatory_scene == normalized_regulatory_scene

        score = 0
        if _norm(item.get("scene"), 64) == target_scene:
            score += 5
        score += min(perm_overlap, 2) * 3
        score += len(matched_pos) * 3
        score += len(matched_neg) * 2
        if rule_prior_hit:
            score += 3
        if regulatory_scene_hit:
            score += 2
        overlap_count = len(matched_pos) + len(matched_neg) + perm_overlap

        ranked_skills.append(
            (
                score,
                overlap_count,
                {
                    "scene": _as_text(item.get("scene"), 64),
                    "permissions": item_perms,
                    "rule_prior": skill_rule_prior,
                    "regulatory_scene": skill_regulatory_scene,
                    "skill_name": _as_text(item.get("skill_name"), 80),
                    "skill_type": _norm(item.get("skill_type"), 32) or "guidance",
                    "guidance": _as_text(item.get("guidance"), 360),
                    "usage_note": _as_text(item.get("usage_note"), 220),
                    "origin": _as_text(item.get("origin"), 80),
                    "matched_positive_cues": matched_pos[:6],
                    "matched_negative_cues": matched_neg[:6],
                },
            )
        )

    retrieved_prior_patterns = _sort_ranked(ranked_prior_patterns, top_k=top_k_patterns)
    retrieved_decision_patterns = _sort_ranked(ranked_patterns, top_k=top_k_patterns)
    retrieved_risky_cases = _sort_ranked(
        [x for x in ranked_cases if not _is_compliant_case((x[2] or {}).get("case_type", ""))],
        top_k=top_k_risky_cases,
    )
    retrieved_compliant_cases = _sort_ranked(
        [x for x in ranked_cases if _is_compliant_case((x[2] or {}).get("case_type", ""))],
        top_k=top_k_compliant_cases,
    )
    retrieved_skill_patterns = _sort_ranked(ranked_skills, top_k=top_k_skills)

    # Compatibility fields for current prompt callers.
    merged_patterns = (retrieved_prior_patterns + retrieved_decision_patterns)[: max(top_k_patterns * 2, 2)]
    merged_cases = (retrieved_risky_cases + retrieved_compliant_cases)[: max(top_k_cases, 2)]

    # Step 4: top-k returned to the single-pass LLM as auxiliary context.
    return {
        "scene_key": target_scene,
        "retrieved_prior_patterns": retrieved_prior_patterns,
        "retrieved_decision_patterns": retrieved_decision_patterns,
        "retrieved_risky_cases": retrieved_risky_cases,
        "retrieved_compliant_cases": retrieved_compliant_cases,
        "retrieved_skill_patterns": retrieved_skill_patterns,
        "retrieved_patterns": merged_patterns,
        "retrieved_cases": merged_cases,
        "retrieved_skills": retrieved_skill_patterns,
    }
