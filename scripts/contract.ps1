$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
uv run python scripts/export_contract.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm run contract --prefix frontend
exit $LASTEXITCODE
