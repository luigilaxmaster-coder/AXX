"""Human selection constraints; these rules never authorize command execution."""
import hashlib
import json

from . import task_memory


def ensure(db):
    task_memory.ensure(db)
    db.execute('''CREATE TABLE IF NOT EXISTS skill_selection_policy (
        skill_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS skill_selection_operations (
        operation_id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, skill_version INTEGER NOT NULL,
        revision INTEGER NOT NULL, request_hash TEXT NOT NULL)''')


def _stored(db, skill_id):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_selection_policy'").fetchone()
    row = db.execute('SELECT revision,payload FROM skill_selection_policy WHERE skill_id=?', (skill_id,)).fetchone() if exists else None
    return (row[0], json.loads(row[1])) if row else (0, {'retired': False, 'folder_preferences': [], 'origin_scopes': []})


def read(db, skill_id):
    if not isinstance(skill_id, str) or not 1 <= len(skill_id) <= 160: raise ValueError('Habilidad inválida')
    revision, stored = _stored(db, skill_id)
    result = {'revision': revision, 'retired': stored['retired'], 'folder_preferences': stored['folder_preferences']}
    if 'project_id' in stored: result['project_id'] = stored['project_id']
    for scope in stored.get('origin_scopes', []):
        try: task_memory.assert_current(db, scope)
        except ValueError:
            result.update(retired=True, requires_review=True, folder_preferences=[])
            break
    return result


def apply(db, skill, action, project_id, folder, memory_scope, operation_id, expected_revision):
    if not db.in_transaction: raise ValueError('La corrección requiere una transacción del llamador')
    if (not isinstance(skill, dict) or not isinstance(skill.get('id'), str) or not 1 <= len(skill['id']) <= 160
            or type(skill.get('version')) is not int or skill['version'] < 1):
        raise ValueError('Referencia de habilidad inválida')
    if action not in ('restrict_project', 'retire_procedure', 'prefer_folder'):
        raise ValueError('Corrección de selección desconocida')
    if not isinstance(project_id, str) or len(project_id) > 128: raise ValueError('Proyecto inválido')
    if type(expected_revision) is not int or expected_revision < 0: raise ValueError('Revisión de selección inválida')
    if (not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 160
            or not operation_id.strip() or any(ord(char) < 32 for char in operation_id)):
        raise ValueError('Operación de corrección inválida')
    if action == 'prefer_folder':
        if (not isinstance(folder, str) or not 1 <= len(folder) <= 2000 or not folder.strip()
                or any(ord(char) < 32 for char in folder)):
            raise ValueError('Carpeta de preferencia inválida')
    elif folder is not None: raise ValueError('Esta corrección no admite una carpeta')
    request = {'skill_id': skill['id'], 'skill_version': skill['version'], 'action': action,
        'project_id': project_id, 'folder': folder, 'memory_scope': memory_scope, 'expected_revision': expected_revision}
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    previous = db.execute('SELECT request_hash FROM skill_selection_operations WHERE operation_id=?', (operation_id,)).fetchone()
    if previous:
        if previous[0] != digest: raise ValueError('La operación ya contiene otra corrección')
        return read(db, skill['id'])
    scope = task_memory.assert_current(db, memory_scope)
    if scope is None: raise ValueError('La corrección requiere el origen de memoria vigente')
    row = db.execute('SELECT version,payload FROM skill_versions WHERE id=? ORDER BY version DESC LIMIT 1', (skill['id'],)).fetchone()
    if not row or row[0] != skill['version']: raise ValueError('La versión de la habilidad cambió')
    current_skill = json.loads(row[1])
    if current_skill.get('memory_scope') is not None:
        task_memory.assert_current(db, current_skill['memory_scope'], task_id=current_skill.get('origin_task_id'))
    revision, stored = _stored(db, skill['id'])
    if revision != expected_revision: raise ValueError('La revisión de selección cambió')
    effective_project = stored.get('project_id', current_skill.get('project_id', ''))
    if effective_project not in ('', project_id): raise ValueError('La habilidad pertenece a otro proyecto')
    if action == 'restrict_project':
        if not project_id: raise ValueError('Selecciona el proyecto que conservará la habilidad')
        stored['project_id'] = project_id
    elif action == 'retire_procedure': stored['retired'] = True
    else:
        preference = {'project_id': project_id, 'folder': folder}
        if preference not in stored['folder_preferences']: stored['folder_preferences'].append(preference)
    if scope not in stored['origin_scopes']: stored['origin_scopes'].append(scope)
    revision += 1
    db.execute('''INSERT INTO skill_selection_policy VALUES (?,?,?)
        ON CONFLICT(skill_id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload''',
        (skill['id'], revision, json.dumps(stored, ensure_ascii=False, allow_nan=False)))
    db.execute('INSERT INTO skill_selection_operations VALUES (?,?,?,?,?)',
               (operation_id, skill['id'], skill['version'], revision, digest))
    return read(db, skill['id'])


def allowed(skill, rule, project_id, folder=None, automatic=True):
    if type(automatic) is not bool: return False
    effective_project = rule.get('project_id', skill.get('project_id', ''))
    if effective_project not in ('', project_id): return False
    return not automatic or not (rule.get('retired') or rule.get('requires_review')
        or skill.get('requires_review') or skill.get('auto_select', True) is False)


def preferred(rule, project, folder):
    return bool(not rule.get('retired') and not rule.get('requires_review') and folder is not None
                and {'project_id': project, 'folder': folder} in rule.get('folder_preferences', []))
