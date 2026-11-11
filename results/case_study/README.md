# RQ1 Case Studies

Two case studies demonstrating the complementary roles of EvoTest's dual-track memory system.

## Structure

```
case_study/
├── evidence_mapping.md              # Maps paper claims to raw evidence
├── case_study_self_consistency.json  # Cross-file consistency verification
├── case_A_sympy_13031/              # Constraint Memory case
│   ├── README.md
│   ├── trajectory_evo.json          # EvoTest agent trajectory
│   ├── trajectory_tf.json           # TestForge baseline trajectory
│   ├── constraint_memory.json       # Constraint Memory entries
│   └── refinement_memory.json       # Refinement Memory entries
└── case_B_sympy_12419/              # Refinement Memory case
    ├── README.md
    ├── trajectory_evo.json          # EvoTest agent trajectory
    ├── trajectory_tf.json           # TestForge baseline trajectory
    ├── constraint_memory.json       # Constraint Memory entries
    └── refinement_memory.json       # Refinement Memory entries
```

## Evidence Chain

```
Paper Claim → evidence_mapping.md → trajectory_*.json → *_memory.json
```

## Key Results

| Case | Instance | EvoTest Coverage | TestForge Coverage | Memory Type |
|------|----------|-----------------|-------------------|-------------|
| A | sympy__sympy-13031-146 | 86.9% | 0.0% | Constraint |
| B | sympy__sympy-12419-178 | 92.6% | 90.1% | Refinement |
