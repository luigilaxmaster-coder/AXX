"""Explicit memory changes over the existing stores; never a second effect executor."""
import copy
from contextlib import contextmanager, ExitStack
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import threading
import uuid

from .chat_store import ident
from .commands import normalized
from .memory import task_memory, selection_policy
from .memory.skill_memory import bounded_object, project_key


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _scope(ref, task_id):
    if not isinstance(ref, dict) or set(ref) != {'task_id', 'generation'} or ref.get('task_id') != task_id:
        raise ValueError('Selecciona la generación exacta de esta sesión')
    if type(ref.get('generation')) is not int or ref['generation'] < 0:
        raise ValueError('Generación de memoria inválida')
    return copy.deepcopy(ref)


def _summary(value):
    """Only counts and opaque IDs survive as cleanup progress, never forgotten text."""
    return {key: item if key in ('invalidated', 'forgotten_lessons', 'withdrawn_skills') else len(item) if isinstance(item, list) else item
            for key, item in value.items() if isinstance(item, (list, int, bool)) and key != 'task_id'}


def _cancel(learning, task_id):
    requests = []
    # Match _run_step's learning -> commands order; callbacks never acquire learning from dispatch.
    with learning.lock, learning.commands.lock:
        for row in learning.db.execute("SELECT payload FROM learning_plans WHERE json_extract(payload,'$.conversation_id')=?", (task_id,)):
            plan = json.loads(row[0])
            learning.events.setdefault(plan['operation_id'], threading.Event()).set()
            learning.pause_events.setdefault(plan['operation_id'], threading.Event()).set()
            if plan.get('active_inference_request_id'):
                request_id = plan['active_inference_request_id']
                requests.append((learning.inference_backends.get(request_id, learning.adapter), request_id))
        for row in learning.commands.db.execute('SELECT operation_id,result_json FROM command_runs').fetchall():
            command = json.loads(row[1])
            if command.get('conversation_id') == task_id and command.get('state') not in ('succeeded', 'failed', 'cancelled', 'unknown', 'expired', 'blocked'):
                learning.commands.cancel(row[0])
    return requests


def _cancel_requests(requests):
    for adapter, request_id in requests:
        try:
            if callable(getattr(adapter, 'cancel', None)): adapter.cancel(request_id)
        except Exception:
            # The durable generation still rejects the late response.
            pass


def _retire_plans(learning, task_id, memory, chat):
    changed = 0
    with learning.lock, learning.commands.lock:
        for row in learning.db.execute('SELECT id,payload FROM learning_plans').fetchall():
            plan = json.loads(row[1])
            owned = plan.get('conversation_id') == task_id
            dependencies = plan.get('context_dependencies', [])
            stale = (any(ref in memory.get('invalidated', []) for ref in dependencies)
                or any(ref.get('id') in memory.get('forgotten_lessons', []) for ref in plan.get('lesson_dependencies', []))
                or any({'id':ref['id'], 'version':ref['version']} in memory.get('withdrawn_skills', []) for ref in plan.get('skill_versions', []))
                or plan.get('memory_context_id') in chat.get('old_connect_ids', []))
            stale = stale or any(ref['task_id'] == task_id for ref in plan.get('memory_dependencies', []))
            if not owned and not stale: continue
            learning.events.setdefault(plan['operation_id'], threading.Event()).set()
            learning.pause_events.setdefault(plan['operation_id'], threading.Event()).set()
            plan.update(memory_forgotten=True, approved_hash=None, context_invalidated=True,
                message='El aprendizaje y el contexto de esta tarea ya no se reutilizan; sus recibos se conservan.')
            if plan.get('state') not in ('succeeded', 'failed', 'unknown', 'cancelled', 'expired', 'blocked'):
                plan.update(state='cancelled', cancel_requested=True)
            if 'resource_bindings' in plan or 'resource_binding_selectors' in plan:
                plan['inputs'] = {}
                for step in plan.get('steps', []): step['inputs'] = {}
                for reference in plan.get('skill_versions', []): reference.pop('inputs', None)
                for record in plan.get('step_records', []): record.pop('resolved_inputs', None)
                plan['goal_spec'] = {'intent': 'Aprendizaje olvidado', 'checks': [], 'criteria': []}
                plan['mission'] = learning._mission(plan)
            for field in ('model_data', 'skill_candidate', 'inference_records', 'operational_context', 'revisions', 'goal_progress', 'resource_bindings', 'resource_binding_selectors'):
                plan.pop(field, None)
            if 'preparation' in plan: plan['preparation'] = {'kind': 'forgotten'}
            learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?',
                (json.dumps(plan, ensure_ascii=False, allow_nan=False), row[0]))
            changed += 1
    return {'plans': changed, 'effect_receipts_preserved': True}


