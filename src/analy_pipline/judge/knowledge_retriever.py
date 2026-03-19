# -*- coding: utf-8 -*-
"""Scene-conditioned structured knowledge retrieval for phase3_v2."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

REFINED_SCENE_LIST = [
    "login_verification",
    "profile_or_identity_update",
    "file_management",
    "file_recovery",
    "system_cleanup",
    "album_selection",
    "media_upload",
    "media_capture_or_recording",
    "map_navigation",
    "nearby_service_or_wifi_scan",
    "content_browsing",
    "customer_support",
    "social_chat_or_share",
    "other",
]
REFINED_SCENE_SET = set(REFINED_SCENE_LIST)
REFINED_SCENE_ALIASES = {
    "profile_or_identity_upload": "profile_or_identity_update",
    "wifi_scan_or_nearby_devices": "nearby_service_or_wifi_scan",
}
UI_TO_REFINED_FALLBACK = {
    "账号与身份认证": "login_verification",
    "地图与位置服务": "map_navigation",
    "内容浏览与搜索": "content_browsing",
    "社交互动与通信": "social_chat_or_share",
    "音频录制与创作": "media_capture_or_recording",
    "图像视频拍摄与扫码": "media_capture_or_recording",
    "相册选择与媒体上传": "album_selection",
    "商品浏览与消费": "content_browsing",
    "支付与金融交易": "other",
    "文件与数据管理": "file_management",
    "设备清理与系统优化": "system_cleanup",
    "网络连接与设备管理": "nearby_service_or_wifi_scan",
    "用户反馈与客服": "customer_support",
    "其他": "other",
}

PERMISSION_RELEVANCE_HINTS: Dict[str, List[str]] = {
    "READ_EXTERNAL_STORAGE": [
        "文件", "相册", "照片", "图片", "视频", "下载", "上传", "恢复", "清理", "缓存", "存储", "安装包", "大文件", "导出",
    ],
    "WRITE_EXTERNAL_STORAGE": [
        "保存", "写入", "下载", "上传", "导出", "删除", "清理", "恢复", "缓存", "存储", "安装包", "大文件",
    ],
    "CAMERA": ["拍摄", "拍照", "扫码", "相机", "录像", "视频录制", "二维码"],
    "RECORD_AUDIO": ["录音", "麦克风", "语音", "清唱", "k歌", "配音", "音频"],
    "ACCESS_FINE_LOCATION": ["定位", "附近", "导航", "地图", "位置", "轨迹"],
    "ACCESS_COARSE_LOCATION": ["定位", "附近", "导航", "地图", "位置", "轨迹"],
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


def _normalize_scene_key(scene: Any) -> str:
    raw = _norm(scene, 64)
    if not raw:
        return ""
    return REFINED_SCENE_ALIASES.get(raw, raw)


def _resolve_scene(refined_scene: str, ui_task_scene: str) -> str:
    rs = _normalize_scene_key(refined_scene)
    if rs in REFINED_SCENE_SET:
        return rs
    return UI_TO_REFINED_FALLBACK.get(_as_text(ui_task_scene, 40), "other")


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


def _to_structured_entry(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    refined_scene = _normalize_scene_key(raw.get("refined_scene") or raw.get("scene"))
    if not refined_scene:
        return None

    perms: List[str] = []
    for p in _as_list(raw.get("permissions")):
        v = _as_text(p, 64).upper()
        if v and v not in perms:
            perms.append(v)
    single_perm = _as_text(raw.get("permission"), 64).upper()
    if single_perm and single_perm not in perms:
        perms.append(single_perm)
    if not perms:
        return None

    source_type = _norm(raw.get("source_type"), 16) or "pattern"
    if source_type not in {"prior", "pattern", "case"}:
        source_type = "pattern"

    return {
        "id": _as_text(raw.get("id"), 48),
        "scene": _as_text(raw.get("scene"), 64),
        "refined_scene": refined_scene,
        "permissions": perms[:4],
        "allow_if": _dedup_text_list(raw.get("allow_if"), max_items=12, max_len=80),
        "deny_if": _dedup_text_list(raw.get("deny_if"), max_items=12, max_len=80),
        "boundary_if_missing": _dedup_text_list(raw.get("boundary_if_missing"), max_items=8, max_len=80),
        "positive_evidence": _dedup_text_list(raw.get("positive_evidence"), max_items=12, max_len=80),
        "negative_evidence": _dedup_text_list(raw.get("negative_evidence"), max_items=12, max_len=80),
        "source_type": source_type,
    }


def load_structured_knowledge_entries(path: str) -> List[Dict[str, Any]]:
    raw = _safe_load_json(path)
    if isinstance(raw, dict):
        rows = raw.get("knowledge", [])
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        entry = _to_structured_entry(item)
        if not entry:
            continue
        if not entry.get("id"):
            entry["id"] = f"R{i + 1:03d}"
        out.append(entry)
    return out


def _build_retrieval_context(
    user_intent: str,
    trigger_action: str,
    page_observation: str,
    visual_evidence: List[Any],
) -> Tuple[str, Set[str]]:
    visual_values = [_as_text(x, 80) for x in _as_list(visual_evidence) if _as_text(x, 80)]
    blob_parts = [
        _as_text(user_intent, 320),
        _as_text(trigger_action, 200),
        _as_text(page_observation, 500),
        " ".join(visual_values[:20]),
    ]
    blob = " ".join([x for x in blob_parts if x]).lower()

    term_set = {_norm(x, 80) for x in visual_values if _norm(x, 80)}
    for tok in re.findall(r"[a-z0-9_\-]{3,}", blob):
        term_set.add(tok)
    return blob, term_set


def _match_terms(candidates: List[str], context_blob: str, context_terms: Set[str]) -> List[str]:
    matched: List[str] = []
    seen_keys: Set[str] = set()
    for cue in candidates:
        key = _norm(cue, 80)
        if not key or key in seen_keys:
            continue
        if key in context_blob or key in context_terms:
            matched.append(cue)
            seen_keys.add(key)
    return matched


def _coarse_recall(
    rule_entries: List[Dict[str, Any]],
    target_scene: str,
    permission_set: Set[str],
) -> List[Dict[str, Any]]:
    stage1 = [x for x in rule_entries if _norm(x.get("refined_scene"), 64) == target_scene]
    if not stage1:
        stage1 = list(rule_entries)

    if permission_set:
        by_perm: List[Dict[str, Any]] = []
        for item in stage1:
            item_perms = {_as_text(p, 64).upper() for p in _as_list(item.get("permissions")) if _as_text(p, 64)}
            if item_perms & permission_set:
                by_perm.append(item)
        stage1 = by_perm
    return stage1


def _score_rule(
    item: Dict[str, Any],
    target_scene: str,
    permission_set: Set[str],
    context_blob: str,
    context_terms: Set[str],
) -> Dict[str, Any]:
    item_perms = [_as_text(p, 64).upper() for p in _as_list(item.get("permissions")) if _as_text(p, 64)]
    overlap_perms = sorted(set(item_perms) & permission_set)
    perm_overlap = len(overlap_perms)

    allow_terms = _dedup_text_list(item.get("allow_if"), max_items=12)
    deny_terms = _dedup_text_list(item.get("deny_if"), max_items=12)
    pos_terms = _dedup_text_list(item.get("positive_evidence"), max_items=12)
    neg_terms = _dedup_text_list(item.get("negative_evidence"), max_items=12)
    boundary_terms = _dedup_text_list(item.get("boundary_if_missing"), max_items=8)

    matched_allow = _match_terms(allow_terms, context_blob, context_terms)
    matched_pos = _match_terms(pos_terms, context_blob, context_terms)
    matched_deny = _match_terms(deny_terms, context_blob, context_terms)
    matched_neg = _match_terms(neg_terms, context_blob, context_terms)

    merged_pos = _dedup_text_list(matched_allow + matched_pos, max_items=10)
    merged_neg = _dedup_text_list(matched_deny + matched_neg, max_items=10)

    boundary_missing: List[str] = []
    for term in boundary_terms:
        key = _norm(term, 80)
        if not key:
            continue
        if key in context_blob or key in context_terms:
            continue
        boundary_missing.append(term)

    pos_hits = len(merged_pos)
    neg_hits = len(merged_neg)
    evidence_hits = pos_hits + neg_hits
    conflict_ratio = round(min(pos_hits, neg_hits) / max(evidence_hits, 1), 3)
    coverage_pool = len(set(allow_terms + deny_terms + pos_terms + neg_terms))
    coverage_score = round(evidence_hits / max(coverage_pool, 1), 3)

    conflict_penalty = round(conflict_ratio * 4.0, 3)
    boundary_penalty = round(min(len(boundary_missing), 3) * 1.8, 3)

    matched_blob = " ".join([_norm(x, 80) for x in (merged_pos + merged_neg)])
    checked_perm_count = 0
    permission_relevance_hits = 0
    for perm in overlap_perms:
        hints = PERMISSION_RELEVANCE_HINTS.get(perm, [])
        if not hints:
            continue
        checked_perm_count += 1
        if any((hint in context_blob) or (hint in matched_blob) for hint in hints):
            permission_relevance_hits += 1

    permission_relevance_score = (
        round(permission_relevance_hits / max(checked_perm_count, 1), 3) if checked_perm_count else 1.0
    )
    permission_miss_penalty = 0.0
    if checked_perm_count > 0 and permission_relevance_hits == 0:
        permission_miss_penalty = 9.0
    elif checked_perm_count > 0 and permission_relevance_hits < checked_perm_count:
        permission_miss_penalty = 3.0

    scene_hit = 5 if _norm(item.get("refined_scene"), 64) == target_scene else 0
    perm_hit = 4 if perm_overlap > 0 else 0
    polarity_bonus = 1.0 if (pos_hits == 0 and neg_hits > 0) else 0.0

    score = (
        scene_hit
        + perm_hit
        + evidence_hits * 2.8
        + polarity_bonus
        - conflict_penalty
        - boundary_penalty
        - permission_miss_penalty
    )
    if evidence_hits == 0:
        score -= 6.0

    return {
        "id": _as_text(item.get("id"), 48),
        "scene": _as_text(item.get("scene"), 64),
        "refined_scene": _as_text(item.get("refined_scene"), 64),
        "permissions": item_perms[:4],
        "source_type": _norm(item.get("source_type"), 16) or "pattern",
        "allow_if": allow_terms[:8],
        "deny_if": deny_terms[:8],
        "boundary_if_missing": boundary_terms[:6],
        "positive_evidence": pos_terms[:8],
        "negative_evidence": neg_terms[:8],
        "matched_positive_evidence": merged_pos[:6],
        "matched_negative_evidence": merged_neg[:6],
        "boundary_missing": boundary_missing[:4],
        "matched_pos_count": pos_hits,
        "matched_neg_count": neg_hits,
        "conflict_ratio": conflict_ratio,
        "coverage_score": coverage_score,
        "permission_relevance_score": permission_relevance_score,
        "permission_relevance_penalty": permission_miss_penalty,
        "retrieval_score": round(float(score), 3),
    }


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
    structured_cues: Optional[Dict[str, List[Any]]] = None,
    top_k_patterns: int = 2,
    top_k_cases: int = 2,
    top_k_risky_cases: int = 2,
    top_k_compliant_cases: int = 2,
    top_k_skills: int = 2,
    structured_entries: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    del pattern_entries, case_entries, prior_entries, skill_entries, structured_cues, top_k_skills

    target_scene = _resolve_scene(refined_scene=refined_scene, ui_task_scene=ui_task_scene)
    permission_set = {_as_text(x, 64).upper() for x in _as_list(permissions) if _as_text(x, 64)}
    context_blob, context_terms = _build_retrieval_context(
        user_intent=user_intent,
        trigger_action=trigger_action,
        page_observation=page_observation,
        visual_evidence=visual_evidence,
    )

    rule_entries = _as_list(structured_entries)
    stage1_candidates = _coarse_recall(
        rule_entries=rule_entries,
        target_scene=target_scene,
        permission_set=permission_set,
    )

    ranked = [
        _score_rule(
            item=item,
            target_scene=target_scene,
            permission_set=permission_set,
            context_blob=context_blob,
            context_terms=context_terms,
        )
        for item in stage1_candidates
    ]
    ranked.sort(
        key=lambda x: (
            x.get("retrieval_score", 0.0),
            x.get("coverage_score", 0.0),
            -x.get("conflict_ratio", 0.0),
        ),
        reverse=True,
    )

    min_relevance_score = 4.0
    filtered_ranked = [x for x in ranked if float(x.get("retrieval_score", 0.0)) >= min_relevance_score]
    ranked_for_select = filtered_ranked if filtered_ranked else []

    conflict_threshold = 0.45
    conflict_detected = any(
        (x.get("conflict_ratio", 0.0) >= conflict_threshold)
        and x.get("matched_pos_count", 0) > 0
        and x.get("matched_neg_count", 0) > 0
        for x in ranked_for_select[: max(top_k_patterns * 2, 4)]
    )

    retained_k = max(top_k_patterns * 2, 4)
    if conflict_detected:
        retained_k = min(retained_k, 3)
    retrieved_rules = ranked_for_select[:retained_k]

    prior_rules = [x for x in retrieved_rules if x.get("source_type") == "prior"][: max(top_k_patterns, 1)]
    pattern_rules = [x for x in retrieved_rules if x.get("source_type") == "pattern"][: max(top_k_patterns, 1)]
    case_rules = [x for x in retrieved_rules if x.get("source_type") == "case"][: max(top_k_cases, 1)]

    risky_cases = [
        x for x in case_rules if x.get("matched_neg_count", 0) >= x.get("matched_pos_count", 0)
    ][: max(top_k_risky_cases, 1)]
    compliant_cases = [
        x for x in case_rules if x.get("matched_pos_count", 0) > x.get("matched_neg_count", 0)
    ][: max(top_k_compliant_cases, 1)]

    if not risky_cases:
        risky_cases = [x for x in retrieved_rules if x.get("matched_neg_count", 0) > 0][: max(top_k_risky_cases, 1)]
    if not compliant_cases:
        compliant_cases = [x for x in retrieved_rules if x.get("matched_pos_count", 0) > 0][: max(top_k_compliant_cases, 1)]

    avg_coverage = round(
        sum(float(x.get("coverage_score", 0.0)) for x in retrieved_rules) / max(len(retrieved_rules), 1),
        3,
    )

    return {
        "scene_key": target_scene,
        "retrieval_strategy": "two_stage_scene_permission_rerank",
        "stage1_candidate_count": len(stage1_candidates),
        "stage2_ranked_count": len(ranked),
        "conflict_threshold": conflict_threshold,
        "conflict_detected": conflict_detected,
        "retained_k": retained_k,
        "retrieved_rules": retrieved_rules,
        "retrieval_diagnostics": {
            "conflict_detected": conflict_detected,
            "avg_coverage_score": avg_coverage,
            "candidate_count": len(stage1_candidates),
            "min_relevance_score": min_relevance_score,
            "filtered_out_count": max(len(ranked) - len(ranked_for_select), 0),
        },
        "retrieved_prior_patterns": prior_rules,
        "retrieved_decision_patterns": pattern_rules,
        "retrieved_risky_cases": risky_cases,
        "retrieved_compliant_cases": compliant_cases,
        "retrieved_skill_patterns": [],
        "retrieved_patterns": (prior_rules + pattern_rules)[: max(top_k_patterns * 2, 2)],
        "retrieved_cases": (risky_cases + compliant_cases)[: max(top_k_cases, 2)],
        "retrieved_skills": [],
    }
