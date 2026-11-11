#!/usr/bin/env python3
"""Reflexion-style self-reflection baseline (prompt-level, same harness/budget/LLM).

No structural analysis, no coverage feedback, no experience memory.

Usage (from anywhere; outputs go under baselines/):
  python run_reflection.py --agent-cls CodeActAgent --llm-config llm.eval_qwen \
      --max-iterations 25 --eval-num-workers 5 --eval-note baselines_reflection \
      --eval-output-dir ./outputs/agent_runs \
      --dataset <path-to>/testgenevallite_test.jsonl --split test
"""
import os, sys, textwrap
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_OH = os.environ.get("OPENHANDS_ROOT", os.path.join(_REPO, "openhands"))
sys.path.insert(0, _OH)

import inspect
import evaluation.benchmarks.testgeneval.run_infer as ri

REFLECTION_APPENDIX = """

<SELF_REFLECTION_PROTOCOL>
You maintain an episodic reflection memory to avoid repeating failures.
- Keep a scratch file at /tmp/reflections.md.
- After EVERY failed test run, BEFORE attempting a fix, append to /tmp/reflections.md:
  (1) the exact error message, (2) your hypothesis for the root cause,
  (3) the fix strategy you are about to try.
- Before each new fix attempt, re-read /tmp/reflections.md.
- If the same error has failed twice with similar fixes, do NOT retry a variation
  of the same strategy; choose a fundamentally different approach.
- When the task is complete, ensure the final test suite incorporates all lessons learned.
</SELF_REFLECTION_PROTOCOL>
"""

_orig_get_instruction = ri.get_instruction

def get_instruction_reflection(instance, metadata):
    instr = _orig_get_instruction(instance, metadata)
    return instr + REFLECTION_APPENDIX

ri.get_instruction = get_instruction_reflection

# 补丁: 跳过 benchmark config.toml 的 selected_ids 过滤 (保持 160 全量), 不改 OpenHands-NEW
_orig_pdp = ri.prepare_dataset_pre
def _pdp_full(dataset, filter_column):
    dataset["instance_id_swebench"] = dataset["instance_id"]
    dataset["instance_id"] = dataset["id"]
    return dataset
ri.prepare_dataset_pre = _pdp_full

# run_infer 的驱动逻辑在 `if __name__ == "__main__"` 块中, 导入时不会执行;
# 在已打补丁的模块命名空间里执行该块 (get_instruction 查找命中的是补丁版)
_marker = 'if __name__ == "__main__":'
_src = open(ri.__file__, encoding="utf-8").read()
assert _marker in _src, "main block marker not found in run_infer.py"
_block = textwrap.dedent(_src.split(_marker, 1)[1])
print(f"[reflection-wrapper] executing run_infer main block ({len(_block)} chars)", flush=True)
exec(compile(_block, ri.__file__, "exec"), ri.__dict__)
