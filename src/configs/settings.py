# -*- coding: utf-8 -*-
"""
Minimal runtime settings for llmui.
Override via environment variables when possible.
"""

import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# =========================
# Data paths
# =========================
DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
DATA_RAW_DIR = os.getenv("DATA_RAW_DIR", os.path.join(DATA_DIR, "raw"))
DATA_PROCESSED_DIR = os.getenv("DATA_PROCESSED_DIR", os.path.join(DATA_DIR, "processed"))

# =========================
# Phase1 (runtime)
# =========================
TIME_LIMIT = int(os.getenv("TIME_LIMIT", "20"))

# =========================
# LLM endpoints / models
# =========================
AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8011/v1")
AGENT_MODEL = os.getenv("AGENT_MODEL", "/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507")

VLLM_TEXT_URL = os.getenv("VLLM_TEXT_URL", "http://127.0.0.1:8011/v1/chat/completions")
VLLM_TEXT_MODEL = os.getenv("VLLM_TEXT_MODEL", "/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507")

VLLM_VL_URL = os.getenv("VLLM_VL_URL", "http://127.0.0.1:8011/v1/chat/completions")
VLLM_VL_MODEL = os.getenv("VLLM_VL_MODEL", "/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507")
