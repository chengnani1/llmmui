# -*- coding: utf-8 -*-
"""Phase3_v2 LLM compliance stage: retrieval + single-pass LLM only."""

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
from analy_pipline.judge.knowledge_retriever import (  # noqa: E402
    load_structured_knowledge_entries,
    retrieve_scene_conditioned_knowledge,
)
from configs import settings  # noqa: E402
from utils.http_retry import post_json_with_retry  # noqa: E402


OUTPUT_FILENAME = "result_llm_review.json"
RETRIEVAL_FILENAME = "result_retrieved_knowledge.json"
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
SCENE_STRUCTURED_KNOWLEDGE_FILE = os.getenv(
    "LLMMUI_SCENE_STRUCTURED_KNOWLEDGE_FILE",
    os.path.join(ROOT, "configs", "scene_structured_knowledge.json"),
)

TIMEOUT_SECONDS = int(os.getenv("LLMMUI_CHAIN_TIMEOUT_SECONDS", "120"))

DECISION_SET = {"compliant", "suspicious", "non_compliant"}
RISK_SET = {"low", "medium", "high"}
NECESSITY_SET = {"necessary", "helpful", "unnecessary"}
CONSISTENCY_SET = {"consistent", "weakly_consistent", "inconsistent"}
OVER_SCOPE_SET = {"minimal", "potentially_over_scoped", "over_scoped"}
EVIDENCE_SUFFICIENCY_SET = {"sufficient", "partial", "weak"}


def _as_text(v: Any, max_len: int = 400) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _dedupe_text_list(values: Any, max_items: int = 12, max_len: int = 80) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in _as_list(values):
        v = _as_text(x, max_len)
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
        if len(out) >= max_items:
            break
    return out


