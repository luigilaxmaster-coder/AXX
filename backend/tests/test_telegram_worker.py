"""Telegram transport boundaries; no real account or Telegram connection."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from backend.telegram.worker import TelegramWorker, chunks, local_input

try:
    from telethon.tl.functions.phone import DiscardCallRequest
    from telethon.tl.types import PhoneCallDiscardReasonBusy, PhoneCallRequested, UpdatePhoneCall
except ImportError:
    PhoneCallRequested = None


ACCOUNT = {'account_id': 11, 'owner_id': 22, 'session': 'session', 'enabled': True}


def event(**changes):
    message = SimpleNamespace(out=False, fwd_from=None, reply_to=None, via_bot_id=None, sender_id=22,
                              media=None, message='hola', id=3, date=datetime.now(timezone.utc))
    sender = SimpleNamespace(id=22, bot=False)
    value = SimpleNamespace(is_private=True, chat_id=22, message=message, get_sender=AsyncMock(return_value=sender))
    for key, item in changes.items():
        if hasattr(message, key):
            setattr(message, key, item)
        elif hasattr(sender, key):
            setattr(sender, key, item)
        else:
            setattr(value, key, item)
    return value


class TelegramWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name, value in [('_dpapi_encrypt', lambda x: x), ('_dpapi_decrypt', lambda x: x),
                            ('load_account', lambda _: ACCOUNT.copy())]:
            p = patch('backend.telegram.worker.' + name, side_effect=value)
            p.start()
            self.addCleanup(p.stop)
        self.client = SimpleNamespace(send_message=AsyncMock(), disconnect=AsyncMock())

    def worker(self):
        worker = TelegramWorker(self.client, ACCOUNT.copy(), 'unused', self.temp.name)
        self.addCleanup(worker.db.close)
        return worker

    async def test_rejects_non_owner_groups_bots_forwarded_and_outgoing_silently(self):
        worker = self.worker()
        cases = [event(chat_id=99), event(sender_id=99), event(is_private=False),
                 event(bot=True), event(fwd_from=object()), event(reply_to=object()), event(out=True), event(via_bot_id=9)]
        for incoming in cases:
            await worker.receive(incoming)
        self.assertEqual(worker.db.execute('SELECT count(*) FROM inbox').fetchone()[0], 0)
        self.client.send_message.assert_not_awaited()

    @unittest.skipIf(PhoneCallRequested is None, 'Telethon is unavailable')
    async def test_incoming_calls_declined_and_owner_notice_deduplicated(self):
        class Client:
            def __init__(self):
                self.requests = []
                self.send_message = AsyncMock()
                self.disconnect = AsyncMock()
            async def __call__(self, request):
                self.requests.append(request)
        self.client = Client()
        worker = self.worker()
        def incoming(call_id, admin=22, participant=11):
            call = PhoneCallRequested(call_id, 321, None, admin, participant, b'', None)
            return UpdatePhoneCall(call)
        granted = dict(ACCOUNT, grants={'private_calls': True})
        with patch('backend.telegram.worker.load_account', return_value=granted):
            await worker.incoming_call(incoming(1))
            await worker.incoming_call(incoming(1))
            await worker.incoming_call(incoming(2, admin=99))
            await worker.incoming_call(incoming(3))
        self.assertEqual(len(self.client.requests), 3)
        self.assertTrue(all(isinstance(item, DiscardCallRequest) and isinstance(item.reason, PhoneCallDiscardReasonBusy) for item in self.client.requests))
        self.client.send_message.assert_awaited_once()
        self.assertEqual(self.client.send_message.await_args.args[0], 22)
        self.assertIn('reparación', self.client.send_message.await_args.args[1])

    @unittest.skipIf(PhoneCallRequested is None, 'Telethon is unavailable')
    async def test_call_without_grant_is_declined_without_notice(self):
        class Client:
            def __init__(self):
                self.requests = []
                self.send_message, self.disconnect = AsyncMock(), AsyncMock()
            async def __call__(self, request): self.requests.append(request)
        self.client = Client()
        worker = self.worker()
        with patch('backend.telegram.worker.load_account', return_value=dict(ACCOUNT, grants={'private_calls': False})):
            await worker.incoming_call(UpdatePhoneCall(PhoneCallRequested(1, 321, None, 22, 11, b'', None)))
        self.assertEqual(len(self.client.requests), 1)
        self.client.send_message.assert_not_awaited()

    async def test_owner_deduplication_and_media_is_not_dispatched(self):
        worker = self.worker()
        await worker.receive(event())
        await worker.receive(event())
        self.assertEqual(worker.queue.qsize(), 1)
        await worker.receive(event(media=object()))
        self.client.send_message.assert_awaited_once_with(22, 'Los adjuntos de Telegram aún no están habilitados.', parse_mode=None)

    async def test_text_over_limit_is_rejected_before_persisting(self):
        worker = self.worker()
        await worker.receive(event(message='x' * 12001))
        self.assertEqual(worker.db.execute('SELECT count(*) FROM inbox').fetchone()[0], 0)
        self.assertIn('12000', self.client.send_message.await_args.args[1])

    async def test_pending_quota_rejects_new_input_and_reserves_priority(self):
        worker = self.worker()
        with worker.db:
            worker.db.executemany('INSERT INTO inbox VALUES (?,?,?,?,?,?)',
                [(11, 22, number, b'{}', 0, 'pending') for number in range(100, 1098)])
        await worker.receive(event(id=9999))
        self.assertIn('no recibió', self.client.send_message.await_args.args[1])
        self.assertEqual(worker.db.execute('SELECT count(*) FROM inbox').fetchone()[0], 998)
        for _ in range(8):
            worker.queue.put_nowait(None)
        with patch('backend.telegram.worker.local_input', return_value={'text': 'ok', 'state': 'ok'}):
            await worker.receive(event(id=9998, message='/estado'))
            await asyncio.gather(*worker.tasks)
        self.assertEqual(worker.db.execute('SELECT state FROM inbox WHERE message_id=9998').fetchone()[0], 'sent')

    async def test_pending_persists_across_restart_and_unknown_is_not_retried(self):
        first = self.worker()
        await first.receive(event())
        await first.receive(event(id=4))
        first.state((11, 22, 4), 'dispatching')
        first.db.close()
        second = self.worker()
        second.pump()
        self.assertEqual(second.queue.qsize(), 1)
        key, payload = second.queue.get_nowait()
        self.assertEqual(key, (11, 22, 3))
        self.assertEqual(payload['text'], 'hola')
        self.assertEqual(second.db.execute('SELECT state FROM inbox WHERE message_id=4').fetchone()[0], 'dispatch_unknown')

    async def test_full_queue_is_durable_and_priority_bypasses_it(self):
        worker = self.worker()
        for number in range(10):
            await worker.receive(event(id=number + 10))
        self.assertEqual(worker.queue.qsize(), 8)
        with patch('backend.telegram.worker.local_input', return_value={'text': 'estado', 'state': 'ok'}):
            await worker.receive(event(id=99, message='/estado'))
            await asyncio.gather(*worker.tasks)
        self.client.send_message.assert_awaited_once_with(22, 'estado', parse_mode=None)
        self.assertEqual(worker.db.execute("SELECT count(*) FROM inbox WHERE state='pending'").fetchone()[0], 10)

    async def test_revocation_prevents_reply_and_disconnects(self):
        worker = self.worker()
        await worker.receive(event())
        key, payload = worker.queue.get_nowait()
        revoked = dict(ACCOUNT, enabled=False)
        with patch('backend.telegram.worker.local_input', return_value={'text': 'ok', 'state': 'ok'}), \
             patch('backend.telegram.worker.load_account', side_effect=[ACCOUNT, revoked]):
            await worker.dispatch(key, payload)
        self.client.send_message.assert_not_awaited()
        self.client.disconnect.assert_awaited()
        self.assertEqual(worker.db.execute('SELECT state FROM inbox').fetchone()[0], 'delivery_unknown')

    async def test_failed_send_is_unknown_and_not_retried(self):
        worker = self.worker()
        await worker.receive(event())
        key, payload = worker.queue.get_nowait()
        self.client.send_message.side_effect = OSError('offline')
        with patch('backend.telegram.worker.local_input', return_value={'text': 'ok', 'state': 'ok'}):
            await worker.dispatch(key, payload)
        self.assertEqual(worker.db.execute('SELECT state FROM inbox').fetchone()[0], 'delivery_unknown')
        worker.pump()
        self.assertTrue(worker.queue.empty())

    def test_chunks_limit_utf16_units(self):
        parts = list(chunks('a' * 3999 + '😀' + 'b' * 4000))
        self.assertEqual(''.join(parts), 'a' * 3999 + '😀' + 'b' * 4000)
        self.assertTrue(all(len(part.encode('utf-16-le')) // 2 <= 4000 for part in parts))

    def test_local_endpoint_uses_loopback_and_rejects_redirects(self):
        path = Path(self.temp.name) / 'endpoint'
        descriptor = {'port': 1234, 'token': 't' * 32, 'instance_id': 'id'}
        path.write_bytes(json.dumps(descriptor).encode())
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"text":"ok","state":"ok"}'
        def check(request, timeout):
            self.assertEqual(request.full_url, 'http://127.0.0.1:1234/axx-api/telegram/input')
            self.assertEqual(request.get_header('Authorization'), 'Bearer ' + 't' * 32)
            self.assertEqual(timeout, 120)
            return Response()
        with patch('backend.telegram.worker.urllib.request.build_opener', return_value=SimpleNamespace(open=check)) as build:
            self.assertEqual(local_input(path, {'text': 'hi'})['text'], 'ok')
            self.assertIsNone(build.call_args.args[1].redirect_request(None, None, 302, '', {}, 'https://other.example'))


if __name__ == '__main__':
    unittest.main()
