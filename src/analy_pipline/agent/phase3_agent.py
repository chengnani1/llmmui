# -*- coding: utf-8 -*-
"""
Phase3 agent (LangGraph)
- Scene recognition
    - text LLM (8001)
    - VL LLM (8002)
- Permission reasoning (LLM-only)
- Rule judgement
- LLM compliance analysis
"""

import argparse
import os
import sys
import json
from typing import Dict, Any, List
from dataclasses import dataclass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from configs import settings
from utils.http_retry import post_json_with_retry

PROMPT_DIR = settings.PROMPT_DIR
RULE_FILE = settings.SCENE_RULE_FILE
ARBITER_PROMPT = os.path.join(PROMPT_DIR, "arbiter.txt")
from analy_pipline.scene import run_scene_llm as scene_llm
from analy_pipline.scene import run_scene_vllm as scene_vl
from analy_pipline.permission import run_permission_rule as perm_rule
from analy_pipline.judge import run_rule_judgement as rule_judge
from analy_pipline.judge import run_llm_compliance as llm_compliance


@dataclass
class AgentConfig:
    agent_base_url: str
    agent_model: str
    vllm_url: str
    vllm_model: str
    vl_url: str
    vl_model: str
    rule_file: str
    prompt_dir: str


CONFIG: AgentConfig


@tool
def run_scene_llm_tool(target: str) -> str:
    """Run text-only scene recognition. target: processed dir or result.json."""
    scene_llm.VLLM_URL = CONFIG.vllm_url
    scene_llm.MODEL_NAME = CONFIG.vllm_model
    scene_llm.run(target)
    return "scene_llm_done"


@tool
def run_scene_vl_tool(target: str) -> str:
    """Run image-based scene recognition (vLLM VL). target: processed dir or result.json."""
    scene_vl.VLLM_URL = CONFIG.vl_url
    scene_vl.MODEL_NAME = CONFIG.vl_model
    scene_vl.run(target)
    return "scene_vl_done"


@tool
def run_permission_rule_tool(target: str) -> str:
    """Run rule-only permission recognition. target: processed dir."""
    perm_rule.run(target)
    return "permission_rule_done"


@tool
def run_rule_judgement_tool(target: str) -> str:
    """Run rule judgement. target: processed dir."""
    rule_judge.run(target, rule_file=CONFIG.rule_file)
    return "rule_judgement_done"


@tool
def run_llm_compliance_tool(target: str) -> str:
    """Run LLM compliance analysis. target: processed dir."""
    llm_compliance.run(
        target,
        prompt_dir=CONFIG.prompt_dir,
        vllm_url=CONFIG.vllm_url,
        model=CONFIG.vllm_model,
    )
    return "llm_compliance_done"


SYSTEM_PROMPT = """你是 Phase3 智能体编排器，负责执行场景识别、权限识别（规则）、规则裁决、合规分析。

规则：
1) 当用户要求“完整三阶段分析”时，按顺序调用：
   场景识别 -> 权限识别（规则） -> 规则裁决 -> 合规分析
2) 若用户明确要求 VL / 图像 / 8002，则用 run_scene_vl_tool，否则默认 run_scene_llm_tool。
3) 场景识别支持 result.json 或 processed 目录；后续步骤必须是 processed 目录。
4) 执行完成后，简短说明生成的结果文件名。
"""


def build_agent(cfg: AgentConfig):
    llm = ChatOpenAI(
        base_url=cfg.agent_base_url,
        api_key=os.getenv("LLM_API_KEY", "not-needed"),
        model=cfg.agent_model,
        temperature=0,
    )
    tools = [
        run_scene_llm_tool,
        run_scene_vl_tool,
        run_permission_rule_tool,
        run_rule_judgement_tool,
        run_llm_compliance_tool,
    ]
    return create_react_agent(llm, tools=tools)


def _tool_schema_block(tools) -> str:
    parts = []
    for t in tools:
        try:
            parts.append(t.tool_json_schema())
        except Exception:
            pass
    if not parts:
        return ""
    return "\n\n[TOOLS_SCHEMA]\n" + "\n".join(parts) + "\n"


def run_agent(target: str, instruction: str, cfg: AgentConfig) -> None:
    global CONFIG
    CONFIG = cfg
    tools = [
        run_scene_llm_tool,
        run_scene_vl_tool,
        run_permission_rule_tool,
        run_rule_judgement_tool,
        run_llm_compliance_tool,
    ]
    llm = ChatOpenAI(
        base_url=cfg.agent_base_url,
        api_key=os.getenv("LLM_API_KEY", "not-needed"),
        model=cfg.agent_model,
        temperature=0,
    )
    agent = create_react_agent(llm, tools=tools)
    sys_prompt = SYSTEM_PROMPT + _tool_schema_block(tools)
    msg = f"目标路径: {target}\n指令: {instruction}"
    try:
        result = agent.invoke({"messages": [("system", sys_prompt), ("user", msg)]})
        content = result["messages"][-1].content
        if isinstance(content, str) and "<tool_call>" in content:
            # qwen3_xml returns tool calls in content; execute full pipeline
            _run_full_pipeline(target, instruction)
            _postprocess_results(target, cfg)
            print("✅ Tool-call detected (qwen3_xml). 已执行完整 Phase3 流程")
            return
        print(content)
        return
    except Exception as e:
        err = str(e)
        # Fallback for vLLM without tool-calling support
        if "tool choice" not in err and "tool-call" not in err and "BadRequestError" not in err:
            raise

    _run_full_pipeline(target, instruction)
    _postprocess_results(target, cfg)
    print("✅ Fallback: 执行完场景识别、权限识别、规则裁决、合规分析")


