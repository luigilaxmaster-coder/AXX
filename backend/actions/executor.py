"""Structured Action Executor for Axx.
Enforces:
  1. Tool existence in registry
  2. Precondition verification
  3. Short transaction recording operation_id as 'prepared'
  4. Execution with error capture and Esc cancellation checking
  5. Postcondition verification on real results
  6. Final state recording ('succeeded' | 'failed' | 'unknown')
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
import sqlite3
import time
import threading
import uuid

from .tools import artifact_path_error, get_tool, ToolResult
from .execution_contract import resolve_mode

LOG = logging.getLogger('axx.executor')
PARALLEL_READ_TOOLS = frozenset({'file_inspection', 'system_telemetry', 'process_state_inspector',
                                'desktop_list_apps', 'desktop_list_windows', 'desktop_cli_anything_scan', 'architecture_status'})

class ActionExecutionError(Exception):
    pass

class ActionExecutor:
    """Executes actions with atomic state tracking and result verification."""
    def __init__(self, db_path: str | Path = 'state.db', workspace_root: str | Path | None = None):
        self.db_path = Path(db_path)
        self.workspace_root = Path(workspace_root or self.db_path.resolve().parent).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.input_control = None
        self.dynamic_tools = {}
        self.native_bridge = None
        self.capture_service = None
        self.reads_done = threading.Condition(self.lock)
        self.parallel_reads = 0
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        self._init_schema()
        # A crash leaves the effect unknown; never replay it automatically.
        with self.db:
            self.db.execute("UPDATE operations SET state='unknown' WHERE state IN ('prepared','running')")

    def _init_schema(self):
        with self.db:
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    tool_name TEXT,
                    state TEXT,
                    inputs_json TEXT,
                    result_json TEXT,
                    evidence_json TEXT,
                    duration_ms REAL,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            columns = {row[1] for row in self.db.execute('PRAGMA table_info(operations)')}
            if 'delivery_mode' not in columns:
                self.db.execute('ALTER TABLE operations ADD COLUMN delivery_mode TEXT')

    def close(self):
        with self.lock:
            self.wait_for_reads()
            if hasattr(self, 'db') and self.db:
                try:
                    self.db.close()
                except Exception:
                    pass
                self.db = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def wait_for_reads(self):
        with self.reads_done:
            while self.parallel_reads:
                self.reads_done.wait()

    def invoke_primitive(self, tool, inputs, cancelled):
        if hasattr(tool, 'execute_with_runtime'):
            return tool.execute_with_runtime(inputs, self.workspace_root, cancelled, self)
        if hasattr(tool, 'execute_with_control'):
            return tool.execute_with_control(inputs, self.workspace_root, cancelled, self.input_control)
        return tool.execute_cancellable(inputs, self.workspace_root, cancelled)

    def execute_action(self, tool_name: str, inputs: dict, operation_id: str | None = None, cancel_event=None,
                       *, allow_parallel_read=False, delivery_mode=None) -> dict:
        try:
            mode = resolve_mode(tool_name, delivery_mode)
        except (ValueError, TypeError) as exc:
            raise ActionExecutionError(str(exc)) from exc
        if type(allow_parallel_read) is not bool or (allow_parallel_read and (not isinstance(tool_name, str) or tool_name not in PARALLEL_READ_TOOLS)):
            raise ValueError('Parallel execution requires an explicitly supported read tool')
        with self.lock:
            if not allow_parallel_read:
                self.wait_for_reads()
                return self._execute_action(tool_name, inputs, operation_id, cancel_event, delivery_mode=mode)
            if self.parallel_reads >= 2:
                raise ValueError('BUSY: two independent reads are already running')
            self.parallel_reads += 1
            try:
                return self._execute_action(tool_name, inputs, operation_id, cancel_event, allow_parallel_read=True, delivery_mode=mode)
            finally:
                self.parallel_reads -= 1
                self.reads_done.notify_all()

    def list_operations(self, limit: int = 20) -> list[dict]:
        with self.lock:
            rows = self.db.execute('SELECT operation_id FROM operations ORDER BY created_at DESC LIMIT ?', (max(1, min(limit, 100)),)).fetchall()
            return [self.get_operation(row[0]) for row in rows]

    def get_operation(self, operation_id: str) -> dict | None:
        if not isinstance(operation_id, str):
            return None
        with self.lock:
            row = self.db.execute('SELECT operation_id,tool_name,state,inputs_json,result_json,evidence_json,duration_ms,delivery_mode FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
        if not row:
            return None
        result = json.loads(row[4]) if row[4] else {}
        if isinstance(result, dict) and result.get('operation_id') == operation_id:
            # The durable state wins over a receipt left behind by an interrupted update.
            if result.get('state') != row[2]:
                result.update(state=row[2], postconditions_passed=False, effect_status='unknown', dispatch_status='unknown')
            return dict(result, inputs=json.loads(row[3]), delivery_mode=row[7])
        return {'operation_id': row[0], 'tool_name': row[1], 'state': row[2],
                'inputs': json.loads(row[3]), 'output': result, 'postconditions_passed': False,
                'evidence': json.loads(row[5]) if row[5] else {}, 'duration_ms': row[6], 'delivery_mode': row[7],
                'effect_status': 'unknown', 'dispatch_status': 'unknown'}

    def _execute_action(self, tool_name: str, inputs: dict, operation_id: str | None = None, cancel_event=None,
                        *, allow_parallel_read=False, delivery_mode=None) -> dict:
        """Executes a registered tool with full pre- and post-condition verification."""
        if not isinstance(tool_name, str) or not isinstance(inputs, dict):
            raise ActionExecutionError('tool_name must be a string and inputs an object')
        if operation_id is not None and (not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 128):
            raise ActionExecutionError('Invalid operation_id')
        tool = self.dynamic_tools.get(tool_name) or get_tool(tool_name)
        if not tool:
            raise ActionExecutionError(f"Tool '{tool_name}' not registered in capability catalogue")

        op_id = operation_id or str(uuid.uuid4())
        inputs = dict(inputs)
        permitted = {'file_artifact_writer': {'path', 'content'}, 'system_telemetry': set(), 'process_state_inspector': {'pid'},
                     'blender_render_fixture': {'filename'}, 'desktop_open_url': {'url'}, 'desktop_open_app': {'app'},
                     'desktop_search': {'query', 'engine'}, 'desktop_powershell': {'script'}, 'desktop_cmd': {'script'},
                     'desktop_installed_app': {'app_id'}, 'desktop_list_apps': set(),
                     'desktop_list_windows': set(),
                     'desktop_close_window': {'window_id', 'pid'},
                     'desktop_inspect_window': {'window_id', 'pid'},
                     'desktop_cli_anything_scan': {'window_id', 'pid'},
                     'desktop_read_window': {'window_id', 'pid', 'expected_title'},
                     'desktop_focus_window': {'window_id', 'pid'},
                     'desktop_move_pointer': {'x', 'y'},
                     'desktop_first_video_pointer': {'window_id', 'pid', 'expected_title'},
                     'desktop_spotify_play': set(),
                     'desktop_set_window_value': {'window_id', 'pid', 'control_id', 'value', 'expected_title'},
                     'desktop_invoke_window_button': {'window_id', 'pid', 'control_id', 'expected_title', 'expected_name'},
                     'desktop_notepad_text': {'window_title', 'value'}, 'desktop_explorer_folder': {'path'},
                     'file_inspection': {'path', 'other_path'}, 'architecture_status': set(),
                     'desktop_find_control': {'window_id', 'pid', 'name'}}
        from .computer_tools import ADAPTERS as COMPUTER_ADAPTERS
        permitted.update({adapter['tool']: set(adapter['parameters']) for adapter in COMPUTER_ADAPTERS.values()})
        from .application_tools import ADAPTERS as APPLICATION_ADAPTERS
        permitted.update({adapter['tool']: set(adapter['parameters']) for adapter in APPLICATION_ADAPTERS.values()})
        from ..computer_use import ADAPTERS as COMPUTER_USE_ADAPTERS
        permitted.update({adapter['tool']: set(adapter['parameters']) for adapter in COMPUTER_USE_ADAPTERS.values()})
        if tool_name in self.dynamic_tools:
            permitted[tool_name] = tool.parameter_names
        if tool_name not in self.dynamic_tools and set(inputs) - permitted.get(tool_name, set()):
            raise ActionExecutionError('Unexpected action inputs')
        if tool_name == 'file_artifact_writer' and isinstance(inputs.get('path'), str):
            candidate = Path(inputs['path'])
            candidate = (self.workspace_root / candidate) if not candidate.is_absolute() else candidate
            path_error = artifact_path_error(str(candidate))
            if path_error:
                return {'operation_id': op_id, 'tool_name': tool_name, 'state': 'failed',
                        'preconditions_passed': False, 'postconditions_passed': False,
                        'error': path_error, 'duration_ms': 0, 'evidence': {}}
            candidate = candidate.resolve()
            if not candidate.is_relative_to(self.workspace_root):
                return {'operation_id': op_id, 'tool_name': tool_name, 'state': 'failed',
                        'preconditions_passed': False, 'postconditions_passed': False,
                        'error': 'Target path is outside the authorized workspace or in a restricted system directory',
                        'duration_ms': 0, 'evidence': {}}
            inputs['path'] = str(candidate)
            if not isinstance(inputs.get('content'), str) or len(inputs['content'].encode('utf-8')) > 1024 * 1024:
                raise ActionExecutionError('File content must be UTF-8 text within 1 MiB')
        existing = self.get_operation(op_id)
        if existing:
            if existing['tool_name'] != tool_name or existing['inputs'] != inputs:
                raise ActionExecutionError('operation_id already belongs to different inputs')
            if existing.get('delivery_mode') not in (None, delivery_mode):
                raise ActionExecutionError('operation_id already belongs to a different delivery mode')
            return dict(existing, replayed=True)
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

        # 1. Verify Preconditions
        pre_ok, pre_msg = tool.verify_preconditions(inputs)
        if not pre_ok:
            return {
                'operation_id': op_id,
                'tool_name': tool_name,
                'state': 'failed',
                'preconditions_passed': False,
                'postconditions_passed': False,
                'error': f"Precondition failed: {pre_msg}",
                'duration_ms': 0.0,
                'evidence': {}
            }

        # 2. Record operation state 'prepared'
        with self.db:
            self.db.execute(
                '''INSERT INTO operations(operation_id, tool_name, state, inputs_json, created_at, updated_at,delivery_mode)
                   VALUES(?, ?, 'prepared', ?, ?, ?, ?)''',
                (op_id, tool_name, json.dumps(inputs), now_iso, now_iso, delivery_mode)
            )

        # 3. Transition to 'running'
        start_time = time.monotonic()
        with self.db:
            self.db.execute(
                '''UPDATE operations SET state='running', updated_at=? WHERE operation_id=?''',
                (dt.datetime.now(dt.timezone.utc).isoformat(), op_id)
            )

        # 4. Execute tool
        try:
            if cancel_event is not None and cancel_event.is_set():
                result = {'operation_id': op_id, 'tool_name': tool_name, 'state': 'cancelled',
                          'preconditions_passed': True, 'postconditions_passed': False,
                          'dispatch_status': 'not_attempted', 'effect_status': 'not_observed',
                          'delivery_mode': delivery_mode, 'error': 'Cancelado antes del despacho.',
                          'evidence': {'cancelled': True}, 'duration_ms': 0}
                with self.db:
                    self.db.execute("UPDATE operations SET state='cancelled',result_json=? WHERE operation_id=?", (json.dumps(result), op_id))
                return result
            # Only the allowlisted read body may overlap; all ledger access stays serialized.
            if allow_parallel_read:
                self.lock.release()
            try:
                if self.native_bridge is not None and tool_name in self.native_bridge.tools:
                    cancelled = cancel_event or threading.Event()
                    tool_res = self.native_bridge.execute(tool_name,
                        lambda: self.invoke_primitive(tool, inputs, cancelled), cancelled, op_id)
                elif hasattr(tool, 'execute_admitted'):
                    tool_res = tool.execute_admitted(inputs, self.workspace_root, cancel_event or threading.Event(), self, op_id)
                else:
                    tool_res = self.invoke_primitive(tool, inputs, cancel_event or threading.Event())
            finally:
                if allow_parallel_read:
                    self.lock.acquire()
        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            result = {
                'operation_id': op_id, 'tool_name': tool_name, 'state': 'unknown',
                'preconditions_passed': True, 'postconditions_passed': False,
                'error': f'Tool execution interrupted; inspect the possible effect before retrying: {exc}',
                'duration_ms': round(duration_ms, 2), 'evidence': {}
            }
            result.update(delivery_mode=delivery_mode, dispatch_status='unknown', effect_status='unknown')
            with self.db:
                self.db.execute(
                    '''UPDATE operations SET state='unknown', result_json=?, duration_ms=?, updated_at=?
                       WHERE operation_id=?''',
                    (json.dumps(result), duration_ms, dt.datetime.now(dt.timezone.utc).isoformat(), op_id)
                )
            return result

        # 5. Verify Postconditions
        verification_unknown = False
        try:
            post_ok, post_msg = tool.verify_postconditions(inputs, tool_res)
        except Exception as exc:
            post_ok = False
            post_msg = f'Cannot verify the possible effect; inspect it before retrying: {exc}'
            verification_unknown = True
        duration_ms = (time.monotonic() - start_time) * 1000.0
        acknowledged_only = tool_res.evidence.get('verification') == 'uia_invoke_acknowledged'
        if acknowledged_only:
            post_ok = False
            tool_res.evidence.update(reconciliation_required=True, effect_uncertain=True)
            post_msg = 'La pulsación fue entregada; el resultado de la aplicación necesita verificación. No se repetirá automáticamente.'
        final_state = ('unknown' if verification_unknown or tool_res.evidence.get('effect_uncertain') else
                       'cancelled' if tool_res.evidence.get('cancelled') is True else
                       'succeeded' if (tool_res.success and post_ok) else 'failed')
        err_msg = None if final_state == 'succeeded' else (tool_res.error or post_msg)

        result = {
            'operation_id': op_id,
            'tool_name': tool_name,
            'state': final_state,
            'preconditions_passed': True,
            'postconditions_passed': post_ok,
            'output': tool_res.output,
            'error': err_msg,
            'duration_ms': round(duration_ms, 2),
            'evidence': tool_res.evidence,
            'delivery_mode': delivery_mode,
            'dispatch_status': ('delivered' if tool_res.success or acknowledged_only or tool_res.evidence.get('dispatch_status') == 'delivered' or tool_res.evidence.get('verification') == 'process_exit'
                                else 'unknown' if final_state == 'unknown' else 'rejected'),
            'effect_status': 'confirmed' if final_state == 'succeeded' else 'partial' if tool_res.evidence.get('partial_effect') else 'unknown' if final_state == 'unknown' else 'not_observed',
        }
        # State and complete receipt must commit together, including across a power loss.
        with self.db:
            self.db.execute('''UPDATE operations SET state=?,result_json=?,evidence_json=?,duration_ms=?,updated_at=?
                               WHERE operation_id=?''',
                            (final_state, json.dumps(result), json.dumps(tool_res.evidence or {}), duration_ms,
                             dt.datetime.now(dt.timezone.utc).isoformat(), op_id))
        return result
