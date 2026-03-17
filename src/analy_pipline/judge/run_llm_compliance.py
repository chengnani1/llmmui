# -*- coding: utf-8 -*-
"""
Phase3 Step4: single-pass LLM compliance analysis.

Input (per chain):
- multimodal semantics
- permissions
- weak rule prior
- OCR/widgets evidence

Output (per chain):
{
  "necessity": {"label", "reason"},
  "consistency": {"label", "reason"},
  "over_scope": {"label", "reason"},
  "final_risk": "low|medium|high",
  "final_decision": "compliant|suspicious|non_compliant",
  "analysis_summary": "..."
}

Compatibility fields are kept:
- necessity_analysis / consistency_analysis / minimality_analysis
- llm_final_decision / llm_final_risk / llm_explanation
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from tqdm import tqdm

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.chain_summary import load_chain_summary_map  # noqa: E402
from analy_pipline.common.schema_utils import (  # noqa: E402
    normalize_llm_review_record,
    validate_rule_screening_results,
)
from analy_pipline.judge.knowledge_retriever import (  # noqa: E402
    load_case_knowledge_entries,
    load_pattern_knowledge_entries,
    load_prior_knowledge_entries,
    load_skill_knowledge_entries,
    retrieve_scene_conditioned_knowledge,
)
from configs import settings  # noqa: E402
from configs.domain.scene_config import SCENE_LIST  # noqa: E402
from utils.http_retry import post_json_with_retry  # noqa: E402


DEFAULT_PROCESSED_DIR = settings.DATA_PROCESSED_DIR
DEFAULT_PROMPT_DIR = settings.PROMPT_DIR

OUTPUT_FILENAME = "result_llm_review.json"
RETRIEVAL_FILENAME = "result_retrieved_knowledge.json"
SEMANTIC_FILENAME = "result_chain_semantics.json"
SEMANTIC_V2_FILENAME = "result_semantic_v2.json"
PERMISSION_FILENAME = "result_permission.json"
PROMPT_FILE = "llm_single_pass_compliance.txt"
SCENE_PRIOR_KNOWLEDGE_FILE = os.getenv(
    "LLMMUI_SCENE_PRIOR_KNOWLEDGE_FILE",
    os.path.join(ROOT, "configs", "scene_prior_knowledge.json"),
)
SCENE_PATTERN_KNOWLEDGE_FILE = os.getenv(
    "LLMMUI_SCENE_PATTERN_KNOWLEDGE_FILE",
    os.path.join(ROOT, "configs", "scene_pattern_knowledge.json"),
)
SCENE_CASE_KNOWLEDGE_FILE = os.getenv(
    "LLMMUI_SCENE_CASE_KNOWLEDGE_FILE",
    os.path.join(ROOT, "configs", "scene_case_knowledge.json"),
)
SCENE_SKILL_KNOWLEDGE_FILE = os.getenv(
    "LLMMUI_SCENE_SKILL_KNOWLEDGE_FILE",
    os.path.join(ROOT, "configs", "scene_skill_knowledge.json"),
)

CHAIN_TIMEOUT_SECONDS = int(os.getenv("LLMMUI_CHAIN_TIMEOUT_SECONDS", "120"))
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

TARGET_STORAGE_PAIR = {"READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"}
TARGET_LOCATION_PERMS = {"ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"}
SENSITIVE_HIGH_FREQ_PERMS = TARGET_STORAGE_PAIR | TARGET_LOCATION_PERMS


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    text = re.sub(r"^```(?:json)?\n", "", text, flags=re.I)
    text = re.sub(r"```$", "", text).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            obj = json.loads(text[s : e + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return {}


def _as_text(v: Any, max_len: int = 320) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _load_prompt(prompt_dir: str) -> str:
    path = os.path.join(prompt_dir, PROMPT_FILE)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            c = f.read().strip()
        if c:
            return c

    return """
你是安卓隐私合规分析助手。你将收到 UI 语义、结构化任务线索、规则先验和 scene-conditioned retrieved knowledge。

请完成一次性分析，输出严格 JSON，不要输出其它文本。

要求：
1) 必须先判断任务和证据，再判断 necessity / consistency / over_scope，最后给 final_decision。
2) Scene is already inferred in semantic parsing; do not re-classify scene.
3) refined_scene 优先于粗粒度 scene，rule_prior 与 retrieved knowledge 均为 soft guidance。
4) retrieved patterns / retrieved cases / retrieved skills 仅作为辅助上下文，不是硬规则。
5) 当 retrieved knowledge 与当前证据冲突时，以当前证据优先。
6) Retrieved patterns highlight common positive and negative cues.
7) Retrieved cases illustrate typical risky/compliant examples.
8) Retrieved skills are distilled heuristics from strong experiments; use them only when field/scene match is strong.
9) Current chain evidence has higher priority than retrieved examples.
10) 优先使用 structured_cues（storage_read_cues / storage_write_cues / location_task_cues）。
11) READ+WRITE 存储成对权限，只有读写证据都明确时，才允许 compliant+low。
12) location 只有在强位置任务证据存在时，才允许 necessary/compliant+low。
13) 证据不足时优先 suspicious+medium，不要默认 compliant+low。

标签集合：
- necessity.label: necessary | helpful | unnecessary
- consistency.label: consistent | weakly_consistent | inconsistent
- over_scope.label: minimal | potentially_over_scoped | over_scoped
- final_risk: low | medium | high
- final_decision: compliant | suspicious | non_compliant
- confidence: 0.0~1.0

输入：
{INPUT}

