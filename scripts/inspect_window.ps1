Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinUtil {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")]
    public static extern int GetClassName(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
}
'@

$relatedPids = @(Get-Process -Name Axx, msedgewebview2 -ErrorAction SilentlyContinue | ForEach-Object { [uint32]$_.Id })
Write-Output "Scanning for PIDs: $($relatedPids -join ', ')"

$callback = [WinUtil+EnumWindowsProc]{
    param($hWnd, $lParam)
    $pidOut = [uint32]0
    [void][WinUtil]::GetWindowThreadProcessId($hWnd, [ref]$pidOut)
    if ($pidOut -in $relatedPids) {
        $sbTitle = New-Object System.Text.StringBuilder 256
        [void][WinUtil]::GetWindowText($hWnd, $sbTitle, 256)
        $sbClass = New-Object System.Text.StringBuilder 256
        [void][WinUtil]::GetClassName($hWnd, $sbClass, 256)
        $title = $sbTitle.ToString()
        $class = $sbClass.ToString()
        $vis = [WinUtil]::IsWindowVisible($hWnd)
        $rect = New-Object WinUtil+RECT
        [void][WinUtil]::GetWindowRect($hWnd, [ref]$rect)
        $w = $rect.Right - $rect.Left
        $h = $rect.Bottom - $rect.Top
        Write-Output "HWND: $hWnd | PID: $pidOut | Vis: $vis | Class: $class | Title: '$title' | Rect: [$($rect.Left), $($rect.Top), w=$w, h=$h]"
    }
    return $true
}
[void][WinUtil]::EnumWindows($callback, [IntPtr]::Zero)
