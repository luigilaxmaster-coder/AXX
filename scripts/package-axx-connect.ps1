param([string]$OutputPath)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$pluginRoot = Join-Path $projectRoot 'plugins\axx-connect'
$portable = Get-Content -LiteralPath (Join-Path $pluginRoot 'plugin.json') -Raw | ConvertFrom-Json
$compat = Get-Content -LiteralPath (Join-Path $pluginRoot '.codex-plugin\plugin.json') -Raw | ConvertFrom-Json
$mcp = Get-Content -LiteralPath (Join-Path $pluginRoot 'mcp.json') -Raw | ConvertFrom-Json
$legacyMcp = Get-Content -LiteralPath (Join-Path $pluginRoot '.mcp.json') -Raw | ConvertFrom-Json
if ($portable.'$schema' -ne 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json' -or $mcp.'$schema' -ne 'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json') { throw 'Falta el esquema portable correcto.' }
if ($portable.name -ne 'axx-connect' -or $portable.name -ne $compat.name -or $portable.version -ne $compat.version) { throw 'Los manifiestos discrepan en identidad o versión.' }
if ($portable.version -notmatch '^\d+\.\d+\.\d+$') { throw 'La versión no es SemVer.' }
$interface = $portable.extensions.'com.openai'.interface
if ($interface.shortDescription.Length -gt 30 -or $interface.shortDescription -ne $compat.interface.shortDescription) { throw 'Subtítulo inválido o manifiestos inconsistentes.' }
if ($mcp.mcpServers.'axx-connect'.command -ne $legacyMcp.mcpServers.'axx-connect'.command -or (@($mcp.mcpServers.'axx-connect'.args) -join '|') -ne (@($legacyMcp.mcpServers.'axx-connect'.args) -join '|')) { throw 'Los transportes portables y de compatibilidad discrepan.' }
foreach ($path in @('server\launch.ps1','skills\axx-connect\SKILL.md','skills\axx-connect\references\operations.md')) {
    if (!(Test-Path -LiteralPath (Join-Path $pluginRoot $path) -PathType Leaf)) { throw "Falta el componente $path" }
}
if (!$OutputPath) { $OutputPath = Join-Path $projectRoot ('dist\axx-connect-' + $portable.version + '.zip') }
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
if ($OutputPath.StartsWith($pluginRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'El ZIP debe quedar fuera de la carpeta del plugin.' }
New-Item -ItemType Directory -Path (Split-Path $OutputPath -Parent) -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stream = [IO.File]::Open($OutputPath, [IO.FileMode]::Create, [IO.FileAccess]::Write)
$zip = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in Get-ChildItem -LiteralPath $pluginRoot -File -Recurse -Force) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'No se permiten symlinks ni reparse points en el paquete.' }
        $relative = $file.FullName.Substring($pluginRoot.Length + 1).Replace('\','/')
        if ($relative -match '(^|/)(__pycache__|node_modules|\.venv)(/|$)' -or $relative -match '\.(db|dpapi|log|pyc)$') { throw "Archivo no distribuible en el plugin: $relative" }
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, ('axx-connect/' + $relative), [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally { $zip.Dispose(); $stream.Dispose() }
$check = [IO.Compression.ZipFile]::OpenRead($OutputPath)
try {
    $entries = @($check.Entries | ForEach-Object FullName)
    foreach ($required in @('axx-connect/plugin.json','axx-connect/mcp.json','axx-connect/.codex-plugin/plugin.json','axx-connect/.mcp.json','axx-connect/server/launch.ps1')) { if ($entries -notcontains $required) { throw "El ZIP omite $required" } }
    @{ path = $OutputPath; version = $portable.version; sha256 = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash; entries = $entries } | ConvertTo-Json -Depth 4
} finally { $check.Dispose() }
