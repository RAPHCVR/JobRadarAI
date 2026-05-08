param(
  [string]$ProjectRoot = "C:\Users\Raphael\Documents\JobRadarAI",
  [int]$RecheckStaleLimit = 40,
  [int]$TimeoutSeconds = 10,
  [int]$Workers = 8,
  [string]$RunName = ""
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Set-Location $ProjectRoot

$argsList = @("-m", "jobradai", "sync-history", "--recheck-stale-limit", $RecheckStaleLimit, "--timeout", $TimeoutSeconds, "--workers", $Workers)
if ($RunName) {
  $argsList += @("--run-name", $RunName)
}
uv run --no-project --with-editable . -- python @argsList
if ($LASTEXITCODE -ne 0) {
  throw "JobRadarAI history sync failed."
}
