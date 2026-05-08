param(
  [string]$ProjectRoot = "C:\Users\Raphael\Documents\JobRadarAI",
  [int]$Limit = 120,
  [int]$BatchSize = 5,
  [int]$TimeoutSeconds = 360,
  [ValidateSet("top", "balanced", "vie", "all")]
  [string]$SelectionMode = "balanced",
  [ValidateSet("none", "minimal", "low", "medium", "high", "xhigh")]
  [string]$Effort = "high"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Set-Location $ProjectRoot

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  uv run --no-project --with-editable . -- python -m jobradai judge --limit $Limit --batch-size $BatchSize --selection-mode $SelectionMode --effort $Effort --timeout $TimeoutSeconds
  $judgeExit = $LASTEXITCODE
} finally {
  $ErrorActionPreference = $previousErrorActionPreference
}
if ($judgeExit -ne 0) {
  throw "JobRadarAI LLM judge failed."
}
