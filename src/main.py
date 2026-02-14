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
import os
import sys
from typing import List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from configs import settings

PROMPT_DIR = os.path.join(ROOT, "src", "configs", "prompt")
RULE_FILE = os.path.join(ROOT, "src", "configs", "domain", "scene_permission_rules_16.json")
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


def run_phase1(target: str) -> None:
    if os.path.isdir(target):
        apk_files = list_valid_apks(target)
        print(f"[INFO] Found {len(apk_files)} APKs.")
        for apk in apk_files:
            full_apk_path = os.path.join(target, apk)
            DataCollectAgent(full_apk_path, time=settings.TIME_LIMIT).run(skip_if_result_exist=True)
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
