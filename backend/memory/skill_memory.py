"""Versioned skill definitions and project context; execution stays in CommandService."""
import copy
from contextlib import contextmanager, nullcontext
import hashlib
import json
import math
from pathlib import PureWindowsPath
import re
import time
import unicodedata

from .procedural_memory import get_action_env_fingerprint
from . import selection_policy, task_memory


PARAMETER = re.compile(r'\{\{([A-Za-z][A-Za-z0-9_]{0,63})\}\}')
CONTEXT_FIELDS = frozenset({'aliases', 'defaults', 'last_inputs', 'last_skill_id', 'current_file', 'current_folder',
    'current_application', 'current_project', 'selected_items', 'mentioned_objects', 'last_result', 'parameters_modified'})


def value_hash(value):
    value = json.loads(json.dumps(value, allow_nan=False))
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def read_skill_state(db, key, version=None, *, project_id=None, task_id=None, procedure_library=None):
    """Read the same projection without migrations or locks; the caller owns its SQL connection."""
    view = SkillMemory.__new__(SkillMemory)
    view.db, view.lock, view.procedure_library = db, nullcontext(), procedure_library
    return view.get(key, version, project_id=project_id, task_id=task_id)


def read_context_state(db, project_id=''):
    """Resolve field freshness and dependencies using the caller's serialized SQL connection."""
    view = SkillMemory.__new__(SkillMemory)
    view.db, view.lock = db, nullcontext()
    return view.context(project_id)


def lesson_refs(items):
    return [{'id': item['id'], 'digest': value_hash(_lesson_content(item))} for item in items]


def _lesson_content(item):
    return {'allow_provider': False} | {key: value for key, value in item.items()
        if key not in ('environment_matches', 'context_matches', 'status')}


def assert_lessons_current(db, refs, project_id, task_id, *, procedure_library=None):
    """Validate selected incident references in the caller's SQL transaction, without writes or locks."""
    project_key(project_id)
    if task_id is not None: task_memory.state(db, task_id)
    if not isinstance(refs, list) or len(refs) > 3: raise ValueError('Referencias de incidentes inválidas')
    view = SkillMemory.__new__(SkillMemory)
    view.db, view.lock, view.procedure_library = db, nullcontext(), procedure_library
    for ref in refs:
        if (not isinstance(ref, dict) or set(ref) != {'id', 'digest'}
                or not isinstance(ref['id'], str) or not re.fullmatch(r'lesson\.[a-f0-9]{32}', ref['id'])
                or not isinstance(ref['digest'], str) or not re.fullmatch(r'[a-f0-9]{64}', ref['digest'])):
            raise ValueError('Referencia de incidente inválida')
        row = db.execute('SELECT payload FROM skill_lessons WHERE id=?', (ref['id'],)).fetchone()
        item = json.loads(row[0]) if row else None
        if (not item or value_hash(_lesson_content(item)) != ref['digest']
                or item.get('project_id', '') not in ('', project_id)
                or item.get('task_id') not in (None, '', task_id)
                or not view._lesson_current(item, project_id, task_id)):
            raise ValueError('El incidente seleccionado cambió o dejó de ser vigente')
    return refs


def lesson_search_text(value):
    return ''.join(char for char in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(char))


class NeedsInput(ValueError):
    pass


def bounded_object(value, limit=16000):
    if not isinstance(value, dict) or len(json.dumps(value, allow_nan=False)) > limit:
        raise ValueError('Objeto demasiado grande o inválido')
    return copy.deepcopy(value)


def project_key(value):
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError('Proyecto inválido')
    return value


def validate_schema(schema):
    schema = bounded_object(schema)
    if set(schema) - {'type', 'properties', 'required', 'additionalProperties'} or schema.get('type', 'object') != 'object':
        raise ValueError('El esquema debe ser un objeto de parámetros tipados')
    properties, required = schema.get('properties', {}), schema.get('required', [])
    if not isinstance(properties, dict) or len(properties) > 32 or not isinstance(required, list):
        raise ValueError('Parámetros inválidos')
    if any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', name) for name in properties):
        raise ValueError('Nombre de parámetro inválido')
    if any(not isinstance(name, str) or name not in properties for name in required):
        raise ValueError('Parámetro requerido desconocido')
    for spec in properties.values():
        if not isinstance(spec, dict) or set(spec) - {'type', 'description', 'default', 'enum'}:
            raise ValueError('Definición de parámetro inválida')
        if spec.get('type') not in ('string', 'integer', 'number', 'boolean'):
            raise ValueError('Tipo de parámetro no soportado')
        if 'description' in spec and (not isinstance(spec['description'], str) or len(spec['description']) > 500):
            raise ValueError('Descripción inválida')
        if 'enum' in spec:
            if not isinstance(spec['enum'], list) or not 1 <= len(spec['enum']) <= 64:
                raise ValueError('Opciones inválidas')
            for value in spec['enum']: _typed(value, spec | {'enum': None})
        if 'default' in spec: _typed(spec['default'], spec)
    return {'type': 'object', 'properties': properties, 'required': list(dict.fromkeys(required)), 'additionalProperties': False}


def _typed(value, spec):
    kind = spec['type']
    valid = ((kind == 'string' and isinstance(value, str) and len(value) <= 16000)
             or (kind == 'boolean' and type(value) is bool)
             or (kind == 'integer' and type(value) is int)
             or (kind == 'number' and type(value) in (int, float)))
    if not valid or (spec.get('enum') is not None and value not in spec['enum']):
        raise NeedsInput('El valor no coincide con el tipo o las opciones del parámetro')
    json.dumps(value, allow_nan=False)
    return value


def bind(skill, inputs, defaults):
    supplied = bounded_object(inputs)
    schema = validate_schema(skill['schema'])
    properties = schema['properties']
    if set(supplied) - properties.keys():
        raise NeedsInput('Parámetros desconocidos: ' + ', '.join(sorted(set(supplied) - properties.keys())))
    values = {}
    for name, spec in properties.items():
        if name in supplied: value = supplied[name]
        elif name in defaults: value = defaults[name]
        elif 'default' in spec: value = spec['default']
        else: continue
        try: values[name] = _typed(value, spec)
        except ValueError as exc: raise NeedsInput(f'Parámetro {name}: {exc}') from exc
    missing = set(schema['required']) - values.keys()
    if missing: raise NeedsInput('Faltan parámetros: ' + ', '.join(sorted(missing)))

    def render(value):
        if isinstance(value, dict): return {key: render(item) for key, item in value.items()}
        if isinstance(value, list): return [render(item) for item in value]
        if not isinstance(value, str): return value
        names = PARAMETER.findall(value)
        if any(name not in values for name in names):
            raise NeedsInput('Faltan parámetros de plantilla: ' + ', '.join(name for name in names if name not in values))
        whole = PARAMETER.fullmatch(value)
        if whole: return values[whole[1]]
        return PARAMETER.sub(lambda match: str(values[match[1]]), value)

    return render(skill['templates']), values


