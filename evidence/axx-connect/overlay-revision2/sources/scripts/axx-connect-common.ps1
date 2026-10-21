function Resolve-AxxCodexExecutable {
    param([string]$ExplicitPath)
    if ($ExplicitPath) {
        if (!(Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) { throw 'El ejecutable Codex indicado no existe.' }
        return [IO.Path]::GetFullPath($ExplicitPath)
    }
    $found = Get-Command codex.exe -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $npmCodex = Join-Path $env:APPDATA 'npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe'
    if (Test-Path -LiteralPath $npmCodex -PathType Leaf) { return $npmCodex }
    $releaseRoot = Join-Path $env:USERPROFILE '.codex\packages\app-server-daemon\releases'
    if (Test-Path -LiteralPath $releaseRoot) {
        $release = Get-ChildItem -LiteralPath $releaseRoot -Directory | Sort-Object Name -Descending | ForEach-Object {
            Join-Path $_.FullName 'bin\codex.exe'
        } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if ($release) { return $release }
    }
    throw 'No se encontró Codex. Instala el cliente oficial compatible o indica -CodexExecutable con una ruta existente.'
}

function Get-AxxConnectDataDirectory {
    if ($env:AXX_CONNECT_DATA_DIR) { return [IO.Path]::GetFullPath($env:AXX_CONNECT_DATA_DIR) }
    return Join-Path $env:LOCALAPPDATA 'Axx'
}

function Write-AxxConnectJson {
    param([string]$Path, [object]$Value)
    $parent = Split-Path $Path -Parent
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = $Path + '.tmp'
    $encoded = $Value | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText($temporary, $encoded, (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}
