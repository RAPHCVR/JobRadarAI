param(
  [string]$ProjectRoot = "C:\Users\Raphael\Documents\JobRadarAI",
  [switch]$Refresh
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

if ($Refresh) {
  $env:PYTHONPATH = Join-Path $ProjectRoot "src"
  uv run --no-project --with-editable . -- python -m jobradai run --max-per-source 800
}

Start-Process (Join-Path $ProjectRoot "runs\latest\dashboard.html")
