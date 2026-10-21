param(
    [ValidateSet('Source', 'Packaged')][string]$RuntimeMode = 'Source',
    [string]$PythonExecutable = 'python',
    [string]$CodexExecutable,
    [string]$BackendExecutable,
    [switch]$SkipDependencies
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'axx-connect-common.ps1')
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$codexPath = Resolve-AxxCodexExecutable $CodexExecutable
$marketplaceRoot = Join-Path $projectRoot 'plugins'
$pluginManifest = Join-Path $marketplaceRoot 'axx-connect\plugin.json'
if (!(Test-Path -LiteralPath $pluginManifest -PathType Leaf)) { throw 'Falta el paquete Axx Connect en el proyecto.' }
$manifest = Get-Content -LiteralPath $pluginManifest -Raw | ConvertFrom-Json
$version = (& $codexPath --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Codex no inicia correctamente.' }
$runtime = @{ schema_version = 1; mode = $RuntimeMode.ToLowerInvariant(); plugin_version = $manifest.version }
if ($RuntimeMode -eq 'Source') {
    $pythonPath = Join-Path $projectRoot '.venv-axx-connect\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        & $PythonExecutable -m venv (Join-Path $projectRoot '.venv-axx-connect')
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python aislado.' }
    }
    if (!$SkipDependencies) {
        & $pythonPath -m pip install --disable-pip-version-check --requirement (Join-Path $projectRoot 'requirements-axx-connect.txt')
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar el SDK MCP fijado en el entorno aislado.' }
    }
    & $pythonPath -c "import importlib.metadata; assert importlib.metadata.version('mcp') == '1.30.0'"
    if ($LASTEXITCODE -ne 0) { throw 'El SDK MCP instalado no coincide con 1.30.0.' }
    if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'backend\connect\mcp_server.py'))) { throw 'Falta el servidor MCP compilable de Axx Connect.' }
    $runtime.source_root = $projectRoot
} else {
    if (!$BackendExecutable) { $BackendExecutable = Join-Path $env:LOCALAPPDATA 'Programs\Axx\resources\axx-backend.exe' }
    if (!(Test-Path -LiteralPath $BackendExecutable -PathType Leaf)) { throw 'No existe el backend empaquetado indicado.' }
    $help = & $BackendExecutable --help 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or !$help.Contains('--mcp-server')) { throw 'El backend instalado todavía no incluye --mcp-server; instala la versión de Axx Connect.' }
    $runtime.backend_executable = [IO.Path]::GetFullPath($BackendExecutable)
}
$axxData = Get-AxxConnectDataDirectory
$runtimePath = Join-Path $axxData 'connect\runtime.json'
if (Test-Path -LiteralPath $runtimePath) {
    Copy-Item -LiteralPath $runtimePath -Destination ($runtimePath + '.before-install') -Force
}
Write-AxxConnectJson $runtimePath $runtime
$marketplaces = (& $codexPath plugin marketplace list | Out-String)
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar marketplaces de Codex.' }
$existing = @($marketplaces -split "`r?`n" | Where-Object { $_ -match '^axx-local\s+' })
if ($existing.Count -gt 0 -and !$existing[0].Contains($marketplaceRoot)) {
    throw 'Ya existe un marketplace axx-local en otra ubicación. No se reemplazó; revisa codex plugin marketplace list.'
}
if ($existing.Count -eq 0) {
    & $codexPath plugin marketplace add $marketplaceRoot --json
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo registrar el marketplace local de Axx.' }
}
$installedText = (& $codexPath plugin list --marketplace axx-local --json | Out-String)
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar la instalación existente de Axx Connect.' }
$installed = $installedText | ConvertFrom-Json
$entry = @($installed.installed | Where-Object { $_.pluginId -eq 'axx-connect@axx-local' }) | Select-Object -First 1
$manifest = Get-Content -LiteralPath $pluginManifest -Raw | ConvertFrom-Json
$reuseExisting = $false
if ($entry -and $entry.version -eq $manifest.version) {
    $codexUserDirectory = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $cachedRoot = Join-Path $codexUserDirectory ('plugins\cache\axx-local\axx-connect\' + $manifest.version)
    $sourcePluginRoot = Split-Path $pluginManifest -Parent
    $reuseExisting = Test-Path -LiteralPath $cachedRoot -PathType Container
    foreach ($sourceFile in Get-ChildItem -LiteralPath $sourcePluginRoot -File -Recurse -Force) {
        $relative = $sourceFile.FullName.Substring($sourcePluginRoot.Length + 1)
        $cachedFile = Join-Path $cachedRoot $relative
        if (!(Test-Path -LiteralPath $cachedFile -PathType Leaf)) { $reuseExisting = $false; break }
        # All current packaged components are UTF-8 text; BOM/CRLF do not alter
        # their semantics. Never write directly into the host-managed cache.
        $sourceText = [IO.File]::ReadAllText($sourceFile.FullName).Replace("`r`n", "`n")
        $cachedText = [IO.File]::ReadAllText($cachedFile).Replace("`r`n", "`n")
        if ($sourceText -cne $cachedText) { $reuseExisting = $false; break }
    }
    if (!$reuseExisting) { throw 'El plugin de esta versión ya está instalado con contenido diferente. Incrementa la versión en ambos manifiestos antes de actualizar; no se sobrescribió el cache activo.' }
}
if ($reuseExisting) {
    Write-Output ('Se reutiliza Axx Connect ' + $manifest.version + ' ya instalado; no se reemplaza su cache activo.')
} else {
    & $codexPath plugin add 'axx-connect@axx-local' --json
    if ($LASTEXITCODE -ne 0) { throw 'Codex rechazó la instalación del plugin; revisa el diagnóstico devuelto.' }
}
$receipt = @{ installed_at = [DateTimeOffset]::Now.ToString('o'); plugin = 'axx-connect@axx-local'; plugin_version = $manifest.version; codex_version = $version; runtime_mode = $runtime.mode; source_root = $projectRoot; marketplace_root = $marketplaceRoot; verified_host_call = $false }
Write-AxxConnectJson (Join-Path $axxData 'connect\installation.json') $receipt
Write-Output 'Axx Connect instalado localmente. Inicia Axx y comprueba axx_status desde el host. La instalación no verifica inferencia ni ejecución.'
