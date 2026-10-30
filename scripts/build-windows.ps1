param([string]$PythonExecutable = 'python', [switch]$SkipBackend, [switch]$BackendOnly,
      [string]$EvidenceDirectory = 'evidence\resident-20261019')
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility
$projectRoot = Split-Path $PSScriptRoot -Parent
$evidencePath = Join-Path $projectRoot $EvidenceDirectory
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
$buildLockPath = Join-Path $projectRoot 'build\.windows-delivery.lock'
New-Item -ItemType Directory -Path (Split-Path $buildLockPath) -Force | Out-Null
$buildLock = [IO.File]::Open($buildLockPath, 'OpenOrCreate', 'ReadWrite', 'None')
Push-Location $projectRoot
try {
    & $PythonExecutable (Join-Path $PSScriptRoot 'release.py') check
    if ($LASTEXITCODE -ne 0) { throw 'Desktop version or README is inconsistent; run scripts/release.py sync' }
    $dependency = Get-Content -LiteralPath 'resources\dependency-manifest.json' -Raw | ConvertFrom-Json
    & $PythonExecutable -c 'import PIL, pypdf'
    if ($LASTEXITCODE -ne 0) { throw 'Install requirements-converter.txt before building the Axx backend' }
    & $PythonExecutable -c "import websocket, win32com.client, pythoncom, playwright.async_api, mcp, uvicorn, psutil, jsonschema, ifcopenshell, rapidocr_onnxruntime, onnxruntime, importlib.metadata as m; assert all(m.version(k) == v for k,v in {'websocket-client':'1.9.2','pywin32':'311','playwright':'1.64.1','mcp':'1.30.0','psutil':'7.2.2','jsonschema':'4.26.0','ifcopenshell':'0.9.0.post1','rapidocr-onnxruntime':'1.4.4','onnxruntime':'1.31.0'}.items())"
    if ($LASTEXITCODE -ne 0) { throw 'Install requirements-computer-use.txt before building the Axx backend' }
    if (-not $SkipBackend) {
        & $PythonExecutable -c "import importlib.metadata as m, pathlib, telethon, pytgcalls, ntgcalls, tkinter; requirements=[line.strip().split('==') for line in pathlib.Path('requirements-telegram.txt').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]; assert requirements and all(len(x)==2 and m.version(x[0])==x[1] for x in requirements)"
        if ($LASTEXITCODE -ne 0) { throw 'Install exact requirements-telegram.txt in the selected build Python and ensure tkinter is available before building the Axx backend' }
    }
    & $PythonExecutable -m backend.mobile.pairing_qr
    if ($LASTEXITCODE -ne 0) { throw 'QR generation failed. Install the qrcode version pinned in requirements-mobile.txt before building' }
    if ((Get-FileHash -LiteralPath 'src-tauri\resources\ai-memory.exe' -Algorithm SHA256).Hash -ne $dependency.exe_sha256) {
        throw 'ai-memory executable differs from the verified official dependency manifest'
    }
    & node mobile/build.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Desktop avatar extraction failed; see mobile/build.mjs' }
    $telegramAssets = @('backend\telegram\webapp.html', 'backend\telegram\webapp.css', 'backend\telegram\webapp.js', 'mobile\www\js\desktop-avatar.js', 'mobile\js\avatar-renderer.js')
    $sourceFiles = @(Get-ChildItem -LiteralPath '1.AXX' -File -Recurse | Where-Object { $_.Extension -in '.html','.js','.css','.json','.png','.ico','.svg','.woff','.woff2' } | ForEach-Object FullName) + @('axx-backend.spec', 'scripts\setup-freellmapi.ps1', 'src-tauri\tauri.conf.json', 'src-tauri\Cargo.toml', 'src-tauri\resources\ai-memory.exe') + $telegramAssets
    $sourceFiles += @(Get-ChildItem backend,src-tauri\src,resources,vendor -File -Recurse | Where-Object { $_.Extension -in '.ps1','.py','.rs','.json','.bin','.txt','.zip' -and $_.FullName -notmatch '\\(__pycache__|tests)\\' -and $_.Name -notlike 'test_*.py' } | ForEach-Object FullName)
    $sourceFiles += @(Get-ChildItem -LiteralPath 'src-tauri\resources\license-notices' -File -Recurse | ForEach-Object FullName)
    $sourceFiles += @('scripts\configure-native-gateway.py', 'scripts\anythingmcp-local.py', 'scripts\backend_bundle.py', 'scripts\build-windows.ps1', 'requirements-telegram.txt')
    $before = @{}
    foreach ($file in $sourceFiles) { $before[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash }
    $steps = @()
    $started = [DateTimeOffset]::Now
    $backendInputs = @{}
    foreach ($file in @(Get-ChildItem backend,resources,vendor -File -Recurse | Where-Object { $_.Extension -in '.ps1','.py','.json','.bin','.txt','.zip' -and $_.FullName -notmatch '\\(__pycache__|tests)\\' -and $_.Name -notlike 'test_*.py' } | ForEach-Object FullName) + @('axx-backend.spec', 'scripts\setup-freellmapi.ps1', 'scripts\configure-native-gateway.py', 'scripts\anythingmcp-local.py', 'scripts\backend_bundle.py', 'scripts\build-windows.ps1', 'requirements-telegram.txt') + $telegramAssets) {
        $backendInputs[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    }
    $backendReceiptPath = Join-Path $projectRoot 'build\backend-build-receipt.json'
    $backendRoot = Join-Path $projectRoot 'dist\axx-backend'
    $backendExecutable = Join-Path $backendRoot 'axx-backend.exe'
    $bundleHelper = Join-Path $PSScriptRoot 'backend_bundle.py'
    $bundleManifestPath = Join-Path $evidencePath 'backend-bundle.json'
    if ($SkipBackend) {
        $receipt = Get-Content -LiteralPath $backendReceiptPath -Raw | ConvertFrom-Json
        if (-not $receipt.bundle) { throw 'Backend receipt has no onedir bundle inventory; rebuild without -SkipBackend' }
        if ((Get-FileHash -LiteralPath $backendExecutable -Algorithm SHA256).Hash -ne $receipt.sha256) { throw 'Packaged backend hash differs from its build receipt' }
        if (@($receipt.inputs.PSObject.Properties).Count -ne $backendInputs.Count) { throw 'Backend source inventory changed; rebuild without -SkipBackend' }
        foreach ($file in $backendInputs.Keys) {
            if ($receipt.inputs.$file -ne $backendInputs[$file]) { throw "Backend source changed: $file; rebuild without -SkipBackend" }
        }
        $receipt.bundle | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $bundleManifestPath -Encoding UTF8
        & $PythonExecutable $bundleHelper verify $backendRoot $bundleManifestPath
        if ($LASTEXITCODE -ne 0) { throw 'Packaged backend bundle differs from its build receipt; rebuild without -SkipBackend' }
        $steps += @{command='Reuse backend with verified source and complete onedir bundle hashes'; exit_code=0}
    } else {
        $ErrorActionPreference = 'Continue'
        & $PythonExecutable -m PyInstaller --noconfirm --clean axx-backend.spec *> (Join-Path $evidencePath 'pyinstaller-build.log')
        $ErrorActionPreference = 'Stop'
        $steps += @{command="$PythonExecutable -m PyInstaller --noconfirm --clean axx-backend.spec"; exit_code=$LASTEXITCODE}
        if ($LASTEXITCODE -ne 0) { throw 'Backend packaging failed; see pyinstaller-build.log' }
        foreach ($file in $backendInputs.Keys) {
            if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $backendInputs[$file]) { throw "Backend source changed during packaging: $file" }
        }
        & $PythonExecutable $bundleHelper inventory $backendRoot --output $bundleManifestPath
        if ($LASTEXITCODE -ne 0) { throw 'Backend onedir bundle inventory failed' }
        $backendBundle = Get-Content -LiteralPath $bundleManifestPath -Raw | ConvertFrom-Json
        @{inputs=$backendInputs; sha256=(Get-FileHash -LiteralPath $backendExecutable -Algorithm SHA256).Hash; bundle=$backendBundle} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $backendReceiptPath -Encoding UTF8
    }
    $backendBundle = Get-Content -LiteralPath $bundleManifestPath -Raw | ConvertFrom-Json
    & $backendExecutable --verify-mobile-qr *> (Join-Path $evidencePath 'packaged-mobile-qr.json')
    $steps += @{command='axx-backend.exe --verify-mobile-qr'; exit_code=$LASTEXITCODE}
    if ($LASTEXITCODE -ne 0) { throw 'Packaged QR rendering failed; see packaged-mobile-qr.json' }
    & $backendExecutable --configure-native-gateway --help *> (Join-Path $evidencePath 'packaged-native-gateway-help.txt')
    $steps += @{command='axx-backend.exe --configure-native-gateway --help'; exit_code=$LASTEXITCODE}
    if ($LASTEXITCODE -ne 0) { throw 'Packaged gateway configuration command failed' }
    & $PythonExecutable $bundleHelper verify $backendRoot $bundleManifestPath
    if ($LASTEXITCODE -ne 0) { throw 'Backend bundle changed during packaged checks' }
    $resourceRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'src-tauri\resources'))
    $targetInternal = [IO.Path]::GetFullPath((Join-Path $resourceRoot '_internal'))
    if ((Split-Path $targetInternal -Parent) -ne $resourceRoot -or (Split-Path $targetInternal -Leaf) -ne '_internal') { throw 'Invalid generated backend resource target' }
    if ((Get-Item -LiteralPath $resourceRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Backend resource directory must not be a link' }
    if (Test-Path -LiteralPath $targetInternal) {
        $existing = @(Get-Item -LiteralPath $targetInternal -Force) + @(Get-ChildItem -LiteralPath $targetInternal -Force -Recurse)
        if (@($existing | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Generated backend directory contains a link; refusing recursive removal' }
        Remove-Item -LiteralPath $targetInternal -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $backendRoot '_internal') -Destination $targetInternal -Recurse -Force
    Copy-Item -LiteralPath $backendExecutable -Destination (Join-Path $resourceRoot 'axx-backend.exe') -Force
    & $PythonExecutable $bundleHelper verify $resourceRoot $bundleManifestPath
    if ($LASTEXITCODE -ne 0) { throw 'Staged Tauri backend resources differ from the verified onedir bundle' }
    if ($BackendOnly) {
        Get-Item -LiteralPath $backendExecutable | Select-Object FullName,Length
        Get-FileHash -LiteralPath $backendExecutable -Algorithm SHA256
        return
    }
    $tauri = Join-Path $projectRoot 'node_modules\.bin\tauri.cmd'
    if (-not (Test-Path -LiteralPath $tauri)) { throw 'Tauri CLI missing; run npm ci before building Windows' }
    $ErrorActionPreference = 'Continue'
    & $tauri build --bundles nsis *> (Join-Path $evidencePath 'tauri-nsis-build.log')
    $ErrorActionPreference = 'Stop'
    $steps += @{command='node_modules\.bin\tauri.cmd build --bundles nsis'; exit_code=$LASTEXITCODE}
    if ($LASTEXITCODE -ne 0) { throw 'Tauri NSIS build failed; see tauri-nsis-build.log' }
    foreach ($file in $sourceFiles) {
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $before[$file]) { throw "Source changed during build: $file" }
    }
    & $PythonExecutable $bundleHelper verify $backendRoot $bundleManifestPath
    if ($LASTEXITCODE -ne 0) { throw 'Backend bundle changed during Tauri packaging' }
    & $PythonExecutable $bundleHelper verify $resourceRoot $bundleManifestPath
    if ($LASTEXITCODE -ne 0) { throw 'Staged backend bundle changed during Tauri packaging' }
    $version = (Get-Content 'src-tauri\tauri.conf.json' -Raw | ConvertFrom-Json).version
    $artifacts = @("src-tauri\target\release\bundle\nsis\Axx_${version}_x64-setup.exe", 'src-tauri\target\release\Axx.exe', 'dist\axx-backend\axx-backend.exe') | ForEach-Object {
        $item=Get-Item -LiteralPath $_
        @{path=$item.FullName; bytes=$item.Length; sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash; architecture='x86_64'; version=$version}
    }
    @{started=$started.ToString('o'); completed=[DateTimeOffset]::Now.ToString('o'); steps=$steps; artifacts=$artifacts; backend_bundle=$backendBundle; source_hashes=$before} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidencePath 'build-result.json') -Encoding UTF8
    $artifacts | ConvertTo-Json -Depth 4
} finally {
    Pop-Location
    $buildLock.Dispose()
}
