"""Durable task generations. Mutations belong to the caller's SQL transaction."""
import json
import time


def _identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 160 or not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError('Identificador de tarea u operación inválido')
    return value


def _generation(value):
    if type(value) is not int or value < 0:
        raise ValueError('Generación de memoria inválida')
    return value


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS memory_task_scopes (
        task_id TEXT PRIMARY KEY, generation INTEGER NOT NULL, forgetting INTEGER NOT NULL,
        operation_id TEXT, result_json TEXT, forgotten_at REAL)''')


def state(db, task_id):
    task_id = _identifier(task_id)
    # Read projections also run on command connections initialized before this feature.
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_task_scopes'").fetchone()
    row = db.execute('SELECT generation,forgetting,operation_id,result_json,forgotten_at FROM memory_task_scopes WHERE task_id=?',
                     (task_id,)).fetchone() if exists else None
    result = {'task_id': task_id, 'generation': row[0] if row else 0,
              'forgetting': bool(row[1]) if row else False, 'operation_id': row[2] if row else None,
              'forgotten_at': float(row[4] or 0) if row else 0.0}
    if row and row[3] is not None: result['result'] = json.loads(row[3])
    return result


def snapshot(db, task_id):
    current = state(db, task_id)
    if current['forgetting']: raise ValueError('El olvido de la tarea sigue pendiente')
    return {key: current[key] for key in ('task_id', 'generation')}


def assert_current(db, ref, *, task_id=None):
    if task_id is not None: _identifier(task_id)
    if ref is None:
        if task_id is None: return None
        current = state(db, task_id)
        if current['forgetting'] or current['generation'] != 0:
            raise ValueError('La tarea requiere una referencia de memoria vigente')
        return {'task_id': task_id, 'generation': 0}
    if not isinstance(ref, dict): raise ValueError('Referencia de memoria inválida')
    owner, generation = _identifier(ref.get('task_id')), _generation(ref.get('generation'))
    if task_id is not None and owner != task_id: raise ValueError('La referencia pertenece a otra tarea')
    current = state(db, owner)
    if current['forgetting'] or current['generation'] != generation:
        raise ValueError('La memoria de la tarea cambió; descarta el resultado anterior')
    if 'context_id' in ref:
        _assert_reference_context(db,owner,ref['context_id'])
    return {'task_id': owner, 'generation': generation}


def _assert_reference_context(db, owner, context_id):
    if context_id is not None:
        _identifier(context_id)
    row = None
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_conversations'").fetchone():
        columns = {item[1] for item in db.execute('PRAGMA table_info(chat_conversations)')}
        required = 'memory_context_required' if 'memory_context_required' in columns else '0'
        row = db.execute(f'SELECT connect_id,{required} FROM chat_conversations WHERE id=?',(owner,)).fetchone()
    if (row and ((context_id is not None and context_id!=row[0]) or (row[1] and context_id is None))) or (not row and context_id is not None):
        raise ValueError('El contexto original de una dependencia cambió')


def assert_context(db, ref, context_id, *, task_id=None):
    current = assert_current(db, ref, task_id=task_id)
    if context_id is not None: _identifier(context_id)
    owner = current['task_id'] if current else task_id
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_conversations'").fetchone()
    row = None
    if owner and exists:
        columns = {item[1] for item in db.execute('PRAGMA table_info(chat_conversations)')}
        required = 'memory_context_required' if 'memory_context_required' in columns else '0'
        row = db.execute(f'SELECT connect_id,{required} FROM chat_conversations WHERE id=?', (owner,)).fetchone()
    if row:
        if (context_id is not None and context_id != row[0]) or (row[1] and context_id is None):
            raise ValueError('El contexto de la conversación cambió; descarta el resultado anterior')
        chat_dependencies(db, owner, current['generation'])
    elif context_id is not None:
        raise ValueError('El contexto no pertenece a una conversación vigente')
    return current


def assert_dependencies(db, references):
    if not isinstance(references,list) or len(references)>24:
        raise ValueError('Se admiten hasta 24 dependencias de memoria')
    checked = []
    for reference in references:
        if not isinstance(reference,dict) or set(reference) not in ({'task_id','generation'},{'task_id','generation','context_id'}):
            raise ValueError('Dependencia de memoria inválida')
        scope = {key:reference[key] for key in ('task_id','generation')}
        current = assert_context(db,scope,reference['context_id']) if 'context_id' in reference else assert_current(db,scope)
        if 'context_id' in reference:
            current = dict(current,context_id=reference['context_id'])
        checked.append(current)
    return checked


def capture_context(db, ref, context_id, *, task_id=None):
    """Admit legacy generation-zero callers once; never call this to publish or replay."""
    scope = assert_context(db, ref, context_id, task_id=task_id)
    if scope and context_id is None and db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_conversations'").fetchone():
        row = db.execute('SELECT connect_id FROM chat_conversations WHERE id=?', (scope['task_id'],)).fetchone()
        if row: context_id = row[0]
    return scope, context_id


def chat_dependencies(db, owner, generation):
    tables = {item[0] for item in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    references = []
    for table in ('chat_messages', 'chat_link_messages'):
        if table not in tables or 'memory_dependencies' not in {item[1] for item in db.execute('PRAGMA table_info(' + table + ')')}:
            continue
        condition = ' AND memory_generation=? AND requires_review=0' if table == 'chat_messages' else ''
        params = (owner,generation) if table == 'chat_messages' else (owner,)
        for item in db.execute('SELECT memory_dependencies FROM ' + table + ' WHERE conversation_id=? AND invalidated=0' + condition, params):
            references.extend(json.loads(item[0]))
    if 'chat_links' in tables and 'source_generation' in {item[1] for item in db.execute('PRAGMA table_info(chat_links)')}:
        references.extend({'task_id':item[0], 'generation':item[1]} for item in db.execute('SELECT source_id,source_generation FROM chat_links WHERE conversation_id=?', (owner,)))
    if 'chat_context' in tables and 'memory_dependencies' in {item[1] for item in db.execute('PRAGMA table_info(chat_context)')}:
        group = db.execute('SELECT group_id FROM chat_conversations WHERE id=?', (owner,)).fetchone()[0]
        for item in db.execute('SELECT origin_task_id,memory_generation,memory_dependencies FROM chat_context WHERE group_id=? AND invalidated=0 AND requires_review=0', (group,)):
            references.extend(json.loads(item[2]))
            if item[0]:
                references.append({'task_id':item[0], 'generation':item[1]})
            else:
                for peer in db.execute('SELECT id FROM chat_conversations WHERE group_id=?', (group,)):
                    references.append(snapshot(db,peer[0]))
    if 'shared_messages' in tables and 'memory_dependencies' in {item[1] for item in db.execute('PRAGMA table_info(shared_messages)')}:
        for item in db.execute('SELECT memory_dependencies FROM shared_messages WHERE memory_task_id=? AND memory_generation=? AND invalidated=0 AND requires_review=0', (owner,generation)):
            references.extend(json.loads(item[0]))
    for reference in references:
        assert_current(db, reference)
    unique = {(owner,generation):{'task_id':owner,'generation':generation}}
    for reference in references:
        key = (reference['task_id'],reference['generation'])
        if key not in unique or 'context_id' in reference:
            unique[key] = {field:reference[field] for field in ('task_id','generation','context_id') if field in reference}
    return [unique[key] for key in sorted(unique)]


def begin_forget(db, task_id, operation_id, expected_generation):
    task_id, operation_id = _identifier(task_id), _identifier(operation_id)
    expected_generation = _generation(expected_generation)
    if not db.in_transaction: raise ValueError('El olvido requiere una transacción del llamador')
    current = state(db, task_id)
    if current['operation_id'] == operation_id: return current
    if current['forgetting']: raise ValueError('Ya existe un olvido pendiente para esta tarea')
    if current['generation'] != expected_generation: raise ValueError('La generación de la tarea cambió')
    db.execute('''INSERT INTO memory_task_scopes VALUES (?,?,1,?,NULL,?)
        ON CONFLICT(task_id) DO UPDATE SET generation=excluded.generation,forgetting=1,
        operation_id=excluded.operation_id,result_json=NULL,forgotten_at=excluded.forgotten_at''',
        (task_id, current['generation'] + 1, operation_id, time.time()))
    return state(db, task_id)


def finish_forget(db, ref, result):
    if not db.in_transaction: raise ValueError('El olvido requiere una transacción del llamador')
    if not isinstance(ref, dict): raise ValueError('Referencia de olvido inválida')
    task_id, generation = _identifier(ref.get('task_id')), _generation(ref.get('generation'))
    operation_id = _identifier(ref.get('operation_id'))
    payload = json.dumps(result, ensure_ascii=False, allow_nan=False)
    current = state(db, task_id)
    if current['generation'] != generation or current['operation_id'] != operation_id:
        raise ValueError('La operación de olvido cambió')
    if not current['forgetting']:
        if current.get('result') != result: raise ValueError('El olvido ya tiene otro resultado')
        return current
    db.execute('UPDATE memory_task_scopes SET forgetting=0,result_json=? WHERE task_id=?', (payload, task_id))
    return state(db, task_id)
