# Experimental Results

This directory contains all experimental outputs reported in the ICSE 2027 paper.

## Directory Structure

```
results/
├── README.md
├── scripts/
│
├── main_experiment/          ← RQ1 (Table I)
│   ├── testgenevallite/
│   └── repoexplorebench/
│
├── ablation/                 ← RQ2 (Table III)
│   ├── wo_structural_analysis/
│   ├── wo_coverage_guided_feedback/
│   ├── wo_both_memories/
│   ├── wo_constraint_memory/
│   └── wo_refinement_memory/
│
├── case_study/               ← RQ1 Case Study (Figure 5)
│   ├── case_A_sympy_13031/
│   ├── case_B_sympy_12419/
│   └── evidence_mapping.md
│
├── quantified_validation/    ← Failure statistics for RQ1 discussion
│
└── parameter_analysis/       ← RQ3 (Figure 6, Figure 7)
    ├── parameter_sensitivity.json
    └── jit_relevance_manual.json
```

## Directory → Paper Mapping

| Directory | Paper Section | Description |
|-----------|--------------|-------------|
| `main_experiment/` | §5.3 RQ1 | Main results on TestGenEval-Lite and RepoExploreBench |
| `ablation/` | §5.4 RQ2 | Ablation study (w/o each core module) |
| `case_study/` | §5.3 RQ1 (Case Study) | Trajectory-level evidence for two SymPy cases |
| `quantified_validation/` | §5.3 RQ1 (Discussion) | Failure mode statistics across all methods |
| `parameter_analysis/` | §5.5 RQ3 | Parameter sensitivity (θ_c, θ_r, τ) — Figure 6, Figure 7 |

## `run/` vs `eval/`

Each method directory contains two subdirectories:

| Subdirectory | Content |
|-------------|---------|
| `run/` | Raw generation outputs — full agent trajectories with generated tests (`output.jsonl` or `.jsonl.gz`) |
| `eval/` | Evaluation outputs — execution results with coverage, mutation scores, and pass/fail metrics (`output.testgeneval.jsonl`) |

The pipeline is: `run/` (generate tests) → `eval/` (execute and measure).

## Methods

| Directory | Method | Description |
|-----------|--------|-------------|
| `EvoTest/` | EvoTest (ours) | Full system with static analysis, coverage feedback, and memory |
| `TestForge/` | TestForge | ICSE 2026 baseline |
| `CovQValue/` | CovQValue | Coverage-guided exploration baseline |
| `zero_shot/` | Zero-shot LLM | Direct LLM generation without agent framework |
| `zero_shot/qwen3.5-flash/` | Zero-shot (Qwen) | Qwen3.5-Flash backbone |
| `zero_shot/claude-4.6-sonnet/` | Zero-shot (Claude) | Claude 4.6 Sonnet (30-instance subset on TestGenEval-Lite) |

## Reproducing Paper Numbers

```bash
# RQ1: Main results (Table I — TestGenEval-Lite)
python3 scripts/show_metrics.py main_experiment/testgenevallite/EvoTest/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py main_experiment/testgenevallite/TestForge/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py main_experiment/testgenevallite/CovQValue/eval/covqvalue_tge.testgeneval.jsonl

# RQ1: Main results (Table I — RepoExploreBench)
python3 scripts/show_metrics.py main_experiment/repoexplorebench/EvoTest/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py main_experiment/repoexplorebench/TestForge/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py main_experiment/repoexplorebench/CovQValue/eval/covqvalue_reb.testgeneval.jsonl

# Table II: Claude subset (the EVOTEST row comes from the 30-instance re-evaluation)
python3 scripts/show_metrics.py main_experiment/testgenevallite/ours_30/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py main_experiment/testgenevallite/zero_shot/claude-4.6-sonnet/eval/converted_testgenevallite.testgeneval.jsonl

# RQ2: Ablation (Table III)
python3 scripts/show_metrics.py ablation/wo_structural_analysis/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py ablation/wo_coverage_guided_feedback/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py ablation/wo_both_memories/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py ablation/wo_constraint_memory/eval/output.testgeneval.jsonl
python3 scripts/show_metrics.py ablation/wo_refinement_memory/eval/output.testgeneval.jsonl

# RQ3: Parameter sensitivity (Figure 6, Figure 7)
python3 -c "import json; d=json.load(open('parameter_analysis/parameter_sensitivity.json')); print(d['parameters']['constraint_memory_merge_threshold'])"
python3 -c "import json; d=json.load(open('parameter_analysis/parameter_sensitivity.json')); print(d['parameters']['refinement_memory_merge_threshold'])"
python3 -c "import json; d=json.load(open('parameter_analysis/parameter_sensitivity.json')); print(d['parameters']['jit_retrieval_threshold'])"
```

`show_metrics.py` aggregates per-instance metrics from each `.testgeneval.jsonl` file and prints **Coverage**, **Branch Coverage**, **Mutation Score**, **Any Pass@1**, and **All Pass@1** — the metrics reported in Tables I–III.

## Case Study Structure

Each case in `case_study/` contains:

| File | Description |
|------|-------------|
| `trajectory_evo.json` | EvoTest agent trajectory for this instance |
| `trajectory_tf.json` | TestForge agent trajectory for comparison |
| `constraint_memory.json` | Static memory entries retrieved during generation |
| `refinement_memory.json` | Dynamic memory entries retrieved during generation |
| `README.md` | Claim-to-evidence mapping for this case |
| `evidence_mapping.md` | Cross-case evidence mapping (parent directory) |

## File Types Reference

| Pattern | Description |
|---------|-------------|
| `output.jsonl` / `output.jsonl.gz` | Full agent trajectory (instruction, action history, generated tests) |
| `output.testgeneval.jsonl` | Evaluation metrics per instance (coverage, mutation, pass/fail) |
| `converted_*.jsonl` | Baseline predictions converted to OpenHands format for uniform evaluation |
| `raw/` | Original baseline data before format conversion |
