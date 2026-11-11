# TestWeaver (ICSE 2026)

## Repository
https://github.com/FSoft-AI4Code/TestWeaver

## Overview
TestWeaver is an LLM-based regression test generation approach that uses
backward slicing, execution tracing, and closest-test retrieval to guide test generation.
The released implementation targets Python projects.

## Observed Benchmark-Specific Assumptions

### Project Discovery
- Project list is loaded from CodaMosa's CSV metadata
  (`scripts/testweaver.py:179`: `modules_csv = test_apps / f"{suite}_modules.csv"`)
- Project paths assume CodaMosa's test-apps directory layout
  (`scripts/testweaver.py:27`: `test_apps = Path("../codamosa/replication/test-apps")`)
- Suite selection is limited to CodaMosa-defined suites
  (`scripts/testweaver.py:126`: `choices=['cm', '1_0', 'mutap']`)

### Execution Pipeline
- Test execution uses pytest via a custom trace module
  (`scripts/trace_execution.py`)
- The `load_suite()` function is duplicated across 4 entry-point files
  (`testweaver.py:168`, `ablate.py`, `ablate_choose_test.py`, `proposed.py`)

### Coverage Collection
- Coverage is measured via a customized Python `trace` module
  (`scripts/trace_execution.py`, based on stdlib `trace`)
- SlipCover is used only for baseline evaluation, not by TestWeaver itself
  (`requirements.txt`: `slipcover==1.0.14`)

### Evaluation Pipeline
- Evaluation is orchestrated through benchmark-specific scripts
  (`scripts/testweaver.py`, `scripts/ablate.py`)
- Output directory structure follows `{suite}/{package}/` layout
  (`scripts/testweaver.py:947`)
- Git submodules reference CodaMosa, CoverUp, and MuTAP repositories
  (`.gitmodules`)

## Summary
The released implementation assumes the CodaMosa benchmark layout,
with project discovery driven by benchmark metadata
and evaluation orchestrated through the released benchmark scripts.

## Key Evidence
- `scripts/testweaver.py:27` — hardcoded CodaMosa path
- `scripts/testweaver.py:179` — CSV-driven project discovery
- `scripts/testweaver.py:126` — suite choices limited to cm/1_0/mutap
- `.gitmodules` — submodules for codamosa, coverup, MuTAP
