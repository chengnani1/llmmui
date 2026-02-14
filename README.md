## llmui

本项目是一个 Android 权限场景分析流水线（科研工具形态），包含三大阶段：
1) Phase1：APK 数据采集（fastbot / adb）
2) Phase2：数据处理与权限链构建
3) Phase3：场景识别、权限推断、规则裁决、合规分析（可选 LangGraph 智能体编排）

---

## 目录结构（主干）

```
src/
  main.py                          # 统一入口（推荐）
  configs/
    settings.py                    # 运行配置（路径/模型/端口）
    domain/                         # 权限/场景/规则等“知识表”
      scene_config.py              # 场景列表与参数（prompt 从 prompt/ 读取）
      permission_config.py         # 权限集合与映射规则
      permission_map.json
      permission_map_en.json
      scene_permission_rules_16.json
    prompt/                         # 所有提示词
      scene_classify.txt
      permission_necessity.txt
      scene_consistency.txt
      finaly_analy.txt
  data_pipline/
    data_collect.py                # Phase1
    data_process.py                # Phase2
  analy_pipline/
    scene/                          # 场景识别
    permission/                     # 权限推断
    judge/                          # 规则裁决 / 合规分析
    agent/phase3_agent.py           # Phase3 智能体入口
data/
  raw/                              # 原始 fastbot 输出
  processed/                        # 处理后结构化数据
scripts/
  experiments/                      # 实验与评估脚本（不影响主流程）
```

---

## 环境要求

- Python 3.9+
- vLLM（或任何 OpenAI-compatible 接口）
- Android 设备 + adb

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 配置说明（强烈建议通过环境变量覆盖）

统一配置在 `src/configs/settings.py`，支持环境变量覆盖（核心运行参数）：

```
DATA_DIR
DATA_RAW_DIR
DATA_PROCESSED_DIR
TIME_LIMIT
AGENT_BASE_URL
AGENT_MODEL
VLLM_TEXT_URL
VLLM_TEXT_MODEL
VLLM_VL_URL
VLLM_VL_MODEL
```

示例（本地 vLLM）：

```bash
export DATA_PROCESSED_DIR=/Users/charon/Downloads/llmui/data/processed
export VLLM_TEXT_URL=http://127.0.0.1:8001/v1/chat/completions
export VLLM_VL_URL=http://127.0.0.1:8002/v1/chat/completions
```

---

## 统一入口（推荐）

### 1) 全流程（Phase1 + Phase2 + Phase3）

```bash
python3 src/main.py full /path/to/apk_or_dir \
  --scene-mode text
```

### 2) 只运行 Phase1（采集）

```bash
python3 src/main.py phase1 /path/to/apk_or_dir
```

### 3) 只运行 Phase2（处理）

```bash
python3 src/main.py phase2 /path/to/raw_root \
  --processed-root /path/to/processed_root
```

### 4) 只运行 Phase3（分析）

```bash
python3 src/main.py phase3 /path/to/processed_root \
  --scene-mode text
```

如果不需要合规分析：

```bash
python3 src/main.py phase3 /path/to/processed_root --no-compliance
```

### 5) 用智能体编排 Phase3

```bash
python3 src/main.py agent /path/to/processed_root \
  --agent-instruction "执行完整三阶段分析"
```

---

## Phase3 产出文件

每个 APK 目录内：

- `results_scene_llm.json` 或 `results_scene_vllm.json`
- `result_permission_llm.json` 或 `result_permission_rule.json`
- `result_rule_judgement.json`
- `result_llm_compliance_v3.json`（可选）
- `result_final_decision.json`（智能体后处理：冲突回滚与最终裁决）

---

## 模块逻辑概览

- **Phase1（采集）**  
  `data_pipline/data_collect.py` 使用 adb + fastbot，输出 raw 目录（fastbot-*）。

- **Phase2（处理）**  
  `data_pipline/data_process.py` 读取 raw 数据，构建 permission chain，生成 `result.json` 与合并图片。

- **Phase3（分析）**  
  - 场景识别：`analy_pipline/scene/run_scene_llm.py` 或 `run_scene_vllm.py`  
  - 权限推断：`analy_pipline/permission/run_permission_llm_only.py` 或 `run_permission_rule_only.py`  
  - 规则裁决：`analy_pipline/judge/run_rule_judgement.py`  
  - 合规分析：`analy_pipline/judge/run_llm_compliance.py`

- **智能体编排**  
  `analy_pipline/agent/phase3_agent.py` 使用 LangGraph 调度 Phase3 各步骤。

---

## 常见问题

1) **端口不一致 / 连接失败**  
检查 `VLLM_TEXT_URL` / `VLLM_VL_URL` 是否与 vLLM 启动端口一致。

2) **找不到数据目录**  
确认 `DATA_RAW_DIR` / `DATA_PROCESSED_DIR` 路径正确并存在。

3) **Phase2 无输出**  
检查 raw 目录下是否存在 `fastbot-*` 输出，且包含 `tupleOfPermissions.json`。

---

## 开发建议

- 路径和端口只在 `settings.py` 或环境变量中配置，避免散落硬编码。
- Phase3 各模块是独立脚本，可单独运行用于调试。
 - 实验脚本集中放在 `scripts/experiments/`，不影响主流程。
