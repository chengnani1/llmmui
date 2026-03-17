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
  "page_observation": "...",
  "page_elements": {"buttons": [], "labels": [], "indicators": [], "dialogs": []},
  "evidence": {"observations": [], "interactions": [], "inferences": []},
  "scene": {"ui_task_scene": "...", "refined_scene": "...", "confidence": 0.0},
  "page_semantics": {"page_type": "...", "primary_function": "...", "user_goal": "...", "interaction_flow": []},
  "permission_context": {"permissions": [], "relevance_to_page_function": "...", "relevance_to_user_goal": "..."}
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
REFINED_SCENE_V1_TO_LEGACY = {
    "login_verification": "login_verification",
    "profile_or_identity_update": "profile_or_identity_upload",
    "file_management": "file_management",
    "file_recovery": "file_recovery",
    "system_cleanup": "system_cleanup",
    "album_selection": "album_selection",
    "media_upload": "media_upload",
    "media_capture_or_recording": "media_upload",
    "map_navigation": "map_navigation",
    "nearby_service_or_wifi_scan": "wifi_scan_or_nearby_devices",
    "content_browsing": "content_browsing",
    "customer_support": "customer_support",
    "social_chat_or_share": "social_chat_or_share",
    "other": "content_browsing",
}

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
    (("录音", "清唱", "k歌", "K歌", "配音", "语音创作", "音频作品", "麦克风"), "音频录制与创作"),
    (("扫码", "拍照", "相机", "拍摄", "录像", "视频录制"), "图像视频拍摄与扫码"),
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
    "音频录制与创作": "media_capture_or_recording",
    "图像视频拍摄与扫码": "media_capture_or_recording",
    "媒体拍摄与扫码": "media_capture_or_recording",
    "相册选择与媒体上传": "album_selection",
    "商品浏览与消费": "content_browsing",
    "支付与金融交易": "login_verification",
    "文件与数据管理": "file_management",
    "设备清理与系统优化": "system_cleanup",
    "网络连接与设备管理": "nearby_service_or_wifi_scan",
    "用户反馈与客服": "customer_support",
    "其他": "other",
}

STORAGE_READ_CUE_RULES = [
    ("album_selection_present", ("相册选择", "选择图片", "选择视频", "选择媒体", "选择文件")),
    ("local_file_browser_present", ("浏览本地", "本地文件", "文件浏览", "打开文件", "读取媒体", "读取文件")),
    ("local_import_entry_present", ("导入", "本地导入", "添加附件", "导入文件", "导入图片", "导入视频")),
]

STORAGE_WRITE_CUE_RULES = [
    ("save_to_local_action_present", ("保存", "另存为", "下载到本地", "写入文件", "写入存储", "落盘")),
    ("export_action_present", ("导出", "分享到本地", "生成文件")),
    ("restore_to_local_action_present", ("编辑后保存", "恢复回写", "回写", "覆盖保存", "恢复文件", "恢复图片", "恢复视频", "恢复到本地")),
    ("offline_cache_write_present", ("缓存到本地", "离线缓存", "本地副本")),
]

LOCATION_TASK_CUE_RULES = [
    ("navigation_intent_present", ("导航", "路线", "路径", "到这去", "位置导航")),
    ("nearby_service_intent_present", ("附近", "周边", "同城", "网点", "附近的人", "附近商家")),
    ("location_service_context_present", ("定位", "当前位置", "位置服务", "地理位置", "实时位置")),
    ("wifi_scan_intent_present", ("wifi扫描", "wi-fi扫描", "搜索wifi", "附近设备", "nearby devices", "蓝牙扫描")),
]

UPLOAD_TASK_CUE_RULES = [
    ("upload_entry_present", ("上传图片", "上传视频", "上传文件", "上传头像", "上传附件")),
    ("submit_or_publish_action_present", ("发布", "提交", "发送", "确认上传")),
    ("attachment_send_action_present", ("附件", "发送文件", "选择媒体", "选择相册")),
]

