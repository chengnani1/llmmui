# -*- coding: utf-8 -*-
"""
Phase3 semantic pre-stage (minimal):
load inputs -> call VLM -> parse JSON -> light normalize -> write outputs.

Output schema (per chain):
{
  "chain_id": 0,
  "page_description": "",
  "page_function": "",
  "user_goal": "",
  "scene": {
    "ui_task_scene": "",
    "refined_scene": "",
    "confidence": 0.0
  }
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
DEFAULT_PROMPT_FILE = os.path.join(settings.PROMPT_DIR, "chain_semantic_interpreter_vision.txt")
PERMISSION_FILENAME = "result_permission.json"

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

_SCENE_KEYWORDS = [
    (("登录", "账号", "认证", "验证码", "密码"), "账号与身份认证", "login_verification"),
    (("地图", "定位", "附近", "同城", "导航"), "地图与位置服务", "map_navigation"),
    (("搜索", "浏览", "资讯", "内容", "推荐"), "内容浏览与搜索", "content_browsing"),
    (("聊天", "消息", "评论", "私信", "社区"), "社交互动与通信", "social_chat_or_share"),
    (("录音", "清唱", "k歌", "K歌", "配音", "语音创作", "音频", "麦克风"), "音频录制与创作", "media_capture_or_recording"),
    (("扫码", "拍照", "相机", "拍摄", "录像", "视频录制"), "图像视频拍摄与扫码", "media_capture_or_recording"),
    (("相册", "上传", "头像", "图片", "照片"), "相册选择与媒体上传", "album_selection"),
    (("文件", "文档", "导出", "导入", "存储"), "文件与数据管理", "file_management"),
    (("清理", "加速", "优化", "垃圾", "释放空间"), "设备清理与系统优化", "system_cleanup"),
    (("wifi", "蓝牙", "网络", "连接", "设备"), "网络连接与设备管理", "nearby_service_or_wifi_scan"),
    (("反馈", "客服", "帮助", "工单"), "用户反馈与客服", "customer_support"),
]


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


def _normalize_text_list(values: Any, max_items: int = 8, max_len: int = 120) -> List[str]:
    vals = [_as_text(x, max_len=max_len) for x in _as_list(values) if _as_text(x, max_len=max_len)]
    return _dedupe_keep_order(vals, max_items=max_items)


def _is_readable_ui_token(token: str) -> bool:
    s = _as_text(token, max_len=80)
    if not s:
        return False
    if len(s) < 2 or len(s) > 32:
        return False
    if re.fullmatch(r"[\W_]+", s):
        return False
    return True


def _clean_scene(scene: Any) -> str:
    s = _as_text(scene, max_len=40)
    if s in SCENE_SET:
        return s
    alias = {
        "账号认证": "账号与身份认证",
        "地图定位": "地图与位置服务",
        "浏览搜索": "内容浏览与搜索",
        "社交通信": "社交互动与通信",
        "媒体拍摄与扫码": "图像视频拍摄与扫码",
        "拍摄扫码": "图像视频拍摄与扫码",
        "音频录制": "音频录制与创作",
        "音频创作": "音频录制与创作",
        "相册上传": "相册选择与媒体上传",
        "文件管理": "文件与数据管理",
        "设备清理": "设备清理与系统优化",
        "网络设备": "网络连接与设备管理",
        "反馈客服": "用户反馈与客服",
        "other": "其他",
        "others": "其他",
    }
    if s in alias:
        return alias[s]
    low = s.lower()
    if low in alias:
        return alias[low]
    return "其他"


def _infer_scene_from_text(text: str) -> Tuple[str, str]:
    blob = str(text or "")
    for terms, ui_scene, refined in _SCENE_KEYWORDS:
        if any(t in blob for t in terms):
            return ui_scene, refined
    return "其他", "other"


def _normalize_refined_scene(v: Any, ui_task_scene: str, text_blob: str) -> str:
    s = _as_text(v, max_len=64).lower()
    s = REFINED_SCENE_ALIASES.get(s, s)
    if s in REFINED_SCENE_SET:
        return s

    _, inferred = _infer_scene_from_text(text_blob)
    if inferred in REFINED_SCENE_SET:
        return inferred

    ui = _clean_scene(ui_task_scene)
    ui_map = {
        "账号与身份认证": "login_verification",
        "地图与位置服务": "map_navigation",
        "内容浏览与搜索": "content_browsing",
        "社交互动与通信": "social_chat_or_share",
        "音频录制与创作": "media_capture_or_recording",
        "图像视频拍摄与扫码": "media_capture_or_recording",
        "相册选择与媒体上传": "album_selection",
        "文件与数据管理": "file_management",
        "设备清理与系统优化": "system_cleanup",
        "网络连接与设备管理": "nearby_service_or_wifi_scan",
        "用户反馈与客服": "customer_support",
        "其他": "other",
    }
    return ui_map.get(ui, "other")


def _normalize_confidence(v: Any, default: float = 0.35) -> float:
    if isinstance(v, (int, float)):
        return max(0.0, min(1.0, round(float(v), 3)))

    label = _as_text(v, max_len=20).lower()
    if label == "high":
        return 0.9
    if label == "medium":
        return 0.65
    if label == "low":
        return 0.35
    return default


def _fallback_function_goal(ui_scene: str) -> Tuple[str, str]:
    mapping = {
        "音频录制与创作": ("提供音频录制或清唱入口", "开始进行音频录制或清唱"),
        "图像视频拍摄与扫码": ("提供拍摄、录制或扫码入口", "进入拍摄、录制或扫码操作"),
        "相册选择与媒体上传": ("提供相册选择与媒体上传入口", "选择已有图片或视频并发起上传"),
        "地图与位置服务": ("提供定位与地图浏览入口", "查看当前位置或附近信息"),
        "账号与身份认证": ("提供账号验证与登录入口", "完成登录或身份验证"),
        "内容浏览与搜索": ("提供内容浏览或搜索入口", "浏览内容或执行搜索"),
        "社交互动与通信": ("提供消息互动或发布入口", "进行聊天、互动或内容发布"),
        "文件与数据管理": ("提供文件选择或管理入口", "选择、浏览或管理文件"),
        "设备清理与系统优化": ("提供清理或优化入口", "执行清理或系统优化操作"),
        "网络连接与设备管理": ("提供网络或设备连接入口", "配置网络或连接设备"),
        "用户反馈与客服": ("提供反馈与客服入口", "提交问题反馈或联系客户支持"),
    }
    return mapping.get(ui_scene, ("提供当前页面业务入口", "继续当前页面业务操作"))


def _empty_record(chain_id: int) -> Dict[str, Any]:
    return {
        "chain_id": int(chain_id),
        "page_description": "",
        "page_function": "",
        "user_goal": "",
        "scene": {
            "ui_task_scene": "其他",
            "refined_scene": "other",
            "confidence": 0.35,
        },
    }


def _default_semantics(chain_summary: Dict[str, Any], chain_id: int = -1) -> Dict[str, Any]:
    widgets = [
        _as_text(x, max_len=28)
        for x in _as_list(chain_summary.get("top_widgets"))[:16]
        if _is_readable_ui_token(_as_text(x, max_len=28))
    ]
    before = _as_text(chain_summary.get("before_text", ""), max_len=160)
    after = _as_text(chain_summary.get("after_text", ""), max_len=160)
    text_blob = " ".join([before, after, " ".join(widgets)])

    ui_scene, refined_scene = _infer_scene_from_text(text_blob)
    function_hint, goal_hint = _fallback_function_goal(ui_scene)

    visible = widgets[:4]
    actions = [
        x for x in widgets
        if any(k in x for k in ["开始", "上传", "拍摄", "录制", "登录", "确认", "发送", "导航", "搜索", "发布"])
    ][:2]
    states = [
        x for x in widgets
        if any(k in x for k in ["中", "加载", "录制", "下载", "上传", "播放", "进度"])
    ][:2]

    parts: List[str] = []
    if visible:
        parts.append(f"页面展示{ '、'.join(visible) }等业务内容")
    if actions:
        parts.append(f"提供{ '、'.join(actions) }等操作入口")
    if states:
        parts.append(f"可见状态包括{ '、'.join(states) }")

    rec = _empty_record(chain_id=chain_id)
    rec["page_description"] = "，".join(parts) if parts else "页面业务语义信息有限，暂无法完整描述页面内容。"
    rec["page_function"] = function_hint
    rec["user_goal"] = goal_hint
    rec["scene"]["ui_task_scene"] = ui_scene
    rec["scene"]["refined_scene"] = refined_scene
    rec["scene"]["confidence"] = 0.55 if ui_scene != "其他" else 0.35
    return rec


def load_prompt_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def extract_json_obj(text: str) -> Dict[str, Any]:
    if not text:
        return {}

    s = text.strip()
    s = re.sub(r"^```(?:json)?\\n", "", s, flags=re.I)
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
            obj = json.loads(s[left:right + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    return {}


def build_prompt(template: str, input_payload: Dict[str, Any], strict: bool) -> str:
    prompt = template.replace("{INPUT_JSON}", json.dumps(input_payload, ensure_ascii=False, indent=2))
    if strict:
        prompt += (
            "\\n\\n【重试补充要求】\\n"
            "1) 只输出合法 JSON。\\n"
            "2) 只输出 page_description/page_function/user_goal/scene 这四层结构。\\n"
            "3) scene.ui_task_scene 必须在固定 taxonomy 内。\\n"
            "4) scene.refined_scene 必须在 refined taxonomy 内。\\n"
            "5) scene.confidence 必须是 0~1 浮点数。\\n"
            "6) 不要输出权限判定、证据链、控件清单。\\n"
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
                ] if image_b64 else [{"type": "text", "text": prompt}],
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

    raise RuntimeError(" | ".join(errors) if errors else "vlm_call_failed")


def _build_input_payload(
    chain_id: int,
    chain: Dict[str, Any],
    chain_summary_obj: Dict[str, Any],
    image_path: str,
    permissions_hint: List[str],
) -> Dict[str, Any]:
    return {
        "chain_id": chain_id,
        "package": chain.get("package") or chain.get("pkg") or "",
        "chain_image": {
            "path": image_path,
            "exists": os.path.exists(image_path),
            "note": "Use screenshot as primary evidence.",
        },
        "ocr_text": {
            "before_text": _as_text(chain_summary_obj.get("before_text", ""), max_len=700),
            "granting_text": _as_text(chain_summary_obj.get("granting_text", ""), max_len=700),
            "after_text": _as_text(chain_summary_obj.get("after_text", ""), max_len=700),
        },
        "widgets": [
            _as_text(x, max_len=40)
            for x in _as_list(chain_summary_obj.get("top_widgets"))[:20]
            if _as_text(x, max_len=40)
        ],
        "permissions_hint": _normalize_text_list(permissions_hint, max_items=10, max_len=60),
        "output_schema": {
            "page_description": "",
            "page_function": "",
            "user_goal": "",
            "scene": {
                "ui_task_scene": "from fixed taxonomy",
                "refined_scene": "from refined taxonomy",
                "confidence": 0.0,
            },
        },
    }


def normalize_semantics_record(
    chain_id: int,
    obj: Dict[str, Any],
    fallback: Dict[str, Any],
) -> Dict[str, Any]:
    rec = json.loads(json.dumps(fallback, ensure_ascii=False)) if isinstance(fallback, dict) else _empty_record(chain_id)
    rec["chain_id"] = int(chain_id)

    if not isinstance(obj, dict):
        obj = {}

    page_description = _as_text(obj.get("page_description"), max_len=560)
    page_function = _as_text(obj.get("page_function"), max_len=220)
    user_goal = _as_text(obj.get("user_goal"), max_len=220)

    scene_obj = obj.get("scene") if isinstance(obj.get("scene"), dict) else {}
    ui_raw = scene_obj.get("ui_task_scene")
    refined_raw = scene_obj.get("refined_scene")
    conf_raw = scene_obj.get("confidence")

    text_blob = " ".join([page_description, page_function, user_goal])
    inferred_ui, inferred_refined = _infer_scene_from_text(text_blob)

    ui_scene = _clean_scene(ui_raw or inferred_ui)
    refined_scene = _normalize_refined_scene(refined_raw or inferred_refined, ui_scene, text_blob)
    confidence = _normalize_confidence(conf_raw, default=0.35)

    rec["page_description"] = page_description or rec.get("page_description", "")
    rec["page_function"] = page_function or rec.get("page_function", "")
    rec["user_goal"] = user_goal or rec.get("user_goal", "")
    rec["scene"] = {
        "ui_task_scene": ui_scene,
        "refined_scene": refined_scene,
        "confidence": confidence,
    }

    # Keep mandatory non-empty function/goal in minimal form
    if not _as_text(rec.get("page_function"), 220):
        rec["page_function"], _ = _fallback_function_goal(ui_scene)
    if not _as_text(rec.get("user_goal"), 220):
        _, rec["user_goal"] = _fallback_function_goal(ui_scene)

    rec["page_description"] = _as_text(rec.get("page_description"), 560)
    rec["page_function"] = _as_text(rec.get("page_function"), 220)
    rec["user_goal"] = _as_text(rec.get("user_goal"), 220)
    return rec


def _is_effective_text(v: Any) -> bool:
    s = _as_text(v, max_len=220)
    if len(s) < 4:
        return False
    bad = {
        "页面功能待确认",
        "用户目标待确认",
        "不确定",
        "未知",
        "暂无",
    }
    return s not in bad


def should_rerun(rec: Dict[str, Any]) -> str:
    if not _is_effective_text(rec.get("page_description")):
        return "missing_page_description"
    if not _is_effective_text(rec.get("page_function")):
        return "missing_page_function"
    if not _is_effective_text(rec.get("user_goal")):
        return "missing_user_goal"

    scene = rec.get("scene") if isinstance(rec.get("scene"), dict) else {}
    ui_scene = _clean_scene(scene.get("ui_task_scene"))
    if ui_scene not in SCENE_SET:
        return "scene_not_in_taxonomy"

    refined = _normalize_refined_scene(scene.get("refined_scene"), ui_scene, _as_text(rec.get("page_description"), 280))
    if refined not in REFINED_SCENE_SET:
        return "refined_scene_not_in_taxonomy"

    try:
        conf = float(scene.get("confidence"))
    except Exception:
        return "invalid_confidence"
    if conf < 0.0 or conf > 1.0:
        return "confidence_out_of_range"

    return ""


def infer_chain_semantics(
    chain_id: int,
    image_path: str,
    input_payload: Dict[str, Any],
    prompt_template: str,
    vllm_url: str,
    model: str,
    single_pass_only: bool = False,
) -> Dict[str, Any]:
    chain_summary_obj = {
        "before_text": _as_text(input_payload.get("ocr_text", {}).get("before_text", ""), 320),
        "granting_text": _as_text(input_payload.get("ocr_text", {}).get("granting_text", ""), 320),
        "after_text": _as_text(input_payload.get("ocr_text", {}).get("after_text", ""), 320),
        "top_widgets": input_payload.get("widgets", []),
    }
    fallback = _default_semantics(chain_summary_obj, chain_id=chain_id)

    try:
        raw = call_vllm_vl(build_prompt(prompt_template, input_payload, strict=False), image_path, vllm_url, model)
        obj = extract_json_obj(raw)
        rec = normalize_semantics_record(chain_id=chain_id, obj=obj, fallback=fallback)
        reason = should_rerun(rec)

        if single_pass_only or not reason:
            return rec

        raw2 = call_vllm_vl(build_prompt(prompt_template, input_payload, strict=True), image_path, vllm_url, model)
        obj2 = extract_json_obj(raw2)
        rec2 = normalize_semantics_record(chain_id=chain_id, obj=obj2, fallback=fallback)
        reason2 = should_rerun(rec2)
        if reason2:
            return fallback
        return rec2
    except Exception as exc:
        print(f"[ChainSemantic][WARN] chain_id={chain_id} vllm_failed: {exc}")
        return fallback


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
        out[cid] = _normalize_text_list(perms, max_items=10, max_len=60)
    return out


def process_app(
    app_dir: str,
    prompt_template: str,
    vllm_url: str,
    model: str,
    output_filename: str = OUTPUT_FILENAME,
    schema_version: str = "v2",
    single_pass_only: bool = False,
    chain_filter: Optional[Set[int]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    del schema_version  # kept for main.py compatibility

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
        permissions_hint = _normalize_text_list(permissions_hint, max_items=10, max_len=60)

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

        conf = float(rec.get("scene", {}).get("confidence", 0.35))
        if conf < 0.5:
            low_conf += 1

        out.append(rec)

    out.sort(key=lambda x: int(x.get("chain_id", -1)))

    out_path = os.path.join(app_dir, output_filename)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[ChainSemantic] finish app={app_dir} chains={len(out)} low_conf={low_conf} out={out_path}")
    return out, low_conf


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

    for rec in records:
        scene = rec.get("scene") if isinstance(rec.get("scene"), dict) else {}
        conf = float(scene.get("confidence", 0.35))
        if conf >= 0.8:
            conf_label = "high"
        elif conf >= 0.5:
            conf_label = "medium"
        else:
            conf_label = "low"

        ui_scene = _as_text(scene.get("ui_task_scene"), 40) or "其他"
        refined = _as_text(scene.get("refined_scene"), 64) or "other"

        conf_counter[conf_label] += 1
        scene_counter[ui_scene] += 1
        refined_scene_counter[refined] += 1

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
    }


def run(
    target: str,
    prompt_file: str,
    vllm_url: str,
    model: str,
    output_filename: str = OUTPUT_FILENAME,
    summary_filename: str = SUMMARY_FILENAME,
    schema_version: str = "v2",
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
    parser = argparse.ArgumentParser(description="VLM multimodal chain semantic interpreter (minimal)")
    parser.add_argument("target", help="processed root or one app dir")
    parser.add_argument("--prompt-file", default=DEFAULT_PROMPT_FILE)
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_VL_URL", settings.VLLM_VL_URL))
    parser.add_argument("--model", default=os.getenv("VLLM_VL_MODEL", settings.VLLM_VL_MODEL))
    parser.add_argument("--output-filename", default=OUTPUT_FILENAME)
    parser.add_argument("--summary-filename", default=SUMMARY_FILENAME)
    parser.add_argument("--schema-version", choices=["v1", "v2"], default="v2")
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
