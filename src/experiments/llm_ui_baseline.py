#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM UI baseline: classify permission risk from textual UI evidence only.

Per app input (preferred):
  - ocr.json
  - widgets.json
  - permission.json

Fallback input (compatible with current pipeline output):
  - result.json
  - result_permission.json

Per app output:
  - result_llm_ui.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
from tqdm import tqdm


DEFAULT_URL = os.getenv("VLLM_TEXT_URL", "http://127.0.0.1:29011/v1/chat/completions")
DEFAULT_MODEL = os.getenv("VLLM_TEXT_MODEL", "Qwen3-30B-A3B-Instruct")
DEFAULT_OUT = "result_llm_ui.json"
DEFAULT_APP_PREFIX = ""

PROMPT_TEMPLATE = """You are a mobile privacy auditor.

UI text:
{OCR_TEXT}

UI widgets:
{WIDGET_TEXT}

Requested permission:
{PERMISSION}

Question:
Is this permission request justified by the UI task?

Answer with one word:
safe or risky
"""


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def uniq_keep_order(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for s in items:
        t = str(s).strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def normalize_permission_name(s: str) -> str:
    s = str(s or "").strip().upper()
    s = re.sub(r"\s+", "_", s)
    return s


def ensure_local_no_proxy() -> None:
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"


def parse_chain_id(item: Dict[str, Any], default_idx: int) -> int:
    raw = item.get("chain_id", default_idx)
    try:
        return int(raw)
    except Exception:
        return default_idx


def find_app_dirs(target: str, app_prefix: str, app: str) -> List[str]:
    if os.path.exists(os.path.join(target, "result.json")):
        return [target]
    if not os.path.isdir(target):
        return []
    if app:
        p = os.path.join(target, app)
        return [p] if os.path.isdir(p) else []
    out: List[str] = []
    for d in sorted(os.listdir(target)):
        p = os.path.join(target, d)
        if not os.path.isdir(p):
            continue
        if app_prefix and not d.startswith(app_prefix):
            continue
        out.append(p)
    return out


def _texts_from_value(v: Any) -> List[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        out: List[str] = []
        for x in v:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                for k in ("text", "label", "title", "name"):
                    if isinstance(x.get(k), str):
                        out.append(x[k])
        return out
    if isinstance(v, dict):
        out: List[str] = []
        for k in ("text", "label", "title", "name"):
            if isinstance(v.get(k), str):
                out.append(v[k])
        return out
    return []


def _parse_chain_list(obj: Any) -> List[Tuple[int, Dict[str, Any]]]:
    pairs: List[Tuple[int, Dict[str, Any]]] = []
    if isinstance(obj, list):
        for i, raw in enumerate(obj):
            item = as_dict(raw)
            if not item:
                continue
            pairs.append((parse_chain_id(item, i), item))
        return pairs
    if isinstance(obj, dict):
        chains = obj.get("chains")
        if isinstance(chains, list):
            for i, raw in enumerate(chains):
                item = as_dict(raw)
                if not item:
                    continue
                pairs.append((parse_chain_id(item, i), item))
            return pairs
        is_digit_key = True
        for k in obj.keys():
            try:
                int(k)
            except Exception:
                is_digit_key = False
                break
        if is_digit_key:
            for k, raw in obj.items():
                item = as_dict(raw)
                if not item:
                    continue
                pairs.append((int(k), item))
            return pairs
    return pairs


def _collect_from_result_json(app_dir: str) -> Tuple[Dict[int, str], Dict[int, str]]:
    ocr_map: Dict[int, str] = {}
    widget_map: Dict[int, str] = {}

    path = os.path.join(app_dir, "result.json")
    data = load_json(path)
    if not isinstance(data, list):
        return ocr_map, widget_map

    for i, raw in enumerate(data):
        item = as_dict(raw)
        if not item:
            continue
        cid = parse_chain_id(item, i)
        ocr_texts: List[str] = []
        widget_texts: List[str] = []

        stages: List[Dict[str, Any]] = []
        stages.append(as_dict(item.get("ui_before_grant")))
        for g in as_list(item.get("ui_granting")):
            stages.append(as_dict(g))
        stages.append(as_dict(item.get("ui_after_grant")))

        for st in stages:
            feat = as_dict(st.get("feature"))
            if isinstance(feat.get("text"), str):
                ocr_texts.append(feat["text"])
            for w in as_list(feat.get("widgets")):
                wd = as_dict(w)
                if isinstance(wd.get("text"), str):
                    widget_texts.append(wd["text"])

        ocr_map[cid] = " | ".join(uniq_keep_order(ocr_texts))
        widget_map[cid] = " | ".join(uniq_keep_order(widget_texts))

    return ocr_map, widget_map


def load_ocr_map(app_dir: str) -> Dict[int, str]:
    path = os.path.join(app_dir, "ocr.json")
    if not os.path.exists(path):
        return _collect_from_result_json(app_dir)[0]

    out: Dict[int, str] = {}
    for cid, item in _parse_chain_list(load_json(path)):
        texts: List[str] = []
        for k in ("ocr_text", "text", "ocr", "before_text", "granting_text", "after_text", "content"):
            texts.extend(_texts_from_value(item.get(k)))
        if not texts:
            # generic fallback
            for k, v in item.items():
                lk = str(k).lower()
                if "text" in lk or "ocr" in lk or "content" in lk:
                    texts.extend(_texts_from_value(v))
        out[cid] = " | ".join(uniq_keep_order(texts))
    return out


def load_widget_map(app_dir: str) -> Dict[int, str]:
    path = os.path.join(app_dir, "widgets.json")
    if not os.path.exists(path):
        return _collect_from_result_json(app_dir)[1]

    out: Dict[int, str] = {}
    for cid, item in _parse_chain_list(load_json(path)):
        texts: List[str] = []
        for k in ("widget_text", "widget_texts", "widgets", "texts"):
            texts.extend(_texts_from_value(item.get(k)))
        if not texts:
            for k, v in item.items():
                lk = str(k).lower()
                if "widget" in lk or lk in {"text", "label", "title", "name"}:
                    texts.extend(_texts_from_value(v))
        out[cid] = " | ".join(uniq_keep_order(texts))
    return out


def load_permission_map(app_dir: str) -> Dict[int, str]:
    out: Dict[int, str] = {}

    for filename in ("permission.json", "result_permission.json"):
        path = os.path.join(app_dir, filename)
        if not os.path.exists(path):
            continue
        for i, raw in enumerate(as_list(load_json(path))):
            item = as_dict(raw)
            if not item:
                continue
            cid = parse_chain_id(item, i)
            perms: List[str] = []

            for key in ("permission", "requested_permission"):
                if isinstance(item.get(key), str):
                    perms.append(normalize_permission_name(item[key]))

            for key in ("permissions", "requested_permissions", "predicted_permissions"):
                val = item.get(key)
                if isinstance(val, list):
                    for x in val:
                        if isinstance(x, str):
                            perms.append(normalize_permission_name(x))
                elif isinstance(val, str):
                    perms.append(normalize_permission_name(val))

            evt = as_dict(item.get("permission_event"))
            ev_perms = evt.get("permissions")
            if isinstance(ev_perms, list):
                for x in ev_perms:
                    if isinstance(x, str):
                        perms.append(normalize_permission_name(x))

            perms = uniq_keep_order(perms)
            if perms:
                out[cid] = ",".join(perms)

    return out


def clip_text(s: str, max_chars: int) -> str:
    s = str(s or "").strip()
    return s[:max_chars] if len(s) > max_chars else s


def call_llm(session: requests.Session, url: str, model: str, prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8,
    }
    r = session.post(url, json=payload, timeout=timeout, proxies={"http": None, "https": None})
    r.raise_for_status()
    data = r.json()
    return str(data["choices"][0]["message"]["content"]).strip()


def parse_pred(raw: str) -> str:
    low = raw.lower()
    m = re.search(r"\b(safe|risky)\b", low)
    if m:
        return m.group(1)
    if any(k in low for k in ("安全", "合规", "合理", "正常")):
        return "safe"
    if any(k in low for k in ("风险", "违规", "可疑", "不合规", "不合理")):
        return "risky"
    # Conservative fallback
    return "risky"


def run_one_app(
    app_dir: str,
    session: requests.Session,
    url: str,
    model: str,
    out_name: str,
    timeout: int,
    force: bool,
) -> int:
    out_path = os.path.join(app_dir, out_name)
    if (not force) and os.path.exists(out_path):
        data = load_json(out_path)
        n = len(data) if isinstance(data, list) else 0
        print(f"[SKIP] app={os.path.basename(app_dir)} output exists ({n}): {out_name}")
        return n

    ocr_map = load_ocr_map(app_dir)
    widget_map = load_widget_map(app_dir)
    perm_map = load_permission_map(app_dir)

    chain_ids = sorted(set(ocr_map.keys()) | set(widget_map.keys()) | set(perm_map.keys()))
    if not chain_ids:
        print(f"[WARN] app={os.path.basename(app_dir)} no chain data found")
        dump_json(out_path, [])
        return 0

    rows: List[Dict[str, Any]] = []
    err_count = 0
    bar = tqdm(chain_ids, desc=f"LLM-UI {os.path.basename(app_dir)}", leave=False)
    for cid in bar:
        ocr_text = clip_text(ocr_map.get(cid, ""), 3500)
        widget_text = clip_text(widget_map.get(cid, ""), 2500)
        permission = perm_map.get(cid, "UNKNOWN")

        prompt = PROMPT_TEMPLATE.format(
            OCR_TEXT=ocr_text if ocr_text else "(empty)",
            WIDGET_TEXT=widget_text if widget_text else "(empty)",
            PERMISSION=permission if permission else "UNKNOWN",
        )

        try:
            raw = call_llm(session=session, url=url, model=model, prompt=prompt, timeout=timeout)
            pred = parse_pred(raw)
        except Exception:
            err_count += 1
            pred = "risky"

        rows.append({"chain_id": int(cid), "pred": pred})

    rows.sort(key=lambda x: int(x["chain_id"]))
    dump_json(out_path, rows)
    print(f"[DONE] app={os.path.basename(app_dir)} chains={len(rows)} req_err={err_count} file={out_path}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM UI baseline (safe/risky) from OCR+widgets+permission")
    parser.add_argument("target", nargs="?", default=os.path.join("data", "processed"))
    parser.add_argument("--url", default=DEFAULT_URL, help="OpenAI-compatible /v1/chat/completions endpoint")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", default=DEFAULT_OUT, help="output filename in each app folder")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--app-prefix", default=DEFAULT_APP_PREFIX)
    parser.add_argument("--app", default="", help="run a single app dir name under processed root")
    parser.add_argument("--force", action="store_true", help="overwrite existing output")
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    app_dirs = find_app_dirs(target=target, app_prefix=args.app_prefix, app=args.app)
    if not app_dirs:
        raise SystemExit(f"no app dirs found: {target}")

    ensure_local_no_proxy()
    session = requests.Session()
    session.trust_env = False
    total = 0
    for app_dir in app_dirs:
        try:
            n = run_one_app(
                app_dir=app_dir,
                session=session,
                url=args.url,
                model=args.model,
                out_name=args.out,
                timeout=args.timeout,
                force=args.force,
            )
            total += n
        except Exception as exc:
            print(f"[WARN] app failed: {app_dir} err={exc}")

    print(f"\n[SUMMARY] apps={len(app_dirs)} chains={total} out={args.out}")


if __name__ == "__main__":
    main()
