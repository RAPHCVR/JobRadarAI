param(
  [string]$ProjectRoot = "C:\Users\Raphael\Documents\JobRadarAI",
  [int]$Limit = 160,
  [int]$TimeoutSeconds = 10,
  [int]$Workers = 12
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Set-Location $ProjectRoot

uv run --no-project --with-editable . -- python -m jobradai verify-links --limit $Limit --timeout $TimeoutSeconds --workers $Workers
if ($LASTEXITCODE -ne 0) {
  throw "JobRadarAI link verification failed."
}
