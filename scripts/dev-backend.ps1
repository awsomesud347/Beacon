Set-Location (Join-Path $PSScriptRoot "..")
uv run uvicorn backend.main:app --reload --port 8000
