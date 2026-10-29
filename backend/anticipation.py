"""Scoped anticipation over the existing command journal; never another executor."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
import weakref

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
ACTIVE_OWNERS = weakref.WeakValueDictionary()
DEFAULTS = {
    'profile': 'discreto', 'paused': False, 'observation_paused': False,
    'sources': {'events': True, 'screen': False, 'microphone': False, 'clipboard': False},
    'profiles': {name: {'mode': mode, 'interruptions': 'silent' if name == 'discreto' else 'cards',
        'cooldown_seconds': 60, 'max_interruptions_hour': 3, 'retention_days': 30}
        for name, mode in zip(PROFILES, ('OFF', 'SUGGEST', 'EXECUTE'))},
    'scopes': []}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value, label='Identificador'):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        raise ValueError(label + ' inválido')
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
            ''')
            if not self.db.execute('SELECT 1 FROM anticipation_config WHERE id=1').fetchone():
                self.db.execute('INSERT INTO anticipation_config VALUES (1,?)', (canonical(DEFAULTS),))
                # Installing anticipation never turns historical artifacts into new initiatives.
                self.db.execute("INSERT OR IGNORE INTO anticipation_seen SELECT operation_id,? FROM operations WHERE tool_name='file_artifact_writer'", (self.clock(),))
        self._recover()

    def _config(self):
        return json.loads(self.db.execute('SELECT payload FROM anticipation_config WHERE id=1').fetchone()[0])

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

    def _policy(self, task_id, path, config=None):
        config = config or self._config()
        matches = [scope for scope in config['scopes'] if
            (not scope.get('task_id') or scope['task_id'] == task_id) and
            (not scope.get('root') or Path(path).is_relative_to(Path(scope['root'])))]
        if any(scope.get('exclude') for scope in matches):
            return None, {'mode': 'OFF'}
        names = {scope['profile'] for scope in matches if scope.get('profile')}
        if len(names) > 1:
            return None, {'mode': 'OFF', 'conflict': True}
        name = next(iter(names)) if names else config['profile']
        options = config['profiles'][name]
        if config['paused'] or config['observation_paused'] or not config['sources']['events']:
            return name, options | {'mode': 'OFF'}
        return name, options

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

    def status(self, task_id=None):
        with self.lock:
            config = self._config()
            rows = self._items(task_id)[:100]
            for item in rows:
                effective, options = self._policy(item['task_id'], item['plan']['inputs']['path'], config)
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
                'metrics': {'proposed': sum(row.get('proposed', 0) for row in stats),
                    'shown': sum(row.get('shown', 0) for row in stats),
                    'verified': sum(row.get('verified', 0) for row in stats),
                    'failed': sum(row.get('failed', 0) for row in stats),
                    'model_calls': 0},
                'capabilities': {'verify_artifact': self._can_verify(), 'physical_execution': False,
                    'screen': False, 'microphone': False, 'clipboard': False,
                    'reason': 'M15 abierto: no se habilita ejecución física proactiva; fuentes nuevas no validadas.'}}

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
                    if type(enabled) is not bool or source != 'events' and enabled:
                        raise ValueError('Esta fuente todavía no dispone de observación validada')
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
                    config['profiles'][name] = options
            if 'scopes' in body:
                if not isinstance(body['scopes'], list) or len(body['scopes']) > 64:
                    raise ValueError('Ámbitos inválidos')
                scopes = []
                for raw in body['scopes']:
                    if not isinstance(raw, dict) or set(raw) - {'task_id', 'root', 'profile', 'exclude'} or not (raw.get('task_id') or raw.get('root')):
                        raise ValueError('Indica tarea o carpeta del ámbito')
                    scope = copy.deepcopy(raw)
                    if scope.get('task_id'):
                        identifier(scope['task_id'], 'Tarea')
                    if scope.get('root'):
                        scope['root'] = directory(scope['root'])
                    if scope.get('profile') not in (None, *PROFILES) or type(scope.get('exclude', False)) is not bool:
                        raise ValueError('Política de ámbito inválida')
                    if not scope.get('profile') and not scope.get('exclude'):
                        raise ValueError('El ámbito debe seleccionar un perfil o excluir')
                    scopes.append(scope)
                config['scopes'] = scopes
            self.db.execute('UPDATE anticipation_config SET payload=? WHERE id=1', (canonical(config),))
            cancelled = self._invalidate(config)
        self._cancel_commands(cancelled)
        return self.status()

    def _invalidate(self, config=None):
        cancelled = []
        for item in self._items():
            if item['state'] not in (*PENDING, 'EXECUTING'):
                continue
            _, options = self._policy(item['task_id'], item['plan']['inputs']['path'], config)
            old_mode = item.get('admitted_mode', 'SUGGEST')
            invalid = MODES.index(options['mode']) < MODES.index(old_mode)
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
            rows = self.db.execute("""SELECT o.operation_id,o.result_json,c.result_json AS command_json
                FROM operations o JOIN command_runs c ON json_extract(c.result_json,'$.action_operation_id')=o.operation_id
                WHERE o.tool_name='file_artifact_writer' AND o.state='succeeded' AND c.state='succeeded'
                AND NOT EXISTS (SELECT 1 FROM anticipation_seen s WHERE s.operation_id=o.operation_id)
                ORDER BY o.created_at LIMIT 50""").fetchall()
        for row in rows:
            with self.lock, self.db:
                inserted = self.db.execute('INSERT OR IGNORE INTO anticipation_seen VALUES (?,?)', (row['operation_id'], self.clock())).rowcount
                if not inserted:
                    continue
                receipt, command = json.loads(row['result_json']), json.loads(row['command_json'])
                output = receipt.get('output') or {}
                task = command.get('conversation_id') or command['operation_id']
                path = output.get('path')
                if (receipt.get('postconditions_passed') is not True or not isinstance(path, str)
                        or not re.fullmatch('[a-f0-9]{64}', output.get('sha256', ''))):
                    continue
                profile, options = self._policy(task, path)
                if options['mode'] == 'OFF' or not Path(path).is_relative_to(self.commands.executor.workspace_root):
                    continue
                event = {'event_id': 'artifact-' + row['operation_id'], 'type': 'artifact.generated', 'task_id': task,
                    'source_operation_id': row['operation_id'], 'path': path, 'sha256': output['sha256'], 'at': self.clock(),
                    'profile': profile, 'retention_days': options['retention_days'],
                    'provenance': self._command_provenance(command), 'outcome': 'verified', 'feedback': 'none'}
                self.db.execute('INSERT OR IGNORE INTO anticipation_events VALUES (?,?,?,?)', (event['event_id'], task, self.clock(), canonical(event)))
                if self._suppressed(task, ROUTINE):
                    continue
                previous = self.db.execute('SELECT MAX(at) FROM anticipation_suggestions WHERE task_id=? AND routine_id=?', (task, ROUTINE)).fetchone()[0]
                if previous is not None and self.clock() - previous < options['cooldown_seconds']:
                    self._stats(task, ROUTINE, 'cooldown_abstentions')
                    continue
                try:
                    self._propose(event, profile, options)
                except OSError:
                    self._stats(task, ROUTINE, 'unavailable_abstentions')

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
        plan = {'version': 1, 'command_id': 'axx.file.sha256', 'inputs': {'path': event['path']},
                'expected_sha256': event['sha256'], 'expected_identity': list(fingerprint(Path(event['path']).stat())),
                'source_operation_id': event['source_operation_id'], 'task_id': event['task_id']}
        context_fingerprint = digest({'path': event['path'], 'sha256': event['sha256'], 'task_id': event['task_id']})
        key = digest({'event': event['event_id'], 'routine': ROUTINE, 'task': event['task_id']})
        sid = 'anticipation-' + key[:32]
        mode = options['mode']
        item = {'suggestion_id': sid, 'candidate_kind': 'verify_artifact', 'task_id': event['task_id'], 'routine_id': ROUTINE, 'routine_version': 1,
            'title': 'Verificar el archivo generado', 'state': 'DETECTED' if mode == 'SHADOW' else 'PREPARED' if mode == 'PREPARE' else 'AWAITING_APPROVAL',
            'plan': plan, 'plan_hash': digest(plan), 'context_fingerprint': context_fingerprint,
            'operation_id': 'ant-' + key[:48], 'profile': profile, 'admitted_mode': mode, 'shadow': mode == 'SHADOW',
            'context_state': 'observed',
            'created_at': self.clock(), 'expires_at': self.clock() + 300, 'result': None, 'error': None,
            'assessment': {'likelihood': {'score': 1, 'method': 'registered_generated_artifact_rule'},
                'capability': {'available': self._can_verify(), 'command_id': 'axx.file.sha256'},
                'authorization': {'allowed': False, 'required': CAPABILITY}},
            'provenance': event['provenance'],
            'initiative_chain': {'root_event_id': event['event_id'], 'depth': 1, 'budget': 1, 'stop_condition': 'verification_terminal'},
            'feedback': {'acceptance': 'none', 'usefulness': 'unknown', 'corrections': 0},
            'message': 'Puedo comprobar que el archivo sigue legible y conserva su SHA256; no verifica su calidad visual.'}
        if mode == 'EXECUTE' and (grant := self._grant(item)):
            item.update(approval='persistent', grant_id=grant['grant_id'])
        inserted = self.db.execute('INSERT OR IGNORE INTO anticipation_suggestions VALUES (?,?,?,?,?,?,?,?)',
            (sid, key, item['task_id'], ROUTINE, item['state'], item['plan_hash'], self.clock(), canonical(item))).rowcount
        if inserted:
            self._stats(item['task_id'], ROUTINE, 'proposed')
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
            self.db.execute('INSERT OR IGNORE INTO anticipation_seen VALUES (?,?)', ('preparation-' + key, self.clock()))
            self._stats(task, routine, 'proposed')
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
            with self.lock:
                if not self._preparation_scope_allowed(task):
                    continue
                profile, options = self._policy(task, path)
            if options['mode'] == 'OFF' or source.get('preparation_complete') is False:
                continue
            if source.get('state') in ('paused', 'interrupted'):
                checkpoint = self._checkpoint(source)
                with self.lock:
                    forgotten = self._forgotten_source(task, 'resume_incomplete_task', source)
                if not forgotten and checkpoint['last_verified_step'] >= 0 and checkpoint['next_step'] < len(source.get('steps', [])):
                    plan = {'kind': 'resume_task', 'inputs': {'path': path}, 'task_id': task,
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
            try:
                skill = learning.skills.get(skill_id, version)
                if not skill.get('environment_matches') or not skill.get('effect_verified'):
                    continue
                from .memory.skill_memory import bind
                steps, _ = bind(skill, ref['inputs'], {})
                learning._validate_steps(steps)
            except (ValueError, KeyError, TypeError):
                continue
            evidence_ids = sorted({entry[0]['operation_id'] for entry in occurrences})
            plan = {'kind': 'prepare_routine', 'inputs': {'path': str(self.commands.executor.workspace_root)},
                'task_id': task, 'skill_id': skill_id, 'skill_version': version, 'inputs_hash': inputs_hash,
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
        skill_row = self.db.execute('SELECT payload FROM skill_versions WHERE id=? AND version=?', (plan['skill_id'], plan['skill_version'])).fetchone()
        if not skill_row:
            raise ValueError('La versión de la rutina ya no existe')
        skill = json.loads(skill_row[0])
        evidence = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM skill_evidence WHERE id=? AND version=?', (plan['skill_id'], plan['skill_version']))]
        from .memory.procedural_memory import get_action_env_fingerprint
        compatible = skill.get('executable') and skill.get('environment') == get_action_env_fingerprint(step['command_id'] for step in skill['templates'])
        if not compatible or not any(row.get('effect_verified') is True for row in evidence):
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
        _, options = self._policy(item['task_id'], item['plan']['inputs']['path'])
        if options['mode'] in ('OFF', 'SHADOW') or self._suppressed(item['task_id'], item['routine_id']):
            raise ValueError('La iniciativa está pausada, excluida o suprimida')
        if item.get('candidate_kind', 'verify_artifact') != 'verify_artifact':
            if not self._preparation_scope_allowed(item['task_id']):
                raise ValueError('La preparación de tareas usa ámbitos por tarea; hay una condición de carpeta sin resolver')
            if automatic:
                raise ApprovalRequired('Revisa la preparación de esta tarea o rutina')
            return self._preparation_source(item)
        if not self._can_verify():
            raise ValueError('El verificador registrado ya no está disponible')
        if automatic or item.get('approval') == 'persistent':
            grant = self._grant(item)
            if options['mode'] != 'EXECUTE' or not grant:
                raise ApprovalRequired('Esta iniciativa necesita una autorización vigente para su tarea y carpeta')
            if item.get('grant_id') and grant['grant_id'] != item['grant_id']:
                raise ApprovalRequired('La autorización aceptada cambió')
        if list(fingerprint(Path(item['plan']['inputs']['path']).stat())) != item['plan']['expected_identity']:
            raise StaleContext('Cambió la identidad del archivo desde la propuesta')
        observed = hash_file(item['plan']['inputs']['path'], threading.Event())
        if observed['sha256'] != item['plan']['expected_sha256']:
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
            cancelled = self._get(item['suggestion_id']).get('cancel_requested')
        if cancelled:
            result = learning.pause(plan_id)
        return self._finish_preparation(item['suggestion_id'], result)

    def _finish_preparation(self, key, result):
        with self.lock, self.db:
            item = self._get(key)
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
            item = self._get(key)
            observed = (result.get('output') or {}).get('files') or []
            try:
                same_identity = list(fingerprint(Path(item['plan']['inputs']['path']).stat())) == item['plan']['expected_identity']
            except OSError:
                same_identity = False
            verified = (result.get('state') == 'succeeded' and result.get('postconditions_passed') is True
                and len(observed) == 1 and observed[0].get('sha256') == item['plan']['expected_sha256']
                and observed[0].get('path') == item['plan']['inputs']['path'] and same_identity)
            if result.get('dispatch_status') == 'delivered':
                self._transition(item, 'EXECUTED', {'operation_id': result['operation_id']})
            state = 'VERIFIED' if verified else 'UNCERTAIN' if result.get('state') in ('unknown', 'running') else 'CANCELLED' if result.get('state') == 'cancelled' else 'FAILED'
            if item.get('counted_result'):
                return item
            item.update(state=state, result=result, completed_at=self.clock(), counted_result=True,
                error=None if verified else result.get('error') or 'El contenido no coincide con el artefacto original.',
                message=('Archivo leído; SHA256 y tamaño observados. No se comprobó calidad visual.' if verified else 'Revisa el resultado; no se repetirá esta iniciativa automáticamente.'))
            if not same_identity:
                item['context_state'] = 'stale'
            self._save(item)
            self._transition(item, state, {'operation_id': result['operation_id'], 'observed': observed})
            self._stats(item['task_id'], item['routine_id'], 'verified' if verified else 'failed')
            if verified:
                self._stats(item['task_id'], item['routine_id'], 'technical_verified')
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
            self._recover()
            self._observe()
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
                    _, options = self._policy(item['task_id'], item['plan']['inputs']['path'])
                    # A later profile upgrade never turns an old suggestion into an automatic action.
                    if item.get('candidate_kind', 'verify_artifact') == 'verify_artifact' and item['admitted_mode'] == 'EXECUTE' and options['mode'] == 'EXECUTE' and not item.get('shadow') and item.get('grant_id') and self._grant(item):
                        candidates.append(item)
            self._cancel_commands(cancelled)
            results = [self.accept(item['suggestion_id'], item['plan_hash'], automatic=True) for item in candidates]
            self._purge()
            return results
        finally:
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
                _, options = self._policy(item['task_id'], item['plan']['inputs']['path'])
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
            elif body.get('routine_id') == ROUTINE:
                self.db.execute('DELETE FROM anticipation_events')
        return {'forgotten_suggestions': len(selected), 'scope': body, 'command_journal_preserved': True}

    def _purge(self):
        with self.lock, self.db:
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
                ACTIVE_OWNERS.pop(self.owner_id, None)
                self.db.close()
