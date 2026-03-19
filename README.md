# llmui (Stabilized Phase3_v2)

本仓库已收敛为一个可复现实验版本，主目标是：

- 从 UI 权限交互链中生成语义中间表示
- 基于场景知识检索 + 单次 LLM 判定完成合规分析
- 输出统一的最终风险标签

当前主链已固定为：

1. `result_permission.json`（规则权限识别）
2. `result_semantic_v2.json`（VLM 语义识别）
3. `result_retrieved_knowledge.json`（结构化知识检索）
4. `result_llm_review.json`（单次 LLM 判定）
5. `result_final_decision.json`（纯标签映射）

## 1. 目录结构（定版后）

- `src/`：工程主流程代码（生产链）
- `scripts/`：实验、评估、知识迭代、历史/归档脚本
- `data/`：`raw`/`processed` 数据目录
- `run_full_pipeline.sh`：统一运行脚本（支持全流程和分阶段）

历史实验代码、旧版规则链路、备份提示词/脚本已迁移到：

- `scripts/experiments/legacy_from_src/`
- `scripts/archive/src_backups/`

## 1.1 data/processed 清理

已新增清理脚本（迁移归档，不直接硬删）：

```bash
python3 scripts/utils/cleanup_processed_unused.py /path/to/data/processed
```

清理说明与保留白名单见：

- `docs/DATASET_CLEANUP_REPORT.md`

## 2. 环境要求

- Python `3.9+`
- ADB / Android 设备环境（Phase1 需要）
- Tesseract OCR（Phase2 需要）
- OpenAI-compatible vLLM 接口（Phase3 需要）

安装依赖：

```bash
pip install -r requirements.txt
```

## 3. 关键配置

配置文件：`src/configs/settings.py`

常用环境变量：

- `LLMMUI_DATA_ROOT`
- `LLMMUI_RAW_DIR`
- `LLMMUI_PROCESSED_DIR`
- `LLMMUI_PROMPT_DIR`
- `LLMMUI_VLLM_TEXT_URL`
- `LLMMUI_VLLM_TEXT_MODEL`
- `LLMMUI_VLLM_VL_URL`
- `LLMMUI_VLLM_VL_MODEL`
- `LLMMUI_SCENE_STRUCTURED_KNOWLEDGE_FILE`

如果你通过 SSH 隧道访问远端 vLLM（示例）：

```bash
ssh -f -N -L 29011:127.0.0.1:18011 -L 29010:127.0.0.1:18010 a100
```

建议运行时使用：

```bash
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
```

## 4. 主流程命令

统一入口：`src/main.py`

### 4.1 全流程（phase1+phase2+phase3_v2）

```bash
python3 src/main.py full <apk_or_apk_dir> \
  --raw-root <raw_root> \
  --processed-root <processed_root> \
  --force
```

### 4.2 仅跑 Phase3_v2（完整后半链）

```bash
python3 src/main.py phase3_v2 <processed_root> --force
```

### 4.3 跳过语义，重跑后半段（推荐知识迭代）

```bash
python3 src/main.py phase3_v2_compliance <processed_root> --force
python3 src/main.py phase3_v2_final <processed_root> --force
```

### 4.4 指定 app / 指定 chain

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

## 5. 一键脚本（全流程 + 分阶段）

`run_full_pipeline.sh` 提供统一封装：

```bash
bash run_full_pipeline.sh <mode> <target> [extra main.py args...]
```

可用 `mode`：

- `full`
- `phase1`
- `phase2`
- `phase3_v2`
- `phase3_v2_compliance`
- `phase3_v2_final`
- `phase3_v2_post`（即 compliance + final）

示例：

```bash
bash run_full_pipeline.sh phase3_v2 /path/to/processed --force
bash run_full_pipeline.sh phase3_v2_post /path/to/processed --app APP --force
```

## 6. Phase3_v2 输入输出与 Schema

### 6.1 输入

每个 app 目录至少需要：

- `result.json`（Phase2 产出）
- `chain_*.png`
- `result_permission.json`（phase3_v2 会自动生成或复用）

### 6.2 语义输出：`result_semantic_v2.json`

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

### 6.3 检索输出：`result_retrieved_knowledge.json`

每条记录包含：

- `chain_id`
- `ui_task_scene` / `refined_scene`
- `permissions`
- `retrieved_knowledge`：
  - `retrieved_rules`
  - `retrieval_diagnostics`
  - `conflict_detected`
  - `coverage_score` 等诊断字段

### 6.4 LLM 输出：`result_llm_review.json`

核心字段：

- `necessity`
- `consistency`
- `over_scope`
- `final_decision`（`compliant|suspicious|non_compliant`）
- `final_risk`（`low|medium|high`）
- `confidence`
- `analysis_summary`
- `supporting_refs` / `conflicting_refs`
- `evidence_sufficiency`

### 6.5 最终输出：`result_final_decision.json`

纯映射结果（无额外规则翻盘）：

- `final_decision`：
  - `compliant -> CLEARLY_OK`
  - `suspicious -> NEED_REVIEW`
  - `non_compliant -> CLEARLY_RISKY`
- `final_risk`：
  - `low -> LOW`
  - `medium -> MEDIUM`
  - `high -> HIGH`

并保留：

- `ui_task_scene` / `refined_scene`
- `permissions`
- `necessity` / `consistency` / `over_scope`
- `confidence`
- `analysis_summary`

## 7. 评估命令（当前主评估）

二分类风险评估：

```bash
python3 scripts/experiments/evaluate_label_judge_binary.py \
  /path/to/processed \
  --pred-file result_final_decision.json \
  --review-as risk \
  --app-prefix fastbot- \
  --output judge_binary_metrics.json
```

## 8. 知识迭代（错例驱动）

常用脚本：

- `scripts/experiments/iterate_knowledge_from_errors.py`
- `scripts/experiments/update_structured_knowledge_from_errors.py`
- `scripts/experiments/lint_structured_knowledge.py`

主知识库文件：

- `src/configs/scene_structured_knowledge.json`

建议流程：

1. 跑评估拿错例
2. 聚类错例模式
3. 更新结构化知识
4. lint 检查
5. 重跑 `phase3_v2_compliance + phase3_v2_final`
6. 再评估对比

## 9. 提示词

当前主流程仅使用两个提示词：

- `src/configs/prompt/chain_semantic_interpreter_vision.txt`
- `src/configs/prompt/llm_single_pass_compliance.txt`

## 10. 论文工作流文档

详细的 ASE 写作导向工作流见：

- `docs/ASE_WORKFLOW.md`
- `docs/PROJECT_CODEBASE_REPORT.md`
