# -*- coding: utf-8 -*-
"""
Unified entrypoint for llmui.
Modes:
  - full       : phase1 + phase2 + phase3
  - phase1     : data collect
  - phase2     : data process
  - phase3     : scene + permission + judgement (+ optional compliance + final decision)
"""

import argparse
import json
import os
import sys
import traceback
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from configs import settings

PROMPT_DIR = settings.PROMPT_DIR
RULE_FILE = settings.SCENE_RULE_FILE
from analy_pipline.scene import (
    run_chain_semantic_interpreter,
    run_regulatory_scene_mapping,
    run_scene_from_semantics_text,
    run_scene_llm,
    run_scene_vllm,
)
from analy_pipline.permission import run_permission_rule
from analy_pipline.judge import run_rule_judgement, run_llm_compliance
from analy_pipline.judge.finalize_decision import FinalizeConfig, finalize_results, finalize_results_v2


def list_valid_apks(directory: str) -> List[str]:
    if not os.path.isdir(directory):
        return []
    files = os.listdir(directory)
    apk_files = []
    for f in files:
        full_path = os.path.join(directory, f)
        if f.endswith(".apk") and not f.startswith("._") and os.path.getsize(full_path) > 1024:
            apk_files.append(f)
    return apk_files


def _phase1_checkpoint_path() -> str:
    return os.path.join(settings.DATA_RAW_DIR, "phase1_checkpoint.json")


def _phase1_runlog_path() -> str:
    return os.path.join(settings.DATA_RAW_DIR, f"phase1_runlog_{settings.RUN_ID}.json")


