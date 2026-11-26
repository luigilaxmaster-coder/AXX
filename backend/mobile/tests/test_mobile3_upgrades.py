"""Unit and TLS integration tests for AXX Mobile 3.0 upgrades (P1-P3)."""
import http.client
import json
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from backend.mobile.control import checked_events
from backend.mobile.gateway import MobileGateway
from backend.mobile.windows_input import KEYS as WIN_KEYS


class Mobile3UpgradeTests(unittest.TestCase):
    def test_persisted_desktop_state_survives_gateway_restart_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'state.db'
            first = MobileGateway(db, tmp, lambda *a: {}, host_resolver=lambda: '127.0.0.1')
            try:
                appearance = {'settings': {'form': 3, 'palette': 1}, 'studio': {'living': True}, 'camera': [0.1, 0.2], 'finish': 'prism'}
                prefs = {'provider': 'bridge', 'provider_name': 'ollama', 'model': 'qwen3', 'selection_mode': 'manual', 'chat_tools': True, 'api_key': 'secret-must-not-persist'}
                first.update_desktop_state(share_history=True, preferences=prefs, appearance=appearance)
            finally:
                first.close()

            second = MobileGateway(db, tmp, lambda *a: {}, host_resolver=lambda: '127.0.0.1')
            try:
                self.assertTrue(second.share_history)
                self.assertEqual(second.appearance, appearance)
                self.assertEqual(second.preferences['model'], 'qwen3')
                self.assertTrue(second.preferences['chat_tools'])
                self.assertNotIn('api_key', second.preferences)
                self.assertNotEqual(first.server_epoch, second.server_epoch)
            finally:
                second.close()

    def test_snapshot_additive_fields_and_events_long_poll_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway = MobileGateway(Path(tmp) / 'state.db', tmp, lambda *a: {}, host_resolver=lambda: '127.0.0.1')
            gateway._event_wait_timeout = 1.5
            try:
                info = gateway.start()
                device = gateway.store.consume_pairing(info['pairing_code'], 'Phone')
                ctx = ssl.create_default_context(cafile=str(gateway._identity[0]))
                conn = http.client.HTTPSConnection('127.0.0.1', gateway.httpd.server_port, context=ctx, timeout=5)
                headers = {'Authorization': 'Bearer ' + device['credential']}
                try:
                    conn.request('GET', '/v1/snapshot', headers=headers)
                    resp = conn.getresponse()
                    self.assertEqual(resp.status, 200)
                    self.assertEqual(resp.getheader('Connection'), 'keep-alive')
                    snap = json.loads(resp.read())['data']
                    self.assertFalse(snap['chat_available'])
                    self.assertEqual(snap['chat_blocked_reason'], 'history_disabled')
                    self.assertEqual(snap['model_status'], 'unconfigured')
                    self.assertTrue(snap['capabilities']['events_stream'])
                    self.assertEqual(snap['server_epoch'], gateway.server_epoch)

                    # Reuse same TLS connection for /v1/events long-poll while another thread emits a message
                    gateway.update_desktop_state(share_history=True, preferences={'provider': 'bridge', 'provider_name': 'local', 'model': 'm1', 'selection_mode': 'manual'})
                    start_cursor = gateway.shared.cursor_bounds()[1]

                    def push_later():
                        time.sleep(0.1)
                        gateway.shared.merge_messages([{'id': 'live-1', 'role': 'assistant', 'text': 'Hola en vivo', 'at': time.time() * 1000}], 'desktop', 'thread-1', activate=True)
                        gateway.notify_events()

                    worker = threading.Thread(target=push_later, daemon=True)
                    worker.start()
                    conn.request('GET', f'/v1/events?after={start_cursor}', headers=headers)
                    ev_resp = conn.getresponse()
                    self.assertEqual(ev_resp.status, 200)
                    self.assertEqual(ev_resp.getheader('Connection'), 'keep-alive')
                    ev_data = json.loads(ev_resp.read())['data']
                    worker.join(timeout=2)
                    self.assertFalse(ev_data['resync_required'])
                    self.assertTrue(any(e['type'] == 'chat.message.created' and e['data']['id'] == 'live-1' for e in ev_data['events']))

                    # Future cursor triggers resync_required immediately
                    conn.request('GET', f'/v1/events?after={ev_data["cursor"] + 999}', headers=headers)
                    gap_resp = conn.getresponse()
                    gap_data = json.loads(gap_resp.read())['data']
                    self.assertTrue(gap_data['resync_required'])

                    # With share_history=False, message events are never leaked
                    gateway.share_history = False
                    gateway.shared.merge_messages([{'id': 'secret-1', 'role': 'assistant', 'text': 'Privado', 'at': time.time() * 1000}], 'desktop', 'thread-1')
                    blocked = gateway.shared.stream_events(ev_data['cursor'], include_messages=False, device_id=device['device_id'])
                    self.assertFalse(any(e['type'] == 'chat.message.created' for e in blocked['events']))
                finally:
                    conn.close()
            finally:
                gateway.close()

    def test_action_brain_routes_sequence_and_propose_with_pc_approval(self):
        calls = []

        def backend(method, path, body):
            calls.append((path, body))
            if path == '/axx-api/commands/resolve':
                return {'match': 'sequence', 'steps': [
                    {'command_id': 'axx.desktop.open_app', 'inputs': {'app': 'calculator'}},
                    {'command_id': 'axx.desktop.search', 'inputs': {'query': 'axx', 'engine': 'google'}},
                ]}
            if '?shared_id=' in path:
                return {'id': 'desktop-thread-1', 'mode': 'ask'}
            if path == '/axx-api/learning/prepare':
                return {'operation_id': body['operation_id'], 'state': 'awaiting_approval', 'steps': body['steps']}
            raise AssertionError(f'Unexpected call: {path}')

        with tempfile.TemporaryDirectory() as tmp:
            gateway = MobileGateway(Path(tmp) / 'state.db', tmp, backend)
            try:
                device = gateway.store.consume_pairing(gateway.store.create_pairing(), 'Phone')
                gateway.share_history = True
                # Without tools.control -> rejected without calling learning/prepare
                denied = gateway._execute_pc_command(device['device_id'], 'abre calculadora y busca axx', 'shared-1', 'task-no-perm')
                self.assertIn('permiso Work', denied)
                self.assertEqual([p for p, _ in calls], ['/axx-api/commands/resolve'])

                # With tools.control -> prepares typed plan awaiting PC approval
                gateway.store.set_tool_permission(device['device_id'], True)
                calls.clear()
                prepared = gateway._execute_pc_command(device['device_id'], 'abre calculadora y busca axx', 'shared-1', 'task-seq-1')
                self.assertIn('Plan preparado en la PC (2 paso(s):', prepared)
                self.assertIn('aprueba en Axx de la PC', prepared)
                self.assertEqual([p for p, _ in calls], ['/axx-api/commands/resolve', '/axx-api/chat/conversations?shared_id=shared-1', '/axx-api/learning/prepare'])
            finally:
                gateway.close()

    def test_action_brain_chat_tools_passed_only_when_authorized_and_receipt_honest(self):
        captured = []

        def backend(method, path, body):
            if path == '/axx-api/commands/resolve':
                return {'match': 'none'}
            if path == '/axx-api/chat':
                captured.append(body)
                return {
                    'request_id': body['request_id'],
                    'choices': [{'message': {'role': 'assistant', 'content': 'Aquí tienes el estado.'}}],
                    'axx_tool_receipt': {
                        'operation_id': 'op-tool-1', 'command_id': 'axx.system.telemetry',
                        'state': 'succeeded', 'postconditions_passed': True,
                        'output': {'cpu_percent': 14.2},
                    },
                }
            raise AssertionError(path)

        with tempfile.TemporaryDirectory() as tmp:
            from backend.chat_store import ChatStore
            db_path = Path(tmp) / 'state.db'
            chats = ChatStore(db_path)
            created = chats.mutate('create', {'title': 'Shared Tools', 'command_mode': 'auto_safe'})
            shared_id = chats.get(created['id'])['shared_id']
            chats.close()
            gateway = MobileGateway(db_path, tmp, backend)
            try:
                device = gateway.store.consume_pairing(gateway.store.create_pairing(), 'Phone')
                gateway.store.set_tool_permission(device['device_id'], True)
                gateway.update_desktop_state(
                    share_history=True,
                    preferences={'provider': 'bridge', 'provider_name': 'local', 'model': 'm1', 'selection_mode': 'manual', 'chat_tools': True},
                )
                gateway.admit_chat(device['device_id'], {'operation': 'chat', 'command_id': 'cmd-tool', 'text': '¿cómo va la CPU?', 'conversation_id': shared_id})
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    task = gateway.store.command(device['device_id'], 'cmd-tool')
                    if task['state'] not in ('admitted', 'running'):
                        break
                    time.sleep(0.01)
                self.assertEqual(task['state'], 'completed', task)
                self.assertEqual(len(captured), 1)
                self.assertTrue(captured[0].get('axx_tools'))
                self.assertEqual(captured[0].get('mobile_device_id'), device['device_id'])
                reply = gateway.shared.snapshot(shared_id)['messages'][-1]['text']
                self.assertIn('Ejecutado y verificado en la PC (axx.system.telemetry)', reply)
                self.assertIn('14.2', reply)
            finally:
                gateway.close()

    def test_input_f_keys_metrics_and_scope_cache_invalidation(self):
        for fn in [f'F{i}' for i in range(1, 13)]:
            self.assertIn(fn, WIN_KEYS)
            checked_events([{'type': 'key', 'key': fn, 'down': True}, {'type': 'key', 'key': fn, 'down': False}])

        from backend.mobile.tests.test_control import Native
        with tempfile.TemporaryDirectory() as tmp:
            gateway = MobileGateway(Path(tmp) / 'state.db', tmp, lambda *a: {})
            try:
                device = gateway.store.consume_pairing(gateway.store.create_pairing(), 'Phone')
                gateway.store.set_input_permission(device['device_id'], True)
                gateway.control.native = Native()
                state = gateway.control.acquire(device['device_id'], {'request_id': str(uuid.uuid4()), 'visible': True})
                reply = gateway.control.events(device['device_id'], {
                    'lease_id': state['lease']['lease_id'], 'boot_id': state['boot_id'], 'seq': 1,
                    'events': [{'type': 'move', 'x': 5, 'y': -3}],
                })
                self.assertIn('metrics', reply)
                self.assertGreaterEqual(reply['metrics']['send_input_ms'], 0.0)
                self.assertGreaterEqual(reply['metrics']['server_total_ms'], 0.0)
                # Immediate revocation invalidates cached scope
                gateway.store.set_input_permission(device['device_id'], False)
                self.assertFalse(gateway.store.device_has_scope(device['device_id'], 'input.control'))
            finally:
                gateway.stop()


if __name__ == '__main__':
    unittest.main()
