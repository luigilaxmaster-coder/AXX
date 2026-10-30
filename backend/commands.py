"""Documentary catalog and a closed, typed bridge to verified local actions.

Imported text is never executable. Only adapters defined here can reach ActionExecutor.
Only an explicitly supplied, reviewed PowerShell script may be evaluated as code.
"""
from __future__ import annotations

import hashlib
import hmac
from contextlib import ExitStack, contextmanager, nullcontext
import json
import math
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
from .actions.command_language import command_text, command_sequence, voice_suggestion
from .actions.executor import ActionExecutionError
from .actions.execution_contract import delivery_policy, resolve_mode
from .actions.computer_tools import ADAPTERS as COMPUTER_ADAPTERS
from .actions.application_tools import ADAPTERS as APPLICATION_ADAPTERS, resolve_application_command
from .computer_use import ADAPTERS as COMPUTER_USE_ADAPTERS
from .actions import artifact_compensation as compensation
from .procedure_library import ProcedureLibrary
from .memory import task_memory

TERMINAL = {'succeeded', 'failed', 'blocked', 'cancelled', 'expired', 'unknown'}


class ApprovalRequired(ValueError):
    pass
ADAPTERS = {
    **{'axx.artifact.' + action: {'title': 'Apartar archivo nuevo en cuarentena' if action == 'quarantine' else 'Restaurar archivo desde cuarentena',
        'tool': 'artifact_' + action, 'risk': 'workspace_write', 'requires_approval': True, 'aliases': [],
        'description': 'Compensa una creación nueva verificada mediante su recibo e identidad; conserva los bytes y nunca sobrescribe originales.',
        'parameters': compensation.PARAMETERS} for action in ('quarantine', 'restore')},
    'axx.desktop.window.find': {
        'title': 'Localizar botón por nombre', 'tool': 'desktop_find_control', 'risk': 'read',
        'description': 'Observa UIA y selecciona un botón único por nombre exacto. Se abstiene si falta, hay duplicados o el árbol está incompleto. No pulsa ni toma el foco.',
        'aliases': [], 'parameters': {
            'window_id': {'type':'string', 'required':True, 'maxLength':18},
            'pid': {'type':'integer', 'required':True, 'minimum':1, 'maximum':4294967295},
            'name': {'type':'string', 'required':True, 'maxLength':200}}},
    'axx.architecture.status': {
        'title': 'Estado de la arquitectura unificada', 'tool': 'architecture_status', 'risk': 'read',
        'description': 'Comprueba los componentes locales y muestra qué integraciones todavía no tienen un adaptador registrado. No ejecuta modelos ni instala dependencias.',
        'aliases': ['estado de la arquitectura', 'estado de integraciones', 'diagnóstico de arquitectura'], 'parameters': {}},
    'axx.desktop.notepad.text': {
        'title': 'Escribir texto en un documento de Notepad', 'tool': 'desktop_notepad_text', 'risk': 'workspace_write',
        'description': 'Resuelve una ventana de Notepad por su título exacto observado y su editor actual, reemplaza el texto con aprobación y verifica SHA256. No guarda el archivo ni cierra pestañas.',
        'aliases': [], 'parameters': {'window_title': {'type': 'string', 'required': True, 'maxLength': 2048},
            'value': {'type': 'string', 'required': True, 'maxLength': 8192, 'maxBytes': 32768}}},
    'axx.desktop.explorer.folder': {
        'title': 'Abrir y enfocar carpeta en Explorador', 'tool': 'desktop_explorer_folder', 'risk': 'local_state', 'requires_approval': False,
        'description': 'Abre una carpeta local, resuelve su ventana mediante Shell y verifica ruta y foco. Reutilizable sin coordenadas guardadas.',
        'aliases': [], 'parameters': {'path': {'type': 'string', 'required': True, 'maxLength': 240}}},
    'axx.file.sha256': {
        'title': 'Calcular SHA256 de un archivo', 'tool': 'file_inspection', 'risk': 'local_file_read',
        'description': 'Lee un archivo local de hasta 512 MiB tras revisar su ruta. Detecta cambios durante la lectura.',
        'aliases': [], 'parameters': {'path': {'type': 'string', 'required': True, 'maxLength': 240,
            'description': 'Ruta absoluta del archivo local. Si un paso anterior lo crea, enlaza su output.path mediante bindings.'}}},
    'axx.file.compare': {
        'title': 'Comparar dos archivos por SHA256', 'tool': 'file_inspection', 'risk': 'local_file_read',
        'description': 'Compara el contenido de dos archivos locales estables, sin modificarlos.',
        'aliases': [], 'parameters': {'path': {'type': 'string', 'required': True, 'maxLength': 240,
                                            'description': 'Ruta absoluta del primer archivo local.'},
                                    'other_path': {'type': 'string', 'required': True, 'maxLength': 240,
                                                  'description': 'Ruta absoluta del segundo archivo local.'}}},
    'axx.desktop.list_apps': {
        'title': 'Aplicaciones instaladas', 'tool': 'desktop_list_apps', 'risk': 'read',
        'description': 'Consulta los nombres y accesos registrados por Windows.',
        'aliases': ['mis aplicaciones', 'aplicaciones instaladas'], 'parameters': {}},
    'axx.desktop.list_windows': {
        'title': 'Ventanas visibles', 'tool': 'desktop_list_windows', 'risk': 'read',
        'description': 'Consulta ventanas superiores visibles con título, proceso e indicador de foco; no lee el contenido de sus controles.',
        'aliases': ['mis ventanas', 'ventanas abiertas', 'lista ventanas', 'lista mis ventanas', 'muestra mis ventanas'], 'parameters': {}},
    'axx.desktop.window.close': {
        'title': 'Cerrar ventana', 'tool': 'desktop_close_window', 'risk': 'local_state', 'requires_approval': False,
        'description': 'Solicita cerrar una ventana visible observada por HWND y PID; respeta avisos de cambios sin guardar y verifica que desaparezca.',
        'aliases': [], 'parameters': {
            'window_id': {'type': 'string', 'required': True, 'maxLength': 18},
            'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295},
            'expected_title': {'type': 'string', 'required': False, 'maxLength': 2048},
            'expected_process_started': {'type': 'string', 'required': False, 'maxLength': 80}}},
    'axx.desktop.window.inspect': {
        'title': 'Observar controles de ventana', 'tool': 'desktop_inspect_window', 'risk': 'read',
        'description': 'Observa el árbol limitado de controles UI Automation de una ventana identificada por HWND y PID observados.',
        'aliases': [], 'parameters': {
            'window_id': {'type': 'string', 'required': True, 'maxLength': 18},
            'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295}}},
    'axx.desktop.window.read': {
        'title': 'Leer contenido de una ventana', 'tool': 'desktop_read_window', 'risk': 'local_content_read',
        'description': 'Lee texto y enlaces que una ventana expone a accesibilidad, tras aprobar. Excluye controles de contraseña. No equivale a acceso al DOM ni garantiza que la aplicación exponga todo el contenido.',
        'aliases': [], 'parameters': {
            'expected_title': {'type': 'string', 'required': True, 'maxLength': 2048},
            'window_id': {'type': 'string', 'required': True, 'maxLength': 18},
            'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295}}},
    'axx.desktop.window.focus': {
        'title': 'Enfocar ventana observada', 'tool': 'desktop_focus_window', 'risk': 'local_state', 'requires_approval': False,
        'description': 'Solicita el foco para una ventana observada y verifica el foreground real de Windows.',
        'aliases': [], 'parameters': {
            'window_id': {'type': 'string', 'required': True, 'maxLength': 18},
            'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295}}},
    'axx.desktop.pointer.move': {
        'title': 'Mover mouse a coordenadas de pantalla', 'tool': 'desktop_move_pointer', 'risk': 'local_state', 'requires_approval': False,
        'description': 'Mueve el cursor a un punto físico explícito de una pantalla activa, sin hacer clic; comprueba la posición final.',
        'aliases': [], 'parameters': {'x': {'type': 'integer', 'required': True, 'minimum': -32768, 'maximum': 32767},
                                    'y': {'type': 'integer', 'required': True, 'minimum': -32768, 'maximum': 32767}}},
    'axx.desktop.pointer.first_video': {
        'title': 'Poner mouse sobre el primer video de YouTube', 'tool': 'desktop_first_video_pointer', 'risk': 'local_state', 'requires_approval': False,
        'description': 'Observa el primer video visible en una ventana única de YouTube en Chrome, la enfoca y mueve el cursor sin hacer clic.',
        'aliases': [], 'parameters': {'window_id': {'type': 'string', 'required': True, 'maxLength': 18},
                                     'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295},
                                     'expected_title': {'type': 'string', 'required': True, 'maxLength': 2048}}},
    'axx.desktop.spotify.play': {
        'title': 'Reproducir Spotify abierto', 'tool': 'desktop_spotify_play', 'risk': 'local_state', 'requires_approval': False,
        'description': 'Enfoca la ventana única de Spotify y activa su botón de reproducción observado; comprueba que cambia a Pausar.',
        'aliases': [], 'parameters': {}},
    'axx.desktop.window.set_value': {
        'title': 'Escribir en un control observado', 'tool': 'desktop_set_window_value', 'risk': 'workspace_write',
        'description': 'Escribe texto exacto en un control único con ValuePattern, ligado a HWND, PID y AutomationId observados. Requiere aprobación por operación.',
        'aliases': [], 'parameters': {
            'window_id': {'type': 'string', 'required': True, 'maxLength': 18},
            'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295},
            'control_id': {'type': 'string', 'required': True, 'maxLength': 64},
            'value': {'type': 'string', 'required': True, 'maxLength': 8192, 'maxBytes': 32768},
            'expected_title': {'type': 'string', 'required': False, 'maxLength': 2048}}},
    'axx.desktop.window.invoke': {
        'title': 'Pulsar botón observado', 'tool': 'desktop_invoke_window_button', 'risk': 'local_state', 'requires_approval': True,
        'description': 'Pulsa un botón UI Automation observado en una ventana identificada. Comprueba la entrega de la pulsación, no el resultado dentro de la aplicación.',
        'aliases': [], 'parameters': {
            'window_id': {'type': 'string', 'required': True, 'maxLength': 18},
            'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295},
            'control_id': {'type': 'string', 'required': True, 'maxLength': 64},
            'expected_title': {'type': 'string', 'required': True, 'maxLength': 2048},
            'expected_name': {'type': 'string', 'required': True, 'maxLength': 2048}}},
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
    'axx.shell.cmd': {
        'title': 'Ejecutar CMD', 'tool': 'desktop_cmd', 'risk': 'system_command',
        'description': 'Ejecuta el comando CMD escrito y aprobado en la PC. Devuelve salida, errores y código de salida. Límite: 30 segundos.',
        'aliases': [], 'parameters': {'script': {'type': 'string', 'required': True, 'maxLength': 8000}}},
    'axx.system.telemetry': {
        'title': 'Información del sistema', 'tool': 'system_telemetry', 'risk': 'read',
        'description': 'Consulta el sistema y el espacio disponible; verifica la respuesta local.',
        'aliases': ['estado del sistema', 'información del sistema', 'informacion del sistema', 'consulta el estado del sistema'], 'parameters': {}},
    'axx.process.inspect': {
        'title': 'Estado de un proceso', 'tool': 'process_state_inspector', 'risk': 'read',
        'description': 'Comprueba un PID local. Sin parámetros consulta el proceso de Axx.',
        'aliases': ['estado de axx'], 'parameters': {'pid': {'type': 'integer', 'required': False, 'minimum': 1, 'maximum': 4294967295}}},
    'axx.desktop.cli_anything.scan': {
        'title': 'Descubrir capacidades UIA', 'tool': 'desktop_cli_anything_scan', 'risk': 'read',
        'description': 'Observa metadatos y patrones de controles expuestos por UI Automation. Solo ofrece acciones del registro; descubrir un patrón no valida su ejecución.',
        'aliases': [], 'parameters': {
            'window_id': {'type': 'string', 'required': True, 'maxLength': 18},
            'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295}}},
    'axx.artifact.write': {
        'title': 'Crear archivo de texto', 'tool': 'file_artifact_writer', 'risk': 'workspace_write',
        'description': 'Crea un archivo nuevo en artifacts tras confirmar ruta y contenido; verifica SHA256.',
        'aliases': [], 'parameters': {'path': {'type': 'string', 'required': True, 'maxLength': 240,
                                             'description': 'Ruta relativa nueva dentro de artifacts, por ejemplo prueba.txt; no una ruta absoluta.'},
                                    'content': {'type': 'string', 'required': True, 'maxBytes': 65536}}},
}


# Explicit implementation bindings; imported prose cannot add to this map.
ADAPTERS.update(COMPUTER_ADAPTERS)
ADAPTERS.update(APPLICATION_ADAPTERS)
ADAPTERS.update(COMPUTER_USE_ADAPTERS)
PROCEDURE_BINDINGS = {'AXX-02-0147': 'axx.file.sha256', 'AXX-02-0148': 'axx.file.compare'}
PARALLEL_READ_COMMANDS = frozenset({'axx.file.sha256', 'axx.file.compare', 'axx.system.telemetry',
                                   'axx.process.inspect', 'axx.desktop.list_apps', 'axx.desktop.list_windows', 'axx.desktop.cli_anything.scan', 'axx.architecture.status'})
# Recovery is independent of concurrency: serial UIA observations also have no
# write effect to reconcile after interruption. This does not authorize overlap.
READ_ONLY_COMMANDS = PARALLEL_READ_COMMANDS | frozenset({'axx.desktop.window.inspect', 'axx.desktop.window.read', 'axx.desktop.window.find',
    'axx.desktop.window.select',
    'axx.desktop.observe', 'axx.desktop.control.find', 'axx.desktop.grid.read', 'axx.desktop.window.observe', 'axx.file.find', 'axx.browser.tabs', 'axx.browser.inspect'})


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
        self.adapters = dict(ADAPTERS)
        self.learning = None
        self.dispatch_guard = None
        self.mission_guard = None
        self.change_revision = 0
        self.lock = threading.RLock()
        self.execution_gate = threading.Lock()
        self.parallel_operations = set()
        self.closed = False
        self.cancel_events = {}
        self.db = sqlite3.connect(str(executor.db_path), timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            task_memory.ensure(self.db)
            compensation.initialize(self.db)
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
        for command_id, adapter in self.adapters.items():
            self.commands[command_id] = {k: v for k, v in adapter.items() if k != 'tool'} | {
                'id': command_id, 'category': 'Axx local', 'execution_enabled': True,
                'requires_approval': adapter.get('requires_approval', adapter['risk'] != 'read'), 'blocked_reason': None,
                'source_status': 'IMPLEMENTADO_LOCAL', 'validation_level': 'IMPLEMENTADO_LOCAL',
                'source': {'kind': 'local_adapter'}, 'delivery': delivery_policy(adapter['tool'])}
            if command_id in compensation.COMMAND_ACTIONS and not compensation.native_available():
                self.commands[command_id].update(execution_enabled=False, blocked_reason='Compensación nativa por identidad no disponible en esta plataforma')
            if command_id == 'axx.artifact.write' and not compensation.native_available():
                self.commands[command_id].update(execution_enabled=False, blocked_reason='La creación requiere una raíz protegida por handles Windows; no hay fallback inseguro por ruta')
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

    def refresh_mcp_catalog(self, host, records):
        from .mcp_host.tool_adapter import McpTool
        with self.lock:
            commands, adapters = dict(self.commands), dict(self.adapters)
            tools = dict(self.executor.dynamic_tools)
            for key, item in commands.items():
                if key.startswith('axx.mcp.'):
                    commands[key] = item | {'execution_enabled': False, 'blocked_reason': 'Conexión desactivada o catálogo actualizado'}
            for record in records:
                key = record['id']
                parameters = {name: dict(spec, required=name in record['input_schema'].get('required', []))
                              for name, spec in record['input_schema'].get('properties', {}).items()}
                adapter = {'title': record['title'], 'description': record['description'], 'parameters': parameters,
                           'aliases': [], 'risk': 'external_content' if record['read_only'] else 'local_state',
                           'requires_approval': True, 'tool': key}
                adapters[key] = adapter
                tools[key] = McpTool(host, record)
                commands[key] = {**adapter, 'id': key, 'category': 'Conexiones MCP', 'execution_enabled': record['enabled'],
                    'blocked_reason': None if record['enabled'] else 'Activa y revisa esta herramienta en Conexiones MCP',
                    'source_status': 'DESCUBIERTO_MCP', 'validation_level': 'SCHEMA_CHECKED',
                    'source': {'kind': 'mcp', 'connection_id': record['connection_id']},
                    'input_schema': record['input_schema'], 'schema_digest': record['schema_digest'],
                    'delivery': delivery_policy(key)}
            index = {key: normalized(' '.join([item['id'], item['title'], item.get('description', ''),
                     *item.get('aliases', []), *item.get('voice_phrases', [])])) for key, item in commands.items()}
            self.executor.dynamic_tools = tools
            self.adapters, self.commands, self.search_index = adapters, commands, index

    def close(self):
        with self.lock:
            for event in self.cancel_events.values():
                event.set()
            if not self.closed:
                self.closed = True
                self.db.close()

    def refresh_generated_catalog(self, records):
        from .generated_commands import GeneratedTool
        with self.lock:
            commands, adapters = dict(self.commands), dict(self.adapters)
            tools = {key: value for key, value in self.executor.dynamic_tools.items()
                     if not key.startswith('axx.generated.')}
            for key, item in commands.items():
                if key.startswith('axx.generated.'):
                    commands[key] = item | {'execution_enabled': False, 'blocked_reason': 'Versión revocada o sustituida'}
            for record in records:
                tool = GeneratedTool(record)
                key = tool.name
                previous = self.executor.dynamic_tools.get(key)
                if isinstance(previous, GeneratedTool) and previous.record == record:
                    tool = previous
                parameters = {name: dict(spec, required=name in record['input_schema'].get('required', []))
                              for name, spec in record['input_schema']['properties'].items()}
                adapter = {'title': record['title'], 'description': record['description'], 'parameters': parameters,
                           'aliases': [], 'risk': 'read', 'requires_approval': False, 'tool': key}
                adapters[key] = adapter
                tools[key] = tool
                commands[key] = {**adapter, 'id': key, 'category': 'Código aprobado', 'execution_enabled': True,
                    'blocked_reason': None, 'source_status': 'CODIGO_REVISADO', 'validation_level': 'SELF_TESTED',
                    'source': {'kind': 'generated', 'capability_id': record['capability_id'],
                               'revision': record['revision'], 'digest': record['digest']},
                    'input_schema': record['input_schema'], 'output_schema': record['output_schema'],
                    'delivery': delivery_policy(key)}
            index = {key: normalized(' '.join([item['id'], item['title'], item.get('description', ''),
                     *item.get('aliases', []), *item.get('voice_phrases', [])])) for key, item in commands.items()}
            self.executor.dynamic_tools = tools
            self.adapters, self.commands, self.search_index = adapters, commands, index

    def executable_catalog(self):
        with self.lock:
            return {'commands': [{name: item[name] for name in ('id', 'title', 'description', 'risk', 'parameters')} |
                    {'pc_approval_required': item.get('requires_approval', False) or item['risk'] not in ('read', 'desktop_open'),
                     'requires_approval': item.get('requires_approval', True), 'source_kind': item.get('source', {}).get('kind'),
                     'execution_enabled': True}
                    for item in self.commands.values() if item['execution_enabled'] and item['id'] in self.adapters]}

    def search(self, query='', limit=30, offset=0):
        if not isinstance(query, str) or len(query) > 500 or type(limit) is not int or type(offset) is not int:
            raise ValueError('Búsqueda o paginación inválida')
        if not 1 <= limit <= 100 or not 0 <= offset <= 20000:
            raise ValueError('Paginación fuera de límites')
        terms = normalized(query).split()
        with self.lock:
            hits = [c for key, c in self.commands.items() if all(term in self.search_index[key] for term in terms)]
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

    def resolve(self, text, source='text', context=None, project_id=''):
        if not isinstance(project_id, str) or len(project_id) > 128:
            raise ValueError('Proyecto inválido')
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
        canonical = command_text(text, source)
        parts=command_sequence(text,source)
        if parts:
            if len(parts)>8 or any(not part.strip() for part in parts):
                return {'match':'needs_input','message':'Indica entre dos y ocho pasos completos. No se ejecutó ninguno.'}
            from .action_learning import ALLOWED
            from urllib.parse import urlsplit, parse_qs
            steps=[];sequence_context=dict(context or {})
            for index,part in enumerate(parts):
                resolved=self.resolve(part,source,sequence_context,project_id)
                command_id=resolved.get('command_id');inputs=resolved.get('inputs') or {}
                if (resolved.get('match')!='exact' or command_id not in ALLOWED
                        or self.commands[command_id].get('execution_enabled') is not True
                        or any(rule.get('required') and key not in inputs for key,rule in self.commands[command_id]['parameters'].items())):
                    return {'match':'sequence_request','message':f'El paso {index+1} necesita planificación. No se ejecutó ningún paso.'}
                steps.append({'command_id':command_id,'inputs':inputs})
                if command_id=='axx.desktop.search':sequence_context.update(inputs)
                if command_id in ('axx.desktop.open_url','axx.app.browse'):
                    url=urlsplit(inputs['url']);engine={'youtube.com':'youtube','google.com':'google','bing.com':'bing','duckduckgo.com':'duckduckgo'}.get(url.hostname.removeprefix('www.'))
                    if engine:sequence_context.update(engine=engine,url=inputs['url'])
                    query=parse_qs(url.query).get('search_query' if engine=='youtube' else 'q')
                    if query:sequence_context['query']=query[0]
                    if command_id=='axx.app.browse':sequence_context['application']=inputs['application']
            return {'match':'sequence','steps':steps,'requires_approval':True}
        def understood(result):
            if normalized(canonical) != normalized(text):
                result['understanding'] = {'method':'bounded_grammar', 'canonical':canonical,
                                           'asr_correction_allowed':source == 'voice'}
            return result
        phrase = normalized(canonical)
        generated = re.fullmatch(r'(?:ejecuta|ejecutar|usa|usar) (?:el )?comando (.+)', phrase)
        if generated:
            candidates = [key for key, item in self.commands.items() if key.startswith('axx.generated.')
                          and item['execution_enabled'] and normalized(item['title']) == generated[1]]
            if len(candidates) == 1:
                key = candidates[0]
                return {'match': 'exact', 'command_id': key, 'inputs': {}, 'parameters': self.commands[key]['parameters']}
            return {'match': 'ambiguous' if candidates else 'none', 'candidates': candidates}
        matches = [command_id for command_id, adapter in self.adapters.items()
                   if phrase in [normalized(s) for s in adapter['aliases']] or phrase == normalized(command_id)]
        if len(matches) == 1:
            return understood({'match': 'exact', 'command_id': matches[0], 'inputs': {}, 'parameters': self.commands[matches[0]]['parameters']})
        desktop = resolve_desktop(text, source, context)
        if desktop and desktop.get('match') == 'exact':
            return understood(desktop)
        application = resolve_application_command(canonical)
        if application:
            application['parameters'] = self.commands[application['command_id']]['parameters']
            return understood(application)
        if self.learning:
            learned = self.learning.find(text, project_id)
            if learned:
                return {'match': 'learned', 'action_id': learned['id'], 'title': learned['title']}
            if self.learning.recognizes(text, project_id):
                return {'match': 'learned', 'action_id': None, 'title': text}
        # A documented phrase may select its disabled record for inspection, never an adapter.
        if not matches:
            matches = sorted(self.documentary_phrases.get(phrase, []))
            if len(matches) == 1:
                return {'match': 'exact', 'command_id': matches[0], 'inputs': {}, 'execution_enabled': self.commands[matches[0]]['execution_enabled'],
                        'parameters': self.commands[matches[0]]['parameters'],
                        'has_recipe_details': self.commands[matches[0]].get('has_recipe_details', False)}
        if desktop:
            return understood(desktop)
        if source == 'voice' and (suggestion := voice_suggestion(canonical)):
            return {'match':'needs_input', 'message':'¿Quisiste decir «'+suggestion+'»? Repite la orden; todavía no se ejecutó.',
                    'understanding':{'method':'verb_suggestion','candidate':suggestion,'execution_allowed':False}}
        return {'match': 'ambiguous' if matches else 'none', 'candidates': matches}

    def _validate_inputs(self, command_id, inputs, require_new=True, check_files=True, deferred_fields=()):
        if not isinstance(inputs, dict):
            raise ValueError('Los parámetros deben ser un objeto JSON')
        if command_id in compensation.COMMAND_ACTIONS:
            if deferred_fields:
                raise ValueError('La compensación requiere un recibo exacto; no acepta bindings diferidos')
            return compensation.validate_inputs(inputs)
        if command_id.startswith(('axx.mcp.', 'axx.generated.')):
            if command_id.startswith('axx.generated.'):
                from .generated_commands import validate_arguments
            else:
                from .mcp_host.catalog import validate_arguments
            descriptor = self.commands[command_id]
            if not descriptor['execution_enabled']:
                raise ValueError('La herramienta ya no está activa')
            schema = descriptor['input_schema']
            if deferred_fields:
                if set(deferred_fields) - schema.get('properties', {}).keys(): raise ValueError('Binding MCP desconocido')
                schema = schema | {'required': [name for name in schema.get('required', []) if name not in deferred_fields]}
            validate_arguments(schema, inputs)
            if check_files and not deferred_fields:
                valid, reason = self.executor.dynamic_tools[command_id].verify_preconditions(inputs)
                if not valid: raise ValueError(reason)
            return dict(inputs)
        schema = self.commands[command_id]['parameters']
        if set(inputs) - schema.keys() or set(deferred_fields) - schema.keys():
            raise ValueError('Parámetro desconocido')
        for name, rule in schema.items():
            if name not in inputs:
                if rule.get('required') and name not in deferred_fields:
                    raise ValueError(f'Falta el parámetro {name}')
                continue
            value = inputs[name]
            if 'enum' in rule and value not in rule['enum']:
                raise ValueError(f'{name} no tiene un valor permitido')
            if rule['type'] == 'boolean' and type(value) is not bool:
                raise ValueError(f'{name} debe ser booleano')
            if rule['type'] == 'number' and (type(value) not in (int, float) or not math.isfinite(value)
                    or not rule.get('minimum', -1e12) <= value <= rule.get('maximum', 1e12)):
                raise ValueError(f'{name} debe ser un número finito dentro de los límites')
            if rule['type'] == 'array':
                if not isinstance(value, list) or not rule.get('minItems', 0) <= len(value) <= rule.get('maxItems', 100):
                    raise ValueError(f'{name} debe ser una lista acotada')
                if rule.get('items', {}).get('type') == 'string' and any(not isinstance(item, str)
                        or len(item) > rule['items'].get('maxLength', 4096) for item in value):
                    raise ValueError(f'{name} debe contener sólo textos acotados')
            if rule['type'] == 'object' and (not isinstance(value, dict)
                    or len(json.dumps(value, allow_nan=False).encode()) > 65536):
                raise ValueError(f'{name} debe ser un objeto acotado')
            if rule['type'] == 'integer' and (type(value) is not int or not rule['minimum'] <= value <= rule['maximum']):
                raise ValueError(f'{name} debe ser un entero dentro de los límites')
            if rule['type'] == 'string':
                if not isinstance(value, str) or len(value) > rule.get('maxLength', 65536) or len(value.encode('utf-8')) > rule.get('maxBytes', 262144):
                    raise ValueError(f'{name} debe ser texto dentro de los límites')
        inputs = dict(inputs)
        if deferred_fields:
            return inputs  # Runtime resolves and validates the complete inputs before prepare.
        if command_id in (*COMPUTER_ADAPTERS, *APPLICATION_ADAPTERS) and isinstance(inputs.get('destination'), str) and compensation.reserved_path(inputs['destination']):
            raise ValueError('El espacio de cuarentena está reservado; elige otro destino')
        if command_id in APPLICATION_ADAPTERS or command_id in COMPUTER_ADAPTERS:
            if check_files:
                from .actions.tools import get_tool
                valid, reason = get_tool(self.adapters[command_id]['tool']).verify_preconditions(inputs)
                if not valid: raise ValueError(reason)
        elif command_id == 'axx.desktop.window.find':
            from .actions.tools import get_tool
            valid, reason = get_tool('desktop_find_control').verify_preconditions(inputs)
            if not valid:
                raise ValueError(reason)
        elif command_id.startswith('axx.desktop.') or command_id in ('axx.shell.powershell', 'axx.shell.cmd'):
            validate_desktop_inputs(self.adapters[command_id]['tool'].removeprefix('desktop_'), inputs)
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
            if compensation.reserved_path(inputs.get('path', '')):
                raise ValueError('El espacio de cuarentena está reservado; elige otro destino')
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

    @staticmethod
    def _recovery_view(result):
        if (result and result.get('state') == 'unknown' and result.get('command_id') in READ_ONLY_COMMANDS
                and not (result.get('evidence') or {}).get('manual_reviewed')):
            result = result | {'evidence': dict(result.get('evidence') or {}, reconciliation_required=True)}
        return result

    def _save(self, result):
        result = dict(result)
        result.pop('compensation', None)  # A current-state projection, never a rewritten historical receipt.
        result = self._recovery_view(result)
        self.db.execute('UPDATE command_runs SET state=?,result_json=? WHERE operation_id=?',
                        (result['state'], json.dumps(result, ensure_ascii=False), result['operation_id']))
        self.db.commit()
        self.change_revision += 1
        return compensation.project_relationship(self.db, result)

    def get(self, operation_id):
        if not isinstance(operation_id, str):
            raise ValueError('operation_id requerido')
        with self.lock:
            row = self.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?', (operation_id,)).fetchone()
            return compensation.project_relationship(self.db, self._recovery_view(json.loads(row[0]))) if row else None

    def operations(self):
        with self.lock:
            return [compensation.project_relationship(self.db, self._recovery_view(json.loads(row[0]))) for row in self.db.execute('SELECT result_json FROM command_runs ORDER BY created_at DESC LIMIT 50')]

    def compensation_preview(self, source_operation_id):
        if not isinstance(source_operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', source_operation_id):
            raise ValueError('COMPENSATION_INPUT_INVALID')
        with self.executor.lock, self.lock:
            if self.closed:
                raise ValueError('Servicio cerrado')
            return compensation.preview(self.db, self.executor.workspace_root, source_operation_id)

    def prepare_compensation(self, source_operation_id, source_receipt_hash, expected_revision, action='quarantine', operation_id=None):
        if action not in ('quarantine', 'restore'):
            raise ValueError('COMPENSATION_ACTION_INVALID')
        inputs = compensation.validate_inputs({'source_operation_id': source_operation_id,
            'source_receipt_hash': source_receipt_hash, 'expected_revision': expected_revision})
        with self.executor.lock, self.lock:
            source = compensation.load_source(self.db, self.executor.workspace_root, source_operation_id)
            if source['source_receipt_hash'] != source_receipt_hash:
                raise ValueError('COMPENSATION_RECEIPT_CHANGED')
            if operation_id and self.get(operation_id):
                return self.prepare('axx.artifact.' + action, inputs, operation_id=operation_id, conversation_id=source['conversation_id'], delivery_mode='background')
            preview = compensation.preview(self.db, self.executor.workspace_root, source_operation_id)
            if (not preview['available'] or preview['action'] != action
                    or preview['compensation']['revision'] != expected_revision):
                raise ValueError('COMPENSATION_PREVIEW_CHANGED')
            return self.prepare('axx.artifact.' + action, inputs, operation_id=operation_id,
                conversation_id=source['conversation_id'], delivery_mode='background')

    def _guard_learning_command(self, command):
        if not command['operation_id'].startswith('learn-'): return
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE name='learning_plans'").fetchone(): return
        row = self.db.execute("""SELECT payload FROM learning_plans WHERE EXISTS
            (SELECT 1 FROM json_each(json_extract(payload,'$.step_records')) r
             WHERE json_extract(r.value,'$.operation_id')=?) LIMIT 1""", (command['operation_id'],)).fetchone()
        if not row: return
        plan = json.loads(row[0])
        index = next(i for i, record in enumerate(plan['step_records']) if record['operation_id'] == command['operation_id'])
        step, record = plan['steps'][index], plan['step_records'][index]
        if (plan['state'] != 'running' or not plan.get('approved_hash') or plan['approved_hash'] != plan.get('plan_hash')
                or record.get('state') != 'running'):
            raise ValueError('El paso pertenece a un plan que todavía no autoriza su despacho.')
        expected = self._validate_inputs(step['command_id'], record.get('resolved_inputs', step['inputs']), require_new=False)
        if (command['command_id'] != step['command_id'] or command['inputs'] != expected or command.get('source') != 'text'
                or command.get('conversation_id') != plan.get('conversation_id')
                or command.get('delivery_mode') != resolve_mode(self.adapters[step['command_id']]['tool'], step.get('delivery_mode'))):
            raise ValueError('El comando no coincide con el paso y el ámbito exactos aprobados.')

    @contextmanager
    def _prepare_transaction(self):
        with self.lock:
            if self.closed: raise ValueError('Servicio cerrado')
            if self.db.in_transaction:
                yield
            else:
                with self.db:
                    self.db.execute('BEGIN IMMEDIATE')
                    yield

    def _assert_memory_scope(self, result):
        if result['command_id'] in compensation.COMMAND_ACTIONS: return None
        task = result.get('conversation_id')
        if task is None and (result.get('memory_scope') is not None or result.get('memory_context_id') is not None):
            raise ValueError('La referencia de memoria requiere una conversación')
        ref = task_memory.assert_context(self.db, result.get('memory_scope'), result.get('memory_context_id'), task_id=task)
        dependencies = task_memory.assert_dependencies(self.db, result.get('memory_dependencies', []))
        match = re.fullmatch(r'axx\.generated\.([a-f0-9]{32})\.r([1-9][0-9]*)\.[a-f0-9]{16}', result['command_id'])
        if match:
            exists = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='capability_revisions'").fetchone()
            row = self.db.execute('SELECT payload FROM capability_revisions WHERE id=? AND revision=?',
                ('cap.' + match[1], int(match[2]))).fetchone() if exists else None
            item = json.loads(row[0]) if row else {}
            if item.get('memory_forgotten'): raise ValueError('La transformación procede de una sesión olvidada')
            source_scope = item.get('memory_scope')
            task_memory.assert_current(self.db, source_scope)
            inherited = item.get('memory_dependencies', []) + ([source_scope] if source_scope else [])
            dependencies = task_memory.assert_dependencies(self.db, list({json.dumps(value,sort_keys=True):value for value in dependencies + inherited}.values()))
            if source_scope is None and self.db.execute('SELECT 1 FROM memory_task_scopes WHERE generation>0 LIMIT 1').fetchone():
                raise ValueError('Revisa la procedencia de la transformación antes de reutilizarla')
        if dependencies: result['memory_dependencies'] = dependencies
        return ref

    def prepare(self, command_id, inputs, source='text', operation_id=None, *, conversation_id=None, command_mode=None, delivery_mode=None, memory_scope=None, memory_context_id=None, _memory_dependencies=()):
        if command_mode not in (None, 'ask', 'auto_safe'):
            raise ValueError('Modo de comandos inválido')
        if conversation_id is not None:
            from .chat_store import ident
            ident(conversation_id)
        if isinstance(command_id, str):
            command_id = PROCEDURE_BINDINGS.get(command_id, command_id)
        if not isinstance(command_id, str) or command_id not in self.commands or source not in ('text', 'voice'):
            raise ValueError('Comando u origen desconocido')
        mode = resolve_mode(self.adapters[command_id]['tool'], delivery_mode) if command_id in self.adapters else None
        if command_id not in self.adapters and delivery_mode is not None:
            raise ValueError('El comando documental no tiene modo ejecutable.')
        if command_id == 'axx.shell.powershell' and source != 'text':
            raise ValueError('Escribe el script PowerShell y revisa su aprobación.')
        op_id = str(uuid.uuid4()) if operation_id is None else operation_id
        if not isinstance(op_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', op_id):
            raise ValueError('operation_id inválido')
        with self._prepare_transaction():
            if command_id in compensation.COMMAND_ACTIONS:
                compensation.validate_inputs(inputs)
                source_receipt = compensation.load_source(self.db, self.executor.workspace_root, inputs['source_operation_id'])
                if conversation_id not in (None, source_receipt['conversation_id']):
                    raise ValueError('La compensación pertenece a otra conversación')
                conversation_id = source_receipt['conversation_id']
            existing = self.get(op_id)
            # Compare before preconditions: idempotent replay must survive an artifact now existing.
            if existing:
                if existing.get('command_id') == '' and existing['state'] == 'cancelled':
                    return existing | {'replayed': True}
                existing_inputs = existing['inputs']
                candidate = self._validate_inputs(command_id, inputs, require_new=False) if command_id in self.adapters else inputs
                if existing['command_id'] != command_id or existing_inputs != candidate or existing['source'] != source or existing.get('conversation_id') != conversation_id or existing.get('command_mode') != command_mode or existing.get('delivery_mode', mode) != mode:
                    raise ValueError('operation_id ya está vinculado a otros parámetros')
                return existing | {'replayed': True}
            admission = {'command_id': command_id, 'conversation_id': conversation_id, 'memory_scope': memory_scope,
                'memory_context_id': memory_context_id, 'memory_dependencies':list(_memory_dependencies)}
            selected_scope = self._assert_memory_scope(admission)
            if command_mode is not None:
                # Unknown effects are guarded by target below; they must not prevent
                # the independent observations needed to reconcile them.
                pending = self.db.execute("SELECT operation_id FROM command_runs WHERE state IN ('prepared','awaiting_approval','running') AND expires_at>? LIMIT 1", (time.time(),)).fetchone()
                if pending:
                    raise ValueError('Hay un comando pendiente. Revisa o cancela la operación antes de preparar otra.')
            command = self.commands[command_id]
            enabled = command['execution_enabled']
            if enabled:
                inputs = self._validate_inputs(command_id, inputs)
                if command_id not in READ_ONLY_COMMANDS:
                    for row in self.db.execute("SELECT result_json FROM command_runs WHERE state='unknown' AND command_id=?", (command_id,)):
                        previous = json.loads(row[0])
                        if (previous.get('evidence') or {}).get('manual_reviewed') is True:
                            continue
                        if previous['inputs'] == inputs:
                            raise ValueError('Hay un efecto desconocido de esta operación. Revisa su resultado antes de repetirla.')
                if command_id in ('axx.desktop.notepad.text', 'axx.desktop.window.set_value', 'axx.desktop.window.invoke',
                                   'axx.desktop.input', 'axx.desktop.state', 'axx.desktop.window.state', 'axx.browser.navigate'):
                    for row in self.db.execute("SELECT result_json FROM command_runs WHERE state='unknown' AND command_id=?", (command_id,)):
                        previous = json.loads(row[0])
                        if (previous.get('evidence') or {}).get('manual_reviewed') is True:
                            continue
                        identity = ('window_title',) if command_id == 'axx.desktop.notepad.text' else ('window_id', 'pid', 'control_id')
                        if command_id in ('axx.desktop.input', 'axx.desktop.window.state'): identity = ('window_id', 'pid')
                        if command_id == 'axx.browser.navigate': identity = ('browser_session', 'tab_id')
                        if all(previous['inputs'].get(key) == inputs.get(key) for key in identity):
                            raise ValueError('Hay una escritura incierta en ese destino. Usa Revisar efecto antes de preparar otra.')
            elif inputs != {}:
                raise ValueError('El comando documental no admite parámetros ejecutables')
            approval = enabled and (command.get('requires_approval', False) or command_mode == 'ask')
            state = ('awaiting_approval' if approval else 'prepared') if enabled else 'blocked'
            result = {'operation_id': op_id, 'command_id': command_id, 'inputs': inputs, 'source': source,
                      'conversation_id': conversation_id, 'command_mode': command_mode,
                      'delivery_mode': mode, 'context_id': 'host',
                      'state': state, 'requires_approval': approval, 'postconditions_passed': False,
                      'evidence': {}, 'output': None, 'cancel_requested': False,
                      'error': None if enabled else {'code': 'NOT_IMPLEMENTED', 'message': command['blocked_reason']}}
            if command_id in compensation.COMMAND_ACTIONS:
                result['source_operation_id'] = inputs['source_operation_id']
            if selected_scope is not None: result['memory_scope'] = selected_scope
            if admission['memory_dependencies']: result['memory_dependencies'] = admission['memory_dependencies']
            if memory_context_id is not None and command_id not in compensation.COMMAND_ACTIONS:
                result['memory_context_id'] = memory_context_id
            now = time.time()
            self.db.execute('INSERT INTO command_runs VALUES (?,?,?,?,?,?,?,?)',
                (op_id, command_id, json.dumps(inputs), source, state, json.dumps(result, ensure_ascii=False), now + 300, now))
            return result

    def renew(self, operation_id):
        """Renew review time only when the immutable command has never reached the executor."""
        with self.executor.lock, self.lock:
            if self.closed:
                raise ValueError('Servicio cerrado')
            result = self.get(operation_id)
            if not result:
                raise ValueError('Operación desconocida')
            if result['state'] not in ('prepared', 'awaiting_approval', 'expired') or result.get('cancel_requested'):
                return result
            action_id = 'cmd-' + hashlib.sha256(operation_id.encode()).hexdigest()
            if self.executor.get_operation(action_id):
                raise ValueError('La operación ya tiene un recibo del ejecutor; reconcilia su resultado')
            inputs = self._validate_inputs(result['command_id'], result['inputs'])
            if inputs != result['inputs']:
                raise ValueError('Los parámetros preparados cambiaron')
            self.db.execute('UPDATE command_runs SET expires_at=? WHERE operation_id=?', (time.time() + 300, operation_id))
            return self._save(result | {'state': 'awaiting_approval' if result['requires_approval'] else 'prepared', 'error': None})

    @staticmethod
    def _allows_remote_confirmation(command_id, command, inputs):
        return command.get('requires_approval', True) is False and (
            command.get('risk') in ('read', 'desktop_open')
            or command_id == 'axx.desktop.window.close' and command.get('risk') == 'local_state'
            and isinstance(inputs.get('expected_title'), str) and bool(inputs['expected_title'].strip())
            and isinstance(inputs.get('expected_process_started'), str) and bool(inputs['expected_process_started'].strip()))

    def remote_review(self, operation_id):
        """Review only fixed, PC-policy-safe commands; this grants no authority."""
        with self.lock:
            result = self.get(operation_id)
            if not result:
                raise ValueError('Operación desconocida')
            row = self.db.execute('SELECT expires_at FROM command_runs WHERE operation_id=?', (operation_id,)).fetchone()
            expires_at = row[0]
            command_id = result['command_id']
            current = self.commands.get(command_id, {})
            adapter = self.adapters.get(command_id, {})
            static = command_id in ADAPTERS and current.get('source', {}).get('kind') == 'local_adapter'
            reserved = operation_id.startswith('learn-')
            if not reserved and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='learning_plans'").fetchone():
                reserved = bool(self.db.execute("""SELECT 1 FROM learning_plans WHERE EXISTS
                    (SELECT 1 FROM json_each(json_extract(payload,'$.step_records')) r
                     WHERE json_extract(r.value,'$.operation_id')=?) LIMIT 1""", (operation_id,)).fetchone())
            requires_pc = not self._allows_remote_confirmation(command_id, current, result['inputs'])
            catalog = {'risk': current.get('risk'), 'requires_approval': current.get('requires_approval'),
                       'execution_enabled': current.get('execution_enabled'), 'tool': adapter.get('tool')}
            snapshot = {key: result.get(key) for key in ('operation_id','command_id','inputs','source','conversation_id','command_mode','delivery_mode')}
            snapshot['catalog'] = catalog
            plan_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
            if reserved:
                reason = 'PLAN_RESERVED'
            elif not static or not current.get('execution_enabled') or not adapter.get('tool'):
                reason = 'NOT_STATIC_EXECUTABLE'
            elif requires_pc:
                reason = 'PC_APPROVAL_REQUIRED'
            elif result.get('cancel_requested') or result['state'] not in ('prepared', 'awaiting_approval'):
                reason = 'NOT_REVIEWABLE'
            elif time.time() > expires_at:
                reason = 'EXPIRED'
            else:
                reason = None
            return {'operation_id': operation_id, 'state': result['state'], 'title': current.get('title', ''),
                    'description': current.get('description', ''), 'risk': current.get('risk'),
                    'inputs': result['inputs'], 'plan_hash': plan_hash, 'expires_at': expires_at,
                    'eligible': reason is None, 'reason': reason}

    def confirm_remote(self, operation_id, plan_hash, authorization_check):
        if not isinstance(plan_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', plan_hash) or not callable(authorization_check):
            raise ValueError('Confirmación remota inválida')

        def claim(current, dispatch=False):
            review = self.remote_review(operation_id)
            if dispatch and current['state'] == 'running' and review['reason'] == 'NOT_REVIEWABLE':
                # The running state was set by this invocation, under the existing gate.
                self._remote_validate_running(current, review, plan_hash)
            elif not review['eligible'] or not hmac.compare_digest(review['plan_hash'], plan_hash):
                raise ValueError('La revisión remota ya no coincide con la operación')
            try:
                allowed = authorization_check()
            except Exception:
                raise ValueError('Autorización remota revocada') from None
            if allowed is False:
                raise ValueError('Autorización remota revocada')

        return self.execute(operation_id, approved=False, _remote_claim=claim)

    def _remote_validate_running(self, current, review, plan_hash):
        # Validate mutable policy and TTL again without treating running as reviewable.
        command_id = current['command_id']
        command = self.commands.get(command_id, {})
        if (command_id not in ADAPTERS or command.get('source', {}).get('kind') != 'local_adapter'
                or not command.get('execution_enabled')
                or not self._allows_remote_confirmation(command_id, command, current['inputs']) or current.get('cancel_requested')
                or time.time() > review['expires_at'] or not hmac.compare_digest(review['plan_hash'], plan_hash)):
            raise ValueError('La revisión remota ya no coincide con la operación')

    def execute(self, operation_id, approved=False, *, allow_parallel_read=False, _remote_claim=None):
        if type(allow_parallel_read) is not bool:
            raise ValueError('allow_parallel_read debe ser booleano')
        with self.lock:
            if allow_parallel_read:
                prepared = self.get(operation_id)
                if not prepared or prepared['command_id'] not in PARALLEL_READ_COMMANDS:
                    raise ValueError('Solo se permite paralelismo para lecturas independientes admitidas')
                if self.execution_gate.locked() or operation_id in self.parallel_operations or len(self.parallel_operations) >= 2:
                    raise ValueError('BUSY: hay una operación de catálogo en curso')
                self.parallel_operations.add(operation_id)
            elif self.parallel_operations or not self.execution_gate.acquire(blocking=False):
                raise ValueError('BUSY: hay una operación de catálogo en curso')
        try:
            with self.lock:
                result = self.get(operation_id)
                if not result:
                    raise ValueError('Operación desconocida; prepara el comando primero')
                if _remote_claim is not None:
                    _remote_claim(result)
                    approved = True
                if result['state'] in TERMINAL:
                    return result | {'replayed': True}
                try:
                    self._assert_memory_scope(result)
                except ValueError as exc:
                    return self._save(result | {'state': 'failed', 'postconditions_passed': False,
                        'error': {'code': 'DISPATCH_REJECTED', 'message': str(exc)}})
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
                self.cancel_events[operation_id] = threading.Event()
                self._save(result)
            try:
                action_id = 'cmd-' + hashlib.sha256(operation_id.encode()).hexdigest()
                # A legacy action may hold the executor. Check cancellation again at the dispatch boundary.
                with (nullcontext() if allow_parallel_read else self.executor.lock), ExitStack() as leases:
                    if not allow_parallel_read:
                        self.executor.wait_for_reads()
                    with self.lock:
                        current = self.get(operation_id)
                        if current['cancel_requested']:
                            return self._save(current | {'state': 'cancelled', 'error': {'code': 'CANCELLED', 'message': 'Cancelado antes de ejecutar.'}})
                        try:
                            self._assert_memory_scope(current)
                            if _remote_claim is not None:
                                _remote_claim(current, dispatch=True)
                            self._guard_learning_command(current)
                        except ValueError as exc:
                            raise ActionExecutionError(str(exc)) from exc
                        if self.dispatch_guard:
                            try:
                                self.dispatch_guard(operation_id)
                            except ValueError as exc:
                                raise ActionExecutionError(str(exc)) from exc
                        if self.mission_guard:
                            try:
                                leases.enter_context(self.mission_guard(operation_id) or nullcontext())
                            except ValueError as exc:
                                raise ActionExecutionError(str(exc)) from exc
                        try:
                            self._assert_memory_scope(current)
                        except ValueError as exc:
                            raise ActionExecutionError(str(exc)) from exc
                    args = (self.adapters[result['command_id']]['tool'], result['inputs'], action_id)
                    mode_args = {'delivery_mode': result['delivery_mode']} if result.get('delivery_mode') else {}
                    if allow_parallel_read:
                        action = self.executor.execute_action(*args, cancel_event=self.cancel_events[operation_id], allow_parallel_read=True, **mode_args)
                    else:
                        action = self.executor.execute_action(*args, cancel_event=self.cancel_events[operation_id], **mode_args) if operation_id in self.cancel_events else self.executor.execute_action(*args, **mode_args)
                final = result | {key: action.get(key) for key in ('state', 'postconditions_passed', 'output', 'evidence', 'duration_ms', 'dispatch_status', 'effect_status')}
                final.update(action_operation_id=action_id, tool_name=self.adapters[result['command_id']]['tool'])
                final.update(model_calls_used=0, model_calls_source='deterministic_no_model_path')
                final['error'] = {'code': 'ACTION_FAILED', 'message': action['error']} if action.get('error') else None
                if final['state'] not in TERMINAL:
                    final.update(state='unknown', postconditions_passed=False)
            except Exception as exc:
                before_dispatch = isinstance(exc, ActionExecutionError) and self.executor.get_operation(action_id) is None
                final = result | {'state': 'failed' if before_dispatch else 'unknown', 'postconditions_passed': False,
                                  'error': {'code': 'DISPATCH_REJECTED' if before_dispatch else 'EXECUTION_UNCERTAIN',
                                            'message': str(exc) if before_dispatch else f'Inspecciona la operación antes de reintentar ({type(exc).__name__}).'}}
            with self.lock:
                final['cancel_requested'] = self.get(operation_id)['cancel_requested']
                return self._save(final)
        finally:
            with self.lock:
                self.cancel_events.pop(operation_id, None)
                if allow_parallel_read:
                    self.parallel_operations.discard(operation_id)
                else:
                    self.execution_gate.release()

    def review_unknown(self, operation_id, reviewed=False):
        """Acknowledge manual inspection, never certify or repeat the prior effect."""
        if reviewed is not True:
            raise ApprovalRequired('Confirma explícitamente que revisaste el efecto antes de preparar otra acción.')
        with self.lock:
            if self.closed:
                raise ValueError('Servicio cerrado')
            if self.parallel_operations or not self.execution_gate.acquire(blocking=False):
                raise ValueError('Hay una operación en curso.')
        try:
            with self.executor.lock, self.lock:
                result = self.get(operation_id)
                if not result or result['state'] != 'unknown':
                    raise ValueError('La operación no tiene un efecto incierto pendiente de revisión.')
                if result['command_id'] in compensation.COMMAND_ACTIONS:
                    raise ValueError('COMPENSATION_RECONCILE_REQUIRED: usa conciliar sin repetir; una revisión manual no autoriza otro movimiento')
                if (result.get('evidence') or {}).get('manual_reviewed') is True:
                    return result  # Idempotent acknowledgement preserves its original time.
                action_id = result.get('action_operation_id') or 'cmd-' + hashlib.sha256(operation_id.encode()).hexdigest()
                action = self.executor.get_operation(action_id)
                if action and (action['state'] != 'unknown' or action.get('tool_name') != self.adapters[result['command_id']]['tool']):
                    raise ValueError('El recibo del ejecutor cambió; revisa su estado actual.')
                acknowledgement = {'manual_reviewed': True, 'manual_reviewed_at': time.time(),
                                   'reconciliation_required': False, 'effect_uncertain': True}
                result.update(state='unknown', postconditions_passed=False, effect_status='unknown',
                              evidence=dict(result.get('evidence') or {}, **acknowledgement))
                # Both journals live in this database. Persist acknowledgement atomically
                # through one connection; a crash cannot unlock only one of them.
                with self.db:
                    if action:
                        evidence = dict(action.get('evidence') or {}, **acknowledgement)
                        action.update(state='unknown', postconditions_passed=False, effect_status='unknown', evidence=evidence)
                        self.db.execute("UPDATE operations SET result_json=?,evidence_json=? WHERE operation_id=? AND state='unknown'",
                                        (json.dumps(action, ensure_ascii=False), json.dumps(evidence), action_id))
                    self.db.execute("UPDATE command_runs SET result_json=? WHERE operation_id=? AND state='unknown'",
                                    (json.dumps(result, ensure_ascii=False), operation_id))
                return result
        finally:
            self.execution_gate.release()

    def reconcile(self, operation_id):
        """Read back an uncertain UIA effect without dispatching it a second time."""
        if not self.execution_gate.acquire(blocking=False): raise ValueError('Hay una operación en curso.')
        try:
            with self.executor.lock, self.lock:
                result = self.get(operation_id)
                if not result or result['state'] != 'unknown': raise ValueError('La operación no está pendiente de reconciliación.')
                if result['command_id'] in compensation.COMMAND_ACTIONS:
                    action_id = result.get('action_operation_id') or 'cmd-' + hashlib.sha256(operation_id.encode()).hexdigest()
                    action = self.executor.get_operation(action_id)
                    if (not action or action['tool_name'] != self.adapters[result['command_id']]['tool']
                            or action.get('inputs') != result['inputs'] or action['state'] not in ('unknown', 'running', 'succeeded')):
                        raise ValueError('COMPENSATION_EXECUTOR_RECEIPT_CHANGED')
                    with self.db:
                        reconciled = compensation.reconcile_result(self.db, self.executor.workspace_root, result)
                        reconciled.pop('compensation', None)
                        action.update({key: reconciled.get(key) for key in ('state', 'postconditions_passed', 'output', 'evidence', 'effect_status')})
                        action['error'] = None if reconciled.get('error') is None else reconciled['error']['message']
                        self.db.execute('UPDATE operations SET state=?,result_json=?,evidence_json=? WHERE operation_id=?',
                            (action['state'], json.dumps(action), json.dumps(action['evidence']), action_id))
                        self.db.execute('UPDATE command_runs SET state=?,result_json=? WHERE operation_id=?',
                            (reconciled['state'], json.dumps(reconciled, ensure_ascii=False), operation_id))
                    return compensation.project_relationship(self.db, reconciled)
                if result['command_id'] in READ_ONLY_COMMANDS:
                    # These immutable registered tools have no write effects. A failed
                    # observation is not success and must not lock every future action.
                    evidence = dict(result.get('evidence') or {}, reconciled=True,
                                    verification='read_only_failure_without_effect', reconciliation_required=False)
                    action_id = result.get('action_operation_id')
                    action = self.executor.get_operation(action_id) if action_id else None
                    if action and action['state'] == 'unknown':
                        action.update(state='failed', postconditions_passed=False, evidence=evidence, effect_status='not_observed')
                        with self.executor.db:
                            self.executor.db.execute("UPDATE operations SET state='failed', result_json=?, evidence_json=? WHERE operation_id=?",
                                                     (json.dumps(action), json.dumps(evidence), action_id))
                    return self._save(result | {'state':'failed', 'postconditions_passed':False, 'evidence':evidence, 'effect_status':'not_observed',
                                                'error':{'code':'READ_FAILED','message':'La observación falló. No se ejecutó ningún efecto ni se repitió la lectura.'}})
                if result['command_id'] not in ('axx.desktop.notepad.text', 'axx.desktop.window.set_value'):
                    raise ValueError('Esta operación necesita revisión manual de su efecto.')
                target = result.get('evidence', {}).get('reconciliation_target')
                if not target: raise ValueError('Falta una identidad verificable; revisa la ventana manualmente.')
                from .actions.windows_automation import _uia
                output = _uia(dict(target, operation='check_value', value=result['inputs']['value']))
                expected_hash = hashlib.sha256(result['inputs']['value'].encode('utf-8')).hexdigest()
                if output.get('value_sha256') != expected_hash or output.get('value_length') != len(result['inputs']['value'].encode('utf-16-le')) // 2:
                    raise ValueError('El efecto todavía no coincide. La operación sigue incierta y no se repitió.')
                evidence = dict(result['evidence'], effect_uncertain=False, reconciliation_required=False,
                                reconciled=True, verification='uia_value_readback', value_sha256=output['value_sha256'], value_length=output['value_length'])
                action_id = result['action_operation_id']
                action = self.executor.get_operation(action_id)
                if not action or action['state'] != 'unknown': raise ValueError('El recibo del ejecutor cambió.')
                action.update(state='succeeded', postconditions_passed=True, error=None, output=output, evidence=evidence,
                              effect_status='confirmed', dispatch_status='delivered')
                with self.executor.db:
                    self.executor.db.execute("UPDATE operations SET state='succeeded', result_json=?, evidence_json=? WHERE operation_id=?", (json.dumps(action),json.dumps(evidence),action_id))
                return self._save(result | {'state':'succeeded','postconditions_passed':True,'error':None,'output':output,'evidence':evidence,
                                           'effect_status':'confirmed','dispatch_status':'delivered'})
        finally:
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
