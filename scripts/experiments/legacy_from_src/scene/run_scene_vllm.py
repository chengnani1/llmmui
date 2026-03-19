# -*- coding: utf-8 -*-
"""
Phase3 Step1 (vision mode): scene and intent inference.
"""

import base64
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.schema_utils import (  # noqa: E402
    CONF_LEVELS,
    SCENE_UNKNOWN,
    normalize_scene_record,
    validate_scene_results,
)
from configs import settings  # noqa: E402
from configs.domain.scene_config import (  # noqa: E402
    MAX_STEPS,
    MAX_TEXT_LEN,
    MAX_TOTAL_LEN,
    MAX_WIDGETS,
    SCENE_LIST,
    build_scene_prompt,
)
from utils.http_retry import post_json_with_retry  # noqa: E402
from utils.validators import validate_result_json_chains  # noqa: E402


OUTPUT_FILENAME = "result_scene_vision.json"
MODEL_NAME = settings.VLLM_VL_MODEL
VLLM_URL = settings.VLLM_VL_URL
LLM_TIMEOUT = settings.LLM_RESPONSE_TIMEOUT


def widget_score(w: Dict[str, Any]) -> int:
    score = 0
    text = (w.get("text") or "").strip()
    if text:
        score += 2
        if len(text) > 4:
            score += 1
    if "permission" in (w.get("resource-id") or "").lower():
        score += 4
    if "Text" in (w.get("class") or "") or "Button" in (w.get("class") or ""):
        score += 2
    return score


def compress_widgets(widgets: List[Dict[str, Any]]) -> str:
    widgets = sorted(widgets, key=widget_score, reverse=True)[:MAX_WIDGETS]
    return "; ".join((w.get("text") or "").strip() for w in widgets if (w.get("text") or "").strip())


def compress_step(step: Dict[str, Any]) -> str:
    f = step.get("feature", {})
    return f"[TEXT]\n{(f.get('text') or '')[:MAX_TEXT_LEN]}\n\n[WIDGETS]\n{compress_widgets(f.get('widgets') or [])}"


def compress_ui_sequence(ui_item: Dict[str, Any]) -> str:
    before = ui_item.get("ui_before_grant")
    granting = (ui_item.get("ui_granting") or [])[: MAX_STEPS * 2]
    after = ui_item.get("ui_after_grant")

    blocks = []
    if before:
        blocks.append("[BEFORE]\n" + compress_step(before))
    if granting:
        blocks.append("[GRANTING]\n" + "\n\n---\n\n".join(compress_step(g) for g in granting))
    if after:
        blocks.append("[AFTER]\n" + compress_step(after))
    return "\n\n======\n\n".join(blocks)[:MAX_TOTAL_LEN]


def _extract_basis_from_chain(chain: Dict[str, Any]) -> Dict[str, Any]:
    def _read_text(ui_part: Dict[str, Any]) -> str:
        feature = (ui_part or {}).get("feature", {})
        return str(feature.get("text", "")).strip()

    before = _read_text(chain.get("ui_before_grant") or {})
    granting_items = chain.get("ui_granting") or []
    granting = " | ".join(_read_text(x) for x in granting_items[:2] if isinstance(x, dict) and _read_text(x))
    after = _read_text(chain.get("ui_after_grant") or {})

    chain_summary = " / ".join(x for x in [before[:80], granting[:80], after[:80]] if x)

    widgets: List[str] = []
    for ui_part in [chain.get("ui_before_grant") or {}, *(granting_items[:2]), chain.get("ui_after_grant") or {}]:
        if not isinstance(ui_part, dict):
            continue
        ws = (ui_part.get("feature", {}) or {}).get("widgets", [])
        if not isinstance(ws, list):
            continue
        for w in ws:
            if not isinstance(w, dict):
                continue
            t = str(w.get("text", "")).strip()
            if t:
                widgets.append(t)
    widgets = list(dict.fromkeys(widgets))[:8]

    tokens: List[str] = []
    for text in [before, granting, after]:
        for seg in re.split(r"[\s,;，。！？、|/]+", text):
            seg = seg.strip()
            if len(seg) >= 2:
                tokens.append(seg)
    keywords = list(dict.fromkeys(tokens))[:8]
    return {
        "keywords": keywords,
        "widgets": widgets,
        "chain_summary": chain_summary[:220],
    }


