"""Versioned skill definitions and project context; execution stays in CommandService."""
import copy
import json
import re
import time

from .procedural_memory import get_action_env_fingerprint


PARAMETER = re.compile(r'\{\{([A-Za-z][A-Za-z0-9_]{0,63})\}\}')


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
            self._migrate()

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
        with self.lock, self.db:
            self.db.execute('INSERT INTO skill_versions VALUES (?,?,?)', (skill['id'], skill['version'], json.dumps(skill, ensure_ascii=False, allow_nan=False)))
        return self.get(skill['id'], skill['version'])

    def get(self, key, version=None):
        with self.lock:
            row = self.db.execute('SELECT payload FROM skill_versions WHERE id=? ' + ('AND version=?' if version is not None else 'ORDER BY version DESC LIMIT 1'),
                                  (key, version) if version is not None else (key,)).fetchone()
            if not row: raise ValueError('Acción aprendida desconocida')
            skill = json.loads(row[0])
            evidence = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM skill_evidence WHERE id=? AND version=?', (key, skill['version']))]
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
        skill['environment_matches'] = bool(skill.get('executable') and expected == skill['environment'])
        return skill

    def list(self):
        with self.lock:
            ids = [row[0] for row in self.db.execute('SELECT id FROM skill_versions GROUP BY id ORDER BY MAX(rowid) DESC')]
            return [self.get(key) for key in ids]

    def record(self, key, version, operation_id, evidence):
        with self.lock, self.db:
            self.db.execute('INSERT INTO skill_evidence VALUES (?,?,?,?) ON CONFLICT(id,version,operation_id) DO UPDATE SET payload=excluded.payload',
                            (key, version, operation_id, json.dumps(evidence, ensure_ascii=False)))

    def context(self, project_id=''):
        project_key(project_id)
        with self.lock:
            row = self.db.execute('SELECT payload FROM skill_context WHERE project_id=?', (project_id,)).fetchone()
        return json.loads(row[0]) if row else {'project_id': project_id, 'aliases': {}, 'defaults': {}, 'last_inputs': {}, 'last_skill_id': ''}

    def update_context(self, project_id, body):
        project_key(project_id)
        body = bounded_object(body)
        allowed = {'aliases', 'defaults', 'last_inputs', 'last_skill_id', 'current_file', 'current_folder', 'current_application', 'current_project',
                   'selected_items', 'mentioned_objects', 'last_result', 'parameters_modified'}
        if set(body) - allowed: raise ValueError('Campo de contexto desconocido')
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
            updated = bounded_object(self.context(project_id) | body)
            if 'aliases' in body: updated['alias_provenance'] = {'source': 'user_configuration', 'updated_at': time.time()}
            self.db.execute('INSERT INTO skill_context VALUES (?,?) ON CONFLICT(project_id) DO UPDATE SET payload=excluded.payload', (project_id, json.dumps(updated, ensure_ascii=False)))
        return updated
