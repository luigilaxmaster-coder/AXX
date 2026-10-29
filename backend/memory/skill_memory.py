"""Versioned skill definitions and project context; execution stays in CommandService."""
import copy
from contextlib import nullcontext
import hashlib
import json
import math
import re
import time

from .procedural_memory import get_action_env_fingerprint


PARAMETER = re.compile(r'\{\{([A-Za-z][A-Za-z0-9_]{0,63})\}\}')
CONTEXT_FIELDS = frozenset({'aliases', 'defaults', 'last_inputs', 'last_skill_id', 'current_file', 'current_folder',
    'current_application', 'current_project', 'selected_items', 'mentioned_objects', 'last_result', 'parameters_modified'})


def value_hash(value):
    value = json.loads(json.dumps(value, allow_nan=False))
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def read_skill_state(db, key, version=None, *, project_id=None, task_id=None):
    """Read the same projection without migrations or locks; the caller owns its SQL connection."""
    view = SkillMemory.__new__(SkillMemory)
    view.db, view.lock = db, nullcontext()
    return view.get(key, version, project_id=project_id, task_id=task_id)


def read_context_state(db, project_id=''):
    """Resolve field freshness and dependencies using the caller's serialized SQL connection."""
    view = SkillMemory.__new__(SkillMemory)
    view.db, view.lock = db, nullcontext()
    return view.context(project_id)


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
    def __init__(self, db, lock):
        self.db, self.lock = db, lock
        with lock, db:
            db.execute('CREATE TABLE IF NOT EXISTS skill_versions (id TEXT, version INTEGER, payload TEXT NOT NULL, PRIMARY KEY(id,version))')
            db.execute('CREATE TABLE IF NOT EXISTS skill_evidence (id TEXT, version INTEGER, operation_id TEXT, payload TEXT NOT NULL, PRIMARY KEY(id,version,operation_id))')
            db.execute('CREATE TABLE IF NOT EXISTS skill_context (project_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS skill_search USING fts5(id UNINDEXED, project_id UNINDEXED, text, tokenize='unicode61 remove_diacritics 2')")
            self._migrate()
            db.execute('DELETE FROM skill_search')
            for row in db.execute('SELECT payload FROM skill_versions v WHERE version=(SELECT MAX(version) FROM skill_versions WHERE id=v.id)').fetchall():
                self._index(json.loads(row[0]))

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
        self._dependencies(skill.get('context_dependencies', []))
        with self.lock, self.db:
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
            return [self.get(row[0], project_id=project_id, task_id=task_id) for row in rows]

    def get(self, key, version=None, *, project_id=None, task_id=None):
        with self.lock:
            row = self.db.execute('SELECT payload FROM skill_versions WHERE id=? ' + ('AND version=?' if version is not None else 'ORDER BY version DESC LIMIT 1'),
                                  (key, version) if version is not None else (key,)).fetchone()
            if not row: raise ValueError('Acción aprendida desconocida')
            skill = json.loads(row[0])
            evidence = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM skill_evidence WHERE id=? AND version=? ORDER BY rowid', (key, skill['version']))]
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
        return skill

    def list(self):
        with self.lock:
            ids = [row[0] for row in self.db.execute('SELECT id FROM skill_versions GROUP BY id ORDER BY MAX(rowid) DESC')]
            return [self.get(key) for key in ids]

    def record(self, key, version, operation_id, evidence):
        if not isinstance(evidence, dict): raise ValueError('Evidencia inválida')
        evidence = copy.deepcopy(evidence)
        json.dumps(evidence, allow_nan=False)
        with self.lock, self.db:
            row = self.db.execute('SELECT payload FROM skill_versions WHERE id=? AND version=?', (key, version)).fetchone()
            if not row: raise ValueError('Acción aprendida desconocida')
            skill = json.loads(row[0])
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

    def _observed_receipts(self, skill, evidence):
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
            if (row[0] != stored.get('state') or stored.get('command_id') != step['command_id']
                    or stored.get('inputs') != step['inputs']
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
        self._stale_derivatives(context)
        for meta in metadata.values():
            meta['freshness'] = 'stale' if meta['status'] != 'active' else 'fresh' if meta.get('observed_at') is not None else 'unknown'
        return context

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

    def update_context(self, project_id, body):
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
        with self.lock, self.db:
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
        if (not isinstance(body, dict) or set(body) - {'source_id', 'session_id', 'forget'}
                or len(set(body) & {'source_id', 'session_id'}) != 1 or type(body.get('forget', False)) is not bool):
            raise ValueError('Selecciona una fuente o sesión de contexto')
        selector = 'source_id' if 'source_id' in body else 'session_id'
        if not isinstance(body[selector], str) or not 1 <= len(body[selector]) <= 200: raise ValueError('Fuente o sesión inválida')
        with self.lock, self.db:
            context = self.context(project_id)
            previous = copy.deepcopy(context['context_meta'])
            affected = {name for name, meta in previous.items() if meta.get(selector) == body[selector]}
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
