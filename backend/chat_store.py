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
            ''')
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

    def _messages(self, db, cid, messages):
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
            old = db.execute('SELECT conversation_id FROM chat_messages WHERE id=?', (mid,)).fetchone()
            if old and old[0] != cid:
                raise ValueError('El mensaje pertenece a otro chat')
            payload = {k: m[k] for k in ('id','role','source','status','at','model') if k in m}
            payload['text'] = content
            db.execute('INSERT INTO chat_messages VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (mid,cid,at,json.dumps(payload,ensure_ascii=False)))

    def get(self, cid):
        self.purge()
        with self.db() as db:
            row = db.execute('SELECT * FROM chat_conversations WHERE id=?', (ident(cid),)).fetchone()
            if not row:
                raise ValueError('Conversación desconocida o vencida')
            result = dict(row)
            result['agent_profile'] = self._profile(db)
            result['messages'] = [json.loads(r[0]) for r in db.execute('SELECT payload FROM chat_messages WHERE conversation_id=? ORDER BY at,id', (cid,))]
            result['context'] = [dict(r) for r in db.execute('SELECT * FROM chat_context WHERE group_id=? ORDER BY at,id', (row['group_id'],))]
            attachment = db.execute('SELECT name,text,at FROM chat_attachments WHERE conversation_id=?', (cid,)).fetchone()
            result['attachment'] = dict(attachment) if attachment else None
            result['links'] = []
            for link in db.execute('SELECT * FROM chat_links WHERE conversation_id=? ORDER BY updated,source_id', (cid,)):
                entry = dict(link)
                entry['messages'] = [json.loads(r[0]) for r in db.execute('SELECT payload FROM chat_link_messages WHERE conversation_id=? AND source_id=? ORDER BY at,message_id', (cid,link['source_id']))]
                result['links'].append(entry)
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
            if 'command_runs' in tables:
                results += [json.loads(r[0]) for r in db.execute('SELECT result_json FROM command_runs ORDER BY created_at DESC LIMIT 100')]
            if 'learning_plans' in tables:
                results += [json.loads(r[0]) for r in db.execute('SELECT payload FROM learning_plans ORDER BY rowid DESC LIMIT 100')]
            return results

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
                    return {'id':old[0]}
                cid = self._new(db, body)
                self._messages(db, cid, body.get('messages', []))
                db.execute("INSERT OR REPLACE INTO chat_settings VALUES('migration_v4',?)", (cid,))
            elif action == 'create':
                cid = self._new(db, body)
            elif action in ('save','update','delete'):
                row = db.execute('SELECT * FROM chat_conversations WHERE id=?', (ident(cid),)).fetchone()
                if not row:
                    raise ValueError('Conversación desconocida')
                if action == 'save':
                    self._messages(db, cid, body.get('messages', []))
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
                                db.execute('INSERT OR REPLACE INTO chat_attachments VALUES(?,?,?,?)',(cid,text(item.get('name'),255),text(item.get('text'),200000),at))
                    draft = text(body.get('draft',row['draft']))
                    draft_at = self.clock() if draft != row['draft'] else row['draft_at']
                    title = row['title']
                    if title == 'Nueva conversación':
                        first = db.execute('SELECT payload FROM chat_messages WHERE conversation_id=? ORDER BY at,id', (cid,))
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
                if body.get('remove_id'):
                    db.execute('DELETE FROM chat_context WHERE id=? AND group_id=?',(ident(body['remove_id']),group))
                else:
                    if db.execute('SELECT COUNT(*) FROM chat_context WHERE group_id=?',(group,)).fetchone()[0] >= 20:
                        raise ValueError('Máximo 20 notas de contexto por grupo')
                    note = text(body.get('text'),4000)
                    total = db.execute('SELECT COALESCE(SUM(length(text)),0) FROM chat_context WHERE group_id=?',(group,)).fetchone()[0]
                    if total+len(note)>12000:
                        raise ValueError('El contexto del grupo admite hasta 12 000 caracteres. Reduce o quita una nota.')
                    db.execute('INSERT INTO chat_context VALUES(?,?,?,?)',(str(uuid.uuid4()),group,note,self.clock()))
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
                if action == 'link':
                    origin = db.execute('SELECT title FROM chat_conversations WHERE id=?', (source,)).fetchone()
                    if not origin:
                        raise ValueError('Hilo desconocido o vencido')
                    exists = db.execute('SELECT 1 FROM chat_links WHERE conversation_id=? AND source_id=?', (cid,source)).fetchone()
                    if not exists and db.execute('SELECT COUNT(*) FROM chat_links WHERE conversation_id=?', (cid,)).fetchone()[0] >= 3:
                        raise ValueError('Máximo tres hilos vinculados por chat')
                    # Copy only this thread's completed transcript, never its links or group notes.
                    selected, remaining = [], 4000
                    for row in db.execute('SELECT payload FROM chat_messages WHERE conversation_id=? ORDER BY at DESC,id DESC LIMIT 30', (source,)):
                        message = json.loads(row[0])
                        if message['role'] not in ('user','assistant') or message['status'] not in ('complete','sent','done'):
                            continue
                        content = message['text'][:remaining]
                        if not content:
                            continue
                        selected.append({k:message[k] for k in ('id','role','at')} | {'text':content})
                        remaining -= len(content)
                        if remaining <= 0:
                            break
                    if not selected:
                        raise ValueError('Este hilo no tiene mensajes guardados y vigentes')
                    db.execute('INSERT OR REPLACE INTO chat_links VALUES(?,?,?,?)', (cid,source,origin['title'],self.clock()))
                    db.execute('DELETE FROM chat_link_messages WHERE conversation_id=? AND source_id=?', (cid,source))
                    for message in selected:
                        db.execute('INSERT INTO chat_link_messages VALUES(?,?,?,?,?)', (cid,source,message['id'],message['at'],json.dumps(message,ensure_ascii=False)))
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
                    db.execute('UPDATE chat_conversations SET connect_id=? WHERE id=?',(str(uuid.uuid4()),row[0]))
                if db.execute("SELECT name FROM sqlite_master WHERE name='shared_messages'").fetchone():
                    db.execute('DELETE FROM shared_messages')
                    db.execute('DELETE FROM shared_events')
            else:
                raise ValueError('Operación de chat desconocida')
        return {'id':cid,'ok':True}