@contextmanager
def _forget_lease(learning, task_id):
    target = Path(learning.commands.executor.db_path).parent / 'memory-forget-locks' / (digest(task_id) + '.lock')
    error = 'El cambio de memoria sigue en curso; consulta de nuevo el mismo ID'
    if os.name == 'nt':
        from .telegram.config import _file_lease
        with ExitStack() as leases:
            try: leases.enter_context(_file_lease(target, error))
            except RuntimeError as exc: raise ValueError(error) from exc
            yield
    else:
        import fcntl
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('a+b') as stream:
            try: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc: raise ValueError(error) from exc
            try: yield
            finally: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def forget_session(learning, task_id, operation_id, memory_scope, **kwargs):
    task_id, operation_id = ident(task_id), ident(operation_id)
    with _forget_lease(learning, task_id):
        return _forget_session(learning, task_id, operation_id, memory_scope, **kwargs)


def _forget_session(learning, task_id, operation_id, memory_scope, *, chats, provider=None, memory=None,
                   memory_context_id=None, request_hash=None):
    task_id, operation_id = ident(task_id), ident(operation_id)
    ref = _scope(memory_scope, task_id)
    request_hash = request_hash or digest({'task_id': task_id, 'operation_id': operation_id,
        'memory_scope': ref, 'memory_context_id': memory_context_id})
    if chats is None: raise ValueError('El repositorio de conversaciones no está disponible')
    with learning.lock, learning.commands.lock:
        current = task_memory.state(learning.db, task_id)
        progress = current.get('result')
        if current.get('operation_id') == operation_id:
            if not progress or progress.get('request_hash') != request_hash:
                raise ValueError('El ID pertenece a otro cambio de memoria')
            if not current['forgetting']: return copy.deepcopy(progress['response'])
        if current.get('operation_id') != operation_id:
            chats.get(task_id)
            task_memory.assert_context(learning.db, ref, memory_context_id, task_id=task_id)
        # Cancel before publishing the barrier so an admitted command sees its event at primitive entry.
        requests = _cancel(learning, task_id)
        with learning.db:
            learning.db.execute('BEGIN IMMEDIATE')
            current = task_memory.begin_forget(learning.db, task_id, operation_id, ref['generation'])
            progress = current.get('result') or {'request_hash': request_hash, 'memory_scope': ref,
                'memory_context_id': memory_context_id, 'stages': {}}
            if progress.get('request_hash') != request_hash: raise ValueError('El ID pertenece a otro cambio de memoria')
            if not current['forgetting']: return progress['response']
            learning.db.execute('UPDATE memory_task_scopes SET result_json=? WHERE task_id=?',
                (json.dumps(progress, allow_nan=False), task_id))
    _cancel_requests(requests)

    def checkpoint(name, callback, *, atomic=False):
        nonlocal progress
        with learning.lock:
            progress = task_memory.state(learning.db, task_id)['result']
            if name in progress['stages']: return progress['stages'][name]
        if atomic:
            with learning.lock, learning.db:
                learning.db.execute('BEGIN IMMEDIATE')
                progress = task_memory.state(learning.db, task_id)['result']
                if name in progress['stages']: return progress['stages'][name]
                value = callback()
                progress['stages'][name] = _summary(value)
                learning.db.execute('UPDATE memory_task_scopes SET result_json=? WHERE task_id=? AND generation=? AND forgetting=1',
                    (json.dumps(progress, allow_nan=False), task_id, current['generation']))
        else:
            value = callback()
            with learning.lock, learning.db:
                learning.db.execute('BEGIN IMMEDIATE')
                progress = task_memory.state(learning.db, task_id)['result']
                progress['stages'].setdefault(name, value)
                learning.db.execute('UPDATE memory_task_scopes SET result_json=? WHERE task_id=? AND generation=? AND forgetting=1',
                    (json.dumps(progress, allow_nan=False), task_id, current['generation']))
        return progress['stages'][name]

    forgotten_memory = checkpoint('memory', lambda: learning.skills.forget_task(task_id), atomic=True)
    if memory is not None:
        checkpoint('procedures', lambda: memory.forget_task(task_id))
    if learning.workshop:
        checkpoint('workshop', lambda: learning.workshop.forget_task(task_id))
    chat_result = checkpoint('chat', lambda: chats.forget_task(task_id, current))
    with learning.lock:
        has_shared = learning.db.execute("SELECT 1 FROM sqlite_master WHERE name='shared_messages'").fetchone()
    if has_shared:
        from .mobile.shared_state import SharedState
        shared = SharedState(learning.commands.executor.db_path)
        shared_result = checkpoint('shared', lambda: shared.forget_task(task_id, current))
        chat_result = chat_result | {key:sorted(set(chat_result.get(key, [])) | set(shared_result.get(key, [])))
            for key in ('old_connect_ids', 'affected_task_ids')}
        chat_result['requires_review'] = chat_result.get('requires_review') or shared_result.get('requires_review')
    checkpoint('plans', lambda: _retire_plans(learning, task_id, forgotten_memory, chat_result), atomic=True)
    if learning.anticipation:
        checkpoint('initiative', lambda: learning.anticipation.forget_task(task_id))
    if provider:
        def cancel_runs():
            old_ids = set(chat_result.get('old_connect_ids', [])); count = 0
            with learning.lock:
                exists = learning.db.execute("SELECT 1 FROM sqlite_master WHERE name='connect_runs'").fetchone()
                runs = [json.loads(row[0]) for row in learning.db.execute('SELECT body_json FROM connect_runs')] if exists else []
            for run in runs:
                scope = run.get('memory_scope') or {}
                if (scope.get('task_id') == task_id and type(scope.get('generation')) is int and scope['generation'] < current['generation']
                        or any(ref.get('task_id') == task_id and type(ref.get('generation')) is int and ref['generation'] < current['generation']
                               for ref in run.get('memory_dependencies', []))
                        or run.get('memory_context_id', run.get('conversation_id')) in old_ids):
                    provider.cancel(run['request_id']); count += 1
            return {'cancelled_runs': count}
        checkpoint('provider', cancel_runs)
    result = {'state': 'applied', 'action': 'forget_session', 'task_id': task_id, 'operation_id': operation_id,
        'memory_scope': {key: current[key] for key in ('task_id', 'generation')},
        'summary': 'Se olvidó el aprendizaje atribuible a esta sesión. Sus archivos y recibos de acciones se conservan.',
        'counts': {name:{key:len(value) if isinstance(value, list) else value for key,value in stage.items()}
                   for name,stage in progress['stages'].items()}, 'coverage': 'owned_attributable_memory_and_context',
        'requires_review': bool(progress['stages']['memory'].get('unattributed') or chat_result.get('requires_review')),
        'external_provider_erasure': False, 'effect_journal_preserved': True, 'draft_preserved': True}
    with learning.lock, learning.db:
        learning.db.execute('BEGIN IMMEDIATE')
        latest = task_memory.state(learning.db, task_id)
        if not latest['forgetting']: return copy.deepcopy(latest['result']['response'])
        progress = latest['result']
        progress['response'] = result
        task_memory.finish_forget(learning.db, current, progress)
        learning.change_revision += 1
    return result