输出：
{
  "necessity": {"label": "...", "reason": "..."},
  "consistency": {"label": "...", "reason": "..."},
  "over_scope": {"label": "...", "reason": "..."},
  "final_risk": "low|medium|high",
  "final_decision": "compliant|suspicious|non_compliant",
  "confidence": 0.0,
  "analysis_summary": "..."
}
""".strip()


def _call_llm(prompt: str, vllm_url: str, model: str, timeout_seconds: int) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    r = post_json_with_retry(
        vllm_url,
        payload,
        timeout=timeout_seconds,
        max_retries=0,
        backoff_factor=1.5,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _load_semantics_map(app_dir: str, filename: str = SEMANTIC_FILENAME) -> Dict[int, Dict[str, Any]]:
    path = os.path.join(app_dir, filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    if not isinstance(raw, list):
        return {}

    out: Dict[int, Dict[str, Any]] = {}
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            continue
        out[cid] = item
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
    if not isinstance(raw, list):
        return {}

    out: Dict[int, List[str]] = {}
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            continue
        perms = [_as_text(x, 64).upper() for x in _as_list(item.get("predicted_permissions")) if _as_text(x, 64)]
        out[cid] = perms
    return out


def _resolve_refined_scene(chain: Dict[str, Any], sem: Dict[str, Any]) -> str:
    rs = _as_text(chain.get("refined_scene") or sem.get("refined_scene"), 64).lower()
    if rs in REFINED_SCENE_SET:
        return rs
    ui_scene = _as_text(chain.get("ui_task_scene") or sem.get("ui_task_scene"), 40)
    return UI_TO_REFINED_FALLBACK.get(ui_scene, "content_browsing")


def _perm_set(v: Any) -> Set[str]:
    out: Set[str] = set()
    for x in _as_list(v):
        p = _as_text(x, 64).upper()
        if p:
            out.add(p)
    return out


def _merge_unique(values: List[str], extra: List[str], max_items: int = 12) -> List[str]:
    out: List[str] = []
    for x in values + extra:
        v = _as_text(x, 60)
        if not v:
            continue
        if v not in out:
            out.append(v)
        if len(out) >= max_items:
            break
    return out


def _collect_structured_cues(
    sem: Dict[str, Any],
    chain: Dict[str, Any],
    chain_summary_obj: Dict[str, Any],
) -> Dict[str, List[str]]:
    cues = {
        "permission_task_cues": [_as_text(x, 60) for x in _as_list(sem.get("permission_task_cues")) if _as_text(x, 60)],
        "storage_read_cues": [_as_text(x, 60) for x in _as_list(sem.get("storage_read_cues")) if _as_text(x, 60)],
        "storage_write_cues": [_as_text(x, 60) for x in _as_list(sem.get("storage_write_cues")) if _as_text(x, 60)],
        "location_task_cues": [_as_text(x, 60) for x in _as_list(sem.get("location_task_cues")) if _as_text(x, 60)],
        "upload_task_cues": [_as_text(x, 60) for x in _as_list(sem.get("upload_task_cues")) if _as_text(x, 60)],
        "cleanup_task_cues": [_as_text(x, 60) for x in _as_list(sem.get("cleanup_task_cues")) if _as_text(x, 60)],
    }

    text_blob = " ".join(
        [
            _as_text(sem.get("user_intent") or chain.get("intent"), 240),
            _as_text(sem.get("trigger_action") or chain.get("trigger_action"), 120),
            _as_text(sem.get("page_observation") or chain.get("page_function"), 320),
            _as_text(chain.get("chain_summary"), 320),
            _as_text(chain_summary_obj.get("before_text"), 320),
            _as_text(chain_summary_obj.get("granting_text"), 320),
            _as_text(chain_summary_obj.get("after_text"), 320),
            " ".join([_as_text(x, 40) for x in _as_list(sem.get("visual_evidence"))[:8] if _as_text(x, 40)]),
            " ".join([_as_text(x, 40) for x in _as_list(chain_summary_obj.get("top_widgets", []))[:12] if _as_text(x, 40)]),
        ]
    ).lower()

    if any(k in text_blob for k in ["选择文件", "选择图片", "选择视频", "相册", "浏览本地", "读取文件", "导入"]):
        cues["storage_read_cues"] = _merge_unique(cues["storage_read_cues"], ["storage_read_from_local"], max_items=8)
    if any(k in text_blob for k in ["保存", "导出", "写入", "下载到本地", "恢复回写", "落盘", "缓存到本地"]):
        cues["storage_write_cues"] = _merge_unique(cues["storage_write_cues"], ["storage_write_to_local"], max_items=8)
    if any(k in text_blob for k in ["导航", "附近", "周边", "路线", "定位", "同城", "网点", "wifi扫描", "nearby devices", "附近设备"]):
        cues["location_task_cues"] = _merge_unique(cues["location_task_cues"], ["location_task_present"], max_items=8)
    if any(k in text_blob for k in ["上传", "附件", "头像", "发送文件", "发布", "提交"]):
        cues["upload_task_cues"] = _merge_unique(cues["upload_task_cues"], ["upload_or_attachment_task"], max_items=8)
    if any(k in text_blob for k in ["垃圾清理", "缓存清理", "清理空间", "深度清理", "重复文件", "释放空间", "一键清理", "视频清理"]):
        cues["cleanup_task_cues"] = _merge_unique(cues["cleanup_task_cues"], ["cleanup_or_space_release_task"], max_items=8)

    cues["permission_task_cues"] = _merge_unique(
        cues["permission_task_cues"],
        cues["storage_read_cues"] + cues["storage_write_cues"] + cues["location_task_cues"] + cues["upload_task_cues"] + cues["cleanup_task_cues"],
        max_items=12,
    )
    return cues


def _normalize_necessity(label: str) -> str:
    v = _as_text(label, 40).lower()
    if v in {"necessary", "helpful", "unnecessary"}:
        return v
    if v in {"partial", "partially_necessary", "weak_necessary"}:
        return "helpful"
    return "helpful"


def _normalize_consistency(label: str) -> str:
    v = _as_text(label, 40).lower()
    if v in {"consistent", "weakly_consistent", "inconsistent"}:
        return v
    if v in {"partial", "partially_consistent", "weak"}:
        return "weakly_consistent"
    return "weakly_consistent"


def _normalize_over_scope(label: str) -> str:
    v = _as_text(label, 60).lower()
    if v in {"minimal", "potentially_over_scoped", "over_scoped"}:
        return v
    if v in {"potentially_over_scope", "potentially_over_privileged"}:
        return "potentially_over_scoped"
    if v in {"over_privileged", "over_scope"}:
        return "over_scoped"
    return "potentially_over_scoped"


def _normalize_final_risk(label: str) -> str:
    v = _as_text(label, 20).lower()
    return v if v in {"low", "medium", "high"} else "medium"


def _normalize_final_decision(label: str) -> str:
    v = _as_text(label, 40).lower()
    if v in {"compliant", "suspicious", "non_compliant"}:
        return v
    if v in {"noncompliant", "non-compliant"}:
        return "non_compliant"
    return "suspicious"


def _normalize_confidence(value: Any) -> float:
    if isinstance(value, str):
        v = value.strip().lower()
        if v == "high":
            return 0.9
        if v == "medium":
            return 0.65
        if v == "low":
            return 0.35
    try:
        score = float(value)
    except Exception:
        score = 0.35
    if score < 0:
        score = 0.0
    if score > 1:
        score = 1.0
    return round(score, 3)


def _to_compat_fields(one_pass: Dict[str, Any]) -> Dict[str, Any]:
    necessity = one_pass.get("necessity") if isinstance(one_pass.get("necessity"), dict) else {}
    consistency = one_pass.get("consistency") if isinstance(one_pass.get("consistency"), dict) else {}
    over_scope = one_pass.get("over_scope") if isinstance(one_pass.get("over_scope"), dict) else {}

    nec_label = _normalize_necessity(necessity.get("label", ""))
    con_label = _normalize_consistency(consistency.get("label", ""))
    ovs_label = _normalize_over_scope(over_scope.get("label", ""))

    final_risk = _normalize_final_risk(one_pass.get("final_risk", ""))
    final_decision = _normalize_final_decision(one_pass.get("final_decision", ""))
    confidence = _normalize_confidence(one_pass.get("confidence", 0.35))

    # Compatibility mapping to old internal fields.
    minimality_label = {
        "minimal": "minimal",
        "potentially_over_scoped": "potentially_over_privileged",
        "over_scoped": "over_privileged",
    }[ovs_label]

    llm_final_decision = {
        "compliant": "COMPLIANT",
        "suspicious": "SUSPICIOUS",
        "non_compliant": "NON_COMPLIANT",
    }[final_decision]

    llm_final_risk = {
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
    }[final_risk]

    return {
        "necessity": {
            "label": nec_label,
            "reason": _as_text(necessity.get("reason", ""), 320),
        },
        "consistency": {
            "label": con_label,
            "reason": _as_text(consistency.get("reason", ""), 320),
        },
        "over_scope": {
            "label": ovs_label,
            "reason": _as_text(over_scope.get("reason", ""), 320),
        },
        "final_risk": final_risk,
        "final_decision": final_decision,
        "confidence": confidence,
        "analysis_summary": _as_text(one_pass.get("analysis_summary", ""), 500),
        # old compatibility
        "necessity_analysis": {"label": nec_label, "reason": _as_text(necessity.get("reason", ""), 320)},
        "consistency_analysis": {"label": con_label, "reason": _as_text(consistency.get("reason", ""), 320)},
        "minimality_analysis": {"label": minimality_label, "reason": _as_text(over_scope.get("reason", ""), 320)},
        "llm_final_decision": llm_final_decision,
        "llm_final_risk": llm_final_risk,
        "llm_explanation": _as_text(one_pass.get("analysis_summary", ""), 500),
    }


def _build_fallback(reason: str) -> Dict[str, Any]:
    return {
        "necessity": {"label": "helpful", "reason": f"fallback:{reason}"},
        "consistency": {"label": "weakly_consistent", "reason": f"fallback:{reason}"},
        "over_scope": {"label": "potentially_over_scoped", "reason": f"fallback:{reason}"},
        "final_risk": "medium",
        "final_decision": "suspicious",
        "confidence": 0.35,
        "analysis_summary": f"fallback_due_to_{reason}",
    }


def _sync_compat_fields(parsed: Dict[str, Any]) -> Dict[str, Any]:
    nec = parsed.get("necessity") if isinstance(parsed.get("necessity"), dict) else {}
    con = parsed.get("consistency") if isinstance(parsed.get("consistency"), dict) else {}
    ovs = parsed.get("over_scope") if isinstance(parsed.get("over_scope"), dict) else {}
    final_dec = _normalize_final_decision(parsed.get("final_decision", "suspicious"))
    final_risk = _normalize_final_risk(parsed.get("final_risk", "medium"))

    minimality_label = {
        "minimal": "minimal",
        "potentially_over_scoped": "potentially_over_privileged",
        "over_scoped": "over_privileged",
    }[_normalize_over_scope(ovs.get("label", "potentially_over_scoped"))]
    parsed["necessity_analysis"] = {
        "label": _normalize_necessity(nec.get("label", "helpful")),
        "reason": _as_text(nec.get("reason", ""), 320),
    }
    parsed["consistency_analysis"] = {
        "label": _normalize_consistency(con.get("label", "weakly_consistent")),
        "reason": _as_text(con.get("reason", ""), 320),
    }
    parsed["minimality_analysis"] = {
        "label": minimality_label,
        "reason": _as_text(ovs.get("reason", ""), 320),
    }
    parsed["llm_final_decision"] = {
        "compliant": "COMPLIANT",
        "suspicious": "SUSPICIOUS",
        "non_compliant": "NON_COMPLIANT",
    }[final_dec]
    parsed["llm_final_risk"] = {
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
    }[final_risk]
    parsed["llm_explanation"] = _as_text(parsed.get("analysis_summary", ""), 500)
    parsed["final_decision"] = final_dec
    parsed["final_risk"] = final_risk
    parsed["confidence"] = _normalize_confidence(parsed.get("confidence", 0.35))
    return parsed


def _apply_storage_softening(
    parsed: Dict[str, Any],
    chain: Dict[str, Any],
    sem: Dict[str, Any],
    chain_summary_obj: Dict[str, Any],
) -> Dict[str, Any]:
    final_decision = _normalize_final_decision(parsed.get("final_decision", "suspicious"))
    final_risk = _normalize_final_risk(parsed.get("final_risk", "medium"))
    if final_decision != "compliant" or final_risk != "low":
        return parsed

    perms = _perm_set(chain.get("permissions", []))
    cues = _collect_structured_cues(sem=sem, chain=chain, chain_summary_obj=chain_summary_obj)
    reasons: List[str] = []

    if TARGET_STORAGE_PAIR.issubset(perms):
        has_read = bool(cues.get("storage_read_cues"))
        has_write = bool(cues.get("storage_write_cues"))
        if not (has_read and has_write):
            reasons.append("storage_dual_evidence_missing")

    if perms & TARGET_LOCATION_PERMS:
        if not cues.get("location_task_cues"):
            reasons.append("location_task_cues_missing")

    has_task = bool(_as_text(sem.get("user_intent") or chain.get("intent"), 240)) and bool(
        _as_text(sem.get("trigger_action") or chain.get("trigger_action"), 120)
    )
    has_page_evidence = len(_as_list(sem.get("visual_evidence"))) >= 2 or len(
        _as_text(sem.get("page_observation") or chain.get("page_function"), 320)
    ) >= 12
    if not (has_task and has_page_evidence):
        reasons.append("weak_task_or_page_evidence")

    rule_prior = _as_text(chain.get("rule_prior"), 20).lower()
    if rule_prior == "unexpected" and (perms & SENSITIVE_HIGH_FREQ_PERMS):
        reasons.append("unexpected_prior_on_sensitive_permission")

    if not reasons:
        return parsed

    # Distilled guardrail: strong necessity threshold for compliant+low.
    parsed["final_decision"] = "suspicious"
    parsed["final_risk"] = "medium"
    if isinstance(parsed.get("necessity"), dict) and parsed["necessity"].get("label") == "necessary":
        parsed["necessity"]["label"] = "helpful"
    if isinstance(parsed.get("consistency"), dict) and parsed["consistency"].get("label") == "consistent":
        parsed["consistency"]["label"] = "weakly_consistent"
    if isinstance(parsed.get("over_scope"), dict) and parsed["over_scope"].get("label") == "minimal":
        parsed["over_scope"]["label"] = "potentially_over_scoped"
    summary = _as_text(parsed.get("analysis_summary", ""), 500)
    gate_note = "distilled_gating:" + ",".join(sorted(set(reasons)))
    parsed["analysis_summary"] = _as_text(f"{summary} | {gate_note}" if summary else gate_note, 500)

    return _sync_compat_fields(parsed)


def _run_one_pass(
    prompt_template: str,
    payload: Dict[str, Any],
    vllm_url: str,
    model: str,
    timeout_seconds: int,
) -> Tuple[Dict[str, Any], bool, str, str]:
    prompt = prompt_template.replace("{INPUT}", json.dumps(payload, ensure_ascii=False, indent=2))
    try:
        raw = _call_llm(prompt, vllm_url=vllm_url, model=model, timeout_seconds=timeout_seconds)
    except Exception as exc:
        msg = str(exc)
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            return {}, False, msg, "timeout"
        return {}, False, msg, "request_error"

    obj = _extract_json(raw)
    if not isinstance(obj, dict) or not obj:
        return {}, False, raw, "format_error"

    # Minimal structural guard.
    if not isinstance(obj.get("necessity"), dict) or not isinstance(obj.get("consistency"), dict):
        return {}, False, raw, "format_error"
    if not isinstance(obj.get("over_scope"), dict):
        return {}, False, raw, "format_error"

    return obj, True, raw, ""


def _build_record(
    chain: Dict[str, Any],
    sem: Dict[str, Any],
    chain_summary_obj: Dict[str, Any],
    one_pass_obj: Dict[str, Any],
    output_valid: bool,
    raw_output: str,
    fallback_reason: str,
    apply_softening: bool = True,
) -> Dict[str, Any]:
    parsed = _to_compat_fields(one_pass_obj)
    if apply_softening:
        parsed = _apply_storage_softening(parsed, chain=chain, sem=sem, chain_summary_obj=chain_summary_obj)
    refined_scene = _resolve_refined_scene(chain=chain, sem=sem)

    record = {
        "chain_id": chain.get("chain_id"),
        "scene": chain.get("scene"),
        "ui_task_scene": chain.get("ui_task_scene") or chain.get("scene") or sem.get("ui_task_scene", ""),
        "refined_scene": refined_scene,
        "ui_task_scene_top3": chain.get("ui_task_scene_top3", []),
        "regulatory_scene": chain.get("regulatory_scene") or chain.get("regulatory_scene_top1", ""),
        "regulatory_scene_top1": chain.get("regulatory_scene_top1", ""),
        "regulatory_scene_top3": chain.get("regulatory_scene_top3", []),
        "task_phrase": _as_text(chain.get("task_phrase") or sem.get("trigger_action") or sem.get("ui_task_scene", ""), 120),
        "intent": _as_text(chain.get("intent") or sem.get("user_intent", ""), 240),
        "page_function": _as_text(chain.get("page_function") or sem.get("page_observation", ""), 280),
        "trigger_action": _as_text(chain.get("trigger_action") or sem.get("trigger_action", ""), 100),
        "visible_actions": _as_list(chain.get("visible_actions")),
        "task_relevance_cues": (
            _as_list(chain.get("task_relevance_cues"))
            + _as_list(sem.get("permission_task_cues"))
            + _as_list(sem.get("visual_evidence"))
        ),
        "permission_context": _as_text(
            chain.get("permission_context")
            or sem.get("page_observation", "")
            or ((sem.get("permission_event") or {}).get("ui_observation", "")),
            320,
        ),
        "permissions": _as_list(chain.get("permissions")),
        "allowed_permissions": _as_list(chain.get("allowed_permissions")),
        "banned_permissions": _as_list(chain.get("banned_permissions")),
        "rule_signal": _as_text(chain.get("overall_rule_signal", "MEDIUM_RISK"), 32),
        "rule_prior": _as_text(chain.get("rule_prior", "suspicious"), 20),
        "rule_notes": _as_list(chain.get("rule_notes"))[:8],
        "chain_summary": _as_text(chain.get("chain_summary") or sem.get("page_observation", ""), 500),
        "semantic": {
            "ui_task_scene": _as_text(sem.get("ui_task_scene", ""), 80),
            "refined_scene": refined_scene,
            "user_intent": _as_text(sem.get("user_intent", ""), 240),
            "trigger_action": _as_text(sem.get("trigger_action", ""), 100),
            "page_observation": _as_text(sem.get("page_observation", ""), 280),
            "visual_evidence": _as_list(sem.get("visual_evidence"))[:8],
        },
        "ocr_triplet": {
            "before_text": _as_text(chain_summary_obj.get("before_text", ""), 320),
            "granting_text": _as_text(chain_summary_obj.get("granting_text", ""), 320),
            "after_text": _as_text(chain_summary_obj.get("after_text", ""), 320),
        },
        "top_widgets": [_as_text(x, 36) for x in _as_list(chain_summary_obj.get("top_widgets", []))[:12] if _as_text(x, 36)],
        # New one-pass output
        "necessity": parsed["necessity"],
        "consistency": parsed["consistency"],
        "over_scope": parsed["over_scope"],
        "final_risk": parsed["final_risk"],
        "final_decision": parsed["final_decision"],
        "confidence": parsed.get("confidence", 0.35),
        "analysis_summary": parsed["analysis_summary"],
        # Compatibility fields
        "necessity_analysis": parsed["necessity_analysis"],
        "consistency_analysis": parsed["consistency_analysis"],
        "minimality_analysis": parsed["minimality_analysis"],
        "llm_final_decision": parsed["llm_final_decision"],
        "llm_final_risk": parsed["llm_final_risk"],
        "llm_explanation": parsed["llm_explanation"],
        "output_valid": bool(output_valid),
        "format_error": bool((not output_valid) and fallback_reason == "format_error"),
    }
    if not output_valid:
        record["raw_output"] = _as_text(raw_output, 1600)
        record["fallback_reason"] = _as_text(fallback_reason, 80)

    return normalize_llm_review_record(record)


def _rule_screening_path(app_dir: str) -> str:
    path = os.path.join(app_dir, "result_rule_screening.json")
    return path if os.path.exists(path) else ""


def _semantic_confidence_score(sem: Dict[str, Any]) -> float:
    raw = sem.get("confidence")
    try:
        return _normalize_confidence(float(raw))
    except Exception:
        pass
    label = _as_text(raw, 20).lower()
    if label == "high":
        return 0.9
    if label == "medium":
        return 0.65
    if label == "low":
        return 0.35
    return 0.35


def _structured_cues_from_task_cues(sem: Dict[str, Any]) -> Dict[str, List[str]]:
    task_cues = sem.get("task_cues") if isinstance(sem.get("task_cues"), dict) else {}
    return {
        "storage_read_cues": [_as_text(x, 60) for x in _as_list(task_cues.get("storage_read")) if _as_text(x, 60)],
        "storage_write_cues": [_as_text(x, 60) for x in _as_list(task_cues.get("storage_write")) if _as_text(x, 60)],
        "location_task_cues": [_as_text(x, 60) for x in _as_list(task_cues.get("location")) if _as_text(x, 60)],
        "upload_task_cues": [_as_text(x, 60) for x in _as_list(task_cues.get("upload")) if _as_text(x, 60)],
        "cleanup_task_cues": [_as_text(x, 60) for x in _as_list(task_cues.get("cleanup")) if _as_text(x, 60)],
        "camera_task_cues": [_as_text(x, 60) for x in _as_list(task_cues.get("camera")) if _as_text(x, 60)],
        "audio_task_cues": [_as_text(x, 60) for x in _as_list(task_cues.get("audio")) if _as_text(x, 60)],
    }


def process_app_dir(
    app_dir: str,
    vllm_url: str,
    model: str,
    prompt_template: str,
    prior_knowledge_entries: List[Dict[str, Any]],
    pattern_knowledge_entries: List[Dict[str, Any]],
    case_knowledge_entries: List[Dict[str, Any]],
    skill_knowledge_entries: List[Dict[str, Any]],
    chain_ids_filter: Optional[Set[int]] = None,
) -> Tuple[int, int]:
    rule_path = _rule_screening_path(app_dir)
    result_json_path = os.path.join(app_dir, "result.json")
    if not rule_path:
        print(f"[LLM-Review] skip app={app_dir} missing rule screening file")
        return 0, 0
    if not os.path.exists(result_json_path):
        print(f"[LLM-Review] skip app={app_dir} missing result.json")
        return 0, 0

    with open(rule_path, "r", encoding="utf-8") as f:
        screening_raw = json.load(f)
    screening, invalid = validate_rule_screening_results(screening_raw, SCENE_LIST)

    sem_map = _load_semantics_map(app_dir)
    permissions_map = {int(x["chain_id"]): x.get("permissions", []) for x in screening}
    summary_map = load_chain_summary_map(result_json_path, permissions_map=permissions_map)

    outputs: List[Dict[str, Any]] = []
    invalid_outputs = invalid

    for chain in screening:
        chain_id = int(chain.get("chain_id", -1))
        if chain_ids_filter is not None and chain_id not in chain_ids_filter:
            continue

        sem = sem_map.get(chain_id, {})
        chain_summary = summary_map.get(chain_id, {"chain_summary": {}})
        chain_summary_obj = chain_summary.get("chain_summary", {})
        if not isinstance(chain_summary_obj, dict):
            chain_summary_obj = {}
        refined_scene = _resolve_refined_scene(chain=chain, sem=sem)
        structured_cues = _collect_structured_cues(sem=sem, chain=chain, chain_summary_obj=chain_summary_obj)
        regulatory_scene = chain.get("regulatory_scene") or chain.get("regulatory_scene_top1", "")
        rule_prior = chain.get("rule_prior", "suspicious")
        retrieved_knowledge = retrieve_scene_conditioned_knowledge(
            prior_entries=prior_knowledge_entries,
            pattern_entries=pattern_knowledge_entries,
            case_entries=case_knowledge_entries,
            refined_scene=refined_scene,
            ui_task_scene=chain.get("ui_task_scene") or sem.get("ui_task_scene", ""),
            permissions=chain.get("permissions", []),
            user_intent=sem.get("user_intent") or chain.get("intent", ""),
            trigger_action=sem.get("trigger_action") or chain.get("trigger_action", ""),
            page_observation=sem.get("page_observation") or chain.get("page_function", ""),
            visual_evidence=sem.get("visual_evidence", []),
            skill_entries=skill_knowledge_entries,
            rule_prior=rule_prior,
            regulatory_scene=regulatory_scene,
            structured_cues=structured_cues,
            top_k_patterns=2,
            top_k_cases=2,
            top_k_risky_cases=2,
            top_k_compliant_cases=2,
            top_k_skills=2,
        )

        payload = {
            "chain_id": chain_id,
            "refined_scene": refined_scene,
            "semantic": {
                "ui_task_scene": sem.get("ui_task_scene", ""),
                "refined_scene": refined_scene,
                "user_intent": sem.get("user_intent", ""),
                "trigger_action": sem.get("trigger_action", ""),
                "page_observation": sem.get("page_observation", ""),
                "visual_evidence": sem.get("visual_evidence", []),
                "permission_task_cues": structured_cues.get("permission_task_cues", []),
                "storage_read_cues": structured_cues.get("storage_read_cues", []),
                "storage_write_cues": structured_cues.get("storage_write_cues", []),
                "location_task_cues": structured_cues.get("location_task_cues", []),
                "upload_task_cues": structured_cues.get("upload_task_cues", []),
                "cleanup_task_cues": structured_cues.get("cleanup_task_cues", []),
            },
            "structured_cues": structured_cues,
            "permissions": chain.get("permissions", []),
            "rule_prior": rule_prior,
            "rule_notes": chain.get("rule_notes", []),
            "ui_task_scene": chain.get("ui_task_scene") or sem.get("ui_task_scene", ""),
            "regulatory_scene": regulatory_scene,
            "regulatory_scene_top1": chain.get("regulatory_scene_top1", ""),
            "regulatory_scene_top3": chain.get("regulatory_scene_top3", []),
            "retrieved_knowledge": retrieved_knowledge,
            "ocr_triplet": {
                "before_text": _as_text(chain_summary_obj.get("before_text", ""), 320),
                "granting_text": _as_text(chain_summary_obj.get("granting_text", ""), 320),
                "after_text": _as_text(chain_summary_obj.get("after_text", ""), 320),
            },
            "widgets": [_as_text(x, 40) for x in _as_list(chain_summary_obj.get("top_widgets", []))[:14] if _as_text(x, 40)],
            "chain_summary": chain.get("chain_summary") or sem.get("page_observation", ""),
        }

        one_pass, ok, raw, fail_reason = _run_one_pass(
            prompt_template=prompt_template,
            payload=payload,
            vllm_url=vllm_url,
            model=model,
            timeout_seconds=CHAIN_TIMEOUT_SECONDS,
        )

        if not ok:
            one_pass = _build_fallback(fail_reason or "invalid_output")
            invalid_outputs += 1

        outputs.append(
            _build_record(
                chain=chain,
                sem=sem,
                chain_summary_obj=chain_summary_obj,
                one_pass_obj=one_pass,
                output_valid=ok,
                raw_output=raw,
                fallback_reason=fail_reason,
                apply_softening=True,
            )
        )

    out_path = os.path.join(app_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=2, ensure_ascii=False)

    print(
        f"[LLM-Review] finish app={app_dir} reviewed={len(outputs)} "
        f"invalid={invalid_outputs} out={out_path}"
    )
    return len(outputs), invalid_outputs


def process_app_dir_v2(
    app_dir: str,
    vllm_url: str,
    model: str,
    prompt_template: str,
    prior_knowledge_entries: List[Dict[str, Any]],
    pattern_knowledge_entries: List[Dict[str, Any]],
    case_knowledge_entries: List[Dict[str, Any]],
    skill_knowledge_entries: List[Dict[str, Any]],
    semantic_filename: str = SEMANTIC_V2_FILENAME,
    retrieval_output_filename: str = RETRIEVAL_FILENAME,
    chain_ids_filter: Optional[Set[int]] = None,
) -> Tuple[int, int]:
    result_json_path = os.path.join(app_dir, "result.json")
    if not os.path.exists(result_json_path):
        print(f"[LLM-Review-V2] skip app={app_dir} missing result.json")
        return 0, 0

    sem_map = _load_semantics_map(app_dir, filename=semantic_filename)
    if not sem_map and semantic_filename != SEMANTIC_FILENAME:
        sem_map = _load_semantics_map(app_dir, filename=SEMANTIC_FILENAME)
    if not sem_map:
        print(f"[LLM-Review-V2] skip app={app_dir} missing semantic file")
        return 0, 0

    permission_map = _load_permission_map(app_dir)
    summary_map = load_chain_summary_map(result_json_path, permissions_map=permission_map)

    outputs: List[Dict[str, Any]] = []
    retrieval_outputs: List[Dict[str, Any]] = []
    invalid_outputs = 0

    for chain_id in sorted(sem_map.keys()):
        if chain_ids_filter is not None and chain_id not in chain_ids_filter:
            continue

        sem = sem_map.get(chain_id, {})
        chain_summary = summary_map.get(chain_id, {"chain_summary": {}})
        chain_summary_obj = chain_summary.get("chain_summary", {})
        if not isinstance(chain_summary_obj, dict):
            chain_summary_obj = {}

        permissions = permission_map.get(chain_id)
        if not permissions:
            permissions = [_as_text(x, 64).upper() for x in _as_list(sem.get("permissions_hint")) if _as_text(x, 64)]

        chain_stub = {
            "chain_id": chain_id,
            "scene": _as_text(sem.get("ui_task_scene"), 80),
            "ui_task_scene": _as_text(sem.get("ui_task_scene"), 80),
            "refined_scene": _as_text(sem.get("refined_scene"), 64),
            "task_phrase": _as_text(sem.get("trigger_action"), 120),
            "intent": _as_text(sem.get("user_intent"), 240),
            "page_function": _as_text(sem.get("page_observation"), 280),
            "trigger_action": _as_text(sem.get("trigger_action"), 120),
            "permissions": permissions,
            "overall_rule_signal": "MEDIUM_RISK",
            "rule_prior": "suspicious",
            "rule_notes": [],
            "chain_summary": _as_text(sem.get("page_observation"), 320),
        }

        structured_cues = _collect_structured_cues(sem=sem, chain=chain_stub, chain_summary_obj=chain_summary_obj)
        task_cue_map = _structured_cues_from_task_cues(sem)
        for k in ["storage_read_cues", "storage_write_cues", "location_task_cues", "upload_task_cues", "cleanup_task_cues"]:
            structured_cues[k] = _merge_unique(structured_cues.get(k, []), task_cue_map.get(k, []), max_items=12)
        structured_cues["permission_task_cues"] = _merge_unique(
            structured_cues.get("permission_task_cues", []),
            structured_cues.get("storage_read_cues", [])
            + structured_cues.get("storage_write_cues", [])
            + structured_cues.get("location_task_cues", [])
            + structured_cues.get("upload_task_cues", [])
            + structured_cues.get("cleanup_task_cues", [])
            + task_cue_map.get("camera_task_cues", [])
            + task_cue_map.get("audio_task_cues", []),
            max_items=16,
        )

        refined_scene = _resolve_refined_scene(chain=chain_stub, sem=sem)
        retrieved_knowledge = retrieve_scene_conditioned_knowledge(
            prior_entries=prior_knowledge_entries,
            pattern_entries=pattern_knowledge_entries,
            case_entries=case_knowledge_entries,
            refined_scene=refined_scene,
            ui_task_scene=_as_text(sem.get("ui_task_scene"), 80),
            permissions=permissions,
            user_intent=_as_text(sem.get("user_intent"), 240),
            trigger_action=_as_text(sem.get("trigger_action"), 120),
            page_observation=_as_text(sem.get("page_observation"), 320),
            visual_evidence=_as_list(sem.get("visual_evidence")),
            skill_entries=skill_knowledge_entries,
            rule_prior="suspicious",
            regulatory_scene="",
            structured_cues=structured_cues,
            top_k_patterns=2,
            top_k_cases=4,
            top_k_risky_cases=2,
            top_k_compliant_cases=2,
            top_k_skills=2,
        )

        retrieval_outputs.append(
            {
                "chain_id": chain_id,
                "ui_task_scene": _as_text(sem.get("ui_task_scene"), 80),
                "refined_scene": refined_scene,
                "permissions": permissions,
                "retrieved_knowledge": retrieved_knowledge,
            }
        )

        payload = {
            "chain_id": chain_id,
            "refined_scene": refined_scene,
            "semantic": {
                "ui_task_scene": _as_text(sem.get("ui_task_scene"), 80),
                "refined_scene": refined_scene,
                "user_intent": _as_text(sem.get("user_intent"), 240),
                "trigger_action": _as_text(sem.get("trigger_action"), 100),
                "page_observation": _as_text(sem.get("page_observation"), 280),
                "visual_evidence": _as_list(sem.get("visual_evidence"))[:8],
                "task_cues": sem.get("task_cues", {}) if isinstance(sem.get("task_cues"), dict) else {},
                "permission_task_cues": structured_cues.get("permission_task_cues", []),
                "storage_read_cues": structured_cues.get("storage_read_cues", []),
                "storage_write_cues": structured_cues.get("storage_write_cues", []),
                "location_task_cues": structured_cues.get("location_task_cues", []),
                "upload_task_cues": structured_cues.get("upload_task_cues", []),
                "cleanup_task_cues": structured_cues.get("cleanup_task_cues", []),
                "camera_task_cues": task_cue_map.get("camera_task_cues", []),
                "audio_task_cues": task_cue_map.get("audio_task_cues", []),
            },
            "structured_cues": structured_cues,
            "permissions": permissions,
            "retrieved_knowledge": retrieved_knowledge,
            "ocr_triplet": {
                "before_text": _as_text(chain_summary_obj.get("before_text", ""), 320),
                "granting_text": _as_text(chain_summary_obj.get("granting_text", ""), 320),
                "after_text": _as_text(chain_summary_obj.get("after_text", ""), 320),
            },
            "widgets": [_as_text(x, 40) for x in _as_list(chain_summary_obj.get("top_widgets", []))[:14] if _as_text(x, 40)],
            "chain_summary": _as_text(sem.get("page_observation"), 320),
        }

        one_pass, ok, raw, fail_reason = _run_one_pass(
            prompt_template=prompt_template,
            payload=payload,
            vllm_url=vllm_url,
            model=model,
            timeout_seconds=CHAIN_TIMEOUT_SECONDS,
        )
        if not ok:
            one_pass = _build_fallback(fail_reason or "invalid_output")
            invalid_outputs += 1
        if "confidence" not in one_pass:
            one_pass["confidence"] = _semantic_confidence_score(sem)

        outputs.append(
            _build_record(
                chain=chain_stub,
                sem=sem,
                chain_summary_obj=chain_summary_obj,
                one_pass_obj=one_pass,
                output_valid=ok,
                raw_output=raw,
                fallback_reason=fail_reason,
                apply_softening=False,
            )
        )

    out_path = os.path.join(app_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=2, ensure_ascii=False)
    retrieval_path = os.path.join(app_dir, retrieval_output_filename)
    with open(retrieval_path, "w", encoding="utf-8") as f:
        json.dump(retrieval_outputs, f, indent=2, ensure_ascii=False)

    print(
        f"[LLM-Review-V2] finish app={app_dir} reviewed={len(outputs)} "
        f"invalid={invalid_outputs} out={out_path} retrieval={retrieval_path}"
    )
    return len(outputs), invalid_outputs


def run(
    processed_dir: str,
    prompt_dir: str,
    vllm_url: str,
    model: str,
    chain_ids: Optional[List[int]] = None,
) -> None:
    prompt = _load_prompt(prompt_dir)
    prior_knowledge_entries = load_prior_knowledge_entries(SCENE_PRIOR_KNOWLEDGE_FILE)
    pattern_knowledge_entries = load_pattern_knowledge_entries(SCENE_PATTERN_KNOWLEDGE_FILE)
    case_knowledge_entries = load_case_knowledge_entries(SCENE_CASE_KNOWLEDGE_FILE)
    skill_knowledge_entries = load_skill_knowledge_entries(SCENE_SKILL_KNOWLEDGE_FILE)

    total = 0
    invalid = 0

    chain_filter: Optional[Set[int]] = None
    if chain_ids:
        chain_filter = {int(x) for x in chain_ids}

    if os.path.exists(os.path.join(processed_dir, "result.json")):
        c, i = process_app_dir(
            processed_dir,
            vllm_url=vllm_url,
            model=model,
            prompt_template=prompt,
            prior_knowledge_entries=prior_knowledge_entries,
            pattern_knowledge_entries=pattern_knowledge_entries,
            case_knowledge_entries=case_knowledge_entries,
            skill_knowledge_entries=skill_knowledge_entries,
            chain_ids_filter=chain_filter,
        )
        total += c
        invalid += i
    else:
        for d in tqdm(sorted(os.listdir(processed_dir)), desc="LLM Review"):
            app_dir = os.path.join(processed_dir, d)
            if not os.path.isdir(app_dir):
                continue
            try:
                c, i = process_app_dir(
                    app_dir,
                    vllm_url=vllm_url,
                    model=model,
                    prompt_template=prompt,
                    prior_knowledge_entries=prior_knowledge_entries,
                    pattern_knowledge_entries=pattern_knowledge_entries,
                    case_knowledge_entries=case_knowledge_entries,
                    skill_knowledge_entries=skill_knowledge_entries,
                    chain_ids_filter=chain_filter,
                )
                total += c
                invalid += i
            except Exception as exc:
                print(f"[LLM-Review][WARN] app failed {app_dir}: {exc}")

    print("\n========== LLM Review Summary ==========")
    print(f"reviewed={total} invalid={invalid}")
    print("=======================================")


def run_v2(
    processed_dir: str,
    prompt_dir: str,
    vllm_url: str,
    model: str,
    chain_ids: Optional[List[int]] = None,
    semantic_filename: str = SEMANTIC_V2_FILENAME,
    retrieval_output_filename: str = RETRIEVAL_FILENAME,
) -> None:
    prompt = _load_prompt(prompt_dir)
    prior_knowledge_entries = load_prior_knowledge_entries(SCENE_PRIOR_KNOWLEDGE_FILE)
    pattern_knowledge_entries = load_pattern_knowledge_entries(SCENE_PATTERN_KNOWLEDGE_FILE)
    case_knowledge_entries = load_case_knowledge_entries(SCENE_CASE_KNOWLEDGE_FILE)
    skill_knowledge_entries = load_skill_knowledge_entries(SCENE_SKILL_KNOWLEDGE_FILE)

    total = 0
    invalid = 0

    chain_filter: Optional[Set[int]] = None
    if chain_ids:
        chain_filter = {int(x) for x in chain_ids}

    if os.path.exists(os.path.join(processed_dir, "result.json")):
        c, i = process_app_dir_v2(
            processed_dir,
            vllm_url=vllm_url,
            model=model,
            prompt_template=prompt,
            prior_knowledge_entries=prior_knowledge_entries,
            pattern_knowledge_entries=pattern_knowledge_entries,
            case_knowledge_entries=case_knowledge_entries,
            skill_knowledge_entries=skill_knowledge_entries,
            semantic_filename=semantic_filename,
            retrieval_output_filename=retrieval_output_filename,
            chain_ids_filter=chain_filter,
        )
        total += c
        invalid += i
    else:
        for d in tqdm(sorted(os.listdir(processed_dir)), desc="LLM Review V2"):
            app_dir = os.path.join(processed_dir, d)
            if not os.path.isdir(app_dir):
                continue
            try:
                c, i = process_app_dir_v2(
                    app_dir,
                    vllm_url=vllm_url,
                    model=model,
                    prompt_template=prompt,
                    prior_knowledge_entries=prior_knowledge_entries,
                    pattern_knowledge_entries=pattern_knowledge_entries,
                    case_knowledge_entries=case_knowledge_entries,
                    skill_knowledge_entries=skill_knowledge_entries,
                    semantic_filename=semantic_filename,
                    retrieval_output_filename=retrieval_output_filename,
                    chain_ids_filter=chain_filter,
                )
                total += c
                invalid += i
            except Exception as exc:
                print(f"[LLM-Review-V2][WARN] app failed {app_dir}: {exc}")

    print("\n========== LLM Review V2 Summary ==========")
    print(f"reviewed={total} invalid={invalid}")
    print("==========================================")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Single-pass LLM compliance review")
    parser.add_argument(
        "--processed-dir",
        default=os.getenv("LLMMUI_PROCESSED_DIR", os.getenv("PROCESSED_DIR", DEFAULT_PROCESSED_DIR)),
    )
    parser.add_argument(
        "--prompt-dir",
        default=os.getenv("LLMMUI_PROMPT_DIR", os.getenv("PROMPT_DIR", DEFAULT_PROMPT_DIR)),
    )
    parser.add_argument(
        "--vllm-url",
        default=os.getenv("LLMMUI_VLLM_TEXT_URL", os.getenv("VLLM_TEXT_URL", settings.VLLM_TEXT_URL)),
    )
    parser.add_argument(
        "--model",
        default=os.getenv("LLMMUI_VLLM_TEXT_MODEL", os.getenv("VLLM_TEXT_MODEL", settings.VLLM_TEXT_MODEL)),
    )
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
        args.processed_dir,
        prompt_dir=args.prompt_dir,
        vllm_url=args.vllm_url,
        model=args.model,
        chain_ids=chain_ids or None,
    )
