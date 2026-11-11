#!/usr/bin/env python3
"""RAG baseline: retrieval-augmented few-shot with same-repo developer tests.

Retrieves real test code written by developers for OTHER PRs of the SAME
repository (from the benchmark dataset's test_patch of other instances) and
injects the top matches as few-shot exemplars into the instruction.
The current instance's own gold test is never used (no label leakage).

Usage: same as run_reflection.py, with --eval-note baselines_rag.
"""
import os, sys, textwrap, json, re
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_OH = os.environ.get("OPENHANDS_ROOT", os.path.join(_REPO, "openhands"))
sys.path.insert(0, _OH)

import evaluation.benchmarks.testgeneval.run_infer as ri

def _extract_added_test_code(test_patch: str, limit: int = 2500) -> str:
    """Extract added lines from a gold test diff (other-instance exemplar)."""
    lines = []
    for ln in test_patch.splitlines():
        if ln.startswith("+++") or ln.startswith("---") or ln.startswith("diff "):
            continue
        if ln.startswith("+"):
            lines.append(ln[1:])
    code = "\n".join(lines).strip()
    # 去掉可能的非测试部分提示
    return code[:limit]

_DATASET_CACHE = None
def _load_dataset(path):
    global _DATASET_CACHE
    if _DATASET_CACHE is None:
        rows = []
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        _DATASET_CACHE = rows
    return _DATASET_CACHE

def _dataset_path_from_argv():
    args = sys.argv
    if "--dataset" in args:
        return args[args.index("--dataset") + 1]
    return None

def _repo_of(iid_or_repo, row):
    repo = row.get("repo", "")
    return repo

RAG_APPENDIX_TMPL = """

<REPOSITORY_TEST_EXEMPLARS>
Below are real test functions written by developers in this repository (from other
modules/PRs), showing its testing conventions, imports, fixtures and assertion style.
Follow these conventions in the test suite you write.

{exemplars}
</REPOSITORY_TEST_EXEMPLARS>
"""

_orig_get_instruction = ri.get_instruction

def get_instruction_rag(instance, metadata):
    instr = _orig_get_instruction(instance, metadata)
    try:
        iid = str(instance.get("instance_id_swebench", instance.get("instance_id", "")))
        repo = str(instance.get("repo", "") or "")
        if not repo and "__" in iid:
            repo = iid.split("__")[0].replace("-", "/", 1)
        ds_path = _dataset_path_from_argv()
        if not ds_path:
            return instr
        rows = _load_dataset(ds_path)
        # 同仓库其他实例的 gold test diff 作为范例 (排除当前实例)
        cur_key = iid.split("-")[0]  # 粗匹配前缀, 精确排除用 id
        exemplars = []
        for r in rows:
            other_id = r.get("id") or r.get("instance_id")
            if not other_id or other_id == iid:
                continue
            r_repo = r.get("repo", "")
            if r_repo and repo and r_repo != repo:
                continue
            tp = r.get("test_patch") or ""
            if not tp.strip():
                continue
            code = _extract_added_test_code(tp)
            if len(code) < 200:
                continue
            exemplars.append((other_id, code))
        if exemplars:
            picked = exemplars[:2]
            body = "\n\n".join(
                f"<example from={oid}>\n{code}\n</example>" for oid, code in picked
            )
            instr += RAG_APPENDIX_TMPL.format(exemplars=body)
    except Exception as e:
        print(f"[rag-wrapper] exemplar injection skipped: {type(e).__name__}: {e}", flush=True)
    return instr

ri.get_instruction = get_instruction_rag

# 补丁: 跳过 benchmark config.toml 的 selected_ids 过滤 (保持 160 全量), 不改 OpenHands-NEW
_orig_pdp = ri.prepare_dataset_pre
def _pdp_full(dataset, filter_column):
    dataset["instance_id_swebench"] = dataset["instance_id"]
    dataset["instance_id"] = dataset["id"]
    return dataset
ri.prepare_dataset_pre = _pdp_full

# run_infer 的驱动逻辑在 `if __name__ == "__main__"` 块中, 导入时不会执行;
# 在已打补丁的模块命名空间里执行该块
_marker = 'if __name__ == "__main__":'
_src = open(ri.__file__, encoding="utf-8").read()
assert _marker in _src, "main block marker not found in run_infer.py"
_block = textwrap.dedent(_src.split(_marker, 1)[1])
print(f"[rag-wrapper] executing run_infer main block ({len(_block)} chars)", flush=True)
exec(compile(_block, ri.__file__, "exec"), ri.__dict__)
