#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

export PYTHONPATH="${PYTHONPATH:-}:${REPO_ROOT}"
PYTHON_BIN="${PYTHON_BIN:-python}"

# vLLM OpenAI-compatible endpoint.
export OPENAI_API_KEY="${OPENAI_API_KEY:-dummy}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-http://10.102.65.40:8002/v1}"

# Cache directories. If an index is missing, LocAgent will build it on demand.
export GRAPH_INDEX_DIR="${GRAPH_INDEX_DIR:-index_data/SWE-bench_Lite/graph_index_v2.3}"
export BM25_INDEX_DIR="${BM25_INDEX_DIR:-index_data/SWE-bench_Lite/BM25_index}"

DATASET="${DATASET:-czlll/SWE-bench_Lite}"
SPLIT="${SPLIT:-test}"
MODEL="${MODEL:-openai/qwen-7B}"
EVAL_N_LIMIT="${EVAL_N_LIMIT:-1}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"
NUM_SAMPLES="${NUM_SAMPLES:-1}"
REPO_CACHE_MODE="${REPO_CACHE_MODE:-instance}"
OUTPUT_FOLDER="${OUTPUT_FOLDER:-test/swebenchlite-10/results_1/location}"

if [[ "${REPO_CACHE_MODE}" == "shared" && "${NUM_PROCESSES}" != "1" ]]; then
  echo "REPO_CACHE_MODE=shared requires NUM_PROCESSES=1" >&2
  exit 1
fi

mkdir -p "${OUTPUT_FOLDER}"

"${PYTHON_BIN}" auto_search_main.py \
  --dataset "${DATASET}" \
  --split "${SPLIT}" \
  --model "${MODEL}" \
  --localize \
  --merge \
  --output_folder "${OUTPUT_FOLDER}" \
  --eval_n_limit "${EVAL_N_LIMIT}" \
  --num_processes "${NUM_PROCESSES}" \
  --num_samples "${NUM_SAMPLES}" \
  --repo_cache_mode "${REPO_CACHE_MODE}" \
  --use_function_calling \
  --simple_desc
