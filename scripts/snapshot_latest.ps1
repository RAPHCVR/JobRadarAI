param(
  [string]$ProjectRoot = "C:\Users\Raphael\Documents\JobRadarAI",
  [string]$Name = ""
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Set-Location $ProjectRoot

$argsList = @("-m", "jobradai", "snapshot")
if ($Name) {
  $argsList += @("--name", $Name)
}
uv run --no-project --with-editable . -- python @argsList
if ($LASTEXITCODE -ne 0) {
  throw "JobRadarAI snapshot failed."
}
