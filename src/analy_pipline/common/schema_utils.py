# -*- coding: utf-8 -*-
"""
Schema normalization and validation helpers for Phase3 outputs.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple


SCENE_UNKNOWN = "UNKNOWN"
CONF_LEVELS = {"low", "medium", "high"}

RULE_SIGNALS = {"LOW_RISK", "MEDIUM_RISK", "HIGH_RISK"}
PERM_DECISIONS = {"CLEARLY_ALLOWED", "CLEARLY_PROHIBITED", "NEEDS_REVIEW"}

NECESSITY_LABELS = {"necessary", "helpful", "unnecessary"}
CONSISTENCY_LABELS = {"consistent", "weakly_consistent", "inconsistent"}
MINIMALITY_LABELS = {"minimal", "potentially_over_privileged", "over_privileged"}
LLM_FINAL_DECISIONS = {"COMPLIANT", "SUSPICIOUS", "NON_COMPLIANT"}
LLM_FINAL_RISKS = {"LOW", "MEDIUM", "HIGH"}

FINAL_DECISIONS = {"CLEARLY_OK", "NEED_REVIEW", "CLEARLY_RISKY"}
FINAL_RISKS = {"LOW", "MEDIUM", "HIGH"}
RECOGNITION_STATUS = {"recognized", "missing", "uncertain"}


def _as_int(v: Any, default: int = -1) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _as_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _enum(v: Any, allowed: Iterable[str], default: str) -> str:
    s = _as_str(v, default=default)
    return s if s in set(allowed) else default


def _normalize_short_text(v: Any, max_len: int = 400) -> str:
    return _as_str(v).strip()[:max_len]


def _normalize_chain_summary(v: Any) -> Any:
    if isinstance(v, dict):
        return {
            "before_text": _normalize_short_text(v.get("before_text"), max_len=400),
            "granting_text": _normalize_short_text(v.get("granting_text"), max_len=400),
            "after_text": _normalize_short_text(v.get("after_text"), max_len=400),
            "top_widgets": [x for x in _as_list(v.get("top_widgets")) if isinstance(x, str)][:16],
            "permissions": [normalize_permission_name(x) for x in _as_list(v.get("permissions")) if isinstance(x, str)],
        }
    return _normalize_short_text(v, max_len=800)


def _dedupe_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _contains_any(text: str, words: Iterable[str]) -> bool:
    t = _as_str(text)
    return any(w in t for w in words)


_PERM_UI_WORDS = (
    "权限",
    "授权",
    "允许",
    "拒绝",
    "始终允许",
    "仅在使用中",
    "本次",
    "去授权",
    "同意",
    "取消",
    "去设置",
    "仅此一次",
    "弹窗",
    "对话框",
    "ALLOW",
    "DENY",
    "PERMISSION",
)

_RATIONALE_WORDS = (
    "用于",
    "以便",
    "为了",
    "因为",
    "合理",
    "不合理",
    "必要",
    "不必要",
    "一致",
    "不一致",
    "匹配",
    "支持",
    "关联",
    "无关",
    "合规",
    "违规",
    "风险",
)

_PERM_SEMANTIC_HINTS = (
    "读写设备",
    "访问相册",
    "位置信息",
    "麦克风",
    "相机",
    "联系人",
    "READ_",
    "WRITE_",
    "ACCESS_",
    "RECORD_",
    "CAMERA",
)

_JUDGEMENT_HINTS = (
    "核心任务",
    "直接关联",
    "无直接关联",
    "合规",
    "违规",
    "风险",
    "合理",
    "不合理",
    "必要",
    "不必要",
    "一致",
    "不一致",
)


def _clean_observation_text(v: Any, max_len: int = 240) -> str:
    text = _normalize_short_text(v, max_len=max_len)
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r"[。；;!！?？\n]+", text) if s.strip()]
    keep: List[str] = []
    for s in sentences:
        if _contains_any(s, _RATIONALE_WORDS):
            continue
        keep.append(s)
    if keep:
        return "；".join(keep)[:max_len]
    text = text
    for w in _RATIONALE_WORDS:
        text = text.replace(w, "")
    return text.strip()[:max_len]


def _clean_intent_or_function(v: Any, max_len: int = 240) -> str:
    text = _normalize_short_text(v, max_len=max_len)
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r"[。；;!！?？\n]+", text) if s.strip()]
    keep: List[str] = []
    for s in sentences:
        if _contains_any(s, _PERM_UI_WORDS):
            continue
        if _contains_any(s, _RATIONALE_WORDS):
            continue
        keep.append(s)
    if keep:
        return "；".join(keep)[:max_len]
    text = text
    for w in list(_PERM_UI_WORDS) + list(_RATIONALE_WORDS):
        text = text.replace(w, "")
    return text.strip()[:max_len]


def _clean_visible_actions(actions: Any, max_items: int = 8) -> List[str]:
    out: List[str] = []
    for x in _as_list(actions):
        if not isinstance(x, str):
            continue
        s = _normalize_short_text(x, max_len=64)
        if not s:
            continue
        if _contains_any(s, _PERM_UI_WORDS):
            continue
        if len(s) >= 32:
            continue
        out.append(s)
    return _dedupe_keep_order(out)[:max_items]


def _normalize_task_phrase(v: Any, max_len: int = 24) -> str:
    text = _normalize_short_text(v, max_len=max_len)
    if not text:
        return ""
    text = re.split(r"[。；;!！?？\n]", text)[0].strip()
    for prefix in ("用户正在", "用户在", "用户希望", "用户想要", "用户尝试", "正在", "尝试"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    for prefix in ("当前页面", "页面", "进行", "执行"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    return text[:max_len]


def _derive_trigger_action(trigger_action: Any, visible_actions: List[str], task_phrase: str) -> str:
    raw = _normalize_short_text(trigger_action, max_len=40)
    if raw and not _contains_any(raw, _PERM_UI_WORDS):
        return raw
    strong_first = ("点击", "切换", "输入", "选择", "上传", "开始", "打开", "获取", "扫码")
    weak_first = ("使用", "浏览", "查看", "搜索")
    for a in visible_actions:
        if a.startswith(strong_first):
            return a[:40]
    for a in visible_actions:
        if a.startswith(weak_first):
            return a[:40]
    if visible_actions:
        return visible_actions[0][:40]
    if task_phrase:
        return f"执行{task_phrase}"[:40]
    return "unknown"


def _infer_page_cues(
    task_phrase: str,
    intent: str,
    page_function: str,
    keywords: List[str],
    widgets: List[str],
) -> List[str]:
    text = " ".join([task_phrase, intent, page_function, " ".join(keywords), " ".join(widgets)])
    cue_rules = [
        (("同城", "附近", "本地"), "local_content_entry"),
        (("定位", "位置", "导航", "地图"), "location_related_tab"),
        (("搜索", "搜"), "search_bar"),
        (("上传", "相册", "头像"), "upload_entry"),
        (("录音", "清唱", "音频"), "recording_controls"),
        (("验证码", "密码", "手机号", "输入"), "form_input_fields"),
        (("参数", "配置", "规格", "型号"), "technical_spec_table"),
        (("商品", "店铺", "购物"), "product_list"),
        (("登录", "注册", "账号"), "auth_flow_entry"),
        (("聊天", "消息", "私信"), "chat_entry"),
    ]
    out: List[str] = []
    for terms, cue in cue_rules:
        if any(t in text for t in terms) and cue not in out:
            out.append(cue)
    return out[:4]


def _normalize_page_cues(v: Any, fallback: List[str]) -> List[str]:
    out: List[str] = []
    for x in _as_list(v):
        if not isinstance(x, str):
            continue
        s = _normalize_short_text(x, max_len=40).lower().replace(" ", "_")
        if not s:
            continue
        if s not in out:
            out.append(s)
    if out:
        return out[:4]
    return fallback[:4]


def _clean_terms(items: Any, max_items: int = 16, max_len: int = 24) -> List[str]:
    out: List[str] = []
    for x in _as_list(items):
        if not isinstance(x, str):
            continue
        s = _normalize_short_text(x, max_len=max_len)
        if not s:
            continue
        out.append(s)
    return _dedupe_keep_order(out)[:max_items]


def _build_permission_observation(permissions: List[str], raw_observation: Any) -> str:
    if permissions:
        joined = "、".join(permissions[:3])
        return f"系统出现涉及{joined}的权限请求弹窗。"
    # Keep strictly observational and avoid purpose inference.
    if _normalize_short_text(raw_observation, max_len=20):
        return "系统出现权限请求弹窗。"
    return "系统出现权限请求弹窗。"


def _build_chain_summary(task_phrase: str, page_function: str, summary: Any) -> str:
    raw = _clean_observation_text(summary, max_len=220)
    if raw and not _contains_any(raw, _RATIONALE_WORDS):
        if "权限" in raw and "权限请求弹窗" not in raw:
            raw = ""
    if raw:
        return raw
    if task_phrase:
        return f"用户在当前页面{task_phrase}时，系统出现权限请求弹窗。"
    if page_function:
        return f"用户在当前页面进行操作时，系统出现权限请求弹窗。"
    return "用户在当前页面进行操作，期间出现系统权限请求弹窗。"


def normalize_scene_record(item: Dict[str, Any], scene_list: List[str]) -> Dict[str, Any]:
    chain_id = _as_int(item.get("chain_id"), default=-1)
    predicted_scene = _as_str(item.get("predicted_scene"), default=SCENE_UNKNOWN)
    if predicted_scene not in scene_list:
        predicted_scene = SCENE_UNKNOWN

    top3_raw = [x for x in _as_list(item.get("scene_top3")) if isinstance(x, str) and x in scene_list]
    top3 = _dedupe_keep_order(top3_raw)[:3]
    if predicted_scene != SCENE_UNKNOWN and predicted_scene not in top3:
        top3 = [predicted_scene] + [x for x in top3 if x != predicted_scene]
        top3 = top3[:3]

    intent = _as_str(item.get("intent"), default="")
    confidence = _enum(_as_str(item.get("confidence"), default="low").lower(), CONF_LEVELS, "low")
    rerun = bool(item.get("rerun", False))
    rerun_reason = _as_str(item.get("rerun_reason"), default="")
    other_reason = _as_str(item.get("other_reason"), default="")

    basis = item.get("scene_basis") if isinstance(item.get("scene_basis"), dict) else {}
    basis_keywords = [x for x in _as_list(basis.get("keywords")) if isinstance(x, str)][:12]
    basis_widgets = [x for x in _as_list(basis.get("widgets")) if isinstance(x, str)][:12]
    basis_summary = _as_str(basis.get("chain_summary"), default="")

    return {
        "chain_id": chain_id,
        "task_phrase": _normalize_short_text(item.get("task_phrase"), max_len=120),
        "predicted_scene": predicted_scene,
        "scene_top3": top3,
        "intent": intent,
        "page_function": _normalize_short_text(item.get("page_function"), max_len=240),
        "permission_context": _normalize_short_text(item.get("permission_context"), max_len=240),
        "chain_summary": _normalize_chain_summary(item.get("chain_summary")),
        "confidence": confidence,
        "rerun": rerun,
        "rerun_reason": rerun_reason,
        "other_reason": other_reason,
        "scene_basis": {
            "keywords": basis_keywords,
            "widgets": basis_widgets,
            "chain_summary": basis_summary,
        },
    }


def validate_scene_results(items: Any, scene_list: List[str]) -> Tuple[List[Dict[str, Any]], int]:
    records = _as_list(items)
    normalized: List[Dict[str, Any]] = []
    invalid = 0
    for raw in records:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        rec = normalize_scene_record(raw, scene_list)
        if rec["chain_id"] < 0:
            invalid += 1
            continue
        normalized.append(rec)
    return normalized, invalid


def normalize_ui_task_scene_record(item: Dict[str, Any], scene_list: List[str]) -> Dict[str, Any]:
    rec = normalize_scene_record(
        {
            "chain_id": item.get("chain_id"),
            "task_phrase": item.get("task_phrase", ""),
            "predicted_scene": item.get("ui_task_scene") or item.get("predicted_scene"),
            "scene_top3": item.get("ui_task_scene_top3") or item.get("scene_top3"),
            "intent": item.get("intent", ""),
            "page_function": item.get("page_function", ""),
            "permission_context": item.get("permission_context", ""),
            "chain_summary": item.get("chain_summary", ""),
            "confidence": item.get("confidence", "low"),
            "rerun": item.get("rerun", False),
            "rerun_reason": item.get("rerun_reason", ""),
            "other_reason": item.get("other_reason", ""),
            "scene_basis": item.get("scene_basis", {}),
        },
        scene_list,
    )
    rec["ui_task_scene"] = rec["predicted_scene"]
    rec["ui_task_scene_top3"] = rec["scene_top3"]
    return rec


def validate_ui_task_scene_results(items: Any, scene_list: List[str]) -> Tuple[List[Dict[str, Any]], int]:
    records = _as_list(items)
    normalized: List[Dict[str, Any]] = []
    invalid = 0
    for raw in records:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        rec = normalize_ui_task_scene_record(raw, scene_list)
        if rec["chain_id"] < 0:
            invalid += 1
            continue
        normalized.append(rec)
    return normalized, invalid


def normalize_chain_semantic_record(item: Dict[str, Any]) -> Dict[str, Any]:
    chain_id = _as_int(item.get("chain_id"), default=-1)
    confidence = _as_str(item.get("confidence"), default="").lower()
    if confidence not in CONF_LEVELS:
        confidence = "low"

    permission_event = item.get("permission_event") if isinstance(item.get("permission_event"), dict) else {}
    pe_permissions = [
        normalize_permission_name(x)
        for x in _as_list(permission_event.get("permissions"))
        if isinstance(x, str)
    ]
    pe_permissions = _dedupe_keep_order([x for x in pe_permissions if x])[:16]
    pe_observation = _build_permission_observation(
        pe_permissions,
        permission_event.get("ui_observation") or item.get("permission_context"),
    )
    rec_status = _enum(
        _as_str(permission_event.get("recognition_status"), default="").lower(),
        RECOGNITION_STATUS,
        "",
    )
    if not rec_status:
        if pe_permissions:
            rec_status = "recognized"
        elif _normalize_short_text(permission_event.get("ui_observation") or item.get("permission_context"), max_len=40):
            rec_status = "missing"
        else:
            rec_status = "uncertain"

    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    keywords = _clean_terms(evidence.get("keywords") or item.get("keywords"), max_items=16, max_len=24)
    widgets = _clean_terms(evidence.get("widgets") or item.get("widgets"), max_items=16, max_len=24)

    visible_actions = _clean_visible_actions(item.get("visible_actions"), max_items=4)
    if not visible_actions:
        visible_actions = [x for x in widgets[:4] if x and not _contains_any(x, _PERM_UI_WORDS)]
    task_phrase = _normalize_task_phrase(item.get("task_phrase"), max_len=24)
    if (not task_phrase) or _contains_any(task_phrase, _PERM_UI_WORDS) or len(task_phrase) > 24:
        task_phrase = visible_actions[0] if visible_actions else "完成当前页面任务"
    if not visible_actions:
        visible_actions = [task_phrase]
    trigger_action = _derive_trigger_action(item.get("trigger_action"), visible_actions, task_phrase)
    page_transition = _clean_observation_text(item.get("page_transition"), max_len=160)

    intent = _clean_intent_or_function(item.get("intent"), max_len=180)
    if _contains_any(intent, _PERM_SEMANTIC_HINTS) or _contains_any(intent, _JUDGEMENT_HINTS):
        intent = ""
    if len(intent) < 6:
        intent = f"用户希望在当前页面完成{task_phrase}。"

    page_function = _clean_intent_or_function(item.get("page_function"), max_len=180)
    if _contains_any(page_function, _PERM_SEMANTIC_HINTS) or _contains_any(page_function, _JUDGEMENT_HINTS):
        page_function = ""
    if len(page_function) < 6:
        page_function = f"页面提供与{task_phrase}相关的功能。"
    page_cues = _normalize_page_cues(
        evidence.get("page_cues"),
        fallback=_infer_page_cues(
            task_phrase=task_phrase,
            intent=intent,
            page_function=page_function,
            keywords=keywords,
            widgets=widgets,
        ),
    )
    task_relevance_cues = _clean_terms(
        item.get("task_relevance_cues"),
        max_items=8,
        max_len=32,
    )
    if not task_relevance_cues:
        task_relevance_cues = page_cues[:4]

    return {
        "chain_id": chain_id,
        "task_phrase": task_phrase,
        "intent": intent,
        "page_function": page_function,
        "trigger_action": trigger_action,
        "page_transition": page_transition,
        "visible_actions": visible_actions,
        "permission_event": {
            "permissions": pe_permissions,
            "ui_observation": pe_observation,
            "recognition_status": rec_status,
        },
        "evidence": {
            "keywords": keywords,
            "widgets": widgets,
            "page_cues": page_cues,
        },
        "task_relevance_cues": task_relevance_cues,
        "chain_summary": _build_chain_summary(task_phrase, page_function, item.get("chain_summary")),
        "confidence": confidence,
        "rerun": bool(item.get("rerun", False)),
        "rerun_reason": _normalize_short_text(item.get("rerun_reason"), max_len=120),
    }


def validate_chain_semantic_results(items: Any) -> Tuple[List[Dict[str, Any]], int]:
    records = _as_list(items)
    normalized: List[Dict[str, Any]] = []
    invalid = 0
    for raw in records:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        rec = normalize_chain_semantic_record(raw)
        if rec["chain_id"] < 0:
            invalid += 1
            continue
        normalized.append(rec)
    return normalized, invalid


def normalize_regulatory_scene_record(
    item: Dict[str, Any],
    scene_list: List[str],
    regulatory_scene_list: List[str],
) -> Dict[str, Any]:
    chain_id = _as_int(item.get("chain_id"), default=-1)

    ui_scene = _as_str(item.get("ui_task_scene") or item.get("predicted_scene"), default=SCENE_UNKNOWN)
    if ui_scene not in scene_list:
        ui_scene = SCENE_UNKNOWN
    ui_top3 = [x for x in _as_list(item.get("ui_task_scene_top3") or item.get("scene_top3")) if isinstance(x, str) and x in scene_list]
    ui_top3 = _dedupe_keep_order(ui_top3)[:3]
    if ui_scene != SCENE_UNKNOWN and ui_scene not in ui_top3:
        ui_top3 = [ui_scene] + [x for x in ui_top3 if x != ui_scene]
        ui_top3 = ui_top3[:3]

    reg_raw = _as_str(item.get("regulatory_scene"), default="") or _as_str(item.get("regulatory_scene_top1"), default="")
    reg_top1 = reg_raw
    if reg_top1 not in regulatory_scene_list:
        reg_top1 = "UNKNOWN"
    reg_top3 = [x for x in _as_list(item.get("regulatory_scene_top3")) if isinstance(x, str) and x in regulatory_scene_list]
    reg_top3 = _dedupe_keep_order(reg_top3)[:3]
    if reg_top1 != "UNKNOWN" and reg_top1 not in reg_top3:
        reg_top3 = [reg_top1] + [x for x in reg_top3 if x != reg_top1]
        reg_top3 = reg_top3[:3]

    allowed_permissions = [
        normalize_permission_name(x)
        for x in _as_list(item.get("allowed_permissions"))
        if isinstance(x, str)
    ]
    banned_permissions = [
        normalize_permission_name(x)
        for x in _as_list(item.get("banned_permissions"))
        if isinstance(x, str)
    ]

    confidence = _as_str(item.get("confidence"), default="").lower()
    if confidence not in CONF_LEVELS:
        confidence = "low"

    return {
        "chain_id": chain_id,
        "task_phrase": _normalize_short_text(item.get("task_phrase"), max_len=120),
        "intent": _normalize_short_text(item.get("intent"), max_len=240),
        "chain_summary": _normalize_chain_summary(item.get("chain_summary")),
        "permissions": [normalize_permission_name(x) for x in _as_list(item.get("permissions")) if isinstance(x, str)],
        "ui_task_scene": ui_scene,
        "ui_task_scene_top3": ui_top3,
        "regulatory_scene": reg_top1,
        "regulatory_scene_top1": reg_top1,
        "regulatory_scene_top3": reg_top3,
        "mapping_reason": _normalize_short_text(item.get("mapping_reason"), max_len=280),
        "allowed_permissions": _dedupe_keep_order(allowed_permissions),
        "banned_permissions": _dedupe_keep_order(banned_permissions),
        "confidence": confidence,
        "rerun": bool(item.get("rerun", False)),
        "rerun_reason": _normalize_short_text(item.get("rerun_reason"), max_len=120),
    }


def validate_regulatory_scene_results(
    items: Any,
    scene_list: List[str],
    regulatory_scene_list: List[str],
) -> Tuple[List[Dict[str, Any]], int]:
    records = _as_list(items)
    normalized: List[Dict[str, Any]] = []
    invalid = 0
    for raw in records:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        rec = normalize_regulatory_scene_record(
            raw,
            scene_list=scene_list,
            regulatory_scene_list=regulatory_scene_list,
        )
        if rec["chain_id"] < 0:
            invalid += 1
            continue
        normalized.append(rec)
    return normalized, invalid


def normalize_permission_name(permission: str) -> str:
    raw = _as_str(permission).strip()
    if not raw:
        return ""

    # Preserve explicit android style first.
    p = raw.upper().replace("ANDROID.PERMISSION.", "")
    p = p.replace("-", "_").replace(" ", "_")
    p = re.sub(r"[^A-Z0-9_]", "", p)

    aliases = {
        "FINE_LOCATION": "ACCESS_FINE_LOCATION",
        "COARSE_LOCATION": "ACCESS_COARSE_LOCATION",
        "LOCATION_FINE": "ACCESS_FINE_LOCATION",
        "LOCATION_COARSE": "ACCESS_COARSE_LOCATION",
        "READ_IMAGES": "READ_MEDIA_IMAGES",
        "READ_IMAGE": "READ_MEDIA_IMAGES",
        "READ_PHOTOS": "READ_MEDIA_IMAGES",
        "READ_VIDEO": "READ_MEDIA_VIDEO",
        "READ_AUDIO": "READ_MEDIA_AUDIO",
        "STORAGE": "READ_EXTERNAL_STORAGE",
        "READ_STORAGE": "READ_EXTERNAL_STORAGE",
        "WRITE_STORAGE": "WRITE_EXTERNAL_STORAGE",
        "READ_PHONE_NUMBER": "READ_PHONE_NUMBERS",
    }
    if p in aliases:
        return aliases[p]
    if p.startswith(
        (
            "ACCESS_",
            "READ_",
            "WRITE_",
            "RECORD_",
            "POST_",
            "CAMERA",
            "BLUETOOTH",
            "BODY_",
            "ACTIVITY_",
            "GET_",
            "NEARBY_",
        )
    ):
        return p

    lower_raw = raw.lower()
    keyword_map = [
        (("麦克风", "录音", "microphone", "audio record"), "RECORD_AUDIO"),
        (("相机", "拍照", "摄像", "camera"), "CAMERA"),
        (("联系人", "通讯录", "contact"), "READ_CONTACTS"),
        (("定位", "位置", "location"), "ACCESS_FINE_LOCATION"),
        (("图片", "照片", "相册", "photo", "image"), "READ_MEDIA_IMAGES"),
        (("视频", "video"), "READ_MEDIA_VIDEO"),
        (("音频", "音乐", "audio"), "READ_MEDIA_AUDIO"),
        (("文件", "存储", "external storage", "storage"), "READ_EXTERNAL_STORAGE"),
    ]
    for keys, target in keyword_map:
        if any(k in raw or k in lower_raw for k in keys):
            return target

    return p


def normalize_permission_record(item: Dict[str, Any]) -> Dict[str, Any]:
    chain_id = _as_int(item.get("chain_id"), default=-1)
    perms = [normalize_permission_name(x) for x in _as_list(item.get("predicted_permissions")) if isinstance(x, str)]
    perms = _dedupe_keep_order(perms)

    files = item.get("files") if isinstance(item.get("files"), dict) else {}
    before = _as_str(files.get("before"), default="")
    granting = [x for x in _as_list(files.get("granting")) if isinstance(x, str)]
    after = _as_str(files.get("after"), default="")

    return {
        "chain_id": chain_id,
        "predicted_permissions": perms,
        "permission_source": "rule",
        "files": {
            "before": before,
            "granting": granting,
            "after": after,
        },
    }


def validate_permission_results(items: Any) -> Tuple[List[Dict[str, Any]], int]:
    records = _as_list(items)
    normalized: List[Dict[str, Any]] = []
    invalid = 0
    for raw in records:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        rec = normalize_permission_record(raw)
        if rec["chain_id"] < 0:
            invalid += 1
            continue
        normalized.append(rec)
    return normalized, invalid


def normalize_rule_screening_record(item: Dict[str, Any], scene_list: List[str]) -> Dict[str, Any]:
    chain_id = _as_int(item.get("chain_id"), default=-1)
    scene = _as_str(item.get("scene"), default=SCENE_UNKNOWN)
    if scene not in scene_list:
        scene = SCENE_UNKNOWN

    scene_top3 = [x for x in _as_list(item.get("scene_top3")) if isinstance(x, str) and x in scene_list]
    scene_top3 = _dedupe_keep_order(scene_top3)[:3]

    perms = [normalize_permission_name(x) for x in _as_list(item.get("permissions")) if isinstance(x, str)]
    perms = _dedupe_keep_order(perms)

    pdec = item.get("permission_decisions") if isinstance(item.get("permission_decisions"), dict) else {}
    clean_pdec = {normalize_permission_name(k): _enum(v, PERM_DECISIONS, "NEEDS_REVIEW") for k, v in pdec.items()}

    matched_rules = _as_list(item.get("matched_rules"))
    norm_rules = []
    for r in matched_rules:
        if not isinstance(r, dict):
            continue
        norm_rules.append({
            "permission": normalize_permission_name(r.get("permission")),
            "decision": _enum(r.get("decision"), PERM_DECISIONS, "NEEDS_REVIEW"),
            "evidence": _as_str(r.get("evidence")),
        })

    return {
        "chain_id": chain_id,
        "scene": scene,
        "scene_top3": scene_top3,
        "ui_task_scene": _normalize_short_text(item.get("ui_task_scene") or scene, max_len=120),
        "ui_task_scene_top3": [x for x in _as_list(item.get("ui_task_scene_top3") or scene_top3) if isinstance(x, str)][:3],
        "regulatory_scene": _normalize_short_text(item.get("regulatory_scene") or item.get("regulatory_scene_top1"), max_len=120),
        "regulatory_scene_top1": _normalize_short_text(item.get("regulatory_scene_top1"), max_len=120),
        "regulatory_scene_top3": [x for x in _as_list(item.get("regulatory_scene_top3")) if isinstance(x, str)][:3],
        "task_phrase": _normalize_short_text(item.get("task_phrase"), max_len=120),
        "intent": _as_str(item.get("intent"), default=""),
        "page_function": _normalize_short_text(item.get("page_function"), max_len=280),
        "trigger_action": _normalize_short_text(item.get("trigger_action"), max_len=80),
        "visible_actions": _clean_visible_actions(item.get("visible_actions"), max_items=8),
        "task_relevance_cues": _clean_terms(item.get("task_relevance_cues"), max_items=8, max_len=40),
        "permission_context": _normalize_short_text(item.get("permission_context"), max_len=280),
        "chain_summary": _normalize_chain_summary(item.get("chain_summary")),
        "permissions": perms,
        "allowed_permissions": [normalize_permission_name(x) for x in _as_list(item.get("allowed_permissions")) if isinstance(x, str)],
        "banned_permissions": [normalize_permission_name(x) for x in _as_list(item.get("banned_permissions")) if isinstance(x, str)],
        "mapping_reason": _normalize_short_text(item.get("mapping_reason"), max_len=280),
        "rule_prior": _enum(item.get("rule_prior"), {"expected", "suspicious", "unexpected"}, "suspicious"),
        "rule_notes": [_normalize_short_text(x, max_len=160) for x in _as_list(item.get("rule_notes")) if _as_str(x)],
        "permission_decisions": clean_pdec,
        "overall_rule_signal": _enum(item.get("overall_rule_signal"), RULE_SIGNALS, "MEDIUM_RISK"),
        "matched_rules": norm_rules,
    }


def validate_rule_screening_results(items: Any, scene_list: List[str]) -> Tuple[List[Dict[str, Any]], int]:
    records = _as_list(items)
    normalized: List[Dict[str, Any]] = []
    invalid = 0
    for raw in records:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        rec = normalize_rule_screening_record(raw, scene_list)
        if rec["chain_id"] < 0:
            invalid += 1
            continue
        normalized.append(rec)
    return normalized, invalid


def _normalize_analysis_block(
    block: Any,
    label_key: str,
    allowed_labels: Iterable[str],
    default_label: str,
) -> Dict[str, Any]:
    b = block if isinstance(block, dict) else {}
    return {
        "label": _enum(b.get(label_key), allowed_labels, default_label),
        "reason": _as_str(b.get("reason"), default=""),
    }


def normalize_llm_review_record(item: Dict[str, Any]) -> Dict[str, Any]:
    chain_id = _as_int(item.get("chain_id"), default=-1)
    necessity_obj = item.get("necessity") if isinstance(item.get("necessity"), dict) else {}
    consistency_obj = item.get("consistency") if isinstance(item.get("consistency"), dict) else {}
    over_scope_obj = item.get("over_scope") if isinstance(item.get("over_scope"), dict) else {}
    raw_conf = item.get("confidence")
    conf_label = "low"
    conf_score = 0.35
    if isinstance(raw_conf, str):
        label = _as_str(raw_conf, default="").lower()
        if label in CONF_LEVELS:
            conf_label = label
            conf_score = {"low": 0.35, "medium": 0.65, "high": 0.9}[label]
        else:
            try:
                score = float(raw_conf)
                conf_score = max(0.0, min(1.0, score))
                if conf_score >= 0.8:
                    conf_label = "high"
                elif conf_score >= 0.5:
                    conf_label = "medium"
                else:
                    conf_label = "low"
            except Exception:
                pass
    elif isinstance(raw_conf, (int, float)):
        conf_score = max(0.0, min(1.0, float(raw_conf)))
        if conf_score >= 0.8:
            conf_label = "high"
        elif conf_score >= 0.5:
            conf_label = "medium"
        else:
            conf_label = "low"

    out = {
        "chain_id": chain_id,
        "scene": _as_str(item.get("scene"), default=SCENE_UNKNOWN),
        "ui_task_scene": _normalize_short_text(item.get("ui_task_scene") or item.get("scene"), max_len=120),
        "ui_task_scene_top3": [x for x in _as_list(item.get("ui_task_scene_top3")) if isinstance(x, str)][:3],
        "regulatory_scene": _normalize_short_text(item.get("regulatory_scene") or item.get("regulatory_scene_top1"), max_len=120),
        "regulatory_scene_top1": _normalize_short_text(item.get("regulatory_scene_top1"), max_len=120),
        "regulatory_scene_top3": [x for x in _as_list(item.get("regulatory_scene_top3")) if isinstance(x, str)][:3],
        "task_phrase": _normalize_short_text(item.get("task_phrase"), max_len=120),
        "intent": _as_str(item.get("intent"), default=""),
        "page_function": _normalize_short_text(item.get("page_function"), max_len=280),
        "trigger_action": _normalize_short_text(item.get("trigger_action"), max_len=80),
        "visible_actions": _clean_visible_actions(item.get("visible_actions"), max_items=8),
        "task_relevance_cues": _clean_terms(item.get("task_relevance_cues"), max_items=8, max_len=40),
        "permission_context": _normalize_short_text(item.get("permission_context"), max_len=280),
        "chain_summary": _normalize_chain_summary(item.get("chain_summary")),
        "permissions": [normalize_permission_name(x) for x in _as_list(item.get("permissions")) if isinstance(x, str)],
        "allowed_permissions": [normalize_permission_name(x) for x in _as_list(item.get("allowed_permissions")) if isinstance(x, str)],
        "banned_permissions": [normalize_permission_name(x) for x in _as_list(item.get("banned_permissions")) if isinstance(x, str)],
        "rule_signal": _enum(item.get("rule_signal"), RULE_SIGNALS, "MEDIUM_RISK"),
        "rule_prior": _enum(item.get("rule_prior"), {"expected", "suspicious", "unexpected"}, "suspicious"),
        "rule_notes": [_normalize_short_text(x, max_len=160) for x in _as_list(item.get("rule_notes")) if _as_str(x)],
        "necessity": {
            "label": _enum(necessity_obj.get("label"), NECESSITY_LABELS, "helpful"),
            "reason": _as_str(necessity_obj.get("reason"), default=""),
        },
        "consistency": {
            "label": _enum(consistency_obj.get("label"), CONSISTENCY_LABELS, "weakly_consistent"),
            "reason": _as_str(consistency_obj.get("reason"), default=""),
        },
        "over_scope": {
            "label": _enum(
                over_scope_obj.get("label"),
                {"minimal", "potentially_over_scoped", "over_scoped"},
                "potentially_over_scoped",
            ),
            "reason": _as_str(over_scope_obj.get("reason"), default=""),
        },
        "final_risk": _enum(item.get("final_risk"), {"low", "medium", "high"}, "medium"),
        "final_decision": _enum(item.get("final_decision"), {"compliant", "suspicious", "non_compliant"}, "suspicious"),
        "confidence": round(conf_score, 3),
        "confidence_label": conf_label,
        "analysis_summary": _as_str(item.get("analysis_summary"), default=""),
        "necessity_analysis": _normalize_analysis_block(
            item.get("necessity_analysis"),
            "label",
            NECESSITY_LABELS,
            "unnecessary",
        ),
        "consistency_analysis": _normalize_analysis_block(
            item.get("consistency_analysis"),
            "label",
            CONSISTENCY_LABELS,
            "inconsistent",
        ),
        "minimality_analysis": _normalize_analysis_block(
            item.get("minimality_analysis"),
            "label",
            MINIMALITY_LABELS,
            "over_privileged",
        ),
        "llm_final_decision": _enum(item.get("llm_final_decision"), LLM_FINAL_DECISIONS, "SUSPICIOUS"),
        "llm_final_risk": _enum(item.get("llm_final_risk"), LLM_FINAL_RISKS, "MEDIUM"),
        "llm_explanation": _as_str(item.get("llm_explanation"), default=""),
        "output_valid": bool(item.get("output_valid", False)),
        "format_error": bool(item.get("format_error", False)),
    }
    if "raw_output" in item:
        out["raw_output"] = _as_str(item.get("raw_output"))
    return out


def validate_llm_review_results(items: Any) -> Tuple[List[Dict[str, Any]], int]:
    records = _as_list(items)
    normalized: List[Dict[str, Any]] = []
    invalid = 0
    for raw in records:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        rec = normalize_llm_review_record(raw)
        if rec["chain_id"] < 0:
            invalid += 1
            continue
        normalized.append(rec)
    return normalized, invalid


def normalize_final_decision_record(item: Dict[str, Any]) -> Dict[str, Any]:
    chain_id = _as_int(item.get("chain_id"), default=-1)
    explain = item.get("explain") if isinstance(item.get("explain"), dict) else {}
    return {
        "chain_id": chain_id,
        "scene": _as_str(item.get("scene"), default=SCENE_UNKNOWN),
        "ui_task_scene": _normalize_short_text(item.get("ui_task_scene") or item.get("scene"), max_len=120),
        "ui_task_scene_top3": [x for x in _as_list(item.get("ui_task_scene_top3")) if isinstance(x, str)][:3],
        "regulatory_scene": _normalize_short_text(item.get("regulatory_scene") or item.get("regulatory_scene_top1"), max_len=120),
        "regulatory_scene_top1": _normalize_short_text(item.get("regulatory_scene_top1"), max_len=120),
        "regulatory_scene_top3": [x for x in _as_list(item.get("regulatory_scene_top3")) if isinstance(x, str)][:3],
        "task_phrase": _normalize_short_text(item.get("task_phrase"), max_len=120),
        "intent": _as_str(item.get("intent"), default=""),
        "page_function": _normalize_short_text(item.get("page_function"), max_len=280),
        "trigger_action": _normalize_short_text(item.get("trigger_action"), max_len=80),
        "visible_actions": _clean_visible_actions(item.get("visible_actions"), max_items=8),
        "task_relevance_cues": _clean_terms(item.get("task_relevance_cues"), max_items=8, max_len=40),
        "permission_context": _normalize_short_text(item.get("permission_context"), max_len=280),
        "chain_summary": _normalize_chain_summary(item.get("chain_summary")),
        "permissions": [normalize_permission_name(x) for x in _as_list(item.get("permissions")) if isinstance(x, str)],
        "allowed_permissions": [normalize_permission_name(x) for x in _as_list(item.get("allowed_permissions")) if isinstance(x, str)],
        "banned_permissions": [normalize_permission_name(x) for x in _as_list(item.get("banned_permissions")) if isinstance(x, str)],
        "rule_signal": _enum(item.get("rule_signal"), RULE_SIGNALS, "MEDIUM_RISK"),
        "llm_final_decision": _enum(item.get("llm_final_decision"), LLM_FINAL_DECISIONS, "SUSPICIOUS"),
        "llm_final_risk": _enum(item.get("llm_final_risk"), LLM_FINAL_RISKS, "MEDIUM"),
        "final_decision": _enum(item.get("final_decision"), FINAL_DECISIONS, "NEED_REVIEW"),
        "final_risk": _enum(item.get("final_risk"), FINAL_RISKS, "MEDIUM"),
        "arbiter_triggered": bool(item.get("arbiter_triggered", False)),
        "arbiter_reason": _as_str(item.get("arbiter_reason"), default=""),
        "rollback": bool(item.get("rollback", False)),
        "rollback_reason": _as_str(item.get("rollback_reason"), default=""),
        "rule_prior": _enum(item.get("rule_prior"), {"expected", "suspicious", "unexpected"}, "suspicious"),
        "rule_notes": [_normalize_short_text(x, max_len=160) for x in _as_list(item.get("rule_notes")) if _as_str(x)],
        "arbitration_strategy": _as_str(item.get("arbitration_strategy"), default=""),
        "arbitration_reason": _as_str(item.get("arbitration_reason"), default=""),
        "explain": {
            "rule_signal": _as_str(explain.get("rule_signal"), default=""),
            "rule_summary": _as_str(explain.get("rule_summary"), default=""),
            "llm_summary": _as_str(explain.get("llm_summary"), default=""),
            "final_summary": _as_str(explain.get("final_summary"), default=""),
        },
    }


def validate_final_decision_results(items: Any) -> Tuple[List[Dict[str, Any]], int]:
    records = _as_list(items)
    normalized: List[Dict[str, Any]] = []
    invalid = 0
    for raw in records:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        rec = normalize_final_decision_record(raw)
        if rec["chain_id"] < 0:
            invalid += 1
            continue
        normalized.append(rec)
    return normalized, invalid
