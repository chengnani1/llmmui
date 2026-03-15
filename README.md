# llmui

Android 权限交互链分析工具（科研实验版），整体分为 3 个阶段：
1. `Phase1`：数据采集（`adb + fastbot`）
2. `Phase2`：数据处理（OCR + 结构化链路 `result.json`）
3. `Phase3`：合规分析（规则先验 + 分解式 LLM + 轻量仲裁）

---

## 1. 环境与依赖

- Python `3.9+`
- Android `adb`
- fastbot 运行环境
- tesseract OCR（Phase2 需要）
- OpenAI-compatible LLM 接口（推荐 vLLM）

```bash
pip install -r requirements.txt
```

---

## 2. 核心配置

统一配置入口：`src/configs/settings.py`（支持 `LLMMUI_*` 环境变量覆盖）

常用变量：
- `LLMMUI_DATA_ROOT` / `LLMMUI_RAW_DIR` / `LLMMUI_PROCESSED_DIR`
- `LLMMUI_SCENE_RULE_FILE`
- `LLMMUI_PROMPT_DIR`
- `LLMMUI_VLLM_TEXT_URL` / `LLMMUI_VLLM_TEXT_MODEL`
- `LLMMUI_VLLM_VL_URL` / `LLMMUI_VLLM_VL_MODEL`
- `LLMMUI_LLM_RESPONSE_TIMEOUT`

示例：

```bash
export LLMMUI_PROCESSED_DIR=/Users/charon/Downloads/llmui/data/processed
export LLMMUI_VLLM_TEXT_URL=http://127.0.0.1:8011/v1/chat/completions
export LLMMUI_VLLM_TEXT_MODEL=/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507
export LLMMUI_VLLM_VL_URL=http://127.0.0.1:8011/v1/chat/completions
export LLMMUI_VLLM_VL_MODEL=/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507
```

场景配置统一在 [scene_config.py](/Users/charon/Downloads/llmui/src/configs/domain/scene_config.py)：
- `SCENE_LIST`：12+1 个预定义任务场景（唯一标签源）
- `SCENE_DEFINITIONS`：每个场景的释义
- `SCENE_DECISION_RULES`：场景判定规则

`scene_classify.txt` 只保留模板，场景列表与释义由 config 注入，避免 prompt 和代码口径漂移。

当前任务导向 scene taxonomy（12+1）：
- 账号与身份认证
- 地图与位置服务
- 内容浏览与搜索
- 社交互动与通信
- 媒体拍摄与扫码
- 相册选择与媒体上传
- 商品浏览与消费
- 支付与金融交易
- 文件与数据管理
- 设备清理与系统优化
- 网络连接与设备管理
- 用户反馈与客服
- 其他

---

## 3. 统一入口命令

入口文件：`src/main.py`

### 3.1 全流程

```bash
python3 src/main.py full /path/to/apk_or_apk_dir --scene-mode text
```

### 3.2 只跑某个阶段

```bash
python3 src/main.py phase1 /path/to/apk_or_apk_dir
python3 src/main.py phase2 /path/to/raw_root --processed-root /path/to/processed_root
python3 src/main.py phase3 /path/to/processed_root --scene-mode text
```

关闭 Phase3 的 LLM 复核（仅规则）：

```bash
python3 src/main.py phase3 /path/to/processed_root --scene-mode text --no-compliance
```

说明：即使关闭 LLM 复核，仍会输出 `result_final_decision.json`，并基于规则结果回退生成最终风险结论。

### 3.3 Phase3 工作流模式（推荐用于论文主实验）

```bash
python3 src/main.py phase3 /path/to/processed_root --scene-mode text
```

视觉场景模式：

```bash
python3 src/main.py phase3 /path/to/processed_root --scene-mode vision
```

### 3.4 Task13 场景实验脚本（text / vision）

```bash
# text 版本
python3 src/analy_pipline/scene/run_scene_task13_text.py /path/to/processed_root

# vision 版本
python3 src/analy_pipline/scene/run_scene_task13_vision.py /path/to/processed_root
```

实验输出（每个 app）：
- `result_scene_task13_text.json`
- `result_scene_task13_vision.json`

实验汇总输出（target 目录）：
- `scene_task13_text_summary.json`
- `scene_task13_vision_summary.json`

---

## 4. Phase3 方法结构（对应论文 3.4）

Phase3 实现为固定流水线，而非多代理辩论：

1. `3.4.1` 场景识别与用户目的推断  
   - `scene/run_chain_semantic_interpreter.py`（视觉语义中间层）
   - `scene/run_scene_from_semantics_text.py`（文本映射）
   - `scene/run_scene_vllm.py`（视觉直推基线，可选）
2. `3.4.2` 基于规则的先验风险评估  
   - `permission/run_permission_rule.py`
   - `judge/run_rule_judgement.py`
3. `3.4.3` 基于 LLM 的分解式合规复核  
   - `judge/run_llm_compliance.py`
   - 三阶段：`Necessity -> Consistency -> Minimality/Final`
4. `3.4.4` 冲突仲裁与最终判定  
   - `judge/finalize_decision.py`
   - 负责冲突处理、回滚、输出最终结论

---

## 5. Phase3 输出文件（每个 app 目录）

主输出（新口径）：
- `result_chain_semantics.json`
- `result_ui_task_scene.json`
- `result_permission.json`
- `result_regulatory_scene.json`
- `result_rule_screening.json`
- `result_llm_review.json`（只含 `MEDIUM_RISK/HIGH_RISK` 链）
- `result_final_decision.json`