class SkillMemory:
    def __init__(self, db, lock, procedure_library=None):
        self.db, self.lock, self.procedure_library = db, lock, procedure_library
        with lock, db:
            task_memory.ensure(db)
            selection_policy.ensure(db)
            db.execute('CREATE TABLE IF NOT EXISTS skill_versions (id TEXT, version INTEGER, payload TEXT NOT NULL, PRIMARY KEY(id,version))')
            db.execute('CREATE TABLE IF NOT EXISTS skill_evidence (id TEXT, version INTEGER, operation_id TEXT, payload TEXT NOT NULL, PRIMARY KEY(id,version,operation_id))')
            db.execute('CREATE TABLE IF NOT EXISTS skill_context (project_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS skill_lessons (id TEXT PRIMARY KEY, command_id TEXT NOT NULL, project_id TEXT NOT NULL, created_at REAL NOT NULL, search_text TEXT NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS skill_lessons_scope ON skill_lessons(project_id,command_id,created_at)')
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS skill_search USING fts5(id UNINDEXED, project_id UNINDEXED, text, tokenize='unicode61 remove_diacritics 2')")
            self._migrate()
            db.execute('DELETE FROM skill_search')
            for row in db.execute('SELECT payload FROM skill_versions v WHERE version=(SELECT MAX(version) FROM skill_versions WHERE id=v.id)').fetchall():
                self._index(json.loads(row[0]))

    @contextmanager
    def _write(self):
        with self.lock:
            if self.db.in_transaction:
                yield
            else:
                with self.db:
                    self.db.execute('BEGIN IMMEDIATE')
                    yield

    def _source_plan(self, item):
        provenance = item.get('provenance', {})
        operation = (provenance.get('operation_id') or provenance.get('source_plan_id')) if isinstance(provenance, dict) else None
        if operation and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='learning_plans'").fetchone():
            row = self.db.execute('SELECT payload FROM learning_plans WHERE id=?', (operation,)).fetchone()
            if row: return json.loads(row[0])
        return {}

    def resolve_document_references(self, references):
        if references is None: return []
        if not isinstance(references, list) or len(references) > 24:
            raise ValueError('Referencias documentales inválidas')
        if not references: return []
        resolve = getattr(getattr(self, 'procedure_library', None), 'resolve_references', None)
        if not callable(resolve): raise ValueError('La biblioteca documental no está disponible para validar la procedencia')
        return resolve(references)

    def inherit_document_references(self, target, *sources):
        references = self.resolve_document_references(target.get('document_references'))
        for source in sources:
            for reference in self.resolve_document_references(source.get('document_references')):
                if reference not in references: references.append(reference)
        if references: target['document_references'] = self.resolve_document_references(references)
        return target

    def _origin(self, item, *, lesson=False):
        scope = item.get('memory_scope')
        task = item.get('origin_task_id') or (scope.get('task_id') if isinstance(scope, dict) else None)
        if lesson: task = task or item.get('task_id')
        provenance = item.get('provenance', {})
        if not task and isinstance(provenance, dict):
            task = provenance.get('origin_task_id')
            scope = scope or provenance.get('memory_scope')
            task = task or (scope.get('task_id') if isinstance(scope, dict) else None)
            plan = self._source_plan(item)
            task = task or plan.get('conversation_id')
            scope = scope or plan.get('memory_scope')
        if not task and isinstance(scope, dict): task = scope.get('task_id')
        return task, scope

    def _assert_origin(self, item, *, lesson=False):
        self.inherit_document_references(item)
        task, scope = self._origin(item, lesson=lesson)
        dependencies = item['memory_dependencies'] if 'memory_dependencies' in item else self._source_plan(item).get('memory_dependencies', [])
        dependencies = task_memory.assert_dependencies(self.db, dependencies)
        return task, task_memory.assert_current(self.db, scope, task_id=task), dependencies

    def _origin_current(self, item, *, lesson=False):
        try: task, _, _ = self._assert_origin(item, lesson=lesson)
        except ValueError: return False
        if not task and self._has_forget(): return False
        return not item.get('requires_review') and item.get('auto_select', True) is not False

    def _has_forget(self):
        exists = self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_task_scopes'").fetchone()
        return bool(exists and self.db.execute('SELECT 1 FROM memory_task_scopes WHERE generation>0 OR forgetting=1 LIMIT 1').fetchone())

    def _migrate(self):
        for row in self.db.execute('SELECT id,trigger,title,steps,environment,verified_at FROM learned_actions').fetchall():
            if self.db.execute('SELECT 1 FROM skill_versions WHERE id=?', (row[0],)).fetchone(): continue
            self.insert({'id': row[0], 'version': 1, 'trigger': row[1], 'title': row[2],
                         'templates': json.loads(row[3]), 'schema': validate_schema({}), 'examples': [row[1]],
                         'project_id': '', 'favorite': False, 'environment': row[4],
                         'checks': ['executor_postconditions'], 'provenance': {'source': 'legacy_learned_action', 'legacy_verified_at': row[5]},
                         'created_at': time.time(), 'executable': True})
        tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'recipes' in tables:
            for row in self.db.execute('SELECT id,intent_key,version,status,steps_json,verified_at FROM recipes').fetchall():
                key = 'recipe.' + row[0]
                if self.db.execute('SELECT 1 FROM skill_versions WHERE id=?', (key,)).fetchone(): continue
                self.insert({'id': key, 'version': 1, 'trigger': row[1], 'title': row[1],
                             'templates': [], 'schema': validate_schema({}), 'examples': [], 'project_id': '', 'favorite': False,
                             'environment': '', 'checks': ['executor_postconditions'], 'executable': False,
                             'provenance': {'source': 'legacy_recipe', 'recipe_id': row[0], 'recipe_version': row[2],
                                            'legacy_status': row[3], 'legacy_verified_at': row[5], 'original_steps': json.loads(row[4])},
                             'created_at': time.time()})

    def insert(self, skill):
        skill = copy.deepcopy(skill)
        self._dependencies(skill.get('context_dependencies', []))
        with self._write():
            task, scope, dependencies = self._assert_origin(skill)
            task_memory.assert_context(self.db, scope, skill.get('memory_context_id'), task_id=task)
            skill['memory_dependencies'] = dependencies
            if task:
                skill.update(origin_task_id=task, memory_scope=scope or task_memory.snapshot(self.db, task))
            self.db.execute('INSERT INTO skill_versions VALUES (?,?,?)', (skill['id'], skill['version'], json.dumps(skill, ensure_ascii=False, allow_nan=False)))
            latest = self.db.execute('SELECT payload FROM skill_versions WHERE id=? ORDER BY version DESC LIMIT 1', (skill['id'],)).fetchone()
            self._index(json.loads(latest[0]))
        return self.get(skill['id'], skill['version'])

    def _index(self, skill):
        self.db.execute('DELETE FROM skill_search WHERE id=?', (skill['id'],))
        text = ' '.join([skill['title'], skill['trigger'], skill.get('objective', ''), *skill.get('examples', [])])
        self.db.execute('INSERT INTO skill_search(id,project_id,text) VALUES (?,?,?)', (skill['id'], skill.get('project_id', ''), text))

    def search(self, text, project_id='', limit=24, *, task_id=None):
        project_key(project_id)
        if not isinstance(text, str) or len(text) > 70000 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Búsqueda de habilidades inválida')
        tokens = list(dict.fromkeys(re.findall(r'[^\W_]+', text.casefold(), re.UNICODE)))[:16]
        if not tokens: return []
        query = ' OR '.join('"' + token + '"' for token in tokens)
        with self.lock:
            rows = self.db.execute("SELECT id FROM skill_search WHERE skill_search MATCH ? AND project_id IN ('',?) ORDER BY bm25(skill_search) LIMIT ?",
                                   (query, project_id, limit)).fetchall()
            result = []
            for row in rows:
                try: skill = self.get(row[0], project_id=project_id, task_id=task_id)
                except ValueError: continue
                if self._origin_current(skill) and selection_policy.allowed(skill, skill['selection_policy'], project_id):
                    result.append(skill)
            return result

    def get(self, key, version=None, *, project_id=None, task_id=None):
        with self.lock:
            row = self.db.execute('SELECT payload FROM skill_versions WHERE id=? ' + ('AND version=?' if version is not None else 'ORDER BY version DESC LIMIT 1'),
                                  (key, version) if version is not None else (key,)).fetchone()
            if not row: raise ValueError('Acción aprendida desconocida')
            skill = json.loads(row[0])
            task, scope, dependencies = self._assert_origin(skill)
            if task: skill.update(origin_task_id=task, memory_scope=scope)
            skill['memory_dependencies'] = dependencies
            skill['selection_policy'] = selection_policy.read(self.db, key)
            if 'project_id' in skill['selection_policy']: skill['project_id'] = skill['selection_policy']['project_id']
            evidence = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM skill_evidence WHERE id=? AND version=? ORDER BY rowid', (key, skill['version']))]
            evidence = [item for item in evidence if self._origin_current(item, lesson=True)]
        skill['effect_verified'] = any(item.get('effect_verified') is True for item in evidence)
        skill['goal_confirmed'] = next((item['goal_confirmed'] for item in reversed(evidence) if 'goal_confirmed' in item), False)
        skill['status'] = 'verified' if skill['effect_verified'] else 'candidate'
        skill.setdefault('objective', skill['title'])
        skill.setdefault('intent', skill['trigger'])
        skill['preconditions'] = ['command_preconditions']
        skill['expected_results'] = skill['checks']
        skill['outcome_history'] = [{key: item[key] for key in ('effect_verified', 'verified_at', 'goal_confirmed', 'route', 'inherited_from_version') if key in item}
                                    for item in evidence[-20:]]
        skill['compatibility'] = {'environment': skill['environment'], 'command_ids': [step['command_id'] for step in skill['templates']]}
        skill['verified_at'] = max((item.get('verified_at', 0) for item in evidence), default=0)
        skill['steps'] = copy.deepcopy(skill['templates'])
        try: expected = get_action_env_fingerprint(step['command_id'] for step in skill['templates'])
        except (KeyError, TypeError, ValueError): expected = None
        dependencies = self._dependencies(skill.get('context_dependencies', []))
        applicable_project = skill.get('project_id', '') if project_id is None else project_key(project_id)
        with self.lock:
            invalid = self._invalid_dependencies(dependencies, applicable_project, task_id)
        context_signature = value_hash(dependencies)
        failures = [item for item in evidence if item.get('observed_outcome') == 'failed']
        failure_at = max((item['receipt_created_at'] for item in failures), default=-1)
        successes = [item for item in evidence if item.get('observed_outcome') == 'succeeded'
                     and item.get('validation_environment') == expected and item.get('validation_context') == context_signature]
        quarantined = bool(failures and not any(item['receipt_created_at'] > failure_at for item in successes))
        environment = next((item['validation_environment'] for item in reversed(successes) if item.get('revalidation') is True), skill['environment'])
        environment_matches = bool(skill.get('executable') and expected is not None and expected == environment)
        skill.update(context_matches=not invalid, invalid_context_dependencies=invalid, quarantined=quarantined,
                     command_environment_matches=environment_matches,
                     environment_matches=environment_matches and not invalid and not quarantined)
        if quarantined or invalid or not environment_matches:
            skill['effect_verified'] = False
            skill['status'] = 'quarantined' if quarantined else 'stale' if invalid or skill.get('executable') else 'candidate'
        if not self._origin_current(skill):
            skill.update(status='requires_review', requires_review=True, effect_verified=False, environment_matches=False, auto_select=False)
        if skill['selection_policy']['retired']: skill['auto_select'] = False
        return skill

    def list(self):
        with self.lock:
            ids = [row[0] for row in self.db.execute('SELECT id FROM skill_versions GROUP BY id ORDER BY MAX(rowid) DESC')]
            result = []
            for key in ids:
                try: result.append(self.get(key))
                except ValueError: continue
            return result

    def record(self, key, version, operation_id, evidence):
        if not isinstance(evidence, dict): raise ValueError('Evidencia inválida')
        evidence = copy.deepcopy(evidence)
        json.dumps(evidence, allow_nan=False)
        with self._write():
            row = self.db.execute('SELECT payload FROM skill_versions WHERE id=? AND version=?', (key, version)).fetchone()
            if not row: raise ValueError('Acción aprendida desconocida')
            skill = json.loads(row[0])
            self._assert_origin(skill)
            self.inherit_document_references(evidence, skill, self._source_plan({'provenance': {'operation_id': operation_id}}))
            source = evidence | {'provenance': {'operation_id': operation_id}}
            task, scope, dependencies = self._assert_origin(source, lesson=True)
            task_memory.assert_context(self.db, scope, evidence.get('memory_context_id'), task_id=task)
            evidence['memory_dependencies'] = dependencies
            if task: evidence.update(origin_task_id=task, memory_scope=scope or task_memory.snapshot(self.db, task))
            # Only journal-backed receipts may quarantine or revalidate a version.
            for field in ('observed_outcome', 'receipt_created_at', 'validation_environment', 'validation_context'):
                evidence.pop(field, None)
            observed = self._observed_receipts(skill, evidence)
            if observed:
                outcome, created_at = observed
                dependencies = self._dependencies(skill.get('context_dependencies', []))
                if not self._invalid_dependencies(dependencies, skill.get('project_id', ''), evidence.get('task_id')):
                    try: environment = get_action_env_fingerprint(step['command_id'] for step in skill['templates'])
                    except (KeyError, TypeError, ValueError): environment = None
                    evidence.update(observed_outcome=outcome, receipt_created_at=created_at,
                                    validation_environment=environment, validation_context=value_hash(dependencies))
            if evidence.get('revalidation') is not None and type(evidence['revalidation']) is not bool: raise ValueError('Revalidación inválida')
            self.db.execute('INSERT INTO skill_evidence VALUES (?,?,?,?) ON CONFLICT(id,version,operation_id) DO UPDATE SET payload=excluded.payload',
                            (key, version, operation_id, json.dumps(evidence, ensure_ascii=False)))

    def _inherit_evidence(self, key, version, source_version, *, memory_scope=None, memory_context_id=None):
        # Transfer stored receipts under a fresh request without rebasing their original context.
        with self._write():
            task_memory.assert_context(self.db, memory_scope, memory_context_id)
            source, target = self.get(key, source_version), self.get(key, version)
            fields = ('templates', 'schema', 'checks', 'environment', 'project_id', 'context_dependencies', 'document_references', 'inference')
            if source_version >= version or any(source.get(field, [] if field in ('context_dependencies', 'document_references') else None)
                    != target.get(field, [] if field in ('context_dependencies', 'document_references') else None) for field in fields):
                raise ValueError('La evidencia heredada requiere los mismos pasos y contexto operativo')
            rows = self.db.execute('SELECT operation_id,payload FROM skill_evidence WHERE id=? AND version=?', (key, source_version)).fetchall()
            for operation, raw in rows:
                evidence = json.loads(raw)
                origin = evidence | {'provenance': {'operation_id': operation}}
                if not self._origin_current(origin, lesson=True): continue
                task, scope, dependencies = self._assert_origin(origin, lesson=True)
                self.inherit_document_references(evidence, target)
                if task: evidence.update(origin_task_id=task, memory_scope=scope)
                evidence.update(memory_dependencies=dependencies, inherited_from_version=source_version)
                self.db.execute('INSERT INTO skill_evidence VALUES (?,?,?,?)',
                                (key, version, operation, json.dumps(evidence, ensure_ascii=False)))

    @staticmethod
    def _receipt_inputs(command_id, inputs):
        if command_id != 'axx.artifact.write': return inputs
        # Match CommandService's relative writer representation without rewriting
        # the immutable template or rechecking a file that may no longer exist.
        raw = inputs.get('path')
        if not isinstance(raw, str): raise ValueError('Ruta de escritura inválida')
        parts = raw.replace('\\', '/').split('/')
        reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
        if PureWindowsPath(raw).is_absolute() or PureWindowsPath(raw).drive or any(
                not part or part in ('.', '..') or part.endswith((' ', '.')) or part.split('.')[0].upper() in reserved
                or re.search(r'[<>:"|?*\x00-\x1f]', part) for part in parts):
            raise ValueError('Ruta de escritura relativa inválida')
        return inputs | {'path': '/'.join(parts)}

    def _observed_receipts(self, skill, evidence):
        from ..actions.plan_contract import resolve_inputs
        results = evidence.get('results')
        if not isinstance(results, list) or not results or len(results) > len(skill['templates']): return None
        try: steps, _ = bind(skill, evidence.get('inputs', {}), {})
        except (ValueError, TypeError, KeyError): return None
        tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'command_runs' not in tables: return None
        receipts = []
        for step, result in zip(steps, results):
            if not isinstance(result, dict) or not isinstance(result.get('operation_id'), str): return None
            row = self.db.execute('SELECT state,result_json,created_at FROM command_runs WHERE operation_id=?', (result['operation_id'],)).fetchone()
            if not row: return None
            stored = json.loads(row[1])
            try:
                expected_inputs = self._receipt_inputs(step['command_id'], resolve_inputs(step,
                    [{'state': receipt['state'], 'result': receipt} for receipt, _ in receipts]))
            except (ValueError, TypeError, KeyError): return None
            if (row[0] != stored.get('state') or stored.get('command_id') != step['command_id']
                    or stored.get('inputs') != expected_inputs
                    or any(result.get(name) != stored.get(name) for name in ('state', 'postconditions_passed', 'command_id', 'inputs', 'output', 'error'))):
                return None
            receipts.append((stored, row[2]))
        if any(result.get('state') == 'failed' and result.get('error') for result, _ in receipts):
            return 'failed', max(at for result, at in receipts if result.get('state') == 'failed')
        if (len(receipts) == len(steps) and evidence.get('effect_verified') is True
                and all(result.get('state') == 'succeeded' and result.get('postconditions_passed') is True
                        and bool(result.get('evidence')) for result, _ in receipts)):
            return 'succeeded', max(at for _, at in receipts)
        return None

    @staticmethod
    def _dependencies(value, *, field_only=False):
        if not isinstance(value, list) or len(value) > 32: raise ValueError('Dependencias de contexto inválidas')
        expected = {'field', 'revision'} if field_only else {'project_id', 'field', 'revision'}
        for ref in value:
            if (not isinstance(ref, dict) or set(ref) != expected or not isinstance(ref.get('field'), str) or ref['field'] not in CONTEXT_FIELDS
                    or type(ref.get('revision')) is not int or ref['revision'] < 0):
                raise ValueError('Referencia de contexto inválida')
            if not field_only: project_key(ref['project_id'])
        return value

    def _invalid_dependencies(self, dependencies, project_id, task_id=None):
        invalid, contexts = [], {}
        for ref in dependencies:
            if ref['project_id'] not in contexts: contexts[ref['project_id']] = self.context(ref['project_id'])
            context = contexts[ref['project_id']]
            meta = context['context_meta'].get(ref['field'], {})
            if (ref['project_id'] != project_id or meta.get('revision') != ref['revision']
                    or meta.get('status') != 'active' or ref['field'] not in context
                    or meta.get('task_id') not in (None, '', task_id)):
                invalid.append(copy.deepcopy(ref))
        return invalid

    def context(self, project_id=''):
        project_key(project_id)
        with self.lock:
            row = self.db.execute('SELECT payload FROM skill_context WHERE project_id=?', (project_id,)).fetchone()
        context = {'project_id': project_id, 'aliases': {}, 'defaults': {}, 'last_inputs': {}, 'last_skill_id': ''}
        if row: context.update(json.loads(row[0]))
        context.setdefault('context_revision', 0)
        metadata = context.setdefault('context_meta', {})
        context.setdefault('context_tombstones', {})
        now = time.time()
        for name in CONTEXT_FIELDS & context.keys():
            if name in context['context_tombstones']: continue
            meta = metadata.setdefault(name, {'kind': 'inferred', 'origin': 'legacy_update', 'revision': 0,
                'observed_at': None, 'expires_at': None, 'status': 'active', 'depends_on': [], 'value_hash': value_hash(context[name])})
            if (meta.get('expires_at') is not None and now >= meta['expires_at']) or meta.get('value_hash') != value_hash(context[name]):
                meta['status'] = 'stale'
            try: self._assert_origin(meta, lesson=True)
            except ValueError: meta['status'] = 'stale'
            if not self._origin(meta, lesson=True)[0] and self._has_forget() and not self._empty_context(name, context.get(name), meta):
                meta.update(status='stale', requires_review=True, auto_select=False)
        self._stale_derivatives(context)
        for meta in metadata.values():
            meta['freshness'] = 'stale' if meta['status'] != 'active' else 'fresh' if meta.get('observed_at') is not None else 'unknown'
        return context

    @staticmethod
    def _empty_context(name, value, meta):
        return (name in ('aliases', 'defaults', 'last_inputs', 'last_skill_id') and value in ({}, '')
            and meta.get('origin') == 'legacy_update' and meta.get('revision') == 0 and meta.get('observed_at') is None)

    @staticmethod
    def _stale_derivatives(context):
        metadata = context['context_meta']
        for meta in metadata.values():
            if meta.get('expires_at') is not None and time.time() >= meta['expires_at']:
                meta['status'] = 'stale'
        changed = True
        while changed:
            changed = False
            for name, meta in metadata.items():
                if meta['status'] != 'active': continue
                for ref in meta.get('depends_on', []):
                    source = metadata.get(ref['field'], {})
                    if source.get('status') != 'active' or source.get('revision') != ref['revision']:
                        meta['status'] = 'stale'; changed = True; break

    def update_context(self, project_id, body, *, memory_scope=None, memory_context_id=None, _memory_dependencies=()):
        project_key(project_id)
        body = bounded_object(body, 48000)
        supplied_meta = body.pop('context_meta', {})
        if set(body) - CONTEXT_FIELDS: raise ValueError('Campo de contexto desconocido')
        if not isinstance(supplied_meta, dict) or set(supplied_meta) - body.keys(): raise ValueError('Procedencia de campo desconocido')
        for key, value in body.items():
            if key in ('aliases', 'defaults', 'last_inputs', 'mentioned_objects', 'last_result', 'parameters_modified'):
                bounded_object(value)
            elif key == 'selected_items':
                if not isinstance(value, list) or len(value) > 50 or any(not isinstance(item, str) or len(item) > 2000 for item in value):
                    raise ValueError('Selección de contexto inválida')
            elif not isinstance(value, str) or len(value) > 2000:
                raise ValueError('Referencia de contexto inválida')
        aliases = body.get('aliases', {})
        for name, value in aliases.items():
            if not isinstance(name, str) or not 1 <= len(name) <= 200 or not (isinstance(value, str) or isinstance(value, list) and 1 <= len(value) <= 8 and all(isinstance(item, str) for item in value)):
                raise ValueError('Alias inválido')
            for key in [value] if isinstance(value, str) else value:
                if self.get(key)['project_id'] not in ('', project_id): raise ValueError('Alias de otro proyecto')
        if body.get('last_skill_id') and self.get(body['last_skill_id'])['project_id'] not in ('', project_id):
            raise ValueError('Acción de otro proyecto')
        with self._write():
            validated_scope = task_memory.assert_context(self.db, memory_scope, memory_context_id)
            dependencies = task_memory.assert_dependencies(self.db, list(_memory_dependencies))
            current = self.context(project_id)
            updated = copy.deepcopy(current) | body
            updated['context_revision'] += 1
            for name in body:
                raw = supplied_meta.get(name, {})
                if not isinstance(raw, dict) or set(raw) - {'kind', 'source_id', 'session_id', 'task_id', 'origin', 'observed_at', 'expires_at', 'depends_on'}:
                    raise ValueError('Procedencia de contexto inválida')
                meta = {'kind': 'inferred', 'origin': 'legacy_update', 'observed_at': time.time(),
                        'expires_at': None, 'depends_on': []} | raw
                if meta['kind'] not in ('observed', 'inferred', 'confirmed_user'): raise ValueError('Tipo de procedencia inválido')
                for key in ('source_id', 'session_id', 'task_id', 'origin'):
                    if key in meta and (not isinstance(meta[key], str) or not 1 <= len(meta[key]) <= 200): raise ValueError('Origen de contexto inválido')
                task = validated_scope['task_id'] if validated_scope else meta.get('task_id')
                task_memory.assert_current(self.db, validated_scope, task_id=task)
                if task:
                    meta.update(origin_task_id=task, memory_scope=validated_scope or task_memory.snapshot(self.db, task))
                    if memory_context_id is not None: meta['memory_context_id'] = memory_context_id
                if dependencies: meta['memory_dependencies'] = dependencies
                for key in ('observed_at', 'expires_at'):
                    if meta[key] is not None and (type(meta[key]) not in (int, float) or not math.isfinite(meta[key]) or meta[key] < 0):
                        raise ValueError('Vigencia de contexto inválida')
                self._dependencies(meta['depends_on'], field_only=True)
                if any(ref['field'] == name for ref in meta['depends_on']): raise ValueError('Un campo no puede depender de sí mismo')
                meta.update(revision=updated['context_revision'], status='active', value_hash=value_hash(body[name]))
                updated['context_meta'][name] = meta
                updated['context_tombstones'].pop(name, None)
            self._stale_derivatives(updated)
            invalidated = [{'project_id': project_id, 'field': name, 'revision': meta['revision']}
                           for name, meta in current['context_meta'].items()
                           if name in body or meta['status'] == 'active' and updated['context_meta'][name]['status'] != 'active']
            updated = bounded_object(updated, 48000)
            if 'aliases' in body: updated['alias_provenance'] = {'source': 'user_configuration', 'updated_at': time.time()}
            self.db.execute('INSERT INTO skill_context VALUES (?,?) ON CONFLICT(project_id) DO UPDATE SET payload=excluded.payload', (project_id, json.dumps(updated, ensure_ascii=False)))
        return self.context(project_id) | {'invalidated': invalidated}

    def invalidate_context(self, project_id, body):
        project_key(project_id)
        if (not isinstance(body, dict) or set(body) - {'source_id', 'session_id', 'task_id', 'forget'}
                or len(set(body) & {'source_id', 'session_id', 'task_id'}) != 1 or type(body.get('forget', False)) is not bool):
            raise ValueError('Selecciona una fuente, sesión o tarea de contexto')
        selector = next(key for key in ('source_id', 'session_id', 'task_id') if key in body)
        if not isinstance(body[selector], str) or not 1 <= len(body[selector]) <= 200: raise ValueError('Fuente o sesión inválida')
        if selector == 'task_id': task_memory.state(self.db, body[selector])
        with self._write():
            context = self.context(project_id)
            previous = copy.deepcopy(context['context_meta'])
            affected = {name for name, meta in previous.items() if
                (self._origin(meta, lesson=True)[0] if selector == 'task_id' else meta.get(selector)) == body[selector]}
            while True:
                derived = {name for name, meta in previous.items() if any(ref['field'] in affected for ref in meta.get('depends_on', []))}
                if derived <= affected: break
                affected.update(derived)
            for name in affected: context['context_meta'][name]['status'] = 'stale'
            self._stale_derivatives(context)
            affected.update(name for name, meta in context['context_meta'].items()
                            if previous[name]['status'] == 'active' and meta['status'] != 'active')
            invalidated = [{'project_id': project_id, 'field': name, 'revision': previous[name]['revision']} for name in sorted(affected)]
            context['context_revision'] += 1
            if body.get('forget'):
                for name in affected:
                    context.pop(name, None)
                    context['context_meta'].pop(name, None)
                    context['context_tombstones'][name] = context['context_revision']
            self.db.execute('INSERT INTO skill_context VALUES (?,?) ON CONFLICT(project_id) DO UPDATE SET payload=excluded.payload',
                            (project_id, json.dumps(context, ensure_ascii=False)))
        return self.context(project_id) | {'invalidated': invalidated}

    def forget_task(self, task_id):
        """Clean attributable memory inside the caller's durable forgetting barrier."""
        with self._write():
            if not task_memory.state(self.db, task_id)['forgetting']:
                raise ValueError('La tarea necesita una barrera de olvido pendiente')
            invalidated, forgotten_lessons, withdrawn, unattributed = [], [], [], []
            forgotten_evidence = 0
            forgotten_references = set()
            projects = [row[0] for row in self.db.execute('SELECT project_id FROM skill_context')]
            for project in projects:
                context = self.context(project)
                if any(self._origin(meta, lesson=True)[0] == task_id for meta in context['context_meta'].values()):
                    refs = self.invalidate_context(project, {'task_id': task_id, 'forget': True})['invalidated']
                    invalidated.extend(refs)
                    forgotten_references.update((ref['project_id'], ref['field'], ref['revision']) for ref in refs)
                    context = self.context(project)
                changed = False
                for name, meta in context['context_meta'].items():
                    if not self._origin(meta, lesson=True)[0] and not self._empty_context(name, context.get(name), meta):
                        meta.update(status='stale', requires_review=True, auto_select=False)
                        invalidated.append({'project_id': project, 'field': name, 'revision': meta['revision']})
                        unattributed.append({'kind': 'context', 'project_id': project, 'field': name})
                        changed = True
                if changed:
                    self.db.execute('UPDATE skill_context SET payload=? WHERE project_id=?',
                                    (json.dumps(context, ensure_ascii=False), project))
            for key, raw in self.db.execute('SELECT id,payload FROM skill_lessons').fetchall():
                item = json.loads(raw)
                task, _ = self._origin(item, lesson=True)
                dependent = any((ref['project_id'], ref['field'], ref['revision']) in forgotten_references
                                for ref in item.get('context_dependencies', []))
                if task == task_id or dependent:
                    self.db.execute('DELETE FROM skill_lessons WHERE id=?', (key,))
                    forgotten_lessons.append(key)
                elif not task:
                    item.update(requires_review=True, auto_select=False)
                    self.db.execute('UPDATE skill_lessons SET payload=? WHERE id=?', (json.dumps(item, ensure_ascii=False), key))
                    unattributed.append({'kind': 'lesson', 'id': key})
            affected_skills = set()
            for key, version, raw in self.db.execute('SELECT id,version,payload FROM skill_versions').fetchall():
                item = json.loads(raw)
                task, _ = self._origin(item)
                if task == task_id:
                    self.db.execute('DELETE FROM skill_versions WHERE id=? AND version=?', (key, version))
                    forgotten_evidence += self.db.execute('DELETE FROM skill_evidence WHERE id=? AND version=?', (key, version)).rowcount
                    withdrawn.append({'id': key, 'version': version})
                    affected_skills.add(key)
                elif not task:
                    item.update(requires_review=True, auto_select=False)
                    self.db.execute('UPDATE skill_versions SET payload=? WHERE id=? AND version=?',
                                    (json.dumps(item, ensure_ascii=False), key, version))
                    unattributed.append({'kind': 'skill', 'id': key, 'version': version})
                    affected_skills.add(key)
            for key, version, operation, raw in self.db.execute('SELECT id,version,operation_id,payload FROM skill_evidence').fetchall():
                item = json.loads(raw)
                task, _ = self._origin(item | {'provenance': {'operation_id': operation}}, lesson=True)
                if task == task_id:
                    forgotten_evidence += self.db.execute('DELETE FROM skill_evidence WHERE id=? AND version=? AND operation_id=?',
                                                         (key, version, operation)).rowcount
                elif not task:
                    item.update(requires_review=True, auto_select=False)
                    self.db.execute('UPDATE skill_evidence SET payload=? WHERE id=? AND version=? AND operation_id=?',
                                    (json.dumps(item, ensure_ascii=False), key, version, operation))
                    unattributed.append({'kind': 'skill_evidence', 'id': key, 'version': version, 'operation_id': operation})
            for key in affected_skills:
                self.db.execute('DELETE FROM skill_search WHERE id=?', (key,))
                row = self.db.execute('SELECT payload FROM skill_versions WHERE id=? ORDER BY version DESC LIMIT 1', (key,)).fetchone()
                if row:
                    item = json.loads(row[0])
                    if not item.get('requires_review'): self._index(item)
            removed_ids = {item['id'] for item in withdrawn
                if not self.db.execute('SELECT 1 FROM skill_versions WHERE id=?', (item['id'],)).fetchone()}
            for project in projects:
                context = self.context(project)
                aliases = context.get('aliases', {})
                filtered = {}
                for name, targets in aliases.items():
                    if isinstance(targets, list):
                        kept = [key for key in targets if key not in removed_ids]
                        if kept: filtered[name] = kept
                    elif targets not in removed_ids: filtered[name] = targets
                if filtered == aliases: continue
                previous = copy.deepcopy(context['context_meta'])
                context['aliases'] = filtered
                context['context_revision'] += 1
                meta = context['context_meta'].get('aliases')
                if meta:
                    invalidated.append({'project_id': project, 'field': 'aliases', 'revision': meta['revision']})
                    forgotten_references.add((project, 'aliases', meta['revision']))
                    meta.update(revision=context['context_revision'], value_hash=value_hash(filtered))
                self._stale_derivatives(context)
                invalidated.extend({'project_id': project, 'field': name, 'revision': previous[name]['revision']}
                    for name, meta in context['context_meta'].items()
                    if previous[name]['status'] == 'active' and meta['status'] != 'active')
                self.db.execute('UPDATE skill_context SET payload=? WHERE project_id=?',
                                (json.dumps(context, ensure_ascii=False), project))
            for key, raw in self.db.execute('SELECT id,payload FROM skill_lessons').fetchall():
                if any((ref['project_id'], ref['field'], ref['revision']) in forgotten_references
                       for ref in json.loads(raw).get('context_dependencies', [])):
                    self.db.execute('DELETE FROM skill_lessons WHERE id=?', (key,))
                    forgotten_lessons.append(key)
            return {'task_id': task_id, 'invalidated': invalidated, 'forgotten_lessons': forgotten_lessons,
                    'withdrawn_skills': withdrawn, 'forgotten_skill_evidence': forgotten_evidence,
                    'unattributed': unattributed, 'command_journal_preserved': True}

    def _lesson_receipt(self, operation_id, state):
        if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', operation_id):
            raise ValueError('Selecciona una operación real del diario')
        row = self.db.execute('SELECT state,result_json,created_at FROM command_runs WHERE operation_id=?', (operation_id,)).fetchone()
        if not row: raise ValueError('La operación no existe en el diario')
        receipt = json.loads(row[1])
        if row[0] != state or receipt.get('state') != state:
            raise ValueError('La operación no tiene el resultado observado requerido')
        if state == 'failed' and not receipt.get('error'):
            raise ValueError('Falta el error observado de la operación')
        if state == 'succeeded':
            action = self.db.execute('SELECT state,result_json FROM operations WHERE operation_id=?', (receipt.get('action_operation_id'),)).fetchone()
            actual = json.loads(action[1]) if action and action[1] else {}
            if (receipt.get('postconditions_passed') is not True or not receipt.get('evidence')
                    or not action or action[0] != 'succeeded' or actual.get('postconditions_passed') is not True
                    or actual.get('output') != receipt.get('output')):
                raise ValueError('La prueba necesita postcondiciones comprobadas por el ejecutor')
        parent = None
        tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'learning_plans' in tables:
            found = self.db.execute("""SELECT payload FROM learning_plans WHERE EXISTS
                (SELECT 1 FROM json_each(json_extract(payload,'$.step_records')) r
                 WHERE json_extract(r.value,'$.operation_id')=?) LIMIT 1""", (operation_id,)).fetchone()
            if found: parent = json.loads(found[0])
        return receipt, row[2], parent

    def record_lesson(self, body):
        body = bounded_object(body, 8000)
        if set(body) - {'operation_id', 'hypothesis', 'user_correction', 'verification_operation_id', 'project_id', 'task_id', 'context_dependencies', 'allow_provider', 'memory_scope', 'memory_context_id'}:
            raise ValueError('Campo de incidente desconocido')
        if type(body.get('allow_provider', False)) is not bool: raise ValueError('El permiso de envío debe ser booleano')
        hypothesis, correction = body.get('hypothesis'), body.get('user_correction', '')
        if not isinstance(hypothesis, str) or not 1 <= len(hypothesis.strip()) <= 1000:
            raise ValueError('Describe una hipótesis explícita de hasta mil caracteres')
        if not isinstance(correction, str) or len(correction) > 1000:
            raise ValueError('Corrección humana inválida')
        with self._write():
            failure, failure_at, parent = self._lesson_receipt(body.get('operation_id'), 'failed')
            sources = [failure, parent or {}]
            documents = self.inherit_document_references({}, *sources)
            project = project_key(body.get('project_id', parent.get('project_id', '') if parent else ''))
            if parent and parent.get('project_id', '') != project:
                raise ValueError('La operación pertenece a otro proyecto')
            task = body.get('task_id', failure.get('conversation_id'))
            if task is not None and (not isinstance(task, str) or not 1 <= len(task) <= 160):
                raise ValueError('Tarea inválida')
            if failure.get('conversation_id') not in (None, task):
                raise ValueError('La operación pertenece a otra tarea')
            source_scope = (parent or {}).get('memory_scope') or failure.get('memory_scope')
            source_context = (parent or {}).get('memory_context_id') or failure.get('memory_context_id')
            task_memory.assert_current(self.db, source_scope, task_id=task)
            task_memory.assert_dependencies(self.db, (parent or {}).get('memory_dependencies', []) + failure.get('memory_dependencies', []))
            selected_scope = body.get('memory_scope', source_scope)
            selected_context = body.get('memory_context_id', source_context)
            selected_scope = task_memory.assert_context(self.db, selected_scope, selected_context, task_id=task)
            dependencies = self._dependencies(body.get('context_dependencies', []))
            if self._invalid_dependencies(dependencies, project, task):
                raise ValueError('El contexto del incidente cambió; conserva el recibo y revisa sus referencias')
            command = failure['command_id']
            environment = get_action_env_fingerprint([command])
            verification = None
            if body.get('verification_operation_id') is not None:
                trial, trial_at, trial_parent = self._lesson_receipt(body['verification_operation_id'], 'succeeded')
                if (trial['command_id'] != command or trial_at <= failure_at
                        or trial.get('conversation_id') != failure.get('conversation_id')
                        or trial_parent and trial_parent.get('project_id', '') != project):
                    raise ValueError('La prueba debe ser posterior, del mismo comando y ámbito')
                verification = {'operation_id': trial['operation_id'], 'receipt_sha256': value_hash(trial),
                                'status': 'verified_test', 'proves_cause': False}
                sources.extend((trial, trial_parent or {}))
                self.inherit_document_references(documents, trial, trial_parent or {})
                task_memory.assert_current(self.db, trial.get('memory_scope'), task_id=task)
            error = failure['error']
            symptom = error.get('message', error.get('code', 'Fallo registrado')) if isinstance(error, dict) else str(error)
            item = {'id': 'lesson.' + value_hash(body)[:32], 'command_id': command, 'project_id': project, 'task_id': task,
                'source_operation_id': failure['operation_id'], 'source_receipt_sha256': value_hash(failure),
                'symptom': symptom[:300], 'error_code': str(error.get('code', 'COMMAND_FAILED'))[:80] if isinstance(error, dict) else 'COMMAND_FAILED',
                'hypothesis': hypothesis.strip(), 'cause_confirmed': False, 'cause_status': 'unconfirmed_hypothesis',
                'user_correction': correction, 'correction_provenance': 'confirmed_user' if correction else None,
                'verification': verification, 'created_at': time.time(), 'context_dependencies': dependencies,
                'command_environment': environment, 'environment_scope': 'registered_command_at_recording_not_historical_app_version',
                'provenance': {'source': 'manual_incident', 'source_plan_id': parent['operation_id'] if parent else None,
                    'scope_source': 'journal' if parent else 'user_selection'},
                'allow_provider': body.get('allow_provider', False), 'permissions_granted': False, 'preference_inferred': False}
            if task:
                item.update(origin_task_id=task, memory_scope=selected_scope or task_memory.snapshot(self.db, task))
                if selected_context is not None: item['memory_context_id'] = selected_context
            dependencies = [ref for source in sources for ref in source.get('memory_dependencies', [])]
            item['memory_dependencies'] = task_memory.assert_dependencies(self.db, list({value_hash(ref):ref for ref in dependencies}.values()))
            self.inherit_document_references(item, documents)
            payload = json.dumps(item, ensure_ascii=False, allow_nan=False)
            if len(payload) > 3000: raise ValueError('Acorta la ficha: el incidente excede tres mil caracteres')
            existing = self.db.execute('SELECT payload FROM skill_lessons WHERE id=?', (item['id'],)).fetchone()
            if existing: return {'allow_provider': False} | json.loads(existing[0])
            if self.db.execute('SELECT COUNT(*) FROM skill_lessons').fetchone()[0] >= 1000:
                raise ValueError('La biblioteca de incidentes está llena; olvida fichas antes de añadir otras')
            text = lesson_search_text(' '.join((command, project, task or '', item['symptom'], item['error_code'], hypothesis, correction)))
            self.db.execute('INSERT INTO skill_lessons VALUES (?,?,?,?,?,?)', (item['id'], command, project, item['created_at'], text, payload))
            self.resolve_document_references(item.get('document_references'))
        return item

    def _lesson_current(self, item, project_id, task_id):
        if not self._origin_current(item, lesson=True): return False
        try: current = get_action_env_fingerprint([item['command_id']])
        except (ValueError, KeyError, TypeError): return False
        return (current == item.get('command_environment')
                and not self._invalid_dependencies(item.get('context_dependencies', []), project_id, task_id))

    def lessons(self, query='', command_id='', limit=3, *, project_id='', task_id=None, allow_provider_only=False):
        project_key(project_id)
        if (not isinstance(query, str) or len(query) > 1000 or not isinstance(command_id, str) or len(command_id) > 128
                or type(limit) is not int or not 1 <= limit <= 3 or type(allow_provider_only) is not bool
                or task_id is not None and (not isinstance(task_id, str) or not 1 <= len(task_id) <= 160)):
            raise ValueError('Consulta de incidentes inválida')
        terms = list(dict.fromkeys(re.findall(r'[^\W_]+', lesson_search_text(query))))[:8]
        where, parameters = ['project_id IN (?,?)'], ['', project_id]
        if command_id: where.append('command_id=?'); parameters.append(command_id)
        if task_id is not None: where.append("json_extract(payload,'$.task_id')=?"); parameters.append(task_id)
        if allow_provider_only: where.append("json_type(payload,'$.allow_provider')='true'")
        for term in terms:
            where.append('search_text LIKE ? ESCAPE \'\\\'')
            parameters.append('%' + term.replace('\\', '\\\\').replace('_', '\\_').replace('%', '\\%') + '%')
        with self.lock:
            rows = self.db.execute('SELECT payload FROM skill_lessons WHERE ' + ' AND '.join(where) + ' ORDER BY created_at DESC LIMIT ?', (*parameters, limit)).fetchall()
            result = []
            for row in rows:
                item = json.loads(row[0])
                try: self._assert_origin(item, lesson=True)
                except ValueError: continue
                item.setdefault('allow_provider', False)
                try: current = get_action_env_fingerprint([item['command_id']])
                except (ValueError, KeyError, TypeError): current = None
                item['environment_matches'] = current is not None and current == item['command_environment']
                item['context_matches'] = not self._invalid_dependencies(item['context_dependencies'], project_id, task_id)
                item['status'] = 'reference' if item['environment_matches'] and item['context_matches'] else 'stale'
                if not self._origin_current(item, lesson=True):
                    item.update(status='stale', requires_review=True, auto_select=False)
                if len(json.dumps(item, ensure_ascii=False)) <= 3500: result.append(item)
            return result

    def forget_lesson(self, lesson_id, *, memory_scope=None, memory_context_id=None):
        if not isinstance(lesson_id, str) or not re.fullmatch(r'lesson\.[a-f0-9]{32}', lesson_id):
            raise ValueError('Identificador de incidente inválido')
        with self._write():
            task_memory.assert_context(self.db, memory_scope, memory_context_id)
            removed = self.db.execute('DELETE FROM skill_lessons WHERE id=?', (lesson_id,)).rowcount
        return {'lesson_id': lesson_id, 'forgotten': bool(removed), 'command_journal_preserved': True}
