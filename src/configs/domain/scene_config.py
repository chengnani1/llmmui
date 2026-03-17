# -*- coding: utf-8 -*-
import os

# ===========================
# 13+1 个任务导向预定义场景（权限合规分析口径）
# ===========================
SCENE_LIST = [
    "账号与身份认证",
    "地图与位置服务",
    "内容浏览与搜索",
    "社交互动与通信",
    "音频录制与创作",
    "图像视频拍摄与扫码",
    "相册选择与媒体上传",
    "商品浏览与消费",
    "支付与金融交易",
    "文件与数据管理",
    "设备清理与系统优化",
    "网络连接与设备管理",
    "用户反馈与客服",
    "其他",
]

SCENE_DEFINITIONS = {
    "账号与身份认证": [
        "登录、注册、验证码、账号绑定、身份校验、密码重置、首次进入认证流程",
    ],
    "地图与位置服务": [
        "地图展示、当前位置、路线导航、附近门店/服务、基于位置发现",
    ],
    "内容浏览与搜索": [
        "浏览信息流、网页、搜索结果、列表页，以阅读和检索为主",
    ],
    "社交互动与通信": [
        "聊天、私信、群聊、语音/视频通话、好友互动、社交表达",
    ],
    "音频录制与创作": [
        "录音、清唱、K歌、配音、语音创作、音频作品录制，以麦克风采集或音频创作为核心任务",
    ],
    "图像视频拍摄与扫码": [
        "调用相机拍照/录像/扫码，采集二维码、图像或视频信息，以摄像头采集为核心任务",
    ],
    "相册选择与媒体上传": [
        "从相册选择已有图片/视频，用于上传头像、发帖、反馈或发送媒体",
    ],
    "商品浏览与消费": [
        "商品浏览、购物车、下单流程、优惠活动、消费决策页面",
    ],
    "支付与金融交易": [
        "支付、转账、收款、充值、钱包、账单确认、交易验证",
    ],
    "文件与数据管理": [
        "浏览/上传/下载/选择 PDF、DOC、ZIP 等文件对象，或数据导入导出",
    ],
    "设备清理与系统优化": [
        "清理缓存、释放存储、加速优化、电量管理、系统维护任务",
    ],
    "网络连接与设备管理": [
        "Wi-Fi/蓝牙/热点/设备连接管理、网络设置、外设控制",
    ],
    "用户反馈与客服": [
        "问题反馈、工单提交、在线客服、帮助中心、投诉建议",
    ],
    "其他": [
        "仅在文本极少、上下文缺失、任务目标无法判断时使用",
    ],
}

SCENE_DECISION_RULES = [
    "以用户当前页面任务为最高优先级，不按 APP 行业、应用名称或品牌做分类。",
    "这是页面任务分类，不是权限类型识别；不要把权限名称本身当成场景标签。",
    "若页面语义可判定，不得优先输出“其他”。",
    "音频录制与创作 与 图像视频拍摄与扫码：前者以麦克风采集/音频创作为核心，后者以摄像头采集为核心。",
    "图像视频拍摄与扫码 与 相册选择与媒体上传：前者是实时拍摄/扫码采集，后者是选择已有媒体。",
    "文件与数据管理 与 相册选择与媒体上传：前者对象是文档/数据文件，后者对象是图片/视频内容表达。",
    "内容浏览与搜索 与 商品浏览与消费：前者以信息检索为主，后者以商品决策/购买为主。",
    "设备清理与系统优化 与 网络连接与设备管理：前者是清理/优化任务，后者是网络/设备连接控制。",
    "账号登录、验证码、绑定/重置账号页面优先归为账号与身份认证。",
    "地图、定位、附近、导航等语义优先归为地图与位置服务。",
    "聊天、私信、通话、好友互动优先归为社交互动与通信。",
    "当页面核心任务为录音、清唱、K歌、配音、语音创作、音频作品录制时，优先归为音频录制与创作。",
    "不要把音频录制页面默认归到图像视频拍摄与扫码，也不要在可判定时归到“其他”。",
    "反馈、客服、帮助中心页面优先归为用户反馈与客服。",
    "“其他”仅在页面文本极少、上下文缺失或任务目标无法判断时使用。",
]

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

def load_scene_prompt_template() -> str:
    with open(PROMPT_SCENE_CLASSIFY_PATH, 'r', encoding='utf-8') as f:
        return f.read().strip()

SCENE_PROMPT_TEMPLATE = load_scene_prompt_template()


def format_scene_list() -> str:
    return "\n".join(f"- {scene}" for scene in SCENE_LIST)


def format_scene_definitions() -> str:
    lines = []
    for idx, scene in enumerate(SCENE_LIST, 1):
        lines.append(f"{idx}. {scene}：")
        for desc in SCENE_DEFINITIONS.get(scene, []):
            lines.append(f"   - {desc}")
        lines.append("")
    return "\n".join(lines).strip()


def format_scene_rules() -> str:
    return "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(SCENE_DECISION_RULES, 1))


def build_scene_prompt(feature: str) -> str:
    prompt = SCENE_PROMPT_TEMPLATE
    prompt = prompt.replace("{FEATURE}", feature)
    prompt = prompt.replace("{SCENE_LIST}", format_scene_list())
    prompt = prompt.replace("{SCENE_DEFINITIONS}", format_scene_definitions())
    prompt = prompt.replace("{SCENE_RULES}", format_scene_rules())
    return prompt
