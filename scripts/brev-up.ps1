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
# -join first: on an array, -match/-notmatch filters instead of returning a boolean.
$status = (Brev "ls") -join "`n"
($status -split "`n") | Select-String $instance
if ($status -notmatch "$instance\s+RUNNING") {
    Write-Host "==> starting $instance (a few minutes)" -ForegroundColor Cyan
    Brev "start $instance" | Out-Null
    foreach ($i in 1..60) {
        Start-Sleep -Seconds 10
        if (((Brev "ls") -join "`n") -match "$instance\s+RUNNING") { break }
    }
}

Write-Host "==> refreshing ssh and starting vLLM (a fresh box reinstalls, ~15 min)" -ForegroundColor Cyan
$repo = (wsl -d Ubuntu -- wslpath -a ("$PWD" -replace '\\', '/')).Trim()
# ssh chats on stderr (host keys, pty warnings); with ErrorActionPreference=Stop that would
# abort a working run, so judge this step by its exit code instead.
$ErrorActionPreference = "Continue"
wsl -d Ubuntu -- bash "$repo/scripts/brev_up.sh" $instance 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { Write-Error "brev_up.sh failed"; exit 1 }
$ErrorActionPreference = "Stop"

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
