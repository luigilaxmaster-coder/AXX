Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinSearch {
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

$axxProc = Get-Process Axx -ErrorAction SilentlyContinue
if (-not $axxProc) { Write-Output "No Axx process"; exit }
$targetPid = [uint32]$axxProc.Id
Write-Output "Inspecting Axx PID: $targetPid"

$callback = [WinSearch+EnumWindowsProc]{
    param($hWnd, $lParam)
    $pidOut = [uint32]0
    [void][WinSearch]::GetWindowThreadProcessId($hWnd, [ref]$pidOut)
    if ($pidOut -eq $targetPid) {
        $sbTitle = New-Object System.Text.StringBuilder 256
        [void][WinSearch]::GetWindowText($hWnd, $sbTitle, 256)
        $sbClass = New-Object System.Text.StringBuilder 256
        [void][WinSearch]::GetClassName($hWnd, $sbClass, 256)
        $vis = [WinSearch]::IsWindowVisible($hWnd)
        $rect = New-Object WinSearch+RECT
        [void][WinSearch]::GetWindowRect($hWnd, [ref]$rect)
        $w = $rect.Right - $rect.Left
        $h = $rect.Bottom - $rect.Top
        Write-Output "HWND: $hWnd | Vis: $vis | Class: $($sbClass.ToString()) | Title: '$($sbTitle.ToString())' | Rect: [$($rect.Left), $($rect.Top), w=$w, h=$h]"
    }
    return $true
}
[void][WinSearch]::EnumWindows($callback, [IntPtr]::Zero)
