import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.actions import browser_bridge as bridge


class BrowserBridgeContracts(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'AXX_BROWSER_CDP_URL': 'http://127.0.0.1:9229', 'AXX_BROWSER_PROFILE_LABEL': 'test-prepared'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.identity = {'tab_id': 'A1', 'expected_url': 'https://example.com/', 'browser_session': 'a' * 64}
        self.inventory = {'browser_session': 'a' * 64, 'configured_profile_label': 'test-prepared',
                          'tabs': [{'tab_id': 'A1', 'url': 'https://example.com/', '_socket': 'ws://127.0.0.1:9229/devtools/page/A1'}]}

    def test_unconfigured_and_remote_endpoints_are_not_connected(self):
        for endpoint in ('', 'http://example.com:9222', 'http://localhost:9222', 'https://127.0.0.1:9222',
                         'http://127.0.0.1:9222/path', 'http://user:secret@127.0.0.1:9222', 'http://127.0.0.1'):
            with self.subTest(endpoint=endpoint), patch.dict(os.environ, {'AXX_BROWSER_CDP_URL': endpoint}), patch.object(bridge, '_json') as request:
                result = bridge.BrowserBridgeTool('tabs').execute({})
                self.assertFalse(result.success)
                request.assert_not_called()

    def test_model_cannot_supply_endpoint_or_executable_page_url(self):
        for extra in ({'endpoint': 'http://127.0.0.1:1'}, {'script': 'alert(1)'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                bridge.validate_inputs('inspect', {**self.identity, **extra})
        for url in ('javascript:alert(1)', 'file:///C:/secret.txt', 'data:text/html,hello'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                bridge.validate_inputs('navigate', {**self.identity, 'document_id': 'doc1', 'url': url})

    def test_inventory_rejects_advertised_remote_or_different_target_socket(self):
        version = {'webSocketDebuggerUrl': 'ws://127.0.0.1:9229/devtools/browser/B1'}
        for socket in ('ws://remote.example:9229/devtools/page/A1', 'ws://127.0.0.1:9228/devtools/page/A1',
                       'ws://127.0.0.1:9229/devtools/page/A2'):
            with self.subTest(socket=socket), patch.object(bridge, '_json', side_effect=[version, [
                    {'id': 'A1', 'type': 'page', 'url': 'https://example.com/', 'webSocketDebuggerUrl': socket}]]):
                with self.assertRaises(ValueError):
                    bridge.discover()

    def test_session_tab_and_url_changes_prevent_socket_connection(self):
        for inputs in ({**self.identity, 'browser_session': 'b' * 64}, {**self.identity, 'tab_id': 'B1'},
                       {**self.identity, 'expected_url': 'https://other.example/'}):
            with self.subTest(inputs=inputs), patch.object(bridge, 'discover', return_value=self.inventory), patch.object(bridge, '_Connection') as connection:
                result = bridge.BrowserBridgeTool('inspect').execute(inputs)
                self.assertFalse(result.success)
                connection.assert_not_called()

    def test_stale_document_never_dispatches_navigation(self):
        with patch.object(bridge, 'discover', return_value=self.inventory), patch.object(bridge, '_Connection') as connection:
            connection.return_value.call.return_value = {'frameTree': {'frame': {'id': 'frame', 'loaderId': 'fresh', 'url': self.identity['expected_url']}}}
            result = bridge.BrowserBridgeTool('navigate').execute({**self.identity, 'document_id': 'stale', 'url': 'https://example.com/next'})
            self.assertFalse(result.success)
            self.assertFalse(result.evidence['effect_uncertain'])
            self.assertEqual([call.args[0] for call in connection.return_value.call.call_args_list], ['Page.getFrameTree'])

    def test_cancel_before_observation_does_not_contact_browser(self):
        event = threading.Event()
        event.set()
        with patch.object(bridge, 'discover') as discover:
            result = bridge.BrowserBridgeTool('inspect').execute_cancellable(self.identity, None, event)
        self.assertFalse(result.success)
        self.assertFalse(result.evidence['effect_uncertain'])
        discover.assert_not_called()

    def test_timeout_after_navigation_stays_uncertain(self):
        def call(method, params=None):
            if method == 'Page.getFrameTree':
                return {'frameTree': {'frame': {'id': 'frame', 'loaderId': 'doc1', 'url': self.identity['expected_url']}}}
            if method == 'Page.navigate':
                raise TimeoutError('lost navigation response')
            return {}
        with patch.object(bridge, 'discover', return_value=self.inventory), patch.object(bridge, '_Connection') as connection:
            connection.return_value.call.side_effect = call
            result = bridge.BrowserBridgeTool('navigate').execute({**self.identity, 'document_id': 'doc1', 'url': 'https://example.com/next'})
        self.assertFalse(result.success)
        self.assertTrue(result.evidence['effect_uncertain'])
        self.assertEqual(result.evidence['effect_status'], 'unknown')


@unittest.skipUnless(os.environ.get('AXX_RUN_BROWSER_FIXTURE') == '1', 'Opt-in isolated real browser fixture')
class PreparedBrowserNativeTests(unittest.TestCase):
    def test_real_isolated_browser_observation_navigation_and_redirect(self):
        executable = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
        if not executable.is_file():
            self.skipTest('Microsoft Edge executable unavailable')

        class Fixture(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/second')
                    self.end_headers()
                    return
                body = ('<!doctype html><title>Axx isolated browser fixture</title><h1>'
                        + ('Second document' if self.path == '/second' else 'First document')
                        + '</h1><a href="/second">Next document</a><button>Read-only fixture</button>').encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        profile = tempfile.TemporaryDirectory(prefix='axx-browser-fixture-')
        process = None
        try:
            base = 'http://127.0.0.1:' + str(server.server_port)
            process = subprocess.Popen([str(executable), '--headless=new', '--remote-debugging-address=127.0.0.1',
                                        '--remote-debugging-port=0', '--user-data-dir=' + profile.name,
                                        '--no-first-run', '--no-default-browser-check', base + '/first'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            active = Path(profile.name) / 'DevToolsActivePort'
            deadline = time.monotonic() + 15
            while not active.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            self.assertTrue(active.exists(), 'Isolated browser did not expose its ephemeral CDP endpoint')
            port = int(active.read_text().splitlines()[0])
            with patch.dict(os.environ, {'AXX_BROWSER_CDP_URL': 'http://127.0.0.1:' + str(port),
                                         'AXX_BROWSER_PROFILE_LABEL': 'disposable-native-test'}):
                tabs = bridge.BrowserBridgeTool('tabs').execute({})
                self.assertTrue(tabs.success, tabs.error)
                target = next(row for row in tabs.output['tabs'] if row['url'] == base + '/first')
                identity = {'browser_session': tabs.output['browser_session'], 'tab_id': target['tab_id'], 'expected_url': target['url']}
                observed = bridge.BrowserBridgeTool('inspect').execute(identity)
                self.assertTrue(observed.success, observed.error)
                self.assertTrue(any('First document' in row['name'] for row in observed.output['elements']))
                inputs = {**identity, 'document_id': observed.output['document_id'], 'url': base + '/second'}
                navigate = bridge.BrowserBridgeTool('navigate')
                result = navigate.execute(inputs)
                self.assertTrue(result.success, result.error)
                self.assertTrue(navigate.verify_postconditions(inputs, result)[0])
                self.assertNotEqual(observed.output['document_id'], result.output['document_id'])
                second = bridge.BrowserBridgeTool('inspect').execute({**identity, 'expected_url': base + '/second'})
                self.assertTrue(second.success, second.error)
                self.assertTrue(any('Second document' in row['name'] for row in second.output['elements']))
                stale = navigate.execute(inputs)
                self.assertFalse(stale.success)
                self.assertFalse(stale.evidence['effect_uncertain'])
                redirected = navigate.execute({**identity, 'expected_url': base + '/second',
                                                'document_id': second.output['document_id'], 'url': base + '/redirect'})
                self.assertFalse(redirected.success)
                self.assertTrue(redirected.evidence['effect_uncertain'])
                self.assertIn('redirected', redirected.error)
        finally:
            if process and process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                process.wait(timeout=10)
            server.shutdown()
            server.server_close()
            for attempt in range(20):
                try:
                    profile.cleanup()
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(.1)


if __name__ == '__main__':
    unittest.main()
