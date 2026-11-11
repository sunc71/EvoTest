# CoverUp (FSE 2025)

## Repository
- Evaluation artifact: https://github.com/plasma-umass/coverup-eval
- Standalone tool: https://github.com/plasma-umass/coverup

## Overview
CoverUp is a coverage-driven LLM-based test generation tool for Python.
Two repositories are associated with this work: the standalone CLI tool
and the evaluation artifact used to reproduce the paper's results.

## Note: Standalone CLI vs Evaluation Artifact

The standalone CoverUp CLI (`pip install coverup`) provides a general-purpose interface:
- `coverup --package src/flask --tests tests` (`coverup-tool/README.md:53-56`)
- Accepts arbitrary Python repositories via `--package-dir` / `--source-dir`
  (`coverup-tool/src/coverup/coverup.py:60-62`)
- No CodaMosa or benchmark dependency in tool source code

Unless otherwise specified, the observations below refer to the released
evaluation artifact (`coverup-eval`), which is the publicly released
implementation used to reproduce the experimental results reported in the paper.

## Observed Benchmark-Specific Assumptions (Evaluation Artifact)

### Project Discovery
- Project list is loaded from CodaMosa's CSV metadata
  (`scripts/eval_coverup.py:62`: `modules_csv = test_apps / f"{suite}_modules.csv"`)
- Project paths assume CodaMosa's test-apps directory layout
  (`scripts/eval_coverup.py:7`: `test_apps = Path("codamosa/replication/test-apps")`)
- Suite selection is limited to CodaMosa/MuTAP suites
  (`scripts/eval_coverup.py:23`: `choices=['cm', '1_0', 'mutap']`)

### Execution Pipeline
- All CoverUp execution occurs inside a Docker container
  (`scripts/eval_coverup.py:123`: `docker run --rm ... coverup-runner bash ...`)
- The Docker image is provided as a pre-built tarball
  (`docker/coverup-runner.tar.bz2`)
- CoverUp runs 3 times per project with checkpoint reuse
  (`scripts/run_coverup.sh:64-74`)

### Coverage Collection
- Coverage is measured via SlipCover
  (`scripts/run_coverup.sh:79`: `python3 -m slipcover --source $SRC/$PKG --branch --json --out final.json -m pytest`)

### Evaluation Pipeline
- Result comparison assumes CodaMosa/MuTAP output layout
  (`scripts/compare.py`)
- Analysis scripts (`cost.py`, `time.py`, `sequences.py`) assume the same directory structure

## Summary
The released evaluation artifact assumes the CodaMosa/MuTAP evaluation infrastructure,
whereas the standalone CoverUp CLI exposes a general-purpose interface
for arbitrary Python repositories.

## Key Evidence
- `scripts/eval_coverup.py:62` — CSV-driven project discovery
- `scripts/eval_coverup.py:7` — hardcoded CodaMosa path
- `scripts/eval_coverup.py:123` — Docker-based execution
- `scripts/run_coverup.sh:79` — SlipCover coverage collection
- `coverup-tool/README.md:53-56` — general-purpose CLI example
- `coverup-tool/src/coverup/coverup.py:60-62` — arbitrary path arguments
