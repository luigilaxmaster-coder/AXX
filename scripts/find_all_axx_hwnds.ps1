Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Win32Hwnd2 {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll", SetLastError=true)]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern int GetClassName(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
}
"@

$allPids = @()
Get-Process | Where-Object { $_.ProcessName -match "Axx|msedgewebview2" } | ForEach-Object { $allPids += $_.Id }

[Win32Hwnd2]::EnumWindows({
    param($hwnd, $lparam)
    $procId = 0
    [Win32Hwnd2]::GetWindowThreadProcessId($hwnd, [ref]$procId)
    if ($allPids -contains $procId) {
        $sbTitle = New-Object System.Text.StringBuilder 256
        [Win32Hwnd2]::GetWindowText($hwnd, $sbTitle, 256) | Out-Null
        $sbClass = New-Object System.Text.StringBuilder 256
        [Win32Hwnd2]::GetClassName($hwnd, $sbClass, 256) | Out-Null
        $rect = New-Object Win32Hwnd2+RECT
        [Win32Hwnd2]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
        $vis = [Win32Hwnd2]::IsWindowVisible($hwnd)
        $procName = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
        Write-Host "HWND: $hwnd | PID: $procId ($procName) | Title: '$sbTitle' | Class: '$sbClass' | Visible: $vis | Rect: ($($rect.Left), $($rect.Top)) - ($($rect.Right), $($rect.Bottom)) [Size: $($rect.Right - $rect.Left) x $($rect.Bottom - $rect.Top)]"
    }
    return $true
}, [IntPtr]::Zero) | Out-Null
