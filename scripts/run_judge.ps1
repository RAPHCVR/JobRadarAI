param(
  [string]$ProjectRoot = "C:\Users\Raphael\Documents\JobRadarAI",
  [int]$Limit = 1200,
  [int]$BatchSize = 10,
  [int]$Concurrency = 1,
  [int]$TimeoutSeconds = 360,
  [double]$MaxFallbackRatio = 0.01,
  [ValidateSet("auto", "sdk", "raw")]
  [string]$Transport = "auto",
  [ValidateSet("top", "balanced", "wide", "vie", "all")]
  [string]$SelectionMode = "wide",
  [ValidateSet("none", "minimal", "low", "medium", "high", "xhigh")]
  [string]$Effort = "medium"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Set-Location $ProjectRoot

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  uv run --no-project --with-editable . -- python -m jobradai judge --limit $Limit --batch-size $BatchSize --concurrency $Concurrency --selection-mode $SelectionMode --effort $Effort --transport $Transport --timeout $TimeoutSeconds --max-fallback-ratio $MaxFallbackRatio
  $judgeExit = $LASTEXITCODE
} finally {
  $ErrorActionPreference = $previousErrorActionPreference
}
if ($judgeExit -ne 0) {
  throw "JobRadarAI LLM judge failed."
}
