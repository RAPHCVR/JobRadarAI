param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $env:PYTHONPATH = "src"
    if (-not $env:JOBRADAR_WEB_PASSWORD) {
        $env:JOBRADAR_WEB_AUTH = "off"
    }
    python -m jobradai web --host $HostName --port $Port
}
finally {
    Pop-Location
}
