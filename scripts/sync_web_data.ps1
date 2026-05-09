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

kubectl exec -n $Namespace $pod -- sh -lc "rm -rf /app/runs/latest && mkdir -p /app/runs /app/runs/cv"
$target = "${Namespace}/${pod}"
kubectl cp (Join-Path $root "runs/latest") "${target}:/app/runs/latest"

$cvTex = Join-Path $root "private/main.tex"
$cvPdf = Join-Path $root "private/main.pdf"
if (Test-Path $cvTex) {
    kubectl cp $cvTex "${target}:/app/runs/cv/main.tex"
}
if (Test-Path $cvPdf) {
    kubectl cp $cvPdf "${target}:/app/runs/cv/main.pdf"
}

if ($IncludeState) {
    $state = Join-Path $root "runs/state/application_state.json"
    if (Test-Path $state) {
        kubectl exec -n $Namespace $pod -- sh -lc "mkdir -p /app/runs/state"
        kubectl cp $state "${target}:/app/runs/state/application_state.json"
    }
}

kubectl exec -n $Namespace $pod -- sh -lc "ls -la /app/runs/latest | head && ls -la /app/runs/cv"
