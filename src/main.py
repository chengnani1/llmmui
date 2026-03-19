# -*- coding: utf-8 -*-
"""
Unified entrypoint for llmui.
Modes:
  - full       : phase1 + phase2 + phase3_v2
  - phase1     : data collect
  - phase2     : data process
  - phase3_v2  : permission + semantic_v2 + retrieved_knowledge + llm + final
  - phase3_v2_compliance : retrieval + llm only (reuse existing semantic/permission outputs)
  - phase3_v2_final      : final label mapping only (reuse existing llm output)
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from configs import settings

PROMPT_DIR = settings.PROMPT_DIR
from analy_pipline.scene import run_chain_semantic_interpreter
from analy_pipline.permission import run_permission_rule
from analy_pipline.judge import run_llm_compliance
from analy_pipline.judge.finalize_decision import FinalizeConfig, finalize_results_v2


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
        output_filename="result_llm_review.json",
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


def run_phase3_v2_compliance(processed_root: str, app_name: str, force: bool, chain_ids: Optional[List[int]]) -> Dict[str, Any]:
    app_dirs = _resolve_phase3_app_dirs(processed_root, app_name=app_name)
    llm_stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_llm_review.json",
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
    summary = {
        "pipeline": "phase3_v2_compliance",
        "llm_v2_stage": llm_stats,
        "total_retrieval_records": sum(len(_read_json_list(os.path.join(app_dir, "result_retrieved_knowledge.json"))) for app_dir in app_dirs),
        "total_llm_records": sum(len(_read_json_list(os.path.join(app_dir, "result_llm_review.json"))) for app_dir in app_dirs),
    }
    summary_path = os.path.join(_summary_dir(processed_root), "phase3_v2_compliance_summary.json")
    _write_json(summary_path, summary)
    print(f"[phase3_v2_compliance] summary={summary_path}")
    return summary


def run_phase3_v2_final(processed_root: str, app_name: str, force: bool, chain_ids: Optional[List[int]]) -> Dict[str, Any]:
    app_dirs = _resolve_phase3_app_dirs(processed_root, app_name=app_name)
    cfg = FinalizeConfig(
        vllm_url=settings.VLLM_TEXT_URL,
        vllm_model=settings.VLLM_TEXT_MODEL,
        prompt_dir=PROMPT_DIR,
    )
    final_stats = _run_apps_with_incremental(
        app_dirs,
        output_filename="result_final_decision.json",
        force=force,
        runner=lambda app_dir: finalize_results_v2(app_dir, cfg, chain_ids=chain_ids),
    )
    summary = {
        "pipeline": "phase3_v2_final",
        "final_v2_stage": final_stats,
        "total_llm_records": sum(len(_read_json_list(os.path.join(app_dir, "result_llm_review.json"))) for app_dir in app_dirs),
        "total_final_records": sum(len(_read_json_list(os.path.join(app_dir, "result_final_decision.json"))) for app_dir in app_dirs),
    }
    summary_path = os.path.join(_summary_dir(processed_root), "phase3_v2_final_summary.json")
    _write_json(summary_path, summary)
    print(f"[phase3_v2_final] summary={summary_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="llmui unified entry")
    parser.add_argument(
        "mode",
        choices=[
            "full",
            "phase1",
            "phase2",
            "phase3_v2",
            "phase3_v2_compliance",
            "phase3_v2_final",
        ],
    )
    parser.add_argument("target", help="APK path, APK dir, raw dir, or processed dir")

    parser.add_argument("--raw-root", default=settings.DATA_RAW_DIR)
    parser.add_argument("--processed-root", default=settings.DATA_PROCESSED_DIR)

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

    if args.mode == "phase3_v2":
        run_phase3_v2(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "phase3_v2_compliance":
        run_phase3_v2_compliance(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "phase3_v2_final":
        run_phase3_v2_final(
            processed_root=args.target or args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )
        return

    if args.mode == "full":
        run_phase1(args.target)
        run_phase2(args.raw_root, args.processed_root)
        run_phase3_v2(
            processed_root=args.processed_root,
            app_name=args.app,
            force=args.force,
            chain_ids=chain_ids,
        )


if __name__ == "__main__":
    main()
