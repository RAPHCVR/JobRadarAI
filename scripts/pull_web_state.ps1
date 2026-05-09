param(
    [string]$Namespace = "jobradarai",
    [string]$Output = "runs/state/application_state.from-web.json"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pod = kubectl get pod -n $Namespace -l app.kubernetes.io/name=jobradarai-web -o jsonpath="{.items[0].metadata.name}"
if (-not $pod) {
    throw "Pod jobradarai-web introuvable."
}

Push-Location $root
try {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
    $target = "${Namespace}/${pod}"
    kubectl exec -n $Namespace $pod -- sh -lc "test -f /app/runs/state/application_state.json" 2>$null
    if ($LASTEXITCODE -ne 0) {
        '{"version":1,"items":{}}' | Set-Content -Path $Output -Encoding UTF8
        Write-Host "Aucun etat web distant trouve; fichier vide cree dans $Output"
        return
    }
    kubectl cp "${target}:/app/runs/state/application_state.json" $Output
    Write-Host "Etat web copie vers $Output"
}
finally {
    Pop-Location
}
