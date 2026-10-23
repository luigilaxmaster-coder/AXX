"""Explicit, bounded UIA demonstrations; observations never grant execution authority."""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time
import uuid

from .actions.windows_apps import installed_apps
from .actions.windows_automation import list_windows

MAX_SECONDS = 300
MAX_EVENTS = 500
MAX_RECORDS = 50
MAX_BYTES = 512 * 1024
ACTIVE = {'starting', 'recording'}
KINDS = {'invoke', 'selection', 'selection_added', 'selection_removed', 'toggle',
         'expand_collapse', 'enabled', 'offscreen'}
NAMED_TYPES = {'Button', 'CheckBox', 'RadioButton', 'MenuItem'}


def _integer(value, label, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f'{label} inválido')
    return value


def _text(value, limit):
    return ''.join(c for c in value[:limit] if c >= ' ' and c != '\x7f') if isinstance(value, str) else ''


def planning_reference(record):
    """Keep full evidence on disk; give the planner a bounded, labeled sample."""
    reference = record.get('reference')
    if record.get('status') != 'stopped' or not reference or not record.get('event_count'):
        raise ValueError('La demostración no contiene observaciones terminadas.')
    events = reference.get('events', [])
    summary = {key: value for key, value in reference.items() if key != 'events'}
    summary.update(events=[], event_count=record['event_count'], omitted_events=record['event_count'])
    indices = list(range(min(8, len(events)))) + list(range(max(8, len(events)-8), len(events)))
    for index in indices:
        candidate = summary | {'events': summary['events'] + [events[index]]}
        if len(json.dumps(candidate)) > 6000: continue
        summary['events'].append(events[index])
    summary['omitted_events'] = record['event_count'] - len(summary['events'])
    if len(json.dumps(summary)) > 6000: raise ValueError('Resume el objetivo de la demostración.')
    return summary


