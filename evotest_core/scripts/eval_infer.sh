#!/bin/bash
set -eo pipefail

INPUT_FILE=$1
NUM_WORKERS=$2
DATASET=$3
SPLIT=$4
SKIP_MUTATION=$5
SKIP_LEXICAL=$6

if [ -z "$INPUT_FILE" ]; then
  echo "INPUT_FILE not specified (should be a path to a jsonl file)"
  exit 1
fi

if [ -z "$DATASET" ]; then
  echo "DATASET not specified, use default kjain14/testgenevallite"
  DATASET="kjain14/testgenevallite"
fi

if [ -z "$SPLIT" ]; then
  echo "SPLIT not specified, use default test"
  SPLIT="test"
fi

if [ -z "$NUM_WORKERS" ]; then
  echo "NUM_WORKERS not specified, use default 1"
  NUM_WORKERS=1
fi

# Default to NOT update memory
if [ -z "$ENABLE_MEMORY_UPDATE" ]; then
  ENABLE_MEMORY_UPDATE=false
fi
echo "ENABLE_MEMORY_UPDATE: $ENABLE_MEMORY_UPDATE"

if [ -n "$LLM_CONFIG" ]; then
  echo "LLM_CONFIG: $LLM_CONFIG"
fi

echo "... Evaluating on $INPUT_FILE ..."

COMMAND="python evotest_core/eval_infer.py \
  --eval-num-workers $NUM_WORKERS \
  --input-file $INPUT_FILE \
  --dataset $DATASET \
  --split $SPLIT"

if [ "$ENABLE_MEMORY_UPDATE" == "true" ]; then
  COMMAND="$COMMAND --enable-memory-update"
fi

if [ -n "$LLM_CONFIG" ]; then
  COMMAND="$COMMAND --llm-config $LLM_CONFIG"
fi

if [ "$SKIP_MUTATION" == "true" ]; then
  echo "Skipping mutation evaluation"
  COMMAND="$COMMAND --skip_mutation"
fi

if [ "$SKIP_LEXICAL" == "true" ]; then
  echo "Skipping lexical metrics"
  COMMAND="$COMMAND --skip_lexical"
fi

if [ -n "$EVAL_LIMIT" ]; then
  echo "EVAL_LIMIT: $EVAL_LIMIT"
  COMMAND="$COMMAND --eval-n-limit $EVAL_LIMIT"
fi

echo $COMMAND
# Run the command
eval $COMMAND

# update the output with evaluation results
# poetry run python evaluation/benchmarks/testgeneval/scripts/eval/update_output_with_eval.py $INPUT_FILE
