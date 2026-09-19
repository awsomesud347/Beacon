Set-Location (Join-Path $PSScriptRoot "..")
$instance = $env:BREV_INSTANCE
if (-not $instance -and (Test-Path .env)) {
    $line = Get-Content .env | Where-Object { $_ -match '^BREV_INSTANCE=' } | Select-Object -First 1
    if ($line) { $instance = ($line -split '=', 2)[1].Trim() }
}
if (-not $instance) { Write-Error "Set BREV_INSTANCE in .env"; exit 1 }
# Brev CLI lives in WSL; WSL2 forwards localhost:8001 to Windows.
wsl -d Ubuntu -- bash -lc "~/.local/bin/brev port-forward $instance --port 8001:8000"
