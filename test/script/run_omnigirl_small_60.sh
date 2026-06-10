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

# OmniGIRL is not in LocAgent's built-in dataset cache map, so enable the
# repository cache explicitly for this benchmark.
export LOCAGENT_REPO_CACHE_DIR="${LOCAGENT_REPO_CACHE_DIR:-repo_omnigirl}"

# Cache directories. If an index is missing, LocAgent will build it on demand.
export GRAPH_INDEX_DIR="${GRAPH_INDEX_DIR:-index_data/OmniGIRL/graph_index_v2.3}"
export BM25_INDEX_DIR="${BM25_INDEX_DIR:-index_data/OmniGIRL/BM25_index}"

DATASET="${DATASET:-Deep-Software-Analytics/OmniGIRL}"
SPLIT="${SPLIT:-test}"
USED_LIST="${USED_LIST:-omnigirl_small_60}"
USED_LIST_CONFIG="${USED_LIST_CONFIG:-test/OmniGIRL/config.omnigirl_small_60.toml}"
MODEL="${MODEL:-openai/qwen-7B}"
NUM_PROCESSES="${NUM_PROCESSES:-1}"
NUM_SAMPLES="${NUM_SAMPLES:-1}"
EVAL_N_LIMIT="${EVAL_N_LIMIT:-0}"
REPO_CACHE_MODE="${REPO_CACHE_MODE:-shared}"
OUTPUT_FOLDER="${OUTPUT_FOLDER:-test/OmniGIRL/results_small_60/location}"

if [[ "${REPO_CACHE_MODE}" == "shared" && "${NUM_PROCESSES}" != "1" ]]; then
  echo "REPO_CACHE_MODE=shared requires NUM_PROCESSES=1" >&2
  exit 1
fi

if [[ ! -f "${USED_LIST_CONFIG}" ]]; then
  echo "Missing used-list config: ${USED_LIST_CONFIG}" >&2
  exit 1
fi

CONFIG_FILE="config.toml"
CONFIG_BACKUP=""
if [[ -f "${CONFIG_FILE}" ]]; then
  CONFIG_BACKUP="$(mktemp)"
  cp "${CONFIG_FILE}" "${CONFIG_BACKUP}"
fi

restore_config() {
  if [[ -n "${CONFIG_BACKUP}" && -f "${CONFIG_BACKUP}" ]]; then
    cp "${CONFIG_BACKUP}" "${CONFIG_FILE}"
    rm -f "${CONFIG_BACKUP}"
  else
    rm -f "${CONFIG_FILE}"
  fi
}
trap restore_config EXIT INT TERM

CONFIG_FILE="${CONFIG_FILE}" USED_LIST_CONFIG="${USED_LIST_CONFIG}" "${PYTHON_BIN}" - <<'PY'
import os
import toml

config_file = os.environ["CONFIG_FILE"]
used_list_config = os.environ["USED_LIST_CONFIG"]

config = {}
if os.path.exists(config_file):
    config = toml.load(config_file)
config.update(toml.load(used_list_config))

with open(config_file, "w", encoding="utf-8") as f:
    toml.dump(config, f)
PY

mkdir -p "${OUTPUT_FOLDER}"

"${PYTHON_BIN}" auto_search_main.py \
  --dataset "${DATASET}" \
  --split "${SPLIT}" \
  --used_list "${USED_LIST}" \
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
