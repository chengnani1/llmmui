# data/processed 清理报告（2026-03-19）

## 1. 清理目标

清理 `data/processed` 根目录与各 app 目录中的历史实验冗余文件，只保留当前主链与评估必需文件。

## 2. 清理方式

采用“迁移归档”而非直接删除：
- 归档目录：`data/processed/_archive_cleanup_20260319_150850/`
- 清理脚本：`scripts/utils/cleanup_processed_unused.py`

## 3. 清理结果

- 根目录迁移文件：`111`
- app 目录迁移文件：`897`
- 额外历史目录迁移：`2`
  - `knowledge_iterations/`
  - `targeted_regression_backup_before/`

根目录当前保留：
- `phase3_v2_summary.json`
- `phase3_v2_compliance_summary.json`
- `phase3_v2_final_summary.json`
- `judge_binary_metrics_after.json`

## 4. app 目录保留白名单

每个 app 目录仅保留：
- `result.json`
- `chain_*.png`
- `result_permission.json`
- `result_semantic_v2.json`
- `result_retrieved_knowledge.json`
- `result_llm_review.json`
- `result_final_decision.json`
- `label_judge.json`
- `labels_permission.json`

## 5. 已迁移的典型冗余文件

- `result_rule_screening.json`
- `result_ui_task_scene.json`
- `result_chain_semantics.json`
- `result_regulatory_scene.json`
- `result_llm_ui.json`
- `result_rule_only_keyword.json`
- `result_vlm_direct_risk.json`
- `results_scene_open.json`
- `results_scene_task13.json`
- `tupleOfPermissions.json`
- `scene_from_semantics_summary.json`
- `regulatory_scene_summary.json`

## 6. 恢复方式

如需恢复历史文件：
- 从 `data/processed/_archive_cleanup_20260319_150850/` 对应路径移回原位置。

## 7. 后续建议

- 后续实验产物统一写到 `data/processed/_exp_runs/<run_id>/`，避免再次污染 app 根目录。
- 若只做 phase3 后半段实验，建议固定只更新：
  - `result_retrieved_knowledge.json`
  - `result_llm_review.json`
  - `result_final_decision.json`