def retry_pending(learning, *, chats, provider=None, memory=None):
    with learning.lock:
        pending = [(row[0], row[1], json.loads(row[2])) for row in learning.db.execute(
            'SELECT task_id,operation_id,result_json FROM memory_task_scopes WHERE forgetting=1 AND result_json IS NOT NULL')]
    return [forget_session(learning, task, operation, progress['memory_scope'], chats=chats, provider=provider, memory=memory,
        memory_context_id=progress.get('memory_context_id'), request_hash=progress['request_hash'])
        for task, operation, progress in pending]


def _action(text):
    if not isinstance(text, str) or not 1 <= len(text) <= 500 or '\n' in text or text.lstrip().startswith(('"', "'", '«', '“', '`')):
        return None
    phrase = normalized(text.strip().rstrip('.!'))
    patterns = {
        'forget_session': r'olvida lo que aprendiste de (?:esta|esa) (?:sesion|conversacion)',
        'restrict_project': r'eso era solo para este proyecto',
        'retire_procedure': r'no uses mas ese procedimiento',
        'prefer_folder': r'hazlo asi de ahora en adelante en esta carpeta',
    }
    return next((action for action, pattern in patterns.items() if re.fullmatch(pattern, phrase)), None)


def _target(learning, task_id, project_id, key, version, operation_id):
    if operation_id is not None:
        plan = learning.get(operation_id)
        if plan.get('conversation_id') != task_id or plan.get('memory_forgotten'):
            raise ValueError('Selecciona un procedimiento vigente de esta conversación')
        references = {(ref['id'], ref['version']) for ref in plan.get('skill_versions', [])}
        if len(references) != 1: raise ValueError('Selecciona un procedimiento concreto para corregirlo')
        resolved_key, resolved_version = next(iter(references))
        if key is not None and (key, version) != (resolved_key, resolved_version):
            raise ValueError('Las referencias de procedimiento no coinciden')
        key, version = resolved_key, resolved_version
    if not isinstance(key, str) or type(version) is not int or version < 1:
        raise ValueError('Selecciona un procedimiento concreto y su versión')
    skill = learning.skills.get(key, version, project_id=project_id, task_id=task_id)
    if skill['version'] != learning.skills.get(key)['version']: raise ValueError('La versión del procedimiento cambió')
    if skill['project_id'] not in ('', project_id): raise ValueError('El procedimiento pertenece a otro proyecto')
    return skill


