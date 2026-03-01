# -*- coding: utf-8 -*-
import os

# ===========================
# 16 个预定义场景（最终版）
# ===========================
SCENE_LIST = [
    "地图与出行",
    "即时通信",
    "音视频内容",
    "文件与存储",
    "账号与登录",
    "支付与金融",
    "电商与消费",
    "信息浏览",
    "游戏娱乐",
    "医疗健康",
    "工具与系统",
    "个人信息",
    "设备与硬件",
    "学习教育",
    "其他"
]

# ===========================
# 场景识别 Prompt（v5 · 16-class）
# ===========================

# ===========================
# 本地 LLM 配置
# ===========================
from configs import settings

VLLM_URL = settings.VLLM_TEXT_URL
MODEL_NAME = settings.VLLM_TEXT_MODEL

# ===========================
# 超参数
# ===========================
MAX_STEPS = 10         # before + granting + after 最大帧数
MAX_WIDGETS = 20       # 每帧最多 widgets
MAX_TEXT_LEN = 4000    # 单段文本上限
MAX_TOTAL_LEN = 30000  # 输入给 LLM 的安全上限


PROMPT_SCENE_CLASSIFY_PATH = os.path.join(os.path.dirname(__file__), '..', 'prompt', 'scene_classify.txt')

def load_scene_prompt() -> str:
    with open(PROMPT_SCENE_CLASSIFY_PATH, 'r', encoding='utf-8') as f:
        return f.read().strip()

SCENE_PROMPT = load_scene_prompt()
