# -*- coding: utf-8 -*-
"""
Unified entrypoint for llmui.
Modes:
  - full       : phase1 + phase2 + phase3
  - phase1     : data collect
  - phase2     : data process
  - phase3     : scene + permission + judgement (+ optional compliance)
  - agent      : phase3 via LangGraph agent
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from typing import List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from configs import settings

PROMPT_DIR = settings.PROMPT_DIR
RULE_FILE = settings.SCENE_RULE_FILE
from data_pipline.data_collect import DataCollectAgent
from data_pipline import data_process
from analy_pipline.scene import run_scene_llm, run_scene_vllm
from analy_pipline.permission import run_permission_rule
from analy_pipline.judge import run_rule_judgement, run_llm_compliance
from analy_pipline.agent.phase3_agent import run_agent, AgentConfig


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
    data_process.process_raw_root(raw_root, processed_root)


def run_phase3(
    processed_root: str,
    scene_mode: str,
    run_compliance: bool,
) -> None:
    if scene_mode == "vl":
        run_scene_vllm.run(processed_root)
    else:
        run_scene_llm.run(processed_root)

    run_permission_rule.run(processed_root)

    run_rule_judgement.run(processed_root, rule_file=RULE_FILE)

    if run_compliance:
        run_llm_compliance.run(
            processed_root,
            prompt_dir=PROMPT_DIR,
            vllm_url=settings.VLLM_TEXT_URL,
            model=settings.VLLM_TEXT_MODEL,
        )


def run_phase3_agent(processed_root: str, instruction: str) -> None:
    cfg = AgentConfig(
        agent_base_url=settings.AGENT_BASE_URL,
        agent_model=settings.AGENT_MODEL,
        vllm_url=settings.VLLM_TEXT_URL,
        vllm_model=settings.VLLM_TEXT_MODEL,
        vl_url=settings.VLLM_VL_URL,
        vl_model=settings.VLLM_VL_MODEL,
        rule_file=RULE_FILE,
        prompt_dir=PROMPT_DIR,
    )
    run_agent(processed_root, instruction, cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="llmui unified entry")
    parser.add_argument("mode", choices=["full", "phase1", "phase2", "phase3", "agent"])
    parser.add_argument("target", help="APK path, APK dir, raw dir, or processed dir")

    parser.add_argument("--raw-root", default=settings.DATA_RAW_DIR)
    parser.add_argument("--processed-root", default=settings.DATA_PROCESSED_DIR)

    parser.add_argument("--scene-mode", choices=["text", "vl"], default="text")
    parser.add_argument("--no-compliance", action="store_true")
    parser.add_argument("--agent-instruction", default="执行完整三阶段分析")

    args = parser.parse_args()
    print(f"[run_id={settings.RUN_ID}] mode={args.mode}")

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
        )
        return

    if args.mode == "agent":
        run_phase3_agent(args.target or args.processed_root, args.agent_instruction)
        return

    if args.mode == "full":
        run_phase1(args.target)
        run_phase2(args.raw_root, args.processed_root)
        run_phase3(
            processed_root=args.processed_root,
            scene_mode=args.scene_mode,
            run_compliance=not args.no_compliance,
        )


if __name__ == "__main__":
    main()
