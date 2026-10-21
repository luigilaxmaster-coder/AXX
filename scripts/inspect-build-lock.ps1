param([string]$OutputPath = 'evidence\command-library-20261019\build-lock-owner.json')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$lockPath = Join-Path $projectRoot 'build\.windows-delivery.lock'
if (-not ('AxxBuildLockProbe' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class AxxBuildLockProbe {
    [StructLayout(LayoutKind.Sequential)] public struct UniqueProcess { public int Id; public FILETIME Started; }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct Info {
        public UniqueProcess Process;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string AppName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=64)] public string ServiceName;
        public int AppType; public uint Status; public uint Session;
        [MarshalAs(UnmanagedType.Bool)] public bool Restartable;
    }
    [DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)] static extern int RmStartSession(out uint handle, int flags, StringBuilder key);
    [DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)] static extern int RmRegisterResources(uint handle, uint files, string[] names, uint apps, UniqueProcess[] processes, uint services, string[] serviceNames);
    [DllImport("rstrtmgr.dll")] static extern int RmGetList(uint handle, out uint needed, ref uint count, [In, Out] Info[] list, out uint reason);
    [DllImport("rstrtmgr.dll")] static extern int RmEndSession(uint handle);
    public static Info[] Owners(string path) {
        uint handle; int result = RmStartSession(out handle, 0, new StringBuilder(Guid.NewGuid().ToString("N"), 33));
        if (result != 0) throw new Exception("RmStartSession error " + result);
        try {
            result = RmRegisterResources(handle, 1, new string[]{path}, 0, null, 0, null);
            if (result != 0) throw new Exception("RmRegisterResources error " + result);
            uint needed, count=0, reason;
            result=RmGetList(handle,out needed,ref count,null,out reason);
            if (result==0) return new Info[0];
            if (result!=234) throw new Exception("RmGetList error " + result);
            for(int retry=0;retry<3;retry++) {
                count=needed; var list=new Info[count];
                result=RmGetList(handle,out needed,ref count,list,out reason);
                if(result==0) { Array.Resize(ref list,(int)count); return list; }
                if(result!=234) throw new Exception("RmGetList error " + result);
            }
            throw new Exception("Owner list changed during inspection");
        } finally { RmEndSession(handle); }
    }
}
'@
}
$available = $false
try { $probe=[IO.File]::Open($lockPath,'Open','ReadWrite','None'); $probe.Dispose(); $available=$true } catch {}
$owners = @()
foreach ($item in [AxxBuildLockProbe]::Owners($lockPath)) {
    $ownerProcess = Get-Process -Id $item.Process.Id -ErrorAction SilentlyContinue
    $owners += [ordered]@{pid=$item.Process.Id;name=$ownerProcess.ProcessName;app=$item.AppName;
        start_utc=$(if($ownerProcess){$ownerProcess.StartTime.ToUniversalTime().ToString('o')});
        cpu_seconds=$(if($ownerProcess){$ownerProcess.CPU});session=$item.Session}
}
$report = [ordered]@{observed_utc=[DateTimeOffset]::UtcNow.ToString('o');path=$lockPath;available=$available;owners=$owners}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $projectRoot $OutputPath) -Encoding UTF8
$report | ConvertTo-Json -Depth 6
