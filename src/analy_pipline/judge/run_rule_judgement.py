# -*- coding: utf-8 -*-
"""
Phase3 Step3: rule-based prior risk screening.
"""

import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.schema_utils import (  # noqa: E402
    PERM_DECISIONS,
    RULE_SIGNALS,
    SCENE_UNKNOWN,
    validate_chain_semantic_results,
    validate_permission_results,
    validate_regulatory_scene_results,
    validate_rule_screening_results,
    validate_scene_results,
)
from configs import settings  # noqa: E402
from configs.domain.scene_config import SCENE_LIST  # noqa: E402


DEFAULT_PROCESSED_DIR = settings.DATA_PROCESSED_DIR
DEFAULT_RULE_FILE = settings.SCENE_RULE_FILE
DEFAULT_KNOWLEDGE_FILE = settings.PERMISSION_KNOWLEDGE_FILE

OUTPUT_FILENAME = "result_rule_screening.json"

CLEARLY_ALLOWED = "CLEARLY_ALLOWED"
CLEARLY_PROHIBITED = "CLEARLY_PROHIBITED"
NEEDS_REVIEW = "NEEDS_REVIEW"

LOW_RISK = "LOW_RISK"
MEDIUM_RISK = "MEDIUM_RISK"
HIGH_RISK = "HIGH_RISK"

NEW_TO_LEGACY_SCENE = {
    "账号与身份认证": "账号与登录",
    "地图与位置服务": "地图与出行",
    "内容浏览与搜索": "信息浏览",
    "社交互动与通信": "即时通信",
    "媒体拍摄与扫码": "拍摄与相册",
    "相册选择与媒体上传": "拍摄与相册",
    "商品浏览与消费": "电商与消费",
    "支付与金融交易": "支付与金融",
    "文件与数据管理": "文件与存储",
    "设备清理与系统优化": "工具与系统",
    "网络连接与设备管理": "设备与硬件",
    "用户反馈与客服": "信息浏览",
    "其他": "其他",
}


