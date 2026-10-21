# stdout is exclusively the child MCP protocol; diagnostics always go to stderr.
$ErrorActionPreference = 'Stop'
try {
    $axxData = if ($env:AXX_CONNECT_DATA_DIR) { $env:AXX_CONNECT_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'Axx' }
    $runtimeFile = Join-Path $axxData 'connect\runtime.json'
    $runtime = if (Test-Path -LiteralPath $runtimeFile) { Get-Content -LiteralPath $runtimeFile -Raw | ConvertFrom-Json } else { $null }
    if ($runtime -and $runtime.mode -eq 'source') {
        $sourceRoot = [IO.Path]::GetFullPath([string]$runtime.source_root)
        $pythonPath = Join-Path $sourceRoot '.venv-axx-connect\Scripts\python.exe'
        $serverPath = Join-Path $sourceRoot 'backend\connect\mcp_server.py'
        if (!(Test-Path -LiteralPath $pythonPath -PathType Leaf) -or !(Test-Path -LiteralPath $serverPath -PathType Leaf)) {
            throw 'La instalación fuente no está disponible. Ejecuta install-axx-connect.ps1 de nuevo.'
        }
        Set-Location -LiteralPath $sourceRoot
        & $pythonPath -m backend.connect.mcp_server
        exit $LASTEXITCODE
    }
    $candidates = @()
    if ($runtime -and $runtime.backend_executable) { $candidates += [string]$runtime.backend_executable }
    $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\Axx\resources\axx-backend.exe')
    $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\Axx\axx-backend.exe')
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (!(Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $help = & $candidate --help 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0 -and $help.Contains('--mcp-server')) {
            Set-Location -LiteralPath (Split-Path $candidate -Parent)
            & $candidate --mcp-server
            exit $LASTEXITCODE
        }
    }
    throw 'No se encontró un runtime Axx Connect compatible. Instala Axx actualizado o ejecuta scripts/install-axx-connect.ps1 en las fuentes.'
} catch {
    [Console]::Error.WriteLine('Axx Connect: ' + $_.Exception.Message)
    exit 1
}
