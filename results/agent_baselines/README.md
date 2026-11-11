# Additional Agent Baselines (added 2026-09-25)

These are post-submission baseline runs referenced in the author response. Both use the same agent scaffold (CodeActAgent), the same model (Qwen3.5-Flash), the same iteration budget (max 25), and the same evaluation pipeline as the main experiments. Neither uses the structural analysis, coverage feedback, or experience-memory components of the proposed framework.

- `run_reflection.py` — Reflexion-style baseline. Prompt-level instantiation of the self-reflection paradigm (Shinn et al., NeurIPS 2023). The instruction is extended with a protocol that asks the agent to maintain an episodic reflection file: after every failed test run it records the exact error message, a root-cause hypothesis, and the next fix strategy, and re-reads the file before each new attempt. This is a paradigm-style instantiation, not a re-implementation of the original Reflexion framework.

- `run_rag.py` — RAG-style baseline. Prompt-level instantiation of the retrieval-augmented generation paradigm (Lewis et al., NeurIPS 2020). Before writing tests for an instance, the script retrieves developer-written test code from other instances of the same repository (from the benchmark dataset's stored test patches) and injects up to two exemplars as few-shot context. The current instance's own gold test is never retrieved, so there is no label leakage. This is a self-designed instantiation of the paradigm.

- `agent_baselines_reflection.testgeneval.jsonl`, `agent_baselines_rag.testgeneval.jsonl` — evaluation outputs on the TestGenEval-Lite test split, in the same JSONL schema as the other evaluation outputs in this artifact (metric fields are defined in `evotest_core/README.md`).

- `reflection_full2.done1.log`, `rag_full2.done1.log` — raw logs of the completed generation runs.

## Rerunning these baselines

The saved evaluations above can be recomputed with `results/scripts/show_metrics.py`. Regenerating them requires the full OpenHands evaluation tree, because both scripts import `evaluation.benchmarks.testgeneval.run_infer`. This artifact ships a trimmed copy of OpenHands that keeps the runtime but not the benchmark entry points.

Point the scripts at a complete OpenHands checkout before running:

```bash
export OPENHANDS_ROOT=/path/to/OpenHands
python run_reflection.py --agent-cls CodeActAgent --llm-config llm.eval_qwen \
  --max-iterations 25 --eval-num-workers 5 --eval-note baselines_reflection \
  --eval-output-dir ./outputs/agent_runs \
  --dataset /path/to/testgenevallite_test.jsonl --split test
```

`run_rag.py` takes the same arguments and uses `--eval-note baselines_rag`.
