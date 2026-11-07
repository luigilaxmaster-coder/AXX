"""Private Telegram text transport for the running local Axx backend."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.request

from backend.auth.chatgpt_auth import _dpapi_decrypt, _dpapi_encrypt
from backend.telegram.config import account_lease, account_path, load_account


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_input(endpoint_file, payload):
    """Send one input only to the DPAPI-discovered loopback backend."""
    raw = Path(endpoint_file).read_bytes()
    if len(raw) > 16384:
        raise ValueError('Invalid local endpoint')
    descriptor = json.loads(_dpapi_decrypt(raw))
    if (not isinstance(descriptor, dict) or type(descriptor.get('port')) is not int
            or not 1 <= descriptor['port'] <= 65535
            or not isinstance(descriptor.get('token'), str) or len(descriptor['token']) < 32
            or not isinstance(descriptor.get('instance_id'), str)):
        raise ValueError('Invalid local endpoint')
    request = urllib.request.Request(
        'http://127.0.0.1:' + str(descriptor['port']) + '/axx-api/telegram/input',
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + descriptor['token'], 'Content-Type': 'application/json'},
        method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=120) as response:
        result = response.read(65537)
    if len(result) > 65536:
        raise ValueError('Invalid local response')
    result = json.loads(result)
    if not isinstance(result, dict) or not isinstance(result.get('text'), str):
        raise ValueError('Invalid local response')
    return result


def authorized_message(event, sender, account):
    message = event.message
    return bool(event.is_private and not message.out and not message.fwd_from
                and not getattr(message, 'reply_to', None)
                and not getattr(message, 'via_bot_id', None)
                and not getattr(sender, 'bot', True)
                and getattr(sender, 'id', None) == account['owner_id']
                and message.sender_id == account['owner_id']
                and event.chat_id == account['owner_id']
                and account['owner_id'] != account['account_id'])


def chunks(text, limit=4000):
    part, size = [], 0
    for char in text:
        units = 2 if ord(char) > 0xffff else 1
        if size + units > limit:
            yield ''.join(part)
            part, size = [], 0
        part.append(char)
        size += units
    if part:
        yield ''.join(part)


class TelegramWorker:
    def __init__(self, client, account, endpoint_file, data_dir=None):
        self.client = client
        self.account = account
        self.endpoint_file = endpoint_file
        self.data_dir = data_dir
        self.queue = asyncio.Queue(maxsize=8)
        self.tasks = set()
        self.queued = set()
        directory = account_path(data_dir).parent
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / 'transport.db')
        self.db.execute('CREATE TABLE IF NOT EXISTS inbox (account_id INTEGER, peer_id INTEGER, message_id INTEGER, payload BLOB NOT NULL, priority INTEGER NOT NULL, state TEXT NOT NULL, PRIMARY KEY(account_id,peer_id,message_id))')
        # A previous process may have dispatched or partially delivered the result.
        self.db.execute("UPDATE inbox SET state='dispatch_unknown' WHERE state='dispatching'")
        self.db.execute("UPDATE inbox SET state='delivery_unknown' WHERE state='sending'")
        self.db.commit()

    async def permitted(self):
        try:
            current = load_account(self.data_dir)
            valid = (current['enabled'] and current['account_id'] == self.account['account_id']
                     and current['owner_id'] == self.account['owner_id']
                     and current['session'] == self.account['session'])
        except Exception:
            valid = False
        if not valid:
            await self.client.disconnect()
        return valid

    async def send(self, text):
        for part in chunks(text):
            if not await self.permitted():
                raise RuntimeError('TELEGRAM_REVOKED')
            await self.client.send_message(self.account['owner_id'], part, parse_mode=None)

    def store(self, payload):
        command = payload['text'].strip().split(maxsplit=1)[0].lower()
        priority = int(command in ('/estado', '/cancelar'))
        key = (payload['account_id'], payload['peer_id'], payload['message_id'])
        if self.db.execute('SELECT 1 FROM inbox WHERE account_id=? AND peer_id=? AND message_id=?', key).fetchone():
            return 'duplicate'
        pending = self.db.execute("SELECT count(*) FROM inbox WHERE state='pending'").fetchone()[0]
        # Reserve two places for status and cancellation when ordinary work is backlogged.
        if pending >= (1000 if priority else 998):
            return 'full'
        encrypted = _dpapi_encrypt(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        with self.db:
            inserted = self.db.execute('INSERT OR IGNORE INTO inbox VALUES (?,?,?,?,?,?)',
                (payload['account_id'], payload['peer_id'], payload['message_id'], encrypted,
                 priority, 'pending')).rowcount
        return 'stored' if inserted else 'duplicate'

    def state(self, key, state):
        with self.db:
            self.db.execute('UPDATE inbox SET state=? WHERE account_id=? AND peer_id=? AND message_id=?', (state, *key))

    def pump(self):
        for priority in (1, 0):
            rows = self.db.execute('SELECT account_id,peer_id,message_id,payload FROM inbox WHERE state=? AND priority=? AND account_id=? AND peer_id=? ORDER BY rowid LIMIT 64', ('pending', priority, self.account['account_id'], self.account['owner_id'])).fetchall()
            for account_id, peer_id, message_id, blob in rows:
                key = (account_id, peer_id, message_id)
                if key in self.queued:
                    continue
                if priority and len(self.tasks) >= 2:
                    break
                if not priority and self.queue.full():
                    break
                try:
                    payload = json.loads(_dpapi_decrypt(blob))
                    if (payload['account_id'], payload['peer_id'], payload['message_id']) != key:
                        raise ValueError('Invalid stored Telegram input')
                except Exception:
                    self.state(key, 'invalid')
                    continue
                self.queued.add(key)
                if priority:
                    task = asyncio.create_task(self.dispatch(key, payload))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)
                else:
                    self.queue.put_nowait((key, payload))

    async def receive(self, event):
        try:
            if not await self.permitted():
                return
            sender = await event.get_sender()
            if not authorized_message(event, sender, self.account):
                return
            message = event.message
            if message.media:
                await self.send('Los adjuntos de Telegram aún no están habilitados.')
                return
            text = message.message or ''
            if not text.strip():
                return
            if len(text) > 12000:
                await self.send('El mensaje supera el límite de 12000 caracteres; envíalo más corto.')
                return
            payload = {'account_id': self.account['account_id'], 'peer_id': event.chat_id,
                       'message_id': message.id, 'sent_at': message.date.timestamp(),
                       'kind': 'text', 'text': text}
            stored = self.store(payload)
            if stored == 'stored':
                self.pump()
            elif stored == 'full':
                await self.send('Axx está ocupado y no recibió esta solicitud; vuelve a enviarla más tarde.')
        except Exception:
            # Message data and Telegram credentials must never enter logs.
            return

    async def dispatch(self, key, payload):
        phase = 'dispatch_unknown'
        try:
            if not await self.permitted():
                return
            self.state(key, 'dispatching')
            result = await asyncio.to_thread(local_input, self.endpoint_file, payload)
            self.state(key, 'sending')
            phase = 'delivery_unknown'
            if result['text']:
                await self.send(result['text'])
            self.state(key, 'sent')
        except Exception:
            self.state(key, phase)
        finally:
            self.queued.discard(key)

    async def consume(self):
        while True:
            key, payload = await self.queue.get()
            try:
                await self.dispatch(key, payload)
            finally:
                self.queue.task_done()
                self.pump()

    async def monitor(self):
        while await self.permitted():
            self.pump()
            await asyncio.sleep(1)


async def run(data_dir=None, endpoint_file=None):
    try:
        account = load_account(data_dir)
    except FileNotFoundError:
        return
    if not account['enabled']:
        return
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    endpoint_file = Path(endpoint_file) if endpoint_file else account_path(data_dir).parent.parent / 'connect' / 'endpoint.dpapi'
    with account_lease(data_dir):
        client = TelegramClient(StringSession(account['session']), account['api_id'], account['api_hash'], catch_up=True)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError('TELEGRAM_AUTHENTICATION_REQUIRED')
            me = await client.get_me()
            if not me or me.id != account['account_id'] or getattr(me, 'bot', False):
                raise RuntimeError('TELEGRAM_ACCOUNT_MISMATCH')
            worker = TelegramWorker(client, account, endpoint_file, data_dir)
            client.add_event_handler(worker.receive, events.NewMessage(incoming=True))
            consumer = asyncio.create_task(worker.consume())
            monitor = asyncio.create_task(worker.monitor())
            try:
                await client.run_until_disconnected()
            finally:
                consumer.cancel()
                monitor.cancel()
                for task in worker.tasks:
                    task.cancel()
                await asyncio.gather(consumer, monitor, *worker.tasks, return_exceptions=True)
                worker.db.close()
        finally:
            await client.disconnect()


def main():
    parser = argparse.ArgumentParser(description='Run the local Axx Telegram channel')
    parser.add_argument('--data-dir')
    parser.add_argument('--endpoint-file')
    args = parser.parse_args()
    try:
        asyncio.run(run(args.data_dir, args.endpoint_file))
    except (Exception, KeyboardInterrupt):
        print('Telegram worker stopped; check local configuration and session.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
