Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DpiHelper {
    [DllImport("user32.dll")]
    public static extern IntPtr GetDC(IntPtr hwnd);
    [DllImport("gdi32.dll")]
    public static extern int GetDeviceCaps(IntPtr hdc, int nIndex);
    [DllImport("user32.dll")]
    public static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);

    public static double GetDpi() {
        IntPtr hdc = GetDC(IntPtr.Zero);
        int logPixelsX = GetDeviceCaps(hdc, 88); // LOGPIXELSX
        ReleaseDC(IntPtr.Zero, hdc);
        return logPixelsX / 96.0;
    }
}
"@
$scale = [DpiHelper]::GetDpi()
Write-Host "DPI scale: $scale ($( [DpiHelper]::GetDpi() * 100 )%)"
