import http.client
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from backend.telegram.daemon import CallbackServer, ChatProxy, CommandProxy, CoreClient, DisabledInference, maintain, remove_endpoint, write_endpoint, write_health


class DaemonTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.service.status.return_value = {'state': 'configured'}
        self.service.admit.return_value = {'state': 'succeeded', 'text': 'ok'}
        self.service.admit_bot.return_value = {'state': 'blocked', 'text': 'not enabled'}
        self.server = CallbackServer(self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, token=None, origin=None, host=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Authorization': 'Bearer ' + (token or ''), 'Content-Type': 'application/json'}
        if origin is not None:
            headers['Origin'] = origin
        if host is not None:
            headers['Host'] = host
        try:
            conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_restart_backoff_and_sanitized_health(self):
        service = Mock()
        service.bot_process = None
        facade = Mock()
        facade.server = None
        next_at = maintain(service, facade, Path('local-endpoint'), 6451, 100, 0)
        self.assertEqual(next_at, 110)
        maintain(service, facade, Path('local-endpoint'), 6451, 109, next_at)
        service.start_bot.assert_called_once()
        facade.start.assert_called_once_with(port=6451)
        maintain(service, facade, Path('local-endpoint'), 6451, 110, next_at)
        self.assertEqual(service.start_bot.call_count, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'health.json'
            write_health(path, True, service, facade)
            value = json.loads(path.read_text())
        self.assertEqual(set(value), {'core_bound', 'bot_running', 'miniapp_port', 'checked_at'})
        self.assertTrue(value['core_bound'])
        self.assertFalse(value['bot_running'])
        self.assertIsNone(value['miniapp_port'])

    def test_callback_requires_token_loopback_host_and_no_origin(self):
        route = '/axx-api/telegram/input'
        for options in ({}, {'token': 'invalid'}, {'token': self.server.token, 'origin': 'https://evil.invalid'},
                        {'token': self.server.token, 'host': 'evil.invalid'}):
            with self.subTest(options=options):
                self.assertEqual(self.request('POST', route, {'text':'test'}, **options)[0], 403)
        self.service.admit.assert_not_called()
        self.assertEqual(self.request('POST', route, {'text':'test'}, token=self.server.token)[0], 200)
        self.service.admit.assert_called_once_with({'text':'test'})

    def test_callback_routes_bot_and_rejects_arbitrary_paths(self):
        self.assertEqual(self.request('POST', '/axx-api/telegram/bot-input', {'text':'test'}, token=self.server.token)[0], 200)
        self.service.admit_bot.assert_called_once_with({'text':'test'})
        self.assertEqual(self.request('POST', '/axx-api/commands/execute', {}, token=self.server.token)[0], 404)
        self.assertEqual(self.request('GET', '/axx-api/telegram/status', token=self.server.token)[1]['state'], 'configured')

    def test_proxies_use_existing_routes_and_never_grant_approval(self):
        core = Mock()
        core.request.return_value = {'state':'prepared'}
        chat, commands = ChatProxy(core), CommandProxy(core)
        chat.get('id')
        core.request.assert_called_with('GET', '/axx-api/chat/conversations?id=id')
        commands.prepare('a', {}, source='text', operation_id='id', conversation_id='chat', command_mode='ask')
        self.assertEqual(core.request.call_args.args[2]['command_mode'], 'ask')
        with self.assertRaises(ValueError):
            commands.execute('id', approved=True)
        commands.execute('id')
        self.assertFalse(core.request.call_args.args[2]['approved'])
        self.assertFalse(DisabledInference().route({})['ok'])

    def test_descriptor_does_not_replace_another_instance_or_native_endpoint(self):
        with tempfile.TemporaryDirectory() as directory, patch('backend.telegram.daemon._dpapi_encrypt', side_effect=lambda x:x), patch('backend.telegram.daemon._dpapi_decrypt', side_effect=lambda x:x):
            path = Path(directory) / 'telegram/local-channel/connect/endpoint.dpapi'
            write_endpoint(path, self.server)
            old = self.server.instance_id
            self.server.instance_id = 'other-instance'
            remove_endpoint(path, self.server)
            self.assertTrue(path.exists())
            self.server.instance_id = old
            remove_endpoint(path, self.server)
            self.assertFalse(path.exists())

    def test_installed_endpoint_identity_change_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch('backend.telegram.daemon._dpapi_decrypt', side_effect=lambda x:x):
            path = Path(directory) / 'endpoint.dpapi'
            path.write_text(json.dumps({'port': 1234, 'token':'x'*40, 'instance_id':'a'}))
            core = CoreClient(path)
            core.instance_id = 'a'
            self.assertEqual(core._descriptor()['instance_id'], 'a')
            path.write_text(json.dumps({'port': 1234, 'token':'x'*40, 'instance_id':'b'}))
            with self.assertRaises(RuntimeError):
                core._descriptor()


if __name__ == '__main__':
    unittest.main()
