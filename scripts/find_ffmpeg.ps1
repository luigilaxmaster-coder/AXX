$files = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue
if ($files) {
    Write-Host "Found ffmpeg at: $($files[0].FullName)"
} else {
    Write-Host "Searching in Program Files..."
    $files = Get-ChildItem -Path "C:\Program Files" -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue
    if ($files) {
        Write-Host "Found ffmpeg at: $($files[0].FullName)"
    } else {
        Write-Host "Not found yet."
    }
}
