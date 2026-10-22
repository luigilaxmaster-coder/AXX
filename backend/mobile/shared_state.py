"""Shared conversation history; SQLite remains owned by the desktop process."""
import json
import math
import sqlite3
import time
from contextlib import contextmanager


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
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(shared_messages)')}
            if 'conversation_id' not in columns:
                db.execute("ALTER TABLE shared_messages ADD COLUMN conversation_id TEXT NOT NULL DEFAULT 'main'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def merge_messages(self, messages, source, conversation_id='main', activate=False):
        if not isinstance(conversation_id, str) or not 1 <= len(conversation_id) <= 160:
            raise ValueError('Invalid conversation')
        if not isinstance(messages, list) or len(messages) > 200:
            raise ValueError('messages debe contener hasta 200 mensajes')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
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
                old = db.execute('SELECT role,text FROM shared_messages WHERE id=?', (m['id'],)).fetchone()
                if old:
                    if old['role'] != m['role'] or old['text'] != m['text']:
                        raise ValueError('Conflicto: el ID ya pertenece a otro mensaje')
                    continue
                status = m.get('status', 'sent')
                if status not in ('sent', 'done', 'complete', 'error', 'pending', 'failed'):
                    status = 'sent'
                msg = dict(id=m['id'], role=m['role'], text=m['text'], at=at, source=source, status=status, conversation_id=conversation_id)
                db.execute('INSERT INTO shared_messages VALUES(?,?,?,?,?,?,?)',
                           (msg['id'], msg['role'], msg['text'], at, source, status, conversation_id))
                db.execute('INSERT INTO shared_events(type,data,at) VALUES(?,?,?)',
                           ('message', json.dumps(msg, ensure_ascii=False), time.time()))
        return self.snapshot(conversation_id)

    def snapshot(self, conversation_id=None):
        with self.connect() as db:
            db.execute('BEGIN')
            if conversation_id is None:
                conversation_id = db.execute('SELECT conversation_id FROM shared_active_conversation WHERE id=1').fetchone()[0]
            cursor = db.execute('SELECT COALESCE(MAX(cursor),0) FROM shared_events').fetchone()[0]
            rows = db.execute('SELECT * FROM (SELECT * FROM shared_messages WHERE conversation_id=? ORDER BY at DESC,id DESC LIMIT 200) ORDER BY at,id', (conversation_id,)).fetchall()
        return {'conversation_id':conversation_id, 'cursor':cursor, 'messages':[dict(row) for row in rows]}

    def events(self, cursor):
        if type(cursor) is not int or cursor < 0:
            raise ValueError('Invalid cursor')
        with self.connect() as db:
            rows = db.execute('SELECT cursor,type,data FROM shared_events WHERE cursor>? ORDER BY cursor LIMIT 200', (cursor,)).fetchall()
        return [{'cursor':r['cursor'], 'type':r['type'], 'data':json.loads(r['data'])} for r in rows]
