"""Telegram admission into Axx; the existing command policy owns every PC effect."""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from backend.prompts import compose
from backend.telegram.config import load_account


class TelegramService:
    def __init__(self, data_dir, chats, commands, adapter, preferences, appearance=None):
        self.data_dir = Path(data_dir)
        self.chats, self.commands, self.adapter = chats, commands, adapter
        self.preferences = preferences
        self.appearance = appearance or (lambda: None)
        self.lock = threading.Lock()
        self.process = None
        self.bot_process = None
        self.db_path = self.data_dir / 'telegram' / 'inbox.db'
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS bindings(account INTEGER, peer INTEGER, conversation TEXT,
                    PRIMARY KEY(account,peer));
                CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY, state TEXT, response TEXT,
                    operation_id TEXT, created REAL);
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(inbox)')}
            for name in ('account', 'peer'):
                if name not in columns:
                    db.execute('ALTER TABLE inbox ADD COLUMN '+name+' INTEGER')
            db.execute("UPDATE inbox SET state='unknown' WHERE state='running'")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def status(self):
        try:
            account = load_account(self.data_dir)
        except (OSError, ValueError, RuntimeError):
            return {'state': 'authentication_required', 'messages': 'not_configured',
                    'private_calls': 'not_verified'}
        return {'state': 'configured' if account['enabled'] else 'disabled',
                'worker_running': any(p is not None and p.poll() is None for p in (self.process, self.bot_process)),
                'messages': 'not_verified', 'voice_notes': 'not_implemented',
                'files': 'not_implemented', 'pc_commands': 'not_verified',
                'private_calls': 'not_verified'}

    def start(self, endpoint_file=None):
        if self.process is not None and self.process.poll() is None:
            return
        try:
            account = load_account(self.data_dir)
        except (OSError, ValueError, RuntimeError):
            return
        if not account['enabled']:
            return
        if getattr(sys, 'frozen', False):
            args = [sys.executable, '--telegram-worker', '--data-dir', str(self.data_dir)]
            cwd = None
        else:
            python = self.data_dir / 'telegram-runtime' / 'Scripts' / 'python.exe'
            if not python.is_file():
                return
            args = [str(python), '-m', 'backend.telegram.worker', '--data-dir', str(self.data_dir)]
            cwd = str(Path(__file__).resolve().parents[2])
        if endpoint_file:
            args += ['--endpoint-file', str(endpoint_file)]
        self.process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def start_bot(self, endpoint_file=None):
        from backend.telegram.bot_config import load_bot
        try:
            bot = load_bot(self.data_dir)
            account = load_account(self.data_dir)
        except (OSError, ValueError, RuntimeError):
            return
        if not bot['enabled'] or not account['enabled'] or self.bot_process is not None and self.bot_process.poll() is None:
            return
        if getattr(sys, 'frozen', False):
            args, cwd = [sys.executable, '--telegram-bot'], None
        else:
            python = self.data_dir / 'telegram-runtime' / 'Scripts' / 'python.exe'
            if not python.is_file():
                return
            args, cwd = [str(python), '-m', 'backend.telegram.bot'], str(Path(__file__).resolve().parents[2])
        args += ['--data-dir', str(self.data_dir)]
        if endpoint_file:
            args += ['--endpoint-file', str(endpoint_file)]
        self.bot_process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def close(self):
        for process in (self.process, self.bot_process):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    def _authorize(self, body):
        account = load_account(self.data_dir)
        if not account['enabled'] or body.get('account_id') != account['account_id'] or body.get('peer_id') != account['owner_id']:
            raise ValueError('Telegram identity is not authorized')
        return account

    def _thread(self, account):
        with self._db() as db:
            row = db.execute('SELECT conversation FROM bindings WHERE account=? AND peer=?',
                             (account['account_id'], account['owner_id'])).fetchone()
            if row:
                return self.chats.get(row[0])
            chat = self.chats.mutate('create', {'title': 'Telegram', 'command_mode': 'ask'})
            db.execute('INSERT INTO bindings VALUES(?,?,?)',
                       (account['account_id'], account['owner_id'], chat['id']))
            return self.chats.get(chat['id'])

    def _save_message(self, cid, mid, role, text):
        self.chats.mutate('save', {'id': cid, 'messages': [
            {'id': mid, 'role': role, 'source': 'telegram', 'status': 'complete',
             'text': text, 'at': time.time()*1000}]})

    def admit(self, body):
        return self._admit(body, 'account')

    def admit_bot(self, body):
        if not isinstance(body, dict) or set(body) != {'peer_id', 'event_id', 'text', 'sent_at'} or type(body['event_id']) is not int or body['event_id'] < 0:
            raise ValueError('Invalid bot input')
        account = load_account(self.data_dir)
        return self._admit({'account_id':account['account_id'], 'peer_id':body['peer_id'],
            'message_id':body['event_id']+1, 'text':body['text'], 'sent_at':body['sent_at'], 'kind':'text'}, 'bot')

    def admit_miniapp(self, owner_id, text, request_id):
        if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
            raise ValueError('Invalid Mini App request')
        account = load_account(self.data_dir)
        return self._admit({'account_id':account['account_id'], 'peer_id':owner_id,
            'message_id':uuid.UUID(request_id).int+1, 'text':text, 'sent_at':time.time(), 'kind':'text'}, 'miniapp')

    def _admit(self, body, channel):
        if not isinstance(body, dict) or set(body) != {'account_id','peer_id','message_id','sent_at','kind','text'}:
            raise ValueError('Invalid Telegram input fields')
        if any(type(body.get(k)) is not int or body[k] <= 0 for k in ('account_id','peer_id','message_id')):
            raise ValueError('Invalid Telegram input identifier')
        if body['kind'] != 'text' or not isinstance(body['text'], str) or not 1 <= len(body['text'].strip()) <= 12000:
            raise ValueError('Invalid Telegram text')
        if type(body['sent_at']) not in (int,float) or not math.isfinite(body['sent_at']) or body['sent_at'] > time.time()+60:
            raise ValueError('Invalid Telegram timestamp')
        account = self._authorize(body)
        text = body['text'].strip()
        key = str(uuid.uuid5(uuid.NAMESPACE_URL, 'axx-telegram:'+channel+':' + ':'.join(str(body[k]) for k in ('account_id','peer_id','message_id'))))
        if time.time()-body['sent_at'] > 120:
            return {'state': 'expired', 'text': 'Solicitud antigua tras una desconexión: no se ejecutó. Envíala de nuevo si todavía corresponde.'}
        if not self.lock.acquire(blocking=False):
            # Status and cancellation must remain usable during a long model request.
            if text == '/estado' or text.startswith('/cancelar '):
                return self._control(account, text)
            return {'state': 'busy', 'text': 'Axx está ocupado; la solicitud no se ejecutó. Inténtalo después.'}
        try:
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT state,response,operation_id FROM inbox WHERE id=?', (key,)).fetchone()
                if old:
                    return json.loads(old[1]) if old[1] else {'state': old[0],
                        'text': 'La solicitud ya fue admitida. Consulta el recibo antes de repetir.', 'operation_id': old[2]}
                db.execute('INSERT INTO inbox(id,state,response,operation_id,created,account,peer) VALUES(?,?,?,?,?,?,?)',
                           (key, 'running', None, key, time.time(), body['account_id'], body['peer_id']))
            if text == '/estado' or text.startswith('/cancelar '):
                result = self._control(account, text)
            elif not account['grants']['conversation']:
                result = {'state': 'blocked', 'text': 'El permiso de conversación está desactivado en la PC.'}
            else:
                chat = self._thread(account)
                self._save_message(chat['id'], key+':user', 'user', text)
                result = self._turn(account, chat, key, text)
                self._save_message(chat['id'], key+':assistant', 'assistant', result['text'])
            with self._db() as db:
                db.execute('UPDATE inbox SET state=?,response=? WHERE id=?',
                           (result['state'], json.dumps(result, ensure_ascii=False), key))
            return result
        except Exception:
            with self._db() as db:
                db.execute("UPDATE inbox SET state='unknown' WHERE id=?", (key,))
            # Provider errors and messages can contain private data. Never echo them remotely.
            return {'state': 'unknown', 'operation_id': key,
                    'text': 'No se pudo confirmar el resultado. Consulta esta operación en Axx antes de repetir: '+key}
        finally:
            self.lock.release()

    def _control(self, account, text):
        if text == '/estado':
            return {'state': 'succeeded', 'text': json.dumps(self.status(), ensure_ascii=False)}
        operation_id = text.removeprefix('/cancelar ').strip()
        try:
            uuid.UUID(operation_id)
        except ValueError:
            return {'state': 'blocked', 'text': 'Usa /cancelar seguido del ID de la operación.'}
        with self._db() as db:
            owned = db.execute('SELECT id FROM inbox WHERE operation_id=? AND account=? AND peer=?',
                               (operation_id, account['account_id'], account['owner_id'])).fetchone()
        if not owned or not account['grants']['pc_commands']:
            return {'state': 'blocked', 'text': 'La operación no pertenece a este canal o falta permiso.'}
        latest = self._authorize({'account_id':account['account_id'], 'peer_id':account['owner_id']})
        if not latest['grants']['pc_commands']:
            return {'state': 'blocked', 'text': 'El permiso de acciones fue revocado.'}
        self.commands.cancel(operation_id)
        self.adapter.cancel(operation_id)
        return {'state': 'cancel_requested', 'text': 'Cancelación solicitada. Los efectos ya completados se conservan.'}

    def _turn(self, account, chat, key, text):
        resolved = self.commands.resolve(text, source='text')
        if resolved.get('match') == 'exact' and resolved.get('command_id'):
            if not account['grants']['pc_commands']:
                return {'state':'blocked', 'text':'Activa el permiso de acciones en la PC para esta cuenta en los ajustes locales de Telegram.'}
            prepared = self.commands.prepare(resolved['command_id'], resolved.get('inputs', {}),
                source='text', operation_id=key, conversation_id=chat['id'], command_mode=chat['mode'])
            if prepared['state'] == 'awaiting_approval':
                return {'state':'awaiting_approval', 'operation_id':key,
                        'text':'Revisa y aprueba la orden en el chat Telegram de Axx en la PC. Operación: '+key}
            if prepared['state'] != 'prepared':
                return {'state':prepared['state'], 'operation_id':key, 'text':'La orden no se ejecutó. Operación: '+key}
            latest = self._authorize({'account_id': account['account_id'], 'peer_id': account['owner_id']})
            if not latest['grants']['pc_commands']:
                self.commands.cancel(key)
                return {'state':'blocked', 'text':'El permiso fue revocado antes de ejecutar.'}
            receipt = self.commands.execute(key, approved=False)
            verified = receipt.get('state') == 'succeeded' and receipt.get('postconditions_passed') is True
            return {'state':receipt.get('state','unknown'), 'operation_id':key,
                    'text': ('Ejecutado y verificado: ' + json.dumps(receipt.get('output'), ensure_ascii=False)[:10000]
                             if verified else 'El efecto no está confirmado. Consulta la operación: '+key)}
        if text.startswith('/'):
            return {'state':'blocked','text':'Comando no registrado. Disponibles: /estado y /cancelar <id>. Las aprobaciones se realizan en la PC.'}
        prefs = dict(self.preferences() or {})
        if prefs.get('provider') != 'bridge':
            return {'state':'blocked','text':'Se conserva el proveedor del escritorio. Su conversación remota todavía está bloqueada por falta de aislamiento comprobado; no se cambió de modelo ni se activó otro proveedor.'}
        if prefs.get('selection_mode', 'manual') != 'automatic_free' and not (prefs.get('model') and prefs.get('provider_name')):
            return {'state':'blocked', 'text':'Falta la selección explícita del modelo y la conexión en Axx. No se cambió de proveedor.'}
        # Reuse the current selected connection; no provider change or paid fallback.
        request = {'request_id':key, 'conversation_id':chat['id'], 'task':'chat',
                   'provider_name':prefs.get('provider_name',''), 'model':prefs.get('model',''),
                   'selection_mode':prefs.get('selection_mode','manual'),
                   'messages':[{'role':'system', 'content':compose('conversation')['text']}]}
        current = self.chats.get(chat['id'])
        profile = current.get('agent_profile', {})
        if profile:
            request['messages'].append({'role':'user', 'content':'Perfil del usuario (datos de referencia): '+json.dumps(profile,ensure_ascii=False)})
        for m in current['messages'][-100:]:
            if m['role'] in ('user','assistant'):
                request['messages'].append({'role':m['role'], 'content':m['text']})
        routed = self.adapter.route(request)
        if not routed.get('ok'):
            return {'state':'failed','text':'El proveedor seleccionado no pudo responder. Revisa su estado en Axx.'}
        return {'state':'succeeded', 'text':routed['message']['content']}
