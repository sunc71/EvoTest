# artifact/

Artifact materials for the ICSE 2027 submission.

## Contents

| Directory | Description |
|-----------|-------------|
| `baseline_analysis/` | Inspection of publicly released baseline implementations (Panta, TestWeaver, CoverUp) |

## Baseline Exclusion Rationale

The baseline analysis documents why three recent baselines are not included as direct comparisons in our evaluation:

| Method | Reason for Exclusion |
|--------|---------------------|
| **Panta** | Targets Java (Defects4J); no Python evaluation infrastructure |
| **TestWeaver** | Tightly coupled to CodaMosa benchmark suite |
| **CoverUp** | Evaluation protocol coupled with CodaMosa/MuTAP benchmarks |

See `baseline_analysis/` for detailed inspection reports.
