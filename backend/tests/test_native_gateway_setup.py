import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from backend.mcp_host import native_gateway


spec = importlib.util.spec_from_file_location('configure_native_gateway',
    Path(__file__).resolve().parents[2]/'scripts/configure-native-gateway.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
NETWORK = {'listen_host': '172.16.5.1', 'allowed_peer': '172.16.5.10'}


class GatewayRecoveryTests(unittest.TestCase):
    def test_online_gateway_does_not_start_a_service(self):
        config=dict(NETWORK,gateway_url='http://127.0.0.1:4000/mcp/owned')
        with patch.object(native_gateway,'verify_wsl_network'), patch.object(native_gateway.socket,'create_connection'), \
                patch.object(native_gateway.importlib.util,'spec_from_file_location') as load:
            native_gateway.ensure_gateway(config,Path('unused'),None)
            load.assert_not_called()

    def test_offline_gateway_resumes_saved_stack_and_revalidates_network(self):
        config=dict(NETWORK,gateway_url='http://127.0.0.1:4000/mcp/owned')
        from unittest.mock import Mock
        module=SimpleNamespace(resume=Mock());spec=SimpleNamespace(loader=SimpleNamespace(exec_module=Mock()))
        with patch.object(native_gateway,'verify_wsl_network',side_effect=[ValueError('offline'),None]) as verify, \
                patch.object(native_gateway.socket,'create_connection'), \
                patch.object(native_gateway.importlib.util,'spec_from_file_location',return_value=spec), \
                patch.object(native_gateway.importlib.util,'module_from_spec',return_value=module):
            native_gateway.ensure_gateway(config,Path('owned'),None)
            module.resume.assert_called_once_with(Path('owned/anythingmcp'),None)
            self.assertEqual(verify.call_count,2)

    def test_failed_recovery_never_changes_route_or_ignores_network(self):
        config=dict(NETWORK,gateway_url='http://127.0.0.1:4000/mcp/owned')
        from unittest.mock import Mock
        module=SimpleNamespace(resume=Mock());spec=SimpleNamespace(loader=SimpleNamespace(exec_module=Mock()))
        with patch.object(native_gateway,'verify_wsl_network',side_effect=ValueError('changed network')), \
                patch.object(native_gateway.importlib.util,'spec_from_file_location',return_value=spec), \
                patch.object(native_gateway.importlib.util,'module_from_spec',return_value=module):
            before=dict(config)
            with self.assertRaisesRegex(native_gateway.GatewayUnavailable,'changed network'):
                native_gateway.ensure_gateway(config,Path('owned'),None)
            self.assertEqual(config,before)


class FakeApi:
    def __init__(self):
        self.calls = []
        self.hosts = ['existing.internal']
        self.connectors = {'public': {'id': 'public', 'name': 'Existing public connector'}}
        self.servers = {'default-server': {'id': 'default-server', 'name': 'Default', 'slug': 'default',
            'connectors': [{'id': 'relation-public', 'connectorId': 'public'}]}}
        self.tools = {}
        self.keys = []
        self.fail_after = None
        self.reject = None

    def __call__(self, method, route, body=None):
        self.calls.append((method, route, copy.deepcopy(body)))
        if self.reject == (method, route):
            raise setup.Rejected('La sesión administrativa caducó')
        if route == 'admin/settings/ssrf-allowed-hosts':
            if method == 'PUT':
                self.hosts = list(body['hosts'])
            result = {'hosts': list(self.hosts)}
        elif route == 'connectors':
            if method == 'GET':
                result = list(self.connectors.values())
            else:
                key = 'native-connector'
                result = self.connectors[key] = dict(body, id=key)
                self.servers['default-server']['connectors'].append({'id': 'relation-'+key, 'connectorId': key})
        elif route.startswith('connectors/'):
            parts = route.split('/')
            if len(parts) == 2:
                result = self.connectors[parts[1]]
                if method == 'PUT':
                    assert 'type' not in body and 'description' not in body
                    result.update(body)
            elif len(parts) == 3:
                if method == 'GET':
                    result = list(self.tools.values())
                else:
                    assert 'isEnabled' not in body
                    result = self.tools['native-tool'] = dict(body, id='native-tool')
            else:
                result = self.tools[parts[3]]
                if method == 'PUT':
                    result.update(body)
        elif route == 'mcp-servers':
            if method == 'GET':
                result = list(self.servers.values())
            else:
                result = self.servers['native-server'] = dict(body, id='native-server', connectors=[])
        elif route.startswith('mcp-servers/'):
            parts = route.split('/')
            result = self.servers[parts[1]]
            if len(parts) == 3:
                result['connectors'] = [{'id': 'relation-'+key, 'connectorId': key} for key in body['connectorIds']]
        elif route == 'mcp-keys':
            result = dict(body, id='native-key', key='mcp_'+('test_only_'*8))
            self.keys.append(result)
        else:
            raise AssertionError((method, route))
        if self.fail_after == (method, route):
            raise setup.SetupError('Transport stopped after possible write')
        return copy.deepcopy(result)


class NativeGatewaySetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)/'Axx'
        self.api = FakeApi()
        network = patch.object(setup, 'verify_wsl_network')
        network.start()
        self.addCleanup(network.stop)
        sockets = patch.object(setup.socket, 'socket')
        self.socket = sockets.start()
        self.socket.return_value.__enter__.return_value.getsockname.return_value = (NETWORK['listen_host'], 45678)
        self.addCleanup(sockets.stop)

    def provision(self, network=NETWORK):
        return setup.Provisioner(self.directory, self.api).configure(network)

    def test_idempotent_resources_secrets_and_default_membership(self):
        result = self.provision()
        original = setup.read_private(self.directory/setup.CONFIG_NAME)
        self.assertEqual(result['state'], 'configured_not_runtime_verified')
        self.assertEqual(self.api.hosts, ['existing.internal', NETWORK['listen_host']])
        self.assertEqual(self.api.servers['default-server']['connectors'], [{'id': 'relation-public', 'connectorId': 'public'}])
        self.assertEqual(self.api.servers['native-server']['connectors'], [{'id': 'relation-native-connector', 'connectorId': 'native-connector'}])
        self.assertEqual(len(self.api.tools), 1)
        tool = self.api.tools['native-tool']
        self.assertEqual(tool['name'], setup.GATEWAY_TOOL)
        self.assertEqual(tool['endpointMapping'], {'method': 'axx_native_execute', 'bodyMapping': {'ticket': '$ticket'}})
        self.assertEqual(tool['parameters']['properties'], {'ticket': {'type': 'string'}})
        self.assertEqual(tool['responseMapping'], {'cacheTtl': 0})
        self.assertEqual(self.api.keys[0]['mcpServerId'], 'native-server')
        first_posts = sum(method == 'POST' for method, _, _ in self.api.calls)
        self.provision()
        self.assertEqual(sum(method == 'POST' for method, _, _ in self.api.calls), first_posts)
        again = setup.read_private(self.directory/setup.CONFIG_NAME)
        self.assertEqual(again, original)
        self.assertEqual(self.socket.call_count, 1)
        public = json.dumps(setup.status(self.directory))
        self.assertNotIn(original['native_token'], public)
        self.assertNotIn(original['gateway_token'], public)

    def test_network_change_preserves_tokens_port_and_prior_allowlist(self):
        self.provision()
        before = setup.read_private(self.directory/setup.CONFIG_NAME)
        changed = {'listen_host': '172.17.6.1', 'allowed_peer': '172.17.6.20'}
        self.provision(changed)
        after = setup.read_private(self.directory/setup.CONFIG_NAME)
        self.assertEqual(after['native_token'], before['native_token'])
        self.assertEqual(after['gateway_token'], before['gateway_token'])
        self.assertEqual(after['listen_port'], before['listen_port'])
        self.assertEqual(after['listen_host'], changed['listen_host'])
        self.assertEqual(self.api.hosts, ['existing.internal', NETWORK['listen_host'], changed['listen_host']])
        self.assertEqual(len(self.api.keys), 1)

    def test_lost_write_response_blocks_automatic_duplicate_creation(self):
        self.api.fail_after = ('POST', 'connectors')
        with self.assertRaises(setup.SetupError):
            self.provision()
        self.assertIn('native-connector', self.api.connectors)
        saved = setup.read_private(self.directory/'anythingmcp'/setup.STATE_NAME)
        self.assertEqual(saved['pending_write']['route'], 'connectors')
        calls = len(self.api.calls)
        with self.assertRaisesRegex(setup.SetupError, 'sin confirmar'):
            self.provision()
        self.assertEqual(len(self.api.calls), calls)
        self.assertFalse((self.directory/setup.CONFIG_NAME).exists())

    def test_known_rejection_does_not_login_or_leave_ambiguous_write(self):
        self.api.reject = ('PUT', 'admin/settings/ssrf-allowed-hosts')
        with self.assertRaises(setup.Rejected):
            self.provision()
        saved = setup.read_private(self.directory/'anythingmcp'/setup.STATE_NAME)
        self.assertNotIn('pending_write', saved)
        self.assertFalse(any('auth/login' in route for _, route, _ in self.api.calls))

    def test_failure_keeps_previous_core_config_and_unrelated_resources(self):
        self.provision()
        before = (self.directory/setup.CONFIG_NAME).read_bytes()
        self.api.fail_after = ('PUT', 'connectors/native-connector')
        with self.assertRaises(setup.SetupError):
            self.provision({'listen_host': '172.17.6.1', 'allowed_peer': '172.17.6.20'})
        self.assertEqual((self.directory/setup.CONFIG_NAME).read_bytes(), before)
        self.assertEqual(self.api.connectors['public'], {'id': 'public', 'name': 'Existing public connector'})

    def test_foreign_connector_on_managed_server_is_not_removed(self):
        self.provision()
        self.api.servers['native-server']['connectors'].append({'id': 'relation-public', 'connectorId': 'public'})
        with self.assertRaisesRegex(setup.SetupError, 'ajenos'):
            self.provision()
        self.assertEqual(self.api.servers['native-server']['connectors'],
            [{'id': 'relation-native-connector', 'connectorId': 'native-connector'}, {'id': 'relation-public', 'connectorId': 'public'}])

    def test_disable_keeps_exact_backup_and_gateway_resources(self):
        self.provision()
        before = (self.directory/setup.CONFIG_NAME).read_bytes()
        calls = len(self.api.calls)
        result = setup.disable(self.directory)
        self.assertTrue(result['restart_required'])
        self.assertEqual(Path(result['backup']).read_bytes(), before)
        self.assertFalse((self.directory/setup.CONFIG_NAME).exists())
        self.assertEqual(len(self.api.calls), calls)
        self.assertEqual(setup.status(self.directory)['state'], 'direct_after_restart')

    def test_admin_redirect_or_expired_session_is_rejected_without_secret_output(self):
        token = 'test_only.header.signature'
        api = setup.Api(token)
        for code in (302, 401):
            with self.subTest(code=code), patch.object(api.opener, 'open', side_effect=urllib.error.HTTPError(
                    'http://127.0.0.1:4000/api/connectors', code, 'fixture rejection', {}, io.BytesIO(token.encode()))):
                with self.assertRaises(setup.Rejected) as rejected:
                    api('POST', 'connectors', {'name': 'test-only'})
                self.assertNotIn(token, str(rejected.exception))

    @unittest.skipUnless(os.name == 'nt', 'Private login requires Windows DPAPI')
    def test_explicit_login_prompts_and_saves_only_raw_jwt_encrypted(self):
        password, token = 'test-only-interactive-password', 'test_only.header.signature'
        with patch('builtins.input', return_value='unit@example.test'), \
                patch.object(setup.getpass, 'getpass', return_value=password) as get_password, \
                patch.object(setup.urllib.request, 'build_opener') as build, \
                patch.object(setup.sys, 'argv', ['setup', 'login', '--data-dir', str(self.directory)]):
            opener = build.return_value
            opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({'accessToken': token}).encode()
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(setup.main(), 0)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:4000/api/auth/login')
            self.assertEqual(json.loads(request.data), {'email': 'unit@example.test', 'password': password})
            self.assertEqual(opener.open.call_args.kwargs['timeout'], 20)
            get_password.assert_called_once()
            self.assertEqual(json.loads(output.getvalue()), {'authenticated': True})
            self.assertNotIn(password, output.getvalue())
            self.assertNotIn(token, output.getvalue())
        session = self.directory/'anythingmcp/administrator-session.dpapi'
        self.assertEqual(setup._dpapi_decrypt(session.read_bytes()), token.encode())
        self.assertNotIn(token.encode(), session.read_bytes())
        self.assertEqual([path.name for path in session.parent.iterdir()], ['administrator-session.dpapi'])

    @unittest.skipUnless(os.name == 'nt', 'Private login requires Windows DPAPI')
    def test_rejected_or_malformed_login_preserves_session_without_retry(self):
        folder = self.directory/'anythingmcp'
        setup.local.protect(folder)
        session = folder/'administrator-session.dpapi'
        setup.write_private_bytes(session, b'test_only.previous.signature')
        original = session.read_bytes()
        for rejection in ('redirect', 'invalid_token', 'unsafe_password_echo'):
            with self.subTest(rejection=rejection), patch('builtins.input', return_value='unit@example.test'), \
                    patch.object(setup.getpass, 'getpass', return_value='test-only-password') as password_prompt, \
                    patch.object(setup.urllib.request, 'build_opener') as build:
                opener = build.return_value
                if rejection == 'unsafe_password_echo':
                    password_prompt.side_effect = setup.getpass.GetPassWarning('test-only missing echo protection')
                elif rejection == 'redirect':
                    opener.open.side_effect = urllib.error.HTTPError('http://127.0.0.1:4000/api/auth/login',
                        302, 'fixture redirect', {}, io.BytesIO(b'private error body'))
                else:
                    opener.open.return_value.__enter__.return_value.read.return_value = b'{"accessToken":"invalid"}'
                with self.assertRaises(setup.SetupError):
                    setup.login(self.directory)
                if rejection == 'unsafe_password_echo':
                    opener.open.assert_not_called()
                else:
                    opener.open.assert_called_once()
                self.assertEqual(session.read_bytes(), original)

    def test_runtime_secrets_cannot_be_written_inside_git_checkout(self):
        (self.directory/'.git').mkdir(parents=True)
        with self.assertRaisesRegex(setup.SetupError, 'fuera'):
            self.provision()
        self.assertFalse(self.api.calls)

    def test_gateway_config_rejects_public_loopback_urls_and_extra_fields(self):
        config = dict(version=1, **NETWORK, listen_port=45678,
            native_token='test_only_native_token_'*3,
            gateway_url='http://127.0.0.1:4000/mcp/native-server', gateway_token='mcp_'+('test_only_'*8))
        self.assertEqual(setup.checked_gateway_config(config), config)
        for changes in ({'listen_host': '127.0.0.1'}, {'listen_host': '8.8.8.8'},
                {'gateway_url': 'http://user:secret@127.0.0.1:4000/mcp/native-server'},
                {'gateway_url': 'http://127.0.0.1:4000/mcp/native-server?token=secret'},
                {'extra': True}, {'listen_port': True}, {'version': True}):
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                setup.checked_gateway_config(config | changes)

    def test_peer_outside_observed_wsl_subnet_is_rejected(self):
        address = type('Address', (), {'family': setup.socket.AF_INET,
            'address': NETWORK['listen_host'], 'netmask': '255.255.255.0'})()
        with patch('psutil.net_if_addrs', return_value={'vEthernet (WSL)': [address]}):
            native_gateway.verify_wsl_network(NETWORK)
            with self.assertRaises(ValueError):
                native_gateway.verify_wsl_network(NETWORK | {'allowed_peer': '172.16.6.10'})
        with patch('psutil.net_if_addrs', return_value={'Wi-Fi': [address]}), self.assertRaises(ValueError):
            native_gateway.verify_wsl_network(NETWORK)

    def test_wsl_detection_uses_ipv4_default_and_eth0_without_shell(self):
        responses = [json.dumps([{'dev': 'eth0', 'gateway': NETWORK['listen_host']}]),
            json.dumps([{'addr_info': [{'family': 'inet', 'local': NETWORK['allowed_peer']}]}])]
        with patch.object(setup.shutil, 'which', return_value='wsl.exe'), patch.object(setup.subprocess, 'run') as run:
            run.side_effect = [type('Result', (), {'stdout': row})() for row in responses]
            self.assertEqual(setup.detect_network('Ubuntu-24.04'), NETWORK)
            self.assertEqual(run.call_args_list[0].args[0],
                ['wsl.exe', '-d', 'Ubuntu-24.04', '--exec', 'ip', '-json', '-4', 'route', 'show', 'default'])
            self.assertTrue(all(not call.kwargs.get('shell') for call in run.call_args_list))
            with self.assertRaises(setup.SetupError):
                setup.detect_network('Ubuntu;other')


if __name__ == '__main__':
    unittest.main()
