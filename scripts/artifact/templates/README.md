# PrivUI-Guard Artifact

This artifact reorganizes the project into a single reusable package for two goals:

1. Reproduce the paper's evaluation results directly from the included processed datasets.
2. Run the released project pipeline code from the same package.

## 1. Included Contents

- `data/benchmark_processed/`
  Released role: benchmark dataset for effectiveness and ablation experiments.
- `data/independent_processed/`
  Released role: independent dataset for generalization evaluation.
- `data/large_scale_processed/`
  Released role: large-scale real-world analysis dataset.
- `src/`
  Main project source code.
- `lib/`
  Fastbot runtime libraries required by the data collection pipeline.
- `experience/`
  Directly runnable evaluation and summarization scripts for the artifact.
- `docs/`
  Project notes and workflow documents copied from the main repository.
- `run_eval.sh`
  One-command evaluation reproduction entry.
- `run_project.sh`
  One-command project execution entry.
- `run_full_pipeline.sh`
  Original project wrapper retained for compatibility.

## 2. Dataset Summary

The included processed data correspond to these released experiment groups.

### Benchmark Dataset

- Apps: 69
- Interaction chains: 333
- Labels: 193 risky, 140 non-risky
- Permission types: 10
- UI task scenarios: 12
- Main use: RQ1 effectiveness and RQ2 ablation

### Independent Dataset

- Apps: 45
- Interaction chains: 186
- Labels: 131 risky, 55 non-risky
- Main use: generalization evaluation

### Large-scale Real-world Dataset

- Processed apps with permission requests: 258
- Interaction chains: 1,684
- Main use: real-world risk analysis

Paper-level collection metadata for the large-scale study:

- Deduplicated apps collected from AndroZoo: 865
- XML-PNG UI pairs observed during collection: 657,632

Only the processed chain-level subset needed for release and evaluation is packaged here.

## 3. Directory Layout

```text
PrivUI-Guard_artifact/
├── README.md
├── requirements.txt
├── run_eval.sh
├── run_project.sh
├── run_full_pipeline.sh
├── src/
├── lib/
├── docs/
├── experience/
├── results/
└── data/
    ├── DATASET_MAPPING.md
    ├── benchmark_processed/
    ├── independent_processed/
    └── large_scale_processed/
```

## 4. Environment

Minimum Python version: `3.9+`

Install dependencies:

```bash
pip install -r requirements.txt
```

The released evaluation path only needs Python and the included processed data.

To rerun the project pipeline itself, these additional runtime prerequisites may be needed depending on mode:

- `adb` and Android device/emulator for `phase1`
- Tesseract OCR for `phase2`
- OpenAI-compatible VLM / LLM endpoints for `phase3_v2`

## 5. Quick Start

Reproduce evaluation results:

```bash
bash run_eval.sh
```

This writes result tables and JSON summaries to `results/`.

Run the project on a released processed dataset:

```bash
bash run_project.sh phase3_v2 benchmark --force
```

Run the project on an arbitrary processed directory:

```bash
bash run_project.sh phase3_v2 /absolute/path/to/processed --force
```

Run the full source pipeline on a local APK directory:

```bash
bash run_project.sh full /absolute/path/to/apks \
  --raw-root /absolute/path/to/raw \
  --processed-root /absolute/path/to/processed \
  --force
```

## 6. Evaluation Scripts

The `experience/` directory contains the runnable artifact-side experiment scripts:

- `summarize_datasets.py`
  Computes released dataset-level statistics from the packaged processed data.
- `evaluate_benchmark.py`
  Reproduces the benchmark effectiveness table and ablation table.
- `evaluate_generalization.py`
  Reproduces the independent-set generalization metrics.
- `summarize_rq3.py`
  Reproduces the large-scale chain-level and app-level risk summaries.
- `reproduce_results.py`
  Runs all of the above and writes the final artifact outputs.

## 7. Output Files

After `bash run_eval.sh`, the artifact generates:

- `results/table_dataset_summary.csv`
- `results/table_rq1_effectiveness.csv`
- `results/table_rq2_ablation.csv`
- `results/table_generalization.csv`
- `results/table_rq3_chain_risk_breakdown.csv`
- `results/table_rq3_app_risk_breakdown.csv`
- `results/dataset_summary.json`
- `results/rq1_effectiveness.json`
- `results/rq2_ablation.json`
- `results/generalization.json`
- `results/rq3_summary.json`
- `results/repro_summary.json`

## 8. File Mapping Used By Evaluation

The released evaluation scripts read the existing chain-level outputs directly from each app directory.

### Benchmark Effectiveness

- PrivUI-Guard: `result_final_decision.json`
- Rule-based baseline: `result_rule_only_keyword.json`
- LLM text-only baseline: `result_llm_ui.json`
- VLM direct baseline: `result_vlm_direct_risk.json`

### Ablation

- w/o interaction chain: `result_final_decision_wo_chain.json`
- w/o semantic modeling: `result_final_decision_wo_semantic.json`
- w/o knowledge enhancement: `result_final_decision_wo_knowledge.json`
- w/o structured reasoning: `result_final_decision_wo_structured_reasoning.json`

The benchmark release also contains extra auxiliary outputs such as `result_knowledge_rule_baseline.json` and `result_final_decision_wo_semantic_pure.json`. They are preserved in the dataset and reported as auxiliary rows where relevant.

## 9. Reproducibility Boundary

This package is designed so that the released evaluation can be reproduced directly from the included processed data.

What is directly reproducible from this artifact:

- effectiveness metrics on the benchmark dataset
- ablation metrics on the benchmark dataset
- generalization metrics on the independent dataset
- chain-level and app-level large-scale risk summaries
- source-level reruns of `phase3_v2` on the included processed datasets

What is not fully self-contained in this artifact:

- raw APK redistribution
- original raw exploration traces used before processing
- full regeneration of the large-scale collection metadata (`865` apps and `657,632` XML-PNG pairs) from raw inputs alone
- `phase1` reruns without local APKs and Android-side runtime setup

## 10. Notes

- `data/benchmark_processed` and `data/independent_processed` include `label_judge.json`, so they can be evaluated directly.
- `data/large_scale_processed` does not include manual binary ground truth labels; it is used for aggregate risk analysis only.
- The project code defaults to `data/` under the artifact root, so the packaged structure is directly runnable without editing source paths.
