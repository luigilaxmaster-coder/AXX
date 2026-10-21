Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public class WinStationHelper {
    [DllImport("user32.dll")]
    public static extern IntPtr GetProcessWindowStation();

    [DllImport("user32.dll")]
    public static extern IntPtr GetThreadDesktop(int dwThreadId);

    [DllImport("kernel32.dll")]
    public static extern int GetCurrentThreadId();

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool GetUserObjectInformation(IntPtr hObj, int nIndex, StringBuilder pvInfo, int nLength, out int lpnLengthNeeded);

    public static string GetInfo() {
        IntPtr hWinsta = GetProcessWindowStation();
        StringBuilder sb = new StringBuilder(256);
        int len;
        GetUserObjectInformation(hWinsta, 2, sb, 256, out len); // UOI_NAME = 2
        string winstaName = sb.ToString();

        IntPtr hDesk = GetThreadDesktop(GetCurrentThreadId());
        sb.Clear();
        GetUserObjectInformation(hDesk, 2, sb, 256, out len);
        string deskName = sb.ToString();

        return "WinStation: " + winstaName + ", Desktop: " + deskName;
    }
}
"@
Write-Host ([WinStationHelper]::GetInfo())
