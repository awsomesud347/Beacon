#!/usr/bin/env bash
# Run ON the Brev GPU instance. Serves Nemotron 3 Nano 4B behind an OpenAI-compatible API on
# 127.0.0.1:8000 (reach it via `brev port-forward <instance> --port 8001:8000`), protected by
# an API key read from $BEACON_LLM_KEY or ~/.beacon_llm_key.
set -euo pipefail

MODEL="${MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16}"
SERVED_NAME="${SERVED_NAME:-nemotron-nano-4b}"
VENV="${VENV:-$HOME/beacon-llm}"
WORKDIR="${WORKDIR:-$HOME/beacon-llm-work}"

KEY="${BEACON_LLM_KEY:-$(cat "$HOME/.beacon_llm_key" 2>/dev/null || true)}"
[ -n "$KEY" ] || { echo "set BEACON_LLM_KEY or write it to ~/.beacon_llm_key" >&2; exit 1; }

export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
# Triton / torch.compile JIT-compile kernels at startup and need a C compiler.
command -v gcc >/dev/null || sudo -n apt-get install -y build-essential

if [ ! -x "$VENV/bin/vllm" ]; then
  uv venv --python 3.12 "$VENV"
  uv pip install --python "$VENV/bin/python" "vllm>=0.15.1"
fi

mkdir -p "$WORKDIR" && cd "$WORKDIR"
PARSER=nano_v3_reasoning_parser.py
[ -f "$PARSER" ] || curl -fsSLO "https://huggingface.co/${MODEL}/resolve/main/${PARSER}"

exec "$VENV/bin/vllm" serve "$MODEL" \
  --served-model-name "$SERVED_NAME" \
  --api-key "$KEY" \
  --host 127.0.0.1 \
  --port 8000 \
  --max-model-len 8192 \
  --max-num-seqs 8 \
  --trust-remote-code \
  --mamba_ssm_cache_dtype float32 \
  --reasoning-parser-plugin "$PARSER" \
  --reasoning-parser nano_v3
