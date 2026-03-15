# -*- coding: utf-8 -*-
"""
Task13 (12+1 taxonomy) text scene inference experiment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

from tqdm import tqdm

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.chain_summary import load_chain_summary_map  # noqa: E402
from analy_pipline.scene.task13_experiment_utils import (  # noqa: E402
    build_summary,
    extract_json_obj,
    normalize_task13_record,
    should_rerun,
)
from configs import settings  # noqa: E402
from configs.domain.scene_config import (  # noqa: E402
    SCENE_LIST,
    format_scene_definitions,
    format_scene_list,
    format_scene_rules,
)
from utils.http_retry import post_json_with_retry  # noqa: E402
from utils.validators import validate_result_json_chains  # noqa: E402


OUTPUT_FILENAME = "result_scene_task13_text.json"
SUMMARY_FILENAME = "scene_task13_text_summary.json"
DEFAULT_PROMPT_FILE = os.path.join(settings.PROMPT_DIR, "scene_task13_text.txt")


def load_prompt_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def build_prompt(template: str, input_payload: Dict[str, Any], strict: bool, forbid_other: bool) -> str:
    prompt = template
    prompt = prompt.replace("{SCENE_LIST}", format_scene_list())
    prompt = prompt.replace("{SCENE_DEFINITIONS}", format_scene_definitions())
    prompt = prompt.replace("{SCENE_RULES}", format_scene_rules())
    prompt = prompt.replace("{INPUT_JSON}", json.dumps(input_payload, ensure_ascii=False, indent=2))
    if strict:
        prompt += (
            "\n\n【输出补充约束】\n"
            "1) scene_top3 必须有3个且去重。\n"
            "2) predicted_scene 必须等于 scene_top3[0]。\n"
            "3) confidence 只能是 high|medium|low。\n"
        )
    if forbid_other:
        prompt += "\n【重跑约束】如能判断，请不要输出“其他”，改为最接近任务类别并降低 confidence。\n"
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


def infer_chain_record(
    chain_id: int,
    input_payload: Dict[str, Any],
    prompt_template: str,
    vllm_url: str,
    model: str,
) -> Dict[str, Any]:
    fallback_phrase = str(input_payload.get("task_hint", "")).strip()
    fallback_intent = str(input_payload.get("before_text", "")).strip()[:80]

    try:
        raw = call_llm(build_prompt(prompt_template, input_payload, strict=False, forbid_other=False), vllm_url, model)
        obj = extract_json_obj(raw)
        rec = normalize_task13_record(
            chain_id=chain_id,
            obj=obj,
            scene_list=SCENE_LIST,
            rerun=False,
            rerun_reason="",
            fallback_task_phrase=fallback_phrase,
            fallback_intent=fallback_intent,
        )
        reason = should_rerun(rec, SCENE_LIST)
        if not reason:
            return rec

        raw2 = call_llm(
            build_prompt(
                prompt_template,
                input_payload,
                strict=True,
                forbid_other=(reason == "other_low_confidence"),
            ),
            vllm_url,
            model,
        )
        obj2 = extract_json_obj(raw2)
        rec2 = normalize_task13_record(
            chain_id=chain_id,
            obj=obj2,
            scene_list=SCENE_LIST,
            rerun=True,
            rerun_reason=reason,
            fallback_task_phrase=fallback_phrase,
            fallback_intent=fallback_intent,
        )
        reason2 = should_rerun(rec2, SCENE_LIST)
        if reason2:
            return normalize_task13_record(
                chain_id=chain_id,
                obj={"predicted_scene": "其他", "scene_top3": ["其他"], "confidence": "low"},
                scene_list=SCENE_LIST,
                rerun=True,
                rerun_reason=reason2,
                fallback_task_phrase=fallback_phrase,
                fallback_intent=fallback_intent,
                error=f"rerun_failed:{reason2}",
            )
        return rec2
    except Exception as exc:
        return normalize_task13_record(
            chain_id=chain_id,
            obj={"predicted_scene": "其他", "scene_top3": ["其他"], "confidence": "low"},
            scene_list=SCENE_LIST,
            rerun=False,
            rerun_reason=f"exception:{type(exc).__name__}",
            fallback_task_phrase=fallback_phrase,
            fallback_intent=fallback_intent,
            error=str(exc),
        )


def iter_app_dirs(target: str) -> List[str]:
    if os.path.exists(os.path.join(target, "result.json")):
        return [target]
    out = []
    for d in sorted(os.listdir(target)):
        app_dir = os.path.join(target, d)
        if os.path.isdir(app_dir) and os.path.exists(os.path.join(app_dir, "result.json")):
            out.append(app_dir)
    return out


def process_app(app_dir: str, prompt_template: str, vllm_url: str, model: str) -> Tuple[List[Dict[str, Any]], int]:
    result_json_path = os.path.join(app_dir, "result.json")
    with open(result_json_path, "r", encoding="utf-8") as f:
        chains = validate_result_json_chains(json.load(f))

    summary_map = load_chain_summary_map(result_json_path)
    records: List[Dict[str, Any]] = []
    invalid = 0

    for idx, chain in enumerate(tqdm(chains, desc=f"Scene Task13 Text {os.path.basename(app_dir)}", ncols=90)):
        chain_id = int(chain.get("chain_id", idx))
        chain_summary = summary_map.get(chain_id, {"chain_summary": {}}).get("chain_summary", {})
        top_widgets = chain_summary.get("top_widgets", []) if isinstance(chain_summary, dict) else []
        task_hint = top_widgets[0] if top_widgets else ""
        input_payload = {
            "chain_id": chain_id,
            "package": chain.get("package") or chain.get("pkg") or "",
            "before_text": chain_summary.get("before_text", ""),
            "granting_text": chain_summary.get("granting_text", ""),
            "after_text": chain_summary.get("after_text", ""),
            "top_widgets": top_widgets,
            "chain_summary": chain_summary,
            "permissions_hint": chain.get("predicted_permissions") or chain.get("true_permissions") or [],
            "task_hint": task_hint,
        }
        rec = infer_chain_record(chain_id, input_payload, prompt_template, vllm_url, model)
        if rec.get("predicted_scene") == "其他" and rec.get("confidence") == "low":
            invalid += 1
        records.append(rec)

    out_path = os.path.join(app_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"[SceneTask13-Text] finish app={app_dir} chains={len(records)} low_conf_other={invalid} out={out_path}")
    return records, invalid


def run(target: str, prompt_file: str, vllm_url: str, model: str) -> None:
    prompt_template = load_prompt_template(prompt_file)
    app_dirs = iter_app_dirs(target)
    all_records: List[Dict[str, Any]] = []
    total_invalid = 0

    for app_dir in app_dirs:
        try:
            records, invalid = process_app(app_dir, prompt_template, vllm_url, model)
            all_records.extend(records)
            total_invalid += invalid
        except Exception as exc:
            print(f"[SceneTask13-Text][WARN] app failed app={app_dir} err={exc}")

    summary = build_summary(all_records)
    summary["invalid_low_conf_other"] = total_invalid
    summary["apps_processed"] = len(app_dirs)

    summary_dir = target if not os.path.exists(os.path.join(target, "result.json")) else os.path.dirname(os.path.join(target, "result.json"))
    summary_path = os.path.join(summary_dir, SUMMARY_FILENAME)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[SceneTask13-Text] done apps={len(app_dirs)} total_chains={len(all_records)} summary={summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task13 text scene inference experiment")
    parser.add_argument("target", help="processed root or one app dir")
    parser.add_argument("--prompt-file", default=DEFAULT_PROMPT_FILE)
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_TEXT_URL", settings.VLLM_TEXT_URL))
    parser.add_argument("--model", default=os.getenv("VLLM_TEXT_MODEL", settings.VLLM_TEXT_MODEL))
    args = parser.parse_args()
    run(args.target, args.prompt_file, args.vllm_url, args.model)
