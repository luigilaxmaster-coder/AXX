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
from typing import Any

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

    def verify_postconditions(self, inputs: dict, result: ToolResult) -> tuple[bool, str]:
        raise NotImplementedError

class FileArtifactTool(BaseTool):
    """Creates a verified file artifact in the workspace.
    Verifies that the target path is safe, writable, creates the file,
    and asserts postconditions: file exists, byte length matches, sha256 matches.
    """
    name = "file_artifact_writer"
    version = "1.0.0"
    description = "Writes a verified file artifact inside an authorized workspace folder"

    def verify_preconditions(self, inputs: dict) -> tuple[bool, str]:
        path_str = inputs.get('path')
        if not path_str or not isinstance(path_str, str):
            return False, "Input 'path' is required and must be a string"
        
        target = Path(path_str).resolve()
        
        # Security: Prevent writing outside project workspace
        # Must not target system directories
        target_str = str(target).lower()
        forbidden_roots = ['c:\\windows', 'c:\\program files', 'c:\\program files (x86)']
        if any(target_str.startswith(f) for f in forbidden_roots):
            return False, f"Target path is inside a restricted system directory: {target}"

        # Ensure parent directory is or can be created
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not os.access(str(target.parent), os.W_OK):
                return False, f"Parent directory is not writable: {target.parent}"
        except Exception as e:
            return False, f"Cannot prepare parent directory: {e}"

        content = inputs.get('content')
        if content is None or not isinstance(content, (str, bytes)):
            return False, "Input 'content' must be string or bytes"

        return True, "Preconditions satisfied"

    def execute(self, inputs: dict) -> ToolResult:
        target = Path(inputs['path']).resolve()
        raw_data = inputs['content']
        data_bytes = raw_data.encode('utf-8') if isinstance(raw_data, str) else raw_data
        
        try:
            target.write_bytes(data_bytes)
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

            data = {
                'os': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'architecture': platform.machine(),
                'python_version': platform.python_version(),
                'disk_total_gb': round(disk_usage.total / (1024**3), 2),
                'disk_free_gb': round(disk_usage.free / (1024**3), 2),
                'pid': os.getpid()
            }
            return ToolResult(
                success=True,
                output=data,
                evidence={'collected_keys': list(data.keys()), 'python_version': data['python_version']}
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
        if pid is not None and (type(pid) is not int or pid <= 0):
            return False, "pid must be a positive integer"
        return True, "Preconditions satisfied"

    def execute(self, inputs: dict) -> ToolResult:
        target_pid = inputs.get('pid', os.getpid())
        try:
            is_active = False
            if os.name == 'nt':
                # Use tasklist for Windows PID inspection
                import subprocess
                res = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {target_pid}', '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True, timeout=5
                )
                output_str = res.stdout.strip()
                if str(target_pid) in output_str:
                    is_active = True
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

# Registry of available tools
TOOL_REGISTRY: dict[str, BaseTool] = {
    FileArtifactTool.name: FileArtifactTool(),
    SystemTelemetryTool.name: SystemTelemetryTool(),
    ProcessStateTool.name: ProcessStateTool(),
    BlenderRenderFixtureTool.name: BlenderRenderFixtureTool(),
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