def _write_phase1_checkpoint(payload: dict) -> None:
    os.makedirs(settings.DATA_RAW_DIR, exist_ok=True)
    payload = dict(payload)
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    payload["run_id"] = settings.RUN_ID
    with open(_phase1_checkpoint_path(), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _write_phase1_runlog(payload: dict) -> None:
    os.makedirs(settings.DATA_RAW_DIR, exist_ok=True)
    with open(_phase1_runlog_path(), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def run_phase1(target: str) -> None:
    from data_pipline.data_collect import DataCollectAgent

    if os.path.isdir(target):
        apk_files = list_valid_apks(target)
        print(f"[INFO] Found {len(apk_files)} APKs.")
        started_at = datetime.now()
        _write_phase1_checkpoint(
            {
                "status": "running",
                "target": target,
                "total_apks": len(apk_files),
                "current_index": 0,
                "current_apk": "",
                "last_success_apk": "",
                "failed_count": 0,
                "failures": [],
            }
        )
        runlog = {
            "run_id": settings.RUN_ID,
            "status": "running",
            "target": target,
            "time_limit_minutes": settings.TIME_LIMIT,
            "total_apks": len(apk_files),
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": "",
            "summary": {
                "success": 0,
                "skipped_existing": 0,
                "recovered_with_output": 0,
                "failed": 0,
            },
            "failed_apks": [],
            "records": [],
        }
        failed = []
        last_success_apk = ""
        for idx, apk in enumerate(apk_files, 1):
            full_apk_path = os.path.join(target, apk)
            item_started = datetime.now()
            print(f"[INFO] Phase1 {idx}/{len(apk_files)} -> {apk}")
            _write_phase1_checkpoint(
                {
                    "status": "running",
                    "target": target,
                    "total_apks": len(apk_files),
                    "current_index": idx,
                    "current_apk": apk,
                    "last_success_apk": last_success_apk,
                    "failed_count": len(failed),
                    "failures": failed,
                }
            )
            try:
                result = DataCollectAgent(full_apk_path, time=settings.TIME_LIMIT).run(skip_if_result_exist=True)
                result = result or "success"
                if result in ("success", "recovered_with_output"):
                    last_success_apk = apk
                if result not in runlog["summary"]:
                    result = "success"
                runlog["summary"][result] += 1
                runlog["records"].append(
                    {
                        "index": idx,
                        "apk": apk,
                        "status": result,
                        "started_at": item_started.isoformat(timespec="seconds"),
                        "finished_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                _write_phase1_checkpoint(
                    {
                        "status": "running",
                        "target": target,
                        "total_apks": len(apk_files),
                        "current_index": idx,
                        "current_apk": apk,
                        "last_success_apk": last_success_apk,
                        "failed_count": len(failed),
                        "failures": failed,
                    }
                )
            except KeyboardInterrupt:
                runlog["status"] = "interrupted"
                runlog["finished_at"] = datetime.now().isoformat(timespec="seconds")
                _write_phase1_runlog(runlog)
                _write_phase1_checkpoint(
                    {
                        "status": "interrupted",
                        "target": target,
                        "total_apks": len(apk_files),
                        "current_index": idx,
                        "current_apk": apk,
                        "last_success_apk": last_success_apk,
                        "failed_count": len(failed),
                        "failures": failed,
                    }
                )
                raise
            except Exception as exc:
                failed.append({"apk": apk, "error": str(exc)})
                runlog["summary"]["failed"] += 1
                runlog["failed_apks"].append({"apk": apk, "error": str(exc)})
                runlog["records"].append(
                    {
                        "index": idx,
                        "apk": apk,
                        "status": "failed",
                        "error": str(exc),
                        "started_at": item_started.isoformat(timespec="seconds"),
                        "finished_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                print(f"[WARN] Phase1 failed for {apk}: {exc}")
                traceback.print_exc()
                _write_phase1_checkpoint(
                    {
                        "status": "running",
                        "target": target,
                        "total_apks": len(apk_files),
                        "current_index": idx,
                        "current_apk": apk,
                        "last_success_apk": last_success_apk,
                        "failed_count": len(failed),
                        "failures": failed,
                    }
                )
                continue
        runlog["status"] = "done_with_failures" if failed else "done"
        runlog["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_phase1_runlog(runlog)
        _write_phase1_checkpoint(
            {
                "status": "done_with_failures" if failed else "done",
                "target": target,
                "total_apks": len(apk_files),
                "current_index": len(apk_files),
                "current_apk": "",
                "last_success_apk": last_success_apk,
                "failed_count": len(failed),
                "failures": failed,
            }
        )
        if failed:
            print(f"[WARN] Phase1 completed with {len(failed)} failures.")
            for item in failed:
                print(f"  - {item['apk']}: {item['error']}")
        print(f"[INFO] Phase1 checkpoint: {_phase1_checkpoint_path()}")
        print(f"[INFO] Phase1 runlog: {_phase1_runlog_path()}")
    else:
        DataCollectAgent(target, time=settings.TIME_LIMIT).run(skip_if_result_exist=True)


def run_phase2(raw_root: str, processed_root: str) -> None:
    from data_pipline import data_process

    data_process.process_raw_root(raw_root, processed_root)


def _parse_chain_ids(raw: str) -> Optional[List[int]]:
    if not raw or not raw.strip():
        return None
    out: List[int] = []
    for seg in raw.split(","):
        seg = seg.strip()
        if not seg:
            continue
        try:
            out.append(int(seg))
        except Exception:
            continue
    return out or None


def _iter_result_app_dirs(target: str) -> List[str]:
    if os.path.isfile(os.path.join(target, "result.json")):
        return [target]
    out: List[str] = []
    if not os.path.isdir(target):
        return out
    for d in sorted(os.listdir(target)):
        app_dir = os.path.join(target, d)
        if os.path.isdir(app_dir) and os.path.isfile(os.path.join(app_dir, "result.json")):
            out.append(app_dir)
    return out


def _resolve_phase3_app_dirs(target: str, app_name: str = "") -> List[str]:
    if os.path.isfile(os.path.join(target, "result.json")):
        if app_name and os.path.basename(target) != app_name:
            return []
        return [target]
    if not os.path.isdir(target):
        return []
    if app_name:
        app_dir = os.path.join(target, app_name)
        if os.path.isfile(os.path.join(app_dir, "result.json")):
            return [app_dir]
        return []
    return _iter_result_app_dirs(target)


def _read_json_list(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _summary_dir(target: str) -> str:
    return target if os.path.isdir(target) else os.path.dirname(target)


def _run_apps_with_incremental(
    app_dirs: List[str],
    output_filename: str,
    force: bool,
    runner,
) -> Dict[str, int]:
    stats = {"apps_total": len(app_dirs), "apps_run": 0, "apps_skipped": 0, "apps_failed": 0}
    for app_dir in app_dirs:
        out_path = os.path.join(app_dir, output_filename)
        if not force and os.path.isfile(out_path):
            stats["apps_skipped"] += 1
            print(f"[SKIP] app={app_dir} output exists: {output_filename}")
            continue
        try:
            runner(app_dir)
            stats["apps_run"] += 1
        except Exception as exc:
            stats["apps_failed"] += 1
            print(f"[WARN] step failed app={app_dir}: {exc}")
    return stats


def _build_semantics_summary(app_dirs: List[str], step_stats: Dict[str, int]) -> Dict[str, Any]:
    total = 0
    low_conf = 0
    timeout = 0
    for app_dir in app_dirs:
        for rec in _read_json_list(os.path.join(app_dir, "result_chain_semantics.json")):
            total += 1
            if str(rec.get("confidence", "")).lower() == "low":
                low_conf += 1
            reason = str(rec.get("rerun_reason", "")).lower()
            err = str(rec.get("error", "")).lower()
            if "timeout" in reason or "timeout" in err:
                timeout += 1
    return {
        **step_stats,
        "total_chains": total,
        "low_confidence_chains": low_conf,
        "timeout_chains": timeout,
    }


def _build_scene_summary(app_dirs: List[str], step_stats: Dict[str, int]) -> Dict[str, Any]:
    scene_counter: Counter = Counter()
    top3_counter: Counter = Counter()
    for app_dir in app_dirs:
        for rec in _read_json_list(os.path.join(app_dir, "result_ui_task_scene.json")):
            scene = str(rec.get("ui_task_scene") or rec.get("predicted_scene") or "UNKNOWN")
            scene_counter[scene] += 1
            top3 = rec.get("ui_task_scene_top3") or rec.get("scene_top3") or []
            top3_key = " | ".join([str(x) for x in top3[:3]]) if isinstance(top3, list) else ""
            if top3_key:
                top3_counter[top3_key] += 1
    total = sum(scene_counter.values())
    return {
        **step_stats,
        "total_chains": total,
        "scene_distribution": [
            {"scene": k, "count": v, "ratio": round(v / total, 4) if total else 0.0}
            for k, v in scene_counter.most_common()
        ],
        "top3_distribution": [
            {"top3": k, "count": v, "ratio": round(v / total, 4) if total else 0.0}
            for k, v in top3_counter.most_common()
        ],
    }


def _build_rule_summary(app_dirs: List[str], step_stats: Dict[str, int]) -> Dict[str, Any]:
    risk_counter: Counter = Counter()
    for app_dir in app_dirs:
        for rec in _read_json_list(os.path.join(app_dir, "result_rule_screening.json")):
            risk_counter[str(rec.get("overall_rule_signal", "MEDIUM_RISK"))] += 1
    total = sum(risk_counter.values())
    return {
        **step_stats,
        "total_chains": total,
        "risk_level_distribution": [
            {"risk": k, "count": v, "ratio": round(v / total, 4) if total else 0.0}
            for k, v in risk_counter.most_common()
        ],
    }


def _map_gt_binary(item: Dict[str, Any]) -> str:
    gt_risk = item.get("gt_risk")
    if str(gt_risk) in {"0", "1"}:
        return "RISKY" if int(gt_risk) == 1 else "SAFE"
    label = str(item.get("gt_label", "")).strip().upper()
    if label in {"SAFE", "RISKY"}:
        return label
    return ""


def _map_final_binary(item: Dict[str, Any]) -> str:
    decision = str(item.get("final_decision", "")).strip().upper()
    risk = str(item.get("final_risk", "")).strip().upper()
    if decision in {"CLEARLY_OK", "COMPLIANT"} or risk == "LOW":
        return "SAFE"
    if decision in {"CLEARLY_RISKY", "NEED_REVIEW", "NON_COMPLIANT", "SUSPICIOUS"} or risk in {"MEDIUM", "HIGH"}:
        return "RISKY"
    return ""


def _build_final_summary(app_dirs: List[str], step_stats: Dict[str, int]) -> Dict[str, Any]:
    tp = fp = tn = fn = 0
    evaluated = 0
    for app_dir in app_dirs:
        pred_map = {int(x.get("chain_id", -1)): x for x in _read_json_list(os.path.join(app_dir, "result_final_decision.json"))}
        gt_items = _read_json_list(os.path.join(app_dir, "label_judge.json"))
        for gt in gt_items:
            try:
                cid = int(gt.get("chain_id"))
            except Exception:
                continue
            gt_b = _map_gt_binary(gt)
            pred_b = _map_final_binary(pred_map.get(cid, {}))
            if not gt_b or not pred_b:
                continue
            evaluated += 1
            if gt_b == "RISKY" and pred_b == "RISKY":
                tp += 1
            elif gt_b == "SAFE" and pred_b == "RISKY":
                fp += 1
            elif gt_b == "SAFE" and pred_b == "SAFE":
                tn += 1
            elif gt_b == "RISKY" and pred_b == "SAFE":
                fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    tnr = tn / (tn + fp) if (tn + fp) else 0.0
    bal_acc = (recall + tnr) / 2 if evaluated else 0.0
    return {
        **step_stats,
        "evaluated_chains": evaluated,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "balanced_accuracy": round(bal_acc, 6),
    }


def run_phase3_semantics(processed_root: str, app_name: str, force: bool, chain_ids: Optional[List[int]]) -> Dict[str, Any]:
    app_dirs = _resolve_phase3_app_dirs(processed_root, app_name=app_name)
    stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_chain_semantics.json",
        force=force,
        runner=lambda app_dir: run_chain_semantic_interpreter.run(
            target=app_dir,
            prompt_file=os.path.join(PROMPT_DIR, "chain_semantic_interpreter_vision.txt"),
            vllm_url=settings.VLLM_VL_URL,
            model=settings.VLLM_VL_MODEL,
            chain_ids=chain_ids,
        ),
    )
    summary = _build_semantics_summary(app_dirs, stats)
    summary_path = os.path.join(_summary_dir(processed_root), "phase3_semantics_summary.json")
    _write_json(summary_path, summary)
    print(f"[phase3_semantics] summary={summary_path}")
    return summary


def run_phase3_scene(
    processed_root: str,
    app_name: str,
    force: bool,
    chain_ids: Optional[List[int]],
    scene_mode: str,
) -> Dict[str, Any]:
    app_dirs = _resolve_phase3_app_dirs(processed_root, app_name=app_name)
    scene_mode = "vision" if scene_mode == "vl" else scene_mode
    if scene_mode == "vision":
        stats = _run_apps_with_incremental(
            app_dirs,
            output_filename="result_scene_vision.json",
            force=force,
            runner=lambda app_dir: run_scene_vllm.run(app_dir),
        )
        summary = {"note": "vision scene mode executed", **stats}
        summary_path = os.path.join(_summary_dir(processed_root), "phase3_scene_summary.json")
        _write_json(summary_path, summary)
        print(f"[phase3_scene] summary={summary_path}")
        return summary

    stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_ui_task_scene.json",
        force=force,
        runner=lambda app_dir: run_scene_from_semantics_text.run(
            target=app_dir,
            prompt_file=os.path.join(PROMPT_DIR, "scene_from_semantics_text.txt"),
            vllm_url=settings.VLLM_TEXT_URL,
            model=settings.VLLM_TEXT_MODEL,
            chain_ids=chain_ids,
        ),
    )
    summary = _build_scene_summary(app_dirs, stats)
    summary_path = os.path.join(_summary_dir(processed_root), "phase3_scene_summary.json")
    _write_json(summary_path, summary)
    print(f"[phase3_scene] summary={summary_path}")
    return summary


def run_phase3_rule(processed_root: str, app_name: str, force: bool, chain_ids: Optional[List[int]]) -> Dict[str, Any]:
    app_dirs = _resolve_phase3_app_dirs(processed_root, app_name=app_name)
    stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_rule_screening.json",
        force=force,
        runner=lambda app_dir: (
            run_permission_rule.run(app_dir, chain_ids=chain_ids),
            run_regulatory_scene_mapping.run(
                target=app_dir,
                prompt_file=os.path.join(PROMPT_DIR, "regulatory_scene_mapping.txt"),
                knowledge_file=settings.PERMISSION_KNOWLEDGE_FILE,
                vllm_url=settings.VLLM_TEXT_URL,
                model=settings.VLLM_TEXT_MODEL,
                chain_ids=chain_ids,
            ),
            run_rule_judgement.run(
                app_dir,
                rule_file=RULE_FILE,
                knowledge_file=settings.PERMISSION_KNOWLEDGE_FILE,
                chain_ids=chain_ids,
            ),
        ),
    )
    summary = _build_rule_summary(app_dirs, stats)
    summary_path = os.path.join(_summary_dir(processed_root), "phase3_rule_summary.json")
    _write_json(summary_path, summary)
    print(f"[phase3_rule] summary={summary_path}")
    return summary


def run_phase3_llm(processed_root: str, app_name: str, force: bool, chain_ids: Optional[List[int]]) -> Dict[str, Any]:
    app_dirs = _resolve_phase3_app_dirs(processed_root, app_name=app_name)
    stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_llm_review.json",
        force=force,
        runner=lambda app_dir: run_llm_compliance.run(
            app_dir,
            prompt_dir=PROMPT_DIR,
            vllm_url=settings.VLLM_TEXT_URL,
            model=settings.VLLM_TEXT_MODEL,
            chain_ids=chain_ids,
        ),
    )
    summary = {
        **stats,
        "total_records": sum(len(_read_json_list(os.path.join(app_dir, "result_llm_review.json"))) for app_dir in app_dirs),
    }
    summary_path = os.path.join(_summary_dir(processed_root), "phase3_llm_summary.json")
    _write_json(summary_path, summary)
    print(f"[phase3_llm] summary={summary_path}")
    return summary


def run_phase3_final(processed_root: str, app_name: str, force: bool, chain_ids: Optional[List[int]]) -> Dict[str, Any]:
    app_dirs = _resolve_phase3_app_dirs(processed_root, app_name=app_name)
    cfg = FinalizeConfig(
        vllm_url=settings.VLLM_TEXT_URL,
        vllm_model=settings.VLLM_TEXT_MODEL,
        prompt_dir=PROMPT_DIR,
    )
    stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_final_decision.json",
        force=force,
        runner=lambda app_dir: finalize_results(app_dir, cfg, chain_ids=chain_ids),
    )
    summary = _build_final_summary(app_dirs, stats)
    summary_path = os.path.join(_summary_dir(processed_root), "phase3_final_summary.json")
    _write_json(summary_path, summary)
    print(f"[phase3_final] summary={summary_path}")
    return summary


def run_phase3_v2(processed_root: str, app_name: str, force: bool, chain_ids: Optional[List[int]]) -> Dict[str, Any]:
    app_dirs = _resolve_phase3_app_dirs(processed_root, app_name=app_name)

    permission_stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_permission.json",
        force=force,
        runner=lambda app_dir: run_permission_rule.run(app_dir, chain_ids=chain_ids),
    )

    semantic_stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_semantic_v2.json",
        force=force,
        runner=lambda app_dir: run_chain_semantic_interpreter.run(
            target=app_dir,
            prompt_file=os.path.join(PROMPT_DIR, "chain_semantic_interpreter_vision.txt"),
            vllm_url=settings.VLLM_VL_URL,
            model=settings.VLLM_VL_MODEL,
            output_filename="result_semantic_v2.json",
            summary_filename="semantic_v2_summary.json",
            schema_version="v2",
            single_pass_only=True,
            chain_ids=chain_ids,
        ),
    )

    llm_stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_retrieved_knowledge.json",
        force=force,
        runner=lambda app_dir: run_llm_compliance.run_v2(
            app_dir,
            prompt_dir=PROMPT_DIR,
            vllm_url=settings.VLLM_TEXT_URL,
            model=settings.VLLM_TEXT_MODEL,
            chain_ids=chain_ids,
            semantic_filename="result_semantic_v2.json",
            retrieval_output_filename="result_retrieved_knowledge.json",
        ),
    )

    cfg = FinalizeConfig(
        vllm_url=settings.VLLM_TEXT_URL,
        vllm_model=settings.VLLM_TEXT_MODEL,
        prompt_dir=PROMPT_DIR,
        arbitration_strategy="lightweight_single_pass_v2",
    )
    final_stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_final_decision.json",
        force=force,
        runner=lambda app_dir: finalize_results_v2(app_dir, cfg, chain_ids=chain_ids),
    )

    summary = {
        "pipeline": "phase3_v2",
        "permission_stage": permission_stats,
        "semantic_v2_stage": semantic_stats,
        "llm_v2_stage": llm_stats,
        "final_v2_stage": final_stats,
        "total_semantic_v2_records": sum(len(_read_json_list(os.path.join(app_dir, "result_semantic_v2.json"))) for app_dir in app_dirs),
        "total_retrieval_records": sum(len(_read_json_list(os.path.join(app_dir, "result_retrieved_knowledge.json"))) for app_dir in app_dirs),
        "total_llm_records": sum(len(_read_json_list(os.path.join(app_dir, "result_llm_review.json"))) for app_dir in app_dirs),
        "total_final_records": sum(len(_read_json_list(os.path.join(app_dir, "result_final_decision.json"))) for app_dir in app_dirs),
    }
    summary_path = os.path.join(_summary_dir(processed_root), "phase3_v2_summary.json")
    _write_json(summary_path, summary)
    print(f"[phase3_v2] summary={summary_path}")
    return summary


