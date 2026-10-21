Add-Type -AssemblyName System.Windows.Forms
foreach ($s in [System.Windows.Forms.Screen]::AllScreens) {
    Write-Host "Device: $($s.DeviceName) Bounds: $($s.Bounds.Width)x$($s.Bounds.Height) WorkArea: $($s.WorkingArea.X),$($s.WorkingArea.Y) $($s.WorkingArea.Width)x$($s.WorkingArea.Height)"
}
