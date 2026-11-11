# Evidence Mapping

Maps each paper claim to the raw evidence in the trajectory logs, memory stores, and evaluation outputs.

---

## Case A: Constraint Memory (sympy__sympy-13031-146)

### Claim: Constraint Memory injects repository-specific testing conventions

| Paper Claim | Raw Evidence | Source |
|------------|-------------|--------|
| CM entry mandates bare functions, prohibits classes | `"Tests MUST be implemented as standalone bare functions using pytest syntax... MUST NOT be written inside classes or use class-based test wrappers."` | constraint_memory.json #0 |
| CM entry explicitly forbids class wrapping | `"DO NOT organize or wrap tests into classes. DO NOT use unittest. Tests MUST be implemented as standalone functions prefixed with 'test_'."` | constraint_memory.json #1 |
| CM entry mandates flat function structure | `"All test cases must be implemented as bare functions starting with 'test_', structured as standalone functions rather than class methods, and maintain a flat function-based structure."` | constraint_memory.json #22 |
| CM entry mandates inline imports | `"Import all necessary symbols... directly at the beginning of each test function from their respective source modules to ensure namespace isolation."` | constraint_memory.json #11 |
| CM entry mandates native assert | `"All assertions must use native assert statements. DO NOT use unittest framework syntax or unittest assertion methods."` | constraint_memory.json #17 |
| Total CM entries for sympy | 25 entries | constraint_memory.json |

### Claim: Agent generates bare function structure adhering to convention

| Paper Claim | Raw Evidence | Source |
|------------|-------------|--------|
| All 75 tests are bare module-level functions | `def test_sparse_matrix_constructor_list():`, `def test_sparse_matrix_constructor_dict():`, ... — no classes | trajectory_evo.json, test_result.test_suite |
| Zero test classes in EvoTest output | No `class Test*:` anywhere in test suite | trajectory_evo.json, test_result.test_suite |
| Inline imports per function | `from sympy.matrices import SparseMatrix` inside each function body | trajectory_evo.json, test_result.test_suite |
| Evaluation script reports 78 tests discovered | 78 tests discovered (70 passing, 8 failing) after test filtering | output.testgeneval.jsonl, report.test_stats |

### Claim: Baseline (no Constraint Memory) uses class-based structure → 0 tests discovered

| Paper Claim | Raw Evidence | Source |
|------------|-------------|--------|
| TestForge writes 22 test classes | `class TestSparseMatrixCreation:`, `class TestSparseMatrixEquality:`, ... (22 classes, 70 methods) | trajectory_tf.json, test_result.test_suite |
| bin/test discovers zero class-based tests | `================== tests finished: 0 passed, in 0.01 seconds ===================` | output.testgeneval.jsonl (TestForge), report.test_output |
| TestForge coverage = 0% | `coverage: 0` | output.testgeneval.jsonl (TestForge), report |
| TestForge mutation = 0% | `mutation_score: 0` | output.testgeneval.jsonl (TestForge), report |
| Test content is functionally correct | TestForge's assertions test the same SparseMatrix operations; the issue is structural, not qualitative | trajectory_tf.json, test_result.test_suite |

### Scores Summary

| Metric | EvoTest | TestForge |
|--------|:-------------------:|:---------------------:|
| Coverage | **86.9%** | 0% |
| Mutation Score | **100.0%** | 0% |
| Tests Discovered | 78 | 0 |
| Tests Passing | 70 | 0 |
| Test Structure | 75 bare functions | 22 classes, 70 methods |

---

## Case B: Refinement Memory (sympy__sympy-12419-178)

### Claim: Execution failure triggers JIT retrieval of similar failure-resolution knowledge

| Paper Claim | Raw Evidence | Source |
|------------|-------------|--------|
| Test execution raises ShapeError | `raise ShapeError("Matrices %s and %s are not aligned"%(A, B))` → `ShapeError: Matrices A*B and A are not aligned` | trajectory_evo.json, history[17].content |
| JIT retrieval triggered | `[SYSTEM MEMORY TRIGGERED] Relevant Historical Insights Found:` | trajectory_evo.json, history[17] (system response) |
| Retrieved entry directly addresses shape compatibility | `"Linear algebra operations in edge case tests must strictly validate operand shape compatibility to prevent runtime dimension mismatch errors."` (Relevance: 0.71) | trajectory_evo.json, JIT content |
| Retrieved knowledge is cross-repository | Memory origin: `scikit-learn/scikit-learn` (Case: `scikit-learn__scikit-learn-14092-66`) — different project from current instance (sympy) | trajectory_evo.json, JIT content |
| Two most relevant entries focus on shape compatibility | `"Linear algebra operations must strictly validate operand shape compatibility..."` (0.71, scikit-learn), `"Assertions involving large integer representations in array shape formatting..."` (0.65, scikit-learn) | trajectory_evo.json, JIT content |

