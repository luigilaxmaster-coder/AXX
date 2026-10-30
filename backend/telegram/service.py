"""Telegram admission into Axx; the existing command policy owns every PC effect."""
from __future__ import annotations

import json
import copy
import hashlib
import hmac
import math
import secrets
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from backend.prompts import compose
from backend.memory import task_memory
from backend.telegram.config import load_account, confirmation_policy, confirmation_fingerprint
from backend.telegram.catalog import is_catalog_request, phrase_catalog


def status_text(status):
    names = {'messages': 'Mensajes', 'voice_notes': 'Notas de voz', 'files': 'Archivos',
             'pc_commands': 'Acciones en la PC', 'private_calls': 'Llamadas'}
    labels = {'not_configured': 'Sin configurar', 'not_verified': 'Falta comprobar',
              'not_implemented': 'En preparación'}
    lines = ['Estado de Axx', 'Proceso activo; falta probar cada función.' if status.get('worker_running') is True else 'El proceso de Telegram no está activo.']
    lines.extend(name + ': ' + labels.get(status.get(key), 'Sin comprobar') for key, name in names.items())
    lines.append('Las llamadas todavía están en reparación. Deja Axx abierto en tu PC.')
    return '\n'.join(lines)


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
                CREATE TABLE IF NOT EXISTS confirmations(operation_id TEXT PRIMARY KEY, account INTEGER,
                    owner INTEGER, epoch TEXT, plan_hash TEXT, token_hash TEXT UNIQUE, expires REAL,
                    state TEXT, response TEXT);
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(inbox)')}
            for name in ('account', 'peer'):
                if name not in columns:
                    db.execute('ALTER TABLE inbox ADD COLUMN '+name+' INTEGER')
            for name,kind in (('task_id','TEXT'),('memory_scope','TEXT'),('memory_context_id','TEXT'),('memory_independent','INTEGER')):
                if name not in columns:db.execute('ALTER TABLE inbox ADD COLUMN '+name+' '+kind)
            db.execute("UPDATE inbox SET state='unknown' WHERE state='running'")
            db.execute("UPDATE confirmations SET state='unknown' WHERE state='claimed'")
            db.execute("UPDATE confirmations SET state='expired' WHERE state='pending'")

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

    def diagnostics(self, owner_id):
        account = load_account(self.data_dir)
        self._authorize({'account_id': account['account_id'], 'peer_id': owner_id})
        prefs = dict(self.preferences() or {})
        if not prefs:
            state, reason, message = 'blocked', 'SELECTED_PROVIDER_NOT_SYNCED', 'Abre Axx en la PC para comprobar el proveedor de chat. El chat con IA todavía no está disponible aquí.'
        elif prefs.get('provider') != 'bridge':
            state, reason, message = 'blocked', 'REMOTE_PROVIDER_ISOLATION_REQUIRED', 'El chat con IA todavía no está disponible en Telegram. Se conserva el proveedor de tu PC; falta comprobar su aislamiento remoto.'
        elif prefs.get('selection_mode', 'manual') != 'automatic_free' and not (prefs.get('provider_name') and prefs.get('model')):
            state, reason, message = 'blocked', 'SELECTED_PROVIDER_NOT_SYNCED', 'Falta la selección explícita del modelo y conexión.'
        else:
            state, reason, message = 'configured', 'READY_FOR_REQUEST', 'Selección configurada; la disponibilidad se comprueba al enviar.'
        connection = getattr(self, 'connection', lambda: None)()
        return {'permissions': {key: value is True for key, value in account['grants'].items()},
                'conversation': {'state': state, 'reason_code': reason, 'provider': 'desktop_selected',
                                 'model': prefs.get('model') or None, 'message': message},
                'remote_confirmations': confirmation_policy(self.data_dir)['enabled'],
                'connection': {'core_bound': connection, 'account_running': self.process is not None and self.process.poll() is None,
                               'bot_running': self.bot_process is not None and self.bot_process.poll() is None, 'checked_at': time.time()},
                'observed_at': time.time()}

    def command_catalog(self, owner_id=None):
        account = load_account(self.data_dir)
        self._authorize({'account_id': account['account_id'],
                         'peer_id': account['owner_id'] if owner_id is None else owner_id})
        try:
            catalog = self.commands.executable_catalog()
        except Exception:
            catalog = None
        return phrase_catalog(catalog, pc_commands=account['grants'].get('pc_commands'),
                              remote_confirmations=confirmation_policy(self.data_dir)['enabled'])

    def activity(self, owner_id):
        account = load_account(self.data_dir)
        self._authorize({'account_id': account['account_id'], 'peer_id': owner_id})
        with self._db() as db:
            rows = db.execute('SELECT operation_id,state,created FROM inbox WHERE account=? AND peer=? ORDER BY created DESC LIMIT 30',
                              (account['account_id'], owner_id)).fetchall()
        items = []
        for operation_id, state, created in rows:
            item = {'id': operation_id, 'state': state, 'created_at': created, 'can_cancel': False}
            try:
                operation = self.commands.get(operation_id)
            except Exception:
                operation = None
            if isinstance(operation, dict) and operation.get('operation_id') == operation_id:
                state = operation.get('state', state)
                item['state'] = state
                if isinstance(operation.get('command_id'), str):
                    item['command_id'] = operation['command_id']
                if type(operation.get('postconditions_passed')) is bool:
                    item['postconditions_passed'] = operation['postconditions_passed']
                item['can_cancel'] = bool(account['grants'].get('pc_commands') and state in ('prepared','awaiting_approval','running'))
                if state in ('prepared', 'awaiting_approval') and callable(getattr(self.commands, 'remote_review', None)):
                    try:
                        review = self.commands.remote_review(operation_id)
                        if isinstance(review, dict):
                            item['review_available'] = True
                            item['title'] = review.get('title', 'Acción en tu PC')
                    except ValueError:
                        pass
            items.append(item)
        return {'items': items}

    def _owned_operation(self, owner_id, operation_id):
        if (type(owner_id) is not int or owner_id <= 0 or not isinstance(operation_id, str)
                or str(uuid.UUID(operation_id)) != operation_id):
            raise ValueError('Invalid operation')
        account = load_account(self.data_dir)
        self._authorize({'account_id': account['account_id'], 'peer_id': owner_id})
        with self._db() as db:
            row = db.execute('SELECT 1 FROM inbox WHERE operation_id=? AND account=? AND peer=?',
                             (operation_id, account['account_id'], owner_id)).fetchone()
        if not row:
            raise ValueError('Unknown operation')
        return account

    def review_operation(self, owner_id, operation_id):
        account = self._owned_operation(owner_id, operation_id)
        review = self.commands.remote_review(operation_id)
        fields = ('operation_id', 'title', 'description', 'risk', 'inputs', 'plan_hash', 'expires_at', 'state')
        result = {key: review[key] for key in fields if key in review}
        reasons = {'PC_APPROVAL_REQUIRED': 'Esta orden solo puede aprobarse en la PC.',
                   'PLAN_RESERVED': 'Esta orden pertenece a un plan; revísala en su plan de la PC.',
                   'NOT_STATIC_EXECUTABLE': 'Este comando todavía no admite confirmación remota.',
                   'NOT_REVIEWABLE': 'Esta orden ya se está ejecutando o terminó.',
                   'EXPIRED': 'Esta orden venció. Envía una solicitud nueva.'}
        result.update(can_confirm=False, reason=reasons.get(review.get('reason'), review.get('reason')))
        if not account['grants'].get('pc_commands') or not confirmation_policy(self.data_dir)['enabled']:
            return result | {'reason': 'Activa Confirmar desde Telegram en Herramientas → Telegram de tu PC.'}
        if not review.get('eligible') or review.get('state') != 'awaiting_approval':
            return result | {'reason': result.get('reason') or 'Esta operación requiere revisión en la PC o ya terminó.'}
        # One Telegram message must show every reviewed parameter without truncation.
        if len(json.dumps(result, ensure_ascii=False).encode('utf-16-le')) > 5500:
            return result | {'reason': 'La orden es demasiado extensa. Revísala completa en la PC.'}
        epoch = confirmation_fingerprint(self.data_dir)
        token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = min(float(review['expires_at']), time.time() + 120)
        if expires <= time.time():
            return result | {'reason': 'La orden ha vencido. Cancélala y envía una nueva solicitud.'}
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT state FROM confirmations WHERE operation_id=?', (operation_id,)).fetchone()
            if old and old[0] in ('claimed', 'done', 'unknown'):
                return result | {'reason': 'La confirmación ya se utilizó. Consulta el resultado sin repetirla.'}
            db.execute("DELETE FROM confirmations WHERE expires<? AND state!='claimed'", (time.time() - 86400,))
            db.execute('INSERT OR REPLACE INTO confirmations VALUES (?,?,?,?,?,?,?,?,?)',
                       (operation_id, account['account_id'], owner_id, epoch, review['plan_hash'], token_hash, expires, 'pending', None))
        return result | {'can_confirm': True, 'reason': None, 'token': token, 'expires_at': expires}

    def decide_operation(self, owner_id, token, decision):
        if (type(owner_id) is not int or owner_id <= 0 or not isinstance(token, str) or len(token) != 32 or
                any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in token)
                or decision not in ('confirm', 'cancel')):
            raise ValueError('Invalid confirmation')
        account = load_account(self.data_dir)
        self._authorize({'account_id': account['account_id'], 'peer_id': owner_id})
        epoch = confirmation_fingerprint(self.data_dir)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._db() as db:
            row = db.execute('SELECT operation_id,account,owner,epoch,plan_hash,expires,state,response FROM confirmations WHERE token_hash=?', (digest,)).fetchone()
        if not row or row[1:3] != (account['account_id'], owner_id) or not hmac.compare_digest(row[3], epoch):
            raise ValueError('Confirmation expired or revoked')
        operation_id, _, _, _, plan_hash, expires, state, response = row
        self._owned_operation(owner_id, operation_id)
        if state == 'done' and response:
            self._inbox_memory(operation_id,manual=True)
            return json.loads(response) | {'replayed': True}
        if state != 'pending':
            return {'state': 'unknown', 'operation_id': operation_id, 'text': 'La confirmación ya se utilizó. Consulta Actividad; no se repetirá la orden.'}
        if expires <= time.time():
            raise ValueError('Confirmation expired')
        if not self.lock.acquire(blocking=False):
            return {'state': 'busy', 'operation_id': operation_id, 'text': 'Axx está ocupado. La confirmación no se utilizó; puedes intentarlo después.'}
        try:
            fresh = self.commands.remote_review(operation_id)
            if (not fresh.get('eligible') or fresh.get('state') != 'awaiting_approval'
                    or not hmac.compare_digest(fresh.get('plan_hash', ''), plan_hash)):
                raise ValueError('The reviewed operation changed')
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                claimed = db.execute("UPDATE confirmations SET state='claimed' WHERE operation_id=? AND token_hash=? AND state='pending' AND expires>?", (operation_id, digest, time.time())).rowcount
                if claimed != 1:
                    return {'state': 'unknown', 'operation_id': operation_id, 'text': 'Otra confirmación ya atendió la orden. Consulta su resultado.'}

            def authorize_dispatch():
                if decision=='confirm':self._inbox_memory(operation_id,manual=True)
                latest = load_account(self.data_dir)
                self._authorize({'account_id': account['account_id'], 'peer_id': owner_id})
                if (latest['account_id'] != account['account_id'] or not latest['grants'].get('pc_commands')
                        or not hmac.compare_digest(confirmation_fingerprint(self.data_dir), epoch)):
                    raise ValueError('Remote permission revoked')
                with self._db() as db:
                    claim = db.execute("SELECT state,token_hash,expires FROM confirmations WHERE operation_id=?", (operation_id,)).fetchone()
                if not claim or claim[:2] != ('claimed', digest) or claim[2] <= time.time():
                    raise ValueError('Remote confirmation no longer valid')

            try:
                authorize_dispatch()
                if decision == 'cancel':
                    receipt = self.commands.cancel(operation_id)
                    self.adapter.cancel(operation_id)
                    state = receipt.get('state', 'unknown')
                    result = {'state': 'cancel_requested' if state == 'running' else state,
                              'operation_id': operation_id, 'postconditions_passed': receipt.get('postconditions_passed') is True,
                              'text': 'Orden cancelada.' if state == 'cancelled' else
                                      'Cancelación solicitada; la orden ya estaba en curso.' if state == 'running' else
                                      'La orden ya terminó. Su estado y los efectos realizados se conservan.'}
                else:
                    receipt = self.commands.confirm_remote(operation_id, plan_hash, authorization_check=authorize_dispatch)
                    verified = receipt.get('state') == 'succeeded' and receipt.get('postconditions_passed') is True
                    result = {'state': receipt.get('state', 'unknown'), 'operation_id': operation_id,
                              'postconditions_passed': verified,
                              'text': ('Resultado comprobado: ' + json.dumps(receipt.get('output'), ensure_ascii=False)[:6000]
                                       if verified else 'El resultado no está comprobado. Consulta Actividad antes de repetir la orden.')}
                if decision=='confirm':self._inbox_memory(operation_id,manual=True)
                with self._db() as db:
                    db.execute("UPDATE confirmations SET state='done',response=? WHERE operation_id=?", (json.dumps(result, ensure_ascii=False), operation_id))
                    db.execute('UPDATE inbox SET state=?,response=? WHERE operation_id=?', (result['state'], json.dumps(result, ensure_ascii=False), operation_id))
                return result
            except Exception:
                with self._db() as db:
                    db.execute("UPDATE confirmations SET state='unknown' WHERE operation_id=?", (operation_id,))
                return {'state': 'unknown', 'operation_id': operation_id, 'text': 'No se pudo confirmar el resultado. La orden no se reenviará; revisa Actividad.'}
        finally:
            self.lock.release()

    def history(self, owner_id):
        account = load_account(self.data_dir)
        self._authorize({'account_id': account['account_id'], 'peer_id': owner_id})
        if not account['grants'].get('conversation'):
            raise ValueError('Conversation permission revoked')
        with self._db() as db:
            row = db.execute('SELECT conversation FROM bindings WHERE account=? AND peer=?', (account['account_id'], owner_id)).fetchone()
        if not row:
            return {'messages': [], 'has_more': False}
        messages = self.chats.get(row[0])['messages']
        selected = []
        size = 64
        for message in reversed(messages[-50:]):
            item = {key: message[key] for key in ('id', 'role', 'text', 'status', 'at') if key in message}
            encoded = json.dumps(item, ensure_ascii=False).encode('utf-8')
            if size + len(encoded) + 1 > 128 * 1024:
                break
            selected.append(item)
            size += len(encoded) + 1
        return {'messages': list(reversed(selected)), 'has_more': len(selected) < len(messages)}

    def cancel_operation(self, owner_id, operation_id):
        if not isinstance(operation_id, str) or str(uuid.UUID(operation_id)) != operation_id:
            raise ValueError('Invalid operation')
        account = load_account(self.data_dir)
        self._authorize({'account_id': account['account_id'], 'peer_id': owner_id})
        if not account['grants'].get('pc_commands'):
            raise ValueError('Permission revoked')
        with self._db() as db:
            owned = db.execute('SELECT 1 FROM inbox WHERE operation_id=? AND account=? AND peer=?',
                               (operation_id, account['account_id'], owner_id)).fetchone()
        if not owned:
            raise ValueError('Unknown operation')
        operation = self.commands.get(operation_id)
        if not operation or operation.get('operation_id') != operation_id or operation.get('state') not in ('prepared','awaiting_approval','running'):
            raise ValueError('Operation cannot be cancelled')
        latest = self._authorize({'account_id': account['account_id'], 'peer_id': owner_id})
        if not latest['grants'].get('pc_commands'):
            raise ValueError('Permission revoked')
        self.commands.cancel(operation_id)
        self.adapter.cancel(operation_id)
        return {'state': 'cancel_requested'}

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

    def pause_account(self):
        process = self.process
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

    @staticmethod
    def _capture_chat(chat):
        ref=copy.deepcopy(chat.get('memory_scope'));context=chat.get('connect_id')
        if (not isinstance(ref,dict) or set(ref)!={'task_id','generation'} or ref.get('task_id')!=chat.get('id')
                or type(ref.get('generation')) is not int or ref['generation']<0 or not isinstance(context,str) or not context):
            raise ValueError('Conversation memory identity unavailable')
        return {'task_id':chat['id'],'memory_scope':ref,'memory_context_id':context}

    def _assert_chat(self, captured):
        if callable(getattr(self.chats,'db',None)):
            with self.chats.db() as db:
                task_memory.assert_context(db,captured['memory_scope'],captured['memory_context_id'],task_id=captured['task_id'])
        current=self.chats.get(captured['task_id'])
        if self._capture_chat(current)!=captured:raise ValueError('Conversation memory changed')
        return current

    def _inbox_memory(self, operation_id,*,manual=False):
        with self._db() as db:
            row=db.execute('SELECT task_id,memory_scope,memory_context_id,memory_independent FROM inbox WHERE operation_id=?',(operation_id,)).fetchone()
        if row and row[3]:return None
        if not row or not row[0] or row[1] is None:
            if manual and callable(getattr(self.chats,'db',None)):
                with self.chats.db() as db:
                    if not db.execute('SELECT 1 FROM memory_task_scopes WHERE generation>0 OR forgetting=1 LIMIT 1').fetchone():return None
            raise ValueError('Unattributed cached response requires manual review')
        captured={'task_id':row[0],'memory_scope':json.loads(row[1]),'memory_context_id':row[2]}
        self._assert_chat(captured)
        return captured

    def _save_message(self, captured, mid, role, text):
        self.chats.mutate('save', {'id': captured['task_id'], 'memory_scope':copy.deepcopy(captured['memory_scope']),
            'memory_context_id':captured['memory_context_id'],'messages': [
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
        remote_review = confirmation_policy(self.data_dir)['enabled']
        text = body['text'].strip()
        key = str(uuid.uuid5(uuid.NAMESPACE_URL, 'axx-telegram:'+channel+':' + ':'.join(str(body[k]) for k in ('account_id','peer_id','message_id'))))
        if time.time()-body['sent_at'] > 120:
            return {'state': 'expired', 'text': 'Solicitud antigua tras una desconexión: no se ejecutó. Envíala de nuevo si todavía corresponde.'}
        if not self.lock.acquire(blocking=False):
            # Status and cancellation must remain usable during a long model request.
            if text == '/estado' or text.startswith('/cancelar ') or is_catalog_request(text):
                return self._control(account, text)
            return {'state': 'busy', 'text': 'Axx está ocupado; la solicitud no se ejecutó. Inténtalo después.'}
        try:
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT state,response,operation_id FROM inbox WHERE id=?', (key,)).fetchone()
                if old:
                    self._inbox_memory(old[2])
                    return json.loads(old[1]) if old[1] else {'state': old[0],
                        'text': 'La solicitud ya fue admitida. Consulta el recibo antes de repetir.', 'operation_id': old[2]}
                db.execute('INSERT INTO inbox(id,state,response,operation_id,created,account,peer) VALUES(?,?,?,?,?,?,?)',
                           (key, 'running', None, key, time.time(), body['account_id'], body['peer_id']))
            captured=None
            if text == '/estado' or text.startswith('/cancelar ') or is_catalog_request(text):
                result = self._control(account, text)
            elif not account['grants'].get('conversation') and not (account['grants'].get('pc_commands') and remote_review):
                result = {'state': 'blocked', 'text': 'La conversación está desactivada. Activa la confirmación remota en la PC para enviar órdenes sin conversación.'}
            else:
                chat = self._thread(account)
                captured=self._capture_chat(chat)
                with self._db() as db:
                    db.execute('UPDATE inbox SET task_id=?,memory_scope=?,memory_context_id=? WHERE id=?',
                        (captured['task_id'],json.dumps(captured['memory_scope']),captured['memory_context_id'],key))
                self._save_message(captured, key+':user', 'user', text)
                result = self._turn(account, chat, key, text, require_remote_review=remote_review,captured=captured)
                self._assert_chat(captured)
                self._save_message(captured, key+':assistant', 'assistant', result['text'])
            with self._db() as db:
                db.execute('UPDATE inbox SET state=?,response=?,memory_independent=? WHERE id=?',
                           (result['state'], json.dumps(result, ensure_ascii=False),int(captured is None),key))
            if captured:self._assert_chat(captured)
            return result
        except Exception:
            with self._db() as db:
                db.execute("UPDATE inbox SET state='unknown',response=NULL WHERE id=?", (key,))
            # Provider errors and messages can contain private data. Never echo them remotely.
            return {'state': 'unknown', 'operation_id': key,
                    'text': 'No se pudo confirmar el resultado. Consulta esta operación en Axx antes de repetir: '+key}
        finally:
            self.lock.release()

    def _control(self, account, text):
        if text == '/estado':
            return {'state': 'succeeded', 'text': status_text(self.status())}
        if is_catalog_request(text):
            return {'state': 'succeeded', 'text': self.command_catalog(account['owner_id'])['text']}
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

    def _turn(self, account, chat, key, text, *, require_remote_review=False,captured=None):
        captured=captured or self._capture_chat(chat)
        self._assert_chat(captured)
        resolved = self.commands.resolve(text, source='text')
        self._assert_chat(captured)
        if resolved.get('match') == 'exact' and resolved.get('command_id'):
            if not account['grants']['pc_commands']:
                return {'state':'blocked', 'text':'Activa el permiso de acciones en la PC para esta cuenta en los ajustes locales de Telegram.'}
            if require_remote_review and not confirmation_policy(self.data_dir)['enabled']:
                return {'state': 'blocked', 'text': 'El permiso de confirmación remota fue retirado. La orden no se ejecutó.'}
            prepared = self.commands.prepare(resolved['command_id'], resolved.get('inputs', {}),
                source='text', operation_id=key, conversation_id=chat['id'],
                command_mode='ask' if require_remote_review else chat['mode'],memory_scope=copy.deepcopy(captured['memory_scope']),
                memory_context_id=captured['memory_context_id'])
            if prepared['state'] == 'awaiting_approval':
                return {'state':'awaiting_approval', 'operation_id':key,
                        'text':'Orden preparada. Revisa su tarjeta para confirmar desde Telegram si está permitido, o apruébala en la PC. Operación: '+key}
            if prepared['state'] != 'prepared':
                return {'state':prepared['state'], 'operation_id':key, 'text':'La orden no se ejecutó. Operación: '+key}
            latest = self._authorize({'account_id': account['account_id'], 'peer_id': account['owner_id']})
            if not latest['grants']['pc_commands']:
                self.commands.cancel(key)
                return {'state':'blocked', 'text':'El permiso fue revocado antes de ejecutar.'}
            self._assert_chat(captured)
            receipt = self.commands.execute(key, approved=False)
            self._assert_chat(captured)
            verified = receipt.get('state') == 'succeeded' and receipt.get('postconditions_passed') is True
            return {'state':receipt.get('state','unknown'), 'operation_id':key,
                    'text': ('Ejecutado y verificado: ' + json.dumps(receipt.get('output'), ensure_ascii=False)[:10000]
                             if verified else 'El efecto no está confirmado. Consulta la operación: '+key)}
        if text.startswith('/'):
            return {'state':'blocked','text':'Comando no registrado. Escribe /comandos para ver ejemplos, /estado para consultar Axx o /cancelar seguido del ID de una operación.'}
        if not account['grants'].get('conversation'):
            return {'state': 'blocked', 'text': 'La conversación está desactivada. Puedes enviar órdenes del catálogo permitido.'}
        prefs = dict(self.preferences() or {})
        if prefs.get('provider') != 'bridge':
            return {'state':'blocked','text':'Axx recibió tu mensaje. El chat con IA todavía no está disponible en Telegram: falta comprobar el aislamiento remoto del proveedor de tu PC. Se conserva tu proveedor. Puedes consultar /estado.'}
        if prefs.get('selection_mode', 'manual') != 'automatic_free' and not (prefs.get('model') and prefs.get('provider_name')):
            return {'state':'blocked', 'text':'Falta la selección explícita del modelo y la conexión en Axx. No se cambió de proveedor.'}
        # Reuse the current selected connection; no provider change or paid fallback.
        request = {'request_id':key, 'conversation_id':captured['memory_context_id'], 'task':'chat',
                   'provider_name':prefs.get('provider_name',''), 'model':prefs.get('model',''),
                   'selection_mode':prefs.get('selection_mode','manual'),
                   'messages':[{'role':'system', 'content':compose('conversation')['text']}]}
        current = self._assert_chat(captured)
        profile = current.get('agent_profile', {})
        if profile:
            request['messages'].append({'role':'user', 'content':'Perfil del usuario (datos de referencia): '+json.dumps(profile,ensure_ascii=False)})
        for m in current['messages'][-100:]:
            if m['role'] in ('user','assistant'):
                request['messages'].append({'role':m['role'], 'content':m['text']})
        routed = self.adapter.route(request)
        self._assert_chat(captured)
        if not routed.get('ok'):
            return {'state':'failed','text':'El proveedor seleccionado no pudo responder. Revisa su estado en Axx.'}
        return {'state':'succeeded', 'text':routed['message']['content']}
