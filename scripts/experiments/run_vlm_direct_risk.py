#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Direct VLM risk judgement from chain images.

For each app dir:
  input : chain_*.png
  output: result_vlm_direct_risk.json

Root summary:
  <target>/vlm_direct_risk_summary.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

import requests


OUTPUT_FILENAME = "result_vlm_direct_risk.json"
SUMMARY_FILENAME = "vlm_direct_risk_summary.json"

DEFAULT_PROMPT = """你是安卓权限合规风险二分类器。
给你一张权限交互链图片（多页拼接），请判断该链是否“有风险”。

判定标准（简化）：
- RISKY(1)：权限请求与当前任务明显不匹配、过度索权、或高度可疑。
- SAFE(0)：权限请求与当前任务基本匹配，未见明显过度索权。

只输出严格 JSON（不要额外文字）：
{
  "pred_risk": 0,
  "pred_label": "SAFE",
  "confidence": "high",
  "reason": "简短理由，不超过40字"
}

约束：
1) pred_risk 只能是 0 或 1
2) pred_label 只能是 SAFE 或 RISKY
3) confidence 只能是 high/medium/low
"""


def _ensure_no_proxy() -> None:
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"


def _new_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    s = text.strip()
    s = re.sub(r"^```(?:json)?\n", "", s, flags=re.I)
    s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(s[i : j + 1])
            except Exception:
                return {}
    return {}


def _parse_chain_id(filename: str) -> Optional[int]:
    m = re.match(r"^chain_(\d+)\.png$", filename)
    if not m:
        return None
    return int(m.group(1))


def _iter_app_dirs(target: str, app_name: str, app_prefix: str) -> List[str]:
    if os.path.isfile(os.path.join(target, "result.json")):
        return [target]
    if not os.path.isdir(target):
        return []
    if app_name:
        app_dir = os.path.join(target, app_name)
        return [app_dir] if os.path.isdir(app_dir) else []
    out: List[str] = []
    for d in sorted(os.listdir(target)):
        app_dir = os.path.join(target, d)
        if not os.path.isdir(app_dir):
            continue
        if app_prefix and not d.startswith(app_prefix):
            continue
        out.append(app_dir)
    return out


def _chain_images(app_dir: str, chain_ids: Optional[Set[int]]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for name in sorted(os.listdir(app_dir)):
        cid = _parse_chain_id(name)
        if cid is None:
            continue
        if chain_ids is not None and cid not in chain_ids:
            continue
        out.append((cid, os.path.join(app_dir, name)))
    return out


def _img_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _post_json(
    session: requests.Session,
    url: str,
    payload: Dict[str, Any],
    timeout: int,
) -> requests.Response:
    return session.post(url, json=payload, timeout=timeout, proxies={"http": None, "https": None})


def _call_vlm(
    session: requests.Session,
    vllm_url: str,
    model: str,
    image_path: str,
    prompt: str,
    timeout: int,
    max_retries: int,
) -> str:
    image_b64 = _img_b64(image_path)

    payload_mm = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            }
        ],
    }

    payload_legacy = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "images": [image_b64],
    }

    last_err = ""
    for payload in (payload_mm, payload_legacy):
        for attempt in range(max_retries + 1):
            try:
                r = _post_json(session, vllm_url, payload, timeout=timeout)
                r.raise_for_status()
                data = r.json()
                return str(data["choices"][0]["message"]["content"])
            except Exception as exc:
                last_err = str(exc)
                if attempt >= max_retries:
                    break
                time.sleep(1.2**attempt)
                continue
    raise RuntimeError(last_err or "vlm_call_failed")


