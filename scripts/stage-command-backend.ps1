param([string]$EvidenceDirectory = 'evidence\command-library-20261019')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
$stageLock = $null
try {
    $evidencePath = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
    if (-not $evidencePath.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence must be inside this workspace' }
    $reportPath = Join-Path $evidencePath 'verified-package-report.json'
    $proof = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($proof.passed -ne $true -or @($proof.checks).Count -lt 20) { throw 'A passing frozen-package verification is required' }
    $candidate = Join-Path $evidencePath 'verified-package\axx-backend.exe'
    $candidateHash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
    if ($candidateHash -ne $proof.binary_sha256 -or (Resolve-Path -LiteralPath $candidate).Path -ne $proof.binary) { throw 'Verified package does not match its report' }
    $stageLock = [IO.File]::Open((Join-Path $projectRoot 'build\.windows-delivery.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $frozen = Get-Content -LiteralPath (Join-Path $evidencePath 'frozen-source-manifest.json') -Raw | ConvertFrom-Json
    foreach ($entry in $frozen) {
        $current = Join-Path $projectRoot $entry.path
        $snapshot = Join-Path (Join-Path $projectRoot 'build\command-library-frozen-source') $entry.path
        if ((Get-FileHash -LiteralPath $current -Algorithm SHA256).Hash -ne $entry.sha256 -or
            (Get-FileHash -LiteralPath $snapshot -Algorithm SHA256).Hash -ne $entry.sha256) { throw "Frozen source changed: $($entry.path)" }
    }
    $backendInputs = @{}
    $frozenRuntime = @{}
    foreach ($entry in $frozen) {
        $relative = $entry.path.Replace('/', '\')
        $extension = [IO.Path]::GetExtension($relative)
        if ($relative -eq 'axx-backend.spec' -or ($relative -match '^(backend|resources|vendor)\\' -and
                $extension -in '.py','.json','.bin','.txt' -and $relative -notmatch '\\(__pycache__|tests)\\' -and
                [IO.Path]::GetFileName($relative) -notlike 'test_*.py')) {
            $frozenRuntime[$relative] = $entry.sha256
        }
    }
    foreach ($file in @(Get-ChildItem backend,resources,vendor -File -Recurse | Where-Object {
            $_.Extension -in '.py','.json','.bin','.txt' -and $_.FullName -notmatch '\\(__pycache__|tests)\\' -and $_.Name -notlike 'test_*.py'
        } | ForEach-Object FullName) + @('axx-backend.spec')) {
        $relative = [IO.Path]::GetRelativePath($projectRoot, [IO.Path]::GetFullPath($file))
        if (-not $frozenRuntime.ContainsKey($relative)) { throw "Runtime input absent from verified snapshot: $relative" }
        $backendInputs[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    }
    if ($backendInputs.Count -ne $frozenRuntime.Count) { throw 'Runtime inventory differs from the verified snapshot' }
    $beforeStage = Join-Path $evidencePath 'before-restage'
    New-Item -ItemType Directory -Path $beforeStage -Force | Out-Null
    $backups = @()
    foreach ($relative in @('dist\axx-backend.exe', 'src-tauri\resources\axx-backend.exe',
            'src-tauri\target\release\Axx.exe', 'src-tauri\target\release\bundle\nsis\Axx_0.20.3_x64-setup.exe',
            'build\backend-build-receipt.json')) {
        if (Test-Path -LiteralPath $relative) {
            $backupPath = Join-Path $beforeStage $relative.Replace('\', '_')
            if (Test-Path -LiteralPath $backupPath) { throw "Backup already exists: $backupPath" }
            Copy-Item -LiteralPath $relative -Destination $backupPath
            $backups += @{path=$relative; backup=$backupPath; sha256=(Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash}
        }
    }
    $backups | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidencePath 'before-restage.json') -Encoding UTF8
    Copy-Item -LiteralPath $candidate -Destination 'dist\axx-backend.exe' -Force
    Copy-Item -LiteralPath $candidate -Destination 'src-tauri\resources\axx-backend.exe' -Force
    @{inputs=$backendInputs; sha256=$candidateHash; verified_package_report=$reportPath} | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath 'build\backend-build-receipt.json' -Encoding UTF8
    @{staged=$true; sha256=$candidateHash; verified_checks=@($proof.checks).Count; backups=$backups.Count} | ConvertTo-Json
} finally {
    if ($null -ne $stageLock) { $stageLock.Dispose() }
    Pop-Location
}
