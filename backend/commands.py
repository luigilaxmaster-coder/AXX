"""Documentary catalog and a closed, typed bridge to verified local actions.

Imported text is never executable. Only adapters defined here can reach ActionExecutor.
Only an explicitly supplied, reviewed PowerShell script may be evaluated as code.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sqlite3
import sys
import threading
import time
import unicodedata
import uuid

from .actions.desktop import APPS, ENGINES, resolve_desktop, validate_inputs as validate_desktop_inputs
from .procedure_library import ProcedureLibrary

TERMINAL = {'succeeded', 'failed', 'blocked', 'cancelled', 'expired', 'unknown'}


class ApprovalRequired(ValueError):
    pass
ADAPTERS = {
    'axx.file.sha256': {
        'title': 'Calcular SHA256 de un archivo', 'tool': 'file_inspection', 'risk': 'local_file_read',
        'description': 'Lee un archivo local de hasta 512 MiB tras revisar su ruta. Detecta cambios durante la lectura.',
        'aliases': [], 'parameters': {'path': {'type': 'string', 'required': True, 'maxLength': 240}}},
    'axx.file.compare': {
        'title': 'Comparar dos archivos por SHA256', 'tool': 'file_inspection', 'risk': 'local_file_read',
        'description': 'Compara el contenido de dos archivos locales estables, sin modificarlos.',
        'aliases': [], 'parameters': {'path': {'type': 'string', 'required': True, 'maxLength': 240},
                                    'other_path': {'type': 'string', 'required': True, 'maxLength': 240}}},
    'axx.desktop.list_apps': {
        'title': 'Aplicaciones instaladas', 'tool': 'desktop_list_apps', 'risk': 'read',
        'description': 'Consulta los nombres y accesos registrados por Windows.',
        'aliases': ['mis aplicaciones', 'aplicaciones instaladas'], 'parameters': {}},
    'axx.desktop.installed_app': {
        'title': 'Abrir aplicación instalada', 'tool': 'desktop_installed_app', 'risk': 'desktop_open', 'requires_approval': False,
        'description': 'Abre un acceso observado en el inventario de Windows. En el chat puedes decir «abre» y su nombre.',
        'aliases': [], 'parameters': {'app_id': {'type': 'string', 'required': True, 'maxLength': 1024}}},
    'axx.desktop.open_url': {
        'title': 'Abrir página web', 'tool': 'desktop_open_url', 'risk': 'desktop_open', 'requires_approval': False,
        'description': 'Abre una dirección http o https en el navegador predeterminado.',
        'aliases': [], 'parameters': {'url': {'type': 'string', 'required': True, 'maxLength': 2048}}},
    'axx.desktop.open_app': {
        'title': 'Abrir aplicación', 'tool': 'desktop_open_app', 'risk': 'desktop_open', 'requires_approval': False,
        'description': 'Abre calculadora, bloc de notas, Paint o explorador de archivos.',
        'aliases': [], 'parameters': {'app': {'type': 'string', 'required': True, 'enum': list(APPS)}}},
    'axx.desktop.search': {
        'title': 'Buscar en internet', 'tool': 'desktop_search', 'risk': 'desktop_open', 'requires_approval': False,
        'description': 'Abre los resultados en YouTube, Google, Bing o DuckDuckGo.',
        'aliases': [], 'parameters': {'query': {'type': 'string', 'required': True, 'maxLength': 500},
                                    'engine': {'type': 'string', 'required': True, 'enum': list(ENGINES)}}},
    'axx.shell.powershell': {
        'title': 'Ejecutar PowerShell', 'tool': 'desktop_powershell', 'risk': 'system_command',
        'description': 'Ejecuta el script escrito tras aprobarlo. Puede modificar archivos y ajustes. Devuelve salida, errores y código de salida. Límite: 30 segundos.',
        'aliases': [], 'parameters': {'script': {'type': 'string', 'required': True, 'maxLength': 8000}}},
    'axx.system.telemetry': {
        'title': 'Información del sistema', 'tool': 'system_telemetry', 'risk': 'read',
        'description': 'Consulta el sistema y el espacio disponible; verifica la respuesta local.',
        'aliases': ['estado del sistema', 'información del sistema', 'informacion del sistema'], 'parameters': {}},
    'axx.process.inspect': {
        'title': 'Estado de un proceso', 'tool': 'process_state_inspector', 'risk': 'read',
        'description': 'Comprueba un PID local. Sin parámetros consulta el proceso de Axx.',
        'aliases': ['estado de axx'], 'parameters': {'pid': {'type': 'integer', 'required': False, 'minimum': 1, 'maximum': 4294967295}}},
    'axx.artifact.write': {
        'title': 'Crear archivo de texto', 'tool': 'file_artifact_writer', 'risk': 'workspace_write',
        'description': 'Crea un archivo nuevo en artifacts tras confirmar ruta y contenido; verifica SHA256.',
        'aliases': [], 'parameters': {'path': {'type': 'string', 'required': True, 'maxLength': 240},
                                    'content': {'type': 'string', 'required': True, 'maxBytes': 65536}}},
}


# Explicit implementation bindings; imported prose cannot add to this map.
PROCEDURE_BINDINGS = {'AXX-02-0147': 'axx.file.sha256', 'AXX-02-0148': 'axx.file.compare'}


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.lower())
                           if not unicodedata.combining(c)).strip(' .?!¿¡').split())


def catalog_path():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'resources' / 'command-library.json'


def parse_command_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Clave JSON duplicada')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Constante JSON no estándar')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


class CommandService:
    """Persist intent, bind approval to immutable inputs, observe actual executor results."""
    def __init__(self, executor, library_path=None):
        self.executor = executor
        self.learning = None
        self.lock = threading.RLock()
        self.execution_gate = threading.Lock()
        self.closed = False
        self.cancel_events = {}
        self.db = sqlite3.connect(str(executor.db_path), timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS command_runs (
                operation_id TEXT PRIMARY KEY, command_id TEXT NOT NULL, inputs_json TEXT NOT NULL,
                source TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT NOT NULL,
                expires_at REAL NOT NULL, created_at REAL NOT NULL)''')
            # Crash recovery never claims an interrupted effect succeeded or retries it.
            for row in self.db.execute("SELECT * FROM command_runs WHERE state NOT IN ('succeeded','failed','blocked','cancelled','expired','unknown')").fetchall():
                result = json.loads(row['result_json'])
                state = 'unknown' if row['state'] == 'running' else 'expired'
                result.update(state=state, postconditions_passed=False,
                              error={'code': 'INTERRUPTED', 'message': 'Revisa el resultado antes de crear otra operación.'})
                self.db.execute('UPDATE command_runs SET state=?,result_json=? WHERE operation_id=?',
                                (state, json.dumps(result), row['operation_id']))
        self.commands = {}
        for command_id, adapter in ADAPTERS.items():
            self.commands[command_id] = {k: v for k, v in adapter.items() if k != 'tool'} | {
                'id': command_id, 'category': 'Axx local', 'execution_enabled': True,
                'requires_approval': adapter.get('requires_approval', adapter['risk'] != 'read'), 'blocked_reason': None,
                'source_status': 'IMPLEMENTADO_LOCAL', 'validation_level': 'IMPLEMENTADO_LOCAL',
                'source': {'kind': 'local_adapter'}}
        self.commands['axx.blender.fixture'] = {
            'id': 'axx.blender.fixture', 'title': 'Render de prueba en Blender', 'category': 'Axx local',
            'description': 'Adaptador existente pendiente de validación física para el catálogo.',
            'parameters': {}, 'aliases': [], 'execution_enabled': False, 'risk': 'workspace_write',
            'blocked_reason': 'Pendiente de validación física del adaptador',
            'source_status': 'IMPLEMENTADO_LOCAL', 'source': {'kind': 'local_adapter'}}
        self.provenance, self.import_counts, self.library_error = {}, {}, None
        path = Path(library_path) if library_path else catalog_path()
        try:
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('Catálogo demasiado grande')
            payload = parse_command_json(path.read_bytes())
            rows = payload['commands']
            if not isinstance(rows, list) or len(rows) > 20000:
                raise ValueError('Formato de catálogo inválido')
            imported = {}
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError('Entrada documental inválida')
                command_id = row['id']
                if not isinstance(command_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', command_id):
                    raise ValueError('Identificador documental inválido')
                if command_id in self.commands or command_id in imported:
                    raise ValueError('Identificador duplicado en catálogo')
                phrases = row.get('voice_phrases', [])
                if not isinstance(phrases, list) or len(phrases) > 100 or any(
                        not isinstance(phrase, str) or not 1 <= len(phrase) <= 2000 for phrase in phrases):
                    raise ValueError('Frases documentales inválidas')
                # Select documentary fields; ignore any supplied adapter/execution/approval policy.
                item = {k: row[k] for k in ('id', 'title', 'description', 'category', 'catalog_group',
                        'source_member', 'source_status', 'voice_phrases', 'voice_status', 'has_recipe_details') if k in row}
                for key in ('title', 'description', 'category'):
                    item[key] = str(item.get(key, command_id if key == 'title' else ''))[:2000]
                item.update(execution_enabled=False, parameters={}, aliases=[], risk='unreviewed',
                            voice_phrases=phrases,
                            blocked_reason='Sin adaptador ejecutable validado',
                            source_status='DOCUMENTED_NOT_EXECUTED',
                            source={'kind': 'documentary', 'member': row.get('source_member', '')})
                imported[command_id] = item
            self.commands.update(imported)
            self.provenance = payload.get('provenance', {})
            self.import_counts = payload.get('counts', {})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.library_error = f'Biblioteca documental no disponible: {type(exc).__name__}'
        self.procedures = ProcedureLibrary(path.with_name('procedure-library.zip'))
        for key, row in self.procedures.records.items():
            item = self.commands.get(key, {'id': key, 'voice_phrases': [], 'aliases': []})
            item.update({k: row[k] for k in ('title', 'description', 'category', 'source_member')})
            item.update(has_recipe_details=True, execution_enabled=False, parameters={}, risk='unreviewed',
                        blocked_reason='Procedimiento disponible para consulta; falta automatización validada',
                        source_status='DOCUMENTED_NOT_EXECUTED',
                        source={'kind': 'documentary', 'member': row['source_member']})
            self.commands[key] = item
        for key, adapter_id in PROCEDURE_BINDINGS.items():
            if key in self.commands:
                adapter = self.commands[adapter_id]
                self.commands[key].update({name: adapter[name] for name in
                    ('execution_enabled', 'parameters', 'risk', 'requires_approval', 'blocked_reason', 'validation_level')})
                self.commands[key]['adapter_id'] = adapter_id
        self.imported = sum(c['source']['kind'] == 'documentary' for c in self.commands.values())
        self.search_index = {key: normalized(' '.join([c['id'], c['title'], c.get('description', ''),
            c.get('category', ''), ' '.join(c.get('voice_phrases', [])), ' '.join(c.get('aliases', []))]))
            for key, c in self.commands.items()}
        self.documentary_phrases = {}
        for command_id, command in self.commands.items():
            if command['source']['kind'] == 'documentary':
                for phrase in [command['title'], *command.get('voice_phrases', [])]:
                    self.documentary_phrases.setdefault(normalized(phrase), set()).add(command_id)

    def close(self):
        with self.lock:
            for event in self.cancel_events.values():
                event.set()
            if not self.closed:
                self.closed = True
                self.db.close()

    def search(self, query='', limit=30, offset=0):
        if not isinstance(query, str) or len(query) > 500 or type(limit) is not int or type(offset) is not int:
            raise ValueError('Búsqueda o paginación inválida')
        if not 1 <= limit <= 100 or not 0 <= offset <= 20000:
            raise ValueError('Paginación fuera de límites')
        terms = normalized(query).split()
        hits = [c for key, c in self.commands.items() if all(term in self.search_index[key] for term in terms)]
        with self.lock:
            verified = self.db.execute("SELECT COUNT(*) FROM command_runs WHERE state='succeeded'").fetchone()[0]
        enabled = sum(bool(c['execution_enabled']) for c in self.commands.values())
        return {'commands': hits[offset:offset + limit], 'matched': len(hits), 'offset': offset,
                'counts': {'total': len(self.commands), 'imported': self.imported, 'enabled': enabled,
                           'blocked': len(self.commands) - enabled, 'builtins': len(self.commands) - self.imported,
                           'verified_operations': verified, 'source': self.import_counts},
                'provenance': self.provenance, 'library_error': self.library_error,
                'procedure_count': len(self.procedures.records), 'procedure_error': self.procedures.error,
                'artifact_root': str(self.executor.workspace_root)}

    def details(self, command_id):
        if not isinstance(command_id, str) or command_id not in self.commands:
            raise ValueError('Comando desconocido')
        return {'command': self.commands[command_id], 'procedure': self.procedures.get(command_id)}

    def resolve(self, text, source='text', context=None):
        if source not in ('text', 'voice') or not isinstance(text, str) or not 1 <= len(text) <= 70000:
            raise ValueError('Texto u origen de comando inválido')
        explicit = re.fullmatch(r'/comando\s+([A-Za-z0-9_.-]{1,128})(?:\s+(\{.*\}))?\s*', text.strip(), re.S)
        if explicit:
            command_id = explicit[1]
            if command_id not in self.commands:
                return {'match': 'none', 'candidates': [], 'error': {'code': 'NOT_FOUND', 'message': 'Comando desconocido'}}
            inputs = parse_command_json(explicit[2]) if explicit[2] else {}
            return {'match': 'exact', 'command_id': command_id, 'inputs': inputs,
                    'parameters': self.commands[command_id]['parameters'],
                    'execution_enabled': self.commands[command_id]['execution_enabled'],
                    'has_recipe_details': self.commands[command_id].get('has_recipe_details', False)}
        phrase = normalized(text)
        matches = [command_id for command_id, adapter in ADAPTERS.items()
                   if phrase in [normalized(s) for s in adapter['aliases']] or phrase == normalized(command_id)]
        if len(matches) == 1:
            return {'match': 'exact', 'command_id': matches[0], 'inputs': {}, 'parameters': self.commands[matches[0]]['parameters']}
        desktop = resolve_desktop(text, source, context)
        if desktop and desktop.get('match') == 'exact':
            return desktop
        if self.learning:
            learned = self.learning.find(text)
            if learned:
                return {'match': 'learned', 'action_id': learned['id'], 'title': learned['title']}
        # A documented phrase may select its disabled record for inspection, never an adapter.
        if not matches:
            matches = sorted(self.documentary_phrases.get(phrase, []))
            if len(matches) == 1:
                return {'match': 'exact', 'command_id': matches[0], 'inputs': {}, 'execution_enabled': self.commands[matches[0]]['execution_enabled'],
                        'parameters': self.commands[matches[0]]['parameters'],
                        'has_recipe_details': self.commands[matches[0]].get('has_recipe_details', False)}
        if desktop:
            return desktop
        return {'match': 'ambiguous' if matches else 'none', 'candidates': matches}

    def _validate_inputs(self, command_id, inputs, require_new=True, check_files=True):
        if not isinstance(inputs, dict):
            raise ValueError('Los parámetros deben ser un objeto JSON')
        schema = self.commands[command_id]['parameters']
        if set(inputs) - schema.keys():
            raise ValueError('Parámetro desconocido')
        for name, rule in schema.items():
            if name not in inputs:
                if rule.get('required'):
                    raise ValueError(f'Falta el parámetro {name}')
                continue
            value = inputs[name]
            if rule['type'] == 'integer' and (type(value) is not int or not rule['minimum'] <= value <= rule['maximum']):
                raise ValueError(f'{name} debe ser un entero dentro de los límites')
            if rule['type'] == 'string':
                if not isinstance(value, str) or len(value) > rule.get('maxLength', 65536) or len(value.encode('utf-8')) > rule.get('maxBytes', 262144):
                    raise ValueError(f'{name} debe ser texto dentro de los límites')
        inputs = dict(inputs)
        if command_id.startswith('axx.desktop.') or command_id == 'axx.shell.powershell':
            validate_desktop_inputs(ADAPTERS[command_id]['tool'].removeprefix('desktop_'), inputs)
        if command_id == 'axx.process.inspect':
            inputs.setdefault('pid', os.getpid())
        if command_id in ('axx.file.sha256', 'axx.file.compare'):
            from .actions.file_inspection import validate_path
            for value in inputs.values():
                if check_files:
                    validate_path(value)
                else:
                    from .actions.tools import artifact_path_error
                    if not Path(value).is_absolute() or artifact_path_error(value):
                        raise ValueError('Indica la ruta absoluta de un archivo local.')
        if command_id == 'axx.artifact.write':
            raw = inputs['path']
            parts = raw.replace('\\', '/').split('/')
            reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
            if PureWindowsPath(raw).is_absolute() or PureWindowsPath(raw).drive or any(
                    not p or p in ('.', '..') or p.endswith((' ', '.')) or p.split('.')[0].upper() in reserved
                    or re.search(r'[<>:"|?*\x00-\x1f]', p) for p in parts):
                raise ValueError('Usa una ruta relativa nueva sin nombres reservados ni secuencias especiales')
            target = (self.executor.workspace_root / Path(*parts)).resolve()
            if not target.is_relative_to(self.executor.workspace_root) or (require_new and target.exists()):
                raise ValueError('El destino debe ser nuevo y estar dentro de artifacts')
            inputs['path'] = '/'.join(parts)
        return inputs

    def _save(self, result):
        self.db.execute('UPDATE command_runs SET state=?,result_json=? WHERE operation_id=?',
                        (result['state'], json.dumps(result, ensure_ascii=False), result['operation_id']))
        self.db.commit()
        return result

    def get(self, operation_id):
        if not isinstance(operation_id, str):
            raise ValueError('operation_id requerido')
        with self.lock:
            row = self.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?', (operation_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def operations(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute('SELECT result_json FROM command_runs ORDER BY created_at DESC LIMIT 50')]

    def prepare(self, command_id, inputs, source='text', operation_id=None):
        if isinstance(command_id, str):
            command_id = PROCEDURE_BINDINGS.get(command_id, command_id)
        if not isinstance(command_id, str) or command_id not in self.commands or source not in ('text', 'voice'):
            raise ValueError('Comando u origen desconocido')
        if command_id == 'axx.shell.powershell' and source != 'text':
            raise ValueError('Escribe el comando PowerShell y revisa su aprobación; no se ejecutan scripts dictados.')
        op_id = str(uuid.uuid4()) if operation_id is None else operation_id
        if not isinstance(op_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', op_id):
            raise ValueError('operation_id inválido')
        with self.lock:
            if self.closed:
                raise ValueError('Servicio cerrado')
            existing = self.get(op_id)
            # Compare before preconditions: idempotent replay must survive an artifact now existing.
            if existing:
                if existing.get('command_id') == '' and existing['state'] == 'cancelled':
                    return existing | {'replayed': True}
                existing_inputs = existing['inputs']
                candidate = self._validate_inputs(command_id, inputs, require_new=False) if command_id in ADAPTERS else inputs
                if existing['command_id'] != command_id or existing_inputs != candidate or existing['source'] != source:
                    raise ValueError('operation_id ya está vinculado a otros parámetros')
                return existing | {'replayed': True}
            command = self.commands[command_id]
            enabled = command['execution_enabled']
            if enabled:
                inputs = self._validate_inputs(command_id, inputs)
            elif inputs != {}:
                raise ValueError('El comando documental no admite parámetros ejecutables')
            approval = enabled and command.get('requires_approval', False)
            state = ('awaiting_approval' if approval else 'prepared') if enabled else 'blocked'
            result = {'operation_id': op_id, 'command_id': command_id, 'inputs': inputs, 'source': source,
                      'state': state, 'requires_approval': approval, 'postconditions_passed': False,
                      'evidence': {}, 'output': None, 'cancel_requested': False,
                      'error': None if enabled else {'code': 'NOT_IMPLEMENTED', 'message': command['blocked_reason']}}
            now = time.time()
            self.db.execute('INSERT INTO command_runs VALUES (?,?,?,?,?,?,?,?)',
                (op_id, command_id, json.dumps(inputs), source, state, json.dumps(result, ensure_ascii=False), now + 300, now))
            self.db.commit()
            return result

    def execute(self, operation_id, approved=False):
        if not self.execution_gate.acquire(blocking=False):
            raise ValueError('BUSY: hay una operación de catálogo en curso')
        try:
            with self.lock:
                result = self.get(operation_id)
                if not result:
                    raise ValueError('Operación desconocida; prepara el comando primero')
                if result['state'] in TERMINAL:
                    return result | {'replayed': True}
                expiry = self.db.execute('SELECT expires_at FROM command_runs WHERE operation_id=?', (operation_id,)).fetchone()[0]
                if time.time() > expiry:
                    return self._save(result | {'state': 'expired', 'error': {'code': 'EXPIRED', 'message': 'La preparación caducó; revisa y prepara otra vez.'}})
                if result['requires_approval'] and approved is not True:
                    raise ApprovalRequired('Confirma los parámetros en la aplicación')
                # Recheck filesystem and typed preconditions after the user reviewed the request.
                try:
                    self._validate_inputs(result['command_id'], result['inputs'])
                except ValueError as exc:
                    return self._save(result | {'state': 'failed', 'error': {'code': 'PRECONDITION_CHANGED', 'message': str(exc)}})
                result.update(state='running')
                if result['command_id'] in ('axx.shell.powershell', 'axx.file.sha256', 'axx.file.compare'):
                    self.cancel_events[operation_id] = threading.Event()
                self._save(result)
            try:
                action_id = 'cmd-' + hashlib.sha256(operation_id.encode()).hexdigest()
                # A legacy action may hold the executor. Check cancellation again at the dispatch boundary.
                with self.executor.lock:
                    with self.lock:
                        current = self.get(operation_id)
                        if current['cancel_requested']:
                            return self._save(current | {'state': 'cancelled', 'error': {'code': 'CANCELLED', 'message': 'Cancelado antes de ejecutar.'}})
                    args = (ADAPTERS[result['command_id']]['tool'], result['inputs'], action_id)
                    action = self.executor.execute_action(*args, cancel_event=self.cancel_events[operation_id]) if operation_id in self.cancel_events else self.executor.execute_action(*args)
                final = result | {key: action.get(key) for key in ('state', 'postconditions_passed', 'output', 'evidence', 'duration_ms')}
                final.update(action_operation_id=action_id, tool_name=ADAPTERS[result['command_id']]['tool'])
                final.update(model_calls_used=0, model_calls_source='deterministic_no_model_path')
                final['error'] = {'code': 'ACTION_FAILED', 'message': action['error']} if action.get('error') else None
                if final['state'] not in TERMINAL:
                    final.update(state='unknown', postconditions_passed=False)
            except Exception as exc:
                final = result | {'state': 'unknown', 'postconditions_passed': False,
                                  'error': {'code': 'EXECUTION_UNCERTAIN', 'message': f'Inspecciona la operación antes de reintentar ({type(exc).__name__}).'}}
            with self.lock:
                final['cancel_requested'] = self.get(operation_id)['cancel_requested']
                return self._save(final)
        finally:
            with self.lock:
                self.cancel_events.pop(operation_id, None)
            self.execution_gate.release()

    def cancel(self, operation_id=None):
        with self.lock:
            targets = [self.get(operation_id)] if operation_id is not None else [json.loads(row[0]) for row in
                self.db.execute("SELECT result_json FROM command_runs WHERE state NOT IN ('succeeded','failed','blocked','cancelled','expired','unknown')")]
            if operation_id is not None and not targets[0]:
                if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', operation_id):
                    raise ValueError('operation_id inválido')
                # The client reserves its ID before preparing. Cancellation can arrive first.
                result = {'operation_id': operation_id, 'command_id': '', 'inputs': {}, 'source': 'text',
                          'state': 'cancelled', 'cancel_requested': True, 'requires_approval': False,
                          'postconditions_passed': False, 'evidence': {}, 'output': None,
                          'error': {'code': 'CANCELLED', 'message': 'Cancelado antes de preparar.'}}
                now = time.time()
                self.db.execute('INSERT INTO command_runs VALUES (?,?,?,?,?,?,?,?)',
                    (operation_id, '', '{}', 'text', 'cancelled', json.dumps(result), now, now))
                self.db.commit()
                return result
            results = []
            for result in targets:
                if result['state'] not in TERMINAL:
                    result['cancel_requested'] = True
                    if result['operation_id'] in self.cancel_events:
                        self.cancel_events[result['operation_id']].set()
                    if result['state'] != 'running':
                        result.update(state='cancelled', error={'code': 'CANCELLED', 'message': 'Cancelado antes de ejecutar.'})
                    self._save(result)
                results.append(result)
            return results[0] if operation_id is not None else {'operations': results, 'cancelled': any(r['state'] == 'cancelled' for r in results)}
