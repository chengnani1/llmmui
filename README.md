# llmui

`llmui` 是一个面向 Android 权限交互链的分阶段分析工程。当前归档上传版本只保留现行主链：`phase1 -> phase2 -> phase3_v2`。旧版 phase3、历史实验脚本、备份脚本和敏感测试文件已经从本仓库清理。

当前主链固定输出：

1. `result_permission.json`
2. `result_semantic_v2.json`
3. `result_retrieved_knowledge.json`
4. `result_llm_review.json`
5. `result_final_decision.json`

## 1. 归档说明

这个归档版本的目标是：

- 保留可运行、可复现的 `phase3_v2` 主流程
- 保留当前仍有价值的评估和知识迭代脚本
- 删除旧 phase3 链路、废弃本地工具、明文密钥和强机器绑定脚本

清理范围和保留边界见：

- `docs/ARCHIVE_UPLOAD_NOTES.md`

## 2. 目录结构

- `src/`：当前主流程代码
- `scripts/experiments/`：当前保留的实验、评估、知识迭代脚本
- `scripts/utils/`：当前保留的通用工具
- `docs/`：工作流、代码结构和归档说明
- `data/`：默认数据目录（被 `.gitignore` 忽略，不随仓库上传）
- `run_full_pipeline.sh`：统一运行入口封装

## 3. 环境要求

- Python `3.9+`
- ADB / Android 设备环境（`phase1` 需要）
- Tesseract OCR（`phase2` 需要）
- OpenAI-compatible vLLM 接口（`phase3_v2` 需要）

安装依赖：

```bash
pip install -r requirements.txt
```

## 4. 配置方式

运行配置集中在 `src/configs/settings.py`。推荐使用环境变量，不要修改源码内默认值。

最常用的环境变量见 `.env.example`：

- `LLMMUI_DATA_ROOT`
- `LLMMUI_RAW_DIR`
- `LLMMUI_PROCESSED_DIR`
- `LLMMUI_PROMPT_DIR`
- `LLMMUI_SCENE_RULE_FILE`
- `LLMMUI_PERMISSION_KNOWLEDGE_FILE`
- `LLMMUI_VLLM_TEXT_URL`
- `LLMMUI_VLLM_TEXT_MODEL`
- `LLMMUI_VLLM_VL_URL`
- `LLMMUI_VLLM_VL_MODEL`

如果通过本地端口访问远端 vLLM，建议额外设置：

```bash
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
```

## 5. 主流程入口

统一入口是 `src/main.py`，当前只支持这些模式：

- `full`
- `phase1`
- `phase2`
- `phase3_v2`
- `phase3_v2_compliance`
- `phase3_v2_final`

### 5.1 全流程

```bash
python3 src/main.py full <apk_or_apk_dir> \
  --raw-root <raw_root> \
  --processed-root <processed_root> \
  --force
```

### 5.2 完整 `phase3_v2`

```bash
python3 src/main.py phase3_v2 <processed_root> --force
```

### 5.3 只重跑后半段

```bash
python3 src/main.py phase3_v2_compliance <processed_root> --force
python3 src/main.py phase3_v2_final <processed_root> --force
```

### 5.4 指定 app / 指定 chain

```bash
python3 src/main.py phase3_v2_compliance <processed_root> \
  --app <APP_DIR_NAME> \
  --chain-ids 0,1,2 \
  --force

python3 src/main.py phase3_v2_final <processed_root> \
  --app <APP_DIR_NAME> \
  --chain-ids 0,1,2 \
  --force
```

## 6. 一键脚本

`run_full_pipeline.sh` 对主入口做了轻封装：

```bash
bash run_full_pipeline.sh <mode> <target> [extra main.py args...]
```

支持的 `mode`：

- `full`
- `phase1`
- `phase2`
- `phase3_v2`
- `phase3_v2_compliance`
- `phase3_v2_final`
- `phase3_v2_post`

示例：

```bash
bash run_full_pipeline.sh phase3_v2 /path/to/processed --force
bash run_full_pipeline.sh phase3_v2_post /path/to/processed --app APP --force
```

## 7. `phase3_v2` 输入输出

每个 app 目录至少需要：

- `result.json`
- `chain_*.png`

`phase3_v2` 的主链输出是：

- `result_permission.json`
- `result_semantic_v2.json`
- `result_retrieved_knowledge.json`
- `result_llm_review.json`
- `result_final_decision.json`
- `phase3_v2_summary.json`

语义输出最小 schema：

```json
[
  {
    "chain_id": 0,
    "page_description": "...",
    "page_function": "...",
    "user_goal": "...",
    "scene": {
      "ui_task_scene": "...",
      "refined_scene": "...",
      "confidence": 0.0
    }
  }
]
```

最终输出 `result_final_decision.json` 是纯映射结果，不再做旧规则链翻盘。

## 8. 当前保留的评估与迭代脚本

主评估：

```bash
python3 scripts/experiments/evaluate_label_judge_binary.py \
  /path/to/processed \
  --pred-file result_final_decision.json \
  --review-as risk \
  --app-prefix fastbot- \
  --output judge_binary_metrics.json
```

常用知识迭代脚本：

- `scripts/experiments/iterate_knowledge_from_errors.py`
- `scripts/experiments/update_structured_knowledge_from_errors.py`
- `scripts/experiments/lint_structured_knowledge.py`
- `scripts/experiments/run_knowledge_iteration_loop.py`

主知识文件：

- `src/configs/scene_structured_knowledge.json`
- `src/configs/domain/permission_map.json`
- `src/configs/domain/scene_permission_rules_task.json`

## 9. 提示词

当前主流程只使用两个提示词：

- `src/configs/prompt/chain_semantic_interpreter_vision.txt`
- `src/configs/prompt/llm_single_pass_compliance.txt`

## 10. 相关文档

- `docs/ARCHIVE_UPLOAD_NOTES.md`
- `docs/ASE_WORKFLOW.md`
- `docs/PROJECT_CODEBASE_REPORT.md`
- `docs/DATASET_CLEANUP_REPORT.md`
