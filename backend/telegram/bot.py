"""Separate Telegram Bot API menu and owner-only text transport."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request

from backend.auth.chatgpt_auth import _dpapi_decrypt, _dpapi_encrypt
from backend.telegram.bot_config import load_bot
from backend.telegram.config import _file_lease, account_path, load_account
from backend.telegram.pairing import PairingStore
from backend.telegram.service import status_text
from backend.telegram.worker import NoRedirect, chunks

MAX_RESPONSE = 1024 * 1024


class BotApiError(RuntimeError):
    def __init__(self, code, retry_after=0):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


def _bot_error(status, data):
    description = data.get('description', '') if isinstance(data, dict) else ''
    description = description.lower() if isinstance(description, str) else ''
    parameters = data.get('parameters', {}) if isinstance(data, dict) else {}
    retry = parameters.get('retry_after', 0) if isinstance(parameters, dict) else 0
    retry = retry if type(retry) is int and 0 < retry <= 86400 else 0
    if status == 401:
        code = 'TOKEN_REJECTED'
    elif status == 403:
        code = 'OWNER_BLOCKED_BOT'
    elif status == 429:
        code = 'RATE_LIMITED'
    elif status == 400 and ('chat not found' in description or 'user not found' in description):
        code = 'OWNER_CHAT_NOT_STARTED'
    elif status == 400 and ('url' in description or 'web app' in description):
        code = 'MINIAPP_URL_REJECTED'
    else:
        code = 'BOT_REQUEST_REJECTED'
    return BotApiError(code, retry)


def bot_request(token, method, body, timeout=15):
    if method not in {'getUpdates', 'sendMessage', 'answerCallbackQuery', 'getMe', 'setChatMenuButton', 'setMyCommands'}:
        raise ValueError('Invalid bot operation')
    request = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method,
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read(16385))
            except (ValueError, TypeError):
                data = {}
            raise _bot_error(exc.code, data) from None
        if len(raw) > MAX_RESPONSE:
            raise BotApiError('BOT_RESPONSE_INVALID')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise BotApiError('BOT_RESPONSE_INVALID')
        if result.get('ok') is not True:
            raise _bot_error(result.get('error_code'), result)
        return result.get('result')
    except BotApiError:
        raise
    except Exception:
        # urllib exceptions may include the credential-bearing URL.
        raise BotApiError('NETWORK_ERROR') from None


def local_request(endpoint_file, route, body=None):
    if route not in {'/axx-api/telegram/status', '/axx-api/telegram/bot-input'}:
        raise ValueError('Invalid local route')
    raw = Path(endpoint_file).read_bytes()
    if len(raw) > 16384:
        raise ValueError('Invalid endpoint')
    descriptor = json.loads(_dpapi_decrypt(raw))
    if (not isinstance(descriptor, dict) or type(descriptor.get('port')) is not int
            or not 1 <= descriptor['port'] <= 65535
            or not isinstance(descriptor.get('token'), str) or len(descriptor['token']) < 32
            or not isinstance(descriptor.get('instance_id'), str)):
        raise ValueError('Invalid endpoint')
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request('http://127.0.0.1:' + str(descriptor['port']) + route,
        data=data, headers={'Authorization': 'Bearer ' + descriptor['token'], 'Content-Type': 'application/json'},
        method='GET' if body is None else 'POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=120) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('Invalid local response')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('Invalid local response')
    return result


def allowed(update, owner):
    callback = update.get('callback_query')
    message = callback.get('message') if isinstance(callback, dict) else update.get('message')
    sender = callback.get('from') if isinstance(callback, dict) else (message or {}).get('from')
    chat = (message or {}).get('chat') or {}
    return bool(isinstance(sender, dict) and sender.get('id') == owner and not sender.get('is_bot')
                and chat.get('type') == 'private' and chat.get('id') == owner
                and not (message or {}).get('forward_origin') and not (message or {}).get('forward_date')
                and not (message or {}).get('reply_to_message'))


def menu(url):
    rows = [[{'text': 'Estado', 'callback_data': 'status'}, {'text': 'Ayuda', 'callback_data': 'help'}],
            [{'text': 'Permisos', 'callback_data': 'permissions'}]]
    if url:
        rows.append([{'text': 'Abrir Axx', 'web_app': {'url': url}}])
    return {'inline_keyboard': rows}


class BotWorker:
    def __init__(self, data_dir, endpoint_file):
        self.data_dir = data_dir
        self.endpoint_file = endpoint_file
        self.config = load_bot(data_dir)
        self.account = load_account(data_dir)
        if not self.config['enabled'] or not self.account['enabled']:
            raise ValueError('Bot or account disabled')
        directory = account_path(data_dir).parent
        directory.mkdir(parents=True, exist_ok=True)
        self.db_path = directory / ('bot-transport-' + hashlib.sha256(self.config['token'].encode()).hexdigest()[:16] + '.db')
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS updates (id INTEGER PRIMARY KEY, payload BLOB NOT NULL, state TEXT NOT NULL)')
            db.execute("UPDATE updates SET state='unknown' WHERE state='running'")
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='axx-telegram-bot')
        self.tasks = set()

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def authorized(self):
        try:
            current, account = load_bot(self.data_dir), load_account(self.data_dir)
            return (current['enabled'] and account['enabled'] and current['token'] == self.config['token']
                    and account['owner_id'] == self.account['owner_id']
                    and account['account_id'] == self.account['account_id'])
        except Exception:
            return False

    def send(self, text, markup=None):
        for part in chunks(text):
            if not self.authorized():
                raise RuntimeError('Bot revoked')
            body = {'chat_id': self.account['owner_id'], 'text': part}
            if markup:
                body['reply_markup'] = markup
            bot_request(self.config['token'], 'sendMessage', body)

    def persist(self, updates):
        if not isinstance(updates, list):
            raise ValueError('Invalid updates')
        ids = [update.get('update_id') if isinstance(update, dict) else None for update in updates]
        if any(type(value) is not int or value < 0 for value in ids) or ids != sorted(ids):
            raise ValueError('Invalid update order')
        with self.db() as db:
            pending = db.execute("SELECT count(*) FROM updates WHERE state='pending'").fetchone()[0]
            for update in updates:
                if not isinstance(update, dict) or type(update.get('update_id')) is not int or update['update_id'] < 0:
                    raise ValueError('Invalid update')
                if db.execute('SELECT 1 FROM updates WHERE id=?', (update['update_id'],)).fetchone():
                    continue
                if pending >= 1000:
                    break
                payload = _dpapi_encrypt(json.dumps(update, ensure_ascii=False).encode('utf-8'))
                db.execute("INSERT INTO updates VALUES (?,?,'pending')", (update['update_id'], payload))
                pending += 1

    def offset(self):
        with self.db() as db:
            row = db.execute('SELECT max(id) FROM updates').fetchone()
        return row[0] + 1 if row[0] is not None else 0

    def process(self, update_id, update):
        status = 'done'
        try:
            callback = update.get('callback_query')
            if not self.authorized() or not allowed(update, self.account['owner_id']):
                return
            if isinstance(callback, dict):
                choice = callback.get('data')
                if choice == 'status':
                    result = local_request(self.endpoint_file, '/axx-api/telegram/status')
                    self.send(status_text(result), menu(load_bot(self.data_dir)['public_url']))
                elif choice == 'permissions':
                    grants = load_account(self.data_dir)['grants']
                    names = {'conversation': 'Conversar por texto', 'voice_notes': 'Notas de voz',
                             'files': 'Archivos', 'pc_commands': 'Acciones en la PC', 'private_calls': 'Llamadas'}
                    lines = ['Lo que permites:'] + [names[key] + ': ' + ('Permitido' if value is True else 'No permitido') for key, value in grants.items()]
                    lines.append('Se cambian en Axx de tu PC: Herramientas → Asistencia → Telegram. Un permiso no significa que la función ya esté lista.')
                    self.send('\n'.join(lines), menu(load_bot(self.data_dir)['public_url']))
                elif choice == 'help':
                    self.send('1. Deja Axx abierto en tu PC.\n2. Toca Estado para ver qué está disponible.\n3. Toca Abrir Axx para abrir la Mini App.\nLos permisos se cambian en tu PC. El chat con IA depende de tu proveedor y las llamadas todavía están en reparación.', menu(load_bot(self.data_dir)['public_url']))
                return
            message = update['message']
            text = message.get('text')
            if not isinstance(text, str):
                self.send('Las notas de voz y archivos de este bot aún no están habilitados.')
            elif re.fullmatch(r'/start\s+axx_[A-Za-z0-9_-]{43}', text.strip()):
                start_param = text.strip().split()[1]
                config = load_bot(self.data_dir)
                account = load_account(self.data_dir)
                if config['public_url'] and PairingStore(self.data_dir).pending(account, start_param):
                    url = config['public_url'] + '#pairing=' + start_param
                    self.send('Abre Axx para completar la vinculación.', {'inline_keyboard': [[
                        {'text': 'Abrir Axx', 'web_app': {'url': url}}]]})
                else:
                    self.send('La vinculación no está disponible o ha vencido. Genera otro QR en la PC.')
            elif text.strip() in ('/start', '/menu'):
                self.send('Menú de Axx. Consulta el estado de cada capacidad.', menu(load_bot(self.data_dir)['public_url']))
            elif text.strip().startswith('/start '):
                self.send('La vinculación no es válida. Genera otro QR en la PC.')
            elif 1 <= len(text.strip()) <= 12000:
                result = local_request(self.endpoint_file, '/axx-api/telegram/bot-input',
                    {'peer_id': self.account['owner_id'], 'event_id': update_id,
                     'sent_at': message.get('date'), 'text': text})
                reply = result.get('text')
                if not isinstance(reply, str):
                    raise ValueError('Invalid local response')
                self.send(reply)
            else:
                self.send('El mensaje debe tener entre 1 y 12000 caracteres.')
        except Exception:
            status = 'unknown'
        finally:
            with self.db() as db:
                db.execute('UPDATE updates SET state=? WHERE id=?', (status, update_id))

    def pump(self):
        self.tasks = {task for task in self.tasks if not task.done()}
        with self.db() as db:
            rows = db.execute("SELECT id,payload FROM updates WHERE state='pending' ORDER BY id LIMIT ?", (2 - len(self.tasks),)).fetchall()
            for update_id, payload in rows:
                try:
                    update = json.loads(_dpapi_decrypt(payload))
                except Exception:
                    db.execute("UPDATE updates SET state='unknown' WHERE id=?", (update_id,))
                    continue
                db.execute("UPDATE updates SET state='running' WHERE id=?", (update_id,))
                db.commit()
                self.tasks.add(self.executor.submit(self.process, update_id, update))

    def run(self):
        while self.authorized():
            self.pump()
            try:
                updates = bot_request(self.config['token'], 'getUpdates',
                    {'offset': self.offset(), 'timeout': 5, 'allowed_updates': ['message', 'callback_query']}, timeout=10)
                self.persist(updates)
                for update in updates:
                    callback = update.get('callback_query')
                    if isinstance(callback, dict) and isinstance(callback.get('id'), str):
                        try:
                            bot_request(self.config['token'], 'answerCallbackQuery', {'callback_query_id': callback['id']}, timeout=5)
                        except Exception:
                            pass
            except BotApiError as exc:
                delay = exc.retry_after if exc.code == 'RATE_LIMITED' and exc.retry_after else 2
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline and self.authorized():
                    time.sleep(max(0, min(1, deadline - time.monotonic())))
            except Exception:
                time.sleep(2)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


def main():
    parser = argparse.ArgumentParser(description='Run Axx Telegram bot')
    parser.add_argument('--data-dir')
    parser.add_argument('--endpoint-file')
    args = parser.parse_args()
    endpoint = Path(args.endpoint_file) if args.endpoint_file else account_path(args.data_dir).parent.parent / 'connect' / 'endpoint.dpapi'
    try:
        with _file_lease(account_path(args.data_dir).parent / 'bot-session.lock', 'TELEGRAM_BOT_IN_USE'):
            worker = BotWorker(args.data_dir, endpoint)
            try:
                worker.run()
            finally:
                worker.close()
    except (Exception, KeyboardInterrupt):
        print('Telegram bot detenido; revisa la configuración local.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
