#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply mined knowledge candidates into prior/pattern/case knowledge files."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Tuple


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def as_text(v: Any, max_len: int = 200) -> str:
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def dedupe_keep_order(values: List[Any], max_items: int = 16, max_len: int = 80) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in values:
        v = as_text(x, max_len)
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
        if len(out) >= max_items:
            break
    return out


def apply_prior(prior: Dict[str, Any], pattern_candidates: List[Dict[str, Any]], min_support: int) -> int:
    changed = 0
    for cand in pattern_candidates:
        support = int(cand.get("support_count", 0) or 0)
        if support < min_support:
            continue
        scene = as_text(cand.get("scene"), 80)
        perm = as_text(cand.get("permission"), 64).upper()
        if not scene or not perm:
            continue
        pos = dedupe_keep_order(as_list(cand.get("positive_cues")), max_items=12)
        neg = dedupe_keep_order(as_list(cand.get("negative_cues")), max_items=12)
        hint = as_text(cand.get("decision_hint"), 320)

        scene_obj = as_dict(prior.get(scene))
        perm_obj = as_dict(scene_obj.get(perm))
        before = json.dumps(perm_obj, ensure_ascii=False, sort_keys=True)

        perm_obj["positive_cues"] = dedupe_keep_order(as_list(perm_obj.get("positive_cues")) + pos, max_items=16)
        perm_obj["negative_cues"] = dedupe_keep_order(as_list(perm_obj.get("negative_cues")) + neg, max_items=16)
        if hint:
            existing = as_text(perm_obj.get("decision_hint"), 320)
            if hint not in existing:
                perm_obj["decision_hint"] = (existing + " " + hint).strip() if existing else hint

        scene_obj[perm] = perm_obj
        prior[scene] = scene_obj
        after = json.dumps(perm_obj, ensure_ascii=False, sort_keys=True)
        if before != after:
            changed += 1
    return changed


def _find_pattern_idx(patterns: List[Dict[str, Any]], scene: str, permission: str) -> int:
    for i, item in enumerate(patterns):
        if as_text(item.get("scene"), 80) == scene and as_text(item.get("permission"), 64).upper() == permission:
            return i
    return -1


def apply_patterns(pattern_data: Dict[str, Any], pattern_candidates: List[Dict[str, Any]], min_support: int) -> int:
    patterns = as_list(pattern_data.get("patterns"))
    changed = 0
    for cand in pattern_candidates:
        support = int(cand.get("support_count", 0) or 0)
        if support < min_support:
            continue
        scene = as_text(cand.get("scene"), 80)
        perm = as_text(cand.get("permission"), 64).upper()
        if not scene or not perm:
            continue
        idx = _find_pattern_idx(patterns, scene, perm)
        pos = dedupe_keep_order(as_list(cand.get("positive_cues")), max_items=12)
        neg = dedupe_keep_order(as_list(cand.get("negative_cues")), max_items=12)
        hint = as_text(cand.get("decision_hint"), 320)

        if idx >= 0:
            item = as_dict(patterns[idx])
            before = json.dumps(item, ensure_ascii=False, sort_keys=True)
            item["positive_cues"] = dedupe_keep_order(as_list(item.get("positive_cues")) + pos, max_items=16)
            item["negative_cues"] = dedupe_keep_order(as_list(item.get("negative_cues")) + neg, max_items=16)
            if hint:
                old = as_text(item.get("decision_hint"), 320)
                if hint not in old:
                    item["decision_hint"] = (old + " " + hint).strip() if old else hint
            patterns[idx] = item
            after = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if before != after:
                changed += 1
            continue

        patterns.append(
            {
                "scene": scene,
                "permission": perm,
                "positive_cues": pos,
                "negative_cues": neg,
                "decision_hint": hint,
            }
        )
        changed += 1

    pattern_data["patterns"] = patterns
    return changed


def _find_case_idx(cases: List[Dict[str, Any]], scene: str, permission: str, case_type: str) -> int:
    for i, item in enumerate(cases):
        if (
            as_text(item.get("scene"), 80) == scene
            and as_text(item.get("permission"), 64).upper() == permission
            and as_text(item.get("case_type"), 32).lower() == case_type
        ):
            return i
    return -1


def apply_cases(case_data: Dict[str, Any], case_candidates: List[Dict[str, Any]], min_support: int) -> int:
    cases = as_list(case_data.get("cases"))
    changed = 0
    for cand in case_candidates:
        support = int(cand.get("support_count", 0) or 0)
        if support < min_support:
            continue
        scene = as_text(cand.get("scene"), 80)
        perm = as_text(cand.get("permission"), 64).upper()
        case_type = as_text(cand.get("case_type"), 32).lower()
        if not scene or not perm or not case_type:
            continue
        idx = _find_case_idx(cases, scene, perm, case_type)
        evidence = dedupe_keep_order(as_list(cand.get("evidence")), max_items=12)
        reason = as_text(cand.get("reason"), 320)

        if idx >= 0:
            item = as_dict(cases[idx])
            before = json.dumps(item, ensure_ascii=False, sort_keys=True)
            item["evidence"] = dedupe_keep_order(as_list(item.get("evidence")) + evidence, max_items=16)
            if reason:
                old = as_text(item.get("reason"), 320)
                if reason not in old:
                    item["reason"] = (old + " " + reason).strip() if old else reason
            cases[idx] = item
            after = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if before != after:
                changed += 1
            continue

        cases.append(
            {
                "scene": scene,
                "permission": perm,
                "case_type": case_type,
                "evidence": evidence,
                "reason": reason,
            }
        )
        changed += 1

    case_data["cases"] = cases
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply mined knowledge candidates")
    parser.add_argument("--patch-json", required=True)
    parser.add_argument("--prior-json", required=True)
    parser.add_argument("--pattern-json", required=True)
    parser.add_argument("--case-json", required=True)
    parser.add_argument("--min-support", type=int, default=5)
    args = parser.parse_args()

    patch = as_dict(load_json(args.patch_json))
    prior = as_dict(load_json(args.prior_json))
    pattern_data = as_dict(load_json(args.pattern_json))
    case_data = as_dict(load_json(args.case_json))

    pattern_candidates = as_list(patch.get("scene_pattern_candidates"))
    case_candidates = as_list(patch.get("scene_case_candidates"))

    changed_prior = apply_prior(prior, pattern_candidates, min_support=args.min_support)
    changed_pattern = apply_patterns(pattern_data, pattern_candidates, min_support=args.min_support)
    changed_case = apply_cases(case_data, case_candidates, min_support=args.min_support)

    save_json(args.prior_json, prior)
    save_json(args.pattern_json, pattern_data)
    save_json(args.case_json, case_data)

    print(
        f"updated prior={changed_prior} pattern={changed_pattern} case={changed_case} "
        f"(min_support={args.min_support})"
    )


if __name__ == "__main__":
    main()

