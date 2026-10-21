"""Windows Process Manager with Win32 Job Objects.
Ensures that when a worker process is terminated or cancelled,
all child and descendant processes are killed atomically, leaving NO orphans.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import subprocess
import sys
import time

LOG = logging.getLogger('axx.process_manager')

# Win32 Constants for Job Objects
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ('ReadOperationCount', ctypes.c_uint64),
        ('WriteOperationCount', ctypes.c_uint64),
        ('OtherOperationCount', ctypes.c_uint64),
        ('ReadTransferCount', ctypes.c_uint64),
        ('WriteTransferCount', ctypes.c_uint64),
        ('OtherTransferCount', ctypes.c_uint64),
    ]

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('PerProcessUserTimeLimit', wintypes.LARGE_INTEGER),
        ('PerJobUserTimeLimit', wintypes.LARGE_INTEGER),
        ('LimitFlags', wintypes.DWORD),
        ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t),
        ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t),
        ('PriorityClass', wintypes.DWORD),
        ('SchedulingClass', wintypes.DWORD),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ('IoInfo', IO_COUNTERS),
        ('ProcessMemoryLimit', ctypes.c_size_t),
        ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryLimit', ctypes.c_size_t),
        ('PeakJobMemoryLimit', ctypes.c_size_t),
    ]

class WindowsJobObject:
    """Encapsulates a Win32 Job Object configured to kill all processes on close."""
    def __init__(self, name: str | None = None):
        self.handle = None
        if os.name == 'nt':
            try:
                kernel32 = ctypes.windll.kernel32
                # ctypes defaults to 32-bit int return values; HANDLE is pointer-sized.
                kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
                kernel32.CreateJobObjectW.restype = wintypes.HANDLE
                kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
                kernel32.SetInformationJobObject.restype = wintypes.BOOL
                kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
                kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle.restype = wintypes.BOOL
                self.handle = kernel32.CreateJobObjectW(None, name)
                if not self.handle:
                    LOG.warning("CreateJobObjectW failed with error %s", kernel32.GetLastError())
                    return

                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                res = kernel32.SetInformationJobObject(
                    self.handle,
                    JobObjectExtendedLimitInformation,
                    ctypes.byref(info),
                    ctypes.sizeof(info)
                )
                if not res:
                    LOG.warning("SetInformationJobObject failed with error %s", kernel32.GetLastError())
            except Exception as e:
                LOG.warning("Win32 Job Object setup exception: %s", e)

    def assign_process(self, process_handle) -> bool:
        """Assigns a Windows process handle to this job object."""
        if os.name == 'nt' and self.handle and process_handle:
            try:
                res = ctypes.windll.kernel32.AssignProcessToJobObject(self.handle, int(process_handle))
                return bool(res)
            except Exception as e:
                LOG.warning("AssignProcessToJobObject exception: %s", e)
                return False
        return False

    def close(self):
        """Closing the job object handle terminates all processes assigned to it."""
        if os.name == 'nt' and self.handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self.handle)
            except Exception as e:
                LOG.warning("CloseHandle exception on Job Object: %s", e)
            finally:
                self.handle = None

def spawn_managed_process(cmd: list[str], **kwargs) -> tuple[subprocess.Popen, WindowsJobObject | None]:
    """Spawns a process attached to a dedicated Job Object on Windows."""
    job = None
    if os.name == 'nt':
        job = WindowsJobObject()
        # Suppress console window for GUI/Sidecar usage
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except Exception:
        if job:
            job.close()
        raise

    if job and job.handle and proc._handle:
        job.assign_process(proc._handle)

    return proc, job

def terminate_process_tree(proc: subprocess.Popen, job: WindowsJobObject | None = None, timeout: float = 2.0):
    """Terminates process and all its children via Job Object, with taskkill /T /F fallback."""
    if proc.poll() is not None:
        if job:
            job.close()
        return

    pid = proc.pid
    # 1. Close Job Object if available (triggers atomic kernel kill of all assigned processes)
    if job:
        job.close()

    # 2. Try standard proc.terminate()
    try:
        proc.terminate()
        proc.wait(timeout=0.5)
    except Exception:
        pass

    # 3. If still alive on Windows, invoke taskkill /T /F as fallback guarantee
    if proc.poll() is None and os.name == 'nt':
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False
            )
        except Exception as e:
            LOG.warning("taskkill fallback failed for PID %s: %s", pid, e)

    # 4. Final kill if still running
    if proc.poll() is None:
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except Exception:
            pass