def load_scene_rules(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _scene_file(app_dir: str) -> str:
    path = os.path.join(app_dir, "result_ui_task_scene.json")
    return path if os.path.exists(path) else ""


def _permission_file(app_dir: str) -> str:
    path = os.path.join(app_dir, "result_permission.json")
    return path if os.path.exists(path) else ""


def _semantics_file(app_dir: str) -> str:
    path = os.path.join(app_dir, "result_chain_semantics.json")
    return path if os.path.exists(path) else ""


def _regulatory_file(app_dir: str) -> str:
    path = os.path.join(app_dir, "result_regulatory_scene.json")
    return path if os.path.exists(path) else ""


def judge_permission(scene: str, permission: str, rules: Dict[str, Any]) -> Tuple[str, str]:
    rule = rules.get(scene)
    if not rule:
        return NEEDS_REVIEW, f"scene={scene} not found in rule base"

    if permission in rule.get("clearly_allowed", []):
        return CLEARLY_ALLOWED, f"{permission} in clearly_allowed for scene={scene}"
    if permission in rule.get("clearly_prohibited", []):
        return CLEARLY_PROHIBITED, f"{permission} in clearly_prohibited for scene={scene}"
    if permission in rule.get("needs_review", []):
        return NEEDS_REVIEW, f"{permission} in needs_review for scene={scene}"
    return NEEDS_REVIEW, f"{permission} not covered by scene={scene} rule"


def judge_permission_regulatory(
    regulatory_scene: str,
    permission: str,
    allowed_map: Dict[str, List[str]],
    banned_map: Dict[str, List[str]],
) -> Tuple[str, str]:
    allowed = set(allowed_map.get(regulatory_scene, []))
    banned = set(banned_map.get(regulatory_scene, []))
    if permission in allowed:
        return CLEARLY_ALLOWED, f"{permission} in allowed_map for regulatory_scene={regulatory_scene}"
    if permission in banned or "ALL" in banned:
        return CLEARLY_PROHIBITED, f"{permission} in banned_map for regulatory_scene={regulatory_scene}"
    return NEEDS_REVIEW, f"{permission} not explicitly listed in allowed/banned for regulatory_scene={regulatory_scene}"


def resolve_scene_for_rule(scene: str, rules: Dict[str, Any]) -> Tuple[str, str]:
    if scene in rules:
        return scene, ""
    legacy_scene = NEW_TO_LEGACY_SCENE.get(scene, "")
    if legacy_scene and legacy_scene in rules:
        return legacy_scene, f"scene_mapped_for_rule: {scene} -> {legacy_scene}"
    return scene, f"scene_rule_missing: {scene}"


def judge_chain(scene: str, permissions: List[str], rules: Dict[str, Any]) -> Tuple[Dict[str, str], str, List[Dict[str, str]]]:
    decisions: Dict[str, str] = {}
    matched_rules: List[Dict[str, str]] = []
    score = 0

    for p in permissions:
        d, evidence = judge_permission(scene, p, rules)
        decisions[p] = d
        matched_rules.append({"permission": p, "decision": d, "evidence": evidence})
        if d == CLEARLY_PROHIBITED:
            score += 2
        elif d == NEEDS_REVIEW:
            score += 1

    if score >= 2:
        overall = HIGH_RISK
    elif score == 1:
        overall = MEDIUM_RISK
    else:
        overall = LOW_RISK
    return decisions, overall, matched_rules


def judge_chain_regulatory(
    regulatory_scene: str,
    permissions: List[str],
    allowed_map: Dict[str, List[str]],
    banned_map: Dict[str, List[str]],
) -> Tuple[Dict[str, str], str, List[Dict[str, str]]]:
    decisions: Dict[str, str] = {}
    matched_rules: List[Dict[str, str]] = []
    score = 0
    for p in permissions:
        d, evidence = judge_permission_regulatory(regulatory_scene, p, allowed_map, banned_map)
        decisions[p] = d
        matched_rules.append({"permission": p, "decision": d, "evidence": evidence})
        if d == CLEARLY_PROHIBITED:
            score += 2
        elif d == NEEDS_REVIEW:
            score += 1
    if score >= 2:
        overall = HIGH_RISK
    elif score == 1:
        overall = MEDIUM_RISK
    else:
        overall = LOW_RISK
    return decisions, overall, matched_rules


def _force_medium_if_unknown(
    scene: str,
    permissions: List[str],
    overall: str,
    matched_rules: List[Dict[str, str]],
) -> Tuple[str, List[Dict[str, str]]]:
    if scene != SCENE_UNKNOWN and permissions:
        return overall, matched_rules

    reason = "scene=UNKNOWN" if scene == SCENE_UNKNOWN else "permissions=[]"
    matched_rules = list(matched_rules)
    matched_rules.append(
        {
            "permission": "",
            "decision": NEEDS_REVIEW,
            "evidence": f"default_to_medium_risk_due_to_{reason}",
        }
    )
    if overall == LOW_RISK:
        return MEDIUM_RISK, matched_rules
    return overall, matched_rules


def process_app_dir(
    apk_dir: str,
    rules: Dict[str, Any],
    allowed_map: Dict[str, List[str]],
    banned_map: Dict[str, List[str]],
    regulatory_scene_list: List[str],
    chain_ids_filter: Optional[Set[int]] = None,
) -> Tuple[int, int]:
    scene_path = _scene_file(apk_dir)
    perm_path = _permission_file(apk_dir)
    sem_path = _semantics_file(apk_dir)
    reg_path = _regulatory_file(apk_dir)
    if not scene_path or not perm_path:
        print(f"[Rule-Screening] skip app={apk_dir} missing scene/permission file")
        return 0, 0

    with open(scene_path, "r", encoding="utf-8") as f:
        scene_items, scene_invalid = validate_scene_results(json.load(f), SCENE_LIST)
    with open(perm_path, "r", encoding="utf-8") as f:
        perm_items, perm_invalid = validate_permission_results(json.load(f))
    sem_items: List[Dict[str, Any]] = []
    sem_invalid = 0
    if sem_path:
        with open(sem_path, "r", encoding="utf-8") as f:
            sem_items, sem_invalid = validate_chain_semantic_results(json.load(f))

    reg_items: List[Dict[str, Any]] = []
    reg_invalid = 0
    if reg_path:
        with open(reg_path, "r", encoding="utf-8") as f:
            reg_items, reg_invalid = validate_regulatory_scene_results(
                json.load(f),
                scene_list=SCENE_LIST,
                regulatory_scene_list=regulatory_scene_list,
            )

    invalid_outputs = scene_invalid + perm_invalid + sem_invalid + reg_invalid

    scene_map = {int(x["chain_id"]): x for x in scene_items}
    perm_map = {int(x["chain_id"]): x for x in perm_items}
    sem_map = {int(x["chain_id"]): x for x in sem_items}
    reg_map = {int(x["chain_id"]): x for x in reg_items}
    chain_ids = sorted(set(scene_map.keys()) | set(perm_map.keys()) | set(sem_map.keys()) | set(reg_map.keys()))

    out = []
    for chain_id in chain_ids:
        if chain_ids_filter is not None and chain_id not in chain_ids_filter:
            continue
        s = scene_map.get(chain_id, {})
        p = perm_map.get(chain_id, {})
        sem = sem_map.get(chain_id, {})
        reg = reg_map.get(chain_id, {})
        if not s:
            invalid_outputs += 1
        if not p:
            invalid_outputs += 1

        scene = s.get("ui_task_scene") or s.get("predicted_scene", SCENE_UNKNOWN)
        scene_top3 = s.get("ui_task_scene_top3") or s.get("scene_top3", [])
        regulatory_scene_top1 = reg.get("regulatory_scene_top1", "")
        regulatory_scene_top3 = reg.get("regulatory_scene_top3", [])
        mapping_reason = reg.get("mapping_reason", "")
        task_phrase = s.get("task_phrase") or sem.get("task_phrase", "")
        intent = s.get("intent") or sem.get("intent", "")
        page_function = s.get("page_function") or sem.get("page_function", "")
        trigger_action = s.get("trigger_action") or sem.get("trigger_action", "")
        visible_actions = s.get("visible_actions") or sem.get("visible_actions", [])
        task_relevance_cues = s.get("task_relevance_cues") or sem.get("task_relevance_cues", [])
        permission_context = (
            s.get("permission_context")
            or ((sem.get("permission_event") or {}).get("ui_observation", ""))
        )
        chain_summary = s.get("chain_summary") or sem.get("chain_summary", "")
        permissions = p.get("predicted_permissions", [])
        allowed_permissions = reg.get("allowed_permissions", [])
        banned_permissions = reg.get("banned_permissions", [])

        if regulatory_scene_top1 and regulatory_scene_top1 != "UNKNOWN":
            decisions, overall, matched_rules = judge_chain_regulatory(
                regulatory_scene=regulatory_scene_top1,
                permissions=permissions,
                allowed_map=allowed_map,
                banned_map=banned_map,
            )
        else:
            applied_scene, mapping_note = resolve_scene_for_rule(scene, rules)
            decisions, overall, matched_rules = judge_chain(applied_scene, permissions, rules)
            if mapping_note:
                matched_rules.append(
                    {
                        "permission": "",
                        "decision": NEEDS_REVIEW if mapping_note.startswith("scene_rule_missing") else CLEARLY_ALLOWED,
                        "evidence": mapping_note,
                    }
                )
            if mapping_note.startswith("scene_rule_missing") and overall == LOW_RISK:
                overall = MEDIUM_RISK
        if not s:
            matched_rules.append(
                {
                    "permission": "",
                    "decision": NEEDS_REVIEW,
                    "evidence": "scene_result_missing_for_chain",
                }
            )
        if not p:
            matched_rules.append(
                {
                    "permission": "",
                    "decision": NEEDS_REVIEW,
                    "evidence": "permission_result_missing_for_chain",
                }
            )
        if not reg:
            matched_rules.append(
                {
                    "permission": "",
                    "decision": NEEDS_REVIEW,
                    "evidence": "regulatory_scene_missing_for_chain",
                }
            )
        overall, matched_rules = _force_medium_if_unknown(
            regulatory_scene_top1 or scene,
            permissions,
            overall,
            matched_rules,
        )

        out.append(
            {
                "chain_id": chain_id,
                "scene": scene,
                "scene_top3": scene_top3,
                "ui_task_scene": scene,
                "ui_task_scene_top3": scene_top3,
                "regulatory_scene_top1": regulatory_scene_top1,
                "regulatory_scene_top3": regulatory_scene_top3,
                "task_phrase": task_phrase,
                "intent": intent,
                "page_function": page_function,
                "trigger_action": trigger_action,
                "visible_actions": visible_actions,
                "task_relevance_cues": task_relevance_cues,
                "permission_context": permission_context,
                "chain_summary": chain_summary,
                "permissions": permissions,
                "allowed_permissions": allowed_permissions,
                "banned_permissions": banned_permissions,
                "mapping_reason": mapping_reason,
                "permission_decisions": decisions,
                "overall_rule_signal": overall,
                "matched_rules": matched_rules,
            }
        )

    normalized, dropped = validate_rule_screening_results(out, SCENE_LIST)
    invalid_outputs += dropped

    out_path = os.path.join(apk_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(
        f"[Rule-Screening] finish app={apk_dir} "
        f"chains={len(normalized)} invalid={invalid_outputs} out={out_path}"
    )
    return len(normalized), invalid_outputs


def run(
    processed_dir: str,
    rule_file: str,
    knowledge_file: str = DEFAULT_KNOWLEDGE_FILE,
    chain_ids: Optional[List[int]] = None,
) -> None:
    rules = load_scene_rules(rule_file)
    knowledge = load_scene_rules(knowledge_file)
    allowed_map = knowledge.get("allowed_map", {})
    banned_map = knowledge.get("banned_map", {})
    regulatory_scene_list = sorted(set(allowed_map.keys()) & set(banned_map.keys()))
    total_chains = 0
    total_invalid = 0
    risk_counter = defaultdict(int)
    decision_counter = defaultdict(int)
    chain_filter: Optional[Set[int]] = None
    if chain_ids:
        chain_filter = {int(x) for x in chain_ids}

    def _process_one(app_dir: str) -> None:
        nonlocal total_chains, total_invalid
        c, i = process_app_dir(
            app_dir,
            rules=rules,
            allowed_map=allowed_map,
            banned_map=banned_map,
            regulatory_scene_list=regulatory_scene_list,
            chain_ids_filter=chain_filter,
        )
        total_chains += c
        total_invalid += i
        path = os.path.join(app_dir, OUTPUT_FILENAME)
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            items, _ = validate_rule_screening_results(json.load(f), SCENE_LIST)
        for item in items:
            risk_counter[item.get("overall_rule_signal", MEDIUM_RISK)] += 1
            for _, d in (item.get("permission_decisions") or {}).items():
                if d in PERM_DECISIONS:
                    decision_counter[d] += 1

    if os.path.exists(os.path.join(processed_dir, "result.json")):
        _process_one(processed_dir)
    else:
        for d in sorted(os.listdir(processed_dir)):
            app_dir = os.path.join(processed_dir, d)
            if not os.path.isdir(app_dir):
                continue
            try:
                _process_one(app_dir)
            except Exception as exc:
                print(f"[Rule-Screening][WARN] app failed {app_dir}: {exc}")

    print("\n========== Rule Screening Summary ==========")
    print(f"chains={total_chains} invalid={total_invalid}")
    for k in RULE_SIGNALS:
        print(f"{k}: {risk_counter[k]}")
    print("permission decisions:")
    for k in PERM_DECISIONS:
        print(f"  {k}: {decision_counter[k]}")
    print("===========================================")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rule-based prior risk screening")
    parser.add_argument(
        "--processed-dir",
        default=os.getenv("LLMMUI_PROCESSED_DIR", os.getenv("PROCESSED_DIR", DEFAULT_PROCESSED_DIR)),
    )
    parser.add_argument(
        "--rule-file",
        default=os.getenv("LLMMUI_SCENE_RULE_FILE", os.getenv("RULE_FILE", DEFAULT_RULE_FILE)),
    )
    parser.add_argument(
        "--knowledge-file",
        default=os.getenv("LLMMUI_PERMISSION_KNOWLEDGE_FILE", os.getenv("PERMISSION_KNOWLEDGE_FILE", DEFAULT_KNOWLEDGE_FILE)),
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
        rule_file=args.rule_file,
        knowledge_file=args.knowledge_file,
        chain_ids=chain_ids or None,
    )
