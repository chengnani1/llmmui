# llmui 全项目代码实现报告（Phase1~Phase3_v2）

本文档面向论文写作与工程复盘，按“问题-模块-数据契约-设计动机”梳理当前代码。

## 1. 目标与边界

项目目标：对 Android 权限交互链做合规风险判定。

当前定版主链：
1. `Phase1` 采集（Fastbot + ADB）
2. `Phase2` 清洗与链构建（OCR + widgets + chain merge）
3. `Phase3_v2` 判定闭环（permission -> semantic -> retrieval -> llm -> final mapping）

核心边界：
- 语义阶段不做最终合规裁决
- 规则知识只在检索阶段提供，不在 final 阶段翻盘
- `finalize_decision.py` 仅做标签映射

## 2. 代码结构与职责

### 2.1 统一入口
- `src/main.py`

职责：
- 提供 `full / phase1 / phase2 / phase3_v2 / phase3_v2_compliance / phase3_v2_final` 六类模式
- 负责 app 目录解析、chain 过滤、阶段串联与 summary 输出

### 2.2 Phase1：数据采集
- `src/data_pipline/data_collect.py`

核心设计：
- 基于 `adbutils` 连接设备
- 安装 APK -> Fastbot 探索 -> 拉取输出
- 通过 `tupleOfPermissions.json` 判断结果是否可用
- 支持失败恢复：fastbot 非零退出但产物可用时保留结果（`recovered_with_output`）

### 2.3 Phase2：原始链加工
- `src/data_pipline/data_process.py`

核心步骤：
1. 读取 raw 下每 app 的 `tupleOfPermissions.json`
2. 通过 `repair_chain()` 修复链边界：
   - 向前找非权限页作为 before
   - 向后找非系统权限页作为 after
   - 允许多个 granting 截图并做签名去重
3. OCR 增强（自适应阈值 + 多尺度）
4. widgets 解析与打分（权限语义词/控件层级/resource-id）
5. 输出：
   - `result.json`（标准 chain 结构）
   - `chain_*.png`（合并链图）
   - `tupleOfPermissions.json`（修复后链对应关系）

## 3. Phase3_v2：判定闭环

### 3.1 权限识别（规则）
- `src/analy_pipline/permission/run_permission_rule.py`

输入：`result.json`
输出：`result_permission.json`

逻辑：
- 从 before/granting/after 的 widgets + OCR 收集文本
- 使用 `BASE_PERMISSION_TABLE` 关键词匹配权限
- 规范化权限名后输出

### 3.2 语义识别（VLM）
- `src/analy_pipline/scene/run_chain_semantic_interpreter.py`
- prompt: `src/configs/prompt/chain_semantic_interpreter_vision.txt`

输入：
- `chain_*.png`
- chain summary（OCR before/granting/after + top widgets）
- `permissions_hint`

输出最小 schema：
```json
{
  "chain_id": 0,
  "page_description": "",
  "page_function": "",
  "user_goal": "",
  "scene": {
    "ui_task_scene": "",
    "refined_scene": "",
    "confidence": 0.0
  }
}
```

实现要点：
- VLM 为主，脚本仅做轻归一：taxonomy、confidence、缺省值
- `should_rerun()` 只校验关键字段有效性
- fallback 为弱默认，不做旧模板长文本重写

### 3.3 知识检索（结构化）
- `src/analy_pipline/judge/knowledge_retriever.py`
- 知识文件：`src/configs/scene_structured_knowledge.json`

两阶段思想：
1. 粗召回：`scene + permission`
2. 重排序：基于 `page_description/page_function/user_goal/widgets` 与知识条件匹配

当前评分核心（净分）：
- 场景命中、权限命中、证据命中加分
- 冲突比、boundary 缺失、权限语义不相关惩罚
- 无证据命中规则降权

输出包含可诊断字段：
- `matched_pos_count`
- `matched_neg_count`
- `conflict_ratio`
- `coverage_score`
- `retrieval_score`

### 3.4 单次 LLM 合规判定
- `src/analy_pipline/judge/run_llm_compliance.py`
- prompt: `src/configs/prompt/llm_single_pass_compliance.txt`

LLM输入：
- semantic（`page_description/page_function/user_goal/scene`）
- permissions
- retrieved_knowledge
- OCR/widgets 摘要上下文

LLM输出（标准块）：
- necessity / consistency / over_scope
- final_decision / final_risk
- confidence
- analysis_summary
- supporting_refs / conflicting_refs / evidence_sufficiency

约束：
- 单次判定，不做 post-hoc 二次推理

### 3.5 最终映射
- `src/analy_pipline/judge/finalize_decision.py`

纯映射策略：
- `compliant -> CLEARLY_OK`
- `suspicious -> NEED_REVIEW`
- `non_compliant -> CLEARLY_RISKY`
- `low/medium/high -> LOW/MEDIUM/HIGH`

并保留：
- LLM 原始标签（`llm_final_decision`, `llm_final_risk`）
- 三维判断块
- `ui_task_scene`, `refined_scene`, `permissions`
- `_meta` 映射来源信息

## 4. 关键公共模块

- `src/analy_pipline/common/chain_summary.py`
  - 从 `result.json` 构建紧凑链摘要，统一供 semantic/llm 使用

- `src/utils/http_retry.py`
  - 统一 HTTP 重试封装，避免 vLLM 瞬时失败导致链路中断

- `src/configs/settings.py`
  - 统一环境变量入口（路径、模型、endpoint、超时）

## 5. 数据契约（可复现最小集合）

每个 app 目录最小必需文件：
- `result.json`
- `chain_*.png`
- `result_permission.json`
- `result_semantic_v2.json`
- `result_retrieved_knowledge.json`
- `result_llm_review.json`
- `result_final_decision.json`
- `label_judge.json`（评估需要）
- `labels_permission.json`（权限评估需要）

## 6. 设计取舍（可写论文）

1. **语义最小化**：减少冗余字段，避免语义层“替判定层写结论”。
2. **知识前置，不后置翻盘**：经验知识进入 retrieval/prompt，而不是 final if-else。
3. **单次LLM + 纯映射**：保证实验闭环可解释，避免多层规则污染。
4. **错例驱动知识更新**：针对 FP/FN 主导模式补充 boundary 规则，而非无差别扩库。

## 7. 目前仍可改进点

- `schema_utils.py` 仍包含大量历史兼容辅助函数，可继续瘦身
- `scripts/experiments/` 存在较多历史脚本，建议按“主实验/归档实验”再分层
- 对 scene 稀有类别可补更多结构化知识边界，提高泛化稳定性

## 8. 论文写作映射建议

- **Method**：按 `Semantic -> Retrieval -> LLM Judge -> Final Mapping` 描述
- **Implementation**：引用本文件第 2~4 节的具体代码路径
- **Ablation**：移除 retrieval 诊断项、移除 boundary 约束、移除知识库对比
- **Error Analysis**：按 SCENE/RETRIEVAL/KNOWLEDGE/JUDGE 四层归因
- **Threats to Validity**：模型波动、知识库覆盖偏置、场景噪声传播