def _normalize_pred(obj: Dict[str, Any]) -> Tuple[Optional[int], str, str, str]:
    pred_risk = obj.get("pred_risk", None)
    pred_label = str(obj.get("pred_label", "")).strip().upper()
    confidence = str(obj.get("confidence", "")).strip().lower()
    reason = str(obj.get("reason", "")).strip()

    if str(pred_risk) in {"0", "1"}:
        pred_risk = int(pred_risk)
    else:
        pred_risk = None
    if pred_risk is None:
        if pred_label == "SAFE":
            pred_risk = 0
        elif pred_label == "RISKY":
            pred_risk = 1

    if pred_label not in {"SAFE", "RISKY"} and pred_risk in {0, 1}:
        pred_label = "RISKY" if pred_risk == 1 else "SAFE"
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    return pred_risk, pred_label, confidence, reason[:200]


def infer_one(
    session: requests.Session,
    vllm_url: str,
    model: str,
    image_path: str,
    timeout: int,
    max_retries: int,
    prompt: str,
) -> Dict[str, Any]:
    ts0 = time.time()
    raw = ""
    try:
        raw = _call_vlm(
            session=session,
            vllm_url=vllm_url,
            model=model,
            image_path=image_path,
            prompt=prompt,
            timeout=timeout,
            max_retries=max_retries,
        )
        obj = _extract_json(raw)
        pred_risk, pred_label, confidence, reason = _normalize_pred(obj)
        if pred_risk in {0, 1} and pred_label in {"SAFE", "RISKY"}:
            return {
                "output_valid": True,
                "fallback_reason": "",
                "pred_risk": pred_risk,
                "pred_label": pred_label,
                "confidence": confidence,
                "reason": reason,
                "latency_seconds": round(time.time() - ts0, 3),
                "raw_output": raw[:1000],
            }
        return {
            "output_valid": False,
            "fallback_reason": "format_error",
            "pred_risk": 1,
            "pred_label": "RISKY",
            "confidence": "low",
            "reason": "输出格式异常，保守判为有风险",
            "latency_seconds": round(time.time() - ts0, 3),
            "raw_output": raw[:1000],
        }
    except Exception as exc:
        msg = str(exc).lower()
        fb = "timeout" if ("timed out" in msg or "timeout" in msg) else "request_error"
        return {
            "output_valid": False,
            "fallback_reason": fb,
            "pred_risk": 1,
            "pred_label": "RISKY",
            "confidence": "low",
            "reason": "请求失败，保守判为有风险",
            "latency_seconds": round(time.time() - ts0, 3),
            "raw_output": str(exc)[:1000],
        }


