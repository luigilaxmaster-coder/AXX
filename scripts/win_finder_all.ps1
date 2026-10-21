Add-Type @"
using System;
using System.Collections.Generic;
using System.Text;
using System.Runtime.InteropServices;

public class WinFinderAll {
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

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static List<string> FindAllInteresting() {
        var results = new List<string>();
        EnumWindows((hwnd, lParam) => {
            var sbTitle = new StringBuilder(256);
            GetWindowText(hwnd, sbTitle, 256);
            var sbClass = new StringBuilder(256);
            GetClassName(hwnd, sbClass, 256);
            string title = sbTitle.ToString();
            string cls = sbClass.ToString();
            uint pid;
            GetWindowThreadProcessId(hwnd, out pid);
            RECT r;
            GetWindowRect(hwnd, out r);
            bool vis = IsWindowVisible(hwnd);

            if (title.IndexOf("Axx", StringComparison.OrdinalIgnoreCase) >= 0 ||
                cls.IndexOf("Axx", StringComparison.OrdinalIgnoreCase) >= 0 ||
                cls.IndexOf("WebView", StringComparison.OrdinalIgnoreCase) >= 0 ||
                cls.IndexOf("Chrome_WidgetWin", StringComparison.OrdinalIgnoreCase) >= 0 ||
                cls.IndexOf("tauri", StringComparison.OrdinalIgnoreCase) >= 0) {
                results.Add(string.Format("PID: {0} | HWND: 0x{1:X} | Vis: {2} | Rect: ({3},{4})-({5},{6}) [{7}x{8}] | Title: '{9}' | Class: '{10}'",
                    pid, hwnd.ToInt64(), vis, r.Left, r.Top, r.Right, r.Bottom, r.Right - r.Left, r.Bottom - r.Top, title, cls));
            }
            return true;
        }, IntPtr.Zero);
        return results;
    }
}
"@

$res = [WinFinderAll]::FindAllInteresting()
Write-Host "Found $($res.Count) matching windows:"
$res | ForEach-Object { Write-Host $_ }
