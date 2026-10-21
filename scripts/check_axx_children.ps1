$axx = Get-Process -Name Axx -ErrorAction SilentlyContinue
if (-not $axx) {
    Write-Host "No Axx process found."
    exit
}
Write-Host "Axx PID: $($axx.Id)"
$children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $axx.Id }
Write-Host "Children of Axx ($($children.Count)):"
foreach ($c in $children) {
    Write-Host "  PID: $($c.ProcessId) Name: $($c.Name) Cmd: $($c.CommandLine)"
}
