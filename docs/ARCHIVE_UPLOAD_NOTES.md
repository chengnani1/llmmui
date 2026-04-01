# Archive Upload Notes

本文档说明当前归档上传版本的边界、保留内容和清理内容。

## 1. 当前保留范围

当前仓库只保留这些内容：

- `phase1 -> phase2 -> phase3_v2` 主链
- `phase3_v2_compliance` / `phase3_v2_final` 两个拆分入口
- 当前仍有用的评估脚本
- 错例驱动的知识迭代脚本
- 当前提示词、规则文件、结构化知识文件

## 2. 已清理内容

为了便于归档上传，以下内容已经移除：

- 旧版 phase3 链路脚本
- 历史实验目录 `scripts/experiments/legacy_from_*`
- 历史备份目录 `scripts/archive/src_backups`
- 带明文 API key 的测试脚本
- 写死个人机器路径的废弃工具脚本
- 调用已不存在 `agent` 模式的旧入口脚本

## 3. 当前正式入口

统一入口是 `src/main.py`，当前只支持：

- `full`
- `phase1`
- `phase2`
- `phase3_v2`
- `phase3_v2_compliance`
- `phase3_v2_final`

`run_full_pipeline.sh` 是对这些模式的轻封装。

## 4. 配置原则

- 运行配置集中在 `src/configs/settings.py`
- 推荐只通过环境变量覆盖默认值
- `.env.example` 提供了可复用模板
- 仓库中不应包含任何真实 API key、个人数据路径或私有模型绝对路径

## 5. 仍保留但需要理解的边界

仓库中仍有少量分析脚本会读取旧字段或旧输出文件名作为兼容输入，这些脚本只用于分析和对比，不属于当前主链运行必需项。

当前主链的正式语义输出文件是：

- `result_semantic_v2.json`

不是：

- `result_chain_semantics.json`

## 6. 上传建议

- 优先使用 git tracked 文件作为上传内容
- 不要把本地 `data/` 大目录、缓存目录、`.DS_Store` 或 `__pycache__` 一起打包
- 上传前再次检查工作区中是否存在未提交的本地临时脚本