def encode_image_base64(image_path: str) -> Optional[str]:
    if not image_path or not os.path.exists(image_path):
        return None
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_vllm_vl(prompt: str, image_path: Optional[str]) -> str:
    payload: Dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    image_b64 = encode_image_base64(image_path)
    if image_b64:
        payload["images"] = [image_b64]
    r = post_json_with_retry(
        VLLM_URL,
        payload,
        timeout=LLM_TIMEOUT,
        max_retries=3,
        backoff_factor=1.5,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def extract_json(text: str) -> Dict[str, Any]:
    text = re.sub(r"^```.*?\n", "", text, flags=re.S).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except Exception:
                pass
    return {}


def infer_confidence(obj: Dict[str, Any], predicted_scene: str, scene_top3: List[str]) -> str:
    raw = str(obj.get("confidence", "")).strip().lower()
    if raw in CONF_LEVELS:
        return raw
    if predicted_scene == SCENE_UNKNOWN:
        return "low"
    if len(scene_top3) < 2:
        return "low"
    if len(scene_top3) == 3 and len(set(scene_top3)) == 3 and scene_top3[0] == predicted_scene:
        return "high"
    return "medium"


def _postprocess_other_scene(rec: Dict[str, Any]) -> Dict[str, Any]:
    if rec.get("predicted_scene") != "其他":
        return rec
    top3 = rec.get("scene_top3", [])
    if not isinstance(top3, list):
        return rec
    candidates = [x for x in top3 if isinstance(x, str) and x != "其他"]
    if not candidates:
        return rec
    promoted = candidates[0]
    new_top3 = [promoted] + [x for x in top3 if isinstance(x, str) and x != promoted]
    rec = dict(rec)
    rec["predicted_scene"] = promoted
    rec["scene_top3"] = new_top3[:3]
    rec["confidence"] = "low"
    if not rec.get("other_reason"):
        rec["other_reason"] = "top1_other_but_non_other_candidate_exists"
    return rec


def parse_scene_record(
    chain_id: int,
    obj: Dict[str, Any],
    rerun: bool,
    rerun_reason: str,
    scene_basis_default: Dict[str, Any],
) -> Dict[str, Any]:
    predicted_scene = obj.get("predicted_scene") or obj.get("top1") or SCENE_UNKNOWN
    top3 = obj.get("scene_top3") or obj.get("top3") or []
    intent = obj.get("intent", "")
    confidence = infer_confidence(obj, str(predicted_scene), top3 if isinstance(top3, list) else [])
    other_reason = obj.get("other_reason", "")
    scene_basis = obj.get("scene_basis", scene_basis_default)
    rec = normalize_scene_record(
        {
            "chain_id": chain_id,
            "predicted_scene": predicted_scene,
            "scene_top3": top3,
            "intent": intent,
            "confidence": confidence,
            "rerun": rerun,
            "rerun_reason": rerun_reason,
            "other_reason": other_reason,
            "scene_basis": scene_basis,
        },
        SCENE_LIST,
    )
    return _postprocess_other_scene(rec)


def abnormal_reason(rec: Dict[str, Any]) -> str:
    if rec["predicted_scene"] == SCENE_UNKNOWN:
        return "missing_scene"
    if len(rec["scene_top3"]) < 3:
        return "top3_incomplete"
    if rec["predicted_scene"] == "其他" and rec["confidence"] in {"low", "medium"}:
        return "other_not_confident"
    if rec["confidence"] == "low":
        return "low_confidence"
    return ""


def unknown_record(chain_id: int, rerun: bool, reason: str, scene_basis: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "chain_id": chain_id,
        "predicted_scene": SCENE_UNKNOWN,
        "scene_top3": [],
        "intent": "",
        "confidence": "low",
        "rerun": rerun,
        "rerun_reason": reason,
        "other_reason": "",
        "scene_basis": scene_basis,
    }


def _build_prompt(feature: str, strict: bool, forbid_other: bool = False) -> str:
    prompt = build_scene_prompt(feature)
    if strict:
        prompt += (
            "\n\n【补充要求】\n"
            "必须输出合法 JSON；`scene_top3` 必须包含 3 个候选场景；"
            "`predicted_scene` 必须等于 `scene_top3[0]`。\n"
        )
    if forbid_other:
        prompt += "\n【重试约束】本次重试禁止输出 predicted_scene=其他，请在非“其他”类别中选最接近任务类别，并降低 confidence。\n"
    return prompt


def recognize_scene(ui_item: Dict[str, Any], result_json_path: str, idx: int) -> Dict[str, Any]:
    chain_id = int(ui_item.get("chain_id", idx))
    image_path = os.path.join(os.path.dirname(result_json_path), f"chain_{chain_id}.png")
    feature = compress_ui_sequence(ui_item)
    scene_basis = _extract_basis_from_chain(ui_item)

    raw = call_vllm_vl(_build_prompt(feature, strict=False), image_path=image_path)
    obj = extract_json(raw)
    rec = parse_scene_record(chain_id, obj, rerun=False, rerun_reason="", scene_basis_default=scene_basis)
    reason = abnormal_reason(rec)
    if not reason:
        return rec

    raw2 = call_vllm_vl(
        _build_prompt(feature, strict=True, forbid_other=(reason == "other_not_confident")),
        image_path=image_path,
    )
    obj2 = extract_json(raw2)
    rec2 = parse_scene_record(chain_id, obj2, rerun=True, rerun_reason=reason, scene_basis_default=scene_basis)
    reason2 = abnormal_reason(rec2)
    if reason2:
        return unknown_record(chain_id, rerun=True, reason=reason2, scene_basis=scene_basis)
    return rec2


def process_result_json(path: str) -> Tuple[int, int]:
    app_dir = os.path.dirname(path)
    print(f"[Scene-Vision] start app={app_dir}")
    with open(path, "r", encoding="utf-8") as f:
        data = validate_result_json_chains(json.load(f))

    out: List[Dict[str, Any]] = []
    invalid_outputs = 0
    for idx, ui_item in enumerate(tqdm(data, desc="Scene Vision", ncols=90)):
        chain_id = int(ui_item.get("chain_id", idx))
        is_invalid = False
        try:
            rec = recognize_scene(ui_item, path, idx)
        except Exception as exc:
            is_invalid = True
            rec = unknown_record(
                chain_id,
                rerun=False,
                reason=f"exception:{exc}",
                scene_basis=_extract_basis_from_chain(ui_item),
            )
        if rec["predicted_scene"] == SCENE_UNKNOWN:
            is_invalid = True
        if is_invalid:
            invalid_outputs += 1
        out.append(rec)

    normalized, dropped = validate_scene_results(out, SCENE_LIST)
    invalid_outputs += dropped

    save_path = os.path.join(app_dir, OUTPUT_FILENAME)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(
        f"[Scene-Vision] finish app={app_dir} chains={len(data)} "
        f"written={len(normalized)} invalid={invalid_outputs} out={save_path}"
    )
    return len(normalized), invalid_outputs


def run(target: str) -> None:
    total_chains = 0
    total_invalid = 0

    def _run_one(result_json_path: str) -> None:
        nonlocal total_chains, total_invalid
        chains, invalid = process_result_json(result_json_path)
        total_chains += chains
        total_invalid += invalid

    if target.endswith("result.json"):
        _run_one(target)
    elif os.path.exists(os.path.join(target, "result.json")):
        _run_one(os.path.join(target, "result.json"))
    else:
        for d in sorted(os.listdir(target)):
            app_dir = os.path.join(target, d)
            if not os.path.isdir(app_dir):
                continue
            result_json_path = os.path.join(app_dir, "result.json")
            if not os.path.exists(result_json_path):
                continue
            try:
                _run_one(result_json_path)
            except Exception as exc:
                print(f"[Scene-Vision][WARN] app failed {app_dir}: {exc}")

    print(f"[Scene-Vision] all_done chains={total_chains} invalid={total_invalid}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_scene_vllm.py <result.json | processed_dir>")
        raise SystemExit(1)
    run(sys.argv[1])
