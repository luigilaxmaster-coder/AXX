param(
    [string]$ConfigFile = "2.analisis e integracion profunda/baseline/axx-api-router/providers.example.json",
    [string]$StateFile = "state.db",
    [string]$RequestFile = "2.analisis e integracion profunda/baseline/axx-api-router/request.example.json",
    [string]$Action = "status"
)

$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if ($Action -eq "status") {
    python backend/inference/router.py --config $ConfigFile --state $StateFile status
    $exitCode = $LASTEXITCODE
    Write-Host "Status Exit Code: $exitCode"
    exit $exitCode
}

if (-not (Test-Path $RequestFile)) {
    Write-Error "Request file '$RequestFile' does not exist."
    exit 1
}

Get-Content -Raw -Encoding utf8 $RequestFile | python backend/inference/router.py --config $ConfigFile --state $StateFile $Action
$exitCode = $LASTEXITCODE
Write-Host "Router Exit Code: $exitCode"
exit $exitCode
