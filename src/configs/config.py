import os

__module_dir = os.path.dirname(os.path.abspath(__file__))
########## data_collect.py ##########
TIME_LIMIT = 20
THROTTLE = 500

ANDROID_DATA_DIR = "/sdcard/fastbotOutput"

FASTBOT_OUTPUT = "fastbot-{package}--running-minutes-{time}"

DATA_RAW_DIR = os.path.join(__module_dir, "..", "data", "version2.11", "raw")

DATA_PROCESSED_DIR = os.path.join(__module_dir, "..", "data", "version2.11.5", "processed")

FASTBOT_COMMAND = "CLASSPATH=/sdcard/monkeyq.jar:/sdcard/framework.jar:/sdcard/fastbot-thirdpart.jar exec app_process /system/bin com.android.commands.monkey.Monkey -p {package} --agent reuseq --running-minutes {time} --throttle {throttle} -v -v"

########## data_process.py ##########

########## data_analyze.py ##########
SERVER_IP = "127.0.0.1"    # 因为你的本地端口转发到了这里
SERVER_PORT = 8001         # 因为你的 vLLM 启动使用 --port 8001

CHAT_URL = f"http://{SERVER_IP}:{SERVER_PORT}/v1/chat/completions"
DEFAULT_MODEL = "Qwen2.5-7B"

# 一次场景分析时使用多少次大模型
SCENE_CLASSIFY_TIMES = 3
# 一次场景合规性判别使用多少次大模型
PERMISSION_NECESSITY_TIMES = 3
# 当大模型生成坏输出时最多重试的次数
MAX_RETRY_TIMES = 3
# 等待大模型相应的时间上限
LLM_RESPONSE_TIMEOUT = 120

# 场景分类prompt的路径
PROMPT_SCENE_CLASSIFY_PATH = os.path.join(__module_dir, "prompts", "scene_classify.txt")
# 权限必要性分析prompt的路径
PROMPT_PERMISSION_NECESSITY_PATH = os.path.join(__module_dir, "prompts", "permission_necessity.txt")
# 目的文本提取prompt的路径
PROMPT_PURPOSE_TEXTS_PATH = os.path.join(__module_dir, "prompts", "purpose_texts.txt")
# 权限使用目的分析prompt的路径
PROMPT_PERMISSION_USAGE_PATH = os.path.join(__module_dir, "prompts", "permission_usage.txt")
# 权限说明prompt的路径
PROMPT_PERMISSIONS_INFO_PATH = os.path.join(__module_dir, "prompts", "permissions_info.txt")
# 场景权限映射表的路径
PERMISSION_MAP_PATH = os.path.join(__module_dir, "permission_map.json")
