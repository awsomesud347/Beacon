# Bring the self-hosted Nemotron back up: start the instance, refresh SSH, run vLLM in tmux,
# then open the tunnel on localhost:8001. Safe to re-run; each step is idempotent.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$instance = $env:BREV_INSTANCE
if (-not $instance -and (Test-Path .env)) {
    $line = Get-Content .env | Where-Object { $_ -match '^BREV_INSTANCE=' } | Select-Object -First 1
    if ($line) { $instance = ($line -split '=', 2)[1].Trim() }
}
if (-not $instance) { Write-Error "Set BREV_INSTANCE in .env"; exit 1 }

function Brev([string]$cmd) { wsl -d Ubuntu -- bash -lc "~/.local/bin/brev $cmd" }

Write-Host "==> instance status" -ForegroundColor Cyan
$status = Brev "ls"
$status | Select-String $instance
if ($status -notmatch "$instance\s+RUNNING") {
    Write-Host "==> starting $instance (a few minutes)" -ForegroundColor Cyan
    Brev "start $instance --wait"
}

Write-Host "==> refreshing ssh config (the IP changes on restart)" -ForegroundColor Cyan
Brev "refresh" | Out-Null

Write-Host "==> starting vLLM in tmux (first run after a wipe reinstalls, ~15 min)" -ForegroundColor Cyan
$remote = @'
mkdir -p ~/ && cat > ~/brev_serve.sh && chmod +x ~/brev_serve.sh
tmux has-session -t llm 2>/dev/null && echo "already running" || \
  tmux new -d -s llm "bash ~/brev_serve.sh 2>&1 | tee ~/llm.log"
'@
$remote = $remote -replace "`r`n", "`n"
wsl -d Ubuntu -- bash -lc "ssh -F ~/.brev/ssh_config -o StrictHostKeyChecking=accept-new $instance '$remote' < scripts/brev_serve.sh"

Write-Host "==> opening tunnel on localhost:8001" -ForegroundColor Cyan
Start-Process wsl -ArgumentList @(
    '-d', 'Ubuntu', '--', 'bash', '-lc',
    "ssh -F ~/.brev/ssh_config -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -N -L 8001:127.0.0.1:8000 $instance"
) -WindowStyle Minimized

$key = (Get-Content .env | Where-Object { $_ -match '^LOCAL_LLM_API_KEY=' } | Select-Object -First 1)
$key = ($key -split '=', 2)[1].Trim()
Write-Host "==> waiting for the model to answer" -ForegroundColor Cyan
foreach ($i in 1..60) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8001/v1/models" -Headers @{ Authorization = "Bearer $key" } `
             -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { Write-Host "Nemotron is up on localhost:8001" -ForegroundColor Green; exit 0 }
    } catch { Start-Sleep -Seconds 10 }
}
Write-Error "Model did not come up. Check: wsl -d Ubuntu -- bash -lc 'ssh -F ~/.brev/ssh_config $instance ""tail -30 ~/llm.log""'"
exit 1
