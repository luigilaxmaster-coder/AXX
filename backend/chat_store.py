"""Local conversation repository. No provider credentials or automatic execution."""
from __future__ import annotations
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from .memory import task_memory

TTL = 90 * 86400 * 1000
MODES = {'ask', 'auto_safe'}

def ident(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        raise ValueError('Identificador de chat inválido')
    return value

def text(value, limit=10000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('Texto inválido o demasiado largo')
    return value

class ChatStore:
    def __init__(self, path, clock=None):
        self.path, self.clock = str(path), clock or (lambda: time.time()*1000)
        self.stop = threading.Event()
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS chat_conversations(id TEXT PRIMARY KEY, title TEXT NOT NULL, group_id TEXT, mode TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, archived INTEGER NOT NULL DEFAULT 0, draft TEXT NOT NULL DEFAULT '', connect_id TEXT NOT NULL, shared_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chat_messages(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS chat_message_thread ON chat_messages(conversation_id,at);
                CREATE TABLE IF NOT EXISTS chat_groups(id TEXT PRIMARY KEY, title TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chat_context(id TEXT PRIMARY KEY, group_id TEXT NOT NULL, text TEXT NOT NULL, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS chat_attachments(conversation_id TEXT PRIMARY KEY, name TEXT NOT NULL, text TEXT NOT NULL, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS chat_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chat_links(conversation_id TEXT NOT NULL, source_id TEXT NOT NULL, title TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(conversation_id,source_id));
                CREATE TABLE IF NOT EXISTS chat_link_messages(conversation_id TEXT NOT NULL, source_id TEXT NOT NULL, message_id TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(conversation_id,source_id,message_id));
                CREATE TABLE IF NOT EXISTS chat_forget_results(task_id TEXT NOT NULL, generation INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(task_id,generation));
            ''')
            task_memory.ensure(db)
            db.executescript('''
                CREATE TABLE IF NOT EXISTS chat_context_ids(context_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, generation INTEGER NOT NULL);
                CREATE TRIGGER IF NOT EXISTS chat_context_ids_insert AFTER INSERT ON chat_conversations BEGIN
                    INSERT OR IGNORE INTO chat_context_ids VALUES(NEW.connect_id,NEW.id,
                        COALESCE((SELECT generation FROM memory_task_scopes WHERE task_id=NEW.id),0));
                END;
                CREATE TRIGGER IF NOT EXISTS chat_context_ids_update AFTER UPDATE OF connect_id ON chat_conversations
                WHEN NEW.connect_id IS NOT OLD.connect_id BEGIN
                    INSERT OR IGNORE INTO chat_context_ids VALUES(NEW.connect_id,NEW.id,
                        COALESCE((SELECT generation FROM memory_task_scopes WHERE task_id=NEW.id),0));
                END;
            ''')
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='connect_runs'").fetchone():
                for row in db.execute('SELECT body_json FROM connect_runs ORDER BY created_at,request_id'):
                    try:
                        run = json.loads(row[0])
                        scope = run.get('memory_scope') if isinstance(run,dict) else None
                        if (not isinstance(scope,dict) or set(scope) != {'task_id','generation'}
                                or type(scope.get('generation')) is not int or scope['generation'] < 0):
                            continue
                        owner = ident(scope.get('task_id'))
                        context = ident(run.get('memory_context_id'))
                    except (TypeError,ValueError):
                        continue
                    db.execute('INSERT OR IGNORE INTO chat_context_ids VALUES(?,?,?)', (context,owner,scope['generation']))
            # Historical scopes win over the current generation during migration.
            db.execute('''INSERT OR IGNORE INTO chat_context_ids
                SELECT c.connect_id,c.id,COALESCE(s.generation,0) FROM chat_conversations c
                LEFT JOIN memory_task_scopes s ON s.task_id=c.id''')
            additions = {'chat_conversations': {'memory_context_required': 'INTEGER NOT NULL DEFAULT 0'},
                         'chat_messages': {'memory_generation': 'INTEGER NOT NULL DEFAULT 0',
                                           'memory_dependencies': "TEXT NOT NULL DEFAULT '[]'", 'invalidated': 'INTEGER NOT NULL DEFAULT 0',
                                           'requires_review': 'INTEGER NOT NULL DEFAULT 0'},
                         'chat_attachments': {'memory_generation': 'INTEGER NOT NULL DEFAULT 0'},
                         'chat_links': {'source_generation': 'INTEGER NOT NULL DEFAULT 0'},
                         'chat_link_messages': {'memory_dependencies': "TEXT NOT NULL DEFAULT '[]'", 'invalidated': 'INTEGER NOT NULL DEFAULT 0'},
                         'chat_context': {'origin_task_id': 'TEXT', 'origin_message_id': 'TEXT',
                                          'memory_generation': 'INTEGER NOT NULL DEFAULT 0',
                                          'memory_dependencies': "TEXT NOT NULL DEFAULT '[]'",
                                          'requires_review': 'INTEGER NOT NULL DEFAULT 0',
                                          'invalidated': 'INTEGER NOT NULL DEFAULT 0'}}
            for table, columns in additions.items():
                existing = {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')}
                for column, definition in columns.items():
                    if column not in existing:
                        db.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + column + ' ' + definition)
            if 'draft_at' not in {r[1] for r in db.execute('PRAGMA table_info(chat_conversations)')}:
                db.execute('ALTER TABLE chat_conversations ADD COLUMN draft_at REAL NOT NULL DEFAULT 0')
                db.execute('UPDATE chat_conversations SET draft_at=updated')
            db.execute("UPDATE chat_conversations SET mode='ask' WHERE mode NOT IN ('ask','auto_safe')")
            db.execute("UPDATE chat_settings SET value='ask' WHERE key='default_mode' AND value NOT IN ('ask','auto_safe')")
        self.purge()
        self.worker = threading.Thread(target=self._maintenance, daemon=True)
        self.worker.start()

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def close(self):
        self.stop.set()
        self.worker.join(2)

    def _maintenance(self):
        while not self.stop.wait(3600):
            try:
                self.purge()
            except sqlite3.Error:
                import logging
                logging.getLogger(__name__).exception('Chat retention failed')

    def purge(self):
        cutoff = self.clock() - TTL
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            affected = {r[0] for r in db.execute('SELECT DISTINCT conversation_id FROM chat_messages WHERE at<=?', (cutoff,))}
            affected.update(r[0] for r in db.execute('SELECT DISTINCT conversation_id FROM chat_link_messages WHERE at<=?', (cutoff,)))
            affected.update(r[0] for r in db.execute('SELECT conversation_id FROM chat_links WHERE source_id NOT IN (SELECT id FROM chat_conversations WHERE updated>?)', (cutoff,)))
            groups = [r[0] for r in db.execute('SELECT DISTINCT group_id FROM chat_context WHERE at<=?', (cutoff,))]
            for group in groups:
                affected.update(r[0] for r in db.execute('SELECT id FROM chat_conversations WHERE group_id=?', (group,)))
            for cid in affected:
                db.execute('UPDATE chat_conversations SET connect_id=? WHERE id=?', (str(uuid.uuid4()), cid))
            db.execute('DELETE FROM chat_messages WHERE at<=?', (cutoff,))
            db.execute('DELETE FROM chat_context WHERE at<=?', (cutoff,))
            db.execute('DELETE FROM chat_attachments WHERE at<=?', (cutoff,))
            db.execute("UPDATE chat_conversations SET draft='' WHERE draft_at<=?", (cutoff,))
            db.execute('DELETE FROM chat_conversations WHERE updated<=?', (cutoff,))
            db.execute('DELETE FROM chat_messages WHERE conversation_id NOT IN (SELECT id FROM chat_conversations)')
            db.execute('DELETE FROM chat_attachments WHERE conversation_id NOT IN (SELECT id FROM chat_conversations)')
            db.execute('DELETE FROM chat_links WHERE conversation_id NOT IN (SELECT id FROM chat_conversations) OR source_id NOT IN (SELECT id FROM chat_conversations)')
            db.execute('DELETE FROM chat_link_messages WHERE at<=? OR NOT EXISTS (SELECT 1 FROM chat_links l WHERE l.conversation_id=chat_link_messages.conversation_id AND l.source_id=chat_link_messages.source_id)', (cutoff,))
            # Mobile's local mirror must not resurrect expired history.
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'shared_messages' in tables:
                db.execute('DELETE FROM shared_messages WHERE at<=?', (cutoff,))
                db.execute('DELETE FROM shared_events WHERE at<=?', (cutoff/1000,))
            if 'connect_runs' in tables:
                db.execute('DELETE FROM connect_events WHERE request_id IN (SELECT request_id FROM connect_runs WHERE created_at<=?)', (cutoff/1000,))
                db.execute('DELETE FROM connect_runs WHERE created_at<=?', (cutoff/1000,))

    def _new(self, db, body):
        cid = str(uuid.uuid4())
        group = body.get('group_id') or None
        if group and not db.execute('SELECT id FROM chat_groups WHERE id=?', (ident(group),)).fetchone():
            raise ValueError('Grupo desconocido')
        default_mode = (db.execute("SELECT value FROM chat_settings WHERE key='default_mode'").fetchone() or ['ask'])[0]
        mode = body.get('command_mode', default_mode)
        if mode not in MODES:
            raise ValueError('Modo de comandos inválido')
        now = self.clock()
        db.execute('INSERT INTO chat_conversations(id,title,group_id,mode,created,updated,archived,draft,connect_id,shared_id,draft_at) VALUES(?,?,?,?,?,?,0,?,?,?,?)',
                   (cid, text(body.get('title', 'Nueva conversación'), 120), group, mode, now, now,
                    text(body.get('draft', '')), ident(body.get('connect_id') or str(uuid.uuid4())), ident(body.get('shared_id') or str(uuid.uuid4())),now))
        return cid

    @staticmethod
    def _refs_current(db, references):
        for ref in references:
            current = task_memory.state(db, ref['task_id'])
            if current['forgetting'] or current['generation'] != ref['generation']:
                return False
            if ref.get('context_id') is not None:
                row = db.execute('SELECT connect_id FROM chat_conversations WHERE id=?', (ref['task_id'],)).fetchone()
                if not row or row[0] != ref['context_id']: return False
        return True

    def _context_dependencies(self, db, cid, generation):
        references = {(cid, generation, None)}
        group = db.execute('SELECT group_id FROM chat_conversations WHERE id=?', (cid,)).fetchone()[0]
        for message in db.execute('SELECT memory_dependencies FROM chat_messages WHERE conversation_id=? AND memory_generation=? AND invalidated=0 AND requires_review=0', (cid,generation)):
            refs = json.loads(message[0])
            if not self._refs_current(db, refs):
                raise ValueError('El contexto de un mensaje anterior cambió')
            references.update((r['task_id'],r['generation'],r.get('context_id')) for r in refs)
        for link in db.execute('SELECT source_id,source_generation FROM chat_links WHERE conversation_id=?', (cid,)):
            refs = [{'task_id': link['source_id'], 'generation': link['source_generation']}]
            if not self._refs_current(db, refs):
                raise ValueError('El contexto de un hilo vinculado cambió')
            references.update((r['task_id'],r['generation'],r.get('context_id')) for r in refs)
            for message in db.execute('SELECT memory_dependencies FROM chat_link_messages WHERE conversation_id=? AND source_id=? AND invalidated=0', (cid,link['source_id'])):
                refs = json.loads(message[0])
                if not self._refs_current(db, refs):
                    raise ValueError('El contexto de un mensaje vinculado cambió')
                references.update((r['task_id'],r['generation'],r.get('context_id')) for r in refs)
        for note in db.execute('SELECT origin_task_id,memory_generation,memory_dependencies FROM chat_context WHERE group_id=? AND invalidated=0 AND requires_review=0', (group,)):
            refs = json.loads(note['memory_dependencies'])
            if note['origin_task_id']:
                refs.append({'task_id':note['origin_task_id'], 'generation':note['memory_generation']})
            else:
                # Unattributed shared notes depend on the group's current eligibility, not an invented owner.
                refs.extend(task_memory.snapshot(db,r[0]) for r in db.execute('SELECT id FROM chat_conversations WHERE group_id=?', (group,)))
            if not self._refs_current(db, refs):
                raise ValueError('El contexto de una nota compartida cambió')
            references.update((r['task_id'],r['generation'],r.get('context_id')) for r in refs)
        return [{'task_id':owner, 'generation':version} | ({'context_id':context} if context is not None else {})
                for owner,version,context in sorted(references, key=lambda ref:(ref[0],ref[1],ref[2] or ''))]

    @staticmethod
    def _operation_dependencies(db, cid, operation_id):
        operation_id = ident(operation_id)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        found = []
        for table, key, payload in (('learning_plans','id','payload'), ('command_runs','operation_id','result_json')):
            if table in tables:
                row = db.execute(f'SELECT {payload} FROM {table} WHERE {key}=?', (operation_id,)).fetchone()
                if row: found.append(json.loads(row[0]))
        if len(found) != 1 or found[0].get('conversation_id') != cid or found[0].get('memory_forgotten'):
            raise ValueError('El mensaje requiere una operación vigente de esta conversación')
        item = found[0]
        from .actions.artifact_compensation import COMMAND_ACTIONS
        if item.get('command_id') in COMMAND_ACTIONS: return []
        scope = task_memory.assert_context(db, item.get('memory_scope'), item.get('memory_context_id'), task_id=cid)
        refs = task_memory.assert_dependencies(db, item.get('memory_dependencies', []))
        origin = scope
        if origin not in refs: refs.append(origin)
        return refs

    def _legacy_context_review(self, db, cid, seen=None):
        seen = set() if seen is None else seen
        if cid in seen:
            return False
        seen.add(cid)
        current = task_memory.state(db, cid)
        if current['forgetting']:
            return True
        try:
            self._context_dependencies(db, cid, current['generation'])
        except ValueError:
            return True
        return any(self._legacy_context_review(db,r[0],seen) for r in db.execute('SELECT source_id FROM chat_links WHERE conversation_id=?', (cid,)))

    def _messages(self, db, cid, messages, generation=0):
        if not isinstance(messages, list) or len(messages) > 2000:
            raise ValueError('Lote de mensajes inválido')
        for m in messages:
            if not isinstance(m, dict):
                raise ValueError('Mensaje inválido')
            mid, content = ident(m.get('id')), text(m.get('text'), 100000)
            at = m.get('at')
            if type(at) not in (int, float) or not math.isfinite(at) or at > self.clock()+60000:
                raise ValueError('Fecha inválida')
            if at <= self.clock()-TTL:
                continue
            if m.get('role') not in ('user','assistant','notice','system') or m.get('status') not in ('complete','pending','interrupted','error','sent','done','failed'):
                raise ValueError('Rol o estado inválido')
            old = db.execute('SELECT conversation_id,memory_generation,memory_dependencies,invalidated,requires_review,payload FROM chat_messages WHERE id=?', (mid,)).fetchone()
            if old and old[0] != cid:
                raise ValueError('El mensaje pertenece a otro chat')
            if old and (old['memory_generation'] != generation or old['invalidated'] or old['requires_review']
                        or not self._refs_current(db, json.loads(old['memory_dependencies']))):
                raise ValueError('El mensaje pertenece al historial olvidado')
            if old and json.loads(old['payload'])['role'] != m['role']:
                raise ValueError('El rol de un mensaje guardado no puede cambiar')
            dependencies = (json.loads(old['memory_dependencies']) if old else
                            self._context_dependencies(db, cid, generation) if m['role'] in ('assistant','notice') else
                            [{'task_id':cid, 'generation':generation}])
            previous_operation = json.loads(old['payload']).get('operation_id') if old else None
            source_operation = m.get('operation_id', previous_operation)
            if previous_operation is not None and source_operation != previous_operation:
                raise ValueError('La procedencia de un mensaje guardado no puede cambiar')
            if source_operation is not None:
                if m['role'] not in ('assistant','notice'): raise ValueError('Sólo un resultado puede referenciar una operación')
                if source_operation != previous_operation:
                    for ref in self._operation_dependencies(db, cid, source_operation):
                        if ref not in dependencies: dependencies.append(ref)
            payload = {k: m[k] for k in ('id','role','source','status','at','model') if k in m}
            if source_operation is not None: payload['operation_id'] = source_operation
            payload['text'] = content
            db.execute('INSERT INTO chat_messages(id,conversation_id,at,payload,memory_generation,memory_dependencies) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (mid,cid,at,json.dumps(payload,ensure_ascii=False),generation,json.dumps(dependencies)))

    def get(self, cid, include_history=False):
        if type(include_history) is not bool:
            raise ValueError('Lectura de historial inválida')
        self.purge()
        with self.db() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT * FROM chat_conversations WHERE id=?', (ident(cid),)).fetchone()
            if not row:
                raise ValueError('Conversación desconocida o vencida')
            result = dict(row)
            current = task_memory.state(db, cid)
            generation, pending = current['generation'], current['forgetting']
            result['memory_scope'] = {'task_id': cid, 'generation': generation}
            result['context_id'] = row['connect_id']
            result['memory_forgetting'] = pending
            result['agent_profile'] = self._profile(db)
            messages = db.execute('SELECT payload,memory_generation,memory_dependencies,invalidated,requires_review FROM chat_messages WHERE conversation_id=? ORDER BY at,id', (cid,)).fetchall()
            legacy_review = self._legacy_context_review(db,cid)
            unknown = [r['memory_dependencies'] == '[]' and json.loads(r['payload'])['role'] in ('assistant','notice') for r in messages]
            visible = [not pending and not r['invalidated'] and not r['requires_review'] and not (legacy_review and unowned) and r['memory_generation'] == generation
                       and self._refs_current(db, json.loads(r['memory_dependencies'])) for r,unowned in zip(messages,unknown)]
            result['messages'] = [json.loads(r['payload']) for r,active in zip(messages,visible) if active]
            result['history_count'] = sum(not active for active in visible)
            result['review_message_count'] = sum(bool(r['requires_review'] or (legacy_review and unowned)) for r,unowned in zip(messages,unknown))
            result['context'], review = [], []
            for note in db.execute('SELECT * FROM chat_context WHERE group_id=? ORDER BY at,id', (row['group_id'],)):
                origin = task_memory.state(db, note['origin_task_id']) if note['origin_task_id'] else None
                active = (not pending and not note['invalidated'] and not note['requires_review']
                          and self._refs_current(db, json.loads(note['memory_dependencies'])))
                if origin:
                    active = active and not origin['forgetting'] and origin['generation'] == note['memory_generation']
                elif active:
                    active = not any(task_memory.state(db, r[0])['forgetting'] for r in db.execute('SELECT id FROM chat_conversations WHERE group_id=?', (row['group_id'],)))
                if active:
                    result['context'].append(dict(note))
                elif note['requires_review']:
                    review.append(dict(note))
            result['review_context_count'] = len(review)
            attachment = db.execute('SELECT name,text,at,memory_generation FROM chat_attachments WHERE conversation_id=?', (cid,)).fetchone()
            result['attachment'] = {k: attachment[k] for k in ('name','text','at')} if attachment and not pending and attachment['memory_generation'] == generation else None
            result['history_attachment_count'] = int(bool(attachment and result['attachment'] is None))
            result['links'] = []
            for link in db.execute('SELECT * FROM chat_links WHERE conversation_id=? ORDER BY updated,source_id', (cid,)):
                source = task_memory.state(db, link['source_id'])
                if pending or source['forgetting'] or source['generation'] != link['source_generation']:
                    continue
                entry = dict(link)
                source_legacy_review = self._legacy_context_review(db,link['source_id'])
                entry['messages'] = [json.loads(r['payload']) for r in db.execute('SELECT payload,memory_dependencies,invalidated FROM chat_link_messages WHERE conversation_id=? AND source_id=? ORDER BY at,message_id', (cid,link['source_id']))
                                     if not r['invalidated'] and self._refs_current(db,json.loads(r['memory_dependencies']))
                                     and not (source_legacy_review and r['memory_dependencies'] == '[]' and json.loads(r['payload'])['role'] in ('assistant','notice'))]
                result['links'].append(entry)
            if include_history:
                result['history_messages'] = [json.loads(r['payload']) for r,active in zip(messages,visible) if not active]
                result['history_attachment'] = {k: attachment[k] for k in ('name','text','at')} if attachment and result['attachment'] is None else None
                result['review_context'] = review
            return result

    @staticmethod
    def _profile(db):
        row = db.execute("SELECT value FROM chat_settings WHERE key='agent_profile'").fetchone()
        return json.loads(row[0]) if row else {}

    def profile(self):
        with self.db() as db:
            return self._profile(db)

    def by_shared_id(self, shared_id):
        self.purge()
        with self.db() as db:
            rows = db.execute('SELECT id FROM chat_conversations WHERE shared_id=?', (ident(shared_id),)).fetchall()
        if len(rows) != 1:
            raise ValueError('El hilo móvil no corresponde a una conversación guardada única')
        return self.get(rows[0][0])

    def list(self):
        self.purge()
        with self.db() as db:
            return {'conversations':[dict(r) for r in db.execute('SELECT id,title,group_id,mode,updated,archived FROM chat_conversations ORDER BY updated DESC')],
                    'groups':[dict(r) for r in db.execute('SELECT * FROM chat_groups ORDER BY title')],
                    'default_mode':(db.execute("SELECT value FROM chat_settings WHERE key='default_mode'").fetchone() or ['ask'])[0]}

    def operations(self):
        """Recover operation identities across both existing executors; never dispatch."""
        self.purge()
        with self.db() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            results = []
            created_times = {}
            if 'command_runs' in tables:
                for row in db.execute('SELECT result_json,created_at FROM command_runs ORDER BY created_at DESC LIMIT 100'):
                    result = json.loads(row[0])
                    created_times[result['operation_id']] = row[1]
                    results.append(result)
                if 'artifact_compensations' in tables:
                    from .actions.artifact_compensation import project_relationship
                    results = [project_relationship(db, result) for result in results]
            if 'learning_plans' in tables:
                from .action_learning import ActionLearning
                for row in db.execute('SELECT payload FROM learning_plans ORDER BY rowid DESC LIMIT 100'):
                    plan = json.loads(row[0])
                    if 'artifact_compensations' in tables:
                        ActionLearning._project_compensations(plan, db)
                    results.append(plan | {'mission': ActionLearning._mission(plan)})
            for result in results:
                task_id = result.get('conversation_id') or result.get('task_id')
                if not task_id:
                    continue
                context = db.execute('SELECT connect_id,memory_context_required FROM chat_conversations WHERE id=?', (task_id,)).fetchone()
                if context and context['memory_context_required'] and result.get('memory_context_id') != context['connect_id']:
                    result['memory_forgotten'] = True
                current = task_memory.state(db, task_id)
                if not current['generation']:
                    continue
                ref = result.get('memory_scope')
                created = result.get('created_at', created_times.get(result.get('operation_id')))
                forgotten = current.get('forgotten_at')
                if (current['forgetting']
                        or (ref is not None and not isinstance(ref, dict))
                        or (isinstance(ref, dict) and (ref.get('task_id') != task_id or ref.get('generation') != current['generation']))
                        or (ref is None and type(created) not in (int, float))
                        or (type(created) in (int, float) and forgotten is not None and created <= forgotten)):
                    result['memory_forgotten'] = True
            return results

    def forget_task(self, task_id, scope_ref):
        """Invalidate reusable chat memory after the coordinator commits its barrier."""
        task_id = ident(task_id)
        if not isinstance(scope_ref, dict) or scope_ref.get('task_id') != task_id:
            raise ValueError('Referencia de olvido inválida')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = task_memory.state(db, task_id)
            if (type(scope_ref.get('generation')) is not int or current['generation'] <= 0
                    or current['generation'] != scope_ref['generation']
                    or current['operation_id'] != scope_ref.get('operation_id')):
                raise ValueError('La operación de olvido cambió')
            saved = db.execute('SELECT payload FROM chat_forget_results WHERE task_id=? AND generation=?',
                               (task_id, current['generation'])).fetchone()
            if saved:
                return json.loads(saved[0])
            if not current['forgetting']:
                raise ValueError('Falta la barrera de olvido de la tarea')
            row = db.execute('SELECT group_id FROM chat_conversations WHERE id=?', (task_id,)).fetchone()
            if not row:
                raise ValueError('Conversación desconocida')
            groups = {r[0] for r in db.execute("SELECT DISTINCT group_id FROM chat_context WHERE origin_task_id=? OR EXISTS (SELECT 1 FROM json_each(chat_context.memory_dependencies) WHERE json_extract(value,'$.task_id')=?)", (task_id,task_id))}
            if row['group_id']:
                groups.add(row['group_id'])
            affected = {task_id}
            affected.update(r[0] for r in db.execute('SELECT conversation_id FROM chat_links WHERE source_id=?', (task_id,)))
            affected.update(r[0] for r in db.execute("SELECT DISTINCT conversation_id FROM chat_messages WHERE invalidated=0 AND memory_generation=COALESCE((SELECT generation FROM memory_task_scopes WHERE task_id=chat_messages.conversation_id),0) AND EXISTS (SELECT 1 FROM json_each(chat_messages.memory_dependencies) WHERE json_extract(value,'$.task_id')=?)", (task_id,)))
            affected.update(r[0] for r in db.execute("SELECT DISTINCT conversation_id FROM chat_link_messages WHERE invalidated=0 AND EXISTS (SELECT 1 FROM json_each(chat_link_messages.memory_dependencies) WHERE json_extract(value,'$.task_id')=?)", (task_id,)))
            for group in groups:
                changed = db.execute("SELECT 1 FROM chat_context WHERE group_id=? AND invalidated=0 AND ((origin_task_id IS NULL AND requires_review=0) OR origin_task_id=? OR EXISTS (SELECT 1 FROM json_each(chat_context.memory_dependencies) WHERE json_extract(value,'$.task_id')=?)) LIMIT 1", (group,task_id,task_id)).fetchone()
                if changed:
                    affected.update(r[0] for r in db.execute('SELECT id FROM chat_conversations WHERE group_id=?', (group,)))
            legacy_links = db.execute("SELECT conversation_id,source_id,message_id FROM chat_link_messages WHERE invalidated=0 AND memory_dependencies='[]' AND json_extract(payload,'$.role') IN ('assistant','notice')").fetchall()
            while True:
                derived = {r['conversation_id'] for r in legacy_links if r['source_id'] in affected}
                if derived <= affected:
                    break
                affected.update(derived)
            counts = {
                'messages_invalidated': db.execute('SELECT COUNT(*) FROM chat_messages WHERE conversation_id=? AND memory_generation<?', (task_id,current['generation'])).fetchone()[0],
                'attachments_invalidated': db.execute('SELECT COUNT(*) FROM chat_attachments WHERE conversation_id=? AND memory_generation<?', (task_id,current['generation'])).fetchone()[0],
                'link_snapshots_removed': db.execute('SELECT COUNT(*) FROM chat_link_messages WHERE conversation_id=? OR source_id=?', (task_id,task_id)).fetchone()[0],
                'links_removed': db.execute('SELECT COUNT(*) FROM chat_links WHERE conversation_id=? OR source_id=?', (task_id,task_id)).fetchone()[0],
                'notes_invalidated': db.execute("SELECT COUNT(*) FROM chat_context WHERE invalidated=0 AND (origin_task_id=? OR EXISTS (SELECT 1 FROM json_each(chat_context.memory_dependencies) WHERE json_extract(value,'$.task_id')=?))", (task_id,task_id)).fetchone()[0],
                'legacy_notes_review': 0,
                'legacy_messages_review': 0,
                'legacy_snapshots_review': 0,
            }
            for cid in affected - {task_id}:
                counts['legacy_messages_review'] += db.execute("UPDATE chat_messages SET requires_review=1 WHERE conversation_id=? AND memory_generation=? AND invalidated=0 AND requires_review=0 AND memory_dependencies='[]' AND json_extract(payload,'$.role') IN ('assistant','notice')", (cid,task_memory.state(db,cid)['generation'])).rowcount
            for legacy in legacy_links:
                if legacy['source_id'] in affected:
                    counts['legacy_snapshots_review'] += db.execute('UPDATE chat_link_messages SET invalidated=1 WHERE conversation_id=? AND source_id=? AND message_id=?', tuple(legacy)).rowcount
            counts['derived_messages_invalidated'] = db.execute("UPDATE chat_messages SET invalidated=1 WHERE conversation_id<>? AND invalidated=0 AND EXISTS (SELECT 1 FROM json_each(chat_messages.memory_dependencies) WHERE json_extract(value,'$.task_id')=?)", (task_id,task_id)).rowcount
            counts['derived_snapshots_invalidated'] = db.execute("UPDATE chat_link_messages SET invalidated=1 WHERE conversation_id<>? AND source_id<>? AND invalidated=0 AND EXISTS (SELECT 1 FROM json_each(chat_link_messages.memory_dependencies) WHERE json_extract(value,'$.task_id')=?)", (task_id,task_id,task_id)).rowcount
            db.execute("UPDATE chat_context SET invalidated=1 WHERE origin_task_id=? OR EXISTS (SELECT 1 FROM json_each(chat_context.memory_dependencies) WHERE json_extract(value,'$.task_id')=?)", (task_id,task_id))
            for group in groups:
                counts['legacy_notes_review'] += db.execute('SELECT COUNT(*) FROM chat_context WHERE group_id=? AND origin_task_id IS NULL', (group,)).fetchone()[0]
                db.execute('UPDATE chat_context SET requires_review=1 WHERE group_id=? AND origin_task_id IS NULL', (group,))
            db.execute('DELETE FROM chat_link_messages WHERE conversation_id=? OR source_id=?', (task_id,task_id))
            db.execute('DELETE FROM chat_links WHERE conversation_id=? OR source_id=?', (task_id,task_id))
            old_connect_ids = []
            for cid in sorted(affected):
                old = db.execute('SELECT connect_id FROM chat_conversations WHERE id=?', (cid,)).fetchone()
                if old:
                    old_connect_ids.append(old[0])
                    db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?', (str(uuid.uuid4()),cid))
            result = {'task_id': task_id, 'scope_ref': {'task_id': task_id, 'generation': current['generation']},
                      'affected_task_ids': sorted(affected), 'affected_connect_ids': old_connect_ids,
                      'old_connect_ids': old_connect_ids, 'counts': counts,
                      'coverage': {'reusable_chat_memory': 'invalidated', 'local_history': 'retained_for_manual_read',
                                   'legacy_shared_context': 'excluded_pending_review', 'legacy_message_attribution': 'unknown',
                                   'external_copies': 'not_verified'},
                      'requires_review': bool(counts['legacy_notes_review'] or counts['legacy_messages_review'] or counts['legacy_snapshots_review'])}
            db.execute('INSERT INTO chat_forget_results VALUES(?,?,?)',
                       (task_id,current['generation'],json.dumps(result,ensure_ascii=False)))
            return result

    def mutate(self, action, body):
        self.purge()
        if not isinstance(body, dict):
            raise ValueError('Petición de chat inválida')
        cid = body.get('id')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if action == 'migrate':
                old = db.execute("SELECT value FROM chat_settings WHERE key='migration_v4'").fetchone()
                if old and db.execute('SELECT id FROM chat_conversations WHERE id=?',(old[0],)).fetchone():
                    return {'id':old[0], 'created':False}
                cid = self._new(db, body)
                self._messages(db, cid, body.get('messages', []))
                db.execute("INSERT OR REPLACE INTO chat_settings VALUES('migration_v4',?)", (cid,))
            elif action == 'create':
                cid = self._new(db, body)
            elif action in ('save','update','delete'):
                row = db.execute('SELECT * FROM chat_conversations WHERE id=?', (ident(cid),)).fetchone()
                if not row:
                    raise ValueError('Conversación desconocida')
                if action == 'delete' and task_memory.state(db, cid)['forgetting']:
                    raise ValueError('El olvido de la tarea sigue pendiente')
                scope = (task_memory.assert_context(db, body.get('memory_scope'), body.get('memory_context_id'), task_id=cid) if action == 'save' else
                         task_memory.assert_current(db, body.get('memory_scope'), task_id=cid) if action == 'update' else None)
                if action == 'save':
                    self._messages(db, cid, body.get('messages', []), scope['generation'])
                    if 'attachment' in body:
                        item = body['attachment']
                        if item is None:
                            db.execute('DELETE FROM chat_attachments WHERE conversation_id=?',(cid,))
                        else:
                            if not isinstance(item, dict):
                                raise ValueError('Adjunto inválido')
                            at = item.get('at',self.clock())
                            if type(at) not in (int,float) or not math.isfinite(at) or at>self.clock()+60000:
                                raise ValueError('Fecha de adjunto inválida')
                            if at>self.clock()-TTL:
                                db.execute('INSERT OR REPLACE INTO chat_attachments(conversation_id,name,text,at,memory_generation) VALUES(?,?,?,?,?)',(cid,text(item.get('name'),255),text(item.get('text'),200000),at,scope['generation']))
                    draft = text(body.get('draft',row['draft']))
                    draft_at = self.clock() if draft != row['draft'] else row['draft_at']
                    title = row['title']
                    if title == 'Nueva conversación':
                        first = db.execute('SELECT payload FROM chat_messages WHERE conversation_id=? AND memory_generation=? ORDER BY at,id', (cid,scope['generation']))
                        for saved in first:
                            message = json.loads(saved[0])
                            if message['role'] == 'user' and message['text'].strip():
                                title = ' '.join(message['text'].split())[:80]
                                break
                    db.execute('UPDATE chat_conversations SET draft=?,draft_at=?,title=?,updated=? WHERE id=?', (draft,draft_at,title,self.clock(),cid))
                elif action == 'delete':
                    db.execute('DELETE FROM chat_messages WHERE conversation_id=?', (cid,))
                    db.execute('DELETE FROM chat_attachments WHERE conversation_id=?', (cid,))
                    db.execute('DELETE FROM chat_conversations WHERE id=?', (cid,))
                    if db.execute("SELECT name FROM sqlite_master WHERE name='shared_messages'").fetchone():
                        db.execute('DELETE FROM shared_messages WHERE conversation_id=?', (row['shared_id'],))
                        # Events contain copies of message text.
                        db.execute("DELETE FROM shared_events WHERE json_extract(data,'$.conversation_id')=?", (row['shared_id'],))
                else:
                    group = body.get('group_id',row['group_id']) or None
                    if group and not db.execute('SELECT id FROM chat_groups WHERE id=?',(ident(group),)).fetchone():
                        raise ValueError('Grupo desconocido')
                    mode = body.get('command_mode', row['mode'])
                    if mode not in MODES:
                        raise ValueError('Modo inválido')
                    db.execute('UPDATE chat_conversations SET title=?,group_id=?,mode=?,archived=?,connect_id=? WHERE id=?',
                               (text(body.get('title',row['title']),120),group,mode,int(bool(body.get('archived',row['archived']))),str(uuid.uuid4()) if group!=row['group_id'] else row['connect_id'],cid))
            elif action == 'group':
                cid = str(uuid.uuid4())
                db.execute('INSERT INTO chat_groups VALUES(?,?)',(cid,text(body.get('title'),120)))
            elif action in ('group_update','group_delete'):
                group = ident(body.get('id'))
                if action == 'group_update':
                    db.execute('UPDATE chat_groups SET title=? WHERE id=?',(text(body.get('title'),120),group))
                else:
                    db.execute('DELETE FROM chat_groups WHERE id=?',(group,))
                    db.execute('DELETE FROM chat_context WHERE group_id=?',(group,))
                    for r in db.execute('SELECT id FROM chat_conversations WHERE group_id=?',(group,)).fetchall():
                        db.execute('UPDATE chat_conversations SET group_id=NULL,connect_id=? WHERE id=?',(str(uuid.uuid4()),r[0]))
            elif action == 'context':
                group = ident(body.get('group_id'))
                if not db.execute('SELECT id FROM chat_groups WHERE id=?',(group,)).fetchone():
                    raise ValueError('Grupo desconocido')
                owner = body.get('source_task_id')
                if body.get('memory_scope') is not None and not isinstance(body['memory_scope'], dict):
                    raise ValueError('Referencia de memoria inválida')
                if owner is None and isinstance(body.get('memory_scope'), dict):
                    owner = body['memory_scope'].get('task_id')
                scope = None
                if owner is not None:
                    owner = ident(owner)
                    if not db.execute('SELECT id FROM chat_conversations WHERE id=? AND group_id=?', (owner,group)).fetchone():
                        raise ValueError('La nota pertenece a otro ámbito de chat')
                    scope = task_memory.assert_current(db, body.get('memory_scope'), task_id=owner)
                elif any(task_memory.state(db, r[0])['generation'] or task_memory.state(db, r[0])['forgetting']
                         for r in db.execute('SELECT id FROM chat_conversations WHERE group_id=?', (group,))):
                    raise ValueError('La nota requiere una referencia de memoria vigente')
                message_id = body.get('source_message_id')
                dependencies = [scope] if scope else []
                if message_id is not None:
                    origin_message = db.execute('SELECT payload,memory_dependencies,invalidated FROM chat_messages WHERE id=? AND conversation_id=? AND memory_generation=?',
                                                (ident(message_id),owner,scope['generation'])).fetchone() if scope else None
                    if (not origin_message or origin_message['invalidated']
                            or not self._refs_current(db,json.loads(origin_message['memory_dependencies']))
                            or json.loads(origin_message['payload']).get('text') != body.get('text')):
                        raise ValueError('El mensaje de origen no está vigente en este chat')
                    dependencies = json.loads(origin_message['memory_dependencies']) or dependencies
                    if not json.loads(origin_message['memory_dependencies']) and json.loads(origin_message['payload'])['role'] in ('assistant','notice'):
                        dependencies = self._context_dependencies(db,owner,scope['generation'])
                if body.get('remove_id'):
                    db.execute('DELETE FROM chat_context WHERE id=? AND group_id=?',(ident(body['remove_id']),group))
                else:
                    if db.execute('SELECT COUNT(*) FROM chat_context WHERE group_id=? AND invalidated=0 AND requires_review=0',(group,)).fetchone()[0] >= 20:
                        raise ValueError('Máximo 20 notas de contexto por grupo')
                    note = text(body.get('text'),4000)
                    total = db.execute('SELECT COALESCE(SUM(length(text)),0) FROM chat_context WHERE group_id=? AND invalidated=0 AND requires_review=0',(group,)).fetchone()[0]
                    if total+len(note)>12000:
                        raise ValueError('El contexto del grupo admite hasta 12 000 caracteres. Reduce o quita una nota.')
                    db.execute('INSERT INTO chat_context(id,group_id,text,at,origin_task_id,origin_message_id,memory_generation,memory_dependencies) VALUES(?,?,?,?,?,?,?,?)',
                               (str(uuid.uuid4()),group,note,self.clock(),owner,message_id,scope['generation'] if scope else 0,json.dumps(dependencies)))
                for r in db.execute('SELECT id FROM chat_conversations WHERE group_id=?',(group,)).fetchall():
                    db.execute('UPDATE chat_conversations SET connect_id=? WHERE id=?',(str(uuid.uuid4()),r[0]))
            elif action == 'profile':
                limits = {'name':80,'role':240,'context':4000,'instructions':4000}
                if set(body)-set(limits)-{'preferred_commands'}:
                    raise ValueError('Campo de personalización desconocido')
                profile = {key:text(body.get(key,''),limit).strip() for key,limit in limits.items()}
                commands = body.get('preferred_commands',[])
                if not isinstance(commands,list) or len(commands)>20:
                    raise ValueError('Elige hasta 20 comandos preferidos')
                profile['preferred_commands'] = list(dict.fromkeys(ident(v) for v in commands))
                db.execute("INSERT OR REPLACE INTO chat_settings VALUES('agent_profile',?)", (json.dumps(profile,ensure_ascii=False),))
                for row in db.execute('SELECT id FROM chat_conversations').fetchall():
                    db.execute('UPDATE chat_conversations SET connect_id=? WHERE id=?',(str(uuid.uuid4()),row[0]))
            elif action == 'default':
                mode = body.get('command_mode')
                if mode not in MODES:
                    raise ValueError('Modo inválido')
                db.execute("INSERT OR REPLACE INTO chat_settings VALUES('default_mode',?)",(mode,))
            elif action in ('link','unlink'):
                cid, source = ident(cid), ident(body.get('source_id'))
                if cid == source:
                    raise ValueError('Elige otro hilo para vincular contexto')
                if not db.execute('SELECT id FROM chat_conversations WHERE id=?', (cid,)).fetchone():
                    raise ValueError('Conversación desconocida')
                task_memory.assert_current(db, body.get('memory_scope'), task_id=cid)
                if action == 'link':
                    origin = db.execute('SELECT title FROM chat_conversations WHERE id=?', (source,)).fetchone()
                    if not origin:
                        raise ValueError('Hilo desconocido o vencido')
                    source_scope = task_memory.snapshot(db, source)
                    if 'source_memory_scope' in body:
                        task_memory.assert_current(db, body['source_memory_scope'], task_id=source)
                    exists = db.execute('SELECT 1 FROM chat_links WHERE conversation_id=? AND source_id=?', (cid,source)).fetchone()
                    if not exists and db.execute('SELECT COUNT(*) FROM chat_links WHERE conversation_id=?', (cid,)).fetchone()[0] >= 3:
                        raise ValueError('Máximo tres hilos vinculados por chat')
                    # Copy only this thread's completed transcript, never its links or group notes.
                    selected, remaining = [], 4000
                    for row in db.execute('SELECT payload,memory_dependencies,invalidated FROM chat_messages WHERE conversation_id=? AND memory_generation=? ORDER BY at DESC,id DESC LIMIT 30', (source,source_scope['generation'])):
                        dependencies = json.loads(row['memory_dependencies'])
                        if row['invalidated'] or not self._refs_current(db,dependencies):
                            continue
                        message = json.loads(row['payload'])
                        if not dependencies and message['role'] in ('assistant','notice'):
                            dependencies = self._context_dependencies(db,source,source_scope['generation'])
                        if message['role'] not in ('user','assistant') or message['status'] not in ('complete','sent','done'):
                            continue
                        content = message['text'][:remaining]
                        if not content:
                            continue
                        selected.append(({k:message[k] for k in ('id','role','at')} | {'text':content},dependencies))
                        remaining -= len(content)
                        if remaining <= 0:
                            break
                    if not selected:
                        raise ValueError('Este hilo no tiene mensajes guardados y vigentes')
                    db.execute('INSERT OR REPLACE INTO chat_links(conversation_id,source_id,title,updated,source_generation) VALUES(?,?,?,?,?)', (cid,source,origin['title'],self.clock(),source_scope['generation']))
                    db.execute('DELETE FROM chat_link_messages WHERE conversation_id=? AND source_id=?', (cid,source))
                    for message,dependencies in selected:
                        db.execute('INSERT INTO chat_link_messages(conversation_id,source_id,message_id,at,payload,memory_dependencies) VALUES(?,?,?,?,?,?)', (cid,source,message['id'],message['at'],json.dumps(message,ensure_ascii=False),json.dumps(dependencies)))
                else:
                    db.execute('DELETE FROM chat_links WHERE conversation_id=? AND source_id=?', (cid,source))
                    db.execute('DELETE FROM chat_link_messages WHERE conversation_id=? AND source_id=?', (cid,source))
                db.execute('UPDATE chat_conversations SET connect_id=? WHERE id=?', (str(uuid.uuid4()),cid))
            elif action == 'forget':
                db.execute('DELETE FROM chat_messages')
                db.execute('DELETE FROM chat_attachments')
                db.execute('DELETE FROM chat_links')
                db.execute('DELETE FROM chat_link_messages')
                db.execute("UPDATE chat_conversations SET draft='' ")
                for row in db.execute('SELECT id FROM chat_conversations').fetchall():
                    db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?',(str(uuid.uuid4()),row[0]))
                if db.execute("SELECT name FROM sqlite_master WHERE name='shared_messages'").fetchone():
                    db.execute('DELETE FROM shared_messages')
                    db.execute('DELETE FROM shared_events')
            else:
                raise ValueError('Operación de chat desconocida')
            result = {'id':cid,'ok':True}
            if action == 'migrate':
                result['created'] = True
            if cid and db.execute('SELECT id FROM chat_conversations WHERE id=?', (cid,)).fetchone():
                result['memory_scope'] = task_memory.snapshot(db, cid)
        return result
