param([string]$Directory = (Join-Path $env:LOCALAPPDATA 'Axx/gateways'), [switch]$IsolatedNode)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$revision = '26484157fd15f5fb66f54d3a86f568997ea304de'
$sourceHash = '0511c5372e3be30bf7013dd34285e0dae82d0a4fc0b00fe7eede203a1f8e9883'
$nodeVersionPinned = '24.14.0'
$nodeHash = '313fa40c0d7b18575821de8cb17483031fe07d95de5994f6f435f3b345f85c66'
$Directory = [IO.Path]::GetFullPath($Directory)
$source = Join-Path $Directory 'freellmapi-26484157'
New-Item -ItemType Directory -Path $Directory -Force | Out-Null

function Get-VerifiedDownload([string]$Url, [string]$Target, [string]$Hash) {
    if (-not (Test-Path -LiteralPath $Target)) {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Target -TimeoutSec 120
    }
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) {
        throw 'Official download checksum mismatch; file preserved without executing.'
    }
}
$node = $null
if (-not $IsolatedNode) {
    $candidates = @((Get-Command node.exe -ErrorAction SilentlyContinue).Source,
        (Join-Path $env:ProgramFiles 'nodejs/node.exe'),
        (Join-Path $Directory "node-v$nodeVersionPinned-win-x64/node.exe"))
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            try {
                $version = [version]((& $candidate --version).TrimStart('v'))
                if ($version -ge [version]'20.18.0' -and $version -lt [version]'25.0.0') {
                    $node = $candidate; break
                }
            } catch { }
        }
    }
}
if (-not $node) {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'The bundled runtime requires 64-bit Windows.' }
    $archiveName = "node-v$nodeVersionPinned-win-x64.zip"
    $nodeZip = Join-Path $Directory $archiveName
    $checksums = (Invoke-WebRequest -UseBasicParsing -Uri "https://nodejs.org/dist/v$nodeVersionPinned/SHASUMS256.txt" -TimeoutSec 30).Content
    if ($checksums -notmatch "(?m)^$nodeHash\s+$([regex]::Escape($archiveName))\s*$") {
        throw 'Official Node checksum manifest differs from the pinned release.'
    }
    Get-VerifiedDownload "https://nodejs.org/dist/v$nodeVersionPinned/$archiveName" $nodeZip $nodeHash
    $nodeDirectory = Join-Path $Directory "node-v$nodeVersionPinned-win-x64"
    if (-not (Test-Path -LiteralPath $nodeDirectory)) {
        Expand-Archive -LiteralPath $nodeZip -DestinationPath $Directory
    }
    $node = Join-Path $nodeDirectory 'node.exe'
    if (-not (Test-Path -LiteralPath $node) -or ((& $node --version).Trim() -ne "v$nodeVersionPinned")) {
        throw 'The isolated Node runtime could not be verified.'
    }
}
$npm = Join-Path (Split-Path -Parent $node) 'npm.cmd'
if (-not (Test-Path -LiteralPath $npm)) { throw 'The verified Node installation does not contain npm.' }
$env:PATH = (Split-Path -Parent $node) + [IO.Path]::PathSeparator + $env:PATH

$sourceReceipt = Join-Path $source '.axx-source-files.json'
if (-not (Test-Path -LiteralPath $source)) {
    $sourceZip = Join-Path $Directory "freellmapi-$revision.zip"
    Get-VerifiedDownload "https://codeload.github.com/tashfeenahmed/freellmapi/zip/$revision" $sourceZip $sourceHash
    $extract = Join-Path $Directory ('extract-' + [Guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $sourceZip -DestinationPath $extract
    $extractedSource = [IO.Path]::GetFullPath((Join-Path $extract "freellmapi-$revision"))
    if (-not $extractedSource.StartsWith($Directory + [IO.Path]::DirectorySeparatorChar) -or
        -not $source.StartsWith($Directory + [IO.Path]::DirectorySeparatorChar)) { throw 'Invalid extraction destination.' }
    Move-Item -LiteralPath $extractedSource -Destination $source
    $baseline = @(Get-ChildItem -LiteralPath $source -File -Recurse | ForEach-Object {
        @{ path=$_.FullName.Substring($source.Length + 1); sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
    @{ commit=$revision; archive_sha256=$sourceHash; files=$baseline } | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $sourceReceipt -Encoding utf8
} elseif (Test-Path -LiteralPath (Join-Path $source '.git')) {
    $git = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
    if (-not $git) { $git = Join-Path $env:ProgramFiles 'Git/cmd/git.exe' }
    if (-not (Test-Path -LiteralPath $git)) { throw 'Existing Git checkout preserved; Git is unavailable to verify local changes.' }
    $actual = (& $git -C $source rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $revision) { throw 'Existing checkout differs; preserved without modification.' }
    if (& $git -C $source status --porcelain --untracked-files=no) { throw 'Existing source has changes; preserved without rebuilding.' }
} else {
    if (-not (Test-Path -LiteralPath $sourceReceipt)) { throw 'Existing unverified source preserved without modification.' }
    $receipt = Get-Content -LiteralPath $sourceReceipt -Raw | ConvertFrom-Json
    if ($receipt.commit -ne $revision -or $receipt.archive_sha256 -ne $sourceHash) { throw 'Source receipt differs from the pinned revision.' }
    foreach ($item in $receipt.files) {
        $file = [IO.Path]::GetFullPath((Join-Path $source $item.path))
        if (-not $file.StartsWith($source + [IO.Path]::DirectorySeparatorChar) -or
            -not (Test-Path -LiteralPath $file) -or
            (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $item.sha256) {
            throw 'Existing source has changes; preserved without rebuilding.'
        }
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $source 'server/dist/index.js')) -or
    -not (Test-Path -LiteralPath (Join-Path $source 'client/dist/index.html'))) {
    Push-Location $source
    try {
        & $npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'FreeLLMAPI dependency installation failed.' }
        & $npm run build
        if ($LASTEXITCODE -ne 0) { throw 'FreeLLMAPI official build failed.' }
    } finally { Pop-Location }
}
$manifest = @{ commit=$revision; version='0.16.9'; source_dir=$source; node_executable=$node;
    method='official_source_build'; source_archive_sha256=$sourceHash; installed_at=[DateTime]::UtcNow.ToString('o') }
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Directory 'freellmapi-install.json') -Encoding utf8
Write-Output 'FreeLLMAPI 0.16.9 is ready. No personal provider credentials were imported.'