class DemonstrationService:
    def __init__(self, state_path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(state_path), check_same_thread=False, timeout=10)
        self.process = self.thread = self.timer = None
        self.current = None
        self.closed = False
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS demonstrations (id TEXT PRIMARY KEY, started REAL NOT NULL, payload TEXT NOT NULL)')
            for key, raw in self.db.execute('SELECT id,payload FROM demonstrations').fetchall():
                record = json.loads(raw)
                if record['status'] in ACTIVE:
                    record.update(status='interrupted', reason='backend_restart', stopped_at=time.time())
                    self._save(record)
                    self.current = record

    def _save(self, record):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO demonstrations VALUES (?,?,?)',
                            (record['id'], record['started_at'], json.dumps(record, ensure_ascii=False)))
            self.db.execute('DELETE FROM demonstrations WHERE id NOT IN (SELECT id FROM demonstrations ORDER BY started DESC LIMIT ?)', (MAX_RECORDS,))

    @staticmethod
    def _public(record, full=True):
        result = copy.deepcopy(record)
        result['event_count'] = len(result['events'])
        result['candidate'] = True
        result['verified'] = False
        result['observation_status'] = 'observed' if result['events'] else 'no_observations'
        if full and result['status'] == 'stopped':
            result['reference'] = {'kind': 'uia_demonstration', 'demonstration_id': result['id'],
                                   'objective': result['objective'], 'window': result['window'],
                                   'events': copy.deepcopy(result['events']), 'trust': 'untrusted_observation',
                                   'verified': False, 'execution_authority': False}
        if not full:
            result.pop('events')
        return result

    def start(self, body):
        if not isinstance(body, dict):
            raise ValueError('Demostración inválida')
        window_id = _integer(body.get('window_id'), 'window_id', 0x7FFFFFFFFFFFFFFF)
        pid = _integer(body.get('pid'), 'pid', 0xFFFFFFFF)
        seconds = _integer(body.get('max_seconds', 120), 'max_seconds', MAX_SECONDS)
        count = _integer(body.get('max_events', 200), 'max_events', MAX_EVENTS)
        objective = body.get('objective', '')
        if not isinstance(objective, str) or len(objective) > 2000:
            raise ValueError('Objetivo inválido; máximo 2000 caracteres.')
        with self.lock:
            if self.closed:
                raise ValueError('El observador está cerrado.')
            if self.current and self.current['status'] in ACTIVE:
                raise ValueError('Ya hay una demostración activa.')
            if self.thread and self.thread.is_alive():
                raise ValueError('El observador anterior todavía se está cerrando.')
            window = next((w for w in list_windows() if w['window_id'] == window_id and w['pid'] == pid), None)
            if window is None:
                raise ValueError('Selecciona una ventana visible vigente con su PID.')
            record = {'id': uuid.uuid4().hex, 'status': 'starting', 'window': {
                'window_id': window_id, 'pid': pid, 'title': _text(window.get('title'), 200)},
                'objective': _text(objective, 2000), 'started_at': time.time(), 'stopped_at': None,
                'events': [], 'reason': '', 'max_seconds': seconds, 'max_events': count,
                'provenance': 'windows_uia_scoped_events', 'candidate': True, 'verified': False}
            self.current = record
            self._save(record)
            try:
                process = self._launch({'window_id': window_id, 'pid': pid, 'max_seconds': seconds,
                                        'max_events': count, 'parent_pid': os.getpid()})
            except (OSError, ValueError) as exc:
                record.update(status='failed', reason='observer_unavailable', stopped_at=time.time())
                self._save(record)
                raise ValueError('No se pudo iniciar el observador UI Automation.') from exc
            self.process = process
            # A second deadline also bounds an unresponsive native UIA provider.
            self.timer = threading.Timer(seconds + 10, self._deadline, args=(record['id'], process))
            self.timer.daemon = True
            self.thread = threading.Thread(target=self._read, args=(record, process), daemon=True)
            self.timer.start()
            self.thread.start()
            return self._public(record)

    @staticmethod
    def _launch(request):
        if os.name != 'nt':
            raise ValueError('UI Automation requiere Windows.')
        executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        script = Path(__file__).parent / 'actions/uia_observer.ps1'
        encoded = base64.b64encode(script.read_text(encoding='utf-8-sig').encode('utf-16-le')).decode('ascii')
        process = subprocess.Popen([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-MTA',
                                    '-EncodedCommand', encoded], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            process.stdin.write((json.dumps(request) + '\n').encode('utf-8'))
            process.stdin.flush()
            process.stdin.close()
        except OSError:
            DemonstrationService._terminate(process)
            raise
        return process

    @staticmethod
    def _terminate(process):
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            except OSError:
                pass

    def _deadline(self, key, process):
        with self.lock:
            if self.current and self.current['id'] == key and self.current['status'] in ACTIVE:
                self.current.update(status='stopped', reason='time_limit', stopped_at=time.time())
                self._save(self.current)
        self._terminate(process)

    @staticmethod
    def _event(raw, record):
        if not isinstance(raw, dict) or raw.get('kind') not in KINDS:
            return None
        if raw.get('window_id') != record['window']['window_id'] or raw.get('pid') != record['window']['pid']:
            return None
        selector = raw.get('selector')
        if not isinstance(selector, dict) or selector.get('is_password') is not False:
            return None
        control_type = _text(selector.get('control_type'), 80).removeprefix('ControlType.')
        runtime_id = selector.get('runtime_id')
        if not isinstance(runtime_id, list) or not 1 <= len(runtime_id) <= 32 or any(type(n) is not int for n in runtime_id):
            return None
        event = {'kind': raw['kind'], 'observed_at': time.time(), 'window_id': raw['window_id'], 'pid': raw['pid'],
                 'selector': {'runtime_id': runtime_id, 'automation_id': _text(selector.get('automation_id'), 200),
                              'control_type': control_type,
                              'name': _text(selector.get('name'), 200) if control_type in NAMED_TYPES else ''},
                 'provenance': 'windows_uia_event', 'execution_authority': False}
        # Only finite semantic states are accepted; no text/value property is retained.
        state = raw.get('state')
        if raw['kind'] in {'enabled', 'offscreen'} and type(state) is bool:
            event['state'] = state
        elif raw['kind'] in {'toggle', 'expand_collapse'} and type(state) is int and 0 <= state <= 3:
            event['state'] = state
        return event

    def _read(self, record, process):
        total = 0
        reason = 'observer_exit'
        try:
            while True:
                line = process.stdout.readline(8193)
                if not line:
                    break
                total += len(line)
                if len(line) > 8192 or total > MAX_BYTES:
                    reason = 'output_limit'
                    break
                try:
                    raw = json.loads(line)
                except (ValueError, UnicodeError):
                    reason = 'invalid_observer_output'
                    break
                if not isinstance(raw, dict):
                    reason = 'invalid_observer_output'
                    break
                with self.lock:
                    if record['status'] not in ACTIVE:
                        break
                    if raw.get('type') == 'ready':
                        record['status'] = 'recording'
                    elif raw.get('type') == 'end':
                        reason = raw.get('reason') if raw.get('reason') in {'time_limit', 'event_limit', 'window_lost', 'observer_error', 'parent_exit'} else 'observer_exit'
                        break
                    elif raw.get('type') == 'event':
                        event = self._event(raw, record)
                        if event:
                            record['events'].append(event)
                            if len(record['events']) >= record['max_events']:
                                reason = 'event_limit'
                                break
        except (OSError, ValueError):
            reason = 'observer_error'
        finally:
            self._terminate(process)
            process.stdout.close()
            with self.lock:
                if record['status'] in ACTIVE:
                    status = 'failed' if reason in {'observer_error', 'observer_exit', 'invalid_observer_output'} else 'stopped'
                    record.update(status=status, reason=reason, stopped_at=time.time())
                if self.current is record and self.timer:
                    self.timer.cancel()
                self._save(record)

    def status(self):
        with self.lock:
            return self._public(self.current) if self.current else {'status': 'idle'}

    def get(self, key):
        if not isinstance(key, str) or len(key) != 32:
            raise ValueError('Identificador de demostración inválido')
        with self.lock:
            if self.current and self.current['id'] == key:
                return self._public(self.current)
            row = self.db.execute('SELECT payload FROM demonstrations WHERE id=?', (key,)).fetchone()
            if not row:
                raise ValueError('Demostración desconocida')
            return self._public(json.loads(row[0]))

    def list(self):
        with self.lock:
            rows = self.db.execute('SELECT payload FROM demonstrations ORDER BY started DESC LIMIT ?', (MAX_RECORDS,)).fetchall()
            result = []
            for row in rows:
                record = json.loads(row[0])
                if self.current and self.current['id'] == record['id']:
                    record = self.current
                result.append(self._public(record, full=False))
            return result

    def stop(self, body=None):
        body = {} if body is None else body
        if not isinstance(body, dict) or type(body.get('cancel', False)) is not bool:
            raise ValueError('Solicitud de parada inválida')
        with self.lock:
            record = self.current
            if not record or (body.get('id') is not None and body['id'] != record['id']):
                raise ValueError('No hay una demostración activa con ese identificador.')
            if record['status'] not in ACTIVE and not body.get('cancel'):
                return self._public(record)
            record.update(status='cancelled' if body.get('cancel') else 'stopped',
                          reason='cancelled' if body.get('cancel') else 'user_stop', stopped_at=time.time())
            if body.get('cancel'):
                record['events'] = []
            self._save(record)
            if self.timer:
                self.timer.cancel()
            process, thread = self.process, self.thread
        if process:
            self._terminate(process)
        if thread:
            thread.join(timeout=5)
        return self._public(record)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            active = bool(self.current and self.current['status'] in ACTIVE)
        if active:
            self.stop()
            with self.lock:
                self.current.update(status='interrupted', reason='backend_shutdown')
                self._save(self.current)
        if self.thread:
            self.thread.join(timeout=5)
        with self.lock:
            self.db.close()

    def inventory(self):
        from .commands import ADAPTERS
        errors, apps, windows = [], [], []
        try:
            apps = installed_apps()[:10000]
        except (OSError, ValueError, subprocess.SubprocessError):
            errors.append('installed_apps_unavailable')
        try:
            windows = list_windows()
        except (OSError, ValueError):
            errors.append('windows_unavailable')
        command_ids = sorted(ADAPTERS)
        generic = [key for key in command_ids if key.startswith('axx.desktop.window.')]
        return {'apps': apps, 'windows': windows, 'command_ids': command_ids, 'errors': errors,
                'capabilities': {'generic_window_command_ids': generic, 'control_availability': 'requires_inspection',
                                 'demonstration': 'windows_uia_events' if os.name == 'nt' else 'unavailable',
                                 'app_specific_adapters': [], 'recorded_replay': False,
                                 'verification': 'registered_commands_only'}}
