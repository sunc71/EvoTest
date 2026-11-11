# Case B: Refinement Memory (sympy__sympy-12419-178)

**Paper Section**: Section V, Case B

**Claim**: Refinement Memory transfers reusable debugging rationale across project boundaries, enabling rapid recovery from runtime failures.

## Files

| File | Description |
|------|-------------|
| `trajectory_evo.json` | Full EvoTest agent trajectory (92.6% coverage, 100% mutation) |
| `trajectory_tf.json` | TestForge baseline trajectory (90.1% coverage, smaller suite) |
| `constraint_memory.json` | Constraint Memory entries for SymPy |
| `refinement_memory.json` | JIT-retrieved Refinement Memory entries (cross-repo debugging insights) |

## Evidence

See `evidence_mapping.md` in parent directory for claim-to-evidence mapping.

Key evidence points:
- ShapeError triggers JIT Refinement Memory retrieval
- Retrieved entries from scikit-learn (relevance 0.71, 0.65) focus on operand shape compatibility
- Agent applies retrieved knowledge within 3 seconds
- Result: 92.6% coverage with 4,477 lines vs TestForge's 90.1% with 655 lines
