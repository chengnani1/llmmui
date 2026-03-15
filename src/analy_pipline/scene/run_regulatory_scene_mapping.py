# -*- coding: utf-8 -*-
"""
Map UI task scene + chain semantics to regulatory scene space.

Input:
  - result_chain_semantics.json
  - result_ui_task_scene.json
  - optional result_permission.json
  - permission_map.json (allowed_map / banned_map)

Output:
  - result_regulatory_scene.json
  - regulatory_scene_summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from tqdm import tqdm

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.common.schema_utils import (  # noqa: E402
    normalize_permission_name,
    validate_chain_semantic_results,
    validate_permission_results,
    validate_regulatory_scene_results,
    validate_ui_task_scene_results,
)
from configs import settings  # noqa: E402
from configs.domain.scene_config import SCENE_LIST  # noqa: E402
from utils.http_retry import post_json_with_retry  # noqa: E402


SEM_FILENAME = "result_chain_semantics.json"
UI_FILENAME = "result_ui_task_scene.json"
PERM_FILENAME = "result_permission.json"
OUTPUT_FILENAME = "result_regulatory_scene.json"
SUMMARY_FILENAME = "regulatory_scene_summary.json"
DEFAULT_PROMPT_FILE = os.path.join(settings.PROMPT_DIR, "regulatory_scene_mapping.txt")
DEFAULT_KNOWLEDGE_FILE = settings.PERMISSION_KNOWLEDGE_FILE


UI_TO_REG_BASE = {
    "账号与身份认证": ["用户登录", "网络社区", "新闻资讯"],
    "地图与位置服务": ["地图导航", "打车服务", "旅游服务"],
    "内容浏览与搜索": ["新闻资讯", "在线影音", "网络社区"],
    "社交互动与通信": ["即时通信聊天服务", "网络社区", "网络直播"],
    "媒体拍摄与扫码": ["网络社区", "网上购物", "网络直播"],
    "相册选择与媒体上传": ["网络社区", "网上购物", "在线影音"],
    "商品浏览与消费": ["网上购物", "餐饮外卖", "旅游服务"],
    "支付与金融交易": ["网络支付", "手机银行", "投资理财"],
    "文件与数据管理": ["文件管理", "实用工具", "网络邮箱"],
    "设备清理与系统优化": ["实用工具", "文件管理", "新闻资讯"],
    "网络连接与设备管理": ["实用工具", "远程会议", "网络邮箱"],
    "用户反馈与客服": ["网络社区", "新闻资讯", "网上购物"],
    "其他": ["实用工具", "新闻资讯", "网络社区"],
}

REG_ALIAS = {
    "用户账户登录": "用户登录",
    "用户帐号登录": "用户登录",
    "支付": "网络支付",
    "购物": "网上购物",
    "聊天": "即时通信聊天服务",
    "地图": "地图导航",
    "工具": "实用工具",
}


def ui_scene_file(app_dir: str) -> str:
    path = os.path.join(app_dir, UI_FILENAME)
    return path if os.path.exists(path) else ""


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def extract_json_obj(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    text = re.sub(r"^```(?:json)?\n", "", text, flags=re.I)
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except Exception:
                return {}
    return {}


def build_prompt(
    template: str,
    reg_scene_list: List[str],
    input_payload: Dict[str, Any],
    strict: bool,
    avoid_first: str = "",
) -> str:
    prompt = template
    prompt = prompt.replace("{REGULATORY_SCENE_LIST}", "\n".join(f"- {x}" for x in reg_scene_list))
    prompt = prompt.replace("{INPUT_JSON}", json.dumps(input_payload, ensure_ascii=False, indent=2))
    if strict:
        prompt += (
            "\n\n【重试补充约束】\n"
            "1) top1/top3 必须来自给定 Regulatory Scene 列表。\n"
            "2) top3 必须为长度3且去重。\n"
            "3) confidence 只能是 high|medium|low。\n"
        )
    if avoid_first:
        prompt += f"\n【重试提示】上次候选不稳定，请避免再次输出 {avoid_first}，优先选择更具体候选。\n"
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


def normalize_reg_scene_label(name: str, reg_scene_list: List[str]) -> str:
    s = str(name or "").strip()
    if s in reg_scene_list:
        return s
    if s in REG_ALIAS and REG_ALIAS[s] in reg_scene_list:
        return REG_ALIAS[s]
    for k, v in REG_ALIAS.items():
        if k in s and v in reg_scene_list:
            return v
    return "UNKNOWN"


def _keyword_candidates(text: str, reg_scene_list: List[str]) -> List[str]:
    text = str(text or "")
    rules = [
        (["登录", "账号", "验证码"], "用户登录"),
        (["支付", "收款", "转账", "付款"], "网络支付"),
        (["购物", "商品", "下单", "店铺"], "网上购物"),
        (["聊天", "消息", "私信", "群聊"], "即时通信聊天服务"),
        (["导航", "定位", "地图", "附近"], "地图导航"),
        (["外卖", "点餐"], "餐饮外卖"),
        (["文档", "文件", "PDF", "下载"], "文件管理"),
        (["清理", "垃圾", "加速", "优化"], "实用工具"),
        (["邮箱", "邮件"], "网络邮箱"),
        (["视频", "直播", "短视频"], "网络直播"),
        (["新闻", "资讯"], "新闻资讯"),
    ]
    out: List[str] = []
    for kws, scene in rules:
        if scene not in reg_scene_list:
            continue
        if any(k in text for k in kws):
            out.append(scene)
    return out


def _permission_candidates(perms: List[str], reg_scene_list: List[str]) -> List[str]:
    pset = set(perms)
    out: List[str] = []
    if {"ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"} & pset:
        out.extend(["地图导航", "打车服务", "旅游服务"])
    if {"READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "READ_MEDIA_IMAGES", "READ_MEDIA_VIDEO"} & pset:
        out.extend(["文件管理", "网上购物", "网络社区"])
    if {"READ_PHONE_NUMBERS"} & pset:
        out.extend(["用户登录", "网络支付"])
    if {"RECORD_AUDIO", "CAMERA"} & pset:
        out.extend(["即时通信聊天服务", "网络直播", "网络社区"])
    return [x for x in out if x in reg_scene_list]


def heuristic_candidates(
    ui_scene: str,
    task_phrase: str,
    intent: str,
    chain_summary: str,
    permissions: List[str],
    reg_scene_list: List[str],
) -> List[str]:
    out: List[str] = []
    for x in UI_TO_REG_BASE.get(ui_scene, UI_TO_REG_BASE["其他"]):
        if x in reg_scene_list and x not in out:
            out.append(x)
    for x in _permission_candidates(permissions, reg_scene_list):
        if x not in out:
            out.append(x)
    text = " ".join([task_phrase, intent, chain_summary])
    for x in _keyword_candidates(text, reg_scene_list):
        if x not in out:
            out.append(x)
    for x in reg_scene_list:
        if len(out) >= 3:
            break
        if x not in out:
            out.append(x)
    return out[:3]


def should_rerun(rec: Dict[str, Any]) -> str:
    if rec.get("regulatory_scene_top1", "UNKNOWN") == "UNKNOWN":
        return "missing_regulatory_top1"
    if len(rec.get("regulatory_scene_top3", [])) < 3:
        return "regulatory_top3_incomplete"
    if rec.get("confidence") == "low":
        return "low_confidence"
    return ""


def normalize_record(
    chain_id: int,
    sem: Dict[str, Any],
    ui: Dict[str, Any],
    permissions: List[str],
    obj: Dict[str, Any],
    reg_scene_list: List[str],
    allowed_map: Dict[str, List[str]],
    banned_map: Dict[str, List[str]],
    rerun: bool,
    rerun_reason: str,
) -> Dict[str, Any]:
    ui_scene = str(ui.get("ui_task_scene") or ui.get("predicted_scene") or "其他")
    ui_top3 = ui.get("ui_task_scene_top3") or ui.get("scene_top3") or [ui_scene]

    top1 = normalize_reg_scene_label(obj.get("regulatory_scene_top1"), reg_scene_list)
    top3_raw = obj.get("regulatory_scene_top3") or []
    top3 = [normalize_reg_scene_label(x, reg_scene_list) for x in top3_raw]
    top3 = [x for x in top3 if x != "UNKNOWN"]

    fallback_top3 = heuristic_candidates(
        ui_scene=ui_scene,
        task_phrase=str(sem.get("task_phrase", "")),
        intent=str(sem.get("intent", "")),
        chain_summary=str(sem.get("chain_summary", "")),
        permissions=permissions,
        reg_scene_list=reg_scene_list,
    )
    if top1 == "UNKNOWN":
        top1 = fallback_top3[0] if fallback_top3 else "UNKNOWN"
    if top1 != "UNKNOWN" and top1 not in top3:
        top3 = [top1] + top3
    for x in fallback_top3:
        if len(top3) >= 3:
            break
        if x not in top3:
            top3.append(x)
    for x in reg_scene_list:
        if len(top3) >= 3:
            break
        if x not in top3:
            top3.append(x)
    top3 = top3[:3]

    confidence = str(obj.get("confidence", "medium")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low" if top1 == "UNKNOWN" else "medium"

    allowed_permissions = [normalize_permission_name(x) for x in allowed_map.get(top1, [])]
    banned_permissions = [normalize_permission_name(x) for x in banned_map.get(top1, [])]
    return {
        "chain_id": chain_id,
        "task_phrase": sem.get("task_phrase", ""),
        "intent": sem.get("intent", ""),
        "chain_summary": sem.get("chain_summary", ""),
        "permissions": permissions,
        "ui_task_scene": ui_scene,
        "ui_task_scene_top3": ui_top3,
        "regulatory_scene_top1": top1,
        "regulatory_scene_top3": top3,
        "mapping_reason": str(obj.get("mapping_reason", ""))[:280],
        "allowed_permissions": allowed_permissions,
        "banned_permissions": banned_permissions,
        "confidence": confidence,
        "rerun": rerun,
        "rerun_reason": rerun_reason,
    }


def infer_regulatory_scene(
    chain_id: int,
    sem: Dict[str, Any],
    ui: Dict[str, Any],
    permissions: List[str],
    prompt_template: str,
    reg_scene_list: List[str],
    allowed_map: Dict[str, List[str]],
    banned_map: Dict[str, List[str]],
    vllm_url: str,
    model: str,
) -> Dict[str, Any]:
    payload = {
        "chain_id": chain_id,
        "task_phrase": sem.get("task_phrase", ""),
        "intent": sem.get("intent", ""),
        "chain_summary": sem.get("chain_summary", ""),
        "ui_task_scene": ui.get("ui_task_scene") or ui.get("predicted_scene", "其他"),
        "ui_task_scene_top3": ui.get("ui_task_scene_top3") or ui.get("scene_top3", []),
        "permissions": permissions,
    }
    try:
        raw = call_llm(
            build_prompt(prompt_template, reg_scene_list, payload, strict=False),
            vllm_url=vllm_url,
            model=model,
        )
        obj = extract_json_obj(raw)
        rec = normalize_record(
            chain_id=chain_id,
            sem=sem,
            ui=ui,
            permissions=permissions,
            obj=obj,
            reg_scene_list=reg_scene_list,
            allowed_map=allowed_map,
            banned_map=banned_map,
            rerun=False,
            rerun_reason="",
        )
        reason = should_rerun(rec)
        if not reason:
            return rec

        raw2 = call_llm(
            build_prompt(
                prompt_template,
                reg_scene_list,
                payload,
                strict=True,
                avoid_first=rec.get("regulatory_scene_top1", ""),
            ),
            vllm_url=vllm_url,
            model=model,
        )
        obj2 = extract_json_obj(raw2)
        rec2 = normalize_record(
            chain_id=chain_id,
            sem=sem,
            ui=ui,
            permissions=permissions,
            obj=obj2,
            reg_scene_list=reg_scene_list,
            allowed_map=allowed_map,
            banned_map=banned_map,
            rerun=True,
            rerun_reason=reason,
        )
        reason2 = should_rerun(rec2)
        if reason2:
            rec2["rerun"] = True
            rec2["rerun_reason"] = reason2
            rec2["confidence"] = "low"
        return rec2
    except Exception as exc:
        rec = normalize_record(
            chain_id=chain_id,
            sem=sem,
            ui=ui,
            permissions=permissions,
            obj={},
            reg_scene_list=reg_scene_list,
            allowed_map=allowed_map,
            banned_map=banned_map,
            rerun=False,
            rerun_reason=f"exception:{type(exc).__name__}",
        )
        rec["mapping_reason"] = f"fallback_due_to_exception:{str(exc)[:120]}"
        rec["confidence"] = "low"
        return rec


def iter_app_dirs(target: str) -> List[str]:
    if os.path.exists(os.path.join(target, SEM_FILENAME)):
        return [target]
    out = []
    for d in sorted(os.listdir(target)):
        app_dir = os.path.join(target, d)
        if os.path.isdir(app_dir) and os.path.exists(os.path.join(app_dir, SEM_FILENAME)):
            out.append(app_dir)
    return out


def load_permissions_map(app_dir: str) -> Dict[int, List[str]]:
    perm_path = os.path.join(app_dir, PERM_FILENAME)
    if not os.path.exists(perm_path):
        return {}
    items, _ = validate_permission_results(load_json(perm_path))
    out: Dict[int, List[str]] = {}
    for it in items:
        out[int(it["chain_id"])] = [normalize_permission_name(x) for x in it.get("predicted_permissions", [])]
    return out


def process_app(
    app_dir: str,
    prompt_template: str,
    reg_scene_list: List[str],
    allowed_map: Dict[str, List[str]],
    banned_map: Dict[str, List[str]],
    vllm_url: str,
    model: str,
    chain_ids_filter: Optional[Set[int]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    sem_items, sem_invalid = validate_chain_semantic_results(load_json(os.path.join(app_dir, SEM_FILENAME)))
    ui_path = ui_scene_file(app_dir)
    if not ui_path:
        raise RuntimeError(f"missing ui scene file in app: {app_dir}")
    ui_items, ui_invalid = validate_ui_task_scene_results(load_json(ui_path), SCENE_LIST)
    perm_map = load_permissions_map(app_dir)

    sem_map = {int(x["chain_id"]): x for x in sem_items}
    ui_map = {int(x["chain_id"]): x for x in ui_items}
    chain_id_list = sorted(set(sem_map.keys()) | set(ui_map.keys()))

    out: List[Dict[str, Any]] = []
    invalid = sem_invalid + ui_invalid
    for chain_id in tqdm(chain_id_list, desc=f"RegSceneMap {os.path.basename(app_dir)}", ncols=90):
        if chain_ids_filter is not None and chain_id not in chain_ids_filter:
            continue
        sem = sem_map.get(chain_id, {})
        ui = ui_map.get(chain_id, {})
        if not sem:
            invalid += 1
        if not ui:
            invalid += 1
        permissions = perm_map.get(chain_id) or [
            normalize_permission_name(x)
            for x in ((sem.get("permission_event") or {}).get("permissions") or [])
            if isinstance(x, str)
        ]
        rec = infer_regulatory_scene(
            chain_id=chain_id,
            sem=sem,
            ui=ui,
            permissions=permissions,
            prompt_template=prompt_template,
            reg_scene_list=reg_scene_list,
            allowed_map=allowed_map,
            banned_map=banned_map,
            vllm_url=vllm_url,
            model=model,
        )
        if rec.get("confidence") == "low":
            invalid += 1
        out.append(rec)

    normalized, dropped = validate_regulatory_scene_results(out, SCENE_LIST, reg_scene_list)
    invalid += dropped
    out_path = os.path.join(app_dir, OUTPUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    print(f"[RegSceneMap] finish app={app_dir} chains={len(normalized)} invalid={invalid} out={out_path}")
    return normalized, invalid


def build_summary(records: List[Dict[str, Any]], apps_processed: int, invalid_count: int) -> Dict[str, Any]:
    total = len(records)
    dist = Counter()
    conf = Counter()
    rerun = Counter()
    for rec in records:
        dist[str(rec.get("regulatory_scene_top1", "UNKNOWN"))] += 1
        conf[str(rec.get("confidence", "low"))] += 1
        if rec.get("rerun"):
            rerun[str(rec.get("rerun_reason", "")) or "rerun_true_no_reason"] += 1
    return {
        "apps_processed": apps_processed,
        "total_chains": total,
        "invalid_count": invalid_count,
        "regulatory_scene_distribution": [
            {"scene": k, "count": v, "ratio": round(v / total, 4) if total else 0.0}
            for k, v in dist.most_common()
        ],
        "confidence_distribution": [
            {"confidence": k, "count": conf[k], "ratio": round(conf[k] / total, 4) if total else 0.0}
            for k in ["high", "medium", "low"]
        ],
        "rerun_distribution": [{"reason": k, "count": v} for k, v in rerun.most_common()],
    }


def run(
    target: str,
    prompt_file: str,
    knowledge_file: str,
    vllm_url: str,
    model: str,
    chain_ids: Optional[List[int]] = None,
) -> None:
    prompt_template = load_prompt_template(prompt_file)
    knowledge = load_json(knowledge_file)
    allowed_map = knowledge.get("allowed_map", {})
    banned_map = knowledge.get("banned_map", {})
    reg_scene_list = sorted(set(allowed_map.keys()) & set(banned_map.keys()))
    if not reg_scene_list:
        raise RuntimeError(f"No regulatory scenes found in knowledge file: {knowledge_file}")

    chain_ids_filter: Optional[Set[int]] = None
    if chain_ids:
        chain_ids_filter = {int(x) for x in chain_ids}

    app_dirs = iter_app_dirs(target)
    all_records: List[Dict[str, Any]] = []
    invalid = 0
    for app_dir in app_dirs:
        if not ui_scene_file(app_dir):
            print(f"[RegSceneMap][WARN] skip app={app_dir} missing ui task scene file")
            continue
        try:
            records, app_invalid = process_app(
                app_dir=app_dir,
                prompt_template=prompt_template,
                reg_scene_list=reg_scene_list,
                allowed_map=allowed_map,
                banned_map=banned_map,
                vllm_url=vllm_url,
                model=model,
                chain_ids_filter=chain_ids_filter,
            )
            all_records.extend(records)
            invalid += app_invalid
        except Exception as exc:
            print(f"[RegSceneMap][WARN] app failed app={app_dir} err={exc}")

    summary = build_summary(all_records, apps_processed=len(app_dirs), invalid_count=invalid)
    summary_dir = target if not os.path.exists(os.path.join(target, SEM_FILENAME)) else os.path.dirname(os.path.join(target, SEM_FILENAME))
    summary_path = os.path.join(summary_dir, SUMMARY_FILENAME)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[RegSceneMap] done apps={len(app_dirs)} total_chains={len(all_records)} summary={summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regulatory scene mapping")
    parser.add_argument("target", help="processed root or one app dir")
    parser.add_argument("--prompt-file", default=DEFAULT_PROMPT_FILE)
    parser.add_argument("--knowledge-file", default=os.getenv("PERMISSION_KNOWLEDGE_FILE", DEFAULT_KNOWLEDGE_FILE))
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_TEXT_URL", settings.VLLM_TEXT_URL))
    parser.add_argument("--model", default=os.getenv("VLLM_TEXT_MODEL", settings.VLLM_TEXT_MODEL))
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
        args.target,
        args.prompt_file,
        args.knowledge_file,
        args.vllm_url,
        args.model,
        chain_ids=chain_ids or None,
    )