### Claim: Retrieved knowledge guides immediate refinement

| Paper Claim | Raw Evidence | Source |
|------------|-------------|--------|
| Agent edits test file immediately after JIT | Step 18: `action: "edit"` on `/testbed/sympy/matrices/expressions/tests/test_matexpr.py` — the very next action after JIT at Step 17 (history[17] → history[18]) | trajectory_evo.json, history[18] |
| Agent iterates with multiple edits | 5 total edits after JIT, covering matrix expression tests | trajectory_evo.json |
| Tests verified passing | `PASSED` appears in run output after edits (Step 20, 3 seconds after edit) | trajectory_evo.json, history[20].content |
| Agent produces comprehensive suite | 4477 lines, 164 passing tests, 92.57% coverage | eval output |

### Claim: Baseline (no Refinement Memory) achieves lower coverage

| Paper Claim | Raw Evidence | Source |
|------------|-------------|--------|
| TestForge produces smaller suite | 16,040 chars (655 lines) vs 140,204 chars (4477 lines) | trajectory_tf.json test_result |
| TestForge coverage lower | coverage: 90.09% vs 92.57% | output.testgeneval.jsonl report |
| TestForge fewer passing tests | 82/90 passed vs 164/715 | output.testgeneval.jsonl report |

### Scores Summary

| Metric | EvoTest | TestForge |
|--------|:-------------------:|:---------------------:|
| Coverage pass@1 | **92.57%** | 90.09% |
| Mutation Score | **100.0%** | 100.0% |
| Tests Passing | 164/715 | 82/90 |
| Suite Length | 140,204 chars (4477 lines) | 16,040 chars (655 lines) |
| All Tests Pass | No (715 tests, 164 pass) | No (90 tests, 82 pass) |

### Temporal Chain Verification

```
Step 17 (02:07:35): ShapeError triggered + JIT retrieval fires (same step)
    ↓  (3 seconds)
Step 18 (02:07:38): EDIT test_matexpr.py (immediate refinement)
    ↓  (3 seconds)
Step 20 (02:07:41): RUN verification → PASSED
    ↓
Steps 29, 35, 41, 47: 4 more edits → iterative expansion → 4477-line suite
```

Timestamps confirm temporal proximity:
- Step 17 (ShapeError + JIT): 2026-05-27T02:07:35
- Step 18 (edit): 2026-05-27T02:07:38 (3 seconds later)
- Step 20 (run): 2026-05-27T02:07:41 (3 seconds later)

---

## Design Consistency Matrix

| Design Concept | Case A Evidence | Case B Evidence |
|---------------|----------------|----------------|
| Repository-specific convention knowledge | ✅ sympy CM: "bare functions, no classes, inline imports" (25 entries) | N/A |
| Cross-repository failure-resolution knowledge | N/A | ✅ scikit-learn → sympy: "validate operand shape compatibility" (relevance 0.71) |
| Pre-generation knowledge injection | ✅ CM loaded into system prompt before generation | N/A |
| Just-in-time retrieval during failure | N/A | ✅ JIT on ShapeError (Step 17) |
| Immediate refinement guided by memory | N/A | ✅ Edit at Step 18 (3 seconds after JIT) |
| Performance improvement over baseline | ✅ 86.9% vs 0% coverage (structural convention gap) | ✅ 92.6% vs 90.1% coverage (refinement depth gap) |

---

## File Inventory

```
case_study/
├── evidence_mapping.md                 ← this file
├── case_study_self_consistency.json    ← cross-file consistency verification
├── case_A_sympy_13031/
│   ├── README.md                       ← case description & claim mapping
│   ├── trajectory_evo.json             ← EvoTest agent trajectory (54 steps)
│   ├── trajectory_tf.json              ← TestForge agent trajectory (54 steps)
│   ├── constraint_memory.json          ← 25 sympy constraint entries
│   └── refinement_memory.json          ← 93 sympy refinement entries
└── case_B_sympy_12419/
    ├── README.md                       ← case description & claim mapping
    ├── trajectory_evo.json             ← EvoTest agent trajectory (53 steps)
    ├── trajectory_tf.json              ← TestForge agent trajectory (53 steps)
    ├── constraint_memory.json          ← 25 sympy constraint entries
    └── refinement_memory.json          ← 93 sympy refinement entries
```
