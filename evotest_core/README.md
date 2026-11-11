# evotest_core/

Core implementation of EvoTest. All code is self-contained here; no modifications to OpenHands are required.

## Module → Paper Mapping

| Module | File | Paper |
|--------|------|:-----:|
| Structural Analysis | `static_extractor.py` | §4.1 |
| Coverage-Guided Feedback | `coverage_analysis.py` | §4.2 |
| Experience Memory System | `memory_utils.py` + `memory_extractor.py` | §4.3 |
| Prompt Templates | `prompt.py` | — |
| Agent Inference | `run_infer.py` | — |
| Evaluation | `eval_infer.py` | — |
| Continual Learning Loop | `run_continual_loop.py` | — |

## Entry Points

```bash
# Single-instance inference
python -m evotest_core.run_infer --llm-config eval_default --dataset kjain14/testgenevallite --instance-id <id>

# Full continual learning loop
python -m evotest_core.run_continual_loop --llm-config eval_default --dataset kjain14/testgenevallite

# Evaluation only
python -m evotest_core.eval_infer --input-file output.jsonl --dataset kjain14/testgenevallite
```

## Data

- `RepoExploreBench/repo_explore_bench.jsonl` — REB benchmark (93 instances)
