export HTTPX_LOG_LEVEL=warning
export LOGURU_LEVEL=WARNING

AGENT_BASE_URL=http://127.0.0.1:8011/v1 \
AGENT_MODEL=/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507 \
VLLM_TEXT_URL=http://127.0.0.1:8011/v1/chat/completions \
VLLM_TEXT_MODEL=/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507 \
python3 src/main.py agent /Users/charon/Downloads/llmui/data/processed --agent-instruction "执行完整三阶段分析"
