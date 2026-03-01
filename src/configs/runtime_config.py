from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from configs import settings


PROJECT_ROOT = settings.PROJECT_ROOT
DATA_ROOT = settings.DATA_DIR
RAW_DIR = settings.DATA_RAW_DIR
PROCESSED_DIR = settings.DATA_PROCESSED_DIR
PROMPT_DIR = settings.PROMPT_DIR

DEFAULT_VLLM_URL = settings.VLLM_TEXT_URL
DEFAULT_MODEL_NAME = settings.VLLM_TEXT_MODEL

FASTBOT_TIME_LIMIT = settings.TIME_LIMIT
FASTBOT_THROTTLE = settings.FASTBOT_THROTTLE
ANDROID_DATA_DIR = settings.ANDROID_DATA_DIR
FASTBOT_OUTPUT_TEMPLATE = settings.FASTBOT_OUTPUT_TEMPLATE
FASTBOT_COMMAND_TIMEOUT_SECONDS = settings.FASTBOT_COMMAND_TIMEOUT_SECONDS
FASTBOT_TIMEOUT_BUFFER_SECONDS = settings.FASTBOT_TIMEOUT_BUFFER_SECONDS
ADB_PULL_TIMEOUT_SECONDS = settings.ADB_PULL_TIMEOUT_SECONDS
LLM_RESPONSE_TIMEOUT = settings.LLM_RESPONSE_TIMEOUT


@dataclass(frozen=True)
class RuntimeConfig:
    project_root: str
    data_root: str
    raw_dir: str
    processed_dir: str
    prompt_dir: str
    default_vllm_url: str
    default_model_name: str
    fastbot_time_limit: int
    fastbot_throttle: int
    android_data_dir: str
    fastbot_output_template: str
    fastbot_command_timeout_seconds: int
    fastbot_timeout_buffer_seconds: int
    adb_pull_timeout_seconds: int
    llm_response_timeout: int


RUNTIME = RuntimeConfig(
    project_root=PROJECT_ROOT,
    data_root=DATA_ROOT,
    raw_dir=RAW_DIR,
    processed_dir=PROCESSED_DIR,
    prompt_dir=PROMPT_DIR,
    default_vllm_url=DEFAULT_VLLM_URL,
    default_model_name=DEFAULT_MODEL_NAME,
    fastbot_time_limit=FASTBOT_TIME_LIMIT,
    fastbot_throttle=FASTBOT_THROTTLE,
    android_data_dir=ANDROID_DATA_DIR,
    fastbot_output_template=FASTBOT_OUTPUT_TEMPLATE,
    fastbot_command_timeout_seconds=FASTBOT_COMMAND_TIMEOUT_SECONDS,
    fastbot_timeout_buffer_seconds=FASTBOT_TIMEOUT_BUFFER_SECONDS,
    adb_pull_timeout_seconds=ADB_PULL_TIMEOUT_SECONDS,
    llm_response_timeout=LLM_RESPONSE_TIMEOUT,
)


def list_fastbot_dirs(root_dir: str) -> List[str]:
    if not os.path.isdir(root_dir):
        return []
    return [
        os.path.join(root_dir, d)
        for d in sorted(os.listdir(root_dir))
        if d.startswith("fastbot-") and os.path.isdir(os.path.join(root_dir, d))
    ]