def run_phase3(
    processed_root: str,
    scene_mode: str,
    run_compliance: bool,
    app_name: str = "",
    force: bool = False,
    chain_ids: Optional[List[int]] = None,
) -> None:
    run_phase3_semantics(processed_root, app_name=app_name, force=force, chain_ids=chain_ids)
    run_phase3_scene(
        processed_root,
        app_name=app_name,
        force=force,
        chain_ids=chain_ids,
        scene_mode=scene_mode,
    )
    run_phase3_rule(processed_root, app_name=app_name, force=force, chain_ids=chain_ids)
    if run_compliance:
        run_phase3_llm(processed_root, app_name=app_name, force=force, chain_ids=chain_ids)
    run_phase3_final(processed_root, app_name=app_name, force=force, chain_ids=chain_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description="llmui unified entry")
    parser.add_argument(
        "mode",
        choices=[
            "full",
            "phase1",
            "phase2",
            "phase3",
            "phase3_v2",
            "phase3_semantics",
            "phase3_scene",
            "phase3_rule",
            "phase3_llm",
            "phase3_final",
        ],
    )
    parser.add_argument("target", help="APK path, APK dir, raw dir, or processed dir")

    parser.add_argument("--raw-root", default=settings.DATA_RAW_DIR)
    parser.add_argument("--processed-root", default=settings.DATA_PROCESSED_DIR)

    parser.add_argument("--scene-mode", choices=["text", "vision", "vl"], default="text")
    parser.add_argument("--no-compliance", action="store_true")
    parser.add_argument("--force", action="store_true", help="force rerun even if output file already exists")
    parser.add_argument("--app", default="", help="run only one app directory name under processed root")
    parser.add_argument("--chain-ids", default="", help="comma-separated chain ids, e.g. 1,3,9")

    args = parser.parse_args()
    print(f"[run_id={settings.RUN_ID}] mode={args.mode}")
    chain_ids = _parse_chain_ids(args.chain_ids)

    if args.mode == "phase1":
        run_phase1(args.target)
        return

    if args.mode == "phase2":
        raw_root = args.target or args.raw_root
        run_phase2(raw_root, args.processed_root)
        return

    if args.mode == "phase3":
        run_phase3(
            processed_root=args.target or args.processed_root,
            scene_mode=args.scene_mode,
            run_compliance=not args.no_compliance,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "phase3_v2":
        run_phase3_v2(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "phase3_semantics":
        run_phase3_semantics(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "phase3_scene":
        run_phase3_scene(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
            scene_mode=args.scene_mode,
        )
        return

    if args.mode == "phase3_rule":
        run_phase3_rule(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "phase3_llm":
        run_phase3_llm(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "phase3_final":
        run_phase3_final(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "full":
        run_phase1(args.target)
        run_phase2(args.raw_root, args.processed_root)
        run_phase3(
            processed_root=args.processed_root,
            scene_mode=args.scene_mode,
            run_compliance=not args.no_compliance,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )


if __name__ == "__main__":
    main()