---

## 6. 固定 Schema（论文统计建议使用）

### 6.1 场景识别 `result_ui_task_scene.json`

```json
{
  "chain_id": 0,
  "predicted_scene": "地图与位置服务",
  "scene_top3": ["地图与位置服务", "内容浏览与搜索", "商品浏览与消费"],
  "intent": "用户希望查看附近门店并获取当前位置",
  "confidence": "high",
  "rerun": false,
  "rerun_reason": ""
}
```

### 6.2 权限识别 `result_permission.json`

```json
{
  "chain_id": 0,
  "predicted_permissions": ["ACCESS_FINE_LOCATION"],
  "permission_source": "rule",
  "files": {
    "before": "step-1.png",
    "granting": ["step-2.png"],
    "after": "step-3.png"
  }
}
```

### 6.3 规则筛选 `result_rule_screening.json`

```json
{
  "chain_id": 0,
  "scene": "地图与位置服务",
  "scene_top3": ["地图与位置服务", "内容浏览与搜索", "商品浏览与消费"],
  "intent": "用户查看附近门店",
  "permissions": ["ACCESS_FINE_LOCATION"],
  "permission_decisions": {"ACCESS_FINE_LOCATION": "CLEARLY_ALLOWED"},
  "overall_rule_signal": "LOW_RISK",
  "matched_rules": [
    {
      "permission": "ACCESS_FINE_LOCATION",
      "decision": "CLEARLY_ALLOWED",
      "evidence": "ACCESS_FINE_LOCATION in clearly_allowed for scene=地图与位置服务"
    }
  ]
}
```

### 6.4 LLM 复核 `result_llm_review.json`

```json
{
  "chain_id": 0,
  "scene": "设备清理与系统优化",
  "intent": "清理缓存",
  "permissions": ["READ_CONTACTS"],
  "rule_signal": "HIGH_RISK",
  "necessity_analysis": {"label": "unnecessary", "reason": "..."},
  "consistency_analysis": {"label": "inconsistent", "reason": "..."},
  "minimality_analysis": {"label": "over_privileged", "reason": "..."},
  "llm_final_decision": "NON_COMPLIANT",
  "llm_final_risk": "HIGH",
  "llm_explanation": "...",
  "output_valid": true,
  "format_error": false
}
```

### 6.5 最终判定 `result_final_decision.json`

```json
{
  "chain_id": 0,
  "scene": "地图与位置服务",
  "intent": "查看附近门店",
  "permissions": ["ACCESS_FINE_LOCATION"],
  "rule_signal": "LOW_RISK",
  "llm_final_decision": "COMPLIANT",
  "llm_final_risk": "LOW",
  "final_decision": "CLEARLY_OK",
  "final_risk": "LOW",
  "arbiter_triggered": false,
  "arbiter_reason": "",
  "rollback": false,
  "rollback_reason": "",
  "explain": {
    "rule_signal": "LOW_RISK",
    "rule_summary": "...",
    "llm_summary": "...",
    "final_summary": "..."
  }
}
```

---

## 7. 关键目录职责

- `src/main.py`：统一 CLI 调度（full/phase1/phase2/phase3）
- `src/analy_pipline/scene/`：场景识别（text/vision 双入口）
- `src/analy_pipline/permission/`：规则权限识别
- `src/analy_pipline/judge/`：规则筛选 + 分解式 LLM 复核 + 最终仲裁
- `src/analy_pipline/common/schema_utils.py`：统一 schema 校验/规范化
- `src/analy_pipline/common/chain_summary.py`：链路摘要构造
- `src/configs/prompt/scene_classify.txt`：场景识别模板（场景定义由 config 注入）
- `src/analy_pipline/scene/run_scene_task13_text.py`：task13 文本场景实验入口
- `src/analy_pipline/scene/run_scene_task13_vision.py`：task13 视觉场景实验入口
- `src/configs/prompt/scene_task13_text.txt`：task13 文本 prompt 模板
- `src/configs/prompt/scene_task13_vision.txt`：task13 视觉 prompt 模板
- `src/configs/prompt/llm_stage_a_necessity.txt`：Stage A 模板（可改）
- `src/configs/prompt/llm_stage_b_consistency.txt`：Stage B 模板（可改）
- `src/configs/prompt/llm_stage_c_final.txt`：Stage C 模板（可改）
- `src/configs/domain/scene_permission_rules_task.json`：新 taxonomy 对应规则库（默认）

---

## 8. 最小运行示例（已完成 Phase1/Phase2）

```bash
VLLM_TEXT_URL=http://127.0.0.1:8011/v1/chat/completions \
VLLM_TEXT_MODEL=/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507 \
VLLM_VL_URL=http://127.0.0.1:8011/v1/chat/completions \
VLLM_VL_MODEL=/home/fanm/zxc/model/Qwen3-30B-A3B-Instruct-2507 \
python3 src/main.py phase3 /Users/charon/Downloads/llmui/data/processed --scene-mode text
```

---

## 9. 注意事项

1. 单个 chain 异常不会中断整个 app；单个 app 异常不会中断 batch。
2. `result_llm_review.json` 只覆盖 `MEDIUM_RISK/HIGH_RISK` 链，低风险链由规则直接给出最终判断。
3. 若 LLM 输出格式异常，系统会自动重试一次，仍失败则回滚到规则结果。
4. 场景类别已统一为 12+1 任务导向 taxonomy，代码与规则库口径一致。
