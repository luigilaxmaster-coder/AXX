"""Scoped anticipation over the existing command journal; never another executor."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import inspect
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
import uuid
import weakref
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .actions.file_inspection import hash_file, fingerprint
from .actions.tools import artifact_path_error, get_tool
from .commands import ApprovalRequired

LOG = logging.getLogger('axx.anticipation')
MODES = ('OFF', 'SHADOW', 'SUGGEST', 'PREPARE', 'EXECUTE')
PROFILES = ('discreto', 'copiloto', 'full')
PENDING = ('DETECTED', 'PREPARED', 'AWAITING_APPROVAL')
TERMINAL = ('VERIFIED', 'FAILED', 'CANCELLED', 'EXPIRED', 'DISMISSED', 'SUPPRESSED', 'UNCERTAIN')
ROUTINE = 'verify_generated_artifact'
CAPABILITY = 'verify_artifact'
ARTIFACT_GENERATORS = ('file_artifact_writer', 'office_excel_csv', 'office_word_pdf', 'office_powerpoint_pdf', 'browser_download_pdf')
ACTIVE_OWNERS = weakref.WeakValueDictionary()
DEFAULTS = {
    'profile': 'discreto', 'paused': False, 'observation_paused': False,
    'sources': {'events': True, 'folders': False, 'applications': False,
                'screen': False, 'microphone': False, 'clipboard': False},
    'profiles': {name: {'mode': mode, 'interruptions': 'silent' if name == 'discreto' else 'cards',
        'cooldown_seconds': 60, 'max_interruptions_hour': 3, 'retention_days': 30,
        'cadence_seconds': 30, 'schedule': None,
        'resources': {'max_events_tick': 25, 'max_entries_scan': 500, 'max_file_bytes': 40 * 1024 * 1024,
                      'max_tick_ms': 1000, 'max_cpu_ms_tick': 250}}
        for name, mode in zip(PROFILES, ('OFF', 'SUGGEST', 'EXECUTE'))},
    'scopes': [], 'observation_targets': []}
CONTEXT_KEYS = ('project_id', 'application_id', 'device_id')
RESOURCE_LIMITS = {'max_events_tick': (1, 100), 'max_entries_scan': (1, 2000),
    'max_file_bytes': (1024, 512 * 1024 * 1024), 'max_tick_ms': (50, 5000), 'max_cpu_ms_tick': (10, 1000)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value, label='Identificador'):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        raise ValueError(label + ' inválido')
    return value


def scope_identifier(value, key):
    if (not isinstance(value, str) or not value or len(value) > (128 if key == 'project_id' else 160)
            or value != value.strip() or any(ord(char) < 32 for char in value)):
        raise ValueError('Identificador de ámbito inválido: ' + key)
    if key == 'device_id':
        identifier(value, key)
    return value


def directory(raw):
    error = artifact_path_error(raw)
    if error:
        raise ValueError(error)
    path = Path(raw)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError('Selecciona una carpeta local absoluta existente')
    return str(path.resolve())


class StaleContext(ValueError):
    pass


class AnticipationService:
    """Durable policy, proposals and evidence in the application's existing SQLite."""

    def __init__(self, commands, clock=time.time):
        self.commands, self.clock = commands, clock
        self.owner_id = uuid.uuid4().hex
        ACTIVE_OWNERS[self.owner_id] = self
        self.lock, self.tick_gate = threading.RLock(), threading.Lock()
        self.closed = False
        self.source_state, self.source_observations = {}, []
        self.verifier_cache = {}
        self.tick_started = None
        self.tick_events = {}
        self.db = sqlite3.connect(str(commands.executor.db_path), timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS anticipation_config (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS anticipation_seen (operation_id TEXT PRIMARY KEY, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS anticipation_events (event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS anticipation_suggestions (suggestion_id TEXT PRIMARY KEY, dedupe_key TEXT UNIQUE NOT NULL, task_id TEXT NOT NULL, routine_id TEXT NOT NULL, state TEXT NOT NULL, plan_hash TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS anticipation_grants (grant_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS anticipation_suppressions (task_id TEXT NOT NULL, routine_id TEXT NOT NULL, PRIMARY KEY(task_id,routine_id));
                CREATE TABLE IF NOT EXISTS anticipation_transitions (id INTEGER PRIMARY KEY AUTOINCREMENT, suggestion_id TEXT NOT NULL, stage TEXT NOT NULL, at REAL NOT NULL, detail TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS anticipation_stats (task_id TEXT NOT NULL, routine_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(task_id,routine_id));
                CREATE TABLE IF NOT EXISTS anticipation_measurements (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, kind TEXT NOT NULL, at REAL NOT NULL, wall_ms REAL NOT NULL, cpu_ms REAL);
                CREATE TABLE IF NOT EXISTS anticipation_privacy (action_operation_id TEXT PRIMARY KEY, verification_scope TEXT NOT NULL, at REAL NOT NULL);
            ''')
            if not self.db.execute('SELECT 1 FROM anticipation_config WHERE id=1').fetchone():
                self.db.execute('INSERT INTO anticipation_config VALUES (1,?)', (canonical(DEFAULTS),))
                # Installing anticipation never turns historical artifacts into new initiatives.
                self.db.execute("INSERT OR IGNORE INTO anticipation_seen SELECT operation_id,? FROM operations WHERE tool_name='file_artifact_writer'", (self.clock(),))
            if not self.db.execute("SELECT 1 FROM anticipation_seen WHERE operation_id='baseline-generators-v2'").fetchone():
                placeholders = ','.join('?' for _ in ARTIFACT_GENERATORS)
                self.db.execute('INSERT OR IGNORE INTO anticipation_seen SELECT operation_id,? FROM operations WHERE tool_name IN (' + placeholders + ')', (self.clock(), *ARTIFACT_GENERATORS))
                self.db.execute('INSERT INTO anticipation_seen VALUES (?,?)', ('baseline-generators-v2', self.clock()))
        self._recover()

    def _config(self):
        saved = json.loads(self.db.execute('SELECT payload FROM anticipation_config WHERE id=1').fetchone()[0])
        config = copy.deepcopy(DEFAULTS) | saved
        config['sources'] = DEFAULTS['sources'] | saved.get('sources', {})
        config['profiles'] = {name: copy.deepcopy(DEFAULTS['profiles'][name]) | saved.get('profiles', {}).get(name, {}) for name in PROFILES}
        for name in PROFILES:
            config['profiles'][name]['resources'] = DEFAULTS['profiles'][name]['resources'] | saved.get('profiles', {}).get(name, {}).get('resources', {})
        return config

    def _save(self, item):
        self.db.execute('UPDATE anticipation_suggestions SET state=?,payload=? WHERE suggestion_id=?',
                        (item['state'], canonical(item), item['suggestion_id']))
        return item

    def _transition(self, item, stage, detail=None):
        self.db.execute('INSERT INTO anticipation_transitions(suggestion_id,stage,at,detail) VALUES (?,?,?,?)',
                        (item['suggestion_id'], stage, self.clock(), canonical(detail or {})))

    def _stats(self, task, routine, field):
        row = self.db.execute('SELECT payload FROM anticipation_stats WHERE task_id=? AND routine_id=?', (task, routine)).fetchone()
        stats = json.loads(row[0]) if row else {}
        stats[field] = stats.get(field, 0) + 1
        stats['last_observed'] = self.clock()
        self.db.execute('INSERT INTO anticipation_stats VALUES (?,?,?) ON CONFLICT(task_id,routine_id) DO UPDATE SET payload=excluded.payload',
                        (task, routine, canonical(stats)))

    def _get(self, key):
        identifier(key)
        row = self.db.execute('SELECT payload FROM anticipation_suggestions WHERE suggestion_id=?', (key,)).fetchone()
        if not row:
            raise ValueError('Propuesta desconocida')
        return json.loads(row[0])

    def _items(self, task_id=None):
        sql = 'SELECT payload FROM anticipation_suggestions'
        args = ()
        if task_id is not None:
            identifier(task_id, 'Tarea')
            sql += ' WHERE task_id=?'
            args = (task_id,)
        return [json.loads(row[0]) for row in self.db.execute(sql + ' ORDER BY at DESC', args)]

    def _policy(self, task_id, path, config=None, context=None):
        config = config or self._config()
        context = context or {}
        possible = [scope for scope in config['scopes'] if
            (not scope.get('task_id') or scope['task_id'] == task_id) and
            (not scope.get('root') or Path(path).is_relative_to(Path(scope['root'])))]
        if any(scope.get(key) and not context.get(key) for scope in possible for key in CONTEXT_KEYS):
            return None, {'mode': 'OFF', 'missing_context': True}
        matches = [scope for scope in possible if all(not scope.get(key) or scope[key] == context.get(key) for key in CONTEXT_KEYS)]
        if any(scope.get('exclude') for scope in matches):
            return None, {'mode': 'OFF'}
        names = {scope['profile'] for scope in matches if scope.get('profile')}
        if len(names) > 1:
            return None, {'mode': 'OFF', 'conflict': True}
        name = next(iter(names)) if names else config['profile']
        options = config['profiles'][name]
        source = context.get('source', 'events')
        if (config['paused'] or config['observation_paused'] or not config['sources'].get(source, False)
                or not self._schedule_active(options.get('schedule'))):
            return name, options | {'mode': 'OFF'}
        return name, options

    def _schedule_active(self, schedule):
        if schedule is None:
            return True
        try:
            local = dt.datetime.fromtimestamp(self.clock(), ZoneInfo(schedule['timezone']))
        except (ZoneInfoNotFoundError, ValueError, OverflowError):
            return False
        minute = local.hour * 60 + local.minute
        start, end = (int(value[:2]) * 60 + int(value[3:]) for value in (schedule['start'], schedule['end']))
        if start <= end:
            return local.weekday() in schedule['days'] and start <= minute <= end
        return ((local.weekday() in schedule['days'] and minute >= start)
                or ((local.weekday() - 1) % 7 in schedule['days'] and minute <= end))

    def _within_budget(self, options):
        if self.tick_started is None:
            return True
        resources = options.get('resources', DEFAULTS['profiles']['discreto']['resources'])
        return ((time.perf_counter() - self.tick_started[0]) * 1000 < resources['max_tick_ms']
                and (time.process_time() - self.tick_started[1]) * 1000 < resources['max_cpu_ms_tick'])

    def _take_event_budget(self, profile, options):
        if self.tick_started is None:
            return True
        if self.tick_events.get(profile, 0) >= options['resources']['max_events_tick']:
            return False
        self.tick_events[profile] = self.tick_events.get(profile, 0) + 1
        return True

    def _grant(self, item):
        now = self.clock()
        for row in self.db.execute('SELECT payload FROM anticipation_grants'):
            grant = json.loads(row[0])
            if (not grant['revoked'] and grant['task_id'] == item['task_id'] and grant['capability'] == CAPABILITY
                    and (not item.get('grant_id') or item['grant_id'] == grant['grant_id'])
                    and (grant['expires_at'] is None or grant['expires_at'] > now)
                    and Path(item['plan']['inputs']['path']).is_relative_to(Path(grant['root']))):
                return grant
        return None

    def _suppressed(self, task, routine):
        return self.db.execute('SELECT 1 FROM anticipation_suppressions WHERE task_id IN (?,?) AND routine_id=?', (task, '*', routine)).fetchone() is not None

    def _visible(self, item, options):
        if item.get('shadow') or item.get('dismissed') or options.get('interruptions') == 'silent' or options.get('mode') == 'OFF':
            return False
        if item['state'] in ('DISMISSED', 'SUPPRESSED', 'CANCELLED', 'EXPIRED'):
            return False
        if item.get('shown_at'):
            return True
        count = self.db.execute("SELECT COUNT(*) FROM anticipation_suggestions WHERE json_extract(payload,'$.shown_at')>?", (self.clock() - 3600,)).fetchone()[0]
        return count < options.get('max_interruptions_hour', 0)

    def _can_verify(self):
        command = self.commands.commands.get('axx.file.sha256') or {}
        adapter = self.commands.adapters.get('axx.file.sha256') or {}
        return command.get('execution_enabled') is True and adapter.get('tool') == 'file_inspection' and get_tool('file_inspection') is not None

    def _verifier(self, path):
        suffix = Path(path).suffix.casefold()
        kind = ('pdf' if suffix == '.pdf' else 'media' if suffix in ('.mp4', '.mkv', '.mov', '.avi', '.mp3', '.wav', '.flac', '.ogg', '.m4a')
                else 'ocr' if suffix in ('.png', '.jpg', '.jpeg') else 'hash')
        command_id = 'axx.file.sha256' if kind == 'hash' else 'axx.artifact.' + kind
        expected_tool = 'file_inspection' if kind == 'hash' else 'artifact_' + kind
        command, adapter = self.commands.commands.get(command_id) or {}, self.commands.adapters.get(command_id) or {}
        available = command.get('execution_enabled') is True and adapter.get('tool') == expected_tool and get_tool(expected_tool) is not None
        reason = 'Lectura local registrada; precondiciones y resultado se comprueban al ejecutar.'
        scope = {'hash': 'integrity_only', 'pdf': 'pdf_structure_and_text_readability', 'media': 'media_metadata', 'ocr': 'image_ocr'}[kind]
        if kind != 'hash' and not callable(getattr(self.commands.executor, 'result_filter', None)):
            available, reason = False, 'Falta el filtro de privacidad del journal; no se conservará texto por una ruta alternativa.'
        if kind == 'pdf':
            try:
                ready = importlib.util.find_spec('pypdf') is not None
            except (ImportError, ValueError):
                ready = False
            if not ready:
                available, reason = False, 'El lector PDF registrado no está disponible en este entorno.'
        elif kind == 'media' and not shutil.which('ffprobe'):
            available, reason = False, 'ffprobe no está disponible; no se simula inspección multimedia.'
        elif kind == 'ocr':
            cached = self.verifier_cache.get('ocr')
            if cached is None or time.monotonic() - cached[0] > 30:
                try:
                    if importlib.util.find_spec('rapidocr_onnxruntime') is None:
                        raise ValueError('OCR no está instalado')
                    from .actions.local_ocr import models
                    models()
                    cached = (time.monotonic(), True)
                except (ImportError, ValueError, OSError, KeyError):
                    cached = (time.monotonic(), False)
                self.verifier_cache['ocr'] = cached
            if not cached[1]:
                available, reason = False, 'Faltan el lector OCR o sus modelos locales verificados; no se instalarán automáticamente.'
        if suffix in ('.docx', '.xlsx', '.pptx'):
            reason = 'No hay inspector de formato de solo lectura registrado; esta comprobación acredita únicamente integridad.'
        return {'command_id': command_id, 'available': available, 'verification_scope': scope,
                'version': str(getattr(get_tool(expected_tool), 'version', 'unknown')),
                'semantic_verified': False, 'reason': reason}

    @staticmethod
    def _applications_available():
        from .actions import windows_automation as windows
        try:
            metadata_reader = 'include_titles' in inspect.signature(windows.list_windows).parameters
        except (TypeError, ValueError):
            metadata_reader = False
        return os.name == 'nt' and get_tool('desktop_list_windows') is not None and metadata_reader

    def filter_result(self, action_operation_id, output, evidence, error=None):
        """Executor hook: remove raw document content before either journal commits it."""
        with self.lock:
            row = self.db.execute('SELECT verification_scope FROM anticipation_privacy WHERE action_operation_id=?', (action_operation_id,)).fetchone()
            if not row:
                return output, evidence, error
            scope = row[0]
        content_keys = {'text', 'text_excerpt', 'content', 'transcript', 'lines', 'full_text', 'page_text', 'ocr_text'}
        def metadata(value):
            if isinstance(value, dict):
                result = {key: metadata(child) for key, child in value.items() if key.casefold() not in content_keys}
                if isinstance(value.get('text_excerpt'), str):
                    result['text_characters'] = len(value['text_excerpt'])
                if isinstance(value.get('lines'), list):
                    result['line_count'] = len(value['lines'])
                return result
            if isinstance(value, list):
                return [metadata(child) for child in value]
            return value
        filtered = metadata(output)
        if isinstance(filtered, dict):
            filtered.update(verification_scope=scope,
                            semantic_verified=False, raw_content_retained=False, provider_sent=False)
        return filtered, metadata(evidence), 'ARTIFACT_INSPECTION_FAILED: no se pudo comprobar el archivo; el diagnóstico de contenido no se conserva.' if error else error

    def _measure(self, task, kind, wall_ms, cpu_ms=None):
        if not math.isfinite(wall_ms) or wall_ms < 0:
            return
        self.db.execute('INSERT INTO anticipation_measurements(task_id,kind,at,wall_ms,cpu_ms) VALUES (?,?,?,?,?)',
                        (task, kind, self.clock(), wall_ms, cpu_ms))
        self.db.execute('DELETE FROM anticipation_measurements WHERE id NOT IN (SELECT id FROM anticipation_measurements ORDER BY id DESC LIMIT 512)')

    def _metrics(self, stats, task_id=None):
        measurements = self.db.execute('SELECT kind,wall_ms,cpu_ms FROM anticipation_measurements' + (' WHERE task_id=?' if task_id else ''), (task_id,) if task_id else ()).fetchall()
        def distribution(values):
            values = sorted(value for value in values if value is not None)
            return {'samples': len(values), **{name: values[max(0, math.ceil(len(values) * percentile) - 1)] if values else None
                    for name, percentile in (('p50', .5), ('p95', .95))}}
        fields = ('eligible', 'evaluated_proposed', 'proposed', 'shown', 'verified', 'failed', 'abstained', 'explicit_acceptances', 'autonomous_executions', 'explicit_useful_feedback', 'explicit_corrections')
        metrics = {key: sum(row.get(key, 0) for row in stats) for key in fields}
        metrics.update(model_calls=0, coverage={'numerator': metrics['evaluated_proposed'], 'denominator': metrics['eligible'], 'universe': 'Candidates evaluated since P1 eligibility counters were introduced.'},
            verification_latency_ms=distribution([row['wall_ms'] for row in measurements if row['kind'] == 'verification']),
            tick_latency_ms=distribution([row['wall_ms'] for row in measurements if row['kind'] == 'tick']),
            tick_cpu_ms=distribution([row['cpu_ms'] for row in measurements if row['kind'] == 'tick']),
            measurement_window_max=512, cpu_basis='Process CPU delta during tick; concurrent threads included, child-process CPU excluded.')
        return metrics

    def _source_target(self, target_id, config=None):
        config = config or self._config()
        for target in config['observation_targets']:
            source = 'folders' if target['source'] == 'folder' else 'applications'
            if (target['id'] == target_id and target['observe'] and config['sources'][source]
                    and (target['expires_at'] is None or self.clock() < target['expires_at'])
                    and (source != 'applications' or self._applications_available())):
                return target
        return None

    def _source_authorized(self, item, config=None):
        target_id = item['plan'].get('source_target_id')
        if not target_id:
            return True
        target = self._source_target(target_id, config)
        return bool(target and target['source'] == 'folder' and target['retain']
            and digest(target) == item['plan'].get('source_authorization_hash')
            and target['task_id'] == item['task_id']
            and self._source_context(target) == item['plan'].get('context')
            and Path(item['plan']['inputs']['path']).is_relative_to(Path(target['root'])))

    @staticmethod
    def _source_context(target):
        return {key: target.get(key, '') for key in CONTEXT_KEYS} | {
            'source': 'folders' if target['source'] == 'folder' else 'applications'}

    def _source_runtime(self, config, task_id=None):
        result = []
        for target in config['observation_targets']:
            if task_id is not None and target['task_id'] != task_id:
                continue
            state = self.source_state.get(target['id'], {})
            _, options = self._policy(target['task_id'], target.get('root', str(self.commands.executor.workspace_root)), config, self._source_context(target))
            active = self._source_target(target['id'], config) is not None and options['mode'] != 'OFF'
            last = state.get('last_observed_at')
            result.append({'id': target['id'], 'source': target['source'], 'active': active and not state.get('error'),
                'last_observed_at': last, 'next_observation_at': last + options.get('cadence_seconds', 30) if active and last is not None else None,
                'error': state.get('error') or (None if active else 'Fuente desactivada, fuera de ámbito/horario o autorización caducada.'),
                'metadata_retained': target['retain'], 'provider_sent': False, 'baseline': state.get('snapshot') is not None,
                'truncated': state.get('truncated', False), 'samples': state.get('samples', 0), 'events': state.get('events', 0)})
        return result

    def _folder_snapshot(self, target, options):
        root = directory(target['root'])
        snapshot, truncated = {}, False
        with os.scandir(root) as entries:
            for index, entry in enumerate(entries):
                if index >= options['resources']['max_entries_scan'] or not self._within_budget(options):
                    truncated = True
                    break
                try:
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if getattr(info, 'st_file_attributes', 0) & (0x400 | 0x1000 | 0x40000 | 0x400000):
                        truncated = True
                        continue
                    path = str(Path(root) / entry.name)
                    if artifact_path_error(path):
                        truncated = True
                        continue
                    snapshot[path] = {'path': path, 'size': info.st_size, 'identity_hash': digest(fingerprint(info))}
                except OSError:
                    truncated = True
        return snapshot, truncated

    def _application_snapshot(self, target, options):
        from .actions import windows_automation as windows
        if not self._applications_available():
            raise ValueError('El lector de aplicaciones Windows no está disponible')
        snapshot, names, truncated = {}, {}, False
        for index, row in enumerate(windows.list_windows(include_untitled=True, include_titles=False)):
            if index >= options['resources']['max_entries_scan'] or not self._within_budget(options):
                truncated = True
                break
            pid = row['pid']
            if pid not in names:
                names[pid] = windows.process_name(pid).casefold()
            if names[pid] != target['process_name']:
                continue
            birth = windows.process_started(pid)
            key = digest([row['window_id'], pid, birth])
            snapshot[key] = {'process_name': names[pid], 'window_id': row['window_id'], 'pid': pid, 'foreground': row.get('foreground') is True}
        return snapshot, truncated

    def _poll_sources(self):
        with self.lock:
            targets = copy.deepcopy(self._config()['observation_targets'])
        for target in targets:
            context = self._source_context(target)
            path = target.get('root', str(self.commands.executor.workspace_root))
            with self.lock:
                current = self._source_target(target['id'])
                profile, options = self._policy(target['task_id'], path, context=context)
                if current is None or options['mode'] == 'OFF':
                    self.source_state.pop(target['id'], None)
                    self.source_observations = [event for event in self.source_observations if event['target_id'] != target['id']]
                    continue
                state = self.source_state.setdefault(target['id'], {'snapshot': None, 'samples': 0, 'events': 0})
                if self.clock() - state.get('last_observed_at', float('-inf')) < options['cadence_seconds'] or not self._within_budget(options):
                    continue
            try:
                snapshot, truncated = (self._folder_snapshot(target, options) if target['source'] == 'folder'
                                       else self._application_snapshot(target, options))
                error = None
            except (OSError, ValueError) as exc:
                snapshot, truncated, error = {}, True, str(exc)[:300]
            with self.lock, self.db:
                if self._source_target(target['id']) != target:
                    continue
                profile, options = self._policy(target['task_id'], path, context=context)
                if options['mode'] == 'OFF':
                    continue
                state.update(last_observed_at=self.clock(), samples=state['samples'] + 1, truncated=truncated, error=error)
                if error:
                    continue
                before = state['snapshot']
                if before is None:
                    state['snapshot'] = snapshot
                    continue
                changes = [(key, value, 'file.created' if target['source'] == 'folder' else 'application.opened')
                           for key, value in snapshot.items() if key not in before]
                changes += [(key, value, 'file.modified' if target['source'] == 'folder' else 'application.foreground')
                            for key, value in snapshot.items() if key in before and before[key] != value]
                if not truncated:
                    changes += [(key, value, 'file.deleted' if target['source'] == 'folder' else 'application.closed')
                                for key, value in before.items() if key not in snapshot]
                state['truncated'] = truncated or len(changes) > options['resources']['max_events_tick']
                for key, resource, kind in changes[:options['resources']['max_events_tick']]:
                    if not self._within_budget(options) or not self._take_event_budget(profile, options):
                        state['truncated'] = True
                        break
                    stamp = int(self.clock() // options['cadence_seconds'])
                    event_id = 'observation-' + digest([target['id'], kind, resource, stamp])
                    event = {'event_id': event_id, 'type': kind, 'task_id': target['task_id'], 'source': context['source'],
                        'target_id': target['id'], 'observed_at': self.clock(), 'resource': resource, 'context': context,
                        'source_authorization_hash': digest(target),
                        'retained': target['retain'], 'sent_to_provider': False, 'profile': profile, 'at': self.clock(),
                        'provenance': {'actor': 'system', 'origin': 'metadata_observation', 'causation_id': target['id'], 'human_preference_evidence': False}}
                    self.source_observations = (self.source_observations + [event])[-20:]
                    state['events'] += 1
                    if kind.endswith(('deleted', 'closed')):
                        before.pop(key, None)
                    else:
                        before[key] = resource
                    if target['retain']:
                        inserted = self.db.execute('INSERT OR IGNORE INTO anticipation_events VALUES (?,?,?,?)',
                            (event_id, target['task_id'], self.clock(), canonical(event))).rowcount
                        if inserted and target['source'] == 'folder' and kind != 'file.deleted':
                            candidate = event | {'path': resource['path'], 'sha256': None}
                            try:
                                self._propose(candidate, profile, options)
                            except (OSError, ValueError):
                                self._stats(target['task_id'], ROUTINE, 'abstained')
                state['snapshot'] = dict(list(before.items())[:options['resources']['max_entries_scan']])

    def status(self, task_id=None):
        with self.lock:
            config = self._config()
            rows = self._items(task_id)[:100]
            for item in rows:
                effective, options = self._policy(item['task_id'], item['plan']['inputs']['path'], config, item['plan'].get('context'))
                item['visible'] = self._visible(item, options)
                item.update(effective_profile=effective, options=options, policy=options)
            grants = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM anticipation_grants')]
            if task_id is not None:
                grants = [grant for grant in grants if grant['task_id'] == task_id]
            stats = [dict(task_id=row['task_id'], routine_id=row['routine_id'], **json.loads(row['payload']))
                     for row in self.db.execute('SELECT * FROM anticipation_stats' + (' WHERE task_id=?' if task_id else ''), (task_id,) if task_id else ())]
            effective = config['profile']
            if task_id:
                scoped = [scope for scope in config['scopes'] if not scope.get('task_id') or scope['task_id'] == task_id]
                names = {scope['profile'] for scope in scoped if scope.get('profile')}
                if any(scope.get('root') or scope.get('exclude') for scope in scoped) or len(names) > 1:
                    effective = None
                elif names:
                    effective = next(iter(names))
            return config | {'effective_profile': effective, 'suggestions': rows, 'grants': grants, 'routines': stats,
                'metrics': self._metrics(stats, task_id),
                'source_runtime': self._source_runtime(config, task_id),
                'source_observations': [copy.deepcopy(event) for event in self.source_observations if task_id is None or event['task_id'] == task_id],
                'capabilities': {'verify_artifact': self._can_verify(), 'physical_execution': False,
                    'folders': True, 'applications': self._applications_available(), 'provider_send': False,
                    'verifiers': {name: self._verifier(path) for name, path in {'hash': 'file.txt', 'pdf': 'file.pdf', 'media': 'file.mp4', 'image': 'file.png', 'docx': 'file.docx', 'xlsx': 'file.xlsx'}.items()},
                    'resource_limits_scope': 'Periodic observation and admission; each registered tool retains its own execution deadline.',
                    'screen': False, 'microphone': False, 'clipboard': False,
                    'reason': 'M15 abierto: input físico proactivo bloqueado. Carpetas y aplicaciones solo producen metadatos locales autorizados; pantalla, micrófono y portapapeles siguen inactivos.'}}

    def configure(self, body):
        if not isinstance(body, dict) or set(body) - set(DEFAULTS):
            raise ValueError('Configuración de anticipación desconocida')
        # Classify already generated artifacts under the policy in force when changing it.
        self._observe()
        with self.lock, self.db:
            config = self._config()
            if 'profile' in body:
                if body['profile'] not in PROFILES:
                    raise ValueError('Perfil inválido')
                config['profile'] = body['profile']
            for key in ('paused', 'observation_paused'):
                if key in body:
                    if type(body[key]) is not bool:
                        raise ValueError('La pausa debe ser booleana')
                    config[key] = body[key]
            if 'sources' in body:
                if not isinstance(body['sources'], dict) or set(body['sources']) - set(config['sources']):
                    raise ValueError('Fuente desconocida')
                for source, enabled in body['sources'].items():
                    if type(enabled) is not bool or source not in ('events', 'folders', 'applications') and enabled:
                        raise ValueError('Esta fuente todavía no dispone de observación validada')
                    if source == 'applications' and enabled and not self._applications_available():
                        raise ValueError('La observación de aplicaciones requiere el lector Windows existente')
                    config['sources'][source] = enabled
            if 'profiles' in body:
                if not isinstance(body['profiles'], dict) or set(body['profiles']) - set(PROFILES):
                    raise ValueError('Perfil desconocido')
                for name, changes in body['profiles'].items():
                    if not isinstance(changes, dict) or set(changes) - set(DEFAULTS['profiles'][name]):
                        raise ValueError('Ajuste de perfil desconocido')
                    options = config['profiles'][name] | changes
                    if options['mode'] not in MODES or options['interruptions'] not in ('silent', 'cards', 'voice', 'cards_voice'):
                        raise ValueError('Modo o interrupción inválidos')
                    for key, minimum, maximum in (('cooldown_seconds', 0, 86400), ('max_interruptions_hour', 0, 60), ('retention_days', 1, 365)):
                        if type(options[key]) is not int or not minimum <= options[key] <= maximum:
                            raise ValueError('Límite de perfil inválido: ' + key)
                    if type(options['cadence_seconds']) is not int or not 5 <= options['cadence_seconds'] <= 3600:
                        raise ValueError('La cadencia debe ser de 5 a 3600 segundos')
                    resources = changes.get('resources', {})
                    if not isinstance(resources, dict) or set(resources) - set(RESOURCE_LIMITS):
                        raise ValueError('Límite de recursos desconocido')
                    options['resources'] = config['profiles'][name]['resources'] | resources
                    for key, (minimum, maximum) in RESOURCE_LIMITS.items():
                        if type(options['resources'][key]) is not int or not minimum <= options['resources'][key] <= maximum:
                            raise ValueError('Límite de recursos inválido: ' + key)
                    schedule = options['schedule']
                    if schedule is not None:
                        if (not isinstance(schedule, dict) or set(schedule) != {'timezone', 'days', 'start', 'end'}
                                or not isinstance(schedule['timezone'], str) or len(schedule['timezone']) > 80
                                or not isinstance(schedule['days'], list) or not 1 <= len(schedule['days']) <= 7
                                or any(type(day) is not int or not 0 <= day <= 6 for day in schedule['days'])
                                or len(set(schedule['days'])) != len(schedule['days'])
                                or any(not isinstance(schedule[key], str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', schedule[key]) for key in ('start', 'end'))):
                            raise ValueError('Horario inválido: zona IANA, días 0–6 y horas HH:MM')
                        try:
                            ZoneInfo(schedule['timezone'])
                        except (ZoneInfoNotFoundError, ValueError) as exc:
                            raise ValueError('La zona horaria IANA solicitada no está disponible en este Python') from exc
                    config['profiles'][name] = options
            if 'scopes' in body:
                if not isinstance(body['scopes'], list) or len(body['scopes']) > 64:
                    raise ValueError('Ámbitos inválidos')
                scopes = []
                for raw in body['scopes']:
                    if not isinstance(raw, dict) or set(raw) - {'task_id', 'root', 'profile', 'exclude', *CONTEXT_KEYS} or not any(raw.get(key) for key in ('task_id', 'root', *CONTEXT_KEYS)):
                        raise ValueError('Indica tarea, carpeta, proyecto, aplicación o dispositivo del ámbito')
                    scope = copy.deepcopy(raw)
                    if scope.get('task_id'):
                        identifier(scope['task_id'], 'Tarea')
                    for key in CONTEXT_KEYS:
                        if key in scope:
                            scope_identifier(scope[key], key)
                    if scope.get('root'):
                        scope['root'] = directory(scope['root'])
                    if scope.get('profile') not in (None, *PROFILES) or type(scope.get('exclude', False)) is not bool:
                        raise ValueError('Política de ámbito inválida')
                    if not scope.get('profile') and not scope.get('exclude'):
                        raise ValueError('El ámbito debe seleccionar un perfil o excluir')
                    scopes.append(scope)
                config['scopes'] = scopes
            if 'observation_targets' in body:
                targets = body['observation_targets']
                if not isinstance(targets, list) or len(targets) > 32:
                    raise ValueError('Selecciona hasta 32 fuentes explícitas')
                checked, ids = [], set()
                for raw in targets:
                    allowed = {'id', 'source', 'task_id', *CONTEXT_KEYS, 'root', 'process_name', 'observe', 'retain', 'send_to_provider', 'expires_at'}
                    if not isinstance(raw, dict) or set(raw) - allowed or raw.get('source') not in ('folder', 'application'):
                        raise ValueError('Fuente seleccionada inválida')
                    target = copy.deepcopy(raw)
                    identifier(target.get('id'), 'Fuente')
                    identifier(target.get('task_id'), 'Tarea')
                    if target['id'] in ids:
                        raise ValueError('Identificador de fuente duplicado')
                    ids.add(target['id'])
                    for key in CONTEXT_KEYS:
                        target.setdefault(key, 'host' if key == 'device_id' else '')
                        if not isinstance(target[key], str):
                            raise ValueError('El ámbito de observación debe usar identificadores de texto')
                        if key == 'device_id' and not target[key]:
                            target[key] = 'host'
                        if target[key]:
                            scope_identifier(target[key], key)
                    if target['device_id'] != 'host':
                        raise ValueError('Estas fuentes solo observan el host local; no hay un observador remoto autorizado')
                    for key in ('observe', 'retain', 'send_to_provider'):
                        target.setdefault(key, False)
                        if type(target[key]) is not bool:
                            raise ValueError('Los consentimientos deben ser booleanos independientes')
                    if target['send_to_provider']:
                        raise ValueError('Envío a proveedores no implementado para estas fuentes; no se autorizará implícitamente')
                    target.setdefault('expires_at', None)
                    expiry = target['expires_at']
                    preserved_expiry = any(old['id'] == target['id'] and old.get('expires_at') == expiry for old in config['observation_targets'])
                    if expiry is not None and (type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry <= self.clock() and not preserved_expiry):
                        raise ValueError('Vigencia de observación inválida')
                    if target['source'] == 'folder':
                        if 'process_name' in target:
                            raise ValueError('Una carpeta no selecciona un proceso')
                        target['root'] = directory(target.get('root'))
                    else:
                        process = target.get('process_name')
                        if ('root' in target or not isinstance(process, str) or not 5 <= len(process) <= 80 or not process.casefold().endswith('.exe')
                                or process != process.strip() or any(ord(char) < 32 or char in '<>:"|?*/\\' for char in process)):
                            raise ValueError('Selecciona un nombre de proceso .exe exacto')
                        target['process_name'] = target['process_name'].casefold()
                        target['application_id'] = target['application_id'] or target['process_name']
                    checked.append(target)
                config['observation_targets'] = checked
            self.db.execute('UPDATE anticipation_config SET payload=? WHERE id=1', (canonical(config),))
            self.source_state.clear()
            self.source_observations.clear()
            cancelled = self._invalidate(config)
        self._cancel_commands(cancelled)
        return self.status()

    def _invalidate(self, config=None):
        cancelled = []
        for item in self._items():
            if item['state'] not in (*PENDING, 'EXECUTING'):
                continue
            _, options = self._policy(item['task_id'], item['plan']['inputs']['path'], config, item['plan'].get('context'))
            old_mode = item.get('admitted_mode', 'SUGGEST')
            invalid = MODES.index(options['mode']) < MODES.index(old_mode)
            if not self._source_authorized(item, config):
                invalid = True
            if item.get('candidate_kind', 'verify_artifact') != 'verify_artifact' and not self._preparation_scope_allowed(item['task_id'], config):
                invalid = True
            if item.get('approval') == 'persistent' and not self._grant(item):
                invalid = True
            if invalid:
                item.update(state='CANCELLED', message='La política o autorización cambió; la iniciativa no se reactivará.', cancel_requested=True)
                self._save(item)
                self._transition(item, 'CANCELLED')
                cancelled.append(item['operation_id'])
        return cancelled

    def _cancel_commands(self, operation_ids):
        # Never hold the policy lock while acquiring CommandService's lock.
        for key in operation_ids:
            self.commands.cancel(key)

    def grant(self, body):
        if not isinstance(body, dict) or set(body) - {'task_id', 'capability', 'root', 'expires_at', 'observe_events'}:
            raise ValueError('Autorización desconocida')
        task = identifier(body.get('task_id'), 'Tarea')
        if body.get('capability') != CAPABILITY or body.get('observe_events', True) is not True:
            raise ValueError('Solo se admite verificación de artefactos y sus eventos autorizados')
        root = directory(body.get('root'))
        if not Path(root).is_relative_to(self.commands.executor.workspace_root):
            raise ValueError('El permiso debe permanecer dentro de la carpeta de artefactos de Axx')
        expiry = body.get('expires_at')
        if expiry is not None and (type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry <= self.clock()):
            raise ValueError('Vigencia inválida')
        grant = {'grant_id': uuid.uuid4().hex, 'task_id': task, 'capability': CAPABILITY,
                 'root': root, 'expires_at': expiry, 'observe_events': True, 'revoked': False, 'created_at': self.clock()}
        with self.lock, self.db:
            self.db.execute('INSERT INTO anticipation_grants VALUES (?,?)', (grant['grant_id'], canonical(grant)))
        return grant

    def revoke(self, grant_id):
        identifier(grant_id)
        with self.lock, self.db:
            row = self.db.execute('SELECT payload FROM anticipation_grants WHERE grant_id=?', (grant_id,)).fetchone()
            if not row:
                raise ValueError('Autorización desconocida')
            grant = json.loads(row[0]) | {'revoked': True, 'revoked_at': self.clock()}
            self.db.execute('UPDATE anticipation_grants SET payload=? WHERE grant_id=?', (canonical(grant), grant_id))
            cancelled = self._invalidate()
        self._cancel_commands(cancelled)
        return grant

    def _observe(self):
        with self.lock:
            placeholders = ','.join('?' for _ in ARTIFACT_GENERATORS)
            rows = self.db.execute("""SELECT o.operation_id,o.result_json,c.result_json AS command_json
                FROM operations o JOIN command_runs c ON json_extract(c.result_json,'$.action_operation_id')=o.operation_id
                WHERE o.tool_name IN (""" + placeholders + """) AND o.state='succeeded' AND c.state='succeeded'
                AND NOT EXISTS (SELECT 1 FROM anticipation_seen s WHERE s.operation_id=o.operation_id)
                ORDER BY o.created_at LIMIT 100""", ARTIFACT_GENERATORS).fetchall()
        for row in rows:
            with self.lock, self.db:
                config = self._config()
                if not self._within_budget(config['profiles'][config['profile']]):
                    break
                receipt, command = json.loads(row['result_json']), json.loads(row['command_json'])
                output = receipt.get('output') or {}
                files = [candidate for candidate in ([output] + (output.get('files') or [])) if isinstance(candidate, dict)
                         and isinstance(candidate.get('path'), str) and isinstance(candidate.get('sha256'), str)]
                # One additional check per generation: prefer the PDF copy when an Office output contains several files.
                if files:
                    output = min(files, key=lambda candidate: (Path(candidate['path']).suffix.casefold() != '.pdf', candidate['path']))
                task = command.get('conversation_id') or command['operation_id']
                path = output.get('path')
                if (receipt.get('postconditions_passed') is not True or not isinstance(path, str)
                        or not re.fullmatch('[a-f0-9]{64}', output.get('sha256', ''))):
                    self.db.execute('INSERT OR IGNORE INTO anticipation_seen VALUES (?,?)', (row['operation_id'], self.clock()))
                    continue
                context = self._command_context(command)
                profile, options = self._policy(task, path, context=context)
                if options['mode'] != 'OFF' and not self._take_event_budget(profile, options):
                    break
                inserted = self.db.execute('INSERT OR IGNORE INTO anticipation_seen VALUES (?,?)', (row['operation_id'], self.clock())).rowcount
                if not inserted:
                    continue
                if options['mode'] == 'OFF' or not Path(path).is_relative_to(self.commands.executor.workspace_root):
                    continue
                event = {'event_id': 'artifact-' + row['operation_id'], 'type': 'artifact.generated', 'task_id': task,
                    'source_operation_id': row['operation_id'], 'path': path, 'sha256': output['sha256'], 'at': self.clock(),
                    'profile': profile, 'retention_days': options['retention_days'],
                    'context': context,
                    'provenance': self._command_provenance(command), 'outcome': 'verified', 'feedback': 'none'}
                self.db.execute('INSERT OR IGNORE INTO anticipation_events VALUES (?,?,?,?)', (event['event_id'], task, self.clock(), canonical(event)))
                try:
                    self._propose(event, profile, options)
                except OSError:
                    self._stats(task, ROUTINE, 'unavailable_abstentions')
                    self._stats(task, ROUTINE, 'abstained')

    def _command_context(self, command):
        context = {'source': 'events', 'device_id': 'host'}
        if self.commands.learning:
            row = self.db.execute("""SELECT payload FROM learning_plans p WHERE EXISTS
                (SELECT 1 FROM json_each(json_extract(p.payload,'$.step_records')) r
                 WHERE json_extract(r.value,'$.operation_id')=?) LIMIT 1""", (command['operation_id'],)).fetchone()
            if row:
                plan = json.loads(row[0])
                context['project_id'] = plan.get('project_id', '')
        return context

    def _command_provenance(self, command):
        provenance = {'actor': 'axx', 'origin': 'direct_instruction',
            'causation_id': command['operation_id'], 'command_source': command.get('source'),
            'human_preference_evidence': False}
        if self.commands.learning:
            row = self.db.execute("""SELECT payload FROM learning_plans p WHERE EXISTS
                (SELECT 1 FROM json_each(json_extract(p.payload,'$.step_records')) r
                 WHERE json_extract(r.value,'$.operation_id')=?) LIMIT 1""", (command['operation_id'],)).fetchone()
            if row:
                plan = json.loads(row[0])
                provenance['learning_plan_id'] = plan['operation_id']
                linked = self.db.execute("SELECT suggestion_id FROM anticipation_suggestions WHERE json_extract(payload,'$.learning_plan_id')=? LIMIT 1", (plan['operation_id'],)).fetchone()
                if plan['operation_id'].startswith('ant-plan-') or linked or self._initiated_plan(plan['operation_id']):
                    provenance.update(origin='suggestion_accepted', causation_id=linked[0] if linked else plan['operation_id'])
        own = self.db.execute("SELECT suggestion_id,payload FROM anticipation_suggestions WHERE json_extract(payload,'$.operation_id')=? LIMIT 1", (command['operation_id'],)).fetchone()
        if own:
            source = json.loads(own['payload'])
            provenance.update(origin='autonomous_routine' if source.get('approval') == 'persistent' else 'suggestion_accepted', causation_id=own['suggestion_id'])
        return provenance

    def _propose(self, event, profile, options):
        verifier = self._verifier(event['path'])
        identity = list(fingerprint(Path(event['path']).stat()))
        # Journal receipts and an opted-in folder can describe the same generation.
        # The UNIQUE dedupe column arbitrates their resource identity across processes.
        key = digest({'path': os.path.normcase(event['path']), 'identity': identity, 'task': event['task_id'],
                      'command': verifier['command_id'], 'verifier_version': verifier['version']})
        existing = self.db.execute("""SELECT payload FROM anticipation_suggestions WHERE
            dedupe_key=? OR (task_id=? AND routine_id=? AND json_extract(payload,'$.plan.inputs.path')=?
            AND json_extract(payload,'$.plan.command_id')=? AND json_extract(payload,'$.plan.expected_identity')=?) LIMIT 1""",
            (key, event['task_id'], ROUTINE, event['path'], verifier['command_id'], canonical(identity))).fetchone()
        if existing:
            return json.loads(existing[0])
        self._stats(event['task_id'], ROUTINE, 'eligible')
        previous = self.db.execute('SELECT MAX(at) FROM anticipation_suggestions WHERE task_id=? AND routine_id=?', (event['task_id'], ROUTINE)).fetchone()[0]
        if (not verifier['available'] or self._suppressed(event['task_id'], ROUTINE)
                or identity[2] > options['resources']['max_file_bytes']
                or previous is not None and self.clock() - previous < options['cooldown_seconds']):
            self._stats(event['task_id'], ROUTINE, 'abstained')
            return None
        plan = {'version': 1, 'command_id': verifier['command_id'], 'inputs': {'path': event['path']},
                'expected_sha256': event.get('sha256'), 'expected_identity': identity,
                'source_operation_id': event.get('source_operation_id'), 'task_id': event['task_id'],
                'context': event.get('context', {}), 'source_target_id': event.get('target_id'),
                'source_authorization_hash': event.get('source_authorization_hash'),
                'verification_scope': verifier['verification_scope'], 'verifier_version': verifier['version'],
                'verification_basis': 'generation_receipt' if event.get('sha256') else 'observed_file_snapshot'}
        context_fingerprint = digest({'path': event['path'], 'sha256': event.get('sha256'), 'identity': identity, 'task_id': event['task_id']})
        sid = 'anticipation-' + key[:32]
        mode = options['mode']
        item = {'suggestion_id': sid, 'candidate_kind': 'verify_artifact', 'task_id': event['task_id'], 'routine_id': ROUTINE, 'routine_version': 1,
            'title': 'Comprobar el archivo observado' if event.get('target_id') else 'Verificar el archivo generado',
            'verification_scope': verifier['verification_scope'], 'semantic_verified': False, 'verifier_reason': verifier['reason'],
            'state': 'DETECTED' if mode == 'SHADOW' else 'PREPARED' if mode == 'PREPARE' else 'AWAITING_APPROVAL',
            'plan': plan, 'plan_hash': digest(plan), 'context_fingerprint': context_fingerprint,
            'operation_id': 'ant-' + key[:48], 'profile': profile, 'admitted_mode': mode, 'shadow': mode == 'SHADOW',
            'context_state': 'observed',
            'created_at': self.clock(), 'expires_at': self.clock() + 300, 'result': None, 'error': None,
            'assessment': {'likelihood': {'score': 1, 'method': 'registered_generated_artifact_rule'},
                'capability': verifier,
                'authorization': {'allowed': False, 'required': CAPABILITY}},
            'provenance': event['provenance'],
            'initiative_chain': {'root_event_id': event['event_id'], 'depth': 1, 'budget': 1, 'stop_condition': 'verification_terminal'},
            'feedback': {'acceptance': 'none', 'usefulness': 'unknown', 'corrections': 0},
            'message': 'Comprobación disponible: ' + verifier['verification_scope'] + '. No acredita corrección semántica ni calidad visual.'}
        item['action_operation_id'] = 'cmd-' + hashlib.sha256(item['operation_id'].encode()).hexdigest()
        if mode == 'EXECUTE' and (grant := self._grant(item)):
            item.update(approval='persistent', grant_id=grant['grant_id'])
        inserted = self.db.execute('INSERT OR IGNORE INTO anticipation_suggestions VALUES (?,?,?,?,?,?,?,?)',
            (sid, key, item['task_id'], ROUTINE, item['state'], item['plan_hash'], self.clock(), canonical(item))).rowcount
        if inserted:
            self.db.execute('INSERT OR IGNORE INTO anticipation_privacy VALUES (?,?,?)',
                            (item['action_operation_id'], verifier['verification_scope'], self.clock()))
            self._stats(item['task_id'], ROUTINE, 'proposed')
            self._stats(item['task_id'], ROUTINE, 'evaluated_proposed')
            self._transition(item, 'DETECTED', {'event_id': event['event_id']})
            if mode == 'PREPARE':
                self._transition(item, 'PREPARED', {'isolated_plan_only': True})
        return item

    @staticmethod
    def _checkpoint(plan):
        records = plan.get('step_records') or []
        last = -1
        for index, record in enumerate(records):
            result = record.get('result') or {}
            if result.get('state') != 'succeeded' or result.get('postconditions_passed') is not True:
                break
            last = index
        return {'last_verified_step': last, 'next_step': last + 1,
                'records_hash': digest([{'operation_id': record.get('operation_id'), 'state': record.get('state'),
                    'verified': (record.get('result') or {}).get('postconditions_passed') is True} for record in records])}

    def _preparation_scope_allowed(self, task, config=None):
        # shortcut: multi-resource plans use task scopes; enable folder scopes after resolving every target.
        return not any(scope.get('root') and (not scope.get('task_id') or scope['task_id'] == task)
                       for scope in (config or self._config())['scopes'])

    def _initiated_plan(self, plan_id):
        return self.db.execute('SELECT 1 FROM anticipation_seen WHERE operation_id=?',
                               ('initiated-learning-' + digest(plan_id),)).fetchone() is not None

    def _preparation_candidate(self, task, routine, title, plan, profile, options, evidence):
        if self._suppressed(task, routine):
            return
        key = digest({'task_id': task, 'routine_id': routine, 'plan': plan})
        if self.db.execute('SELECT 1 FROM anticipation_seen WHERE operation_id=?', ('preparation-' + key,)).fetchone():
            return
        if self.db.execute('SELECT 1 FROM anticipation_suggestions WHERE dedupe_key=?', (key,)).fetchone():
            return
        if self.db.execute("SELECT 1 FROM anticipation_suggestions WHERE task_id=? AND routine_id=? AND state IN ('DETECTED','AWAITING_APPROVAL','EXECUTING') LIMIT 1", (task, routine)).fetchone():
            return
        last = self.db.execute('SELECT MAX(at) FROM anticipation_suggestions WHERE task_id=? AND routine_id=?', (task, routine)).fetchone()[0]
        if last is not None and self.clock() - last < options['cooldown_seconds']:
            return
        if not self._within_budget(options) or not self._take_event_budget(profile, options):
            return
        kind = plan['kind']
        sid = 'anticipation-' + key[:32]
        item = {'suggestion_id': sid, 'candidate_kind': kind, 'task_id': task, 'routine_id': routine,
            'routine_version': plan.get('skill_version', 1), 'title': title, 'plan': plan, 'plan_hash': digest(plan),
            'state': 'DETECTED' if options['mode'] == 'SHADOW' else 'AWAITING_APPROVAL',
            'profile': profile, 'admitted_mode': options['mode'], 'shadow': options['mode'] == 'SHADOW',
            'operation_id': 'ant-' + key[:48], 'created_at': self.clock(), 'expires_at': self.clock() + 300,
            'result': None, 'error': None, 'preparation_complete': False,
            'context_state': 'inferred',
            'context_fingerprint': digest(evidence), 'evidence': evidence,
            'provenance': {'actor': 'axx', 'origin': 'suggestion', 'causation_id': plan['learning_operation_id'], 'human_preference_evidence': False},
            'feedback': {'acceptance': 'none', 'usefulness': 'unknown', 'corrections': 0},
            'message': 'Prepararé el plan existente para que lo revises; no ejecutaré sus acciones.',
            'assessment': {'likelihood': {'score': 1, 'method': 'verified_checkpoint' if kind == 'resume_task' else 'repeated_verified_skill', 'evidence_count': len(evidence)},
                'capability': {'available': True, 'method': 'ActionLearning.resume' if kind == 'resume_task' else 'ActionLearning.prepare_steps'},
                'authorization': {'allowed': False, 'required': 'prepare_existing_plan'}}}
        inserted = self.db.execute('INSERT OR IGNORE INTO anticipation_suggestions VALUES (?,?,?,?,?,?,?,?)',
            (sid, key, task, routine, item['state'], item['plan_hash'], self.clock(), canonical(item))).rowcount
        if inserted:
            self._stats(task, routine, 'eligible')
            self.db.execute('INSERT OR IGNORE INTO anticipation_seen VALUES (?,?)', ('preparation-' + key, self.clock()))
            self._stats(task, routine, 'proposed')
            self._stats(task, routine, 'evaluated_proposed')
            self._transition(item, 'DETECTED', {'candidate_kind': kind})

    def _observe_preparations(self):
        learning = self.commands.learning
        if learning is None or learning.closed or learning.closing:
            return
        with self.lock:
            plans = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM learning_plans')]
        groups = {}
        for source in plans:
            task = source.get('conversation_id') or source['operation_id']
            path = str(self.commands.executor.workspace_root)
            context = {'source': 'events', 'project_id': source.get('project_id', ''), 'device_id': 'host'}
            with self.lock:
                if not self._preparation_scope_allowed(task):
                    continue
                profile, options = self._policy(task, path, context=context)
            if options['mode'] == 'OFF' or not self._within_budget(options) or source.get('preparation_complete') is False:
                continue
            if source.get('state') in ('paused', 'interrupted'):
                checkpoint = self._checkpoint(source)
                with self.lock:
                    forgotten = self._forgotten_source(task, 'resume_incomplete_task', source)
                if not forgotten and checkpoint['last_verified_step'] >= 0 and checkpoint['next_step'] < len(source.get('steps', [])):
                    plan = {'kind': 'resume_task', 'inputs': {'path': path}, 'task_id': task, 'context': context,
                            'learning_operation_id': source['operation_id'], 'source_plan_hash': source.get('plan_hash'), **checkpoint}
                    with self.lock, self.db:
                        self._preparation_candidate(task, 'resume_incomplete_task', 'Preparar reanudación de la tarea', plan, profile, options,
                            [{'operation_id': source['operation_id'], **checkpoint}])
            if source.get('state') != 'succeeded' or source.get('postconditions_passed') is not True:
                continue
            with self.lock:
                initiated = self.db.execute("SELECT 1 FROM anticipation_suggestions WHERE json_extract(payload,'$.learning_plan_id')=? LIMIT 1", (source['operation_id'],)).fetchone()
            with self.lock:
                initiated = initiated or self._initiated_plan(source['operation_id'])
            if (source['operation_id'].startswith('ant-plan-') or initiated
                    or source.get('origin') in ('anticipation', 'autonomous_routine', 'suggestion_accepted')):
                continue
            for ref in source.get('skill_versions', []):
                with self.lock:
                    if self._forgotten_source(task, 'repeat.' + ref['id'], source):
                        continue
                records = source.get('step_records', [])[ref['step_start']:ref['step_start'] + ref['step_count']]
                if not records or not all((record.get('result') or {}).get('state') == 'succeeded'
                    and (record.get('result') or {}).get('postconditions_passed') is True
                    and (record.get('result') or {}).get('evidence') for record in records):
                    continue
                key = (task, ref['id'], ref['version'], digest(ref['inputs']))
                groups.setdefault(key, []).append((source, ref, profile, options))
        for (task, skill_id, version, inputs_hash), occurrences in groups.items():
            if len({source['operation_id'] for source, *_ in occurrences}) < 3:
                continue
            source, ref, profile, options = max(occurrences, key=lambda entry: entry[0].get('updated_at', entry[0].get('created_at', 0)))
            if not self._within_budget(options):
                continue
            try:
                skill = learning.skills.get(skill_id, version, project_id=source.get('project_id', ''), task_id=task)
                if not skill.get('environment_matches') or not skill.get('effect_verified'):
                    continue
                from .memory.skill_memory import bind
                steps, _ = bind(skill, ref['inputs'], {})
                learning._validate_steps(steps)
            except (ValueError, KeyError, TypeError):
                continue
            evidence_ids = sorted({entry[0]['operation_id'] for entry in occurrences})
            plan = {'kind': 'prepare_routine', 'inputs': {'path': str(self.commands.executor.workspace_root)},
                'task_id': task, 'context': {'source': 'events', 'project_id': source.get('project_id', ''), 'device_id': 'host'},
                'skill_id': skill_id, 'skill_version': version, 'inputs_hash': inputs_hash,
                'learning_operation_id': source['operation_id'], 'source_plan_hash': source['plan_hash'],
                'evidence_ids': evidence_ids}
            with self.lock, self.db:
                self._preparation_candidate(task, 'repeat.' + skill_id, 'Preparar rutina: ' + skill['title'][:100],
                    plan, profile, options, [{'operation_id': key} for key in evidence_ids])

    def _forgotten_source(self, task, routine, source):
        keys = ('forget-task-' + digest(task), 'forget-routine-' + digest(routine),
                'forget-task-routine-' + digest({'task_id': task, 'routine_id': routine}))
        cutoff = self.db.execute('SELECT MAX(at) FROM anticipation_seen WHERE operation_id IN (?,?,?)', keys).fetchone()[0]
        return cutoff is not None and source.get('created_at', 0) <= cutoff

    def _preparation_source(self, item):
        learning = self.commands.learning
        if learning is None or learning.closed or learning.closing:
            raise ValueError('El planificador existente no está disponible')
        plan = item['plan']
        source_row = self.db.execute('SELECT payload FROM learning_plans WHERE id=?', (plan['learning_operation_id'],)).fetchone()
        if not source_row:
            raise ValueError('La tarea de origen ya no existe')
        source = json.loads(source_row[0])
        task = source.get('conversation_id') or source['operation_id']
        if task != item['task_id'] or source.get('plan_hash') != plan['source_plan_hash'] or learning._plan_hash(source) != source.get('plan_hash'):
            raise StaleContext('La tarea de origen o sus pasos cambiaron')
        if plan['kind'] == 'resume_task':
            if source['state'] not in ('paused', 'interrupted') or self._checkpoint(source) != {key: plan[key] for key in ('last_verified_step', 'next_step', 'records_hash')}:
                raise StaleContext('El checkpoint cambió; prepara una propuesta nueva')
            if source.get('preparation_complete') is False:
                raise ValueError('El plan requiere completar la planificación antes de reanudar')
            return learning, source, None
        refs = [ref for ref in source.get('skill_versions', []) if ref['id'] == plan['skill_id']
            and ref['version'] == plan['skill_version'] and digest(ref['inputs']) == plan['inputs_hash']]
        if source['state'] != 'succeeded' or len(refs) != 1:
            raise ValueError('La rutina ya no tiene parámetros verificados inequívocos')
        from .memory.skill_memory import read_skill_state
        skill = read_skill_state(self.db, plan['skill_id'], plan['skill_version'], project_id=source.get('project_id', ''), task_id=item['task_id'])
        if not skill.get('environment_matches') or not skill.get('effect_verified'):
            raise ValueError('La rutina ya no es compatible con el entorno')
        from .memory.skill_memory import bind
        steps, _ = bind(skill, refs[0]['inputs'], {})
        return learning, source, steps

    def _check(self, item, *, automatic=False):
        if item.get('cancel_requested') or item['state'] not in (*PENDING, 'EXECUTING'):
            raise ValueError('La iniciativa fue cancelada o ya no está pendiente')
        if digest(item['plan']) != item['plan_hash'] or item['plan']['task_id'] != item['task_id']:
            raise StaleContext('El plan cambió; se requiere una propuesta nueva')
        if self.clock() >= item['expires_at']:
            raise ValueError('La propuesta caducó')
        _, options = self._policy(item['task_id'], item['plan']['inputs']['path'], context=item['plan'].get('context'))
        if options['mode'] in ('OFF', 'SHADOW') or self._suppressed(item['task_id'], item['routine_id']):
            raise ValueError('La iniciativa está pausada, excluida o suprimida')
        if item.get('candidate_kind', 'verify_artifact') != 'verify_artifact':
            if not self._preparation_scope_allowed(item['task_id']):
                raise ValueError('La preparación de tareas usa ámbitos por tarea; hay una condición de carpeta sin resolver')
            if automatic:
                raise ApprovalRequired('Revisa la preparación de esta tarea o rutina')
            return self._preparation_source(item)
        path = item['plan']['inputs']['path']
        if not self._source_authorized(item):
            raise ValueError('La autorización de origen cambió, fue revocada o caducó')
        verifier = self._verifier(path)
        if (not verifier['available'] or verifier['command_id'] != item['plan']['command_id']
                or item['plan'].get('verifier_version', verifier['version']) != verifier['version']):
            raise ValueError('El verificador registrado ya no está disponible')
        if automatic or item.get('approval') == 'persistent':
            grant = self._grant(item)
            if options['mode'] != 'EXECUTE' or not grant:
                raise ApprovalRequired('Esta iniciativa necesita una autorización vigente para su tarea y carpeta')
            if item.get('grant_id') and grant['grant_id'] != item['grant_id']:
                raise ApprovalRequired('La autorización aceptada cambió')
        if artifact_path_error(path) or list(fingerprint(Path(path).stat())) != item['plan']['expected_identity']:
            raise StaleContext('Cambió la identidad del archivo desde la propuesta')
        if Path(path).stat().st_size > options['resources']['max_file_bytes']:
            raise ValueError('El archivo excede el presupuesto de lectura del perfil')
        observed = hash_file(path, threading.Event())
        if item['plan'].get('expected_sha256') is not None and observed['sha256'] != item['plan']['expected_sha256']:
            raise StaleContext('El archivo cambió desde la propuesta; no se ejecutará el plan anterior')
        return observed

    def dispatch_guard(self, operation_id):
        if not isinstance(operation_id, str) or not operation_id.startswith('ant-'):
            return
        with self.lock:
            row = self.db.execute('SELECT payload FROM anticipation_suggestions WHERE json_extract(payload,\'$.operation_id\')=?', (operation_id,)).fetchone()
            if not row:
                return
            item = json.loads(row[0])
            if item['state'] != 'EXECUTING' or item.get('cancel_requested'):
                raise ValueError('La iniciativa ya no está autorizada para despachar')
            if item.get('candidate_kind', 'verify_artifact') != 'verify_artifact':
                raise ValueError('Esta iniciativa solo prepara un plan; no autoriza un comando')
            command_row = self.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?', (operation_id,)).fetchone()
            command = json.loads(command_row[0]) if command_row else {}
            if (item.get('accepted_hash') != item['plan_hash'] or command.get('command_id') != item['plan']['command_id']
                    or command.get('inputs') != item['plan']['inputs'] or command.get('conversation_id') != item['task_id']
                    or command.get('delivery_mode') != 'background' or command.get('source') != 'text'):
                raise ValueError('La operación no corresponde al plan de anticipación aceptado')
            try:
                self._check(item)
            except OSError as exc:
                raise ValueError('El archivo ya no está disponible para verificar') from exc
            with self.db:
                self._transition(item, 'DISPATCHED', {'operation_id': operation_id})

    def accept(self, suggestion_id, plan_hash, *, automatic=False):
        identifier(suggestion_id)
        if not isinstance(plan_hash, str) or not re.fullmatch('[a-f0-9]{64}', plan_hash):
            raise ValueError('Hash de plan inválido')
        with self.lock:
            item = self._get(suggestion_id)
            if item['plan_hash'] != plan_hash:
                raise ValueError('La aceptación corresponde a otra versión del plan')
            if item['state'] not in PENDING:
                return item | {'replayed': True}
            if item.get('preparation_complete'):
                return item | {'replayed': True}
            try:
                self._check(item, automatic=automatic)
            except (OSError, ValueError) as exc:
                if isinstance(exc, ApprovalRequired):
                    raise
                with self.db:
                    item.update(state='EXPIRED' if self.clock() >= item['expires_at'] else 'FAILED', error=str(exc))
                    if isinstance(exc, (StaleContext, OSError)) or item['state'] == 'EXPIRED':
                        item['context_state'] = 'stale'
                    self._save(item)
                    self._transition(item, item['state'])
                return item
            item.update(state='EXECUTING', approval='persistent' if automatic else 'manual', accepted_hash=plan_hash,
                        accepted_at=self.clock(), owner_id=self.owner_id, lease_expires_at=self.clock() + 60)
            item.setdefault('feedback', {})['acceptance'] = 'persistent_grant' if automatic else 'explicit'
            if automatic:
                item['grant_id'] = self._grant(item)['grant_id']
            item['assessment']['authorization'] = {'allowed': True, 'source': item['approval'], 'grant_id': item.get('grant_id')}
            # The conditional claim also arbitrates two backend processes sharing state.db.
            with self.db:
                changed = self.db.execute('UPDATE anticipation_suggestions SET state=?,payload=? WHERE suggestion_id=? AND state IN (?,?,?)',
                    ('EXECUTING', canonical(item), suggestion_id, *PENDING)).rowcount
                if not changed:
                    return self._get(suggestion_id) | {'replayed': True}
                self._stats(item['task_id'], item['routine_id'], 'accepted')
                self._stats(item['task_id'], item['routine_id'], 'autonomous_executions' if automatic else 'explicit_acceptances')
                self._transition(item, 'INTENDED', {'plan_hash': plan_hash})
        try:
            if item.get('candidate_kind', 'verify_artifact') != 'verify_artifact':
                return self._prepare_existing(item)
            prepared = self.commands.prepare(item['plan']['command_id'], item['plan']['inputs'], 'text', item['operation_id'],
                                             conversation_id=item['task_id'], delivery_mode='background')
            with self.lock:
                self._check(self._get(suggestion_id))
                with self.db:
                    self._transition(item, 'PREPARED', {'operation_id': prepared['operation_id']})
            result = self.commands.execute(item['operation_id'], approved=True)
            return self._finish(suggestion_id, result)
        except Exception as exc:
            LOG.warning('Anticipation execution stopped: %s', type(exc).__name__)
            with self.lock:
                forgotten = self.db.execute('SELECT 1 FROM anticipation_suggestions WHERE suggestion_id=?', (suggestion_id,)).fetchone() is None
            if forgotten:
                # Forget may race preparation, but cannot leave a command waiting
                # for a later accidental approval or recreate personal context.
                self.commands.cancel(item['operation_id'])
                return {'suggestion_id': suggestion_id, 'state': 'CANCELLED', 'forgotten': True, 'result': None}
            if item.get('candidate_kind', 'verify_artifact') != 'verify_artifact':
                with self.lock, self.db:
                    item = self._get(suggestion_id)
                    if item['state'] == 'EXECUTING':
                        item.update(state='FAILED', error=str(exc))
                        self._save(item)
                        self._transition(item, 'FAILED')
                return item
            result = self.commands.get(item['operation_id'])
            if result and result.get('state') not in ('prepared', 'awaiting_approval', 'running'):
                return self._finish(suggestion_id, result)
            with self.lock, self.db:
                item = self._get(suggestion_id)
                if item['state'] == 'EXECUTING':
                    item.update(state='UNCERTAIN' if result and result['state'] == 'running' else 'FAILED', error=str(exc))
                    self._save(item)
                    self._transition(item, item['state'])
            if result and result.get('state') in ('prepared', 'awaiting_approval'):
                self.commands.cancel(item['operation_id'])
            return item

    def _prepare_existing(self, item):
        with self.lock:
            item = self._get(item['suggestion_id'])
            if item['state'] != 'EXECUTING' or item.get('cancel_requested'):
                raise ValueError('La preparación fue cancelada antes de empezar')
            learning, source, steps = self._check(item)
            plan_id = source['operation_id'] if steps is None else 'ant-plan-' + item['suggestion_id'].split('-', 1)[1]
            item['learning_plan_id'] = plan_id
            with self.db:
                self._save(item)
                # Causation survives proposal retention without retaining content or plan identifiers.
                self.db.execute('INSERT OR IGNORE INTO anticipation_seen VALUES (?,?)',
                    ('initiated-learning-' + digest(plan_id), self.clock()))
        with self.lock:
            current = self._get(item['suggestion_id'])
            if current['state'] != 'EXECUTING' or current.get('cancel_requested'):
                raise ValueError('La preparación fue cancelada antes de usar el planificador')
        result = (learning.resume(source['operation_id'], approved=False) if steps is None else
            learning.prepare_steps(item['title'], steps, operation_id=plan_id,
                project_id=source.get('project_id', ''), conversation_id=item['task_id']))
        with self.lock:
            try:
                cancelled = self._get(item['suggestion_id']).get('cancel_requested')
            except ValueError:
                cancelled = True
        if cancelled:
            result = learning.pause(plan_id)
        return self._finish_preparation(item['suggestion_id'], result)

    def _finish_preparation(self, key, result):
        with self.lock, self.db:
            try:
                item = self._get(key)
            except ValueError:
                return {'suggestion_id': key, 'state': 'CANCELLED', 'forgotten': True, 'result': None}
            prepared = result.get('state') == 'awaiting_approval' and bool(result.get('steps')) and bool(result.get('plan_hash'))
            state = 'PREPARED' if prepared else 'FAILED'
            if item.get('cancel_requested'):
                state = 'CANCELLED'
            item.update(state=state, preparation_complete=prepared, learning_plan_id=result['operation_id'],
                result=result | {'kind': 'learned_plan'}, completed_at=self.clock(),
                message='Plan preparado en la tarea existente. Revisa y aprueba sus pasos antes de ejecutarlos.' if prepared else 'La tarea requiere revisión; no se ejecutaron nuevos pasos.',
                error=None if prepared else result.get('message'))
            self._save(item)
            self._transition(item, state, {'learning_plan_id': result['operation_id'], 'effects_executed': False})
            return item

    def _finish(self, key, result):
        with self.lock, self.db:
            try:
                item = self._get(key)
            except ValueError:
                return {'suggestion_id': key, 'state': 'CANCELLED', 'forgotten': True, 'result': None,
                        'message': 'La iniciativa se olvidó; la cancelación no revierte efectos ya ocurridos.'}
            output = result.get('output') or {}
            observed = output.get('files') or ([output] if output.get('sha256') and output.get('path') else [])
            try:
                same_identity = list(fingerprint(Path(item['plan']['inputs']['path']).stat())) == item['plan']['expected_identity']
            except OSError:
                same_identity = False
            verified = (result.get('state') == 'succeeded' and result.get('postconditions_passed') is True
                and len(observed) == 1 and isinstance(observed[0].get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', observed[0]['sha256'])
                and (item['plan'].get('expected_sha256') is None or observed[0].get('sha256') == item['plan']['expected_sha256'])
                and observed[0].get('path') == item['plan']['inputs']['path'] and same_identity)
            if result.get('dispatch_status') == 'delivered':
                self._transition(item, 'EXECUTED', {'operation_id': result['operation_id']})
            state = 'VERIFIED' if verified else 'UNCERTAIN' if result.get('state') in ('unknown', 'running') else 'CANCELLED' if result.get('state') == 'cancelled' else 'FAILED'
            if item.get('counted_result'):
                return item
            item.update(state=state, result=result, completed_at=self.clock(), counted_result=True,
                error=None if verified else result.get('error') or 'El contenido no coincide con el artefacto original.',
                message=('Comprobación observada: ' + item['plan'].get('verification_scope', 'integrity_only') + '. No acredita corrección semántica ni calidad visual.' if verified else 'Revisa el resultado; no se repetirá esta iniciativa automáticamente.'))
            if not same_identity:
                item['context_state'] = 'stale'
            self._save(item)
            self._transition(item, state, {'operation_id': result['operation_id'], 'observed': observed})
            self._stats(item['task_id'], item['routine_id'], 'verified' if verified else 'failed')
            if verified:
                self._stats(item['task_id'], item['routine_id'], 'technical_verified')
            if type(result.get('duration_ms')) in (int, float):
                self._measure(item['task_id'], 'verification', result['duration_ms'])
            return item

    def _recover(self):
        with self.lock:
            pending = [item for item in self._items() if item['state'] == 'EXECUTING']
        for item in pending:
            if item.get('owner_id') in ACTIVE_OWNERS:
                continue
            if item.get('candidate_kind', 'verify_artifact') != 'verify_artifact' and item.get('learning_plan_id') and self.commands.learning:
                try:
                    prepared = self.commands.learning.get(item['learning_plan_id'])
                    if prepared.get('state') == 'awaiting_approval':
                        self._finish_preparation(item['suggestion_id'], prepared)
                        continue
                except ValueError:
                    pass
            result = self.commands.get(item['operation_id'])
            if result and result['state'] == 'unknown':
                result = self.commands.reconcile(item['operation_id'])
            if result and result['state'] in ('succeeded', 'failed', 'cancelled', 'unknown'):
                self._finish(item['suggestion_id'], result)
            else:
                # An unexpired claim may belong to another live process; expiry never means success.
                if item.get('lease_expires_at', 0) > self.clock():
                    continue
                with self.lock, self.db:
                    item.update(state='UNCERTAIN', error='La sesión se interrumpió; inspecciona el recibo. No se reintentará.')
                    self._save(item)
                    self._transition(item, 'UNCERTAIN')

    def tick(self):
        if self.closed or not self.tick_gate.acquire(blocking=False):
            return []
        try:
            self.tick_started = (time.perf_counter(), time.process_time())
            self.tick_events = {}
            self._recover()
            self._observe()
            self._poll_sources()
            with self.lock:
                config = self._config()
                options = config['profiles'][config['profile']]
            if self._within_budget(options):
                self._observe_preparations()
            with self.lock, self.db:
                cancelled = self._invalidate()
                candidates = []
                for item in self._items():
                    if item['state'] not in PENDING:
                        continue
                    if item.get('preparation_complete'):
                        continue
                    if self.clock() >= item['expires_at']:
                        item.update(state='EXPIRED', context_state='stale')
                        self._save(item)
                        self._transition(item, 'EXPIRED')
                        continue
                    _, options = self._policy(item['task_id'], item['plan']['inputs']['path'], context=item['plan'].get('context'))
                    # A later profile upgrade never turns an old suggestion into an automatic action.
                    if self._within_budget(options) and item.get('candidate_kind', 'verify_artifact') == 'verify_artifact' and item['admitted_mode'] == 'EXECUTE' and options['mode'] == 'EXECUTE' and not item.get('shadow') and item.get('grant_id') and self._grant(item):
                        candidates.append(item)
            self._cancel_commands(cancelled)
            results = []
            dispatched = {}
            for item in candidates:
                with self.lock:
                    profile, options = self._policy(item['task_id'], item['plan']['inputs']['path'], context=item['plan'].get('context'))
                    # Admission is checked after each real inspector; an admitted
                    # bounded command still uses its existing executor timeout.
                    if (not self._within_budget(options)
                            or dispatched.get(profile, 0) >= options['resources']['max_events_tick']):
                        continue
                    dispatched[profile] = dispatched.get(profile, 0) + 1
                results.append(self.accept(item['suggestion_id'], item['plan_hash'], automatic=True))
            self._purge()
            return results
        finally:
            if self.tick_started is not None:
                started, cpu_started = self.tick_started
                with self.lock:
                    if not self.closed:
                        with self.db:
                            self._measure('', 'tick', (time.perf_counter() - started) * 1000, (time.process_time() - cpu_started) * 1000)
                self.tick_started = None
            self.tick_gate.release()

    def feedback(self, key, body):
        if isinstance(body, str):
            body = {'action': body}
        if not isinstance(body, dict) or set(body) != {'action'} or body['action'] not in ('dismiss', 'suppress', 'restore', 'shown', 'useful', 'correction'):
            raise ValueError('Feedback inválido')
        action = body['action']
        with self.lock, self.db:
            item = self._get(key)
            if action in ('useful', 'correction'):
                feedback = item.setdefault('feedback', {'acceptance': 'none', 'usefulness': 'unknown', 'corrections': 0})
                if action == 'correction':
                    feedback.update(usefulness='corrected', corrections=feedback.get('corrections', 0) + 1)
                    self._stats(item['task_id'], item['routine_id'], 'explicit_corrections')
                elif not feedback.get('corrections') and feedback.get('usefulness') != 'confirmed':
                    feedback['usefulness'] = 'confirmed'
                    self._stats(item['task_id'], item['routine_id'], 'explicit_useful_feedback')
            elif action == 'shown':
                _, options = self._policy(item['task_id'], item['plan']['inputs']['path'], context=item['plan'].get('context'))
                if not item.get('shown_at') and self._visible(item, options):
                    item['shown_at'] = self.clock()
                    self._stats(item['task_id'], item['routine_id'], 'shown')
            elif action == 'restore':
                self.db.execute('DELETE FROM anticipation_suppressions WHERE task_id=? AND routine_id=?', (item['task_id'], item['routine_id']))
                # Restoring the routine affects future events, never old plans.
            else:
                item['dismissed'] = True
                if action == 'suppress':
                    self.db.execute('INSERT OR IGNORE INTO anticipation_suppressions VALUES (?,?)', (item['task_id'], item['routine_id']))
                if item['state'] in PENDING:
                    item.update(state='SUPPRESSED' if action == 'suppress' else 'DISMISSED')
                    self._stats(item['task_id'], item['routine_id'], 'rejected')
            self._save(item)
        if action == 'correction' and item['state'] in (*PENDING, 'EXECUTING'):
            return self.cancel(key)
        return item

    def cancel(self, key=None):
        with self.lock, self.db:
            items = [self._get(key)] if key else self._items()
            commands = []
            for item in items:
                if item['state'] in (*PENDING, 'EXECUTING'):
                    item.update(state='CANCELLED', cancel_requested=True,
                        message='Iniciativa cancelada; los efectos ya observados permanecen en el recibo.')
                    self._save(item)
                    self._transition(item, 'CANCELLED')
                    commands.append(item['operation_id'])
            if key is None:
                config = self._config() | {'paused': True}
                self.db.execute('UPDATE anticipation_config SET payload=? WHERE id=1', (canonical(config),))
        self._cancel_commands(commands)
        return self.status() if key is None else self.status_item(key)

    def pause(self, paused=True, observation=True):
        return self.configure({'paused': paused, **({'observation_paused': paused} if observation else {})})

    def status_item(self, key):
        with self.lock:
            return self._get(key)

    def suggestions(self, task_id=None):
        return self.status(task_id)['suggestions']

    def forget(self, body):
        if not isinstance(body, dict) or set(body) - {'task_id', 'routine_id'} or not body:
            raise ValueError('Indica la tarea o rutina que deseas olvidar')
        for value in body.values():
            identifier(value)
        with self.lock:
            selected = [item for item in self._items(body.get('task_id')) if not body.get('routine_id') or item['routine_id'] == body['routine_id']]
        for item in selected:
            self.cancel(item['suggestion_id'])
        with self.lock, self.db:
            marker = ('forget-task-routine-' + digest(body) if len(body) == 2 else
                      'forget-task-' + digest(body['task_id']) if 'task_id' in body else 'forget-routine-' + digest(body['routine_id']))
            self.db.execute('INSERT INTO anticipation_seen VALUES (?,?) ON CONFLICT(operation_id) DO UPDATE SET at=excluded.at', (marker, self.clock()))
            for item in selected:
                self.db.execute('DELETE FROM anticipation_transitions WHERE suggestion_id=?', (item['suggestion_id'],))
                self.db.execute('DELETE FROM anticipation_suggestions WHERE suggestion_id=?', (item['suggestion_id'],))
            where = ' AND '.join(key + '=?' for key in body)
            for table in ('anticipation_stats', 'anticipation_suppressions'):
                self.db.execute('DELETE FROM ' + table + ' WHERE ' + where, tuple(body.values()))
            if body.get('task_id') and body.get('routine_id', ROUTINE) == ROUTINE:
                self.db.execute('DELETE FROM anticipation_events WHERE task_id=?', (body['task_id'],))
                self.db.execute('DELETE FROM anticipation_measurements WHERE task_id=?', (body['task_id'],))
            elif body.get('routine_id') == ROUTINE:
                self.db.execute('DELETE FROM anticipation_events')
        return {'forgotten_suggestions': len(selected), 'scope': body, 'command_journal_preserved': True}

    def _purge(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM anticipation_privacy WHERE action_operation_id IN (SELECT operation_id FROM operations WHERE state IN ('succeeded','failed','cancelled'))")
            config = self._config()
            for name, options in config['profiles'].items():
                cutoff = self.clock() - options['retention_days'] * 86400
                ids = [row[0] for row in self.db.execute("SELECT suggestion_id FROM anticipation_suggestions WHERE at<? AND json_extract(payload,'$.profile')=? AND state NOT IN ('EXECUTING')", (cutoff, name))]
                for key in ids:
                    self.db.execute('DELETE FROM anticipation_transitions WHERE suggestion_id=?', (key,))
                    self.db.execute('DELETE FROM anticipation_suggestions WHERE suggestion_id=?', (key,))
            for row in self.db.execute('SELECT event_id,at,payload FROM anticipation_events').fetchall():
                event = json.loads(row['payload'])
                days = config['profiles'].get(event.get('profile'), {}).get('retention_days', event.get('retention_days', 1))
                if row['at'] < self.clock() - days * 86400:
                    self.db.execute('DELETE FROM anticipation_events WHERE event_id=?', (row['event_id'],))

    def close(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.source_state.clear()
                self.source_observations.clear()
                ACTIVE_OWNERS.pop(self.owner_id, None)
                self.db.close()
