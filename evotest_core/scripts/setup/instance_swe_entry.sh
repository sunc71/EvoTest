#!/bin/bash

source ~/.bashrc
SWEUTIL_DIR=/swe_util

# FIXME: Cannot read SWE_INSTANCE_ID from the environment variable
# SWE_INSTANCE_ID=django__django-11099
if [ -z "$SWE_INSTANCE_ID" ]; then
    echo "Error: SWE_INSTANCE_ID is not set." >&2
    exit 1
fi

# Read the swe-bench-test-lite.json file and extract the required item based on instance_id
item=$(jq --arg INSTANCE_ID "$SWE_INSTANCE_ID" '.[] | select(.instance_id == $INSTANCE_ID)' $SWEUTIL_DIR/eval_data/instances/swe-bench-instance.json)

if [[ -z "$item" ]]; then
  echo "No item found for the provided instance ID."
  exit 1
fi

WORKSPACE_NAME=$(echo "$item" | jq -r '(.repo | tostring) + "__" + (.version | tostring) | gsub("/"; "__")')

echo "WORKSPACE_NAME: $WORKSPACE_NAME"

# Ensure /testbed exists (newer swe-bench images use REPO_DIR instead of /testbed)
if [ ! -d /testbed ]; then
    if [ -n "$REPO_DIR" ] && [ -d "$REPO_DIR" ]; then
        ln -s "$REPO_DIR" /testbed
        echo "Created /testbed -> $REPO_DIR"
    else
        # Fallback: try to find the repo directory
        candidate=$(find /home/swe-bench -maxdepth 2 -name ".git" -type d 2>/dev/null | head -1)
        if [ -n "$candidate" ]; then
            ln -s "$(dirname "$candidate")" /testbed
            echo "Created /testbed -> $(dirname "$candidate")"
        fi
    fi
fi

# Clear the workspace
if [ -d /workspace ]; then
    rm -rf /workspace/*
else
    mkdir /workspace
fi
# Copy repo to workspace
if [ -d /workspace/$WORKSPACE_NAME ]; then
    rm -rf /workspace/$WORKSPACE_NAME
fi
mkdir -p /workspace
ln -s /testbed /workspace/$WORKSPACE_NAME

# Activate instance-specific environment
if [ -f /opt/miniconda3/etc/profile.d/conda.sh ]; then
    . /opt/miniconda3/etc/profile.d/conda.sh
elif [ -f /home/swe-bench/miniconda3/etc/profile.d/conda.sh ]; then
    . /home/swe-bench/miniconda3/etc/profile.d/conda.sh
fi
conda activate testbed 2>/dev/null || true