def _extract_json_obj(text: str) -> Dict[str, Any]:
    raw = _as_text(text, 20000)
    if not raw:
        return {}
    raw = re.sub(r"^```(?:json)?\n", "", raw, flags=re.I)
    raw = re.sub(r"```$", "", raw).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    s, e = raw.find("{"), raw.rfind("}")
    if s >= 0 and e > s:
        try:
            obj = json.loads(raw[s : e + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _load_prompt_template(prompt_dir: str) -> str:
    path = os.path.join(prompt_dir, PROMPT_FILE)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return (
        "你是安卓权限合规分析助手。请基于输入完成 single-pass 判定，只输出 JSON。\n"
        "输入：{INPUT}\n"
        "输出字段：necessity/consistency/over_scope/final_risk/final_decision/confidence/analysis_summary。"
    )


def _render_prompt(template: str, payload: Dict[str, Any]) -> str:
    input_json = json.dumps(payload, ensure_ascii=False, indent=2)
    if "{INPUT}" in template:
        return template.replace("{INPUT}", input_json)
    return template.rstrip() + "\n\n输入：\n" + input_json


def _call_llm(prompt: str, vllm_url: str, model: str, timeout_seconds: int) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    resp = post_json_with_retry(
        vllm_url,
        payload,
        timeout=timeout_seconds,
        max_retries=0,
        backoff_factor=1.5,
    )
    return resp.json()["choices"][0]["message"]["content"]


def _load_semantics_map(app_dir: str, filename: str) -> Dict[int, Dict[str, Any]]:
    path = os.path.join(app_dir, filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    out: Dict[int, Dict[str, Any]] = {}
    for idx, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            continue
        out[cid] = item
    return out


def _load_permissions_map(app_dir: str) -> Dict[int, List[str]]:
    path = os.path.join(app_dir, PERMISSION_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}

    out: Dict[int, List[str]] = {}
    for idx, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            continue
        perms = []
        seen = set()
        for p in _as_list(item.get("predicted_permissions")):
            v = _as_text(p, 64).upper()
            if not v or v in seen:
                continue
            seen.add(v)
            perms.append(v)
        out[cid] = perms
    return out


def _sem_scene(sem: Dict[str, Any]) -> Dict[str, Any]:
    return sem.get("scene") if isinstance(sem.get("scene"), dict) else {}


def _sem_ui_scene(sem: Dict[str, Any]) -> str:
    return _as_text(_sem_scene(sem).get("ui_task_scene"), 80)


def _sem_refined_scene(sem: Dict[str, Any]) -> str:
    return _as_text(_sem_scene(sem).get("refined_scene"), 64)


def _sem_confidence(sem: Dict[str, Any]) -> float:
    try:
        score = float(_sem_scene(sem).get("confidence", 0.35))
    except Exception:
        score = 0.35
    return round(max(0.0, min(1.0, score)), 3)


def _normalize_label_block(v: Any, allowed: Set[str], default_label: str) -> Dict[str, str]:
    d = _as_dict(v)
    label = _as_text(d.get("label"), 48).lower() or default_label
    if label not in allowed:
        label = default_label
    reason = _as_text(d.get("reason"), 900)
    return {"label": label, "reason": reason}


def _normalize_ref_list(v: Any, max_items: int = 8, max_len: int = 120) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in _as_list(v):
        s = _as_text(x, max_len)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _normalize_one_pass(raw_obj: Dict[str, Any], fallback_reason: str = "") -> Dict[str, Any]:
    necessity = _normalize_label_block(raw_obj.get("necessity"), NECESSITY_SET, "helpful")
    consistency = _normalize_label_block(raw_obj.get("consistency"), CONSISTENCY_SET, "weakly_consistent")
    over_scope = _normalize_label_block(raw_obj.get("over_scope"), OVER_SCOPE_SET, "potentially_over_scoped")

    final_decision = _as_text(raw_obj.get("final_decision"), 40).lower() or "suspicious"
    if final_decision not in DECISION_SET:
        final_decision = "suspicious"

    final_risk = _as_text(raw_obj.get("final_risk"), 20).lower() or "medium"
    if final_risk not in RISK_SET:
        final_risk = "medium"

    try:
        confidence = float(raw_obj.get("confidence", 0.5))
    except Exception:
        confidence = 0.5
    confidence = round(max(0.0, min(1.0, confidence)), 3)

    summary = _as_text(raw_obj.get("analysis_summary"), 1200)
    if not summary and fallback_reason:
        summary = f"single_pass_fallback: {fallback_reason}"

    evidence_sufficiency = _as_text(raw_obj.get("evidence_sufficiency"), 32).lower() or "partial"
    if evidence_sufficiency not in EVIDENCE_SUFFICIENCY_SET:
        evidence_sufficiency = "partial"

    supporting_refs = _normalize_ref_list(raw_obj.get("supporting_refs"), max_items=8, max_len=140)
    conflicting_refs = _normalize_ref_list(raw_obj.get("conflicting_refs"), max_items=8, max_len=140)

    return {
        "necessity": necessity,
        "consistency": consistency,
        "over_scope": over_scope,
        "final_risk": final_risk,
        "final_decision": final_decision,
        "confidence": confidence,
        "analysis_summary": summary,
        "supporting_refs": supporting_refs,
        "conflicting_refs": conflicting_refs,
        "evidence_sufficiency": evidence_sufficiency,
    }


def _fallback_one_pass(reason: str) -> Dict[str, Any]:
    return _normalize_one_pass(
        {
            "necessity": {"label": "helpful", "reason": "single_pass_output_missing"},
            "consistency": {"label": "weakly_consistent", "reason": "single_pass_output_missing"},
            "over_scope": {"label": "potentially_over_scoped", "reason": "single_pass_output_missing"},
            "final_risk": "medium",
            "final_decision": "suspicious",
            "confidence": 0.5,
            "analysis_summary": f"single_pass_fallback: {reason}",
            "supporting_refs": [],
            "conflicting_refs": [],
            "evidence_sufficiency": "weak",
        }
    )


def _run_one_pass(payload: Dict[str, Any], prompt_template: str, vllm_url: str, model: str) -> Tuple[Dict[str, Any], bool, str, str]:
    prompt = _render_prompt(prompt_template, payload)
    try:
        raw = _call_llm(prompt=prompt, vllm_url=vllm_url, model=model, timeout_seconds=TIMEOUT_SECONDS)
    except Exception as exc:
        return _fallback_one_pass(f"api_error:{exc}"), False, "", f"api_error:{exc}"

    obj = _extract_json_obj(raw)
    if not obj:
        return _fallback_one_pass("invalid_json"), False, raw, "invalid_json"

    return _normalize_one_pass(obj), True, raw, ""


def _build_record(chain_id: int, sem: Dict[str, Any], permissions: List[str], one_pass: Dict[str, Any], ok: bool, raw_output: str, fail_reason: str) -> Dict[str, Any]:
    ui_scene = _sem_ui_scene(sem)
    refined_scene = _sem_refined_scene(sem)
    page_description = _as_text(sem.get("page_description"), 800)
    page_function = _as_text(sem.get("page_function"), 240)
    user_goal = _as_text(sem.get("user_goal"), 240)

    out = {
        "chain_id": chain_id,
        "ui_task_scene": ui_scene,
        "refined_scene": refined_scene,
        "permissions": permissions,
        "page_description": page_description,
        "page_function": page_function,
        "user_goal": user_goal,
        "necessity": one_pass.get("necessity", {"label": "helpful", "reason": ""}),
        "consistency": one_pass.get("consistency", {"label": "weakly_consistent", "reason": ""}),
        "over_scope": one_pass.get("over_scope", {"label": "potentially_over_scoped", "reason": ""}),
        "final_risk": _as_text(one_pass.get("final_risk"), 20) or "medium",
        "final_decision": _as_text(one_pass.get("final_decision"), 40) or "suspicious",
        "confidence": one_pass.get("confidence", _sem_confidence(sem)),
        "analysis_summary": _as_text(one_pass.get("analysis_summary"), 1200),
        "supporting_refs": _normalize_ref_list(one_pass.get("supporting_refs"), max_items=8, max_len=140),
        "conflicting_refs": _normalize_ref_list(one_pass.get("conflicting_refs"), max_items=8, max_len=140),
        "evidence_sufficiency": _as_text(one_pass.get("evidence_sufficiency"), 32) or "partial",
        "output_valid": bool(ok),
        "format_error": not bool(ok),
    }
    if fail_reason:
        out["fallback_reason"] = fail_reason
    if raw_output:
        out["raw_output"] = _as_text(raw_output, 12000)
    return out


def _iter_app_dirs(processed_dir: str) -> List[str]:
    if os.path.exists(os.path.join(processed_dir, "result.json")):
        return [processed_dir]
    out: List[str] = []
    for d in sorted(os.listdir(processed_dir)) if os.path.isdir(processed_dir) else []:
        app_dir = os.path.join(processed_dir, d)
        if os.path.isdir(app_dir) and os.path.exists(os.path.join(app_dir, "result.json")):
            out.append(app_dir)
    return out


def process_app_dir_v2(
    app_dir: str,
    vllm_url: str,
    model: str,
    prompt_template: str,
    structured_knowledge_entries: List[Dict[str, Any]],
    semantic_filename: str = SEMANTIC_V2_FILENAME,
    retrieval_output_filename: str = RETRIEVAL_FILENAME,
    chain_ids_filter: Optional[Set[int]] = None,
) -> Tuple[int, int]:
    result_json_path = os.path.join(app_dir, "result.json")
    if not os.path.exists(result_json_path):
        print(f"[LLM-Review-V2] skip app={app_dir} missing result.json")
        return 0, 0

    sem_map = _load_semantics_map(app_dir, filename=semantic_filename)
    if not sem_map:
        print(f"[LLM-Review-V2] skip app={app_dir} missing semantic file={semantic_filename}")
        return 0, 0

    permissions_map = _load_permissions_map(app_dir)
    summary_map = load_chain_summary_map(result_json_path, permissions_map=permissions_map)

    outputs: List[Dict[str, Any]] = []
    retrieval_outputs: List[Dict[str, Any]] = []
    invalid = 0

    for chain_id in sorted(sem_map.keys()):
        if chain_ids_filter is not None and chain_id not in chain_ids_filter:
            continue

        sem = _as_dict(sem_map.get(chain_id))
        permissions = _as_list(permissions_map.get(chain_id))

        summary_obj = _as_dict(_as_dict(summary_map.get(chain_id)).get("chain_summary"))
        widgets = _dedupe_text_list(summary_obj.get("top_widgets"), max_items=14, max_len=80)
        before_text = _as_text(summary_obj.get("before_text"), 320)
        granting_text = _as_text(summary_obj.get("granting_text"), 320)
        after_text = _as_text(summary_obj.get("after_text"), 320)

        ui_scene = _sem_ui_scene(sem)
        refined_scene = _sem_refined_scene(sem)
        page_description = _as_text(sem.get("page_description"), 800)
        page_function = _as_text(sem.get("page_function"), 240)
        user_goal = _as_text(sem.get("user_goal"), 240)

        retrieved_knowledge = retrieve_scene_conditioned_knowledge(
            prior_entries=[],
            pattern_entries=[],
            case_entries=[],
            skill_entries=[],
            structured_entries=structured_knowledge_entries,
            refined_scene=refined_scene,
            ui_task_scene=ui_scene,
            permissions=permissions,
            user_intent=user_goal,
            trigger_action=page_function,
            page_observation=page_description,
            visual_evidence=widgets,
            structured_cues=None,
            top_k_patterns=2,
            top_k_cases=4,
            top_k_risky_cases=2,
            top_k_compliant_cases=2,
            top_k_skills=2,
        )

        retrieval_outputs.append(
            {
                "chain_id": chain_id,
                "ui_task_scene": ui_scene,
                "refined_scene": refined_scene,
                "permissions": permissions,
                "retrieved_knowledge": retrieved_knowledge,
            }
        )

        payload = {
            "chain_id": chain_id,
            "semantic": {
                "page_description": page_description,
                "page_function": page_function,
                "user_goal": user_goal,
                "scene": {
                    "ui_task_scene": ui_scene,
                    "refined_scene": refined_scene,
                    "confidence": _sem_confidence(sem),
                },
            },
            "permissions": permissions,
            "retrieved_knowledge": retrieved_knowledge,
            "ocr_widgets": {
                "before_text": before_text,
                "granting_text": granting_text,
                "after_text": after_text,
                "widgets": widgets,
            },
        }

        one_pass, ok, raw_output, fail_reason = _run_one_pass(
            payload=payload,
            prompt_template=prompt_template,
            vllm_url=vllm_url,
            model=model,
        )
        if not ok:
            invalid += 1

        outputs.append(
            _build_record(
                chain_id=chain_id,
                sem=sem,
                permissions=permissions,
                one_pass=one_pass,
                ok=ok,
                raw_output=raw_output,
                fail_reason=fail_reason,
            )
        )

    out_path = os.path.join(app_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)

    retrieval_path = os.path.join(app_dir, retrieval_output_filename)
    with open(retrieval_path, "w", encoding="utf-8") as f:
        json.dump(retrieval_outputs, f, ensure_ascii=False, indent=2)

    print(
        f"[LLM-Review-V2] finish app={app_dir} reviewed={len(outputs)} "
        f"invalid={invalid} out={out_path} retrieval={retrieval_path}"
    )
    return len(outputs), invalid


def run_v2(
    processed_dir: str,
    prompt_dir: str,
    vllm_url: str,
    model: str,
    chain_ids: Optional[List[int]] = None,
    semantic_filename: str = SEMANTIC_V2_FILENAME,
    retrieval_output_filename: str = RETRIEVAL_FILENAME,
) -> None:
    prompt_template = _load_prompt_template(prompt_dir)
    structured_knowledge_entries = load_structured_knowledge_entries(SCENE_STRUCTURED_KNOWLEDGE_FILE)

    chain_filter = {int(x) for x in chain_ids} if chain_ids else None
    total, invalid = 0, 0

    app_dirs = _iter_app_dirs(processed_dir)
    iterator = app_dirs
    if len(app_dirs) > 1:
        iterator = tqdm(app_dirs, desc="LLM Review V2")

    for app_dir in iterator:
        c, i = process_app_dir_v2(
            app_dir,
            vllm_url=vllm_url,
            model=model,
            prompt_template=prompt_template,
            structured_knowledge_entries=structured_knowledge_entries,
            semantic_filename=semantic_filename,
            retrieval_output_filename=retrieval_output_filename,
            chain_ids_filter=chain_filter,
        )
        total += c
        invalid += i

    print("\n========== LLM Review V2 Summary ==========")
    print(f"processed_apps={len(app_dirs)} reviewed={total} invalid={invalid}")
    print("==========================================")


def run(
    processed_dir: str,
    prompt_dir: str,
    vllm_url: str,
    model: str,
    chain_ids: Optional[List[int]] = None,
) -> None:
    run_v2(
        processed_dir=processed_dir,
        prompt_dir=prompt_dir,
        vllm_url=vllm_url,
        model=model,
        chain_ids=chain_ids,
        semantic_filename=SEMANTIC_V2_FILENAME,
        retrieval_output_filename=RETRIEVAL_FILENAME,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run phase3_v2 single-pass LLM compliance")
    parser.add_argument("processed_dir", help="processed root or one app dir")
    parser.add_argument("--prompt-dir", default=settings.PROMPT_DIR)
    parser.add_argument("--vllm-url", default=settings.VLLM_TEXT_URL)
    parser.add_argument("--model", default=settings.VLLM_TEXT_MODEL)
    parser.add_argument("--chain-ids", default="", help="comma-separated chain ids")
    parser.add_argument("--semantic-filename", default=SEMANTIC_V2_FILENAME)
    parser.add_argument("--retrieval-output-filename", default=RETRIEVAL_FILENAME)
    args = parser.parse_args()

    ids: Optional[List[int]] = None
    if args.chain_ids.strip():
        ids = []
        for seg in args.chain_ids.split(","):
            seg = seg.strip()
            if not seg:
                continue
            try:
                ids.append(int(seg))
            except Exception:
                continue

    run_v2(
        processed_dir=args.processed_dir,
        prompt_dir=args.prompt_dir,
        vllm_url=args.vllm_url,
        model=args.model,
        chain_ids=ids,
        semantic_filename=args.semantic_filename,
        retrieval_output_filename=args.retrieval_output_filename,
    )