def preview_change(learning, text, task_id, *, project_id='', operation_id=None, target_skill_id=None,
                   target_skill_version=None, target_operation_id=None, folder=None, chats=None,
                   memory_scope=None, memory_context_id=None):
    action = _action(text)
    if action is None: return {'kind': 'memory_change', 'status': 'not_memory_command'}
    task_id, project_id = ident(task_id), project_key(project_id)
    operation_id = ident(operation_id or uuid.uuid4().hex)
    if chats is None: raise ValueError('Las conversaciones no están disponibles')
    chat = chats.get(task_id)
    with learning.lock:
        ref = task_memory.assert_context(learning.db, memory_scope, memory_context_id, task_id=task_id)
    change = {'operation_id': operation_id, 'action': action, 'task_id': task_id, 'project_id': project_id,
        'memory_scope': ref, 'memory_context_id': memory_context_id, 'target': {'task_id': task_id}, 'policy_revision': 0}
    labels = {'forget_session': 'Olvidar el aprendizaje de «' + chat['title'] + '»',
              'restrict_project': 'Usar este procedimiento sólo en el proyecto actual',
              'retire_procedure': 'Retirar este procedimiento de la selección automática',
              'prefer_folder': 'Preferir este procedimiento en la carpeta actual'}
    if action != 'forget_session':
        try:
            skill = _target(learning, task_id, project_id, target_skill_id, target_skill_version, target_operation_id)
            if action == 'restrict_project' and not project_id: raise ValueError('Indica el proyecto actual antes de reducir el ámbito')
            change['target'] = {'skill_id': skill['id'], 'version': skill['version']}
            with learning.lock: change['policy_revision'] = selection_policy.read(learning.db, skill['id'])['revision']
            if action == 'prefer_folder':
                context = learning._planning_context(project_id, task_id)
                actual = context.get('current_folder')
                if not actual: raise ValueError('Selecciona la carpeta concreta antes de registrar la preferencia')
                from .actions.tools import artifact_path_error
                path = Path(actual)
                if not path.is_absolute() or artifact_path_error(str(path)) or not path.is_dir():
                    raise ValueError('La carpeta actual no es una ruta local vigente')
                actual = str(path.resolve(strict=True))
                if folder is not None and folder != actual: raise ValueError('La carpeta cambió; revisa el ámbito actual')
                change['target']['folder'] = actual
        except ValueError as exc:
            return {'kind': 'memory_change', 'status': 'needs_input', 'summary': str(exc)}
    return {'kind': 'memory_change', 'status': 'ready', 'change': change,
            'review_hash': digest(change), 'summary': labels[action], 'permissions_granted': False}


