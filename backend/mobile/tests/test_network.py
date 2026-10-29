from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.mobile.gateway import MobileGateway
from backend.mobile.network import MobileNetwork


def online(address='100.101.102.103'):
    return {'BackendState': 'Running', 'Self': {'Online': True}, 'TailscaleIPs': [address, 'fd7a:115c:a1e0::1']}


class NetworkTests(unittest.TestCase):
    def test_explicit_tailscale_requires_online_own_cgnat_address_and_caches_probe(self):
        calls = []
        def probe():
            calls.append(1)
            return online()
        network = MobileNetwork(lambda: '192.168.1.10', probe)
        self.assertEqual(network.resolve('lan'), '192.168.1.10')
        self.assertEqual(calls, [])
        self.assertEqual(network.status('tailscale')['address'], '100.101.102.103')
        self.assertTrue(network.status('tailscale')['ready'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(network.resolve('tailscale'), '100.101.102.103')
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ValueError):
            network.resolve('public')

    def test_offline_missing_and_wrong_interface_never_fall_back_to_lan(self):
        for value in ({'BackendState': 'NoState'}, {'BackendState': 'NeedsLogin'},
                      {'BackendState': 'Running', 'Self': {'Online': False}}, online('8.8.8.8'), online('192.168.1.1')):
            with self.subTest(value=value):
                network = MobileNetwork(lambda: self.fail('LAN fallback is forbidden'), lambda: value)
                status = network.status('tailscale')
                self.assertFalse(status['ready'])
                self.assertTrue(status['message'])
                with self.assertRaises(RuntimeError):
                    network.resolve('tailscale')

    def test_offline_switch_retains_identity_grants_mode_and_always_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway = MobileGateway(root / 'state.db', root, lambda *args: {}, host_resolver=lambda: '127.0.0.1',
                                    tailscale_probe=lambda: {'BackendState': 'NoState'})
            try:
                initial = gateway.start()
                device = gateway.store.consume_pairing(initial['pairing_code'], 'Phone')
                gateway.store.set_file_permissions(device['device_id'], True, True)
                gateway.set_always_access(True)
                with self.assertRaisesRegex(RuntimeError, 'Tailscale'):
                    gateway.set_network_mode('tailscale')
                status = gateway.status()
                self.assertFalse(status['enabled'])
                self.assertFalse(status['remote_ready'])
                self.assertTrue(status['always_on'])
                self.assertEqual(status['network_mode'], 'tailscale')
                self.assertTrue(gateway.store.authorize(device['credential'], 'files.read'))
                restored = gateway.set_network_mode('lan')
                self.assertEqual(restored['fingerprint'], initial['fingerprint'])
                self.assertTrue(restored['always_on'])
                self.assertTrue(restored['endpoint'].startswith('https://127.0.0.1:'))
            finally:
                gateway.close()

    def test_remote_binds_only_discovered_interface_and_preserves_qr_identity(self):
        class BoundServer:
            def __init__(self, address, handler):
                self.server_address = address
                self.server_port = address[1]
            def serve_forever(self): pass
            def shutdown(self): pass
            def server_close(self): pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway = MobileGateway(root / 'state.db', root, lambda *args: {}, host_resolver=lambda: '127.0.0.1',
                                    tailscale_probe=online)
            try:
                initial = gateway.start()
                device = gateway.store.consume_pairing(initial['pairing_code'], 'Phone')
                gateway.store.set_tool_permission(device['device_id'], True)
                gateway.set_always_access(True)
                with patch('backend.mobile.gateway.BoundedHTTPServer', BoundServer):
                    remote = gateway.set_network_mode('tailscale')
                self.assertEqual(gateway.httpd.server_address[0], '100.101.102.103')
                self.assertTrue(remote['endpoint'].startswith('https://100.101.102.103:'))
                self.assertTrue(remote['remote_ready'])
                self.assertEqual(remote['fingerprint'], initial['fingerprint'])
                self.assertTrue(remote['always_on'])
                self.assertTrue(gateway.store.authorize(device['credential'], 'tools.control'))
                renewed = gateway.store.consume_pairing(remote['pairing_code'], 'Phone', credential=device['credential'])
                self.assertEqual(renewed['device_id'], device['device_id'])
                self.assertEqual(renewed['credential'], device['credential'])
                self.assertEqual(gateway.store.access_settings()['network_mode'], 'tailscale')
            finally:
                gateway.close()


if __name__ == '__main__':
    unittest.main()
