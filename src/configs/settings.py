# -*- coding: utf-8 -*-
"""
Single source of runtime configuration for llmui.

Naming convention:
- Preferred env vars: LLMMUI_*
- Backward compatibility: legacy vars are still accepted
"""

import json
import os
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _env_first(names, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _env_int(names, default: int) -> int:
    raw = _env_first(names, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _derive_models_url(chat_url: str) -> str:
    url = (chat_url or "").strip()
    if not url:
        return ""
    if url.endswith("/models"):
        return url
    marker = "/chat/completions"
    if url.endswith(marker):
        return url[: -len(marker)] + "/models"
    return url.rstrip("/") + "/models"


def _fetch_first_model_id(chat_url: str, timeout_seconds: float = 5.0) -> str:
    models_url = _derive_models_url(chat_url)
    if not models_url:
        return ""
    req = Request(models_url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return ""

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return ""
    first = data[0]
    if not isinstance(first, dict):
        return ""
    model_id = str(first.get("id", "")).strip()
    return model_id


def _resolve_vllm_model(names, default: str, chat_url: str) -> str:
    configured = _env_first(names, default)
    normalized = configured.strip().lower()
    if normalized and normalized not in {"qwen-text-model", "qwen-vl-model", "auto", "default"}:
        return configured
    discovered = _fetch_first_model_id(chat_url)
    return discovered or configured


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# =========================
# Runtime context
# =========================
RUN_ID = _env_first(["LLMMUI_RUN_ID", "RUN_ID"], uuid.uuid4().hex[:8])

# =========================
# Data paths
# =========================
DATA_DIR = _env_first(
    ["LLMMUI_DATA_ROOT", "DATA_DIR"],
    os.path.join(PROJECT_ROOT, "data"),
)
DATA_RAW_DIR = _env_first(
    ["LLMMUI_RAW_DIR", "DATA_RAW_DIR"],
    os.path.join(DATA_DIR, "raw"),
)
DATA_PROCESSED_DIR = _env_first(
    ["LLMMUI_PROCESSED_DIR", "DATA_PROCESSED_DIR"],
    os.path.join(DATA_DIR, "processed"),
)
PROMPT_DIR = _env_first(
    ["LLMMUI_PROMPT_DIR", "PROMPT_DIR"],
    os.path.join(PROJECT_ROOT, "src", "configs", "prompt"),
)
SCENE_RULE_FILE = _env_first(
    ["LLMMUI_SCENE_RULE_FILE", "RULE_FILE"],
    os.path.join(PROJECT_ROOT, "src", "configs", "domain", "scene_permission_rules_task.json"),
)
PERMISSION_KNOWLEDGE_FILE = _env_first(
    ["LLMMUI_PERMISSION_KNOWLEDGE_FILE", "PERMISSION_KNOWLEDGE_FILE"],
    os.path.join(PROJECT_ROOT, "src", "configs", "domain", "permission_map.json"),
)

# =========================
# Phase1 runtime
# =========================
TIME_LIMIT = _env_int(["LLMMUI_FASTBOT_TIME_LIMIT", "TIME_LIMIT"], 15)
FASTBOT_THROTTLE = _env_int(["LLMMUI_FASTBOT_THROTTLE", "FASTBOT_THROTTLE"], 500)
ANDROID_DATA_DIR = _env_first(["LLMMUI_ANDROID_DATA_DIR", "ANDROID_DATA_DIR"], "/sdcard/fastbotOutput")
FASTBOT_OUTPUT_TEMPLATE = _env_first(
    ["LLMMUI_FASTBOT_OUTPUT_TEMPLATE", "FASTBOT_OUTPUT_TEMPLATE"],
    "fastbot-{package}--running-minutes-{time}",
)
# 0 means dynamic timeout: TIME_LIMIT * 60 + FASTBOT_TIMEOUT_BUFFER_SECONDS
FASTBOT_COMMAND_TIMEOUT_SECONDS = _env_int(
    ["LLMMUI_FASTBOT_COMMAND_TIMEOUT_SECONDS", "FASTBOT_COMMAND_TIMEOUT_SECONDS"],
    0,
)
FASTBOT_TIMEOUT_BUFFER_SECONDS = _env_int(
    ["LLMMUI_FASTBOT_TIMEOUT_BUFFER_SECONDS", "FASTBOT_TIMEOUT_BUFFER_SECONDS"],
    300,
)
ADB_PULL_TIMEOUT_SECONDS = _env_int(
    ["LLMMUI_ADB_PULL_TIMEOUT_SECONDS", "ADB_PULL_TIMEOUT_SECONDS"],
    300,
)

# =========================
# LLM runtime
# =========================
VLLM_TEXT_URL = _env_first(
    ["LLMMUI_VLLM_TEXT_URL", "VLLM_TEXT_URL", "LLMMUI_VLLM_URL"],
    "http://127.0.0.1:8011/v1/chat/completions",
)
VLLM_TEXT_MODEL = _resolve_vllm_model(
    ["LLMMUI_VLLM_TEXT_MODEL", "VLLM_TEXT_MODEL", "LLMMUI_MODEL_NAME"],
    "qwen-text-model",
    VLLM_TEXT_URL,
)

VLLM_VL_URL = _env_first(
    ["LLMMUI_VLLM_VL_URL", "VLLM_VL_URL"],
    "http://127.0.0.1:8010/v1/chat/completions",
)
VLLM_VL_MODEL = _resolve_vllm_model(
    ["LLMMUI_VLLM_VL_MODEL", "VLLM_VL_MODEL"],
    "qwen-vl-model",
    VLLM_VL_URL,
)
LLM_RESPONSE_TIMEOUT = _env_int(["LLMMUI_LLM_RESPONSE_TIMEOUT", "LLM_RESPONSE_TIMEOUT"], 120)
