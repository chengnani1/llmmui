#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test local connection to vLLM via SSH tunnel.

Expected environment:
127.0.0.1:8011 -> SSH forwarded -> remote vLLM text model

Usage:
python scripts/test_vllm_local.py
"""

import requests
import time
import json
import os

PLACEHOLDER_MODELS = {"", "qwen-text-model", "qwen-vl-model", "auto", "default"}


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

URL_CHAT = os.getenv(
    "LLMMUI_VLLM_TEXT_URL",
    os.getenv(
        "VLLM_TEXT_URL",
        "http://127.0.0.1:29011/v1/chat/completions"
    )
)

URL_MODELS = os.getenv(
    "LLMMUI_VLLM_TEXT_MODELS_URL",
    os.getenv(
        "VLLM_MODELS_URL",
        _derive_models_url(URL_CHAT)
    )
)

MODEL = os.getenv(
    "LLMMUI_VLLM_TEXT_MODEL",
    os.getenv(
        "VLLM_TEXT_MODEL",
        "qwen-text-model"
    )
)

TIMEOUT = 30


def test_models():
    print("\n========== TEST /v1/models ==========")

    t0 = time.time()

    try:
        r = requests.get(URL_MODELS, timeout=TIMEOUT)
        latency = time.time() - t0

        print("status_code:", r.status_code)
        print("latency:", round(latency, 3), "s")

        data = r.json()

        print("models_found:", len(data.get("data", [])))

        for m in data.get("data", []):
            print("model_id:", m.get("id"))

        return True, data.get("data", [])

    except Exception as e:
        print("ERROR:", e)
        return False, []


def test_chat():
    print("\n========== TEST /v1/chat/completions ==========")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "Say only the word: pong"}
        ],
        "temperature": 0,
        "max_tokens": 8,
    }

    t0 = time.time()

    try:
        r = requests.post(URL_CHAT, json=payload, timeout=TIMEOUT)
        latency = time.time() - t0

        print("status_code:", r.status_code)
        print("latency:", round(latency, 3), "s")

        data = r.json()

        msg = data["choices"][0]["message"]["content"]

        print("model_reply:", msg.strip())

        return True

    except Exception as e:
        print("ERROR:", e)
        return False


def main():
    global MODEL
    print("========== vLLM LOCAL TEST ==========")
    print("models_url:", URL_MODELS)
    print("chat_url:", URL_CHAT)
    print("model:", MODEL)

    ok1, models = test_models()
    if MODEL.strip().lower() in PLACEHOLDER_MODELS and models:
        detected = str(models[0].get("id", "")).strip()
        if detected:
            MODEL = detected
            print("auto_detected_model:", MODEL)
    ok2 = test_chat()

    print("\n========== RESULT ==========")

    if ok1 and ok2:
        print("SUCCESS: vLLM reachable and responding")
    else:
        print("FAILED: check SSH tunnel or vLLM server")


if __name__ == "__main__":
    main()
