#!/usr/bin/env bash
# Run ON the Brev GPU instance. Serves Nemotron 3 Nano 4B behind an OpenAI-compatible API
# on port 8000, protected by an API key. Usage: BEACON_LLM_KEY=<secret> bash brev_serve.sh
set -euo pipefail

MODEL="${MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16}"
SERVED_NAME="${SERVED_NAME:-nemotron-nano-4b}"
: "${BEACON_LLM_KEY:?set BEACON_LLM_KEY to the key the Beacon backend will send}"

if ! python3 -c "import vllm, sys; from packaging.version import Version as V; \
sys.exit(V(vllm.__version__) < V('0.15.1'))" 2>/dev/null; then
  pip install -U "vllm>=0.15.1"
fi

PARSER=nano_v3_reasoning_parser.py
[ -f "$PARSER" ] || wget -q "https://huggingface.co/${MODEL}/resolve/main/${PARSER}"

exec vllm serve "$MODEL" \
  --served-model-name "$SERVED_NAME" \
  --api-key "$BEACON_LLM_KEY" \
  --host 127.0.0.1 \
  --port 8000 \
  --max-model-len 8192 \
  --max-num-seqs 8 \
  --trust-remote-code \
  --mamba_ssm_cache_dtype float32 \
  --reasoning-parser-plugin "$PARSER" \
  --reasoning-parser nano_v3