def process_app(
    app_dir: str,
    session: requests.Session,
    vllm_url: str,
    model: str,
    timeout: int,
    max_retries: int,
    force: bool,
    chain_ids: Optional[Set[int]],
    prompt: str,
) -> Tuple[int, int, int]:
    out_path = os.path.join(app_dir, OUTPUT_FILENAME)
    if (not force) and os.path.exists(out_path):
        print(f"[SKIP] app={os.path.basename(app_dir)} output exists: {OUTPUT_FILENAME}")
        data = _load_json(out_path)
        return len(data) if isinstance(data, list) else 0, 0, 0

    imgs = _chain_images(app_dir, chain_ids=chain_ids)
    if not imgs:
        print(f"[WARN] app={os.path.basename(app_dir)} no chain images")
        _save_json(out_path, [])
        return 0, 0, 0

    records: List[Dict[str, Any]] = []
    invalid = 0
    timeout_count = 0
    for cid, img_path in imgs:
        rec = infer_one(
            session=session,
            vllm_url=vllm_url,
            model=model,
            image_path=img_path,
            timeout=timeout,
            max_retries=max_retries,
            prompt=prompt,
        )
        if not rec.get("output_valid", False):
            invalid += 1
            if rec.get("fallback_reason") == "timeout":
                timeout_count += 1
        rec["chain_id"] = cid
        rec["image"] = os.path.basename(img_path)
        records.append(rec)

    records.sort(key=lambda x: int(x.get("chain_id", -1)))
    _save_json(out_path, records)
    print(
        f"[DONE] app={os.path.basename(app_dir)} chains={len(records)} "
        f"invalid={invalid} timeout={timeout_count} file={out_path}"
    )
    return len(records), invalid, timeout_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct VLM risk judgement from chain images")
    parser.add_argument("target", nargs="?", default=os.path.join("data", "processed"))
    parser.add_argument("--app", default="", help="only run one app dir name under target root")
    parser.add_argument("--app-prefix", default="fastbot-", help="filter app dirs by prefix in root mode")
    parser.add_argument("--chain-ids", default="", help="comma-separated chain ids, e.g. 1,3,9")
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_VL_URL", "http://127.0.0.1:29010/v1/chat/completions"))
    parser.add_argument("--model", default=os.getenv("VLLM_VL_MODEL", "qwen-vl-model"))
    parser.add_argument("--timeout", type=int, default=120, help="per request timeout seconds")
    parser.add_argument("--max-retries", type=int, default=0, help="retry times per payload format")
    parser.add_argument("--force", action="store_true", help="overwrite existing result_vlm_direct_risk.json")
    parser.add_argument("--prompt-file", default="", help="optional custom prompt file")
    args = parser.parse_args()

    _ensure_no_proxy()

    chain_ids: Optional[Set[int]] = None
    if args.chain_ids.strip():
        parsed: Set[int] = set()
        for seg in args.chain_ids.split(","):
            seg = seg.strip()
            if not seg:
                continue
            try:
                parsed.add(int(seg))
            except Exception:
                continue
        chain_ids = parsed or None

    prompt = DEFAULT_PROMPT
    if args.prompt_file and os.path.exists(args.prompt_file):
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            p = f.read().strip()
        if p:
            prompt = p

    target = os.path.abspath(args.target)
    app_dirs = _iter_app_dirs(target=target, app_name=args.app, app_prefix=args.app_prefix)

    session = _new_session()
    apps_total = len(app_dirs)
    apps_run = 0
    apps_failed = 0
    total_chains = 0
    total_invalid = 0
    total_timeout = 0
    pred_counter: Counter = Counter()
    conf_counter: Counter = Counter()
    fb_counter: Counter = Counter()

    for app_dir in app_dirs:
        try:
            n, invalid, timeout_n = process_app(
                app_dir=app_dir,
                session=session,
                vllm_url=args.vllm_url,
                model=args.model,
                timeout=args.timeout,
                max_retries=args.max_retries,
                force=args.force,
                chain_ids=chain_ids,
                prompt=prompt,
            )
            apps_run += 1
            total_chains += n
            total_invalid += invalid
            total_timeout += timeout_n
            recs = _load_json(os.path.join(app_dir, OUTPUT_FILENAME))
            for rec in recs if isinstance(recs, list) else []:
                pred_counter[str(rec.get("pred_label", ""))] += 1
                conf_counter[str(rec.get("confidence", ""))] += 1
                if not rec.get("output_valid", True):
                    fb_counter[str(rec.get("fallback_reason", ""))] += 1
        except Exception as exc:
            apps_failed += 1
            print(f"[WARN] app failed: {app_dir} err={exc}")

    summary = {
        "apps_total": apps_total,
        "apps_run": apps_run,
        "apps_failed": apps_failed,
        "total_chains": total_chains,
        "invalid_outputs": total_invalid,
        "timeout_outputs": total_timeout,
        "pred_distribution": dict(pred_counter),
        "confidence_distribution": dict(conf_counter),
        "fallback_distribution": dict(fb_counter),
        "vllm_url": args.vllm_url,
        "model": args.model,
        "timeout": args.timeout,
        "max_retries": args.max_retries,
    }
    out_dir = target if os.path.isdir(target) else os.path.dirname(target)
    summary_path = os.path.join(out_dir, SUMMARY_FILENAME)
    _save_json(summary_path, summary)
    print(f"\n[SAVED] summary={summary_path}")


if __name__ == "__main__":
    main()
