param(
    [Parameter(Mandatory=$true)][string]$BuildResult,
    [string]$EvidenceDirectory = 'evidence\resident-20261019'
)
$ErrorActionPreference = 'Stop'
$canonicalRoot = Split-Path $PSScriptRoot -Parent
$evidencePath = Join-Path $canonicalRoot $EvidenceDirectory
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
$build = Get-Content -LiteralPath $BuildResult -Raw | ConvertFrom-Json
$installer = Get-Item -LiteralPath $build.artifacts[0].path
if ((Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash -ne $build.artifacts[0].sha256) {
    throw 'Installer changed since its successful build'
}
$appDirectory = Join-Path $env:LOCALAPPDATA 'Programs\Axx'
$appExecutable = Join-Path $appDirectory 'Axx.exe'
$existing = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'Axx.exe' })
if ($existing.Count) { throw 'An Axx instance is running; close only the identified instance before installation' }
$started = [DateTimeOffset]::Now
$installProcess = Start-Process -FilePath $installer.FullName -ArgumentList @('/S','/UPDATE',"/D=$appDirectory") -WindowStyle Hidden -PassThru -Wait
if ($installProcess.ExitCode -ne 0) { throw "Installer exited $($installProcess.ExitCode)" }
& python (Join-Path $PSScriptRoot 'verify-installed-files.py') --installed $appDirectory --build-result $BuildResult --output (Join-Path $evidencePath 'installed-files.json')
if ($LASTEXITCODE -ne 0) { throw 'Installed artifact verification failed' }
$registry = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Axx'
if ($registry.DisplayVersion -ne $build.artifacts[0].version -or $registry.InstallLocation.Trim('"') -ne $appDirectory) {
    throw 'Installed application registry does not match the delivery'
}
$desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Axx.lnk'
$startMenuLink = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Axx.lnk'
$shortcutReader = New-Object -ComObject WScript.Shell
$links = @($desktopLink,$startMenuLink) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) { throw "Shortcut missing: $_" }
    $link = $shortcutReader.CreateShortcut($_)
    if ($link.TargetPath -ne $appExecutable -or $link.Arguments) { throw "Unexpected shortcut target/arguments: $_" }
    @{path=$_;target=$link.TargetPath;arguments=$link.Arguments}
}
$launchTime = [DateTimeOffset]::Now
$originalPath = $env:PATH
try {
    $env:PATH = 'C:\Windows\System32;C:\Windows'
    Start-Process -FilePath $desktopLink -WorkingDirectory $appDirectory | Out-Null
} finally { $env:PATH = $originalPath }
$nativeProcess = $null
$ready = $null
for ($i=0; $i -lt 60; $i++) {
    $processes = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $appExecutable })
    if ($processes.Count -eq 1) {
        $nativeProcess = $processes[0]
        $readyPath = Join-Path $env:LOCALAPPDATA "Axx\backend-ready-$($nativeProcess.ProcessId).json"
        if ((Test-Path -LiteralPath $readyPath) -and (Get-Item -LiteralPath $readyPath).LastWriteTimeUtc -ge $launchTime.UtcDateTime.AddSeconds(-1)) {
            $ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
            if ($ready.port -gt 0 -and $ready.instance_id) { break }
        }
    }
    Start-Sleep -Milliseconds 500
}
if (-not $nativeProcess -or -not $ready) { throw 'Installed host/backend did not reach readiness within 30 seconds' }
$backendProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($ready.pid)"
if ($backendProcess.ExecutablePath -ne (Join-Path $appDirectory 'resources\axx-backend.exe')) {
    throw 'Installed host started an unexpected backend executable'
}
$ancestor = $backendProcess
for ($i=0; $i -lt 4 -and $ancestor.ProcessId -ne $nativeProcess.ProcessId; $i++) {
    $ancestor = Get-CimInstance Win32_Process -Filter "ProcessId=$($ancestor.ParentProcessId)"
    if (-not $ancestor) { break }
}
if (-not $ancestor -or $ancestor.ProcessId -ne $nativeProcess.ProcessId) {
    throw 'Ready backend is not a descendant of the installed native host'
}
$httpStatus = $null
try {
    $unexpectedPublicResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($ready.port)/axx-api/status" -TimeoutSec 2
    throw 'Private backend unexpectedly accepted a request without its host token'
} catch {
    if ($_.Exception.Response) { $httpStatus = [int]$_.Exception.Response.StatusCode }
    if ($httpStatus -ne 401) { throw }
}
$runtime = [ordered]@{
    result='INSTALLED_RUNTIME_STARTED';version=$build.artifacts[0].version;
    started=$started.ToString('o');completed=[DateTimeOffset]::Now.ToString('o');
    installer=$installer.FullName;installer_sha256=$build.artifacts[0].sha256;installer_exit=$installProcess.ExitCode;
    executable=$appExecutable;pid=$nativeProcess.ProcessId;launch='Desktop shortcut with PATH limited to Windows';
    launched_at=$launchTime.ToString('o');working_directory=$appDirectory;
    backend=@{pid=$ready.pid;port=$ready.port;instance_id=$ready.instance_id;executable=$backendProcess.ExecutablePath;unauthenticated_http_status=$httpStatus};
    registry=@{display_version=$registry.DisplayVersion;install_location=$registry.InstallLocation;uninstall=$registry.UninstallString};
    shortcuts=$links;visual_acceptance='Separate native observation required';recording='DEFERRED_BY_USER'
}
$runtime | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidencePath 'installed-runtime.json') -Encoding UTF8
$runtime | ConvertTo-Json -Depth 6

