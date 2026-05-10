param(
  [string]$ProjectRoot = "C:\Users\Raphael\Documents\JobRadarAI",
  [int]$MaxPerSource = 1200,
  [switch]$Judge,
  [int]$JudgeLimit = 1200,
  [int]$JudgeBatchSize = 10,
  [int]$JudgeConcurrency = 1,
  [int]$JudgeTimeoutSeconds = 360,
  [double]$JudgeMaxFallbackRatio = 0.01,
  [ValidateSet("auto", "sdk", "raw")]
  [string]$JudgeTransport = "auto",
  [int]$JudgeMaxAttempts = 3,
  [int]$JudgeRetrySeconds = 30,
  [switch]$JudgeRequired,
  [switch]$SkipLinkCheck,
  [int]$LinkCheckLimit = 160,
  [int]$LinkCheckTimeoutSeconds = 10,
  [int]$LinkCheckWorkers = 12,
  [switch]$SkipHistorySync,
  [int]$HistoryRecheckStaleLimit = 40,
  [switch]$NoSnapshot,
  [int]$LogRetentionDays = 45,
  [ValidateSet("top", "balanced", "wide", "vie", "all")]
  [string]$JudgeSelectionMode = "wide",
  [ValidateSet("none", "minimal", "low", "medium", "high", "xhigh")]
  [string]$JudgeEffort = "medium"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Set-Location $ProjectRoot
$logDir = Join-Path $ProjectRoot "runs\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if ($LogRetentionDays -gt 0) {
  $cutoff = (Get-Date).AddDays(-$LogRetentionDays)
  Get-ChildItem -Path $logDir -File -Filter "*.log" |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    Remove-Item -Force
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $logDir "run-$stamp.log"
$judgeFailureMessage = ""

function Invoke-LoggedNative {
  param(
    [Parameter(Mandatory = $true)]
    [string]$LogFile,
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $Executable @Arguments > $LogFile 2>&1
    return $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
}

$runExit = Invoke-LoggedNative -LogFile $logFile -Executable "uv" run --no-project --with-editable . -- python -m jobradai run --max-per-source $MaxPerSource
if ($runExit -ne 0) {
  throw "JobRadarAI run failed. See $logFile"
}
Get-Content $logFile

if ($Judge) {
  $judgeLog = Join-Path $logDir "judge-$stamp.log"
  $judgeOk = $false
  $attempts = [Math]::Max(1, $JudgeMaxAttempts)
  for ($attempt = 1; $attempt -le $attempts; $attempt++) {
    "attempt=$attempt/$attempts started=$(Get-Date -Format o)" | Out-File -FilePath $judgeLog -Encoding utf8 -Append
    $judgeAttemptLog = Join-Path $logDir "judge-$stamp-attempt-$attempt.log"
    $judgeExit = Invoke-LoggedNative -LogFile $judgeAttemptLog -Executable "uv" run --no-project --with-editable . -- python -m jobradai judge --limit $JudgeLimit --batch-size $JudgeBatchSize --concurrency $JudgeConcurrency --selection-mode $JudgeSelectionMode --effort $JudgeEffort --transport $JudgeTransport --timeout $JudgeTimeoutSeconds --max-fallback-ratio $JudgeMaxFallbackRatio
    Get-Content $judgeAttemptLog | Out-File -FilePath $judgeLog -Encoding utf8 -Append
    if ($judgeExit -eq 0) {
      $judgeOk = $true
      break
    }
    "attempt=$attempt/$attempts failed_exit=$judgeExit ended=$(Get-Date -Format o)" | Out-File -FilePath $judgeLog -Encoding utf8 -Append
    if ($attempt -lt $attempts) {
      Start-Sleep -Seconds ([Math]::Max(1, $JudgeRetrySeconds))
    }
  }
  if (-not $judgeOk) {
    $message = "JobRadarAI LLM judge failed after $attempts attempt(s). See $judgeLog"
    $message | Out-File -FilePath $judgeLog -Encoding utf8 -Append
    if ($JudgeRequired) {
      $judgeFailureMessage = $message
      Write-Warning $message
    } else {
      Write-Warning $message
    }
  } else {
    Get-Content $judgeLog
  }
}

if (-not $SkipLinkCheck) {
  $linkLog = Join-Path $logDir "links-$stamp.log"
  $linkExit = Invoke-LoggedNative -LogFile $linkLog -Executable "uv" run --no-project --with-editable . -- python -m jobradai verify-links --limit $LinkCheckLimit --timeout $LinkCheckTimeoutSeconds --workers $LinkCheckWorkers
  if ($linkExit -ne 0) {
    throw "JobRadarAI link verification failed. See $linkLog"
  }
  Get-Content $linkLog
}

if (-not $SkipHistorySync) {
  $historyLog = Join-Path $logDir "history-$stamp.log"
  $historyExit = Invoke-LoggedNative -LogFile $historyLog -Executable "uv" run --no-project --with-editable . -- python -m jobradai sync-history --run-name $stamp --recheck-stale-limit $HistoryRecheckStaleLimit --timeout $LinkCheckTimeoutSeconds --workers $LinkCheckWorkers
  if ($historyExit -ne 0) {
    throw "JobRadarAI history sync failed. See $historyLog"
  }
  Get-Content $historyLog
}

$auditLog = Join-Path $logDir "audit-$stamp.log"
$auditExit = Invoke-LoggedNative -LogFile $auditLog -Executable "uv" run --no-project --with-editable . -- python -m jobradai audit
if ($auditExit -ne 0) {
  throw "JobRadarAI audit failed. See $auditLog"
}
Get-Content $auditLog

if (-not $NoSnapshot) {
  $snapshotLog = Join-Path $logDir "snapshot-$stamp.log"
  $snapshotExit = Invoke-LoggedNative -LogFile $snapshotLog -Executable "uv" run --no-project --with-editable . -- python -m jobradai snapshot --name $stamp
  if ($snapshotExit -ne 0) {
    throw "JobRadarAI snapshot failed. See $snapshotLog"
  }
  Get-Content $snapshotLog
}

if ($judgeFailureMessage) {
  throw $judgeFailureMessage
}
