# Panta (ICSE 2026)

## Repository
https://github.com/PANTA-TestAutomation/Panta

## Overview
Panta is an LLM-based test generation technique that integrates static control flow
analysis with dynamic coverage feedback. The released implementation targets Java projects.

## Observed Benchmark-Specific Assumptions

### Project Discovery
- Evaluation scripts hardcode a list of 14 Defects4J projects
  (`evaluation/execute_classes_with_high_complexity.py:130-132`)
- Project classes are loaded from a pre-computed CSV
  (`evaluation/data/class_list.csv`)
- Defects4J source trees are bundled in the repository
  (`defects4j-subjects-notests/`)

### Execution Pipeline
- Test execution uses Maven: `mvn clean package -Dtest=...`
  (`src/panta/config.ini:15`)
- JUnit version is hardcoded per project
  (`evaluation/execute_classes_pick_one.py:20-23`)
- Special-case handling for specific projects (Gson-16f, JxPath-22f)
  (`evaluation/execute_classes_with_high_complexity.py:16-29`)

### Coverage Collection
- Coverage is collected via JaCoCo (CSV + XML + HTML reports)
  (`src/panta/coverage/jacoco_coverage.py`)
- JaCoCo report paths assume Maven output structure
  (`src/panta/coverage/jacoco_parser.py:19,46,75`)
- Python coverage backend is declared but not implemented
  (`src/panta/coverage/pycov_coverage.py:9-10`, returns `None`)

### Evaluation Pipeline
- Evaluation scripts assume Defects4J directory layout
  (`evaluation/setup_d4j-subjects.sh:12-13`)
- Result parsing targets Defects4J-specific HTML report format
  (`evaluation/result-html-parser.py`)

## Summary
The released implementation assumes a Defects4J-based Java evaluation workflow,
including Maven-based execution, JaCoCo coverage collection,
and Defects4J project organization.

## Key Evidence
- `evaluation/execute_classes_with_high_complexity.py:130-132` — hardcoded project list
- `src/panta/config.ini:15` — Maven build command
- `src/panta/coverage/pycov_coverage.py:9-10` — Python coverage stub (returns `None`)
- `evaluation/execute_classes_pick_one.py:20-23` — JUnit version logic per project
