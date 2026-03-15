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

URL_MODELS = os.getenv(
    "VLLM_MODELS_URL",
    "http://127.0.0.1:8011/v1/models"
)

URL_CHAT = os.getenv(
    "VLLM_TEXT_URL",
    "http://127.0.0.1:8011/v1/chat/completions"
)

MODEL = os.getenv(
    "VLLM_TEXT_MODEL",
    "/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507"
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

        return True

    except Exception as e:
        print("ERROR:", e)
        return False


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
    print("========== vLLM LOCAL TEST ==========")
    print("models_url:", URL_MODELS)
    print("chat_url:", URL_CHAT)
    print("model:", MODEL)

    ok1 = test_models()
    ok2 = test_chat()

    print("\n========== RESULT ==========")

    if ok1 and ok2:
        print("SUCCESS: vLLM reachable and responding")
    else:
        print("FAILED: check SSH tunnel or vLLM server")


if __name__ == "__main__":
    main()