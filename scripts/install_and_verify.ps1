Stop-Process -Name Axx, axx-backend -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$installer = (Get-ChildItem (Join-Path $PSScriptRoot "..\src-tauri\target\release\bundle\nsis\Axx_*_x64-setup.exe") | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
Write-Output "Installing: $installer"
$proc = Start-Process -FilePath $installer -ArgumentList "/S" -Wait -PassThru
Write-Output "Installer ExitCode: $($proc.ExitCode)"
Start-Sleep -Seconds 2
$installedExe = "$env:LOCALAPPDATA\Programs\Axx\Axx.exe"
$ver = (Get-Item $installedExe).VersionInfo.FileVersion
Write-Output "Installed Version: $ver"
