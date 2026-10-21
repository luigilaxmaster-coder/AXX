Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
}
"@

$procs = Get-Process -Name Axx -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    $rect = New-Object Win32+RECT
    $hasRect = [Win32]::GetWindowRect($p.MainWindowHandle, [ref]$rect)
    $visible = [Win32]::IsWindowVisible($p.MainWindowHandle)
    Write-Host "PID: $($p.Id) HWND: $($p.MainWindowHandle) Visible: $visible Rect: ($($rect.Left), $($rect.Top)) - ($($rect.Right), $($rect.Bottom)) [Size: $($rect.Right - $rect.Left) x $($rect.Bottom - $rect.Top)]"
}
