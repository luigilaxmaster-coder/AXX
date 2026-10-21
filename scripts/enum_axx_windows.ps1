Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class EnumWin {
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

$proc = Get-Process -Name Axx -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) {
    Write-Output "Axx process not found"
    exit 0
}
Write-Output "Found Axx PID: $($proc.Id)"

$targetPid = [uint32]$proc.Id
$callback = [EnumWin+EnumWindowsProc]{
    param($hWnd, $lParam)
    $pidOut = [uint32]0
    [EnumWin]::GetWindowThreadProcessId($hWnd, [ref]$pidOut)
    if ($pidOut -eq $targetPid) {
        $sbTitle = New-Object System.Text.StringBuilder 256
        [EnumWin]::GetWindowText($hWnd, $sbTitle, 256)
        $sbClass = New-Object System.Text.StringBuilder 256
        [EnumWin]::GetClassName($hWnd, $sbClass, 256)
        $rect = New-Object EnumWin+RECT
        [EnumWin]::GetWindowRect($hWnd, [ref]$rect)
        $vis = [EnumWin]::IsWindowVisible($hWnd)
        $w = $rect.Right - $rect.Left
        $h = $rect.Bottom - $rect.Top
        Write-Output "HWND: $hWnd | Class: $($sbClass.ToString()) | Title: '$($sbTitle.ToString())' | Vis: $vis | Rect: [$($rect.Left), $($rect.Top), w=$w, h=$h]"
    }
    return $true
}

[EnumWin]::EnumWindows($callback, [IntPtr]::Zero)
