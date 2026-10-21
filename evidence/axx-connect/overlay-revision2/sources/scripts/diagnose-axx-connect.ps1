param([string]$CodexExecutable, [switch]$Probe, [switch]$ExecuteTelemetry)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'axx-connect-common.ps1')
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$axxData = Get-AxxConnectDataDirectory
$runtimePath = Join-Path $axxData 'connect\runtime.json'
$runtime = if (Test-Path -LiteralPath $runtimePath) { Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json } else { $null }
$codexPath = $null; $codexVersion = $null; $codexError = $null
try { $codexPath = Resolve-AxxCodexExecutable $CodexExecutable; $codexVersion = (& $codexPath --version | Out-String).Trim() } catch { $codexError = $_.Exception.Message }
$report = @{ plugin = 'axx-connect'; codex_version = $codexVersion; codex_available = [bool]$codexPath; codex_error = $codexError; runtime_configured = [bool]$runtime; runtime_mode = $(if ($runtime) { $runtime.mode } else { $null }); executor_endpoint_present = (Test-Path -LiteralPath (Join-Path $axxData 'connect\endpoint.dpapi')); inference_verified_by_this_diagnostic = $false; data_directory = $axxData }
$report | ConvertTo-Json -Depth 5
if ($Probe) {
    $pythonPath = Join-Path $projectRoot '.venv-axx-connect\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $pythonPath)) { throw 'La prueba SDK requiere el entorno aislado fuente. En el host instalado llama axx_status.' }
    $probeArgs = @((Join-Path $PSScriptRoot 'probe-axx-connect.py'))
    if ($ExecuteTelemetry) { $probeArgs += '--execute-telemetry' }
    & $pythonPath @probeArgs
    if ($LASTEXITCODE -ne 0) { throw 'La prueba MCP no terminó correctamente.' }
}
