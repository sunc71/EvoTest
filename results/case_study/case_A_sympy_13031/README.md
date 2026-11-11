# Case A: Constraint Memory (sympy__sympy-13031-146)

**Paper Section**: Section V, Case A

**Claim**: Constraint Memory transfers repository-specific testing conventions that are prerequisite for test discovery.

## Files

| File | Description |
|------|-------------|
| `trajectory_evo.json` | Full EvoTest agent trajectory (75 bare functions, 86.9% coverage) |
| `trajectory_tf.json` | TestForge baseline trajectory (22 classes, 0% coverage due to test runner incompatibility) |
| `constraint_memory.json` | 25 Constraint Memory entries encoding SymPy testing conventions |
| `refinement_memory.json` | Refinement Memory entries (cross-repo debugging insights) |

## Evidence

See `evidence_mapping.md` in parent directory for claim-to-evidence mapping.

Key evidence points:
- Constraint Memory mandates bare functions, prohibits classes
- EvoTest generates 75 standalone `def test_*()` functions (0 classes)
- TestForge generates 22 classes with 70 methods (invisible to SymPy's `bin/test` runner)
- Result: 86.9% vs 0% line coverage
