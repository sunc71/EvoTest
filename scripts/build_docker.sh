#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$REPO_ROOT/evotest_core/scripts/docker"

echo "=== Building EvoTest Docker Images ==="

# 1. Build curiositybench base image
echo "[1/2] Building curiositybench:latest..."
docker build -f "$DOCKER_DIR/Dockerfile.curiositybench" -t curiositybench:latest "$DOCKER_DIR"
echo "  -> curiositybench:latest built."

# 2. Build REB instance image
echo "[2/2] Building sweb.eval.x86_64.repo_explore_bench:latest..."
docker build -f "$DOCKER_DIR/Dockerfile.reb" -t sweb.eval.x86_64.repo_explore_bench:latest "$DOCKER_DIR"
echo "  -> sweb.eval.x86_64.repo_explore_bench:latest built."

echo ""
echo "=== Docker Images Built ==="
echo ""
echo "For testgeneval (SWE-bench Lite) instances, pull from DockerHub:"
echo "  bash scripts/pull_testgeneval_images.sh"
echo "  (Pulls 160 images from kdjain/ on DockerHub)"
