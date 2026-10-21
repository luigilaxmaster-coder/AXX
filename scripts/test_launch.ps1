$exe = "$env:LOCALAPPDATA\Programs\Axx\Axx.exe"
Write-Output "Launching: $exe"
$p = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 2
Write-Output "HasExited: $($p.HasExited)"
if ($p.HasExited) {
    Write-Output "ExitCode: $($p.ExitCode)"
} else {
    Write-Output "PID: $($p.Id)"
    Write-Output "MainWindowHandle: $($p.MainWindowHandle)"
}
