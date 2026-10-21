param([string]$CodexExecutable, [switch]$RemoveMarketplace)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'axx-connect-common.ps1')
$codexPath = Resolve-AxxCodexExecutable $CodexExecutable
& $codexPath plugin remove 'axx-connect@axx-local' --json
if ($LASTEXITCODE -ne 0) { throw 'Codex no confirmó la desinstalación del plugin.' }
if ($RemoveMarketplace) {
    & $codexPath plugin marketplace remove 'axx-local'
    if ($LASTEXITCODE -ne 0) { throw 'El plugin se quitó, pero no se pudo quitar el marketplace.' }
}
Write-Output 'Plugin desinstalado. Se conservan Axx, sus datos, recetas, archivos, entorno aislado y la autenticación oficial de Codex.'
