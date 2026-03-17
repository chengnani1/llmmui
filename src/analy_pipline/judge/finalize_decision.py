# -*- coding: utf-8 -*-
"""
Phase3 final decision builder (lightweight mapping).

Design:
- Do NOT add heavy heuristic fusion here.
- Use single-pass LLM output as primary signal.
- Use rule prior only for fallback when LLM output is missing/invalid.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.schema_utils import (  # noqa: E402
    FINAL_DECISIONS,
    FINAL_RISKS,
    LLM_FINAL_DECISIONS,
    LLM_FINAL_RISKS,
    RULE_SIGNALS,
    normalize_final_decision_record,
    validate_final_decision_results,
    validate_llm_review_results,
    validate_rule_screening_results,
)
from configs import settings  # noqa: E402
from configs.domain.scene_config import SCENE_LIST  # noqa: E402


TARGET_LOCATION_PERMS = {"ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"}
LOCATION_MISMATCH_UI_SCENES = {"文件与数据管理", "网络连接与设备管理", "设备清理与系统优化"}


@dataclass
class FinalizeConfig:
    vllm_url: str
    vllm_model: str
    prompt_dir: str
    use_arbiter: bool = False
    arbitration_strategy: str = "lightweight_single_pass_v1"


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _iter_app_dirs(target: str) -> List[str]:
    if os.path.exists(os.path.join(target, "result.json")):
        return [target]
    out: List[str] = []
    for d in sorted(os.listdir(target)):
        app_dir = os.path.join(target, d)
        if os.path.isdir(app_dir):
            out.append(app_dir)
    return out


def _rule_prior_to_final(rule_prior: str, rule_signal: str) -> Tuple[str, str, str]:
    rp = str(rule_prior or "").strip().lower()
    if rp == "expected":
        return "CLEARLY_OK", "LOW", "fallback_from_rule_prior_expected"
    if rp == "unexpected":
        return "CLEARLY_RISKY", "HIGH", "fallback_from_rule_prior_unexpected"
    if rp == "suspicious":
        return "NEED_REVIEW", "MEDIUM", "fallback_from_rule_prior_suspicious"

    sig = str(rule_signal or "MEDIUM_RISK").strip().upper()
    if sig == "LOW_RISK":
        return "CLEARLY_OK", "LOW", "fallback_from_rule_signal_low"
    if sig == "HIGH_RISK":
        return "CLEARLY_RISKY", "HIGH", "fallback_from_rule_signal_high"
    return "NEED_REVIEW", "MEDIUM", "fallback_from_rule_signal_medium"


def _single_pass_to_final(llm_item: Dict[str, Any]) -> Tuple[str, str, str]:
    # Prefer new lowercase single-pass fields.
    fd = str(llm_item.get("final_decision", "")).strip().lower()
    fr = str(llm_item.get("final_risk", "")).strip().lower()

    if fd == "compliant":
        if fr == "high":
            return "NEED_REVIEW", "MEDIUM", "llm_compliant_but_high_risk_to_review"
        if fr == "medium":
            return "NEED_REVIEW", "MEDIUM", "llm_compliant_medium_risk_to_review"
        return "CLEARLY_OK", "LOW", "llm_compliant_low"
    if fd == "suspicious":
        return "NEED_REVIEW", "MEDIUM", "llm_suspicious"
    if fd == "non_compliant":
        if fr == "medium":
            return "CLEARLY_RISKY", "MEDIUM", "llm_non_compliant_medium"
        return "CLEARLY_RISKY", "HIGH", "llm_non_compliant_high"

    # Compatibility with old fields.
    old_dec = str(llm_item.get("llm_final_decision", "SUSPICIOUS")).strip().upper()
    old_risk = str(llm_item.get("llm_final_risk", "MEDIUM")).strip().upper()
    if old_dec == "COMPLIANT":
        if old_risk == "HIGH":
            return "NEED_REVIEW", "MEDIUM", "llm_compat_compliant_high_to_review"
        if old_risk == "MEDIUM":
            return "NEED_REVIEW", "MEDIUM", "llm_compat_compliant_medium_to_review"
        return "CLEARLY_OK", "LOW", "llm_compat_compliant_low"
    if old_dec == "NON_COMPLIANT":
        return "CLEARLY_RISKY", "HIGH" if old_risk == "HIGH" else "MEDIUM", "llm_compat_non_compliant"
    return "NEED_REVIEW", "MEDIUM", "llm_compat_suspicious"


def _as_perm_set(v: Any) -> Set[str]:
    if not isinstance(v, list):
        return set()
    out: Set[str] = set()
    for x in v:
        s = str(x or "").strip().upper()
        if s:
            out.add(s)
    return out


def _apply_scene_permission_guard(
    rule_item: Dict[str, Any],
    llm_item: Dict[str, Any],
    final_decision: str,
) -> Optional[Tuple[str, str]]:
    # Minimal safety guard only; main decision pattern should be learned in phase3_llm.
    if final_decision != "CLEARLY_OK":
        return None
    llm_dec = str(llm_item.get("llm_final_decision", "")).strip().upper()
    llm_risk = str(llm_item.get("llm_final_risk", "")).strip().upper()
    if llm_dec != "COMPLIANT" or llm_risk != "LOW":
        return None

    rule_prior = str(rule_item.get("rule_prior", "")).strip().lower()
    ui_scene = str(rule_item.get("ui_task_scene", "")).strip()
    perms = _as_perm_set(rule_item.get("permissions", []))

    if rule_prior == "unexpected":
        return "NEED_REVIEW", "minimal_guard_unexpected_prior"

    if (
        rule_prior in {"suspicious", "unexpected"}
        and (perms & TARGET_LOCATION_PERMS)
        and ui_scene in LOCATION_MISMATCH_UI_SCENES
    ):
        return "NEED_REVIEW", "minimal_guard_location_scene_mismatch"

    return None


def _apply_risk_relax_guard(
    rule_item: Dict[str, Any],
    llm_item: Dict[str, Any],
    final_decision: str,
) -> Optional[Tuple[str, str]]:
    # No handcrafted relax rules in final stage; keep this layer lightweight.
    return None


def _build_final_decision_for_app(
    app_dir: str,
    cfg: FinalizeConfig,
    chain_ids_filter: Optional[Set[int]] = None,
) -> Tuple[int, int]:
    rule_path = os.path.join(app_dir, "result_rule_screening.json")
    llm_path = os.path.join(app_dir, "result_llm_review.json")
    if not os.path.exists(rule_path):
        print(f"[FinalDecision][WARN] skip app={app_dir} missing {rule_path}")
        return 0, 0

    rules, invalid_rule = validate_rule_screening_results(_load_json(rule_path), SCENE_LIST)
    llm_map: Dict[int, Dict[str, Any]] = {}
    invalid_llm = 0
    if os.path.exists(llm_path):
        llm_items, invalid_llm = validate_llm_review_results(_load_json(llm_path))
        llm_map = {int(x["chain_id"]): x for x in llm_items}

    out: List[Dict[str, Any]] = []
    invalid = invalid_rule + invalid_llm

    for item in rules:
        chain_id = int(item["chain_id"])
        if chain_ids_filter is not None and chain_id not in chain_ids_filter:
            continue

        llm_item = llm_map.get(chain_id, {})
        output_valid = bool(llm_item.get("output_valid", False))

        rollback = False
        rollback_reason = ""

        if llm_item and output_valid:
            final_decision, final_risk, final_reason = _single_pass_to_final(llm_item)
            relax_guard = _apply_risk_relax_guard(item, llm_item, final_decision)
            if relax_guard is not None:
                final_decision = relax_guard[0]
                final_risk = "LOW"
                final_reason = f"{final_reason}|{relax_guard[1]}"
            guard = _apply_scene_permission_guard(item, llm_item, final_decision)
            if guard is not None:
                final_decision = guard[0]
                final_risk = "MEDIUM"
                final_reason = f"{final_reason}|{guard[1]}"
        else:
            rollback = True
            rollback_reason = "missing_or_invalid_llm_output"
            final_decision, final_risk, final_reason = _rule_prior_to_final(
                rule_prior=item.get("rule_prior", ""),
                rule_signal=item.get("overall_rule_signal", "MEDIUM_RISK"),
            )

        llm_final_decision = str(llm_item.get("llm_final_decision", "SUSPICIOUS"))
        llm_final_risk = str(llm_item.get("llm_final_risk", "MEDIUM"))
        if llm_final_decision not in LLM_FINAL_DECISIONS:
            llm_final_decision = "SUSPICIOUS"
        if llm_final_risk not in LLM_FINAL_RISKS:
            llm_final_risk = "MEDIUM"

        llm_summary = str(llm_item.get("analysis_summary") or llm_item.get("llm_explanation") or "")

        rec = normalize_final_decision_record(
            {
                "chain_id": chain_id,
                "scene": item.get("scene", "UNKNOWN"),
                "ui_task_scene": item.get("ui_task_scene", item.get("scene", "UNKNOWN")),
                "ui_task_scene_top3": item.get("ui_task_scene_top3", []),
                "regulatory_scene_top1": item.get("regulatory_scene_top1", ""),
                "regulatory_scene_top3": item.get("regulatory_scene_top3", []),
                "task_phrase": item.get("task_phrase", ""),
                "intent": item.get("intent", ""),
                "page_function": item.get("page_function", ""),
                "trigger_action": item.get("trigger_action", ""),
                "visible_actions": item.get("visible_actions", []),
                "task_relevance_cues": item.get("task_relevance_cues", []),
                "permission_context": item.get("permission_context", ""),
                "chain_summary": item.get("chain_summary", ""),
                "permissions": item.get("permissions", []),
                "allowed_permissions": item.get("allowed_permissions", []),
                "banned_permissions": item.get("banned_permissions", []),
                "rule_signal": item.get("overall_rule_signal", "MEDIUM_RISK"),
                "llm_final_decision": llm_final_decision,
                "llm_final_risk": llm_final_risk,
                "final_decision": final_decision if final_decision in FINAL_DECISIONS else "NEED_REVIEW",
                "final_risk": final_risk if final_risk in FINAL_RISKS else "MEDIUM",
                "arbiter_triggered": False,
                "arbiter_reason": "",
                "rollback": rollback,
                "rollback_reason": rollback_reason,
                "explain": {
                    "rule_signal": item.get("overall_rule_signal", "MEDIUM_RISK")
                    if item.get("overall_rule_signal", "MEDIUM_RISK") in RULE_SIGNALS
                    else "MEDIUM_RISK",
                    "rule_summary": "; ".join(item.get("rule_notes", [])[:4]) or str(item.get("mapping_reason", "")),
                    "llm_summary": llm_summary,
                    "final_summary": f"[{cfg.arbitration_strategy}] {final_reason}",
                },
            }
        )

        # Keep new fields for analysis and compatibility.
        rec["refined_scene"] = str(item.get("refined_scene", ""))
        rec["rule_prior"] = str(item.get("rule_prior", "suspicious"))
        rec["rule_notes"] = item.get("rule_notes", [])[:8] if isinstance(item.get("rule_notes", []), list) else []
        rec["single_pass"] = {
            "necessity": llm_item.get("necessity", {}),
            "consistency": llm_item.get("consistency", {}),
            "over_scope": llm_item.get("over_scope", {}),
            "final_risk": llm_item.get("final_risk", ""),
            "final_decision": llm_item.get("final_decision", ""),
            "analysis_summary": llm_item.get("analysis_summary", ""),
        }
        rec["arbitration_strategy"] = cfg.arbitration_strategy
        rec["arbitration_reason"] = final_reason
        out.append(rec)

    normalized, dropped = validate_final_decision_results(out)
    invalid += dropped

    # restore extra fields after schema normalization
    by_id = {int(x.get("chain_id", -1)): x for x in out if isinstance(x, dict)}
    for rec in normalized:
        cid = int(rec.get("chain_id", -1))
        src = by_id.get(cid, {})
        for k in [
            "refined_scene",
            "rule_prior",
            "rule_notes",
            "single_pass",
            "arbitration_strategy",
            "arbitration_reason",
        ]:
            if k in src:
                rec[k] = src[k]

    out_path = os.path.join(app_dir, "result_final_decision.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"[FinalDecision] finish app={app_dir} chains={len(normalized)} invalid={invalid} out={out_path}")
    return len(normalized), invalid


def _build_final_decision_for_app_v2(
    app_dir: str,
    cfg: FinalizeConfig,
    chain_ids_filter: Optional[Set[int]] = None,
) -> Tuple[int, int]:
    llm_path = os.path.join(app_dir, "result_llm_review.json")
    if not os.path.exists(llm_path):
        print(f"[FinalDecision-V2][WARN] skip app={app_dir} missing {llm_path}")
        return 0, 0

    llm_items, invalid_llm = validate_llm_review_results(_load_json(llm_path))
    out: List[Dict[str, Any]] = []
    invalid = invalid_llm

    for llm_item in llm_items:
        chain_id = int(llm_item["chain_id"])
        if chain_ids_filter is not None and chain_id not in chain_ids_filter:
            continue

        output_valid = bool(llm_item.get("output_valid", False))
        rollback = False
        rollback_reason = ""

        if output_valid:
            final_decision, final_risk, final_reason = _single_pass_to_final(llm_item)
        else:
            rollback = True
            rollback_reason = "missing_or_invalid_llm_output"
            final_decision, final_risk, final_reason = ("NEED_REVIEW", "MEDIUM", "fallback_from_invalid_llm_output_v2")

        llm_final_decision = str(llm_item.get("llm_final_decision", "SUSPICIOUS"))
        llm_final_risk = str(llm_item.get("llm_final_risk", "MEDIUM"))
        if llm_final_decision not in LLM_FINAL_DECISIONS:
            llm_final_decision = "SUSPICIOUS"
        if llm_final_risk not in LLM_FINAL_RISKS:
            llm_final_risk = "MEDIUM"

        llm_summary = str(llm_item.get("analysis_summary") or llm_item.get("llm_explanation") or "")

        rec = normalize_final_decision_record(
            {
                "chain_id": chain_id,
                "scene": llm_item.get("scene", "UNKNOWN"),
                "ui_task_scene": llm_item.get("ui_task_scene", llm_item.get("scene", "UNKNOWN")),
                "ui_task_scene_top3": llm_item.get("ui_task_scene_top3", []),
                "regulatory_scene_top1": llm_item.get("regulatory_scene_top1", ""),
                "regulatory_scene_top3": llm_item.get("regulatory_scene_top3", []),
                "task_phrase": llm_item.get("task_phrase", ""),
                "intent": llm_item.get("intent", ""),
                "page_function": llm_item.get("page_function", ""),
                "trigger_action": llm_item.get("trigger_action", ""),
                "visible_actions": llm_item.get("visible_actions", []),
                "task_relevance_cues": llm_item.get("task_relevance_cues", []),
                "permission_context": llm_item.get("permission_context", ""),
                "chain_summary": llm_item.get("chain_summary", ""),
                "permissions": llm_item.get("permissions", []),
                "allowed_permissions": llm_item.get("allowed_permissions", []),
                "banned_permissions": llm_item.get("banned_permissions", []),
                "rule_signal": "MEDIUM_RISK",
                "llm_final_decision": llm_final_decision,
                "llm_final_risk": llm_final_risk,
                "final_decision": final_decision if final_decision in FINAL_DECISIONS else "NEED_REVIEW",
                "final_risk": final_risk if final_risk in FINAL_RISKS else "MEDIUM",
                "arbiter_triggered": False,
                "arbiter_reason": "",
                "rollback": rollback,
                "rollback_reason": rollback_reason,
                "explain": {
                    "rule_signal": "MEDIUM_RISK",
                    "rule_summary": "v2_light_mapping_no_rule_screening",
                    "llm_summary": llm_summary,
                    "final_summary": f"[{cfg.arbitration_strategy}] {final_reason}",
                },
            }
        )
        rec["confidence"] = llm_item.get("confidence", 0.35)
        rec["confidence_label"] = llm_item.get("confidence_label", "")
        rec["refined_scene"] = str(llm_item.get("refined_scene", ""))
        rec["rule_prior"] = "suspicious"
        rec["rule_notes"] = []
        rec["single_pass"] = {
            "necessity": llm_item.get("necessity", {}),
            "consistency": llm_item.get("consistency", {}),
            "over_scope": llm_item.get("over_scope", {}),
            "final_risk": llm_item.get("final_risk", ""),
            "final_decision": llm_item.get("final_decision", ""),
            "analysis_summary": llm_item.get("analysis_summary", ""),
        }
        rec["arbitration_strategy"] = cfg.arbitration_strategy
        rec["arbitration_reason"] = final_reason
        out.append(rec)

    normalized, dropped = validate_final_decision_results(out)
    invalid += dropped

    by_id = {int(x.get("chain_id", -1)): x for x in out if isinstance(x, dict)}
    for rec in normalized:
        cid = int(rec.get("chain_id", -1))
        src = by_id.get(cid, {})
        for k in [
            "confidence",
            "confidence_label",
            "refined_scene",
            "rule_prior",
            "rule_notes",
            "single_pass",
            "arbitration_strategy",
            "arbitration_reason",
        ]:
            if k in src:
                rec[k] = src[k]

    out_path = os.path.join(app_dir, "result_final_decision.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"[FinalDecision-V2] finish app={app_dir} chains={len(normalized)} invalid={invalid} out={out_path}")
    return len(normalized), invalid


def finalize_results(
    target: str,
    cfg: FinalizeConfig,
    chain_ids: Optional[List[int]] = None,
) -> Tuple[int, int]:
    total = 0
    invalid = 0
    app_dirs = _iter_app_dirs(target)

    chain_filter: Optional[Set[int]] = None
    if chain_ids:
        chain_filter = {int(x) for x in chain_ids}

    for idx, app_dir in enumerate(app_dirs, 1):
        if not os.path.exists(os.path.join(app_dir, "result.json")):
            continue
        print(f"[FinalDecision] start app={idx}/{len(app_dirs)} path={app_dir}")
        try:
            c, i = _build_final_decision_for_app(app_dir, cfg, chain_ids_filter=chain_filter)
            total += c
            invalid += i
        except Exception as exc:
            print(f"[FinalDecision][WARN] failed app={app_dir}: {exc}")

    print(f"[FinalDecision] done total_chains={total} invalid={invalid}")
    return total, invalid


def finalize_results_v2(
    target: str,
    cfg: FinalizeConfig,
    chain_ids: Optional[List[int]] = None,
) -> Tuple[int, int]:
    total = 0
    invalid = 0
    app_dirs = _iter_app_dirs(target)

    chain_filter: Optional[Set[int]] = None
    if chain_ids:
        chain_filter = {int(x) for x in chain_ids}

    for idx, app_dir in enumerate(app_dirs, 1):
        if not os.path.exists(os.path.join(app_dir, "result.json")):
            continue
        print(f"[FinalDecision-V2] start app={idx}/{len(app_dirs)} path={app_dir}")
        try:
            c, i = _build_final_decision_for_app_v2(app_dir, cfg, chain_ids_filter=chain_filter)
            total += c
            invalid += i
        except Exception as exc:
            print(f"[FinalDecision-V2][WARN] failed app={app_dir}: {exc}")

    print(f"[FinalDecision-V2] done total_chains={total} invalid={invalid}")
    return total, invalid


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build result_final_decision.json via lightweight mapping")
    parser.add_argument(
        "target",
        nargs="?",
        default=settings.DATA_PROCESSED_DIR,
        help="processed root or one app dir (default: settings.DATA_PROCESSED_DIR)",
    )
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_TEXT_URL", settings.VLLM_TEXT_URL))
    parser.add_argument("--model", default=os.getenv("VLLM_TEXT_MODEL", settings.VLLM_TEXT_MODEL))
    parser.add_argument("--prompt-dir", default=settings.PROMPT_DIR)
    parser.add_argument(
        "--strategy",
        default=os.getenv("LLMMUI_FINAL_STRATEGY", "lightweight_single_pass_v1"),
        help="final strategy name for traceability",
    )
    parser.add_argument("--disable-arbiter", action="store_true", help="kept for compatibility; no effect")
    parser.add_argument("--chain-ids", default="", help="comma-separated chain ids, e.g. 1,3,9")
    args = parser.parse_args()

    cfg = FinalizeConfig(
        vllm_url=args.vllm_url,
        vllm_model=args.model,
        prompt_dir=args.prompt_dir,
        use_arbiter=False,
        arbitration_strategy=args.strategy,
    )

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

    finalize_results(args.target, cfg, chain_ids=chain_ids or None)
