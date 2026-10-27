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
& python -I (Join-Path $PSScriptRoot 'verify-installed-files.py') --installed $appDirectory --build-result $BuildResult --output (Join-Path $evidencePath 'installed-files.json')
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
$launchInfo = New-Object System.Diagnostics.ProcessStartInfo
$launchInfo.FileName = $appExecutable
$launchInfo.WorkingDirectory = $appDirectory
$launchInfo.UseShellExecute = $false
# A resident GUI must not keep the verification terminal's pipes alive.
# Native diagnostics go to LogDir; closed launcher streams are acceptance-tested.
$launchInfo.RedirectStandardOutput = $true
$launchInfo.RedirectStandardError = $true
$launchInfo.EnvironmentVariables['PATH'] = 'C:\Windows\System32;C:\Windows'
foreach ($name in @('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')) {
    $launchInfo.EnvironmentVariables.Remove($name)
}
$launchedProcess = [System.Diagnostics.Process]::Start($launchInfo)
$launchedProcess.StandardOutput.Close()
$launchedProcess.StandardError.Close()
$nativeProcess = $null
$hostEvidence = $null
$evidenceFile = Join-Path $env:LOCALAPPDATA 'Axx\logs\native-runtime.json'
for ($i=0; $i -lt 240; $i++) {
    $processes = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $appExecutable })
    if ($processes.Count -eq 1) {
        $nativeProcess = $processes[0]
        if ((Test-Path -LiteralPath $evidenceFile) -and (Get-Item -LiteralPath $evidenceFile).LastWriteTimeUtc -ge $launchTime.UtcDateTime.AddSeconds(-1)) {
            try { $candidateEvidence = Get-Content -LiteralPath $evidenceFile -Raw | ConvertFrom-Json } catch { $candidateEvidence = $null }
            $instanceGuid = [Guid]::Empty
            $validInstance = [Guid]::TryParse([string]$candidateEvidence.backendInstance, [ref]$instanceGuid) -and $instanceGuid -ne [Guid]::Empty
            if ($candidateEvidence.schemaVersion -eq 1 -and $candidateEvidence.executable -eq $appExecutable -and $nativeProcess.ProcessId -eq $launchedProcess.Id -and $candidateEvidence.pid -eq $nativeProcess.ProcessId -and $candidateEvidence.version -eq $build.artifacts[0].version -and $validInstance -and $candidateEvidence.backendReady -and $candidateEvidence.backendPort -gt 0 -and $candidateEvidence.desktop.ready -and $candidateEvidence.windowVisible) {
                $hostEvidence = $candidateEvidence
                break
            }
        }
    }
    Start-Sleep -Milliseconds 500
}
if (-not $nativeProcess -or -not $hostEvidence) { throw 'Installed host did not report authenticated backend and visible resident surface within 120 seconds' }
$listener = @(Get-NetTCPConnection -State Listen -LocalPort $hostEvidence.backendPort -ErrorAction Stop | Where-Object { $_.LocalAddress -eq '127.0.0.1' })
if ($listener.Count -ne 1) { throw 'Expected exactly one private IPv4 backend listener' }
$backendProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
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
    $unexpectedPublicResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($hostEvidence.backendPort)/axx-api/status" -TimeoutSec 2
    throw 'Private backend unexpectedly accepted a request without its host token'
} catch {
    if ($_.Exception.Response) { $httpStatus = [int]$_.Exception.Response.StatusCode }
    if ($httpStatus -ne 401) { throw }
}
$runtime = [ordered]@{
    result='INSTALLED_RUNTIME_STARTED';version=$build.artifacts[0].version;
    started=$started.ToString('o');completed=[DateTimeOffset]::Now.ToString('o');
    installer=$installer.FullName;installer_sha256=$build.artifacts[0].sha256;installer_exit=$installProcess.ExitCode;
    executable=$appExecutable;pid=$nativeProcess.ProcessId;launch='Installed EXE; UseShellExecute=false; closed launcher streams; PATH limited to Windows; Python environment overrides removed';
    launched_at=$launchTime.ToString('o');working_directory=$appDirectory;
    backend=@{pid=$backendProcess.ProcessId;port=$hostEvidence.backendPort;instance_id=$hostEvidence.backendInstance;executable=$backendProcess.ExecutablePath;authenticated_by_native_host=$hostEvidence.backendReady;unauthenticated_http_status=$httpStatus};
    native_surface=$hostEvidence.desktop;native_window_visible=$hostEvidence.windowVisible;
    registry=@{display_version=$registry.DisplayVersion;install_location=$registry.InstallLocation;uninstall=$registry.UninstallString};
    shortcuts=$links;visual_acceptance='Separate native observation required';recording='NOT_VERIFIED'
}
$runtime | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidencePath 'installed-runtime.json') -Encoding UTF8
Copy-Item -LiteralPath $evidenceFile -Destination (Join-Path $evidencePath 'installed-native-runtime.json') -Force
$runtime | ConvertTo-Json -Depth 6