def _run_full_pipeline(target: str, instruction: str) -> None:
    use_vl = any(k in instruction.lower() for k in ["vl", "图像", "8002"])
    if use_vl:
        run_scene_vl_tool(target)
    else:
        run_scene_llm_tool(target)
    run_permission_rule_tool(target)
    run_rule_judgement_tool(target)
    run_llm_compliance_tool(target)


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _call_arbiter_llm(cfg: AgentConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not os.path.exists(ARBITER_PROMPT):
        return {}
    with open(ARBITER_PROMPT, "r", encoding="utf-8") as f:
        prompt = f.read().strip()
    prompt = prompt.replace("{INPUT}", json.dumps(payload, ensure_ascii=False, indent=2))
    body = {
        "model": cfg.vllm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    try:
        r = post_json_with_retry(
            cfg.vllm_url,
            body,
            timeout=settings.LLM_RESPONSE_TIMEOUT,
            max_retries=3,
            backoff_factor=1.5,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        s, e = content.find("{"), content.rfind("}")
        if s != -1 and e != -1:
            return json.loads(content[s:e + 1])
    except Exception:
        return {}
    return {}


def _postprocess_results(root: str, cfg: AgentConfig) -> None:
    def iter_app_dirs(p: str) -> List[str]:
        if os.path.exists(os.path.join(p, "result.json")):
            return [p]
        return [
            os.path.join(p, d)
            for d in os.listdir(p)
            if d.startswith("fastbot-") and os.path.isdir(os.path.join(p, d))
        ]

    for app_dir in iter_app_dirs(root):
        rule_path = os.path.join(app_dir, "result_rule_judgement.json")
        comp_path = os.path.join(app_dir, "result_llm_compliance_v3.json")

        rules = _load_json(rule_path) or []
        comps = _load_json(comp_path) or []
        comp_map = {c.get("chain_id"): c for c in comps if isinstance(c, dict)}

        final_results = []
        for r in rules:
            chain_id = r.get("chain_id")
            comp = comp_map.get(chain_id, {})
            final_comp = comp.get("final_compliance", {}) if isinstance(comp, dict) else {}

            final_decision = final_comp.get("final_decision")
            final_risk = final_comp.get("final_risk")
            rollback = False
            rollback_reason = ""

            if not final_decision or not final_risk or "_error" in final_comp or "_parse_error" in final_comp:
                rollback = True
                rollback_reason = "llm_output_invalid_or_missing"
                rule_signal = r.get("overall_rule_signal", "LOW_RISK")
                final_decision = "NEEDS_HUMAN_REVIEW" if rule_signal != "LOW_RISK" else "CLEARLY_OK"
                final_risk = "HIGH" if rule_signal == "HIGH_RISK" else ("MEDIUM" if rule_signal == "MEDIUM_RISK" else "LOW")

            if not rollback:
                rule_signal = r.get("overall_rule_signal", "LOW_RISK")
                if rule_signal == "HIGH_RISK" and final_decision == "CLEARLY_OK":
                    arb = _call_arbiter_llm(cfg, {"rule": r, "compliance": final_comp})
                    if arb.get("final_decision"):
                        final_decision = arb.get("final_decision")
                        final_risk = arb.get("final_risk", final_risk)
                        rollback = True
                        rollback_reason = "arbiter_override"

            final_results.append({
                "chain_id": chain_id,
                "scene": r.get("scene"),
                "permissions": r.get("permissions"),
                "rule_signal": r.get("overall_rule_signal"),
                "final_decision": final_decision,
                "final_risk": final_risk,
                "rollback": rollback,
                "rollback_reason": rollback_reason,
                "explain": {
                    "rule_signal": r.get("overall_rule_signal"),
                    "llm_final_decision": final_comp.get("final_decision"),
                    "llm_final_risk": final_comp.get("final_risk"),
                },
            })

        if final_results:
            out = os.path.join(app_dir, "result_final_decision.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(final_results, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase3 LangGraph agent")
    parser.add_argument("target", help="processed dir or result.json")
    parser.add_argument("instruction", nargs="?", default="执行完整三阶段分析")

    parser.add_argument("--agent-base-url", default=settings.AGENT_BASE_URL)
    parser.add_argument("--agent-model", default=settings.AGENT_MODEL)

    parser.add_argument("--vllm-url", default=settings.VLLM_TEXT_URL)
    parser.add_argument("--vllm-model", default=settings.VLLM_TEXT_MODEL)

    parser.add_argument("--vl-url", default=settings.VLLM_VL_URL)
    parser.add_argument("--vl-model", default=settings.VLLM_VL_MODEL)

    parser.add_argument("--rule-file", default=RULE_FILE)
    parser.add_argument("--prompt-dir", default=PROMPT_DIR)

    args = parser.parse_args()

    cfg = AgentConfig(
        agent_base_url=args.agent_base_url,
        agent_model=args.agent_model,
        vllm_url=args.vllm_url,
        vllm_model=args.vllm_model,
        vl_url=args.vl_url,
        vl_model=args.vl_model,
        rule_file=args.rule_file,
        prompt_dir=args.prompt_dir,
    )
    run_agent(args.target, args.instruction, cfg)


if __name__ == "__main__":
    main()