def apply_change(learning, body, *, chats, provider=None, memory=None):
    if (not isinstance(body, dict) or set(body) != {'change', 'review_hash', 'confirmed'}
            or body['confirmed'] is not True or not isinstance(body['review_hash'], str)):
        raise ValueError('Confirma un cambio de memoria concreto')
    change = bounded_object(body['change'], 16000)
    if set(change) != {'operation_id', 'action', 'task_id', 'project_id', 'memory_scope', 'memory_context_id', 'target', 'policy_revision'}:
        raise ValueError('Cambio de memoria inválido')
    if not hmac.compare_digest(digest(change), body['review_hash']): raise ValueError('La revisión de memoria cambió')
    task, operation = ident(change['task_id']), ident(change['operation_id'])
    project = project_key(change['project_id']); ref = _scope(change['memory_scope'], task)
    action, target = change['action'], change['target']
    if action == 'forget_session':
        if target != {'task_id': task}: raise ValueError('Ámbito de olvido inválido')
        return forget_session(learning, task, operation, ref, chats=chats, provider=provider, memory=memory,
                              memory_context_id=change['memory_context_id'], request_hash=body['review_hash'])
    if action not in ('restrict_project', 'retire_procedure', 'prefer_folder'):
        raise ValueError('Cambio de memoria desconocido')
    fields = {'skill_id', 'version', 'folder'} if action == 'prefer_folder' else {'skill_id', 'version'}
    if not isinstance(target, dict) or set(target) != fields: raise ValueError('Procedimiento de memoria inválido')
    with learning.lock, learning.db:
        learning.db.execute('BEGIN IMMEDIATE')
        task_memory.assert_context(learning.db, ref, change['memory_context_id'], task_id=task)
        skill = _target(learning, task, project, target['skill_id'], target['version'], None)
        if action == 'prefer_folder':
            current = learning._planning_context(project, task).get('current_folder')
            if not current or str(Path(current).resolve(strict=True)) != target['folder']:
                raise ValueError('La carpeta cambió; revisa la preferencia antes de guardarla')
        policy = selection_policy.apply(learning.db, skill, action, project, target.get('folder'), ref,
                                        operation, change['policy_revision'])
    learning.change_revision += 1
    return {'state': 'applied', 'action': action, 'task_id': task, 'operation_id': operation,
            'memory_scope': ref, 'selection_policy': policy, 'permissions_granted': False,
            'summary': 'Cambio explícito de memoria aplicado. No concede permisos ni ejecuta acciones.'}
