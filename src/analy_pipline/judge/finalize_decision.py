# -*- coding: utf-8 -*-
"""Phase3 final decision: pure mapping from result_llm_review.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class FinalizeConfig:
    vllm_url: str
    vllm_model: str
    prompt_dir: str


DECISION_MAP = {
    "compliant": "CLEARLY_OK",
    "suspicious": "NEED_REVIEW",
    "non_compliant": "CLEARLY_RISKY",
}

RISK_MAP = {
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
}


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_text(v: Any, max_len: int = 1000) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def _to_confidence(v: Any) -> float:
    try:
        score = float(v)
    except Exception:
        return 0.5
    score = max(0.0, min(1.0, score))
    return round(score, 3)


def _normalize_judge_block(v: Any, default_label: str) -> Dict[str, str]:
    d = _as_dict(v)
    label = _as_text(d.get("label"), 60) or default_label
    reason = _as_text(d.get("reason"), 1200)
    return {"label": label, "reason": reason}


def _dedupe_permissions(v: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in _as_list(v):
        p = _as_text(x, 100)
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _normalize_record(item: Dict[str, Any]) -> Dict[str, Any]:
    llm_decision_raw = _as_text(item.get("final_decision"), 40)
    llm_risk_raw = _as_text(item.get("final_risk"), 20)
    llm_decision = llm_decision_raw.lower() or "suspicious"
    llm_risk = llm_risk_raw.lower() or "medium"

    mapped_decision = DECISION_MAP.get(llm_decision, DECISION_MAP["suspicious"])
    mapped_risk = RISK_MAP.get(llm_risk, RISK_MAP["medium"])
    ui_task_scene = _as_text(item.get("ui_task_scene") or item.get("scene"), 120)
    refined_scene = _as_text(item.get("refined_scene"), 120)

    return {
        "chain_id": int(item.get("chain_id", -1)),
        "ui_task_scene": ui_task_scene,
        "refined_scene": refined_scene,
        "page_function": _as_text(item.get("page_function"), 300),
        "user_goal": _as_text(item.get("user_goal"), 300),
        "llm_final_decision": llm_decision_raw or "suspicious",
        "llm_final_risk": llm_risk_raw or "medium",
        "final_decision": mapped_decision,
        "final_risk": mapped_risk,
        "necessity": _normalize_judge_block(item.get("necessity"), "helpful"),
        "consistency": _normalize_judge_block(item.get("consistency"), "weakly_consistent"),
        "over_scope": _normalize_judge_block(item.get("over_scope"), "potentially_over_scoped"),
        "confidence": _to_confidence(item.get("confidence", 0.5)),
        "analysis_summary": _as_text(item.get("analysis_summary"), 2000),
        "permissions": _dedupe_permissions(item.get("permissions")),
        "final_summary": f"LLM结果为{(llm_decision_raw or 'suspicious')}/{(llm_risk_raw or 'medium')}，映射为{mapped_decision}/{mapped_risk}。",
        "_meta": {
            "source": "llm_single_pass",
            "mapping_strategy": "direct_label_mapping",
        },
    }


def _build_for_app(app_dir: str, chain_ids_filter: Optional[Set[int]] = None) -> Tuple[int, int]:
    llm_path = os.path.join(app_dir, "result_llm_review.json")
    rows = _as_list(_load_json(llm_path))
    if not rows:
        print(f"[FinalDecision][WARN] skip app={app_dir} missing_or_empty={llm_path}")
        return 0, 0

    out: List[Dict[str, Any]] = []
    invalid = 0
    for item in rows:
        if not isinstance(item, dict):
            invalid += 1
            continue
        try:
            cid = int(item.get("chain_id", -1))
        except Exception:
            invalid += 1
            continue
        if cid < 0 or (chain_ids_filter is not None and cid not in chain_ids_filter):
            if cid < 0:
                invalid += 1
            continue
        out.append(_normalize_record(item))

    out.sort(key=lambda x: int(x.get("chain_id", -1)))
    out_path = os.path.join(app_dir, "result_final_decision.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[FinalDecision] finish app={app_dir} chains={len(out)} invalid={invalid} out={out_path}")
    return len(out), invalid


def finalize_results(app_dir: str, cfg: FinalizeConfig, chain_ids: Optional[List[int]] = None) -> Tuple[int, int]:
    del cfg
    chain_filter = {int(x) for x in chain_ids} if chain_ids else None
    return _build_for_app(app_dir, chain_ids_filter=chain_filter)


def finalize_results_v2(app_dir: str, cfg: FinalizeConfig, chain_ids: Optional[List[int]] = None) -> Tuple[int, int]:
    del cfg
    chain_filter = {int(x) for x in chain_ids} if chain_ids else None
    return _build_for_app(app_dir, chain_ids_filter=chain_filter)
