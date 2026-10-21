$sh = New-Object -ComObject WScript.Shell
$target = $sh.CreateShortcut("C:\Users\luigi\Desktop\Axx.lnk")
Write-Output "TargetPath: $($target.TargetPath)"
Write-Output "IconLocation: $($target.IconLocation)"
