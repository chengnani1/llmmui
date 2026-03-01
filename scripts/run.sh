export HTTPX_LOG_LEVEL=warning
export LOGURU_LEVEL=WARNING

LLMMUI_AGENT_BASE_URL=http://127.0.0.1:8011/v1 \
LLMMUI_AGENT_MODEL=/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507 \
LLMMUI_VLLM_TEXT_URL=http://127.0.0.1:8011/v1/chat/completions \
LLMMUI_VLLM_TEXT_MODEL=/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507 \
python3 src/main.py agent /Users/charon/Downloads/llmui/data/processed --agent-instruction "执行完整三阶段分析"
