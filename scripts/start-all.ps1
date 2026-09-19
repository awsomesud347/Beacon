# Start everything for a working session: backend, frontend, ngrok. Each runs in its own
# window so you can watch or kill it. Add -Brev to also bring the GPU box and tunnel up.
param([switch]$Brev)

Set-Location (Join-Path $PSScriptRoot "..")

function Get-EnvValue([string]$name) {
    $line = Get-Content .env | Where-Object { $_ -match "^$name=" } | Select-Object -First 1
    if ($line) { ($line -split '=', 2)[1].Trim() }
}

function Test-Port([int]$port) {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Start-Window([string]$title, [string]$command) {
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command', "`$host.UI.RawUI.WindowTitle='$title'; Set-Location '$PWD'; $command"
    )
}

if ($Brev) { & "$PSScriptRoot\brev-up.ps1" }

if (Test-Port 8000) { Write-Host "backend already on :8000" } else {
    Start-Window "beacon backend" ".venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000"
}
if (Test-Port 5173) { Write-Host "frontend already on :5173" } else {
    Start-Window "beacon frontend" "npm run dev --prefix frontend"
}
if (Test-Port 4040) { Write-Host "ngrok already running" } else {
    $domain = Get-EnvValue 'NGROK_DOMAIN'
    if ($domain) { Start-Window "beacon ngrok" "ngrok http --url=$domain 8000" }
    else { Write-Warning "NGROK_DOMAIN not set; voice will not reach this machine" }
}

Write-Host "`n==> checking" -ForegroundColor Cyan
foreach ($i in 1..40) { if (Test-Port 8000) { break }; Start-Sleep -Milliseconds 500 }

$domain = Get-EnvValue 'NGROK_DOMAIN'
$checks = @(
    @{ name = 'backend   '; url = 'http://localhost:8000/api/health' },
    @{ name = 'frontend  '; url = 'http://localhost:5173' }
)
if ($domain) { $checks += @{ name = 'public url'; url = "https://$domain/api/health" } }

foreach ($c in $checks) {
    try {
        $r = Invoke-WebRequest -Uri $c.url -TimeoutSec 15 -UseBasicParsing -Headers @{ 'ngrok-skip-browser-warning' = '1' }
        Write-Host ("{0} OK ({1})" -f $c.name, $r.StatusCode) -ForegroundColor Green
    } catch {
        Write-Host ("{0} FAILED {1}" -f $c.name, $c.url) -ForegroundColor Red
    }
}

try {
    $h = (Invoke-WebRequest -Uri 'http://localhost:8000/api/health' -TimeoutSec 10 -UseBasicParsing).Content | ConvertFrom-Json
    Write-Host ("narrator={0} demo_mode={1} rows={2}" -f $h.narrator, $h.demo_mode, $h.dataset.row_count)
    if ($h.narrator -eq 'local' -and -not (Test-Port 8001)) {
        Write-Warning "NARRATOR=local but the Brev tunnel is down - answers will fall back to templates. Run scripts\brev-up.ps1"
    }
} catch { }

Write-Host "`nOpen http://localhost:5173" -ForegroundColor Cyan
