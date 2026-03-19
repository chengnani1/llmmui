# -*- coding: utf-8 -*-
"""
Alias entrypoint for UI task scene classification from semantics.
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analy_pipline.scene import run_scene_from_semantics_text  # noqa: E402
from configs import settings  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UI task scene classification from chain semantics")
    parser.add_argument("target", help="processed root or one app dir")
    parser.add_argument("--prompt-file", default=os.path.join(settings.PROMPT_DIR, "scene_from_semantics_text.txt"))
    parser.add_argument("--vllm-url", default=os.getenv("VLLM_TEXT_URL", settings.VLLM_TEXT_URL))
    parser.add_argument("--model", default=os.getenv("VLLM_TEXT_MODEL", settings.VLLM_TEXT_MODEL))
    args = parser.parse_args()
    run_scene_from_semantics_text.run(args.target, args.prompt_file, args.vllm_url, args.model)
