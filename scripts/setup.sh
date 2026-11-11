#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== EvoTest Environment Setup ==="

# 1. Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
echo "[1/5] Python version: $PYTHON_VERSION"

# 2. Check/install Poetry
if ! command -v poetry &> /dev/null; then
    echo "[2/5] Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "[2/5] Poetry found: $(poetry --version)"
fi

# 3. Install OpenHands Python dependencies via Poetry
echo "[3/5] Installing OpenHands dependencies (poetry install)..."
cd "$REPO_ROOT/openhands"
poetry install --no-root --no-interaction 2>&1 | tail -5
cd "$REPO_ROOT"

# 4. Install additional evaluation dependencies
echo "[4/5] Installing additional dependencies..."
poetry -C "$REPO_ROOT/openhands" run pip install datasets nltk rouge-score fuzzywuzzy python-Levenshtein 2>&1 | tail -3
poetry -C "$REPO_ROOT/openhands" run python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True)" 2>/dev/null || true

# 5. Create config.toml if not exists
CONFIG_FILE="$REPO_ROOT/config.toml"
CONFIG_EXAMPLE="$REPO_ROOT/config.toml.example"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "[5/5] Creating config.toml from template..."
    if [ -f "$CONFIG_EXAMPLE" ]; then
        cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
    else
        cat > "$CONFIG_FILE" << 'EOF'
[llm]
# Set your model and API key here, or use environment variables:
#   export OPENAI_API_KEY="sk-xxx"
# model = "gpt-4o"
# api_key = "sk-xxx"

[llm.eval_default]
# Configuration for --llm-config eval_default
# model = "gpt-4o"
# api_key = "sk-xxx"
# temperature = 0.0
EOF
    fi
    echo "  -> Created $CONFIG_FILE"
    echo "  -> Please edit it to set your LLM model and API key."
else
    echo "[5/5] config.toml already exists, skipping."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit config.toml to set your LLM model and API key"
echo "     (or: export OPENAI_API_KEY='sk-xxx')"
echo "  2. Build Docker images for evaluation:"
echo "     bash scripts/build_docker.sh"
echo "  3. Run: bash scripts/run.sh --llm-config eval_default --eval-n-limit 3"
