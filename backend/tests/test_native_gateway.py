"""Real MCP HTTP hops with owned gateway/native fixtures; never desktop input."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import secrets
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from backend.actions.executor import ActionExecutor
from backend.actions.tools import ToolResult, get_tool
from backend.mcp_host.client_manager import Transport
from backend.mcp_host.native_bridge import NativeMcpBridge


class GatewayFixture:
    """Only the fixed admitted native tool is proxied through a second HTTP hop."""
    def __init__(self, native_port, native_token, mode='normal'):
        self.native_port, self.native_token, self.mode = native_port, native_token, mode
        self.token = secrets.token_urlsafe(32)
        self.calls = self.forwards = 0
        self.received, self.release = threading.Event(), threading.Event()
        self.finished = threading.Event()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *_args):
                pass

            def handle(self):
                try:
                    super().handle()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def send_json(self, status, value=None):
                data = b'' if value is None else json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def do_POST(self):
                if self.path != '/mcp/server':
                    self.send_json(404)
                    return
                if self.headers.get('Authorization') != 'Bearer ' + fixture.token:
                    self.close_connection = True
                    self.send_json(401, {'error': 'Unauthorized fixture client'})
                    return
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                method = request['method']
                if method.startswith('notifications/'):
                    self.send_json(202)
                    return
                if method == 'initialize':
                    if fixture.mode == 'hold_initialize':
                        fixture.received.set()
                        if not fixture.release.wait(5):
                            self.send_json(504)
                            return
                    result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}},
                              'serverInfo': {'name': 'owned-gateway-fixture', 'version': '1.0'}}
                elif method == 'tools/list':
                    result = {'tools': [{'name': 'axx_windows_native_execute',
                        'inputSchema': {'type': 'object', 'properties': {'ticket': {'type': 'string'}},
                                        'required': ['ticket'], 'additionalProperties': False}}]}
                elif method == 'tools/call':
                    fixture.calls += 1
                    fixture.received.set()
                    params = request['params']
                    if params['name'] != 'axx_windows_native_execute' or set(params['arguments']) != {'ticket'}:
                        self.send_json(400, {'error': 'Unexpected gateway tool'})
                        return
                    if fixture.mode == 'hold_before' and not fixture.release.wait(5):
                        self.send_json(504, {'error': 'Fixture release deadline'})
                        return
                    upstream = None
                    try:
                        upstream = Transport({'transport': 'streamable_http',
                            'url': f'http://127.0.0.1:{fixture.native_port}/mcp',
                            'token': fixture.native_token})
                        def forward():
                            fixture.forwards += 1
                            return upstream.request('tools/call', name='axx_native_execute',
                                                    arguments=params['arguments'])
                        child = forward()
                        if fixture.mode == 'duplicate':
                            duplicate = forward()
                            if duplicate != child:
                                raise ValueError('Duplicate native redemption changed its receipt')
                        if fixture.mode == 'drop_after':
                            self.connection.shutdown(socket.SHUT_RDWR)
                            self.close_connection = True
                            return
                        if fixture.mode == 'forged_receipt':
                            child['structuredContent'] = {'receipt': 'not-the-native-receipt'}
                        if fixture.mode == 'nested_error':
                            child['isError'] = True
                        result = {'content': [{'type': 'text', 'text': json.dumps(child)}], 'isError': False}
                    except Exception:
                        result = {'content': [{'type': 'text', 'text': json.dumps({
                            'content': [{'type': 'text', 'text': 'Native fixture rejected request'}],
                            'isError': True})}], 'isError': False}
                    finally:
                        if upstream is not None:
                            upstream.close()
                        fixture.finished.set()
                else:
                    self.send_json(400, {'error': 'Unexpected MCP fixture method'})
                    return
                try:
                    self.send_json(200, {'jsonrpc': '2.0', 'id': request['id'], 'result': result})
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/mcp/server'

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


@contextmanager
def configured_bridge(mode='normal', *, wrong_gateway_token=False, wrong_native_token=False, wrong_peer=False):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        native_port = reservation.getsockname()[1]
    native_token = secrets.token_urlsafe(32)
    gateway = GatewayFixture(native_port, 'wrong-token' if wrong_native_token else native_token, mode)
    config = {'version': 1, 'listen_host': '127.0.0.1', 'listen_port': native_port,
              'allowed_peer': '127.0.0.2' if wrong_peer else '127.0.0.1', 'native_token': native_token,
              'gateway_url': gateway.url,
              'gateway_token': 'wrong-token' if wrong_gateway_token else gateway.token}
    bridge = None
    with patch('backend.mcp_host.native_bridge.load_gateway_config', return_value=config), \
            patch('backend.mcp_host.native_gateway.verify_wsl_network'):
        try:
            bridge = NativeMcpBridge('unused-owned-fixture')
            yield bridge, gateway
        finally:
            gateway.release.set()
            if bridge is not None:
                if bridge.active:
                    bridge.active['cancelled'].set()
                    bridge.active['finished'].wait(5)
                bridge.close()
            gateway.close()


class NativeGatewayTests(unittest.TestCase):
    def test_typed_uia_write_and_invoke_use_gateway_and_preserve_unknown_effect(self):
        reference = {'window_id': '1', 'pid': 123, 'control_id': 'a' * 64,
                     'expected_title': 'Owned UI fixture'}
        value = 'Texto de prueba ñ 🚀'
        cases = [
            ('desktop_set_window_value', dict(reference, value=value), 'succeeded',
             ToolResult(True, output={'value_set': True}, evidence={
                 'verification': 'uia_value_readback',
                 'value_sha256': hashlib.sha256(value.encode()).hexdigest(),
                 'value_length': len(value.encode('utf-16-le')) // 2})),
            ('desktop_invoke_window_button', dict(reference, expected_name='Confirmar'), 'unknown',
             ToolResult(True, output={'button_sent': True}, evidence={
                 'verification': 'uia_invoke_acknowledged', 'accepted': True})),
        ]
        for name, inputs, expected_state, tool_result in cases:
            with self.subTest(tool=name), configured_bridge('duplicate') as (bridge, gateway), \
                    tempfile.TemporaryDirectory() as folder:
                tool = get_tool(name)
                with ActionExecutor(Path(folder) / 'state.db', folder) as executor, \
                        patch.object(tool, 'execute_with_control', return_value=tool_result) as body:
                    executor.native_bridge = bridge
                    result = executor.execute_action(name, inputs, name)
                    self.assertEqual(result['state'], expected_state, result)
                    self.assertEqual(result['postconditions_passed'], expected_state == 'succeeded')
                    self.assertEqual(result['evidence']['transport'], 'anythingmcp_streamable_http')
                    self.assertEqual(result['evidence']['native_operation_id'], name)
                    if expected_state == 'unknown':
                        self.assertEqual(result['effect_status'], 'unknown')
                        self.assertEqual(result['dispatch_status'], 'delivered')
                        self.assertTrue(result['evidence']['reconciliation_required'])
                    replay = executor.execute_action(name, inputs, name)
                    self.assertTrue(replay['replayed'])
                    self.assertEqual(replay['state'], expected_state)
                    body.assert_called_once()
                    self.assertEqual(executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
                self.assertEqual((gateway.calls, gateway.forwards), (1, 2))

    def test_real_gateway_single_use_receipt_and_one_executor_journal(self):
        calls = []
        class OwnedReadTool:
            parameter_names = set()
            def verify_preconditions(self, _inputs):
                return True, 'Owned fixture'
            def execute_cancellable(self, _inputs, _workspace, _cancelled):
                calls.append(1)
                return ToolResult(True, output={'observed': 42}, evidence={'verification': 'owned_fixture'})
            def verify_postconditions(self, _inputs, result):
                return result.success and result.output == {'observed': 42}, 'Owned fixture readback'
        with configured_bridge('duplicate') as (bridge, gateway), tempfile.TemporaryDirectory() as folder:
            with ActionExecutor(Path(folder) / 'state.db', folder) as executor:
                executor.native_bridge = bridge
                executor.dynamic_tools['desktop_list_windows'] = OwnedReadTool()
                result = executor.execute_action('desktop_list_windows', {}, 'one-native-operation')
                self.assertEqual(result['state'], 'succeeded', result)
                self.assertTrue(result['postconditions_passed'])
                self.assertEqual(result['evidence']['transport'], 'anythingmcp_streamable_http')
                self.assertEqual(result['evidence']['gateway_url'], gateway.url)
                self.assertEqual(result['evidence']['native_operation_id'], 'one-native-operation')
                self.assertTrue(executor.execute_action('desktop_list_windows', {}, 'one-native-operation')['replayed'])
                self.assertEqual(executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
            self.assertEqual(calls, [1])
            self.assertEqual((gateway.calls, gateway.forwards), (1, 2))
            self.assertEqual(bridge.status()['mode'], 'gateway')
            self.assertEqual(bridge.status()['state'], 'verified')
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(f'http://127.0.0.1:{bridge.port}/mcp', timeout=3)
            self.assertEqual(denied.exception.code, 401)
            with self.assertRaises(ValueError):
                bridge._redeem('unadmitted')

    def test_wrong_gateway_or_native_credential_never_invokes_the_body(self):
        for key in ('wrong_gateway_token', 'wrong_native_token', 'wrong_peer'):
            with self.subTest(credential=key), configured_bridge(**{key: True}) as (bridge, gateway):
                calls = []
                result = bridge.execute('desktop_list_windows', lambda: calls.append(1), threading.Event(), key)
                self.assertFalse(result.success)
                self.assertFalse(result.evidence['effect_uncertain'])
                self.assertEqual(calls, [])
                self.assertLessEqual(gateway.calls, 1)
                self.assertEqual(bridge.status()['state'], 'error')

    def test_cancel_while_gateway_initializes_never_admits_a_body(self):
        with configured_bridge('hold_initialize') as (bridge, gateway), ThreadPoolExecutor(max_workers=1) as pool:
            calls, cancelled = [], threading.Event()
            future = pool.submit(bridge.execute, 'desktop_list_windows', lambda: calls.append(1), cancelled, 'cancel-startup')
            try:
                self.assertTrue(gateway.received.wait(5))
                cancelled.set()
                result = future.result(3)
                self.assertFalse(result.success)
                self.assertFalse(result.evidence['effect_uncertain'])
                self.assertEqual(calls, [])
                self.assertEqual(gateway.calls, 0)
                self.assertIsNone(bridge.active)
            finally:
                gateway.release.set()

    def test_bad_or_error_receipt_after_native_effect_stays_uncertain(self):
        for mode in ('forged_receipt', 'nested_error', 'drop_after'):
            with self.subTest(mode=mode), configured_bridge(mode) as (bridge, gateway):
                calls = []
                def primitive():
                    calls.append(1)
                    return ToolResult(True, output={'observed': 42})
                result = bridge.execute('desktop_list_windows', primitive, threading.Event(), mode)
                self.assertFalse(result.success)
                self.assertTrue(result.evidence['effect_uncertain'])
                self.assertEqual(calls, [1])
                self.assertEqual(gateway.calls, 1)
                self.assertEqual(gateway.forwards, 1)

    def test_cancel_before_dispatch_and_expired_ticket_do_not_invoke_body(self):
        with configured_bridge() as (bridge, gateway):
            cancelled = threading.Event()
            cancelled.set()
            calls = []
            result = bridge.execute('desktop_list_windows', lambda: calls.append(1), cancelled, 'pre-cancelled')
            self.assertFalse(result.success)
            self.assertTrue(result.evidence['cancelled'])
            self.assertEqual((gateway.calls, calls), (0, []))
        with configured_bridge('hold_before') as (bridge, gateway), ThreadPoolExecutor(max_workers=1) as pool:
            calls = []
            future = pool.submit(bridge.execute, 'desktop_list_windows', lambda: calls.append(1), threading.Event(), 'expired')
            try:
                self.assertTrue(gateway.received.wait(5))
                with bridge.lock:
                    bridge.active['expires'] = time.monotonic() - 1
                gateway.release.set()
                result = future.result(10)
                self.assertFalse(result.success)
                self.assertFalse(result.evidence['effect_uncertain'])
                self.assertEqual(calls, [])
            finally:
                gateway.release.set()

    def test_cancel_during_native_body_blocks_another_body_until_finished(self):
        with configured_bridge() as (bridge, gateway), ThreadPoolExecutor(max_workers=1) as pool:
            entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()
            calls = []
            def primitive():
                calls.append(1)
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('Owned body release deadline')
                return ToolResult(True)
            future = pool.submit(bridge.execute, 'desktop_list_windows', primitive, cancelled, 'cancel-during')
            try:
                self.assertTrue(entered.wait(5))
                cancelled.set()
                result = future.result(3)
                self.assertFalse(result.success)
                self.assertTrue(result.evidence['effect_uncertain'])
                second = bridge.execute('desktop_list_windows', primitive, threading.Event(), 'must-not-overlap')
                self.assertFalse(second.success)
                self.assertEqual(calls, [1])
                self.assertEqual(gateway.calls, 1)
            finally:
                release.set()
                if bridge.active:
                    self.assertTrue(bridge.active['finished'].wait(5))
            recovered = bridge.execute('desktop_list_windows', primitive, threading.Event(), 'explicit-after-finished')
            self.assertTrue(recovered.success, recovered.error)
            self.assertEqual(calls, [1, 1])
            self.assertEqual(gateway.calls, 2)

    def test_configured_but_offline_gateway_does_not_fall_back_to_native(self):
        with configured_bridge() as (bridge, gateway):
            gateway.server.shutdown()
            gateway.server.server_close()
            calls = []
            result = bridge.execute('desktop_list_windows', lambda: calls.append(1), threading.Event(), 'offline')
            self.assertFalse(result.success)
            self.assertFalse(result.evidence['effect_uncertain'])
            self.assertEqual(calls, [])
            self.assertEqual(gateway.calls, 0)

    def test_invalid_private_config_fails_closed_without_starting_native(self):
        with patch('backend.mcp_host.native_bridge.load_gateway_config', side_effect=ValueError('Invalid fixture config')):
            bridge = NativeMcpBridge('unused-owned-fixture')
        try:
            calls = []
            result = bridge.execute('desktop_list_windows', lambda: calls.append(1), threading.Event(), 'invalid-config')
            self.assertFalse(result.success)
            self.assertFalse(result.evidence['effect_uncertain'])
            self.assertEqual(calls, [])
            self.assertIsNone(bridge.server)
            self.assertIsNone(bridge.transport)
        finally:
            bridge.close()


if __name__ == '__main__':
    unittest.main()
