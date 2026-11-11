#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
IMAGE_LIST="$REPO_ROOT/evotest_core/scripts/docker/all-swebench-lite-instance-images.txt"
PREFIX="docker.io/kdjain/"

echo "=== Pulling TestGenEval Lite Docker Images ==="
echo "Prefix: $PREFIX"
echo ""

# Filter only sweb.eval instance images (skip base/env images)
IMAGES=$(grep "^sweb.eval" "$IMAGE_LIST" 2>/dev/null || true)

if [ -z "$IMAGES" ]; then
    echo "No instance images found in $IMAGE_LIST"
    exit 1
fi

TOTAL=$(echo "$IMAGES" | wc -l)
echo "Found $TOTAL instance images to pull."
echo ""

COUNT=0
FAILED=0
while IFS= read -r image; do
    COUNT=$((COUNT + 1))
    FULL="${PREFIX}${image}"
    echo "[$COUNT/$TOTAL] Pulling $FULL ..."
    if docker pull "$FULL" 2>&1 | tail -1; then
        :
    else
        echo "  WARNING: Failed to pull $FULL"
        FAILED=$((FAILED + 1))
    fi
done <<< "$IMAGES"

echo ""
echo "=== Done ==="
echo "Pulled: $((COUNT - FAILED))/$TOTAL"
if [ "$FAILED" -gt 0 ]; then
    echo "Failed: $FAILED (may need manual retry)"
fi
