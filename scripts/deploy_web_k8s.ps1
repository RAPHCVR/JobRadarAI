param(
    [string]$Image = "ghcr.io/raphcvr/jobradarai-web:latest",
    [string]$Namespace = "jobradarai",
    [string]$SourcePullSecretNamespace = "motus"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$manifestDir = Join-Path $root "deploy/k8s/jobradarai-web"

kubectl apply -f (Join-Path $manifestDir "namespace.yaml")

if (-not (kubectl get secret ghcr-secret -n $Namespace --ignore-not-found)) {
    $secretJson = kubectl get secret ghcr-secret -n $SourcePullSecretNamespace -o json | ConvertFrom-Json
    $secretJson.metadata.namespace = $Namespace
    $secretJson.metadata.resourceVersion = $null
    $secretJson.metadata.uid = $null
    $secretJson.metadata.creationTimestamp = $null
    $secretJson.metadata.annotations = $null
    $secretJson | ConvertTo-Json -Depth 100 | kubectl apply -f -
}

if (-not (kubectl get secret jobradarai-web-secret -n $Namespace --ignore-not-found)) {
    $password = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).TrimEnd("=")
    $sessionSecret = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48)).TrimEnd("=")
    $apiToken = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).TrimEnd("=")
    kubectl create secret generic jobradarai-web-secret -n $Namespace `
        --from-literal=JOBRADAR_WEB_PASSWORD=$password `
        --from-literal=JOBRADAR_WEB_SESSION_SECRET=$sessionSecret `
        --from-literal=JOBRADAR_WEB_API_TOKEN=$apiToken
    $stateDir = Join-Path $root "runs/state"
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    @"
url=https://jobs.raphcvr.me
namespace=$Namespace
password=$password
api_token=$apiToken
generated_at=$(Get-Date -Format o)
"@ | Set-Content -Path (Join-Path $stateDir "web_initial_credentials.txt") -Encoding UTF8
    Write-Host "Mot de passe web initial: $password"
}

kubectl apply -k $manifestDir
kubectl set image deployment/jobradarai-web web=$Image -n $Namespace
kubectl rollout status deployment/jobradarai-web -n $Namespace --timeout=180s
