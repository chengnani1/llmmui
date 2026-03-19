#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lint structured scene knowledge quality constraints."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

REQUIRED_FIELDS = [
    "id",
    "scene",
    "refined_scene",
    "permissions",
    "allow_if",
    "deny_if",
    "boundary_if_missing",
    "positive_evidence",
    "negative_evidence",
    "source_type",
]


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def as_text(v: Any) -> str:
    return str(v or "").strip()


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def contains_derived(v: Any) -> bool:
    if isinstance(v, str):
        return "Derived from" in v
    if isinstance(v, list):
        return any(contains_derived(x) for x in v)
    if isinstance(v, dict):
        return any(contains_derived(x) for x in v.values())
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint structured scene knowledge")
    parser.add_argument("path", nargs="?", default="src/configs/scene_structured_knowledge.json")
    parser.add_argument("--max-cue-len", type=int, default=48)
    parser.add_argument("--max-overlap-ratio", type=float, default=0.4)
    args = parser.parse_args()

    obj = load_json(args.path)
    rows = obj.get("knowledge", []) if isinstance(obj, dict) else []

    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(rows, list):
        errors.append("knowledge must be a list")
        rows = []

    for i, item in enumerate(rows):
        if not isinstance(item, dict):
            errors.append(f"#{i}: entry is not object")
            continue

        for field in REQUIRED_FIELDS:
            if field not in item:
                errors.append(f"#{i}({item.get('id','?')}): missing field {field}")

        if contains_derived(item):
            errors.append(f"#{i}({item.get('id','?')}): contains forbidden phrase 'Derived from'")

        allow_if = [as_text(x) for x in as_list(item.get("allow_if")) if as_text(x)]
        deny_if = [as_text(x) for x in as_list(item.get("deny_if")) if as_text(x)]
        if not allow_if:
            errors.append(f"#{i}({item.get('id','?')}): allow_if is empty")
        if not deny_if:
            errors.append(f"#{i}({item.get('id','?')}): deny_if is empty")

        for field in [
            "allow_if",
            "deny_if",
            "boundary_if_missing",
            "positive_evidence",
            "negative_evidence",
        ]:
            vals = [as_text(x) for x in as_list(item.get(field)) if as_text(x)]
            for v in vals:
                if len(v) > args.max_cue_len:
                    errors.append(
                        f"#{i}({item.get('id','?')}): {field} item too long ({len(v)}>{args.max_cue_len}) -> {v}"
                    )

        pos = set([as_text(x) for x in as_list(item.get("positive_evidence")) if as_text(x)])
        neg = set([as_text(x) for x in as_list(item.get("negative_evidence")) if as_text(x)])
        overlap = pos & neg
        if pos or neg:
            ratio = len(overlap) / max(1, min(len(pos), len(neg)) if pos and neg else 1)
            if ratio > args.max_overlap_ratio:
                errors.append(
                    f"#{i}({item.get('id','?')}): positive/negative overlap ratio too high ({ratio:.2f})"
                )
            elif overlap:
                warnings.append(f"#{i}({item.get('id','?')}): overlap={sorted(overlap)}")

    print(f"checked={len(rows)} errors={len(errors)} warnings={len(warnings)}")
    for e in errors:
        print("[ERROR]", e)
    for w in warnings:
        print("[WARN]", w)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
