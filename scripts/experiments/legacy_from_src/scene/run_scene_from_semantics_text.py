# -*- coding: utf-8 -*-
"""
Scene mapping from chain semantics (text reasoning).

Input:
  <processed>/<app>/result_chain_semantics.json

Output:
  <processed>/<app>/result_ui_task_scene.json
  <processed|app>/scene_from_semantics_summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from tqdm import tqdm

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.schema_utils import (  # noqa: E402
    normalize_scene_record,
    validate_ui_task_scene_results,
)
from analy_pipline.scene.task13_experiment_utils import build_summary  # noqa: E402
from configs import settings  # noqa: E402
from configs.domain.scene_config import (  # noqa: E402
    SCENE_LIST,
    format_scene_definitions,
    format_scene_list,
    format_scene_rules,
)
from utils.http_retry import post_json_with_retry  # noqa: E402


INPUT_FILENAME = "result_chain_semantics.json"
OUTPUT_FILENAME = "result_ui_task_scene.json"
SUMMARY_FILENAME = "scene_from_semantics_summary.json"
DEFAULT_PROMPT_FILE = os.path.join(settings.PROMPT_DIR, "scene_from_semantics_text.txt")

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


def load_prompt_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


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


def build_prompt(template: str, input_payload: Dict[str, Any], strict: bool, forbid_other: bool) -> str:
    prompt = template
    prompt = prompt.replace("{SCENE_LIST}", format_scene_list())
    prompt = prompt.replace("{SCENE_DEFINITIONS}", format_scene_definitions())
    prompt = prompt.replace("{SCENE_RULES}", format_scene_rules())
    prompt = prompt.replace("{INPUT_JSON}", json.dumps(input_payload, ensure_ascii=False, indent=2))
    if strict:
        prompt += (
            "\n\n【输出补充约束】\n"
            "1) ui_task_scene 必须来自给定 taxonomy。\n"
            "2) ui_task_scene_top3 必须有 3 个且去重。\n"
            "3) confidence 只能是 high|medium|low。\n"
        )
    if forbid_other:
        prompt += "\n【重试约束】如可判断，禁止输出“其他”，请在非“其他”中选择最接近任务类别，并降低 confidence。\n"
    return prompt


def call_llm(prompt: str, vllm_url: str, model: str) -> str:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    r = post_json_with_retry(
        vllm_url,
        payload,
        timeout=settings.LLM_RESPONSE_TIMEOUT,
        max_retries=3,
        backoff_factor=1.5,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def should_rerun(rec: Dict[str, Any]) -> str:
    if rec.get("ui_task_scene") not in SCENE_LIST:
        return "scene_not_in_taxonomy"
    if len(rec.get("ui_task_scene_top3", [])) < 3:
        return "scene_top3_incomplete"
    if rec.get("ui_task_scene") == "其他" and rec.get("confidence") == "low":
        return "other_low_confidence"
    return ""


def _as_text(v: Any, max_len: int = 240) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def _dedupe_keep_order(items: List[str], max_items: int = 3) -> List[str]:
    out: List[str] = []
    for x in items:
        v = _as_text(x, max_len=80)
        if not v:
            continue
        if v not in out:
            out.append(v)
        if len(out) >= max_items:
            break
    return out


def _fallback_top3(scene: str) -> List[str]:
    out: List[str] = [scene] if scene in SCENE_LIST else ["其他"]
    for s in SCENE_LIST:
        if s not in out:
            out.append(s)
        if len(out) >= 3:
            break
    return out[:3]


def _normalize_sem_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    chain_id = raw.get("chain_id", -1)
    try:
        chain_id = int(chain_id)
    except Exception:
        chain_id = -1

    scene = _as_text(raw.get("ui_task_scene") or raw.get("predicted_scene") or "", max_len=40)
    if scene not in SCENE_LIST:
        scene = "其他"
    refined_scene = _as_text(raw.get("refined_scene"), max_len=64).lower()
    if refined_scene not in REFINED_SCENE_SET:
        refined_scene = UI_TO_REFINED_FALLBACK.get(scene, "content_browsing")

    user_intent = _as_text(raw.get("user_intent") or raw.get("intent") or raw.get("task_phrase"), max_len=220)
    trigger_action = _as_text(raw.get("trigger_action"), max_len=80)

    ve = raw.get("visual_evidence")
    visual_evidence: List[str] = []
    if isinstance(ve, list):
        visual_evidence.extend([_as_text(x, max_len=40) for x in ve])
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
    if not visual_evidence:
        visual_evidence.extend([_as_text(x, max_len=40) for x in evidence.get("keywords", [])[:8]])
        visual_evidence.extend([_as_text(x, max_len=40) for x in evidence.get("widgets", [])[:8]])
    visual_evidence = _dedupe_keep_order([x for x in visual_evidence if x], max_items=8)

    return {
        "chain_id": chain_id,
        "ui_task_scene": scene,
        "refined_scene": refined_scene,
        "user_intent": user_intent,
        "trigger_action": trigger_action,
        "page_observation": _as_text(raw.get("page_observation"), max_len=280),
        "visual_evidence": visual_evidence,
        "confidence": _as_text(raw.get("confidence", "medium"), max_len=10).lower() or "medium",
        "rerun": bool(raw.get("rerun", False)),
        "rerun_reason": _as_text(raw.get("rerun_reason", ""), max_len=120),
        # Backward-compatible fields if present.
        "task_phrase": _as_text(raw.get("task_phrase"), max_len=120),
        "intent": _as_text(raw.get("intent"), max_len=220),
        "page_function": _as_text(raw.get("page_function"), max_len=220),
        "chain_summary": _as_text(raw.get("chain_summary"), max_len=400),
        "permission_event": raw.get("permission_event") if isinstance(raw.get("permission_event"), dict) else {},
        "task_relevance_cues": raw.get("task_relevance_cues", []),
        "evidence": evidence,
    }


def _load_sem_items(sem_path: str) -> Tuple[List[Dict[str, Any]], int]:
    with open(sem_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        return [], 1

    out: List[Dict[str, Any]] = []
    invalid = 0
    for item in raw:
        if not isinstance(item, dict):
            invalid += 1
            continue
        rec = _normalize_sem_item(item)
        if int(rec.get("chain_id", -1)) < 0:
            invalid += 1
            continue
        out.append(rec)
    return out, invalid


def _fallback_from_semantics(chain_id: int, sem: Dict[str, Any], rerun: bool, rerun_reason: str, error: str = "") -> Dict[str, Any]:
    task_phrase = str(sem.get("task_phrase") or sem.get("trigger_action") or sem.get("ui_task_scene", "")).strip()
    intent = str(sem.get("intent") or sem.get("user_intent", "")).strip()
    if not intent:
        intent = str(sem.get("chain_summary", "")).strip()[:120]

    rec = normalize_scene_record(
        {
            "chain_id": chain_id,
            "task_phrase": task_phrase,
            "intent": intent,
            "page_function": sem.get("page_function", ""),
            "permission_context": ((sem.get("permission_event") or {}).get("ui_observation", "")),
            "chain_summary": sem.get("chain_summary", ""),
            "predicted_scene": "其他",
            "scene_top3": ["其他"],
            "confidence": "low",
            "rerun": rerun,
            "rerun_reason": rerun_reason,
            "other_reason": error or rerun_reason,
        },
        SCENE_LIST,
    )
    rec["ui_task_scene"] = rec["predicted_scene"]
    rec["ui_task_scene_top3"] = rec["scene_top3"]
    rec["refined_scene"] = _as_text(sem.get("refined_scene"), max_len=64).lower()
    if rec["refined_scene"] not in REFINED_SCENE_SET:
        rec["refined_scene"] = UI_TO_REFINED_FALLBACK.get(rec["ui_task_scene"], "content_browsing")
    return rec


def _direct_from_semantics(chain_id: int, sem: Dict[str, Any]) -> Dict[str, Any]:
    scene = str(sem.get("ui_task_scene") or "其他")
    if scene not in SCENE_LIST:
        scene = "其他"
    top3 = _fallback_top3(scene)

    task_phrase = _as_text(sem.get("task_phrase") or sem.get("trigger_action") or scene, max_len=120)
    intent = _as_text(sem.get("intent") or sem.get("user_intent"), max_len=220)
    if not intent:
        intent = f"用户希望进行{scene}相关操作。"

    page_function = _as_text(sem.get("page_function") or sem.get("page_observation"), max_len=220)
    if not page_function:
        page_function = f"页面提供{scene}相关功能入口。"

    permission_context = _as_text(((sem.get("permission_event") or {}).get("ui_observation", "")), max_len=220)
    chain_summary = _as_text(sem.get("chain_summary") or sem.get("page_observation"), max_len=380)
    if not chain_summary:
        chain_summary = f"用户在当前页面进行{scene}相关操作。"

    rec = normalize_scene_record(
        {
            "chain_id": chain_id,
            "task_phrase": task_phrase,
            "intent": intent,
            "page_function": page_function,
            "permission_context": permission_context,
            "chain_summary": chain_summary,
            "predicted_scene": scene,
            "scene_top3": top3,
            "confidence": sem.get("confidence", "medium"),
            "rerun": bool(sem.get("rerun", False)),
            "rerun_reason": sem.get("rerun_reason", ""),
            "other_reason": "scene_from_semantics_direct",
        },
        SCENE_LIST,
    )
    rec["ui_task_scene"] = rec["predicted_scene"]
    rec["ui_task_scene_top3"] = rec["scene_top3"]
    rec["refined_scene"] = _as_text(sem.get("refined_scene"), max_len=64).lower()
    if rec["refined_scene"] not in REFINED_SCENE_SET:
        rec["refined_scene"] = UI_TO_REFINED_FALLBACK.get(scene, "content_browsing")
    return rec


def _normalize_scene_from_obj(chain_id: int, sem: Dict[str, Any], obj: Dict[str, Any], rerun: bool, rerun_reason: str) -> Dict[str, Any]:
    rec = normalize_scene_record(
        {
            "chain_id": chain_id,
            "task_phrase": obj.get("task_phrase") or sem.get("task_phrase", ""),
            "intent": obj.get("intent") or sem.get("intent", ""),
            "page_function": sem.get("page_function", ""),
            "permission_context": ((sem.get("permission_event") or {}).get("ui_observation", "")),
            "chain_summary": sem.get("chain_summary", ""),
            "predicted_scene": obj.get("ui_task_scene") or obj.get("predicted_scene") or obj.get("top1") or "其他",
            "scene_top3": obj.get("ui_task_scene_top3") or obj.get("scene_top3") or obj.get("top3") or [],
            "confidence": obj.get("confidence", "medium"),
            "rerun": rerun,
            "rerun_reason": rerun_reason,
            "other_reason": obj.get("other_reason", ""),
        },
        SCENE_LIST,
    )
    if rec["predicted_scene"] == "其他" and rec["confidence"] != "low":
        rec["confidence"] = "medium"
    rec["ui_task_scene"] = rec["predicted_scene"]
    rec["ui_task_scene_top3"] = rec["scene_top3"]
    rec["refined_scene"] = _as_text(
        obj.get("refined_scene") or sem.get("refined_scene"),
        max_len=64,
    ).lower()
    if rec["refined_scene"] not in REFINED_SCENE_SET:
        rec["refined_scene"] = UI_TO_REFINED_FALLBACK.get(rec["ui_task_scene"], "content_browsing")
    return rec


def infer_scene(
    chain_id: int,
    sem: Dict[str, Any],
    prompt_template: str,
    vllm_url: str,
    model: str,
) -> Dict[str, Any]:
    # New semantics already outputs ui_task_scene. Prefer direct pass-through.
    if str(sem.get("ui_task_scene", "")).strip() in SCENE_LIST:
        return _direct_from_semantics(chain_id, sem)

    sem_summary = sem.get("chain_summary", {})
    if isinstance(sem_summary, dict):
        ocr_triplet = {
            "before_text": str(sem_summary.get("before_text", ""))[:320],
            "granting_text": str(sem_summary.get("granting_text", ""))[:320],
            "after_text": str(sem_summary.get("after_text", ""))[:320],
        }
        summary_text = sem_summary
    else:
        ocr_triplet = {}
        summary_text = str(sem_summary)

    payload = {
        "chain_id": chain_id,
        "task_phrase": sem.get("task_phrase") or sem.get("trigger_action", ""),
        "intent": sem.get("intent") or sem.get("user_intent", ""),
        "page_function": sem.get("page_function", ""),
        "trigger_action": sem.get("trigger_action", ""),
        "page_transition": sem.get("page_transition", ""),
        "permission_event": sem.get("permission_event", {}),
        "visible_actions": sem.get("visible_actions", []),
        "task_relevance_cues": sem.get("task_relevance_cues", []),
        "page_cues": ((sem.get("evidence") or {}).get("page_cues", [])),
        "keywords": (sem.get("evidence") or {}).get("keywords", []) or sem.get("visual_evidence", []),
        "widgets": (sem.get("evidence") or {}).get("widgets", []) or sem.get("visual_evidence", []),
        "permission_popup_text": ((sem.get("permission_event") or {}).get("ui_observation", "")),
        "ocr_triplet": ocr_triplet,
        "chain_summary": summary_text,
    }
    try:
        raw = call_llm(build_prompt(prompt_template, payload, strict=False, forbid_other=False), vllm_url, model)
        obj = extract_json_obj(raw)
        rec = _normalize_scene_from_obj(chain_id, sem, obj, rerun=False, rerun_reason="")
        reason = should_rerun(rec)
        if not reason:
            return rec

        raw2 = call_llm(
            build_prompt(
                prompt_template,
                payload,
                strict=True,
                forbid_other=(reason == "other_low_confidence"),
            ),
            vllm_url,
            model,
        )
        obj2 = extract_json_obj(raw2)
        rec2 = _normalize_scene_from_obj(chain_id, sem, obj2, rerun=True, rerun_reason=reason)
        reason2 = should_rerun(rec2)
        if reason2:
            return _fallback_from_semantics(chain_id, sem, rerun=True, rerun_reason=reason2, error=f"rerun_failed:{reason2}")
        return rec2
    except Exception as exc:
        return _fallback_from_semantics(
            chain_id,
            sem,
            rerun=False,
            rerun_reason=f"exception:{type(exc).__name__}",
            error=str(exc),
        )


def iter_app_dirs(target: str) -> List[str]:
    if os.path.exists(os.path.join(target, INPUT_FILENAME)):
        return [target]
    out = []
    for d in sorted(os.listdir(target)):
        app_dir = os.path.join(target, d)
        if os.path.isdir(app_dir) and os.path.exists(os.path.join(app_dir, INPUT_FILENAME)):
            out.append(app_dir)
    return out


def process_app(
    app_dir: str,
    prompt_template: str,
    vllm_url: str,
    model: str,
    chain_ids: Optional[Set[int]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    sem_path = os.path.join(app_dir, INPUT_FILENAME)
    sem_items, sem_invalid = _load_sem_items(sem_path)
    sem_map = {int(x["chain_id"]): x for x in sem_items}

    out: List[Dict[str, Any]] = []
    invalid = sem_invalid
    for chain_id in tqdm(sorted(sem_map.keys()), desc=f"SceneFromSem {os.path.basename(app_dir)}", ncols=90):
        if chain_ids is not None and chain_id not in chain_ids:
            continue
        rec = infer_scene(chain_id, sem_map[chain_id], prompt_template, vllm_url, model)
        if rec.get("ui_task_scene") == "其他" and rec.get("confidence") == "low":
            invalid += 1
        out.append(rec)

    normalized, dropped = validate_ui_task_scene_results(out, SCENE_LIST)
    invalid += dropped

    # restore refined_scene (schema validator does not include it yet)
    by_id = {int(x.get("chain_id", -1)): x for x in out if isinstance(x, dict)}
    for rec in normalized:
        cid = int(rec.get("chain_id", -1))
        src = by_id.get(cid, {})
        refined_scene = _as_text(src.get("refined_scene"), max_len=64).lower()
        if refined_scene not in REFINED_SCENE_SET:
            refined_scene = UI_TO_REFINED_FALLBACK.get(rec.get("ui_task_scene", "其他"), "content_browsing")
        rec["refined_scene"] = refined_scene

    out_path = os.path.join(app_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"[SceneFromSem] finish app={app_dir} chains={len(normalized)} invalid={invalid} out={out_path}")
    return normalized, invalid


def run(
    target: str,
    prompt_file: str,
    vllm_url: str,
    model: str,
    chain_ids: Optional[List[int]] = None,
) -> None:
    prompt_template = load_prompt_template(prompt_file)
    app_dirs = iter_app_dirs(target)
    all_records: List[Dict[str, Any]] = []
    total_invalid = 0

    chain_filter = None if not chain_ids else {int(x) for x in chain_ids}
    for app_dir in app_dirs:
        try:
            records, invalid = process_app(
                app_dir,
                prompt_template,
                vllm_url,
                model,
                chain_ids=chain_filter,
            )
            all_records.extend(records)
            total_invalid += invalid
        except Exception as exc:
            print(f"[SceneFromSem][WARN] app failed app={app_dir} err={exc}")

    summary = build_summary(all_records)
    summary["invalid_count"] = total_invalid
    summary["apps_processed"] = len(app_dirs)

    summary_dir = (
        target
        if not os.path.exists(os.path.join(target, INPUT_FILENAME))
        else os.path.dirname(os.path.join(target, INPUT_FILENAME))
    )
    summary_path = os.path.join(summary_dir, SUMMARY_FILENAME)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[SceneFromSem] done apps={len(app_dirs)} total_chains={len(all_records)} summary={summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scene mapping from chain semantics")
    parser.add_argument("target", help="processed root or one app dir")
    parser.add_argument("--prompt-file", default=DEFAULT_PROMPT_FILE)
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_TEXT_URL", settings.VLLM_TEXT_URL))
    parser.add_argument("--model", default=os.getenv("VLLM_TEXT_MODEL", settings.VLLM_TEXT_MODEL))
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
    run(args.target, args.prompt_file, args.vllm_url, args.model, chain_ids=chain_ids or None)
