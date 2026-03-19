# -*- coding: utf-8 -*-
"""
Phase3 Step3: weak rule prior generator.

This step no longer outputs hard final judgement. It provides soft prior only:
- rule_prior: expected|suspicious|unexpected
- rule_notes: concise evidence list

For backward compatibility, we still output:
- overall_rule_signal: LOW_RISK|MEDIUM_RISK|HIGH_RISK
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
    normalize_permission_name,
    validate_permission_results,
    validate_regulatory_scene_results,
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

PRIOR_EXPECTED = "expected"
PRIOR_SUSPICIOUS = "suspicious"
PRIOR_UNEXPECTED = "unexpected"

PRIOR_TO_SIGNAL = {
    PRIOR_EXPECTED: "LOW_RISK",
    PRIOR_SUSPICIOUS: "MEDIUM_RISK",
    PRIOR_UNEXPECTED: "HIGH_RISK",
}

STORAGE_PERMISSIONS = {
    "READ_EXTERNAL_STORAGE",
    "WRITE_EXTERNAL_STORAGE",
    "MANAGE_EXTERNAL_STORAGE",
    "READ_MEDIA_IMAGES",
    "READ_MEDIA_VIDEO",
    "READ_MEDIA_AUDIO",
}
LOCATION_PERMISSIONS = {"ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"}

STORAGE_UI_SCENES = {
    "文件与数据管理",
    "设备清理与系统优化",
    "相册选择与媒体上传",
}

STORAGE_EVIDENCE_KEYWORDS = {
    "恢复",
    "导出",
    "保存",
    "相册",
    "图片",
    "视频",
    "文件",
    "文件夹",
    "文档",
    "媒体",
    "上传",
    "扫描文件",
    "清理文件",
    "管理文件",
}

LOCATION_EVIDENCE_KEYWORDS = {
    "导航",
    "附近",
    "周边",
    "路线",
    "定位",
    "同城",
    "网点",
    "wifi扫描",
    "WiFi扫描",
    "nearby devices",
    "附近设备",
}

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


def load_json_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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


def _as_text(v: Any, max_len: int = 280) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _load_semantics_map(app_dir: str) -> Tuple[Dict[int, Dict[str, Any]], int]:
    sem_path = _semantics_file(app_dir)
    if not sem_path:
        return {}, 0
    try:
        raw = load_json_file(sem_path)
    except Exception:
        return {}, 1
    if not isinstance(raw, list):
        return {}, 1

    out: Dict[int, Dict[str, Any]] = {}
    invalid = 0
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            invalid += 1
            continue
        try:
            cid = int(item.get("chain_id", idx))
        except Exception:
            invalid += 1
            continue
        out[cid] = item
    return out, invalid


def resolve_scene_for_rule(scene: str, rules: Dict[str, Any]) -> Tuple[str, str]:
    if scene in rules:
        return scene, ""
    legacy_scene = NEW_TO_LEGACY_SCENE.get(scene, "")
    if legacy_scene and legacy_scene in rules:
        return legacy_scene, f"scene_mapped_for_rule: {scene} -> {legacy_scene}"
    return scene, f"scene_rule_missing: {scene}"


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


def _build_prior(
    permission_decisions: Dict[str, str],
    rule_missing: bool,
    permissions_empty: bool,
) -> str:
    if permissions_empty:
        return PRIOR_SUSPICIOUS
    values = list(permission_decisions.values())
    if any(v == CLEARLY_PROHIBITED for v in values):
        return PRIOR_UNEXPECTED
    if values and all(v == CLEARLY_ALLOWED for v in values):
        return PRIOR_EXPECTED
    if rule_missing:
        return PRIOR_SUSPICIOUS
    return PRIOR_SUSPICIOUS


def _contains_storage_evidence(text: str) -> bool:
    t = str(text or "")
    return any(k in t for k in STORAGE_EVIDENCE_KEYWORDS)


def _is_storage_dominant(permissions: List[str]) -> bool:
    if not permissions:
        return False
    pset = {normalize_permission_name(p) for p in permissions if isinstance(p, str)}
    if not pset:
        return False
    return pset.issubset(STORAGE_PERMISSIONS)


def _contains_location_evidence(text: str) -> bool:
    t = str(text or "")
    return any(k in t for k in LOCATION_EVIDENCE_KEYWORDS)


def _collect_structured_cues(sem: Dict[str, Any], scene_item: Dict[str, Any]) -> Dict[str, List[str]]:
    cues = {
        "storage_read_cues": [_as_text(x, 60) for x in _as_list(sem.get("storage_read_cues")) if _as_text(x, 60)],
        "storage_write_cues": [_as_text(x, 60) for x in _as_list(sem.get("storage_write_cues")) if _as_text(x, 60)],
        "location_task_cues": [_as_text(x, 60) for x in _as_list(sem.get("location_task_cues")) if _as_text(x, 60)],
        "upload_task_cues": [_as_text(x, 60) for x in _as_list(sem.get("upload_task_cues")) if _as_text(x, 60)],
        "cleanup_task_cues": [_as_text(x, 60) for x in _as_list(sem.get("cleanup_task_cues")) if _as_text(x, 60)],
    }
    text_blob = " ".join(
        [
            _as_text(sem.get("user_intent"), 260),
            _as_text(sem.get("trigger_action"), 120),
            _as_text(sem.get("page_observation"), 320),
            _as_text(scene_item.get("intent"), 260),
            _as_text(scene_item.get("trigger_action"), 120),
            _as_text(scene_item.get("permission_context"), 320),
            _as_text(scene_item.get("chain_summary"), 360),
            " ".join([_as_text(x, 40) for x in _as_list(sem.get("visual_evidence"))[:8] if _as_text(x, 40)]),
        ]
    )
    if _contains_storage_evidence(text_blob):
        if not cues["storage_read_cues"]:
            cues["storage_read_cues"] = ["storage_read_evidence"]
        if not cues["storage_write_cues"] and any(k in text_blob for k in ["保存", "导出", "写入", "恢复", "下载到本地", "落盘"]):
            cues["storage_write_cues"] = ["storage_write_evidence"]
    if _contains_location_evidence(text_blob) and not cues["location_task_cues"]:
        cues["location_task_cues"] = ["location_task_evidence"]
    return cues


def _adjust_prior_with_structured_cues(
    rule_prior: str,
    permissions: List[str],
    cues: Dict[str, List[str]],
) -> Tuple[str, List[str]]:
    prior = rule_prior
    notes: List[str] = []
    perm_set = {normalize_permission_name(p) for p in permissions if isinstance(p, str)}
    has_storage_pair = {"READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"}.issubset(perm_set)
    has_location = bool(perm_set & LOCATION_PERMISSIONS)
    has_storage_read = bool(cues.get("storage_read_cues"))
    has_storage_write = bool(cues.get("storage_write_cues"))
    has_location_task = bool(cues.get("location_task_cues"))

    # Pattern 1: storage dual-evidence gating (very light prior adjustment).
    if has_storage_pair and prior == PRIOR_EXPECTED and not (has_storage_read and has_storage_write):
        prior = PRIOR_SUSPICIOUS
        notes.append("distilled_prior:storage_pair_missing_dual_evidence")
    if has_storage_pair and prior == PRIOR_UNEXPECTED and has_storage_read and has_storage_write:
        prior = PRIOR_SUSPICIOUS
        notes.append("distilled_prior:storage_pair_dual_evidence_relax")

    # Pattern 2: location task-cue gating.
    if has_location and prior == PRIOR_EXPECTED and not has_location_task:
        prior = PRIOR_SUSPICIOUS
        notes.append("distilled_prior:location_missing_task_cues")
    if has_location and prior == PRIOR_UNEXPECTED and has_location_task:
        prior = PRIOR_SUSPICIOUS
        notes.append("distilled_prior:location_with_strong_task_cues_relax")

    return prior, notes


def _build_rule_notes(
    mapping_note: str,
    matched_rules: List[Dict[str, str]],
    rule_prior: str,
    extra_notes: Optional[List[str]] = None,
) -> List[str]:
    notes: List[str] = []
    if mapping_note:
        notes.append(mapping_note)
    notes.append(f"rule_prior={rule_prior}")
    for n in extra_notes or []:
        if _as_text(n, max_len=180):
            notes.append(_as_text(n, max_len=180))

    for r in matched_rules[:4]:
        if not isinstance(r, dict):
            continue
        perm = _as_text(r.get("permission"), max_len=60)
        decision = _as_text(r.get("decision"), max_len=40)
        evidence = _as_text(r.get("evidence"), max_len=120)
        if perm and decision:
            notes.append(f"{perm}:{decision}")
        if evidence:
            notes.append(evidence)

    # dedupe
    out: List[str] = []
    for n in notes:
        if n and n not in out:
            out.append(n)
    return out[:8]


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
    reg_path = _regulatory_file(apk_dir)

    if not scene_path or not perm_path:
        print(f"[Rule-Screening] skip app={apk_dir} missing scene/permission file")
        return 0, 0

    scene_items, scene_invalid = validate_scene_results(load_json_file(scene_path), SCENE_LIST)
    perm_items, perm_invalid = validate_permission_results(load_json_file(perm_path))

    reg_items: List[Dict[str, Any]] = []
    reg_invalid = 0
    if reg_path:
        reg_items, reg_invalid = validate_regulatory_scene_results(
            load_json_file(reg_path),
            scene_list=SCENE_LIST,
            regulatory_scene_list=regulatory_scene_list,
        )

    sem_map, sem_invalid = _load_semantics_map(apk_dir)
    invalid_outputs = scene_invalid + perm_invalid + reg_invalid + sem_invalid

    scene_map = {int(x["chain_id"]): x for x in scene_items}
    perm_map = {int(x["chain_id"]): x for x in perm_items}
    reg_map = {int(x["chain_id"]): x for x in reg_items}

    chain_ids = sorted(set(scene_map.keys()) | set(perm_map.keys()) | set(reg_map.keys()) | set(sem_map.keys()))

    out: List[Dict[str, Any]] = []
    for chain_id in chain_ids:
        if chain_ids_filter is not None and chain_id not in chain_ids_filter:
            continue

        s = scene_map.get(chain_id, {})
        p = perm_map.get(chain_id, {})
        reg = reg_map.get(chain_id, {})
        sem = sem_map.get(chain_id, {})

        scene = s.get("ui_task_scene") or s.get("predicted_scene") or sem.get("ui_task_scene") or SCENE_UNKNOWN
        refined_scene = _as_text(s.get("refined_scene") or sem.get("refined_scene"), max_len=64).lower()
        scene_top3 = s.get("ui_task_scene_top3") or s.get("scene_top3") or [scene]
        permissions = [normalize_permission_name(x) for x in _as_list(p.get("predicted_permissions")) if isinstance(x, str)]

        regulatory_scene_top1 = _as_text(reg.get("regulatory_scene") or reg.get("regulatory_scene_top1"), max_len=120)
        regulatory_scene_top3 = _as_list(reg.get("regulatory_scene_top3"))
        mapping_reason = _as_text(reg.get("mapping_reason"), max_len=280)

        permission_decisions: Dict[str, str] = {}
        matched_rules: List[Dict[str, str]] = []
        mapping_note = ""

        if regulatory_scene_top1 and regulatory_scene_top1 != "UNKNOWN":
            for perm in permissions:
                d, evidence = judge_permission_regulatory(regulatory_scene_top1, perm, allowed_map, banned_map)
                permission_decisions[perm] = d
                matched_rules.append({"permission": perm, "decision": d, "evidence": evidence})
        else:
            applied_scene, mapping_note = resolve_scene_for_rule(str(scene), rules)
            for perm in permissions:
                d, evidence = judge_permission(applied_scene, perm, rules)
                permission_decisions[perm] = d
                matched_rules.append({"permission": perm, "decision": d, "evidence": evidence})

        rule_prior = _build_prior(
            permission_decisions=permission_decisions,
            rule_missing=bool(mapping_note.startswith("scene_rule_missing")),
            permissions_empty=not permissions,
        )
        structured_cues = _collect_structured_cues(sem=sem, scene_item=s)
        rule_prior, prior_adjust_notes = _adjust_prior_with_structured_cues(
            rule_prior=rule_prior,
            permissions=permissions,
            cues=structured_cues,
        )
        cue_notes: List[str] = []
        for cue_key in [
            "storage_read_cues",
            "storage_write_cues",
            "location_task_cues",
            "upload_task_cues",
            "cleanup_task_cues",
        ]:
            values = [_as_text(x, 40) for x in _as_list(structured_cues.get(cue_key))[:3] if _as_text(x, 40)]
            if values:
                cue_notes.append(f"{cue_key}={','.join(values)}")

        rule_notes = _build_rule_notes(
            mapping_note=mapping_note,
            matched_rules=matched_rules,
            rule_prior=rule_prior,
            extra_notes=prior_adjust_notes + cue_notes,
        )
        if refined_scene:
            tag = f"refined_scene={refined_scene}"
            if tag not in rule_notes:
                rule_notes = [tag] + rule_notes
                rule_notes = rule_notes[:8]
        overall_rule_signal = PRIOR_TO_SIGNAL[rule_prior]

        rec = {
            "chain_id": chain_id,
            "scene": scene,
            "scene_top3": scene_top3,
            "ui_task_scene": scene,
            "refined_scene": refined_scene,
            "ui_task_scene_top3": scene_top3,
            "regulatory_scene": regulatory_scene_top1,
            "regulatory_scene_top1": regulatory_scene_top1,
            "regulatory_scene_top3": regulatory_scene_top3,
            "task_phrase": _as_text(s.get("task_phrase") or sem.get("trigger_action", ""), max_len=120),
            "intent": _as_text(s.get("intent") or sem.get("user_intent", ""), max_len=240),
            "page_function": _as_text(s.get("page_function") or sem.get("page_observation", ""), max_len=280),
            "trigger_action": _as_text(s.get("trigger_action") or sem.get("trigger_action", ""), max_len=120),
            "visible_actions": _as_list(s.get("visible_actions")),
            "task_relevance_cues": (
                _as_list(s.get("task_relevance_cues"))
                + _as_list(sem.get("permission_task_cues"))
                + _as_list(sem.get("visual_evidence"))
            ),
            "permission_context": _as_text(
                s.get("permission_context")
                or ((sem.get("permission_event") or {}).get("ui_observation", ""))
                or sem.get("page_observation", ""),
                max_len=280,
            ),
            "chain_summary": _as_text(s.get("chain_summary") or sem.get("page_observation", ""), max_len=400),
            "permissions": permissions,
            "allowed_permissions": _as_list(reg.get("allowed_permissions")),
            "banned_permissions": _as_list(reg.get("banned_permissions")),
            "mapping_reason": mapping_reason,
            "permission_decisions": permission_decisions,
            "overall_rule_signal": overall_rule_signal,
            "matched_rules": matched_rules,
            # New soft-prior fields
            "rule_prior": rule_prior,
            "rule_notes": rule_notes,
        }
        out.append(rec)

    out_path = os.path.join(apk_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(
        f"[Rule-Screening] finish app={apk_dir} "
        f"chains={len(out)} invalid={invalid_outputs} out={out_path}"
    )
    return len(out), invalid_outputs


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
    prior_counter = defaultdict(int)
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
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
            if not isinstance(items, list):
                return
            for item in items:
                if not isinstance(item, dict):
                    continue
                sig = str(item.get("overall_rule_signal", "MEDIUM_RISK"))
                if sig in RULE_SIGNALS:
                    risk_counter[sig] += 1
                prior = str(item.get("rule_prior", PRIOR_SUSPICIOUS))
                prior_counter[prior] += 1
                for _, d in (item.get("permission_decisions") or {}).items():
                    if d in PERM_DECISIONS:
                        decision_counter[d] += 1
        except Exception:
            return

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

    print("\n========== Rule Prior Summary ==========")
    print(f"chains={total_chains} invalid={total_invalid}")
    for k in RULE_SIGNALS:
        print(f"{k}: {risk_counter[k]}")
    print("rule prior:")
    for k in [PRIOR_EXPECTED, PRIOR_SUSPICIOUS, PRIOR_UNEXPECTED]:
        print(f"  {k}: {prior_counter[k]}")
    print("permission decisions:")
    for k in PERM_DECISIONS:
        print(f"  {k}: {decision_counter[k]}")
    print("========================================")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Weak rule prior generator")
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
