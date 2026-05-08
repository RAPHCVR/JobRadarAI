param(
  [string]$ProjectRoot = "C:\Users\Raphael\Documents\JobRadarAI"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Set-Location $ProjectRoot

uv run --no-project --with-editable . -- python -m jobradai audit
if ($LASTEXITCODE -ne 0) {
  throw "JobRadarAI audit failed."
}