CLEANUP_TASK_CUE_RULES = [
    ("cleanup_action_present", ("垃圾清理", "缓存清理", "清理缓存", "清理垃圾")),
    ("storage_release_action_present", ("清理空间", "释放空间", "深度清理", "一键清理")),
    ("duplicate_cleanup_action_present", ("重复文件", "相似图片", "视频清理", "微信清理", "相册清理")),
    ("device_optimize_action_present", ("加速", "优化", "手机加速", "内存优化")),
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


def _confidence_score_to_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _scene_terms(text: str) -> Dict[str, List[str]]:
    t = str(text or "").lower()
    groups: Dict[str, Tuple[str, ...]] = {
        "login": ("登录", "账号", "认证", "验证码", "密码", "手机号"),
        "identity_update": ("头像", "实名认证", "证件", "人脸", "身份核验", "资料完善", "昵称"),
        "file_recovery": ("恢复", "找回", "误删", "已恢复", "文档恢复", "图片恢复", "视频恢复", "回收站"),
        "cleanup": ("清理", "垃圾", "加速", "优化", "释放空间", "缓存清理", "重复文件"),
        "album": ("相册", "选择图片", "选择视频", "本地图片", "本地视频"),
        "upload": ("上传", "发布", "发送", "提交", "附件"),
        "capture": ("拍照", "拍摄", "扫码", "录像", "录制视频", "扫描二维码", "camera", "scan"),
        "audio_record": ("录音", "录制音频", "麦克风", "语音输入", "record_audio", "microphone"),
        "map_nav": ("地图", "导航", "路线", "到这去", "位置导航"),
        "nearby_or_wifi": ("附近", "周边", "同城", "wifi", "wi-fi", "蓝牙", "附近设备", "nearby"),
        "chat_or_share": ("聊天", "消息", "私信", "分享", "发送给好友"),
        "support": ("客服", "反馈", "帮助中心", "工单"),
        "browse": ("浏览", "搜索", "推荐", "资讯", "内容"),
    }
    out: Dict[str, List[str]] = {}
    for key, terms in groups.items():
        hits = [term for term in terms if term in t]
        out[key] = hits
    return out


def _extract_camera_audio_cues(rec: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    blob = " ".join(
        [
            _as_text(rec.get("user_intent"), max_len=220),
            _as_text(rec.get("trigger_action"), max_len=120),
            _as_text(rec.get("page_observation"), max_len=320),
            _as_text(rec.get("scene_reason"), max_len=240),
            " ".join([_as_text(x, max_len=40) for x in _as_list(rec.get("visual_evidence"))[:10] if _as_text(x, max_len=40)]),
            " ".join([_as_text(x, max_len=60) for x in _as_list(rec.get("supporting_evidence"))[:8] if _as_text(x, max_len=60)]),
        ]
    ).lower()
    terms = _scene_terms(blob)

    camera_cues: List[str] = []
    audio_cues: List[str] = []
    if terms["capture"] or ("相机" in blob):
        camera_cues.append("camera_entry_present")
    if any(x in blob for x in ["拍照", "拍摄", "扫码", "录像", "开始拍摄", "开始录制视频"]):
        camera_cues.append("capture_button_present")
    if any(x in blob for x in ["扫码", "扫描二维码", "scan"]):
        camera_cues.append("scan_mode_present")
    if any(x in blob for x in ["录制视频", "录像中", "视频录制"]):
        camera_cues.append("video_recording_indicator_present")
    if any(x in blob for x in ["相机权限", "camera permission", "拍摄照片和录制视频"]):
        camera_cues.append("camera_permission_context_present")

    if terms["audio_record"] or ("语音" in blob):
        audio_cues.append("record_button_present")
    if any(x in blob for x in ["录音中", "录制中", "波形", "计时"]):
        audio_cues.append("recording_indicator_present")
    if any(x in blob for x in ["麦克风", "microphone", "record_audio"]):
        audio_cues.append("microphone_usage_context_present")
    if any(x in blob for x in ["语音消息", "语音发送", "通话"]):
        audio_cues.append("voice_message_context_present")
    if any(x in blob for x in ["清唱", "k歌", "K歌", "配音", "语音创作", "音频作品"]):
        audio_cues.append("singing_or_voice_creation_context_present")

    return _dedupe_keep_order(camera_cues, max_items=8), _dedupe_keep_order(audio_cues, max_items=8)


def _infer_refined_scene(ui_task_scene: str, text_blob: str) -> str:
    scene = str(ui_task_scene or "其他")
    t = str(text_blob or "")
    terms = _scene_terms(t)

    if scene == "文件与数据管理":
        if terms["file_recovery"]:
            return "file_recovery"
        if terms["cleanup"]:
            return "system_cleanup"
        return "file_management"

    if scene == "设备清理与系统优化":
        return "system_cleanup"

    if scene == "相册选择与媒体上传":
        if terms["upload"]:
            return "media_upload"
        return "album_selection"

    if scene in {"图像视频拍摄与扫码", "媒体拍摄与扫码"}:
        if terms["capture"] or terms["audio_record"]:
            return "media_capture_or_recording"
        if terms["upload"]:
            return "media_upload"
        return "media_capture_or_recording"

    if scene == "音频录制与创作":
        if terms["audio_record"] or any(k in t for k in ["录音", "清唱", "k歌", "K歌", "配音"]):
            return "media_capture_or_recording"
        return "other"

    if scene == "地图与位置服务":
        if terms["nearby_or_wifi"] and not terms["map_nav"]:
            return "nearby_service_or_wifi_scan"
        return "map_navigation"

    if scene == "网络连接与设备管理":
        return "nearby_service_or_wifi_scan"

    if scene == "账号与身份认证":
        if terms["identity_update"]:
            return "profile_or_identity_update"
        return "login_verification"

    if scene == "用户反馈与客服":
        return "customer_support"

    if scene == "社交互动与通信":
        return "social_chat_or_share"

    if scene == "内容浏览与搜索":
        return "content_browsing"

    if terms["cleanup"]:
        return "system_cleanup"
    if terms["file_recovery"]:
        return "file_recovery"
    if terms["capture"] or terms["audio_record"]:
        return "media_capture_or_recording"
    if terms["upload"]:
        return "media_upload"
    if terms["map_nav"]:
        return "map_navigation"
    if terms["nearby_or_wifi"]:
        return "nearby_service_or_wifi_scan"
    if terms["support"]:
        return "customer_support"
    if terms["chat_or_share"]:
        return "social_chat_or_share"
    if terms["browse"]:
        return "content_browsing"
    return UI_TO_REFINED_BASE.get(scene, "other")


def _normalize_refined_scene(v: Any, ui_task_scene: str, text_blob: str) -> str:
    s = _as_text(v, max_len=64).strip().lower()
    s = REFINED_SCENE_ALIASES.get(s, s)
    if s in REFINED_SCENE_SET:
        return s
    return _infer_refined_scene(ui_task_scene, text_blob)


def _legacy_refined_scene(refined_scene: str) -> str:
    rs = _as_text(refined_scene, max_len=64).lower()
    return REFINED_SCENE_V1_TO_LEGACY.get(rs, "content_browsing")


def _infer_primary_function(refined_scene: str, text_blob: str) -> str:
    rs = _as_text(refined_scene, max_len=64).lower()
    terms = _scene_terms(text_blob)
    mapping = {
        "login_verification": "登录验证",
        "profile_or_identity_update": "资料/身份信息更新",
        "file_management": "文件管理",
        "file_recovery": "文件恢复",
        "system_cleanup": "系统清理",
        "album_selection": "相册选择",
        "media_upload": "媒体上传",
        "media_capture_or_recording": "媒体拍摄或录音",
        "map_navigation": "地图导航",
        "nearby_service_or_wifi_scan": "附近服务或Wi-Fi扫描",
        "content_browsing": "内容浏览",
        "customer_support": "客服支持",
        "social_chat_or_share": "社交聊天或分享",
        "other": "其他任务",
    }
    if rs == "media_capture_or_recording":
        if terms["audio_record"]:
            return "录音创作"
        if terms["capture"]:
            return "视频拍摄"
    primary = mapping.get(rs, "其他任务")
    if rs == "other":
        if terms["audio_record"]:
            return "录音创作"
        if terms["capture"]:
            return "视频拍摄"
        if terms["upload"] and terms["album"]:
            return "图片上传"
        if terms["file_recovery"]:
            return "文件恢复"
        if terms["cleanup"]:
            return "系统清理"
        if terms["map_nav"]:
            return "地图导航"
    return primary


def _align_ui_task_scene(
    ui_task_scene: str,
    refined_scene: str,
    primary_function: str,
    text_blob: str,
) -> str:
    scene = _clean_scene(ui_task_scene)
    refined = _as_text(refined_scene, max_len=64).lower()
    primary = _as_text(primary_function, max_len=80)
    terms = _scene_terms(text_blob)

    audio_signal = bool(
        terms["audio_record"]
        or any(k in primary for k in ["录音", "清唱", "K歌", "k歌", "配音", "音频"])
    )
    camera_signal = bool(
        terms["capture"]
        or any(k in primary for k in ["拍摄", "视频", "扫码", "相机"])
    )

    if refined == "media_capture_or_recording":
        if audio_signal:
            return "音频录制与创作"
        if camera_signal:
            return "图像视频拍摄与扫码"
        if scene in {"其他", "媒体拍摄与扫码"}:
            return "图像视频拍摄与扫码"

    if refined == "album_selection":
        return "相册选择与媒体上传"
    if refined == "media_upload" and scene == "其他":
        return "相册选择与媒体上传"

    if scene == "其他":
        fallback = {
            "login_verification": "账号与身份认证",
            "profile_or_identity_update": "账号与身份认证",
            "file_management": "文件与数据管理",
            "file_recovery": "文件与数据管理",
            "system_cleanup": "设备清理与系统优化",
            "map_navigation": "地图与位置服务",
            "nearby_service_or_wifi_scan": "网络连接与设备管理",
            "content_browsing": "内容浏览与搜索",
            "customer_support": "用户反馈与客服",
            "social_chat_or_share": "社交互动与通信",
        }
        if refined in fallback:
            return fallback[refined]

    if scene == "媒体拍摄与扫码":
        if audio_signal:
            return "音频录制与创作"
        return "图像视频拍摄与扫码"
    return scene


def _calc_scene_confidence(
    confidence_label: str,
    refined_scene: str,
    supporting: List[str],
    conflicting: List[str],
) -> float:
    score = _confidence_to_score(confidence_label)
    if _as_text(refined_scene, 64).lower() == "other":
        score = min(score, 0.45)
    if len(supporting) >= 3:
        score += 0.05
    if conflicting:
        score -= 0.08 * len(conflicting[:2])
    if len(supporting) <= len(conflicting) and conflicting:
        score -= 0.08
    if score < 0.05:
        return 0.05
    if score > 0.98:
        return 0.98
    return round(score, 3)


def to_semantic_v2_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    def _cap(values: Any, max_items: int, max_len: int) -> List[str]:
        return _dedupe_keep_order(
            [_as_text(x, max_len=max_len) for x in _as_list(values) if _as_text(x, max_len=max_len)],
            max_items=max_items,
        )

    def _to_score(raw: Any) -> float:
        try:
            return max(0.05, min(0.98, round(float(raw), 3)))
        except Exception:
            label = _as_text(raw, max_len=16).lower()
            if label in CONF_LEVELS:
                return _confidence_to_score(label)
            return 0.35

    def _pick_scene_from_refined(refined_scene: str) -> str:
        mapping = {
            "login_verification": "账号与身份认证",
            "profile_or_identity_update": "账号与身份认证",
            "file_management": "文件与数据管理",
            "file_recovery": "文件与数据管理",
            "system_cleanup": "设备清理与系统优化",
            "album_selection": "相册选择与媒体上传",
            "media_upload": "相册选择与媒体上传",
            "media_capture_or_recording": "图像视频拍摄与扫码",
            "map_navigation": "地图与位置服务",
            "nearby_service_or_wifi_scan": "网络连接与设备管理",
            "content_browsing": "内容浏览与搜索",
            "customer_support": "用户反馈与客服",
            "social_chat_or_share": "社交互动与通信",
            "other": "其他",
        }
        return mapping.get(_as_text(refined_scene, 64).lower(), "其他")

    def _quote_join(items: List[str], max_items: int = 3) -> str:
        vals = [f"“{_as_text(x, 20)}”" for x in items[:max_items] if _as_text(x, 20)]
        return "、".join(vals)

    def _clean_elements(values: Any, max_items: int, max_len: int) -> List[str]:
        out: List[str] = []
        for raw in _as_list(values):
            t = _as_text(raw, max_len=max_len)
            if not t:
                continue
            if not _is_readable_ui_token(t):
                continue
            if _contains_perm_ui_word(t):
                continue
            if any(x in t for x in ["页面显示", "页面包含", "按钮位于", "用户点击", "系统弹出", "权限请求"]):
                continue
            out.append(t)
        return _dedupe_keep_order(out, max_items=max_items)

    def _is_generic_goal(text: str) -> bool:
        t = _as_text(text, max_len=120)
        if not t:
            return True
        bad_phrases = ("相关任务", "进行相关操作", "当前页面任务", "执行操作")
        return any(p in t for p in bad_phrases) or len(t) < 6

    def _build_page_observation(
        labels: List[str],
        buttons: List[str],
        indicators: List[str],
        dialogs: List[str],
        visual_tokens: List[str],
        fallback_text: str,
    ) -> str:
        sentences: List[str] = []
        text_tokens = _dedupe_keep_order(labels + visual_tokens, max_items=6)
        if text_tokens:
            sentences.append(f"页面可见文本包括{_quote_join(text_tokens, 3)}。")
        if buttons:
            sentences.append(f"可点击入口有{_quote_join(buttons, 3)}。")
        if indicators:
            sentences.append(f"状态信息显示{_quote_join(indicators, 2)}。")
        elif dialogs:
            sentences.append(f"页面存在业务弹窗{_quote_join(dialogs, 1)}。")
        if len(sentences) < 2 and fallback_text:
            toks = [t for t in _tokens_from_text(fallback_text, max_items=8) if _is_readable_ui_token(t) and not _contains_perm_ui_word(t)]
            if toks:
                sentences.append(f"页面上下文还出现{_quote_join(toks, 3)}。")
        if len(sentences) < 2:
            sentences.append("页面展示了当前任务入口与相关文本信息。")
        return _as_text("".join(sentences[:4]), max_len=260)

    def _permission_match_ratio(perms: List[str], text: str) -> float:
        if not perms:
            return 0.0
        blob = str(text or "").lower()
        total = 0
        hit = 0
        for p in perms:
            key = _as_text(p, max_len=80).upper()
            total += 1
            if key == "CAMERA":
                if any(k in blob for k in ["拍照", "拍摄", "录像", "扫码", "相机", "视频"]):
                    hit += 1
            elif key == "RECORD_AUDIO":
                if any(k in blob for k in ["录音", "清唱", "配音", "语音", "音频", "麦克风"]):
                    hit += 1
            elif key in {"ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"}:
                if any(k in blob for k in ["地图", "导航", "定位", "附近", "同城"]):
                    hit += 1
            elif key in {"READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "READ_MEDIA_IMAGES", "READ_MEDIA_VIDEO", "READ_MEDIA_AUDIO"}:
                if any(k in blob for k in ["相册", "上传", "下载", "保存", "导入", "文件", "图片", "视频", "音频"]):
                    hit += 1
        return round(hit / max(total, 1), 3)

    def _relation_text(ratio: float) -> str:
        if ratio >= 0.8:
            return "关联较强：页面证据与权限用途一致。"
        if ratio >= 0.4:
            return "关联中等：页面存在部分对应证据。"
        return "关联较弱或不确定：页面证据不足。"

    scene_obj = rec.get("scene") if isinstance(rec.get("scene"), dict) else {}
    page_sem_obj = rec.get("page_semantics") if isinstance(rec.get("page_semantics"), dict) else {}
    page_desc_obj = rec.get("page_description") if isinstance(rec.get("page_description"), dict) else {}
    task_under_obj = rec.get("task_understanding") if isinstance(rec.get("task_understanding"), dict) else {}
    page_elements_obj = rec.get("page_elements") if isinstance(rec.get("page_elements"), dict) else {}
    key_ui_obj = page_desc_obj.get("key_ui_elements") if isinstance(page_desc_obj.get("key_ui_elements"), dict) else {}
    evidence_obj = rec.get("evidence") if isinstance(rec.get("evidence"), dict) else {}

    ui_task_scene = _clean_scene(scene_obj.get("ui_task_scene") or rec.get("ui_task_scene"))
    text_blob = " ".join(
        [
            _as_text(rec.get("user_intent"), 220),
            _as_text(rec.get("trigger_action"), 100),
            _as_text(rec.get("page_observation"), 360),
            _as_text(page_sem_obj.get("primary_function"), 80),
            _as_text(page_desc_obj.get("current_page_summary"), 360),
            " ".join([_as_text(x, 40) for x in _as_list(rec.get("visual_evidence"))[:10] if _as_text(x, 40)]),
        ]
    )
    refined_scene = _normalize_refined_scene(
        scene_obj.get("refined_scene") or rec.get("refined_scene"),
        ui_task_scene=ui_task_scene,
        text_blob=text_blob,
    )

    raw_conf = scene_obj.get("confidence")
    if raw_conf is None:
        raw_conf = rec.get("scene_confidence")
    if raw_conf is None:
        raw_conf = rec.get("confidence")
    scene_confidence = _to_score(raw_conf)

    buttons = _clean_elements(page_elements_obj.get("buttons") or key_ui_obj.get("buttons"), max_items=5, max_len=40)
    labels = _clean_elements(page_elements_obj.get("labels") or key_ui_obj.get("labels"), max_items=6, max_len=40)
    indicators = _clean_elements(page_elements_obj.get("indicators") or key_ui_obj.get("indicators"), max_items=4, max_len=40)
    dialogs = _clean_elements(page_elements_obj.get("dialogs") or key_ui_obj.get("dialogs"), max_items=4, max_len=60)

    raw_trigger = _as_text(
        (page_sem_obj.get("permission_context", {}) if isinstance(page_sem_obj.get("permission_context"), dict) else {}).get("trigger_source")
        or rec.get("trigger_action")
        or task_under_obj.get("trigger_action")
        or "",
        max_len=80,
    )
    chosen_button = ""
    for b in buttons:
        if b and b in raw_trigger:
            chosen_button = b
            break
    if not chosen_button and buttons:
        chosen_button = buttons[0]

    if chosen_button:
        action_step = f"用户点击“{chosen_button}”入口"
    else:
        action_step = "用户执行页面入口操作"

    visual_tokens = _cap(
        evidence_obj.get("visual_evidence") or rec.get("visual_evidence"),
        max_items=8,
        max_len=60,
    )
    visual_tokens = [x for x in visual_tokens if _is_readable_ui_token(x) and not _contains_perm_ui_word(x)][:6]
    if len(visual_tokens) < 3:
        visual_tokens = _dedupe_keep_order(
            visual_tokens + labels[:3] + buttons[:2] + indicators[:2],
            max_items=6,
        )

    fallback_obs_text = " ".join(
        [
            _as_text(rec.get("page_observation"), 160),
            _as_text(page_desc_obj.get("context_before_popup"), 120),
            _as_text(page_desc_obj.get("context_after_popup"), 120),
        ]
    )
    page_observation = _build_page_observation(
        labels=labels,
        buttons=buttons,
        indicators=indicators,
        dialogs=dialogs,
        visual_tokens=visual_tokens,
        fallback_text=fallback_obs_text,
    )

    primary_function = _as_text(
        page_sem_obj.get("primary_function")
        or task_under_obj.get("primary_function")
        or _infer_primary_function(refined_scene, text_blob),
        max_len=80,
    )
    ui_task_scene = _align_ui_task_scene(
        ui_task_scene=ui_task_scene,
        refined_scene=refined_scene,
        primary_function=primary_function,
        text_blob=" ".join([text_blob, page_observation]),
    )
    if ui_task_scene == "其他":
        ui_task_scene = _pick_scene_from_refined(refined_scene)
        if ui_task_scene != "其他":
            scene_confidence = max(0.45, scene_confidence)

    page_type = _as_text(page_sem_obj.get("page_type") or page_desc_obj.get("page_type"), max_len=80)
    if not page_type:
        page_type = _infer_page_type(refined_scene, popup_present=False)

    user_goal = _as_text(
        page_sem_obj.get("user_goal") or task_under_obj.get("user_goal") or rec.get("user_intent"),
        max_len=220,
    )
    if _is_generic_goal(user_goal):
        if chosen_button:
            user_goal = _as_text(f"用户希望点击“{chosen_button}”继续{primary_function}流程。", max_len=220)
        else:
            user_goal = _as_text(f"用户希望继续当前页面并完成{primary_function}。", max_len=220)

    interaction_flow: List[str] = [f"用户进入{primary_function}相关页面", action_step]
    if indicators:
        interaction_flow.append(f"页面进入“{_as_text(indicators[0], 20)}”状态")
    elif dialogs:
        interaction_flow.append(f"页面出现业务弹窗“{_as_text(dialogs[0], 20)}”")
    else:
        interaction_flow.append("页面进入下一步任务流程")
    interaction_flow = _normalize_text_list(interaction_flow, max_items=4, max_len=48)

    observations = _normalize_text_list(
        [
            f"页面出现文本：{_quote_join((labels + visual_tokens)[:3], 3)}" if (labels or visual_tokens) else "",
            f"页面存在入口：{_quote_join(buttons[:3], 3)}" if buttons else "",
            f"页面状态：{_quote_join(indicators[:2], 2)}" if indicators else "",
            f"页面弹窗：{_quote_join(dialogs[:1], 1)}" if dialogs else "",
        ],
        max_items=5,
        max_len=80,
    )
    interactions = _normalize_text_list(
        [
            interaction_flow[0] if interaction_flow else "",
            interaction_flow[1] if len(interaction_flow) > 1 else "",
            interaction_flow[2] if len(interaction_flow) > 2 else "",
        ],
        max_items=4,
        max_len=80,
    )
    inferences = _normalize_text_list(
        [
            "页面以可点击入口驱动后续操作" if buttons else "页面以文本信息引导后续操作",
            "存在状态指示，流程不是静态浏览" if indicators else "",
            f"页面能力集中在{primary_function}相关操作",
        ],
        max_items=3,
        max_len=80,
    )

    known_permissions = _cap(rec.get("permissions_hint"), max_items=8, max_len=60)
    if not known_permissions:
        known_permissions = _cap(
            (page_sem_obj.get("permission_context", {}) if isinstance(page_sem_obj.get("permission_context"), dict) else {}).get("requested_permissions")
            or ((page_desc_obj.get("permission_popup") or {}) if isinstance(page_desc_obj.get("permission_popup"), dict) else {}).get("requested_permissions"),
            max_items=8,
            max_len=60,
        )
    function_ratio = _permission_match_ratio(known_permissions, " ".join([primary_function, page_observation, " ".join(observations)]))
    goal_ratio = _permission_match_ratio(known_permissions, " ".join([user_goal, " ".join(interaction_flow)]))

    return {
        "chain_id": int(rec.get("chain_id", -1)),
        "page_observation": page_observation,
        "page_elements": {
            "buttons": buttons,
            "labels": labels,
            "indicators": indicators,
            "dialogs": dialogs,
        },
        "evidence": {
            "observations": observations,
            "interactions": interactions,
            "inferences": inferences,
        },
        "scene": {
            "ui_task_scene": ui_task_scene,
            "refined_scene": refined_scene,
            "confidence": round(scene_confidence, 3),
        },
        "page_semantics": {
            "page_type": page_type,
            "primary_function": primary_function,
            "user_goal": user_goal,
            "interaction_flow": interaction_flow,
        },
        "permission_context": {
            "permissions": known_permissions,
            "relevance_to_page_function": _relation_text(function_ratio) if known_permissions else "无已知权限。",
            "relevance_to_user_goal": _relation_text(goal_ratio) if known_permissions else "无已知权限。",
        },
    }


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
        "拍摄扫码": "图像视频拍摄与扫码",
        "媒体拍摄与扫码": "图像视频拍摄与扫码",
        "音频录制": "音频录制与创作",
        "音频创作": "音频录制与创作",
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
        "音频录制与创作": "点击开始入口",
        "图像视频拍摄与扫码": "点击拍摄或扫码入口",
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


def _normalize_text_list(values: Any, max_items: int = 8, max_len: int = 80) -> List[str]:
    return _dedupe_keep_order(
        [_as_text(x, max_len=max_len) for x in _as_list(values) if _as_text(x, max_len=max_len)],
        max_items=max_items,
    )


def _is_readable_ui_token(token: str) -> bool:
    s = _as_text(token, max_len=80)
    if not s or len(s) < 2 or len(s) > 28:
        return False
    if "..." in s or "：" in s:
        return False
    if re.fullmatch(r"[\W_]+", s):
        return False
    if re.search(r"[A-Za-z]", s) and re.search(r"[\u4e00-\u9fff]", s):
        return False
    if len(set(s)) <= 1 and len(s) >= 3:
        return False
    return True


def _build_key_ui_elements(
    widgets: List[str],
    visual_evidence: List[str],
    granting_text: str,
) -> Dict[str, List[str]]:
    tokens = _normalize_text_list(widgets + visual_evidence, max_items=24, max_len=40)
    if granting_text:
        tokens.extend(_tokens_from_text(granting_text, max_items=8))
    tokens = _normalize_text_list(tokens, max_items=24, max_len=40)
    tokens = [t for t in tokens if _is_readable_ui_token(t)]

    buttons: List[str] = []
    tabs: List[str] = []
    labels: List[str] = []
    indicators: List[str] = []
    dialogs: List[str] = []
    for token in tokens:
        t = token.lower()
        if any(k in token for k in ["按钮", "点击", "开始", "继续", "上传", "拍照", "拍摄", "录音", "登录", "提交", "确定", "允许", "拒绝"]):
            buttons.append(token)
            continue
        if any(k in token for k in ["tab", "首页", "发现", "消息", "我的", "附近", "地图", "设置", "频道"]):
            tabs.append(token)
            continue
        if any(k in token for k in ["中", "中...", "loading", "定位", "扫描", "录制", "进度", "已选", "已连接"]):
            indicators.append(token)
            continue
        if any(k in token for k in ["权限", "允许", "拒绝", "仅在使用中", "去设置", "对话框", "弹窗", "dialog"]):
            dialogs.append(token)
            continue
        if len(t) <= 24:
            labels.append(token)

    return {
        "buttons": _normalize_text_list(buttons, max_items=5, max_len=40),
        "tabs": _normalize_text_list(tabs, max_items=8, max_len=40),
        "labels": _normalize_text_list(labels, max_items=6, max_len=40),
        "indicators": _normalize_text_list(indicators, max_items=4, max_len=40),
        "dialogs": _normalize_text_list(dialogs, max_items=4, max_len=60),
    }


def _build_permission_popup(
    granting_text: str,
    permissions_hint: List[str],
    trigger_action: str,
) -> Dict[str, Any]:
    popup_present = bool(granting_text and _contains_perm_ui_word(granting_text)) or bool(permissions_hint)
    popup_text = _as_text(granting_text, max_len=260)
    if popup_present and (not popup_text):
        popup_text = "系统权限请求弹窗出现。"
    return {
        "present": bool(popup_present),
        "requested_permissions": _normalize_text_list(permissions_hint, max_items=8, max_len=60),
        "popup_text": popup_text,
        "trigger_source": _as_text(trigger_action, max_len=100),
    }


def _infer_page_type(refined_scene: str, popup_present: bool) -> str:
    rs = _as_text(refined_scene, max_len=64).lower()
    mapping = {
        "login_verification": "authentication_page",
        "profile_or_identity_update": "profile_update_page",
        "file_management": "file_management_page",
        "file_recovery": "file_recovery_page",
        "system_cleanup": "system_cleanup_page",
        "album_selection": "album_picker_page",
        "media_upload": "media_upload_page",
        "media_capture_or_recording": "capture_or_recording_page",
        "map_navigation": "map_navigation_page",
        "nearby_service_or_wifi_scan": "nearby_or_wifi_scan_page",
        "content_browsing": "content_browsing_page",
        "customer_support": "customer_support_page",
        "social_chat_or_share": "social_chat_or_share_page",
    }
    base = mapping.get(rs, "generic_task_page")
    if popup_present:
        return f"{base}_with_permission_popup"
    return base


def _default_action_by_primary_function(primary_function: str) -> str:
    func = _as_text(primary_function, max_len=40)
    mapping = [
        (("录音", "音频"), "点击“开始录音”按钮"),
        (("拍摄", "视频", "扫码"), "点击“开始拍摄”按钮"),
        (("上传", "相册"), "点击“上传”入口"),
        (("导航", "地图"), "点击“开始导航”按钮"),
        (("清理",), "点击“开始清理”按钮"),
        (("登录", "验证"), "点击“登录”按钮"),
        (("恢复",), "点击“开始恢复”按钮"),
        (("聊天", "分享"), "点击“发送”按钮"),
    ]
    for terms, action in mapping:
        if any(t in func for t in terms):
            return action
    return "执行当前页面操作"


def _normalize_trigger_action(primary_function: str, trigger_action: str) -> str:
    action = _as_text(trigger_action, max_len=40)
    if not action or action == "unknown":
        return _default_action_by_primary_function(primary_function)
    if action in {"开始", "启动", "录制", "拍摄", "清唱", "上传", "导航"}:
        return f"点击“{action}”入口"
    good_terms = ("点击", "选择", "输入", "开始", "上传", "拍摄", "录音", "登录", "导航", "清理", "扫描", "打开", "提交", "发送")
    if any(t in action for t in good_terms):
        if (len(action) <= 3) and ("点击" not in action):
            return f"点击“{action}”入口"
        return action
    return _default_action_by_primary_function(primary_function)


def _build_interaction_flow(
    page_type: str,
    primary_function: str,
    trigger_action: str,
    popup_present: bool,
    requested_permissions: Optional[List[str]] = None,
) -> List[str]:
    primary = _as_text(primary_function, max_len=40) or "当前任务"
    ptype = _as_text(page_type, max_len=60).lower()
    requested_permissions = requested_permissions or []

    def _page_name(func: str, ptype_norm: str) -> str:
        if func and func != "其他任务":
            return f"{func}页面"
        if "recording" in ptype_norm or "capture" in ptype_norm:
            return "媒体创作页面"
        if "navigation" in ptype_norm or "map" in ptype_norm:
            return "地图导航页面"
        if "cleanup" in ptype_norm:
            return "系统清理页面"
        if "upload" in ptype_norm or "album" in ptype_norm:
            return "媒体上传页面"
        return "当前功能页面"

    action_text = _normalize_trigger_action(primary, trigger_action)
    page_name = _page_name(primary, ptype)

    flow: List[str] = [f"用户进入{page_name}", f"用户{action_text}"]
    if popup_present:
        if requested_permissions:
            perms = "、".join([_as_text(x, max_len=30) for x in requested_permissions[:2] if _as_text(x, max_len=30)])
            flow.append(f"系统弹出{perms}权限请求" if perms else "系统弹出权限请求")
        else:
            flow.append("系统弹出权限请求")
    else:
        flow.append("页面进入任务执行状态")

    flow = _normalize_text_list(flow, max_items=4, max_len=44)
    if len(flow) < 2:
        flow = ["用户进入当前功能页面", "页面进入任务执行状态"]
    return flow[:4]


def _build_supporting_evidence(
    primary_function: str,
    trigger_source: str,
    requested_permissions: List[str],
    popup_present: bool,
    page_elements: Dict[str, List[str]],
) -> List[str]:
    primary = _as_text(primary_function, max_len=40) or "当前任务"
    trigger = _as_text(trigger_source, max_len=40) or "执行页面操作"
    buttons = _as_list(page_elements.get("buttons"))
    labels = _as_list(page_elements.get("labels"))
    indicators = _as_list(page_elements.get("indicators"))

    flow: List[str] = []
    if buttons:
        flow.append(f"页面存在“{_as_text(buttons[0], max_len=20)}”操作入口")
    elif labels:
        flow.append(f"页面包含“{_as_text(labels[0], max_len=20)}”功能标识")

    if trigger != "unknown":
        if trigger.startswith("点击"):
            if "“" in trigger or "\"" in trigger:
                flow.append(f"页面记录到用户执行{trigger}")
            else:
                flow.append(f"页面记录到用户执行“{trigger}”操作")
        else:
            flow.append(f"页面记录到用户执行{trigger}")

    if popup_present:
        perms = "、".join([_as_text(x, max_len=30) for x in requested_permissions[:2] if _as_text(x, max_len=30)])
        if perms:
            flow.append(f"权限请求明确涉及{perms}")
        else:
            flow.append("页面出现系统权限请求")

    if indicators:
        flow.append(f"页面状态指示为“{_as_text(indicators[0], max_len=20)}”")

    if len(flow) < 2:
        flow.append(f"页面主功能为{primary}")

    return _normalize_text_list(flow, max_items=4, max_len=48)


def _build_scene_reason(
    refined_scene: str,
    ui_task_scene: str,
    trigger_action: str,
    page_summary: str,
) -> str:
    rs = _as_text(refined_scene, max_len=64)
    reason = (
        f"根据页面描述与交互链路（场景:{ui_task_scene}，触发动作:{trigger_action or 'unknown'}），"
        f"页面语义更接近 {rs}。"
    )
    hint = _as_text(page_summary, max_len=120)
    if hint:
        reason += f" 关键依据：{hint}"
    return _as_text(reason, max_len=320)


def _build_conflicting_evidence(refined_scene: str, text_blob: str) -> List[str]:
    rs = _as_text(refined_scene, max_len=64).lower()
    terms = _scene_terms(text_blob)
    out: List[str] = []
    if rs == "media_upload" and (terms["capture"] or terms["audio_record"]):
        out.append("页面同时出现拍摄/录音信号，上传场景存在歧义")
    if rs == "media_capture_or_recording" and terms["upload"]:
        out.append("页面同时出现上传信号，可能是拍摄后上传流程")
    if rs == "map_navigation" and terms["upload"]:
        out.append("出现上传语义，和导航主任务不完全一致")
    if rs == "file_management" and terms["cleanup"]:
        out.append("出现清理优化语义，可能应归类为 system_cleanup")
    if rs == "other":
        out.append("场景证据不足，暂不强行归类")
    return _normalize_text_list(out, max_items=4, max_len=90)


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
    primary_function = _infer_primary_function(refined_scene, text_blob)
    user_intent = _as_text(f"用户希望完成“{primary_function}”相关操作。", max_len=220)
    page_observation = _as_text(
        f"用户在{scene}页面执行“{trigger_action}”后，系统弹出权限请求；页面上下文包含：{before[:70]} {granting[:70]} {after[:70]}",
        max_len=280,
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
    permission_popup = _build_permission_popup(granting, permissions_hint, trigger_action)
    key_ui_elements = _build_key_ui_elements(widget_texts, evidence, granting)
    interaction_flow = _build_interaction_flow(
        page_type=_infer_page_type(refined_scene, permission_popup["present"]),
        primary_function=primary_function,
        trigger_action=trigger_action,
        popup_present=permission_popup["present"],
        requested_permissions=_as_list(permission_popup.get("requested_permissions")),
    )[:4]
    visual_evidence = _normalize_text_list(evidence or ["页面出现系统权限请求弹窗"], max_items=6, max_len=80)
    visual_evidence = [x for x in visual_evidence if _is_readable_ui_token(x)][:6]
    supporting_evidence = _build_supporting_evidence(
        primary_function=primary_function,
        trigger_source=_normalize_trigger_action(primary_function, trigger_action),
        requested_permissions=_as_list(permission_popup.get("requested_permissions")),
        popup_present=bool(permission_popup["present"]),
        page_elements={
            "buttons": key_ui_elements.get("buttons", []),
            "labels": key_ui_elements.get("labels", []),
            "indicators": key_ui_elements.get("indicators", []),
            "dialogs": key_ui_elements.get("dialogs", []),
        },
    )
    conflicting_evidence = _normalize_text_list(
        _build_conflicting_evidence(refined_scene, text_blob),
        max_items=2,
        max_len=90,
    )

    task_cues = {
        "storage_read": _normalize_text_list(cues["storage_read_cues"], max_items=3, max_len=60),
        "storage_write": _normalize_text_list(cues["storage_write_cues"], max_items=3, max_len=60),
        "location": _normalize_text_list(cues["location_task_cues"], max_items=3, max_len=60),
        "upload": _normalize_text_list(cues["upload_task_cues"], max_items=3, max_len=60),
        "cleanup": _normalize_text_list(cues["cleanup_task_cues"], max_items=3, max_len=60),
        "camera": [],
        "audio": [],
    }
    scene_confidence = _calc_scene_confidence(
        confidence_label="low",
        refined_scene=refined_scene,
        supporting=supporting_evidence,
        conflicting=conflicting_evidence,
    )

    return {
        "scene": {
            "ui_task_scene": scene,
            "refined_scene": refined_scene,
            "confidence": scene_confidence,
        },
        "page_semantics": {
            "page_type": _infer_page_type(refined_scene, permission_popup["present"]),
            "primary_function": primary_function,
            "user_goal": user_intent,
            "interaction_flow": interaction_flow[:4],
            "permission_context": {
                "popup_present": bool(permission_popup["present"]),
                "requested_permissions": _normalize_text_list(permission_popup.get("requested_permissions"), max_items=6, max_len=60),
                "trigger_source": _as_text(trigger_action, max_len=80),
            },
        },
        "page_elements": {
            "buttons": _normalize_text_list(key_ui_elements.get("buttons"), max_items=5, max_len=40),
            "labels": _normalize_text_list(key_ui_elements.get("labels"), max_items=6, max_len=40),
            "indicators": _normalize_text_list(key_ui_elements.get("indicators"), max_items=4, max_len=40),
            "dialogs": _normalize_text_list(key_ui_elements.get("dialogs"), max_items=4, max_len=60),
        },
        "evidence": {
            "visual_evidence": visual_evidence[:6],
            "supporting_evidence": supporting_evidence[:4],
            "conflicting_evidence": conflicting_evidence[:2],
        },
        "task_cues": task_cues,
        # fallback keeps minimal compatibility aliases
        "ui_task_scene": scene,
        "refined_scene": refined_scene,
        "user_intent": user_intent,
        "trigger_action": trigger_action,
        "page_observation": _as_text("；".join(interaction_flow[:2]), max_len=220),
        "visual_evidence": visual_evidence[:6],
        "confidence": "low",
        "storage_read_cues": task_cues["storage_read"],
        "storage_write_cues": task_cues["storage_write"],
        "location_task_cues": task_cues["location"],
        "upload_task_cues": task_cues["upload"],
        "cleanup_task_cues": task_cues["cleanup"],
        "permission_task_cues": _normalize_text_list(
            task_cues["storage_read"] + task_cues["storage_write"] + task_cues["location"] + task_cues["upload"] + task_cues["cleanup"],
            max_items=10,
            max_len=60,
        ),
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
            "page_observation": "2-4 objective sentences with visible text, key entries and status",
            "page_elements": {
                "buttons": [],
                "labels": [],
                "indicators": [],
                "dialogs": [],
            },
            "evidence": {
                "observations": ["visible facts from page"],
                "interactions": ["chain-confirmed actions and transitions"],
                "inferences": ["minimal inference supported by observations + interactions"],
            },
            "scene": {
                "ui_task_scene": "from fixed taxonomy",
                "refined_scene": "from scene taxonomy v1",
                "confidence": 0.0,
            },
            "page_semantics": {
                "page_type": "page type",
                "primary_function": "specific function",
                "user_goal": "user goal",
                "interaction_flow": ["2-4 concise steps"],
            },
            "permission_context": {
                "permissions": permissions_hint[:10],
                "relevance_to_page_function": "strong|medium|weak with short rationale",
                "relevance_to_user_goal": "strong|medium|weak with short rationale",
            },
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
    scene_obj = obj.get("scene") if isinstance(obj.get("scene"), dict) else {}
    page_sem_obj = obj.get("page_semantics") if isinstance(obj.get("page_semantics"), dict) else {}
    permission_ctx_top = obj.get("permission_context") if isinstance(obj.get("permission_context"), dict) else {}
    system_dialog_obj = obj.get("system_permission_dialog") if isinstance(obj.get("system_permission_dialog"), dict) else {}
    evidence_obj_new = obj.get("evidence") if isinstance(obj.get("evidence"), dict) else {}
    task_cues_obj_new = obj.get("task_cues") if isinstance(obj.get("task_cues"), dict) else {}
    page_elements_obj_new = obj.get("page_elements") if isinstance(obj.get("page_elements"), dict) else {}

    page_desc_obj = obj.get("page_description") if isinstance(obj.get("page_description"), dict) else {}
    task_under_obj = obj.get("task_understanding") if isinstance(obj.get("task_understanding"), dict) else {}
    scene_inf_obj = obj.get("scene_inference") if isinstance(obj.get("scene_inference"), dict) else {}
    decision_support_obj = obj.get("decision_support") if isinstance(obj.get("decision_support"), dict) else {}
    fallback_page_desc = fallback.get("page_description") if isinstance(fallback.get("page_description"), dict) else {}
    fallback_task_under = fallback.get("task_understanding") if isinstance(fallback.get("task_understanding"), dict) else {}
    fallback_scene_inf = fallback.get("scene_inference") if isinstance(fallback.get("scene_inference"), dict) else {}

    # Accept a few key aliases for robustness.
    scene = _clean_scene(
        scene_obj.get("ui_task_scene")
        or
        obj.get("ui_task_scene")
        or scene_inf_obj.get("ui_task_scene")
        or obj.get("scene")
        or obj.get("predicted_scene")
        or fallback.get("ui_task_scene")
    )
    text_blob = " ".join(
        [
            _as_text(obj.get("page_overview"), max_len=120),
            _as_text(obj.get("user_intent") or obj.get("intent") or page_sem_obj.get("user_goal") or task_under_obj.get("user_goal"), max_len=220),
            _as_text(obj.get("page_observation") or obj.get("page_function") or page_sem_obj.get("primary_function") or page_desc_obj.get("current_page_summary"), max_len=320),
            _as_text(
                obj.get("trigger_action")
                or (page_sem_obj.get("permission_context", {}).get("trigger_source") if isinstance(page_sem_obj.get("permission_context"), dict) else "")
                or task_under_obj.get("trigger_action"),
                max_len=80,
            ),
            _as_text(fallback.get("user_intent"), max_len=200),
            _as_text(fallback.get("page_observation"), max_len=260),
            _as_text(page_desc_obj.get("context_before_popup"), max_len=220),
            _as_text(page_desc_obj.get("context_after_popup"), max_len=220),
            " ".join([_as_text(x, max_len=30) for x in _as_list(obj.get("visual_evidence"))[:8]]),
            " ".join([_as_text(x, max_len=30) for x in _as_list(evidence_obj_new.get("visual_evidence"))[:8]]),
            " ".join([_as_text(x, max_len=30) for x in _as_list(evidence_obj_new.get("observations"))[:8]]),
        ]
    )
    refined_scene = _normalize_refined_scene(
        scene_obj.get("refined_scene") or obj.get("refined_scene") or scene_inf_obj.get("refined_scene") or obj.get("scene_refined"),
        ui_task_scene=scene,
        text_blob=text_blob,
    )
    intent = _as_text(
        page_sem_obj.get("user_goal") or obj.get("user_intent") or obj.get("intent") or task_under_obj.get("user_goal") or fallback.get("user_intent"),
        max_len=220,
    )
    trigger = _as_text(
        (page_sem_obj.get("permission_context", {}).get("trigger_source") if isinstance(page_sem_obj.get("permission_context"), dict) else "")
        or
        permission_ctx_top.get("trigger_source")
        or
        obj.get("trigger_action")
        or task_under_obj.get("trigger_action")
        or ((page_desc_obj.get("permission_popup") or {}).get("trigger_source") if isinstance(page_desc_obj.get("permission_popup"), dict) else "")
        or fallback.get("trigger_action"),
        max_len=80,
    )
    page_observation = _as_text(
        obj.get("page_observation")
        or obj.get("page_function")
        or obj.get("page_overview")
        or page_sem_obj.get("primary_function")
        or page_desc_obj.get("current_page_summary")
        or fallback.get("page_observation"),
        max_len=520,
    )

    ve_raw = obj.get("visual_evidence")
    if not isinstance(ve_raw, list):
        ve_raw = []
        ve_raw.extend(evidence_obj_new.get("visual_evidence") if isinstance(evidence_obj_new.get("visual_evidence"), list) else [])
        ve_raw.extend(evidence_obj_new.get("observations") if isinstance(evidence_obj_new.get("observations"), list) else [])
        evidence = obj.get("evidence") if isinstance(obj.get("evidence"), dict) else {}
        ve_raw.extend(evidence.get("keywords") if isinstance(evidence.get("keywords"), list) else [])
        ve_raw.extend(evidence.get("widgets") if isinstance(evidence.get("widgets"), list) else [])
    if not ve_raw:
        ve_raw = _as_list(decision_support_obj.get("supporting_evidence"))
    visual_evidence = _dedupe_keep_order([_as_text(x, max_len=40) for x in ve_raw if _as_text(x, max_len=40)], max_items=10)

    if not intent:
        intent = fallback.get("user_intent", "用户希望完成当前页面任务。")
    if not trigger:
        trigger = fallback.get("trigger_action", "unknown")
    if not page_observation:
        page_observation = fallback.get("page_observation", "页面出现系统权限请求弹窗。")
    if not visual_evidence:
        visual_evidence = fallback.get("visual_evidence", ["页面出现系统权限请求弹窗"])

    confidence_raw = obj.get("confidence")
    if confidence_raw is None:
        confidence_raw = scene_obj.get("confidence")
    if confidence_raw is None:
        confidence_raw = fallback.get("confidence")
    confidence: str
    try:
        confidence = _confidence_score_to_label(float(confidence_raw))
    except Exception:
        confidence = _as_text(confidence_raw, max_len=10).lower()
    if confidence not in CONF_LEVELS:
        confidence = "low"

    widget_terms = [_as_text(x, max_len=40) for x in _as_list(obj.get("widgets"))[:16] if _as_text(x, max_len=40)]
    if not widget_terms:
        for k in ("buttons", "labels", "indicators", "dialogs"):
            widget_terms.extend([_as_text(x, max_len=40) for x in _as_list(page_elements_obj_new.get(k)) if _as_text(x, max_len=40)])
        key_ui = page_desc_obj.get("key_ui_elements") if isinstance(page_desc_obj.get("key_ui_elements"), dict) else {}
        for k in ("buttons", "tabs", "labels", "indicators", "dialogs"):
            widget_terms.extend([_as_text(x, max_len=40) for x in _as_list(key_ui.get(k)) if _as_text(x, max_len=40)])
    widget_terms = _normalize_text_list(widget_terms, max_items=20, max_len=40)

    popup_fallback = fallback_page_desc.get("permission_popup") if isinstance(fallback_page_desc.get("permission_popup"), dict) else {}
    popup_obj = page_desc_obj.get("permission_popup") if isinstance(page_desc_obj.get("permission_popup"), dict) else {}
    permission_ctx_obj = page_sem_obj.get("permission_context") if isinstance(page_sem_obj.get("permission_context"), dict) else {}
    popup_present = bool(
        system_dialog_obj.get("present")
        if system_dialog_obj.get("present") is not None
        else permission_ctx_obj.get("popup_present")
        if permission_ctx_obj.get("popup_present") is not None
        else
        popup_obj.get("present")
        if popup_obj.get("present") is not None
        else popup_fallback.get("present")
    )
    if not popup_present:
        popup_present = _contains_perm_ui_word(_as_text(popup_obj.get("popup_text") or "", 260)) or _contains_perm_ui_word(_as_text(page_observation, 280))

    popup_permissions = _normalize_text_list(
        system_dialog_obj.get("requested_permissions")
        or permission_ctx_obj.get("requested_permissions")
        or permission_ctx_top.get("permissions")
        or
        popup_obj.get("requested_permissions")
        or popup_fallback.get("requested_permissions")
        or obj.get("permissions_hint")
        or fallback.get("permissions_hint"),
        max_items=8,
        max_len=60,
    )
    popup_text = _as_text(
        " ".join([_as_text(x, max_len=80) for x in _as_list(system_dialog_obj.get("permission_text"))[:3]])
        or
        popup_obj.get("popup_text")
        or popup_fallback.get("popup_text")
        or _as_text(page_desc_obj.get("context_before_popup"), max_len=120),
        max_len=260,
    )
    key_ui_elements = _build_key_ui_elements(
        widgets=widget_terms,
        visual_evidence=visual_evidence,
        granting_text=popup_text,
    )
    key_ui_obj = page_desc_obj.get("key_ui_elements") if isinstance(page_desc_obj.get("key_ui_elements"), dict) else {}
    fallback_key_ui_obj = fallback_page_desc.get("key_ui_elements") if isinstance(fallback_page_desc.get("key_ui_elements"), dict) else {}
    for k in ("buttons", "tabs", "labels", "indicators", "dialogs"):
        key_ui_elements[k] = _normalize_text_list(
            key_ui_obj.get(k) or fallback_key_ui_obj.get(k) or key_ui_elements.get(k),
            max_items=12,
            max_len=40,
        )

    context_before = _as_text(
        page_desc_obj.get("context_before_popup") or fallback_page_desc.get("context_before_popup"),
        max_len=220,
    )
    context_after = _as_text(
        page_desc_obj.get("context_after_popup") or fallback_page_desc.get("context_after_popup"),
        max_len=220,
    )
    if not context_before:
        context_before = _as_text(page_observation, max_len=160)

    current_page_summary = _as_text(
        page_desc_obj.get("current_page_summary") or fallback_page_desc.get("current_page_summary"),
        max_len=520,
    )
    if len(current_page_summary) < 16:
        current_page_summary = _as_text(
            f"页面主任务围绕{_infer_primary_function(refined_scene, text_blob)}展开。"
            f"用户执行“{trigger}”后出现权限请求弹窗；"
            f"弹窗前上下文：{context_before[:90]}；弹窗后状态：{context_after[:90]}。",
            max_len=520,
        )

    page_type = _as_text(page_desc_obj.get("page_type") or fallback_page_desc.get("page_type"), max_len=80)
    if not page_type:
        page_type = _infer_page_type(refined_scene, popup_present)

    page_description = {
        "current_page_summary": current_page_summary,
        "context_before_popup": context_before,
        "context_after_popup": context_after,
        "page_type": page_type,
        "key_ui_elements": key_ui_elements,
        "permission_popup": {
            "present": bool(popup_present),
            "requested_permissions": popup_permissions,
            "popup_text": popup_text,
            "trigger_source": _as_text(popup_obj.get("trigger_source") or trigger, max_len=100),
        },
    }

    interaction_flow = _normalize_text_list(
        page_sem_obj.get("interaction_flow")
        or
        task_under_obj.get("interaction_flow") or fallback_task_under.get("interaction_flow"),
        max_items=6,
        max_len=120,
    )
    if not interaction_flow:
        interaction_flow = _build_interaction_flow(
            page_type=page_type,
            primary_function=_infer_primary_function(refined_scene, text_blob),
            trigger_action=trigger,
            popup_present=bool(popup_present),
            requested_permissions=popup_permissions,
        )
    primary_function = _as_text(
        page_sem_obj.get("primary_function")
        or
        task_under_obj.get("primary_function")
        or fallback_task_under.get("primary_function")
        or _infer_primary_function(refined_scene, text_blob),
        max_len=80,
    )
    if not primary_function:
        primary_function = "其他任务"
    task_understanding = {
        "primary_function": primary_function,
        "user_goal": _as_text(task_under_obj.get("user_goal") or intent, max_len=220),
        "trigger_action": _as_text(task_under_obj.get("trigger_action") or trigger, max_len=80),
        "interaction_flow": interaction_flow,
    }

    extracted_cues = _extract_structured_cues(
        user_intent=intent,
        trigger_action=trigger,
        page_observation=current_page_summary,
        visual_evidence=visual_evidence,
        widgets=widget_terms,
        ocr_triplet=[context_before, popup_text, context_after],
    )
    decision_task_cues = decision_support_obj.get("task_cues") if isinstance(decision_support_obj.get("task_cues"), dict) else {}
    top_task_cues = obj.get("task_cues") if isinstance(obj.get("task_cues"), dict) else {}
    storage_from_new = _normalize_text_list(_as_list(task_cues_obj_new.get("storage")), max_items=10, max_len=60)
    storage_read_from_old = _normalize_text_list(decision_task_cues.get("storage_read") or top_task_cues.get("storage_read"), max_items=10, max_len=60)
    storage_write_from_old = _normalize_text_list(decision_task_cues.get("storage_write") or top_task_cues.get("storage_write"), max_items=10, max_len=60)
    cue_bridge = {
        "permission_task_cues": _normalize_text_list(obj.get("permission_task_cues"), max_items=12, max_len=60),
        "storage_read_cues": _normalize_text_list(storage_from_new + storage_read_from_old, max_items=10, max_len=60),
        "storage_write_cues": _normalize_text_list(storage_from_new + storage_write_from_old, max_items=10, max_len=60),
        "location_task_cues": _normalize_text_list(task_cues_obj_new.get("location") or decision_task_cues.get("location") or top_task_cues.get("location"), max_items=10, max_len=60),
        "upload_task_cues": _normalize_text_list(task_cues_obj_new.get("upload") or decision_task_cues.get("upload") or top_task_cues.get("upload"), max_items=10, max_len=60),
        "cleanup_task_cues": _normalize_text_list(decision_task_cues.get("cleanup") or top_task_cues.get("cleanup"), max_items=10, max_len=60),
    }

    cue_values: Dict[str, List[str]] = {}
    for field in STRUCTURED_CUE_FIELDS:
        merged = _merge_cue_lists(obj.get(field), fallback.get(field), max_items=12)
        merged = _merge_cue_lists(merged, cue_bridge.get(field, []), max_items=12)
        merged = _merge_cue_lists(merged, extracted_cues.get(field, []), max_items=12)
        cue_values[field] = merged

    supporting_evidence = _normalize_text_list(
        evidence_obj_new.get("interaction_evidence")
        or evidence_obj_new.get("inferred_evidence")
        or evidence_obj_new.get("observations")
        or evidence_obj_new.get("interactions")
        or evidence_obj_new.get("inferences")
        or
        decision_support_obj.get("supporting_evidence")
        or obj.get("supporting_evidence")
        or fallback.get("supporting_evidence"),
        max_items=10,
        max_len=90,
    )
    if not supporting_evidence:
        supporting_evidence = _normalize_text_list(
            visual_evidence
            + [f"主功能:{primary_function}", f"触发动作:{trigger}"]
            + [_as_text(x, max_len=90) for x in interaction_flow[:3]],
            max_items=10,
            max_len=90,
        )
    conflicting_evidence = _normalize_text_list(
        evidence_obj_new.get("conflicting_evidence")
        or
        decision_support_obj.get("conflicting_evidence")
        or obj.get("conflicting_evidence")
        or fallback.get("conflicting_evidence"),
        max_items=6,
        max_len=90,
    )
    if not conflicting_evidence:
        conflicting_evidence = _build_conflicting_evidence(refined_scene, text_blob)

    scene_reason = _as_text(
        scene_inf_obj.get("scene_reason") or obj.get("scene_reason") or fallback_scene_inf.get("scene_reason"),
        max_len=320,
    )
    if not scene_reason:
        scene_reason = _build_scene_reason(
            refined_scene=refined_scene,
            ui_task_scene=scene,
            trigger_action=trigger,
            page_summary=current_page_summary,
        )

    raw_scene_conf = scene_inf_obj.get("scene_confidence")
    if raw_scene_conf is None:
        raw_scene_conf = obj.get("scene_confidence")
    if raw_scene_conf is None:
        raw_scene_conf = fallback_scene_inf.get("scene_confidence")
    try:
        scene_confidence = float(raw_scene_conf)
    except Exception:
        scene_confidence = _calc_scene_confidence(
            confidence_label=confidence,
            refined_scene=refined_scene,
            supporting=supporting_evidence,
            conflicting=conflicting_evidence,
        )
    scene_confidence = max(0.05, min(0.98, round(scene_confidence, 3)))

    decision_task_cues_full = {
        "storage_read": cue_values["storage_read_cues"],
        "storage_write": cue_values["storage_write_cues"],
        "location": cue_values["location_task_cues"],
        "upload": cue_values["upload_task_cues"],
        "cleanup": cue_values["cleanup_task_cues"],
        "camera": _normalize_text_list(decision_task_cues.get("camera") or top_task_cues.get("camera"), max_items=8, max_len=60),
        "audio": _normalize_text_list(decision_task_cues.get("audio") or top_task_cues.get("audio"), max_items=8, max_len=60),
    }
    scene_inference = {
        "ui_task_scene": scene,
        "refined_scene": refined_scene,
        "scene_confidence": scene_confidence,
        "scene_reason": scene_reason,
        "refined_scene_legacy": _legacy_refined_scene(refined_scene),
    }
    decision_support = {
        "supporting_evidence": supporting_evidence,
        "conflicting_evidence": conflicting_evidence,
        "task_cues": decision_task_cues_full,
    }

    rec = {
        "chain_id": chain_id,
        "ui_task_scene": scene,
        "refined_scene": refined_scene,
        "refined_scene_legacy": _legacy_refined_scene(refined_scene),
        "user_intent": intent,
        "trigger_action": trigger,
        "page_observation": _as_text(current_page_summary or page_observation, max_len=520),
        "visual_evidence": visual_evidence,
        "confidence": confidence,
        "confidence_label": confidence,
        "scene_confidence": scene_confidence,
        "scene_reason": scene_reason,
        "supporting_evidence": supporting_evidence,
        "conflicting_evidence": conflicting_evidence,
        "page_description": page_description,
        "task_understanding": task_understanding,
        "scene_inference": scene_inference,
        "decision_support": decision_support,
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
    if not isinstance(rec.get("page_description"), dict):
        return "missing_page_description"
    if not isinstance(rec.get("task_understanding"), dict):
        return "missing_task_understanding"
    return ""


def build_prompt(template: str, input_payload: Dict[str, Any], strict: bool) -> str:
    prompt = template.replace("{INPUT_JSON}", json.dumps(input_payload, ensure_ascii=False, indent=2))
    if strict:
        prompt += (
            "\n\n【重试补充要求】\n"
            "1) 必须按 page_observation/page_elements/evidence/scene/page_semantics/permission_context 输出。\n"
            "2) scene.ui_task_scene 必须从固定 taxonomy 选择；不确定时 refined_scene 可输出 other。\n"
            "3) scene.confidence 必须是 0~1 浮点数。\n"
            "4) page_observation 必须 2~4 句客观描述可见文本、入口和状态，不要直接给场景结论。\n"
            "5) interaction_flow 必须是动作链，且涉及按钮必须来自 page_elements.buttons。\n"
            "6) evidence 仅保留 observations/interactions/inferences；不要输出 task_cues 或 reasoning_basis。\n"
            "7) permission_context.permissions 直接使用已知 permissions_hint，不要重新识别权限。\n"
            "8) page_elements 只放原始可见元素，禁止解释句、推断句、权限弹窗按钮。\n"
            "9) 只输出严格 JSON，不要额外文字。\n"
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
        scene_obj = rec.get("scene") if isinstance(rec.get("scene"), dict) else {}
        page_sem = rec.get("page_semantics") if isinstance(rec.get("page_semantics"), dict) else {}
        perm_ctx = page_sem.get("permission_context") if isinstance(page_sem.get("permission_context"), dict) else {}

        conf = _as_text(rec.get("confidence_label"), max_len=10).lower()
        if conf not in CONF_LEVELS:
            raw_conf = scene_obj.get("confidence")
            if raw_conf is None:
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
        scene = _as_text(scene_obj.get("ui_task_scene") or rec.get("ui_task_scene") or "其他", max_len=30) or "其他"
        trigger = _as_text(
            perm_ctx.get("trigger_source")
            or rec.get("trigger_action", ""),
            max_len=80,
        )
        refined_scene = _as_text(scene_obj.get("refined_scene") or rec.get("refined_scene") or "other", max_len=64) or "other"
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
