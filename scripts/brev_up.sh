#!/usr/bin/env bash
# Runs inside WSL: copy the serve script to the Brev box and make sure vLLM is running.
# Usage: bash scripts/brev_up.sh <instance-name>
set -euo pipefail

INSTANCE="${1:?usage: brev_up.sh <instance>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"
# -T: no pty, so ssh does not warn on stderr (PowerShell treats that as a failure).
SSH=(ssh -T -F "$HOME/.brev/ssh_config" -o StrictHostKeyChecking=accept-new)

brev refresh >/dev/null 2>&1 || true

"${SSH[@]}" "$INSTANCE" 'cat > ~/brev_serve.sh && chmod +x ~/brev_serve.sh' \
  < "$REPO/scripts/brev_serve.sh"

"${SSH[@]}" "$INSTANCE" '
  if tmux has-session -t llm 2>/dev/null; then
    echo "vllm: already running"
  else
    tmux new -d -s llm "bash ~/brev_serve.sh 2>&1 | tee ~/llm.log"
    echo "vllm: started"
  fi'
