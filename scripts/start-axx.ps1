Add-Type @"
using System;
using System.Runtime.InteropServices;

public class DesktopLauncher {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct STARTUPINFO {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX;
        public int dwY;
        public int dwXSize;
        public int dwYSize;
        public int dwXCountChars;
        public int dwYCountChars;
        public int dwFillAttribute;
        public int dwFlags;
        public short wShowWindow;
        public short cbReserved2;
        public IntPtr lpReserved2;
        public IntPtr hStdInput;
        public IntPtr hStdOutput;
        public IntPtr hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION {
        public IntPtr hProcess;
        public IntPtr hThread;
        public int dwProcessId;
        public int dwThreadId;
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool CreateProcess(
        string lpApplicationName,
        string lpCommandLine,
        IntPtr lpProcessAttributes,
        IntPtr lpThreadAttributes,
        bool bInheritHandles,
        uint dwCreationFlags,
        IntPtr lpEnvironment,
        string lpCurrentDirectory,
        ref STARTUPINFO lpStartupInfo,
        out PROCESS_INFORMATION lpProcessInformation
    );

    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr hObject);

    public static int Launch(string appPath, string desktopName) {
        STARTUPINFO si = new STARTUPINFO();
        si.cb = Marshal.SizeOf(si);
        si.lpDesktop = desktopName;

        PROCESS_INFORMATION pi = new PROCESS_INFORMATION();

        bool success = CreateProcess(
            appPath,
            null,
            IntPtr.Zero,
            IntPtr.Zero,
            false,
            0,
            IntPtr.Zero,
            null,
            ref si,
            out pi
        );

        if (!success) {
            int err = Marshal.GetLastWin32Error();
            throw new Exception("CreateProcess failed with error: " + err);
        }

        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return pi.dwProcessId;
    }
}
"@

Stop-Process -Name Axx, axx-backend -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$exe = "$env:LOCALAPPDATA\Programs\Axx\Axx.exe"
if (-not (Test-Path $exe)) {
    $localExe = Join-Path $PSScriptRoot "..\src-tauri\target\release\Axx.exe"
    if (Test-Path $localExe) {
        $exe = (Resolve-Path $localExe).Path
    } else {
        throw "Axx.exe not found at $exe or $localExe"
    }
}

Write-Host "Launching Axx on WinSta0\Default..."
$launchedPid = [DesktopLauncher]::Launch($exe, "WinSta0\Default")
Write-Host "Axx launched with PID: $launchedPid"

Start-Sleep -Seconds 3
$proc = Get-Process -Id $launchedPid -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "Axx process is alive ($($proc.Id)). Holding daemon loop..."
    while ($true) {
        Start-Sleep -Seconds 5
        $check = Get-Process -Id $launchedPid -ErrorAction SilentlyContinue
        if (-not $check) {
            Write-Host "Axx process exited."
            break
        }
    }
} else {
    Write-Host "Axx process did not stay running."
}
