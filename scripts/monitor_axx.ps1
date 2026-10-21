Add-Type @'
using System;
using System.Runtime.InteropServices;
public class WinUtil {
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
}
'@

$exe = "$env:LOCALAPPDATA\Programs\Axx\Axx.exe"
Write-Output "Starting: $exe"
$p = Start-Process -FilePath $exe -PassThru
Write-Output "Started Axx. PID=$($p.Id)"

for ($i = 0; $i -lt 8; $i++) {
    Start-Sleep -Seconds 1
    $p.Refresh()
    if ($p.HasExited) {
        Write-Output "Axx EXITED at second $i with ExitCode: $($p.ExitCode)"
        break
    } else {
        $hwnd = $p.MainWindowHandle
        $rect = New-Object WinUtil+RECT
        $vis = [WinUtil]::IsWindowVisible($hwnd)
        [WinUtil]::GetWindowRect($hwnd, [ref]$rect)
        $w = $rect.Right - $rect.Left
        $h = $rect.Bottom - $rect.Top
        Write-Output "Second $i - Running. HWND=$hwnd, Visible=$vis, Rect=[$($rect.Left), $($rect.Top), w=$w, h=$h]"
    }
}

$backend = Get-Process -Name axx-backend -ErrorAction SilentlyContinue
Write-Output "Backend process: $(if ($backend) { $backend.Id } else { 'None' })"
