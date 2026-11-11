# EvoTest: Self-Evolving Agent for Test Suite Generation with Repository Context

[![ICSE 2027](https://img.shields.io/badge/ICSE-2027-blue.svg)](https://conf.researchr.org/home/icse-2027)
[![Python 3.12](https://img.shields.io/badge/python-3.12-green.svg)](https://www.python.org/downloads/release/python-3120/)
[![Docker](https://img.shields.io/badge/Docker-supported-blue.svg)](https://www.docker.com/)
[![OpenHands](https://img.shields.io/badge/Built%20with-OpenHands-orange.svg)](https://github.com/All-Hands-AI/OpenHands)

## Overview

EvoTest is a self-evolving autonomous agent for repository-aware test suite generation. It addresses three key challenges in repository-scale test generation — structural blindness, coarse-grained feedback, and repeated failures — by integrating structural analysis, coverage-guided feedback, and a dual-track experience memory system into a closed-loop agent workflow.

The framework consists of three core components:

- **Structural Analysis (§4.1)**: Extracts API signatures, dependency constraints, and exception handling via AST analysis to provide repository-level structural context.
- **Coverage-Guided Feedback (§4.2)**: Transforms raw coverage reports into semantically attributed, difficulty-ranked exploration targets.
- **Experience Memory System (§4.3)**: A dual-track memory comprising Constraint Memory (per-repository testing conventions) and Refinement Memory (cross-repository debugging insights) with vector-based retrieval.

This repository contains the implementation, benchmark datasets, experimental results, and artifact materials used in our ICSE 2027 paper.

## Quick Start

### Option A: Docker (Recommended)

```bash
git clone https://github.com/sunc71/EvoTest && cd EvoTest
docker build -t evotest:latest .
docker run -it --network host -v /var/run/docker.sock:/var/run/docker.sock evotest:latest

# Inside the container
cp config.toml.example config.toml
# edit config.toml: set your api_key under [llm.eval_qwen] and [llm.embedding]
bash scripts/build_docker.sh
bash scripts/run.sh --llm-config eval_qwen --dataset kjain14/testgenevallite \
  --use-re-preprocess --use-static-memory --use-dynamic-memory --enable-memory-update \
  --eval-n-limit 3
```

### Option B: Local Setup

```bash
git clone https://github.com/sunc71/EvoTest && cd EvoTest
bash scripts/setup.sh                          # Install Poetry + dependencies
cp config.toml.example config.toml             # Fill in api_key for LLM and embedding
bash scripts/build_docker.sh                   # Build Docker images
bash scripts/pull_testgeneval_images.sh        # Pull benchmark images
bash scripts/run.sh --llm-config eval_qwen --dataset kjain14/testgenevallite \
  --use-re-preprocess --use-static-memory --use-dynamic-memory --enable-memory-update \
  --eval-n-limit 3
```

The four flags above enable the full method: structural preprocessing, constraint memory, refinement memory, and cross-task memory updates. Without them the agent still runs the CodeAct loop for up to 25 iterations with coverage feedback, but with neither structural preprocessing nor memory, so the run does not correspond to any row in the paper. The paper's `Zero-shot` row is a single-shot prompt outside this agent loop. The paper runs Qwen3.5-Flash at temperature 0.2 with `text-embedding-v4` for memory retrieval; `config.toml.example` already holds these values and only needs the API key.

See [CLI Flags](#cli-flags) for all configuration options.

## Repository Structure

```
EvoTest/
├── evotest_core/              # Core implementation (Structural Analysis, Coverage-Guided Feedback, Memory)
├── openhands/                 # OpenHands framework (runtime & agent infrastructure)
├── scripts/                   # Automation scripts (setup, run, build)
├── results/                   # Experimental results (see results/README.md)
│   ├── main_experiment/       #   RQ1: main results (Table I)
│   ├── ablation/              #   RQ2: ablation study (Table III)
│   ├── case_study/            #   RQ1: case study evidence (Figure 5)
│   ├── parameter_analysis/    #   RQ3: parameter sensitivity (Figures 6–7)
│   ├── quantified_validation/ #   RQ1: failure statistics
├── artifact/                  # Baseline analysis (Panta, TestWeaver, CoverUp)
├── config.toml.example        # LLM config template
├── Dockerfile                 # Docker build file
└── patches/                   # No patches to OpenHands required
```

## Architecture

EvoTest integrates three core modules into a closed-loop agent workflow:

| Module | File | Paper | Description |
|--------|------|:-----:|-------------|
| Structural Analysis | `static_extractor.py` | §4.1 | AST-based extraction of API signatures, imports, exceptions |
| Coverage-Guided Feedback | `coverage_analysis.py` | §4.2 | Transforms coverage reports into structured, difficulty-ranked targets |
| Experience Memory System | `memory_utils.py` + `memory_extractor.py` | §4.3 | Constraint Memory (per-repo conventions) + Refinement Memory (cross-repo debugging insights) with vector retrieval |
| LLM Agent | `run_infer.py` + `prompt.py` | — | CodeActAgent generates tests in Docker sandbox |
| Evaluation | `eval_infer.py` | — | Line/branch coverage, mutation score |

## Paper Guide

| Paper Section | Implementation | Results |
|--------------|----------------|---------|
| §4.1 Structural Analysis | `evotest_core/static_extractor.py` | — |
| §4.2 Coverage-Guided Feedback | `evotest_core/coverage_analysis.py` | — |
| §4.3 Experience Memory System | `evotest_core/memory_utils.py` | — |
| Table I (overall, both benchmarks) | — | `results/main_experiment/` |
| Table II (Claude subset) | — | `results/main_experiment/testgenevallite/zero_shot/claude-4.6-sonnet/` and `.../ours_30/` |
| Table III (Ablation) | — | `results/ablation/` |
| Figure 5 (Case Study) | — | `results/case_study/` |
| Figures 6–7 (Parameters) | — | `results/parameter_analysis/` |

## Experimental Results

All experimental outputs reported in the paper are provided under `results/`. See [`results/README.md`](results/README.md) for detailed documentation.

Reproduce paper numbers:

```bash
# RQ1: Main results
python3 results/scripts/show_metrics.py results/main_experiment/testgenevallite/EvoTest/eval/output.testgeneval.jsonl

# Table II: the EVOTEST row on the Claude subset comes from the 30-instance re-evaluation
python3 results/scripts/show_metrics.py results/main_experiment/testgenevallite/ours_30/eval/output.testgeneval.jsonl
python3 results/scripts/show_metrics.py results/main_experiment/testgenevallite/zero_shot/claude-4.6-sonnet/eval/converted_testgenevallite.testgeneval.jsonl

# RQ2: Ablation
python3 results/scripts/show_metrics.py results/ablation/wo_structural_analysis/eval/output.testgeneval.jsonl

# RQ3: Parameter sensitivity
python3 -c "import json; d=json.load(open('results/parameter_analysis/parameter_sensitivity.json')); print(d['parameters']['constraint_memory_merge_threshold'])"
```

`show_metrics.py` outputs **Coverage**, **Branch Coverage**, **Mutation Score**, and **Any Pass@1**.

## Datasets

### TestGenEval-Lite (160 instances)

A function-level test generation benchmark from [TestGenEval](https://arxiv.org/abs/2410.00752) (Jain et al., 2024). Covers Django, SymPy, scikit-learn, pytest, astropy, matplotlib, seaborn.

```bash
bash scripts/pull_testgeneval_images.sh   # Pull 160 Docker images from DockerHub
bash scripts/run.sh --llm-config eval_default --dataset kjain14/testgenevallite --eval-n-limit 3
```

### RepoExploreBench (93 instances)

A repository-level test generation benchmark across Python packages (click, jinja2, flask, etc.).

```bash
bash scripts/run.sh --llm-config eval_default --dataset evotest_core/RepoExploreBench/repo_explore_bench.jsonl --eval-n-limit 3
```

## CLI Flags

**Memory (§4.3)**

| Flag | Description |
|------|-------------|
| `--use-static-memory` | Enable Constraint Memory (per-repository testing conventions) |
| `--use-dynamic-memory` | Enable Refinement Memory (cross-repository debugging insights) |
| `--enable-memory-update` | Extract memory after each instance evaluation |

**Analysis (§4.1)**

| Flag | Description |
|------|-------------|
| `--use-re-preprocess` | Enable Structural Analysis hints in prompt |

**Coverage (§4.2)**

| Flag | Description |
|------|-------------|
| `--disable-coverage-feedback` | Disable Coverage-Guided Feedback (ablation) |
| `--random-difficulty-sort` | Random target ordering instead of difficulty-sorted (ablation) |

**Evaluation**

| Flag | Description |
|------|-------------|
| `--skip_mutation` | Skip mutation testing (saves time) |
| `--skip_lexical` | Skip lexical metrics |

**Execution**

| Flag | Description |
|------|-------------|
| `--eval-n-limit N` | Limit number of instances |
| `--instance-id ID` | Run single instance |
| `--repo NAME` | Filter by repo (e.g., `sympy/sympy`) |
| `--start-idx N` | Resume from iteration N |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | LLM API key |
| `OPENAI_BASE_URL` | (optional) | Custom API endpoint |
| `STATIC_MEMORY_THRESHOLD` | `0.80` | Cosine similarity threshold (θ_c) for Constraint Memory dedup |
| `DYNAMIC_MEMORY_THRESHOLD` | `0.85` | Cosine similarity threshold (θ_r) for Refinement Memory dedup |
| `JIT_RETRIEVAL_THRESHOLD` | `0.60` | Minimum similarity (τ) for JIT memory injection |

## Unit Tests

```bash
export PYTHONPATH="$(pwd)/openhands:$(pwd):$PYTHONPATH"
python -m pytest evotest_core/test_memory_logic.py -v
```

## References

- [TestGenEval](https://arxiv.org/abs/2410.00752) — Function-level test generation benchmark (Jain et al., 2024)
- [TestForge](https://github.com/kdjain/testforge) — Baseline and testgenevallite Docker images
- [RepoExploreBench](https://arxiv.org/abs/2604.05159) — Repository-level test generation benchmark
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) — Runtime framework
