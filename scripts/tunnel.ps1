Set-Location (Join-Path $PSScriptRoot "..")
$domain = $env:NGROK_DOMAIN
if (-not $domain -and (Test-Path .env)) {
    $line = Get-Content .env | Where-Object { $_ -match '^NGROK_DOMAIN=' } | Select-Object -First 1
    if ($line) { $domain = ($line -split '=', 2)[1].Trim() }
}
if (-not $domain) { Write-Error "Set NGROK_DOMAIN in .env"; exit 1 }
ngrok http --url=$domain 8000
