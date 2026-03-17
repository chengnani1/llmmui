# -*- coding: utf-8 -*-
"""
Phase3 semantic pre-stage:
VLM-based multimodal chain semantic parsing (observation only).

Input:
  <processed>/<app>/result.json + chain_*.png + OCR/widgets text summary

Output:
  <processed>/<app>/result_chain_semantics.json
  <processed|app>/chain_semantics_summary.json

Schema (per chain):
{
  "chain_id": 0,
  "ui_task_scene": "...",
  "user_intent": "...",
  "trigger_action": "...",
  "page_observation": "...",
  "visual_evidence": ["...", "..."],
  "permission_task_cues": ["..."],
  "storage_read_cues": ["..."],
  "storage_write_cues": ["..."],
  "location_task_cues": ["..."],
  "upload_task_cues": ["..."],
  "cleanup_task_cues": ["..."],
  "confidence": "high|medium|low",
  "rerun": false,
  "rerun_reason": "",
  "error": ""  # optional
}
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from tqdm import tqdm

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.chain_summary import load_chain_summary_map  # noqa: E402
from configs import settings  # noqa: E402
from configs.domain.scene_config import SCENE_LIST  # noqa: E402
from utils.http_retry import post_json_with_retry  # noqa: E402
from utils.validators import validate_result_json_chains  # noqa: E402


OUTPUT_FILENAME = "result_chain_semantics.json"
SUMMARY_FILENAME = "chain_semantics_summary.json"
OUTPUT_FILENAME_V2 = "result_semantic_v2.json"
SUMMARY_FILENAME_V2 = "semantic_v2_summary.json"
DEFAULT_PROMPT_FILE = os.path.join(settings.PROMPT_DIR, "chain_semantic_interpreter_vision.txt")
PERMISSION_FILENAME = "result_permission.json"

CONF_LEVELS = {"high", "medium", "low"}
SCENE_SET = set(SCENE_LIST)
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

_PERMISSION_UI_TERMS = {
    "权限",
    "授权",
    "允许",
    "拒绝",
    "仅在使用中",
    "始终允许",
    "去授权",
    "系统权限",
}

_SCENE_KEYWORDS = [
    (("登录", "账号", "认证", "验证码", "密码"), "账号与身份认证"),
    (("地图", "定位", "附近", "同城", "导航"), "地图与位置服务"),
    (("搜索", "浏览", "资讯", "内容", "推荐"), "内容浏览与搜索"),
    (("聊天", "消息", "评论", "私信", "社区"), "社交互动与通信"),
    (("扫码", "拍照", "相机", "拍摄"), "媒体拍摄与扫码"),
    (("相册", "上传", "头像", "图片", "照片"), "相册选择与媒体上传"),
    (("商品", "店铺", "购物", "下单", "购买"), "商品浏览与消费"),
    (("支付", "转账", "收款", "账单", "金融"), "支付与金融交易"),
    (("文件", "文档", "导出", "导入", "存储"), "文件与数据管理"),
    (("清理", "加速", "优化", "垃圾", "释放空间"), "设备清理与系统优化"),
    (("wifi", "蓝牙", "网络", "连接", "设备"), "网络连接与设备管理"),
    (("反馈", "客服", "帮助", "问题", "工单"), "用户反馈与客服"),
]

UI_TO_REFINED_BASE = {
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

STORAGE_READ_CUE_RULES = [
    ("select_local_media", ("相册选择", "选择图片", "选择视频", "选择媒体", "选择文件")),
    ("browse_local_file", ("浏览本地", "本地文件", "文件浏览", "打开文件", "读取媒体", "读取文件")),
    ("import_local_file", ("导入", "本地导入", "添加附件", "导入文件", "导入图片", "导入视频")),
]

STORAGE_WRITE_CUE_RULES = [
    ("save_or_export", ("保存", "导出", "另存为", "下载到本地", "写入文件", "写入存储", "落盘")),
    ("edit_write_back", ("编辑后保存", "恢复回写", "回写", "覆盖保存")),
    ("backup_restore_write", ("备份", "恢复文件", "恢复图片", "恢复视频", "恢复到本地")),
    ("cache_local_copy", ("缓存到本地", "离线缓存", "本地副本")),
]

LOCATION_TASK_CUE_RULES = [
    ("map_navigation", ("导航", "路线", "路径", "到这去", "位置导航")),
    ("nearby_search", ("附近", "周边", "同城", "网点", "附近的人", "附近商家")),
    ("location_service", ("定位", "当前位置", "位置服务", "地理位置", "实时位置")),
    ("wifi_or_nearby_scan", ("wifi扫描", "wi-fi扫描", "搜索wifi", "附近设备", "nearby devices", "蓝牙扫描")),
]

UPLOAD_TASK_CUE_RULES = [
    ("upload_media", ("上传图片", "上传视频", "上传文件", "上传头像", "发布", "提交")),
    ("attach_or_send_file", ("附件", "发送文件", "选择媒体", "选择相册", "上传附件")),
]

CLEANUP_TASK_CUE_RULES = [
    ("junk_cleanup", ("垃圾清理", "缓存清理", "清理缓存", "清理垃圾")),
    ("space_cleanup", ("清理空间", "释放空间", "深度清理", "一键清理")),
    ("duplicate_cleanup", ("重复文件", "相似图片", "视频清理", "微信清理", "相册清理")),
    ("optimize_speedup", ("加速", "优化", "手机加速", "内存优化")),
]

STRUCTURED_CUE_FIELDS = (
    "permission_task_cues",
    "storage_read_cues",
    "storage_write_cues",
    "location_task_cues",
    "upload_task_cues",
    "cleanup_task_cues",
)


def _confidence_to_score(label: str) -> float:
    v = str(label or "").strip().lower()
    if v == "high":
        return 0.9
    if v == "medium":
        return 0.65
    return 0.35


def _extract_camera_audio_cues(rec: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    blob = " ".join(
        [
            _as_text(rec.get("user_intent"), max_len=220),
            _as_text(rec.get("trigger_action"), max_len=120),
            _as_text(rec.get("page_observation"), max_len=280),
            " ".join([_as_text(x, max_len=40) for x in _as_list(rec.get("visual_evidence"))[:8] if _as_text(x, max_len=40)]),
        ]
    ).lower()
    camera_terms = ["拍照", "拍摄", "相机", "扫码", "录制视频", "camera", "scan"]
    audio_terms = ["录音", "语音", "音频", "麦克风", "通话", "record_audio", "microphone"]

    camera_hits = [k for k in camera_terms if k in blob]
    audio_hits = [k for k in audio_terms if k in blob]
    camera_cues = ["camera_task_present"] if camera_hits else []
    audio_cues = ["audio_task_present"] if audio_hits else []
    return camera_cues, audio_cues


def to_semantic_v2_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    camera_cues, audio_cues = _extract_camera_audio_cues(rec)
    confidence_label = _as_text(rec.get("confidence"), max_len=10).lower()
    confidence_score = _confidence_to_score(confidence_label)

    out = dict(rec)
    out["task_cues"] = {
        "storage_read": _as_list(rec.get("storage_read_cues")),
        "storage_write": _as_list(rec.get("storage_write_cues")),
        "location": _as_list(rec.get("location_task_cues")),
        "upload": _as_list(rec.get("upload_task_cues")),
        "cleanup": _as_list(rec.get("cleanup_task_cues")),
        "camera": camera_cues,
        "audio": audio_cues,
    }
    # V2 keeps old confidence label in compatibility field while exposing numeric confidence.
    out["confidence_label"] = confidence_label if confidence_label in CONF_LEVELS else "low"
    out["confidence"] = round(confidence_score, 3)
    return out


def _infer_refined_scene(ui_task_scene: str, text_blob: str) -> str:
    scene = str(ui_task_scene or "其他")
    t = str(text_blob or "")

    if scene == "文件与数据管理":
        if any(k in t for k in ["恢复", "找回", "误删", "已恢复", "文档恢复", "图片恢复", "视频恢复"]):
            return "file_recovery"
        if any(k in t for k in ["清理", "垃圾", "加速", "优化", "释放空间"]):
            return "system_cleanup"
        return "file_management"

    if scene == "设备清理与系统优化":
        return "system_cleanup"

    if scene == "相册选择与媒体上传":
        if any(k in t for k in ["上传", "发布", "发送", "头像", "提交"]):
            return "media_upload"
        return "album_selection"

    if scene == "媒体拍摄与扫码":
        return "media_upload"

    if scene == "地图与位置服务":
        return "map_navigation"

    if scene == "网络连接与设备管理":
        return "wifi_scan_or_nearby_devices"

    if scene == "账号与身份认证":
        if any(k in t for k in ["头像", "证件", "实名认证", "人脸", "身份核验"]):
            return "profile_or_identity_upload"
        return "login_verification"

    if scene == "用户反馈与客服":
        return "customer_support"

    if scene == "社交互动与通信":
        return "social_chat_or_share"

    if scene == "内容浏览与搜索":
        return "content_browsing"

    return UI_TO_REFINED_BASE.get(scene, "content_browsing")


def _normalize_refined_scene(v: Any, ui_task_scene: str, text_blob: str) -> str:
    s = _as_text(v, max_len=64).strip().lower()
    if s in REFINED_SCENE_SET:
        return s
    return _infer_refined_scene(ui_task_scene, text_blob)


def load_prompt_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def extract_json_obj(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    s = text.strip()
    s = re.sub(r"^```(?:json)?\n", "", s, flags=re.I)
    s = re.sub(r"```$", "", s).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj[0]
    except Exception:
        pass

    left, right = s.find("{"), s.rfind("}")
    if left != -1 and right != -1 and right > left:
        try:
            obj = json.loads(s[left : right + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            return {}
    return {}


def _as_text(v: Any, max_len: int = 240) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def _as_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, (tuple, set)):
        return list(v)
    if v is None:
        return []
    return [v]


def _clean_scene(scene: Any) -> str:
    s = _as_text(scene, max_len=40)
    if s in SCENE_SET:
        return s

    alias = {
        "账号认证": "账号与身份认证",
        "地图定位": "地图与位置服务",
        "浏览搜索": "内容浏览与搜索",
        "社交通信": "社交互动与通信",
        "拍摄扫码": "媒体拍摄与扫码",
        "相册上传": "相册选择与媒体上传",
        "商品消费": "商品浏览与消费",
        "支付交易": "支付与金融交易",
        "文件管理": "文件与数据管理",
        "设备清理": "设备清理与系统优化",
        "网络设备": "网络连接与设备管理",
        "反馈客服": "用户反馈与客服",
        "other": "其他",
        "others": "其他",
    }
    low = s.lower()
    if low in alias:
        return alias[low]
    if s in alias:
        return alias[s]
    return "其他"


def _contains_perm_ui_word(text: str) -> bool:
    if not text:
        return False
    return any(w in text for w in _PERMISSION_UI_TERMS)


def _dedupe_keep_order(items: List[str], max_items: int) -> List[str]:
    out: List[str] = []
    for x in items:
        if not isinstance(x, str):
            continue
        v = x.strip()
        if not v:
            continue
        if v not in out:
            out.append(v)
        if len(out) >= max_items:
            break
    return out


def _match_cue_rules(text: str, rules: List[Tuple[str, Tuple[str, ...]]], max_items: int = 8) -> List[str]:
    if not text:
        return []
    blob = text.lower()
    out: List[str] = []
    for cue_key, keywords in rules:
        if any(str(k).lower() in blob for k in keywords):
            out.append(cue_key)
        if len(out) >= max_items:
            break
    return _dedupe_keep_order(out, max_items=max_items)


def _extract_structured_cues(
    user_intent: str,
    trigger_action: str,
    page_observation: str,
    visual_evidence: List[str],
    widgets: List[str],
    ocr_triplet: List[str],
) -> Dict[str, List[str]]:
    text_blob = " ".join(
        [
            _as_text(user_intent, max_len=260),
            _as_text(trigger_action, max_len=120),
            _as_text(page_observation, max_len=320),
            " ".join([_as_text(x, max_len=40) for x in visual_evidence[:10]]),
            " ".join([_as_text(x, max_len=40) for x in widgets[:16]]),
            " ".join([_as_text(x, max_len=320) for x in ocr_triplet[:3]]),
        ]
    )

    storage_read_cues = _match_cue_rules(text_blob, STORAGE_READ_CUE_RULES, max_items=6)
    storage_write_cues = _match_cue_rules(text_blob, STORAGE_WRITE_CUE_RULES, max_items=6)
    location_task_cues = _match_cue_rules(text_blob, LOCATION_TASK_CUE_RULES, max_items=6)
    upload_task_cues = _match_cue_rules(text_blob, UPLOAD_TASK_CUE_RULES, max_items=6)
    cleanup_task_cues = _match_cue_rules(text_blob, CLEANUP_TASK_CUE_RULES, max_items=6)

    permission_task_cues = _dedupe_keep_order(
        storage_read_cues + storage_write_cues + location_task_cues + upload_task_cues + cleanup_task_cues,
        max_items=12,
    )
    return {
        "permission_task_cues": permission_task_cues,
        "storage_read_cues": storage_read_cues,
        "storage_write_cues": storage_write_cues,
        "location_task_cues": location_task_cues,
        "upload_task_cues": upload_task_cues,
        "cleanup_task_cues": cleanup_task_cues,
    }


def _merge_cue_lists(primary: Any, secondary: Any, max_items: int = 12) -> List[str]:
    p = [_as_text(x, max_len=60) for x in _as_list(primary) if _as_text(x, max_len=60)]
    s = [_as_text(x, max_len=60) for x in _as_list(secondary) if _as_text(x, max_len=60)]
    return _dedupe_keep_order(p + s, max_items=max_items)


def _tokens_from_text(text: str, max_items: int = 12) -> List[str]:
    chunks = re.split(r"[\\s,;，。！？、|/]+", text or "")
    out: List[str] = []
    for c in chunks:
        c = c.strip()
        if len(c) < 2 or len(c) > 24:
            continue
        if c not in out:
            out.append(c)
        if len(out) >= max_items:
            break
    return out


def _infer_scene_from_text(all_text: str) -> str:
    txt = all_text or ""
    for terms, scene in _SCENE_KEYWORDS:
        if any(t in txt for t in terms):
            return scene
    return "其他"


def _pick_trigger_action(top_widgets: List[Any], fallback_scene: str) -> str:
    candidates: List[str] = []
    for w in top_widgets[:16]:
        s = _as_text(w, max_len=30)
        if not s or _contains_perm_ui_word(s):
            continue
        candidates.append(s)

    for s in candidates:
        if s.startswith(("点击", "切换", "输入", "选择", "上传", "开始", "打开", "搜索", "浏览", "查看", "使用")):
            return s

    if candidates:
        return candidates[0]

    default_by_scene = {
        "地图与位置服务": "查看附近内容",
        "相册选择与媒体上传": "选择并上传图片",
        "媒体拍摄与扫码": "点击拍摄或扫码入口",
        "文件与数据管理": "浏览本地文件",
        "设备清理与系统优化": "开始清理或优化",
    }
    return default_by_scene.get(fallback_scene, "unknown")


def _build_visual_evidence(chain_summary: Dict[str, Any]) -> List[str]:
    before = _as_text(chain_summary.get("before_text", ""), max_len=320)
    granting = _as_text(chain_summary.get("granting_text", ""), max_len=320)
    after = _as_text(chain_summary.get("after_text", ""), max_len=320)
    widgets = [
        _as_text(x, max_len=32)
        for x in (chain_summary.get("top_widgets", []) if isinstance(chain_summary.get("top_widgets", []), list) else [])[:12]
    ]
    widgets = [x for x in widgets if x]

    out: List[str] = []
    out.extend(_tokens_from_text(before, max_items=4))
    out.extend(_tokens_from_text(granting, max_items=4))
    out.extend(_tokens_from_text(after, max_items=4))
    out.extend(widgets[:6])
    return _dedupe_keep_order(out, max_items=8)


def _default_semantics(chain_summary: Dict[str, Any], permissions_hint: List[str]) -> Dict[str, Any]:
    before = _as_text(chain_summary.get("before_text", ""), max_len=320)
    granting = _as_text(chain_summary.get("granting_text", ""), max_len=320)
    after = _as_text(chain_summary.get("after_text", ""), max_len=320)
    widgets = chain_summary.get("top_widgets", []) if isinstance(chain_summary.get("top_widgets", []), list) else []
    widget_texts = [_as_text(x, max_len=40) for x in widgets[:16] if _as_text(x, max_len=40)]

    scene = _infer_scene_from_text(" ".join([before, granting, after, " ".join(widget_texts[:12])]))
    trigger_action = _pick_trigger_action(widgets, scene)
    text_blob = " ".join([before, granting, after, " ".join(widget_texts[:12])])
    refined_scene = _infer_refined_scene(scene, text_blob)
    user_intent = f"用户希望在当前页面进行{scene}相关操作。"
    page_observation = _as_text(
        " ".join(
            [
                f"页面主要呈现{scene}相关内容。",
                "系统权限请求弹窗出现。",
                granting[:120],
            ]
        ),
        max_len=260,
    )
    evidence = _build_visual_evidence(chain_summary)

    # Add short permission cue as objective evidence only.
    if permissions_hint:
        evidence = _dedupe_keep_order(evidence + [f"权限请求:{','.join(permissions_hint[:3])}"], max_items=8)

    cues = _extract_structured_cues(
        user_intent=user_intent,
        trigger_action=trigger_action,
        page_observation=page_observation,
        visual_evidence=evidence,
        widgets=widget_texts,
        ocr_triplet=[before, granting, after],
    )

    return {
        "ui_task_scene": scene,
        "refined_scene": refined_scene,
        "user_intent": user_intent,
        "trigger_action": trigger_action,
        "page_observation": page_observation,
        "visual_evidence": evidence or ["页面出现系统权限请求弹窗"],
        "permission_task_cues": cues["permission_task_cues"],
        "storage_read_cues": cues["storage_read_cues"],
        "storage_write_cues": cues["storage_write_cues"],
        "location_task_cues": cues["location_task_cues"],
        "upload_task_cues": cues["upload_task_cues"],
        "cleanup_task_cues": cues["cleanup_task_cues"],
        "confidence": "low",
    }


def _build_input_payload(
    chain_id: int,
    chain: Dict[str, Any],
    chain_summary_obj: Dict[str, Any],
    image_path: str,
    permissions_hint: List[str],
) -> Dict[str, Any]:
    fallback = _default_semantics(chain_summary_obj, permissions_hint)
    return {
        "chain_id": chain_id,
        "package": chain.get("package") or chain.get("pkg") or "",
        "chain_image": {
            "path": image_path,
            "exists": os.path.exists(image_path),
            "note": "The model must use this screenshot as primary visual evidence.",
        },
        "ocr_text": {
            "before_text": _as_text(chain_summary_obj.get("before_text", ""), max_len=700),
            "granting_text": _as_text(chain_summary_obj.get("granting_text", ""), max_len=700),
            "after_text": _as_text(chain_summary_obj.get("after_text", ""), max_len=700),
        },
        "widgets": [
            _as_text(x, max_len=40)
            for x in (chain_summary_obj.get("top_widgets", []) if isinstance(chain_summary_obj.get("top_widgets", []), list) else [])[:20]
            if _as_text(x, max_len=40)
        ],
        "permissions_hint": permissions_hint[:10],
        "output_schema": {
            "ui_task_scene": "from fixed taxonomy",
            "refined_scene": "from refined taxonomy: login_verification|profile_or_identity_upload|file_management|file_recovery|system_cleanup|album_selection|media_upload|map_navigation|wifi_scan_or_nearby_devices|content_browsing|customer_support|social_chat_or_share",
            "user_intent": "short intent sentence",
            "trigger_action": "most likely user action before permission prompt",
            "page_observation": "concise objective page observation",
            "visual_evidence": ["3-8 concise UI clues"],
            "permission_task_cues": ["optional cue tags"],
            "storage_read_cues": ["optional cue tags"],
            "storage_write_cues": ["optional cue tags"],
            "location_task_cues": ["optional cue tags"],
            "upload_task_cues": ["optional cue tags"],
            "cleanup_task_cues": ["optional cue tags"],
        },
        "fallback_hints": fallback,
    }


def normalize_semantics_record(
    chain_id: int,
    obj: Dict[str, Any],
    fallback: Dict[str, Any],
    rerun: bool,
    rerun_reason: str,
    error: str = "",
) -> Dict[str, Any]:
    # Accept a few key aliases for robustness.
    scene = _clean_scene(
        obj.get("ui_task_scene")
        or obj.get("scene")
        or obj.get("predicted_scene")
        or fallback.get("ui_task_scene")
    )
    text_blob = " ".join(
        [
            _as_text(obj.get("user_intent") or obj.get("intent"), max_len=200),
            _as_text(obj.get("page_observation") or obj.get("page_function"), max_len=260),
            _as_text(obj.get("trigger_action"), max_len=80),
            _as_text(fallback.get("user_intent"), max_len=200),
            _as_text(fallback.get("page_observation"), max_len=260),
            " ".join([_as_text(x, max_len=30) for x in _as_list(obj.get("visual_evidence"))[:8]]),
        ]
    )
    refined_scene = _normalize_refined_scene(
        obj.get("refined_scene") or obj.get("scene_refined"),
        ui_task_scene=scene,
        text_blob=text_blob,
    )
    intent = _as_text(obj.get("user_intent") or obj.get("intent") or fallback.get("user_intent"), max_len=220)
    trigger = _as_text(obj.get("trigger_action") or fallback.get("trigger_action"), max_len=80)
    page_observation = _as_text(
        obj.get("page_observation")
        or obj.get("page_function")
        or fallback.get("page_observation"),
        max_len=280,
    )

    ve_raw = obj.get("visual_evidence")
    if not isinstance(ve_raw, list):
        ve_raw = []
        evidence = obj.get("evidence") if isinstance(obj.get("evidence"), dict) else {}
        ve_raw.extend(evidence.get("keywords") if isinstance(evidence.get("keywords"), list) else [])
        ve_raw.extend(evidence.get("widgets") if isinstance(evidence.get("widgets"), list) else [])
    visual_evidence = _dedupe_keep_order([_as_text(x, max_len=40) for x in ve_raw if _as_text(x, max_len=40)], max_items=8)

    if not intent:
        intent = fallback.get("user_intent", "用户希望完成当前页面任务。")
    if not trigger:
        trigger = fallback.get("trigger_action", "unknown")
    if not page_observation:
        page_observation = fallback.get("page_observation", "页面出现系统权限请求弹窗。")
    if not visual_evidence:
        visual_evidence = fallback.get("visual_evidence", ["页面出现系统权限请求弹窗"])

    confidence = _as_text(obj.get("confidence") or fallback.get("confidence"), max_len=10).lower()
    if confidence not in CONF_LEVELS:
        confidence = "low"

    widget_terms = [_as_text(x, max_len=40) for x in _as_list(obj.get("widgets"))[:16] if _as_text(x, max_len=40)]
    extracted_cues = _extract_structured_cues(
        user_intent=intent,
        trigger_action=trigger,
        page_observation=page_observation,
        visual_evidence=visual_evidence,
        widgets=widget_terms,
        ocr_triplet=[text_blob],
    )

    cue_values: Dict[str, List[str]] = {}
    for field in STRUCTURED_CUE_FIELDS:
        merged = _merge_cue_lists(obj.get(field), fallback.get(field), max_items=12)
        merged = _merge_cue_lists(merged, extracted_cues.get(field, []), max_items=12)
        cue_values[field] = merged

    rec = {
        "chain_id": chain_id,
        "ui_task_scene": scene,
        "refined_scene": refined_scene,
        "user_intent": intent,
        "trigger_action": trigger,
        "page_observation": page_observation,
        "visual_evidence": visual_evidence,
        "confidence": confidence,
        "rerun": bool(rerun),
        "rerun_reason": _as_text(rerun_reason, max_len=120),
        "permission_task_cues": cue_values["permission_task_cues"],
        "storage_read_cues": cue_values["storage_read_cues"],
        "storage_write_cues": cue_values["storage_write_cues"],
        "location_task_cues": cue_values["location_task_cues"],
        "upload_task_cues": cue_values["upload_task_cues"],
        "cleanup_task_cues": cue_values["cleanup_task_cues"],
    }
    if error:
        rec["error"] = _as_text(error, max_len=240)
    return rec


def should_rerun(rec: Dict[str, Any]) -> str:
    if rec.get("ui_task_scene") not in SCENE_SET:
        return "scene_not_in_taxonomy"
    if rec.get("refined_scene") not in REFINED_SCENE_SET:
        return "refined_scene_not_in_taxonomy"
    if len(_as_text(rec.get("user_intent", ""), max_len=240)) < 6:
        return "intent_too_short"
    if not _as_text(rec.get("trigger_action", ""), max_len=80):
        return "missing_trigger_action"
    if len(_as_text(rec.get("page_observation", ""), max_len=280)) < 6:
        return "missing_page_observation"
    if not isinstance(rec.get("visual_evidence"), list) or not rec.get("visual_evidence"):
        return "missing_visual_evidence"
    return ""


def build_prompt(template: str, input_payload: Dict[str, Any], strict: bool) -> str:
    prompt = template.replace("{INPUT_JSON}", json.dumps(input_payload, ensure_ascii=False, indent=2))
    if strict:
        prompt += (
            "\n\n【重试补充要求】\n"
            "1) ui_task_scene 必须从固定 taxonomy 选择；无法判断时输出“其他”。\n"
            "2) refined_scene 必须从给定 refined taxonomy 选择。\n"
            "3) user_intent 需为简洁目标句，长度至少 8 个字。\n"
            "4) trigger_action 必须是具体动作，无法判断时写 unknown。\n"
            "5) page_observation 必须是客观页面观察描述。\n"
            "6) visual_evidence 输出 3~8 个短语。\n"
            "7) 只输出严格 JSON，不要额外文字。\n"
        )
    return prompt


def encode_image_base64(path: str) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_vllm_vl(prompt: str, image_path: str, vllm_url: str, model: str) -> str:
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

    image_b64 = encode_image_base64(image_path)
    payload_legacy: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    if image_b64:
        payload_legacy["images"] = [image_b64]

    payload_openai_mm: Dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ]
                if image_b64
                else [{"type": "text", "text": prompt}],
            }
        ],
        "temperature": 0,
    }

    errors: List[str] = []
    for payload in [payload_legacy, payload_openai_mm]:
        try:
            r = post_json_with_retry(
                vllm_url,
                payload,
                timeout=settings.LLM_RESPONSE_TIMEOUT,
                max_retries=2,
                backoff_factor=1.5,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            detail = str(exc)
            if isinstance(exc, requests.HTTPError) and getattr(exc, "response", None) is not None:
                resp = exc.response
                body = ""
                try:
                    body = resp.text[:300]
                except Exception:
                    body = ""
                detail = f"HTTP {resp.status_code}: {body}"
            errors.append(detail)
            continue

    raise RuntimeError(" | ".join(errors) if errors else "vlm_call_failed")


def infer_chain_semantics(
    chain_id: int,
    image_path: str,
    input_payload: Dict[str, Any],
    prompt_template: str,
    vllm_url: str,
    model: str,
    single_pass_only: bool = False,
) -> Dict[str, Any]:
    ocr = input_payload.get("ocr_text", {}) if isinstance(input_payload.get("ocr_text", {}), dict) else {}
    fallback_source = {
        "before_text": ocr.get("before_text", ""),
        "granting_text": ocr.get("granting_text", ""),
        "after_text": ocr.get("after_text", ""),
        "top_widgets": input_payload.get("widgets", []),
    }
    fallback = _default_semantics(fallback_source, input_payload.get("permissions_hint", []))
    try:
        raw = call_vllm_vl(build_prompt(prompt_template, input_payload, strict=False), image_path, vllm_url, model)
        obj = extract_json_obj(raw)
        rec = normalize_semantics_record(
            chain_id=chain_id,
            obj=obj,
            fallback=fallback,
            rerun=False,
            rerun_reason="",
        )
        reason = should_rerun(rec)
        if single_pass_only or not reason:
            return rec

        raw2 = call_vllm_vl(build_prompt(prompt_template, input_payload, strict=True), image_path, vllm_url, model)
        obj2 = extract_json_obj(raw2)
        rec2 = normalize_semantics_record(
            chain_id=chain_id,
            obj=obj2,
            fallback=fallback,
            rerun=True,
            rerun_reason=reason,
        )
        reason2 = should_rerun(rec2)
        if reason2:
            return normalize_semantics_record(
                chain_id=chain_id,
                obj={},
                fallback=fallback,
                rerun=True,
                rerun_reason=reason2,
                error=f"rerun_failed:{reason2}",
            )
        return rec2
    except Exception as exc:
        print(f"[ChainSemantic][WARN] chain_id={chain_id} vllm_failed: {exc}")
        return normalize_semantics_record(
            chain_id=chain_id,
            obj={},
            fallback=fallback,
            rerun=False,
            rerun_reason=f"exception:{type(exc).__name__}",
            error=str(exc),
        )


def iter_app_dirs(target: str) -> List[str]:
    if os.path.exists(os.path.join(target, "result.json")):
        return [target]
    out = []
    for d in sorted(os.listdir(target)):
        app_dir = os.path.join(target, d)
        if os.path.isdir(app_dir) and os.path.exists(os.path.join(app_dir, "result.json")):
            out.append(app_dir)
    return out


def _load_permission_map(app_dir: str) -> Dict[int, List[str]]:
    path = os.path.join(app_dir, PERMISSION_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    out: Dict[int, List[str]] = {}
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("chain_id"))
        except Exception:
            continue
        perms = item.get("predicted_permissions", [])
        if isinstance(perms, list):
            out[cid] = [_as_text(x, max_len=60) for x in perms if _as_text(x, max_len=60)]
    return out


def process_app(
    app_dir: str,
    prompt_template: str,
    vllm_url: str,
    model: str,
    output_filename: str = OUTPUT_FILENAME,
    schema_version: str = "v1",
    single_pass_only: bool = False,
    chain_filter: Optional[Set[int]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    result_json_path = os.path.join(app_dir, "result.json")
    with open(result_json_path, "r", encoding="utf-8") as f:
        chains = validate_result_json_chains(json.load(f))

    permission_map = _load_permission_map(app_dir)
    summary_map = load_chain_summary_map(result_json_path, permissions_map=permission_map)

    out: List[Dict[str, Any]] = []
    low_conf = 0

    for idx, chain in enumerate(tqdm(chains, desc=f"ChainSemantic {os.path.basename(app_dir)}", ncols=90)):
        chain_id = int(chain.get("chain_id", idx))
        if chain_filter is not None and chain_id not in chain_filter:
            continue

        image_path = os.path.join(app_dir, f"chain_{chain_id}.png")
        chain_summary_obj = summary_map.get(chain_id, {"chain_summary": {}}).get("chain_summary", {})
        if not isinstance(chain_summary_obj, dict):
            chain_summary_obj = {}

        permissions_hint = permission_map.get(chain_id) or chain.get("predicted_permissions") or chain.get("true_permissions") or []
        permissions_hint = [
            _as_text(x, max_len=60)
            for x in permissions_hint
            if _as_text(x, max_len=60)
        ]

        input_payload = _build_input_payload(
            chain_id=chain_id,
            chain=chain,
            chain_summary_obj=chain_summary_obj,
            image_path=image_path,
            permissions_hint=permissions_hint,
        )
        rec = infer_chain_semantics(
            chain_id,
            image_path,
            input_payload,
            prompt_template,
            vllm_url,
            model,
            single_pass_only=single_pass_only,
        )
        rec["permissions_hint"] = permissions_hint
        if rec.get("confidence") == "low":
            low_conf += 1
        out.append(rec)

    out.sort(key=lambda x: int(x.get("chain_id", -1)))
    records_for_output = out if schema_version != "v2" else [to_semantic_v2_record(x) for x in out]
    out_path = os.path.join(app_dir, output_filename)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records_for_output, f, ensure_ascii=False, indent=2)

    print(f"[ChainSemantic] finish app={app_dir} chains={len(out)} low_conf={low_conf} out={out_path}")
    return records_for_output, low_conf


def _parse_chain_ids(chain_ids: Optional[List[int]]) -> Optional[Set[int]]:
    if not chain_ids:
        return None
    out: Set[int] = set()
    for x in chain_ids:
        try:
            out.add(int(x))
        except Exception:
            continue
    return out if out else None


def build_summary(records: List[Dict[str, Any]], apps_processed: int, low_conf_count: int) -> Dict[str, Any]:
    total = len(records)
    conf_counter = Counter()
    scene_counter = Counter()
    refined_scene_counter = Counter()
    trigger_counter = Counter()
    rerun_counter = Counter()
    low_scene_counter = Counter()

    for rec in records:
        conf = _as_text(rec.get("confidence_label"), max_len=10).lower()
        if conf not in CONF_LEVELS:
            raw_conf = rec.get("confidence")
            try:
                score = float(raw_conf)
            except Exception:
                score = -1.0
            if score >= 0.8:
                conf = "high"
            elif score >= 0.5:
                conf = "medium"
            else:
                conf = "low"
        scene = _as_text(rec.get("ui_task_scene", "其他"), max_len=30) or "其他"
        trigger = _as_text(rec.get("trigger_action", ""), max_len=80)
        refined_scene = _as_text(rec.get("refined_scene", "content_browsing"), max_len=64) or "content_browsing"
        rerun_reason = _as_text(rec.get("rerun_reason", ""), max_len=120)

        conf_counter[conf] += 1
        scene_counter[scene] += 1
        refined_scene_counter[refined_scene] += 1
        if trigger:
            trigger_counter[trigger] += 1
        if rec.get("rerun"):
            rerun_counter[rerun_reason or "rerun_true_no_reason"] += 1
        if conf == "low":
            low_scene_counter[scene] += 1

    return {
        "apps_processed": apps_processed,
        "total_chains": total,
        "low_conf_count": low_conf_count,
        "confidence_distribution": [
            {"confidence": k, "count": conf_counter[k], "ratio": round(conf_counter[k] / total, 4) if total else 0.0}
            for k in ["high", "medium", "low"]
        ],
        "scene_distribution": [
            {"ui_task_scene": k, "count": v, "ratio": round(v / total, 4) if total else 0.0}
            for k, v in scene_counter.most_common()
        ],
        "refined_scene_distribution": [
            {"refined_scene": k, "count": v, "ratio": round(v / total, 4) if total else 0.0}
            for k, v in refined_scene_counter.most_common()
        ],
        "top_trigger_actions": [{"trigger_action": k, "count": v} for k, v in trigger_counter.most_common(20)],
        "low_conf_distribution": [{"ui_task_scene": k, "count": v} for k, v in low_scene_counter.most_common(20)],
        "rerun_distribution": [{"reason": k, "count": v} for k, v in rerun_counter.most_common()],
    }


def run(
    target: str,
    prompt_file: str,
    vllm_url: str,
    model: str,
    output_filename: str = OUTPUT_FILENAME,
    summary_filename: str = SUMMARY_FILENAME,
    schema_version: str = "v1",
    single_pass_only: bool = False,
    chain_ids: Optional[List[int]] = None,
) -> None:
    prompt_template = load_prompt_template(prompt_file)
    app_dirs = iter_app_dirs(target)
    chain_filter = _parse_chain_ids(chain_ids)

    all_records: List[Dict[str, Any]] = []
    low_conf_total = 0
    for app_dir in app_dirs:
        try:
            records, low_conf = process_app(
                app_dir=app_dir,
                prompt_template=prompt_template,
                vllm_url=vllm_url,
                model=model,
                output_filename=output_filename,
                schema_version=schema_version,
                single_pass_only=single_pass_only,
                chain_filter=chain_filter,
            )
            all_records.extend(records)
            low_conf_total += low_conf
        except Exception as exc:
            print(f"[ChainSemantic][WARN] app failed app={app_dir} err={exc}")

    summary = build_summary(all_records, apps_processed=len(app_dirs), low_conf_count=low_conf_total)
    summary_dir = target if not os.path.exists(os.path.join(target, "result.json")) else os.path.dirname(target)
    summary_path = os.path.join(summary_dir, summary_filename)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[ChainSemantic] done apps={len(app_dirs)} total_chains={len(all_records)} summary={summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VLM multimodal chain semantic interpreter")
    parser.add_argument("target", help="processed root or one app dir")
    parser.add_argument("--prompt-file", default=DEFAULT_PROMPT_FILE)
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_VL_URL", settings.VLLM_VL_URL))
    parser.add_argument("--model", default=os.getenv("VLLM_VL_MODEL", settings.VLLM_VL_MODEL))
    parser.add_argument("--output-filename", default=OUTPUT_FILENAME)
    parser.add_argument("--summary-filename", default=SUMMARY_FILENAME)
    parser.add_argument("--schema-version", choices=["v1", "v2"], default="v1")
    parser.add_argument("--single-pass-only", action="store_true", help="disable rerun; exactly one VLM call per chain")
    parser.add_argument("--chain-ids", default="", help="comma-separated chain ids, e.g. 1,3,9")
    args = parser.parse_args()

    chain_ids: List[int] = []
    if args.chain_ids.strip():
        for seg in args.chain_ids.split(","):
            seg = seg.strip()
            if not seg:
                continue
            try:
                chain_ids.append(int(seg))
            except Exception:
                continue

    run(
        target=args.target,
        prompt_file=args.prompt_file,
        vllm_url=args.vllm_url,
        model=args.model,
        output_filename=args.output_filename,
        summary_filename=args.summary_filename,
        schema_version=args.schema_version,
        single_pass_only=args.single_pass_only,
        chain_ids=chain_ids or None,
    )
