param(
    [string]$Namespace = "jobradarai",
    [switch]$IncludeState
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pod = kubectl get pod -n $Namespace -l app.kubernetes.io/name=jobradarai-web -o jsonpath="{.items[0].metadata.name}"
if (-not $pod) {
    throw "Pod jobradarai-web introuvable."
}

Push-Location $root
try {
    kubectl exec -n $Namespace $pod -- sh -lc "rm -rf /app/runs/latest && mkdir -p /app/runs /app/runs/cv"
    $target = "${Namespace}/${pod}"
    kubectl cp "runs/latest" "${target}:/app/runs/latest"

    if (Test-Path "private/main.tex") {
        kubectl cp "private/main.tex" "${target}:/app/runs/cv/main.tex"
    }
    if (Test-Path "private/main.pdf") {
        kubectl cp "private/main.pdf" "${target}:/app/runs/cv/main.pdf"
    }

    if ($IncludeState -and (Test-Path "runs/state/application_state.json")) {
        kubectl exec -n $Namespace $pod -- sh -lc "mkdir -p /app/runs/state"
        kubectl cp "runs/state/application_state.json" "${target}:/app/runs/state/application_state.json"
    }

    kubectl exec -n $Namespace $pod -- sh -lc "ls -la /app/runs/latest | head && ls -la /app/runs/cv"
}
finally {
    Pop-Location
}
