"""Shared conversation history; SQLite remains owned by the desktop process."""
import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from backend.memory import task_memory


class SharedState:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS shared_messages (
                    id TEXT PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL,
                    at REAL NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL,
                    conversation_id TEXT NOT NULL DEFAULT 'main'
                );
                CREATE TABLE IF NOT EXISTS shared_events (
                    cursor INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL, data TEXT NOT NULL, at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shared_active_conversation (id INTEGER PRIMARY KEY CHECK(id=1), conversation_id TEXT NOT NULL);
                INSERT OR IGNORE INTO shared_active_conversation VALUES(1,'main');
                CREATE TABLE IF NOT EXISTS shared_memory_cutoffs(task_id TEXT PRIMARY KEY, cutoff_ms REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS shared_forget_results(task_id TEXT NOT NULL,generation INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(task_id,generation));
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(shared_messages)')}
            if 'conversation_id' not in columns:
                db.execute("ALTER TABLE shared_messages ADD COLUMN conversation_id TEXT NOT NULL DEFAULT 'main'")
            for name,definition in {'memory_task_id':'TEXT','memory_generation':'INTEGER NOT NULL DEFAULT 0',
                                    'memory_context_id':'TEXT','memory_dependencies':"TEXT NOT NULL DEFAULT '[]'",
                                    'provenance_known':'INTEGER NOT NULL DEFAULT 0','invalidated':'INTEGER NOT NULL DEFAULT 0',
                                    'requires_review':'INTEGER NOT NULL DEFAULT 0'}.items():
                if name not in columns:
                    db.execute('ALTER TABLE shared_messages ADD COLUMN '+name+' '+definition)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _chat(db, conversation_id):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_conversations'").fetchone():
            return None
        rows = db.execute('SELECT * FROM chat_conversations WHERE shared_id=?',(conversation_id,)).fetchall()
        if len(rows)>1:
            raise ValueError('El hilo móvil no corresponde a un chat único')
        return rows[0] if rows else None

    def capture_scope(self, conversation_id):
        with self.connect() as db:
            db.execute('BEGIN')
            chat = self._chat(db,conversation_id)
            if not chat:
                if self._has_forget(db):
                    raise ValueError('Selecciona un chat guardado en la PC para continuar')
                return {}
            reference = task_memory.snapshot(db,chat['id'])
            task_memory.assert_context(db,reference,chat['connect_id'])
            return {'memory_scope':reference,'memory_context_id':chat['connect_id'],
                    'memory_dependencies':task_memory.chat_dependencies(db,chat['id'],reference['generation'])}

    @staticmethod
    def _has_forget(db):
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_task_scopes'").fetchone() and
                    db.execute('SELECT 1 FROM memory_task_scopes WHERE generation>0 LIMIT 1').fetchone())

    @staticmethod
    def _known_message(db, message_id):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_messages'").fetchone():
            return None
        return db.execute('SELECT * FROM chat_messages WHERE id=?',(message_id,)).fetchone()

    def _visible(self, db, row):
        if row['invalidated'] or row['requires_review'] or row['at']<=time.time()*1000-90*86400000:
            return False
        chat = self._chat(db,row['conversation_id'])
        owner = row['memory_task_id'] or (chat['id'] if chat else None)
        if not owner and self._has_forget(db):
            return False
        try:
            if owner:
                task_memory.assert_current(db,{'task_id':owner,'generation':row['memory_generation']})
            for reference in json.loads(row['memory_dependencies']):
                task_memory.assert_current(db,reference)
            if chat and row['role']=='assistant' and not row['provenance_known']:
                if chat['memory_context_required']:
                    return False
                task_memory.assert_context(db,None,None,task_id=chat['id'])
            known = self._known_message(db,row['id'])
            if known and owner == known['conversation_id']:
                if known['invalidated'] or known['requires_review'] or known['memory_generation'] != row['memory_generation']:
                    return False
                for reference in json.loads(known['memory_dependencies']):
                    task_memory.assert_current(db,reference)
        except ValueError:
            return False
        return True

    def merge_messages(self, messages, source, conversation_id='main', activate=False, *, memory_scope=None, memory_context_id=None, memory_dependencies=None):
        if not isinstance(conversation_id, str) or not 1 <= len(conversation_id) <= 160:
            raise ValueError('Invalid conversation')
        if not isinstance(messages, list) or len(messages) > 200:
            raise ValueError('messages debe contener hasta 200 mensajes')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            chat = self._chat(db,conversation_id)
            owner = chat['id'] if chat else None
            if not chat and (memory_scope is not None or memory_context_id is not None):
                raise ValueError('El hilo móvil no corresponde al ámbito de memoria indicado')
            reference = task_memory.assert_context(db,memory_scope,memory_context_id,task_id=owner)
            dependencies = memory_dependencies if memory_dependencies is not None else (task_memory.chat_dependencies(db,owner,reference['generation']) if reference and chat else [])
            if not isinstance(dependencies,list):
                raise ValueError('Invalid memory dependencies')
            for dependency in dependencies:
                task_memory.assert_current(db,dependency)
            if activate:
                db.execute('UPDATE shared_active_conversation SET conversation_id=? WHERE id=1', (conversation_id,))
            for m in messages:
                if not isinstance(m, dict) or not isinstance(m.get('id'), str) or not 1 <= len(m['id']) <= 160:
                    raise ValueError('Invalid message ID')
                if m.get('role') not in ('user', 'assistant', 'system') or not isinstance(m.get('text'), str) or len(m['text']) > 100000:
                    raise ValueError('Invalid message')
                at = m.get('at', time.time()*1000)
                if not isinstance(at, (int, float)) or not math.isfinite(at):
                    raise ValueError('Invalid date')
                if at <= time.time()*1000 - 90*86400000:
                    continue
                old = db.execute('SELECT role,text,conversation_id FROM shared_messages WHERE id=?', (m['id'],)).fetchone()
                if old:
                    if old['role'] != m['role'] or old['text'] != m['text'] or old['conversation_id'] != conversation_id:
                        raise ValueError('Conflicto: el ID ya pertenece a otro mensaje')
                    continue
                status = m.get('status', 'sent')
                if status not in ('sent', 'done', 'complete', 'error', 'pending', 'failed'):
                    status = 'sent'
                msg = dict(id=m['id'], role=m['role'], text=m['text'], at=at, source=source, status=status, conversation_id=conversation_id)
                known = self._known_message(db,m['id'])
                if known and owner and (known['conversation_id'] != owner or json.loads(known['payload'])['text'] != m['text'] or json.loads(known['payload'])['role'] != m['role']):
                    raise ValueError('El mensaje no coincide con el historial autorizado del chat')
                generation = known['memory_generation'] if known else reference['generation'] if reference else 0
                refs = json.loads(known['memory_dependencies']) if known else dependencies if m['role']=='assistant' else [reference] if reference else []
                provenance = bool(known or (memory_dependencies is not None and reference))
                cutoff = db.execute('SELECT cutoff_ms FROM shared_memory_cutoffs WHERE task_id=?',(owner,)).fetchone() if owner else None
                before_forget = bool(cutoff and at<=cutoff[0] and not provenance)
                unknown_assistant = bool(chat and chat['memory_context_required'] and m['role']=='assistant' and not provenance)
                invalidated = bool((known and known['invalidated']) or before_forget)
                review = bool((known and known['requires_review']) or unknown_assistant or (before_forget and not known) or (not owner and self._has_forget(db)))
                db.execute('INSERT INTO shared_messages(id,role,text,at,source,status,conversation_id,memory_task_id,memory_generation,memory_context_id,memory_dependencies,provenance_known,invalidated,requires_review) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (msg['id'],msg['role'],msg['text'],at,source,status,conversation_id,owner,generation,memory_context_id,json.dumps(refs),int(provenance),int(invalidated),int(review)))
                db.execute('INSERT INTO shared_events(type,data,at) VALUES(?,?,?)',
                           ('message', json.dumps(msg, ensure_ascii=False), time.time()))
        return self.snapshot(conversation_id)

    def forget_task(self, task_id, scope_ref=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = task_memory.state(db,task_id)
            if current['generation']<=0 or (scope_ref is not None and (not isinstance(scope_ref,dict) or scope_ref.get('task_id')!=task_id or type(scope_ref.get('generation')) is not int or scope_ref['generation']!=current['generation'])):
                raise ValueError('La generación del olvido móvil cambió')
            saved = db.execute('SELECT payload FROM shared_forget_results WHERE task_id=? AND generation=?',(task_id,current['generation'])).fetchone()
            if saved:
                return json.loads(saved[0])
            if not current['forgetting']:
                raise ValueError('Falta la barrera de olvido de la tarea')
            chat_result = db.execute('SELECT payload FROM chat_forget_results WHERE task_id=? AND generation=?',(task_id,current['generation'])).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_forget_results'").fetchone() else None
            chat_affected = set(json.loads(chat_result[0])['affected_task_ids']) if chat_result else {task_id}
            affected = set(chat_affected)
            counts = {'messages_invalidated':0,'legacy_messages_review':0,'unmapped_legacy_review':0}
            rows = db.execute('SELECT * FROM shared_messages').fetchall()
            for row in rows:
                chat = self._chat(db,row['conversation_id'])
                owner = row['memory_task_id'] or (chat['id'] if chat else None)
                if not owner:
                    counts['unmapped_legacy_review'] += db.execute('UPDATE shared_messages SET requires_review=1 WHERE id=? AND requires_review=0',(row['id'],)).rowcount
                    continue
                derived = any(ref['task_id']==task_id for ref in json.loads(row['memory_dependencies']))
                if owner==task_id or derived:
                    counts['messages_invalidated'] += int(not row['invalidated'])
                    review = not row['provenance_known']
                    db.execute('UPDATE shared_messages SET invalidated=1,requires_review=MAX(requires_review,?) WHERE id=?',(int(review),row['id']))
                    if not row['invalidated'] and not row['requires_review'] and row['memory_generation']==task_memory.state(db,owner)['generation']:
                        affected.add(owner)
            for row in rows:
                chat = self._chat(db,row['conversation_id'])
                owner = row['memory_task_id'] or (chat['id'] if chat else None)
                if owner in affected and row['role']=='assistant' and not row['provenance_known']:
                    counts['legacy_messages_review'] += db.execute('UPDATE shared_messages SET requires_review=1 WHERE id=? AND requires_review=0',(row['id'],)).rowcount
            old_connect_ids = []
            for owner in sorted(affected):
                db.execute('INSERT INTO shared_memory_cutoffs VALUES(?,?) ON CONFLICT(task_id) DO UPDATE SET cutoff_ms=MAX(cutoff_ms,excluded.cutoff_ms)',(owner,current['forgotten_at']*1000))
                if owner not in chat_affected:
                    chat = db.execute('SELECT connect_id FROM chat_conversations WHERE id=?',(owner,)).fetchone()
                    if chat:
                        old_connect_ids.append(chat[0])
                        db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?',(str(uuid.uuid4()),owner))
            result = {'task_id':task_id,'scope_ref':{'task_id':task_id,'generation':current['generation']},
                      'affected_task_ids':sorted(affected),'old_connect_ids':old_connect_ids,'counts':counts,
                      'requires_review':bool(counts['legacy_messages_review'] or counts['unmapped_legacy_review']),
                      'coverage':{'shared_messages':'invalidated','shared_events':'filtered_without_cursor_reset',
                                  'local_history':'retained','unmapped_legacy_attribution':'unknown','external_copies':'not_verified'}}
            db.execute('INSERT INTO shared_forget_results VALUES(?,?,?)',(task_id,current['generation'],json.dumps(result)))
            return result

    def snapshot(self, conversation_id=None):
        with self.connect() as db:
            db.execute('BEGIN')
            db.execute('DELETE FROM shared_messages WHERE at<=?', (time.time()*1000-90*86400000,))
            db.execute('DELETE FROM shared_events WHERE at<=?', (time.time()-90*86400,))
            if conversation_id is None:
                conversation_id = db.execute('SELECT conversation_id FROM shared_active_conversation WHERE id=1').fetchone()[0]
            cursor = db.execute('SELECT COALESCE(MAX(cursor),0) FROM shared_events').fetchone()[0]
            rows = db.execute('SELECT * FROM (SELECT * FROM shared_messages WHERE conversation_id=? ORDER BY at DESC,id DESC LIMIT 200) ORDER BY at,id', (conversation_id,)).fetchall()
            visible = [self._visible(db,row) for row in rows]
            fields = ('id','role','text','at','source','status','conversation_id')
            result = {'conversation_id':conversation_id, 'cursor':cursor,
                      'messages':[{key:row[key] for key in fields} for row,active in zip(rows,visible) if active],
                      'history_count':sum(not active for active in visible)}
        return result

    def events(self, cursor):
        if type(cursor) is not int or cursor < 0:
            raise ValueError('Invalid cursor')
        with self.connect() as db:
            db.execute('BEGIN')
            rows = db.execute('SELECT cursor,type,data FROM shared_events WHERE cursor>? ORDER BY cursor LIMIT 200', (cursor,)).fetchall()
            events = []
            for row in rows:
                data = json.loads(row['data'])
                message = db.execute('SELECT * FROM shared_messages WHERE id=?',(data.get('id'),)).fetchone() if row['type']=='message' else None
                if row['type']=='message' and (not message or not self._visible(db,message)):
                    continue
                events.append({'cursor':row['cursor'],'type':row['type'],'data':data})
        return events
