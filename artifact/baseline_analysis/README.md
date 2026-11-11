# Baseline Implementation Inspection

This directory documents our inspection of publicly released baseline implementations
to understand the assumptions made by their released evaluation infrastructures.

The inspection summarizes benchmark assumptions, project discovery mechanisms,
execution pipelines, coverage collection, and evaluation harnesses.

These observations informed the baseline selection described in Section 5 (Evaluation).

## Summary

| Method     | Primary Evaluation Benchmark | Target Language | Public Release                       |
|------------|------------------------------|-----------------|--------------------------------------|
| Panta      | Defects4J                    | Java            | Source code + evaluation scripts     |
| TestWeaver | CodaMosa suite               | Python          | Source code + evaluation scripts     |
| CoverUp    | CodaMosa / MuTAP             | Python          | Evaluation artifact + standalone CLI |

## Scope

This inspection focuses on the publicly released repositories accompanying each paper.
It does not evaluate unpublished implementations,
nor does it modify or reimplement released methods
for alternative benchmark infrastructures.
