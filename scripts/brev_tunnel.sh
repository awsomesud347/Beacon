#!/usr/bin/env bash
# Keeps localhost:8001 pointed at the Brev box's vLLM. Reconnects if the link drops —
# a dead tunnel is easy to miss, because answers quietly fall back to templates.
# Usage: bash scripts/brev_tunnel.sh <instance-name>
set -u

INSTANCE="${1:?usage: brev_tunnel.sh <instance>}"
export PATH="$HOME/.local/bin:$PATH"

while true; do
    echo "[$(date +%H:%M:%S)] connecting tunnel 8001 -> $INSTANCE:8000"
    ssh -T -F "$HOME/.brev/ssh_config" \
        -o StrictHostKeyChecking=accept-new \
        -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -N -L 8001:127.0.0.1:8000 "$INSTANCE"
    echo "[$(date +%H:%M:%S)] tunnel closed; retrying in 5s"
    sleep 5
done
