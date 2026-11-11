# Worked Example: Structural Constraint Extraction (`static_extractor.py`)

This document illustrates, end to end, what the structural analysis module of Sec. IV-A extracts from a repository file. The extraction is fully deterministic static analysis over the Python AST with no LLM involved. Everything below was produced by running the tool as-is from this artifact; the input file is synthetic and shown in full.

## Usage

```bash
python evotest_core/static_extractor.py <file_path>
```

## Input (`demo_parser.py`)

```python
"""Demo module for static extraction illustration."""
import os
import sympy
from requests import get

class ResultStore:
    """Stores parsed results keyed by run id."""

    def __init__(self, cache_size=128):
        self.cache_size = cache_size

    def lookup(self, key: str, default=None) -> dict:
        if not key:
            raise ValueError("key must be non-empty")
        return {"key": key, "default": default}

def parse_stream(stream, encoding="utf-8") -> int:
    count = 0
    for line in stream:
        if "FAIL" in line:
            raise RuntimeError("stream reported failure")
        count += 1
    return count
```

## Output (verbatim tool run)

```
=== STATIC ANALYSIS REPORT FOR: demo_parser.py ===

--- INTERNAL DEPENDENCIES ---
- requests
- sympy
-----------------------------

--- CODE STRUCTURE & SIGNATURES ---
class ResultStore:
    # Docstring: Stores parsed results keyed by run id.
    def __init__(self, cache_size = 128):
    def lookup(self, key: str, default = None) -> dict:
        # RAISES EXCEPTIONS: ValueError

def parse_stream(stream, encoding = 'utf-8') -> int:
    # RAISES EXCEPTIONS: RuntimeError
```

## How the output maps to the three constraint categories

1. **Dependency constraints** — the `INTERNAL DEPENDENCIES` block lists minimal non-stdlib imports (`requests`, `sympy`; `os` is filtered by the stdlib allowlist in `STD_LIB_MODULES`). The agent must honor these when writing executable tests for the module.

2. **Executable entry points** — the `CODE STRUCTURE & SIGNATURES` block lists class/function skeletons with exact signatures, parameter defaults (`cache_size = 128`, `encoding = 'utf-8'`), return annotations (`-> dict`, `-> int`), and docstring first lines. Only skeletons are emitted, so the context scales with the interface surface rather than the file size. These are the callable surfaces the agent may initialize or invoke when constructing tests.

3. **Failure-oriented constraints** — the `# RAISES EXCEPTIONS:` lines are collected from `raise` statements encountered inside each function body (`ValueError` in `ResultStore.lookup`, `RuntimeError` in `parse_stream`). They tell the agent which guard conditions exist and which exception types failure-oriented tests should trigger or expect.

The "expected behaviors" available statically are the docstring first lines plus the return annotations, as stated in the paper (Sec. IV-A).

## Scope notes

- The extraction is Python-specific and operates on AST-visible constructs. Dynamic constructs such as monkey-patching or metaclass-registered entry points fall outside AST visibility (Reviewer-C-Q1).
- The extractor never executes the target code; it is deterministic, so repeated runs on the same file yield identical output.
