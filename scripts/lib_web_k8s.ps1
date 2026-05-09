function Get-JobRadarWebPod {
    param(
        [string]$Namespace = "jobradarai"
    )

    $payload = kubectl get pod -n $Namespace -l app.kubernetes.io/name=jobradarai-web -o json | ConvertFrom-Json
    $pod = $payload.items |
        Where-Object {
            $_.status.phase -eq "Running" -and
            ($_.status.containerStatuses | Where-Object { $_.ready -eq $true } | Select-Object -First 1)
        } |
        Sort-Object { $_.metadata.creationTimestamp } -Descending |
        Select-Object -First 1

    if (-not $pod) {
        throw "Pod jobradarai-web Running/Ready introuvable."
    }
    return $pod.metadata.name
}
