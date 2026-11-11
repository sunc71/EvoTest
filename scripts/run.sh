#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

export PYTHONPATH="$REPO_ROOT/openhands:$REPO_ROOT:$PYTHONPATH"

# Run from the repository root so that ./config.toml is the file OpenHands reads.
cd "$REPO_ROOT"

if command -v poetry >/dev/null 2>&1 && [ -f "$REPO_ROOT/openhands/pyproject.toml" ]; then
  VENV_PY="$(poetry -C "$REPO_ROOT/openhands" env info --executable)"
  exec "$VENV_PY" -m evotest_core.run_continual_loop "$@"
fi

exec python -m evotest_core.run_continual_loop "$@"
