Stop-Process -Name Axx, axx-backend -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$exe = "$env:LOCALAPPDATA\Programs\Axx\Axx.exe"
Write-Output "Launching: $exe"
$proc = Start-Process -FilePath $exe -RedirectStandardOutput "axx_stdout.log" -RedirectStandardError "axx_stderr.log" -PassThru
Start-Sleep -Seconds 5
$p = Get-Process -Name Axx -ErrorAction SilentlyContinue
if ($p) {
    Write-Output "Axx is running with PID: $($p.Id)"
} else {
    Write-Output "Axx process not found (may have exited)"
}
