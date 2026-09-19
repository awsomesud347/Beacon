Set-Location (Join-Path $PSScriptRoot "..")
$failed = @()

function Step($name, [scriptblock]$cmd) {
    Write-Host "==> $name" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) { $script:failed += $name }
}

Step "ruff" { uv run ruff check backend tests scripts data }
Step "pytest" { uv run pytest -q }
Step "frontend lint" { npm run lint --prefix frontend }
Step "frontend test" { npm run test --prefix frontend }
Step "frontend build" { npm run build --prefix frontend }

if ($failed.Count -gt 0) {
    Write-Host "FAILED: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "All checks passed" -ForegroundColor Green
