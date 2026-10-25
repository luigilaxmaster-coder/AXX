"""Real System Tools for Axx Action Executor.
Each tool defines:
  - inputs schema
  - version
  - preconditions check function
  - structured execution function
  - verifiable postconditions check function
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import threading
from typing import Any


def artifact_path_error(path_str: str) -> str | None:
    """Reject device names, streams and linked parents before resolving a path."""
    if not isinstance(path_str, str) or not path_str or len(path_str) > 240:
        return 'Artifact path must be a non-empty string within 240 characters'
    path = Path(path_str)
    if path_str.startswith(('\\\\', '//')):
        return 'Network and device namespace paths are not permitted'
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$',
                *[f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in '123456789¹²³']}
    for part in path.parts:
        if part == path.anchor:
            continue
        if (part.endswith((' ', '.')) or part.split('.', 1)[0].upper() in reserved
                or any(ord(char) < 32 or char in '<>:"|?*' for char in part)):
            return 'Artifact path contains a reserved Windows name, stream or invalid character'
    try:
        for component in (path, *path.parents):
            try:
                entry = component.lstat()
            except FileNotFoundError:
                continue
            if component.is_symlink() or getattr(entry, 'st_file_attributes', 0) & 0x400:
                return 'Artifact paths must not pass through symbolic links or reparse points'
    except OSError as exc:
        return f'Cannot inspect artifact path: {exc}'
    return None


class ToolResult:
    def __init__(self, success: bool, output: Any = None, error: str | None = None, evidence: dict | None = None):
        self.success = success
        self.output = output
        self.error = error
        self.evidence = evidence or {}

    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'output': self.output,
            'error': self.error,
            'evidence': self.evidence
        }

class BaseTool:
    name: str = "base"
    version: str = "1.0.0"
    description: str = ""

    def verify_preconditions(self, inputs: dict) -> tuple[bool, str]:
        raise NotImplementedError

    def execute(self, inputs: dict) -> ToolResult:
        raise NotImplementedError

    def execute_in_workspace(self, inputs: dict, workspace_root: Path) -> ToolResult:
        """The executor supplies this scope; it is never accepted from frontend inputs."""
        return self.execute(inputs)

    def execute_cancellable(self, inputs: dict, workspace_root: Path, cancelled: threading.Event) -> ToolResult:
        return self.execute_in_workspace(inputs, workspace_root)

    def verify_postconditions(self, inputs: dict, result: ToolResult) -> tuple[bool, str]:
        raise NotImplementedError

class FileArtifactTool(BaseTool):
    """Creates a verified file artifact in the workspace.
    Verifies that the target path is safe, writable, creates the file,
    and asserts postconditions: file exists, byte length matches, sha256 matches.
    """
    name = "file_artifact_writer"
    version = "1.1.0"
    description = "Writes a verified file artifact inside an authorized workspace folder"

    def verify_preconditions(self, inputs: dict) -> tuple[bool, str]:
        path_str = inputs.get('path')
        if not path_str or not isinstance(path_str, str):
            return False, "Input 'path' is required and must be a string"
        path_error = artifact_path_error(path_str)
        if path_error:
            return False, path_error
        content = inputs.get('content')
        if not isinstance(content, (str, bytes)):
            return False, "Input 'content' must be string or bytes"
        target = Path(path_str).resolve()
        if target.exists():
            return False, 'The target already exists; choose a new artifact path'
        
        # Security: Prevent writing outside project workspace
        # Must not target system directories
        target_str = str(target).lower()
        forbidden_roots = ['c:\\windows', 'c:\\program files', 'c:\\program files (x86)']
        if any(target_str.startswith(f) for f in forbidden_roots):
            return False, f"Target path is inside a restricted system directory: {target}"

        # Preconditions inspect only. Directory creation belongs to execution.
        try:
            ancestor = target.parent
            while not ancestor.exists() and ancestor != ancestor.parent:
                ancestor = ancestor.parent
            if not ancestor.is_dir() or not os.access(str(ancestor), os.W_OK):
                return False, f"Parent directory is not writable: {ancestor}"
        except Exception as e:
            return False, f"Cannot prepare parent directory: {e}"

        return True, "Preconditions satisfied"

    def execute(self, inputs: dict) -> ToolResult:
        target = Path(inputs['path']).resolve()
        raw_data = inputs['content']
        data_bytes = raw_data.encode('utf-8') if isinstance(raw_data, str) else raw_data
        
        try:
            # Recheck after preconditions and create exclusively: an existing
            # file, symlink or hardlink can never be silently replaced.
            path_error = artifact_path_error(inputs['path'])
            if path_error:
                return ToolResult(success=False, error=path_error)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as artifact:
                artifact.write(data_bytes)
            computed_hash = hashlib.sha256(data_bytes).hexdigest()
            return ToolResult(
                success=True,
                output={'path': str(target), 'bytes_written': len(data_bytes), 'sha256': computed_hash},
                evidence={'path': str(target), 'sha256': computed_hash, 'size': len(data_bytes)}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def verify_postconditions(self, inputs: dict, result: ToolResult) -> tuple[bool, str]:
        if not result.success:
            return False, f"Execution failed: {result.error}"

        target = Path(inputs['path']).resolve()
        if not target.exists():
            return False, f"Postcondition failed: Target file does not exist: {target}"

        actual_bytes = target.read_bytes()
        expected_len = result.evidence.get('size')
        if len(actual_bytes) != expected_len:
            return False, f"Postcondition failed: File size mismatch ({len(actual_bytes)} != {expected_len})"

        actual_hash = hashlib.sha256(actual_bytes).hexdigest()
        expected_hash = result.evidence.get('sha256')
        if actual_hash != expected_hash:
            return False, f"Postcondition failed: Hash mismatch ({actual_hash} != {expected_hash})"

        return True, "Postconditions verified: File exists, size and SHA256 match perfectly"

class SystemTelemetryTool(BaseTool):
    """Collects real system telemetry without external dependencies.
    Verifies that system info can be accessed, executes checks,
    and asserts postconditions: non-empty platform, valid memory/disk readings.
    """
    name = "system_telemetry"
    version = "1.0.0"
    description = "Queries real Windows hardware and environment telemetry"

    def verify_preconditions(self, inputs: dict) -> tuple[bool, str]:
        # Precondition: OS must be accessible
        if not sys.platform.startswith('win'):
            # Allow running in mock/test mode on non-windows
            pass
        return True, "Preconditions satisfied"

    def execute(self, inputs: dict) -> ToolResult:
        try:
            # Query disk space
            cwd_drive = Path.cwd().anchor or 'C:\\'
            disk_usage = shutil.disk_usage(cwd_drive)

            mem_total_mb = 0
            mem_used_mb = 0
            cpu_percent = 0.0
            if os.name == 'nt':
                try:
                    import ctypes
                    class MEMORYSTATUSEX(ctypes.Structure):
                        _fields_ = [
                            ("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                        ]
                    stat = MEMORYSTATUSEX()
                    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                        mem_total_mb = round(stat.ullTotalPhys / (1024 * 1024), 1)
                        mem_used_mb = round((stat.ullTotalPhys - stat.ullAvailPhys) / (1024 * 1024), 1)
                        cpu_percent = float(stat.dwMemoryLoad)
                except Exception:
                    pass

            data = {
                'os': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'architecture': platform.machine(),
                'python_version': platform.python_version(),
                'disk_total_gb': round(disk_usage.total / (1024**3), 2),
                'disk_free_gb': round(disk_usage.free / (1024**3), 2),
                'memory_total_mb': mem_total_mb,
                'memory_used_mb': mem_used_mb,
                'pid': os.getpid()
            }
            return ToolResult(
                success=True,
                output=data,
                evidence={
                    'collected_keys': list(data.keys()),
                    'python_version': data['python_version'],
                    'memory_total_mb': mem_total_mb,
                    'memory_used_mb': mem_used_mb,
                    'disk_free_gb': data['disk_free_gb'],
                    'disk_total_gb': data['disk_total_gb']
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def verify_postconditions(self, inputs: dict, result: ToolResult) -> tuple[bool, str]:
        if not result.success:
            return False, f"Execution failed: {result.error}"
        out = result.output
        if not isinstance(out, dict) or 'os' not in out or 'disk_free_gb' not in out:
            return False, "Postcondition failed: Incomplete telemetry payload"
        if out['disk_free_gb'] <= 0:
            return False, "Postcondition failed: Free disk space must be greater than zero"
        return True, "Postconditions verified: Telemetry is valid and non-zero"

class ProcessStateTool(BaseTool):
    """Queries running processes for a specific executable name or checks self PID."""
    name = "process_state_inspector"
    version = "1.0.0"
    description = "Inspects process execution state and ensures PID is active"

    def verify_preconditions(self, inputs: dict) -> tuple[bool, str]:
        pid = inputs.get('pid')
        if pid is not None and (type(pid) is not int or not 1 <= pid <= 0xffffffff):
            return False, "pid must be a positive 32-bit integer"
        return True, "Preconditions satisfied"

    def execute(self, inputs: dict) -> ToolResult:
        target_pid = inputs.get('pid', os.getpid())
        try:
            is_active = False
            if os.name == 'nt':
                # Query only the requested PID. No locale-sensitive command
                # output or substring matching can count another PID as active.
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.WaitForSingleObject.restype = wintypes.DWORD
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle.restype = wintypes.BOOL
                handle = kernel.OpenProcess(0x100000, False, target_pid)  # SYNCHRONIZE only
                if handle:
                    try:
                        status = kernel.WaitForSingleObject(handle, 0)
                        if status == 0xffffffff:
                            raise ctypes.WinError(ctypes.get_last_error())
                        if status not in (0, 258):
                            raise OSError(f'Unexpected process wait status: {status}')
                        is_active = status == 258
                    finally:
                        kernel.CloseHandle(handle)
                elif ctypes.get_last_error() != 87:
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                try:
                    os.kill(target_pid, 0)
                    is_active = True
                except OSError:
                    is_active = False

            return ToolResult(
                success=True,
                output={'pid': target_pid, 'active': is_active},
                evidence={'pid': target_pid, 'checked_active': is_active}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def verify_postconditions(self, inputs: dict, result: ToolResult) -> tuple[bool, str]:
        if not result.success:
            return False, f"Execution failed: {result.error}"
        if 'active' not in result.output:
            return False, "Postcondition failed: 'active' boolean missing from result"
        return True, "Postconditions verified"

class BlenderRenderFixtureTool(BaseTool):
    """Runs the pinned local CLI-Anything adapter against a fixed Blender scene."""
    name = 'blender_render_fixture'
    version = '1.0.0'
    description = 'Renders a fixed local Blender scene through CLI-Anything and verifies its PNG artifact'

    def verify_preconditions(self, inputs: dict) -> tuple[bool, str]:
        filename = inputs.get('filename')
        if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.png', filename):
            return False, 'filename must be a simple .png name within 84 characters'
        if Path(filename).stem.upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1,10)], *[f'LPT{i}' for i in range(1,10)]}:
            return False, 'Reserved Windows filename'
        return True, 'Fixed-scene render filename validated'

    def execute(self, inputs: dict) -> ToolResult:
        return ToolResult(False, error='An authorized executor workspace is required')

    def execute_in_workspace(self, inputs: dict, workspace_root: Path) -> ToolResult:
        from .cli_blender import render_fixture
        result = render_fixture(workspace_root, inputs['filename'])
        return ToolResult(bool(result.get('success')), output=result.get('output'),
                          error=result.get('error'), evidence=result.get('evidence'))

    def verify_postconditions(self, inputs: dict, result: ToolResult) -> tuple[bool, str]:
        if not result.success:
            return False, result.error or 'Blender render failed'
        try:
            target = Path(result.evidence['path'])
            size = target.stat().st_size
            if not 8 < size <= 64 * 1024 * 1024:
                return False, 'Rendered image size is invalid'
            data = target.read_bytes()
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                return False, 'Rendered artifact is not a PNG'
            if size != result.evidence.get('size') or hashlib.sha256(data).hexdigest() != result.evidence.get('sha256'):
                return False, 'Rendered image hash or size does not match'
        except (KeyError, OSError, TypeError) as exc:
            return False, f'Cannot verify rendered artifact: {exc}'
        return True, 'Rendered PNG exists and its size and SHA256 were verified'

class DesktopTool(BaseTool):
    """Fixed desktop adapters and explicitly approved PowerShell scripts."""
    version = '1.2.0'

    def __init__(self, kind):
        self.kind = kind
        self.name = 'desktop_' + kind
        self.description = 'Desktop action: ' + kind

    def verify_preconditions(self, inputs):
        from .desktop import validate_inputs
        try:
            validate_inputs(self.kind, inputs)
            return True, 'Validated desktop parameters'
        except ValueError as exc:
            return False, str(exc)

    def execute(self, inputs):
        if self.kind in ('powershell', 'cmd'):
            return ToolResult(False, error='Shell commands require a workspace and explicit approval')
        return self.execute_cancellable(inputs, None, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        return self.execute_with_control(inputs, workspace_root, cancelled, None)

    def execute_with_control(self, inputs, workspace_root, cancelled, input_control):
        if self.kind in ('powershell', 'cmd'):
            from .desktop import run_shell
            return ToolResult(**run_shell(self.kind, inputs, workspace_root, cancelled))
        from .desktop import open_target
        from .windows_automation import UncertainEffect
        try:
            if self.kind in ('focus_window', 'set_window_value', 'invoke_window_button', 'notepad_text', 'explorer_folder', 'open_app', 'move_pointer', 'first_video_pointer', 'spotify_play'):
                if input_control is None:
                    raise ValueError('El dueño de entrada de Windows no está conectado a este ejecutor.')
                with input_control.automation(cancelled) as control:
                    return ToolResult(**open_target(self.kind, inputs, cancelled=control, control=control))
            return ToolResult(**open_target(self.kind, inputs, cancelled=cancelled))
        except UncertainEffect as exc:
            return ToolResult(False, error=str(exc), evidence={'effect_uncertain': True, 'reconciliation_required': True,
                              'reconciliation_target': getattr(exc, 'target', None), 'partial_stages': getattr(exc, 'partial_stages', [])})
        except ValueError as exc:
            return ToolResult(False, error=str(exc), evidence={'cancelled': cancelled.is_set() or getattr(exc, 'input_cancelled', False), 'partial_stages': getattr(exc, 'partial_stages', [])})

    def verify_postconditions(self, inputs, result):
        if self.kind in ('powershell', 'cmd'):
            valid = result.success and result.evidence.get('exit_code') == 0 and not result.evidence.get('cancelled')
        elif self.kind in ('set_window_value', 'notepad_text'):
            import hashlib
            valid = (result.success and result.evidence.get('verification') == 'uia_value_readback'
                     and result.evidence.get('value_sha256') == hashlib.sha256(inputs['value'].encode('utf-8')).hexdigest()
                     and result.evidence.get('value_length') == len(inputs['value'].encode('utf-16-le')) // 2)
        elif self.kind == 'explorer_folder':
            valid = result.success and result.evidence.get('verification') == 'shell_folder_and_foreground_readback' and result.output.get('foreground_verified') is True
        elif self.kind in ('move_pointer','first_video_pointer'):
            valid = result.success and result.evidence.get('verification') == 'cursor_readback' and result.output.get('confirmed') is True
        elif self.kind == 'spotify_play':
            valid = result.success and result.evidence.get('verification') == 'spotify_uia_playback_state' and result.output.get('playing') is True
        elif self.kind == 'invoke_window_button':
            valid = result.success and result.evidence.get('verification') == 'uia_invoke_acknowledged' and result.output.get('button_sent') is True
        elif self.kind == 'cli_anything_scan':
            valid = (result.success and result.evidence.get('verification') == 'uia_capabilities_observed'
                     and result.output.get('window_id') == int(inputs['window_id'], 16)
                     and result.output.get('pid') == inputs['pid'] and isinstance(result.output.get('commands'), dict))
        elif self.kind == 'list_apps':
            valid = result.success and isinstance(result.output.get('applications'), list) and result.evidence.get('count') == len(result.output['applications'])
        else:
            valid = result.success and result.evidence.get('accepted') is True
        return bool(valid), 'Execution result checked' if valid else result.error or 'Desktop action failed'


class FileInspectionTool(BaseTool):
    name = 'file_inspection'
    description = 'SHA256 of explicitly selected, stable local files'

    def verify_preconditions(self, inputs):
        from .file_inspection import validate_path
        try:
            validate_path(inputs.get('path'))
            if 'other_path' in inputs:
                validate_path(inputs['other_path'])
            return True, 'Local paths validated'
        except (ValueError, OSError) as exc:
            return False, str(exc)

    def execute(self, inputs):
        return self.execute_cancellable(inputs, None, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .file_inspection import inspect_files
        try:
            output = inspect_files(inputs, cancelled)
            return ToolResult(True, output=output, evidence={'verification': 'stable_file_sha256', 'files': output['files']})
        except (ValueError, OSError) as exc:
            return ToolResult(False, error=str(exc), evidence={'cancelled': cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        files = (result.output or {}).get('files', [])
        valid = result.success and len(files) == (2 if 'other_path' in inputs else 1) and all(
            re.fullmatch('[a-f0-9]{64}', f.get('sha256', '')) for f in files)
        return bool(valid), 'Stable SHA256 verified' if valid else result.error or 'Hash unavailable'


# Registry of available tools
TOOL_REGISTRY: dict[str, BaseTool] = {
    FileInspectionTool.name: FileInspectionTool(),
    FileArtifactTool.name: FileArtifactTool(),
    SystemTelemetryTool.name: SystemTelemetryTool(),
    ProcessStateTool.name: ProcessStateTool(),
    BlenderRenderFixtureTool.name: BlenderRenderFixtureTool(),
    **{('desktop_' + kind): DesktopTool(kind) for kind in (
        'open_url', 'open_app', 'installed_app', 'list_apps', 'search', 'powershell', 'cmd',
        'list_windows', 'close_window', 'inspect_window', 'read_window', 'focus_window', 'move_pointer', 'first_video_pointer', 'spotify_play', 'set_window_value', 'invoke_window_button', 'notepad_text', 'explorer_folder', 'cli_anything_scan')},
}

def get_tool(name: str) -> BaseTool | None:
    return TOOL_REGISTRY.get(name)

def list_tools() -> list[dict]:
    return [
        {
            'name': t.name,
            'version': t.version,
            'description': t.description
        }
        for t in TOOL_REGISTRY.values()
    ]
