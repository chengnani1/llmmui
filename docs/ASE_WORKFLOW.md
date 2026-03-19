# ASE Paper Workflow (llmui Phase3_v2)

本文件用于论文写作与实验复现，描述当前项目的完整工作流、设计边界与可复现协议。

## 1. 问题定义

目标：给定 Android 权限交互链（截图 + OCR + widgets + 已识别权限），判断当前权限请求在当前页面任务下是否合规。

判定对象是“链级样本（chain）”，不是整个 App 的全局权限策略。

## 2. 方法总览

当前方法是一个单向流水线（无后置翻盘规则）：

1. UI chain 语义识别（VLM）
2. 场景知识检索（结构化知识）
3. 单次 LLM 合规判定（necessity / consistency / over_scope）
4. 纯标签映射得到最终系统标签

核心约束：

- LLM 后不再做规则修正
- 规则知识只在检索阶段提供给 LLM，不在 finalize 阶段重判
- semantic 层只输出中间表示，不做最终合规结论

## 3. 输入与输出

### 3.1 输入

每个 app 目录包含：

- `result.json`：Phase2 提取后的链结构
- `chain_*.png`：链截图
- `result_permission.json`：权限识别结果（phase3_v2 中可自动生成）

### 3.2 中间输出

#### A) `result_semantic_v2.json`

```json
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
```

#### B) `result_retrieved_knowledge.json`

- 记录每个 chain 的召回规则、命中证据、冲突比、覆盖率等诊断信息

#### C) `result_llm_review.json`

- necessity / consistency / over_scope 三维判定
- final_decision / final_risk
- supporting_refs / conflicting_refs
- evidence_sufficiency

### 3.3 最终输出

#### `result_final_decision.json`

- `CLEARLY_OK | NEED_REVIEW | CLEARLY_RISKY`
- `LOW | MEDIUM | HIGH`
- 保留 LLM 原始标签与三维判定块

## 4. 核心模块与职责边界

### 4.1 Semantic 模块

文件：`src/analy_pipline/scene/run_chain_semantic_interpreter.py`

职责：

- 从链截图 + OCR + widgets 生成最小语义表示
- 输出页面描述、页面功能、用户目标、场景

不做：

- 权限合理性裁决
- 风险结论输出

### 4.2 Retrieval 模块

文件：`src/analy_pipline/judge/knowledge_retriever.py`

职责：

- 按 `scene + permission` 粗召回
- 结合 `page_description/page_function/user_goal` 做重排序
- 输出规则命中证据与冲突诊断

当前打分思想：

- 正向证据加分
- 负向证据单独计数
- 冲突比与边界缺失惩罚
- 权限语义不相关惩罚
- 无命中证据的 scene+perm 规则降权

### 4.3 LLM Compliance 模块

文件：`src/analy_pipline/judge/run_llm_compliance.py`

职责：

- 单次调用 LLM 完成三维判定 + 最终标签
- 强制输出结构化 JSON

输入仅来自：

- semantic
- permissions
- retrieved_knowledge
- OCR/widgets 辅助文本

### 4.4 Final Mapping 模块

文件：`src/analy_pipline/judge/finalize_decision.py`

职责：

- 纯映射，无二次推理
- 将 LLM 标签映射到系统标签

不做：

- guard/rollback/arbiter
- scene 或 risk 的规则翻盘

## 5. 结构化知识设计

主文件：`src/configs/scene_structured_knowledge.json`

每条知识结构：

```json
{
  "id": "...",
  "scene": "...",
  "refined_scene": "...",
  "permissions": ["..."],
  "allow_if": ["..."],
  "deny_if": ["..."],
  "boundary_if_missing": ["..."],
  "positive_evidence": ["..."],
  "negative_evidence": ["..."],
  "source_type": "prior|pattern|case"
}
```

设计原则：

- 规则必须有“允许边界”和“拒绝边界”
- 允许 `suspicious` 作为边界态，不强行二元化
- 高冲突知识不直接全量注入 prompt

## 6. 错例驱动迭代协议

### 6.1 分析

- 评估脚本产出 TP/FP/TN/FN
- 聚类错例到 `(scene, permission, error_type)`
- 排序得到主导失败模式

### 6.2 更新

- 只更新高频组合
- 优先补 boundary 规则，不做泛化关键词堆叠
- 使用 lint 保证质量

### 6.3 验证

- 先 targeted regression（FN-heavy / FP-heavy app）
- 再全量回归
- 记录每轮变化（TP/FP/FN、precision/recall/F1）

## 7. 复现实验命令

### 7.1 后半段（推荐）

```bash
python3 src/main.py phase3_v2_compliance /path/to/processed --force
python3 src/main.py phase3_v2_final /path/to/processed --force
```

### 7.2 全量 Phase3_v2

```bash
python3 src/main.py phase3_v2 /path/to/processed --force
```

### 7.3 评估

```bash
python3 scripts/experiments/evaluate_label_judge_binary.py \
  /path/to/processed \
  --pred-file result_final_decision.json \
  --review-as risk \
  --app-prefix fastbot- \
  --output judge_binary_metrics.json
```

## 8. 论文可写贡献点（建议）

1. 语义中间表示 + 结构化知识 + 单次 LLM 的闭环架构
2. 冲突感知与边界缺失约束的知识检索机制
3. LLM 后纯映射，避免后置 heuristic 污染实验结论
4. 错例驱动知识迭代协议（可操作、可追踪）

## 9. 实验报告建议

建议至少报告：

- Overall：accuracy / precision / recall / F1 / specificity / balanced accuracy
- Error breakdown：SCENE / RETRIEVAL / KNOWLEDGE / JUDGE / AMBIGUOUS
- Per-app：FN-heavy 与 FP-heavy 变化
- Ablation：
  - 去掉结构化知识
  - 去掉冲突惩罚
  - 去掉 evidence sufficiency 约束
  - 去掉 boundary_if_missing 约束

## 10. 威胁与限制（论文必写）

- 场景语义噪声会影响检索与 LLM 判定
- 知识库迭代存在数据集偏置风险（需独立验证集）
- 远端模型波动可能引入轻微非确定性（建议固定模型与温度）
- 规则文本质量直接影响 LLM 可解释性与稳定性

## 11. 可复现性检查清单

- 固定 commit
- 固定 prompt 版本
- 固定知识库版本
- 固定模型 endpoint 与 model id
- 固定评估脚本与阈值映射策略
- 保存每轮 metrics JSON 与错例聚类 CSV
