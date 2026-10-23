import base64
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from xml.etree import ElementTree

from backend.mobile.gateway import MobileGateway
from backend.mobile.http_api import MobileHTTP
from backend.mobile.pairing_qr import pairing_qr_base64, verify_qr_runtime


class PairingQrTests(unittest.TestCase):
    def test_real_management_route_returns_rendered_qr_and_one_time_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway = MobileGateway(Path(tmp)/'state.db', tmp, lambda *args: {}, host_resolver=lambda: '127.0.0.1')
            self.addCleanup(gateway.close)
            replies = []
            handler = SimpleNamespace(server=SimpleNamespace(mobile=gateway, host_owned=True),
                                      _send_json=lambda status, body: replies.append((status, body)))
            self.assertTrue(MobileHTTP(handler).post('/axx-api/mobile/start', {}))
            status, info = replies[-1]
            self.assertEqual(status, 200)
            self.assertTrue(info['pairing_uri'].startswith('axx://pair?'))
            svg = ElementTree.fromstring(base64.b64decode(info['qr_svg_base64'], validate=True))
            self.assertEqual(svg.tag, '{http://www.w3.org/2000/svg}svg')
            self.assertTrue(svg.findall('{http://www.w3.org/2000/svg}path'))
            self.assertEqual(info['expires_in'], 120)
            device = gateway.store.consume_pairing(info['pairing_code'], 'QR test phone')
            self.assertTrue(device['device_id'])
            with self.assertRaises(ValueError): gateway.store.consume_pairing(info['pairing_code'], 'Replay')
            gateway.close()

    def test_build_check_generates_real_svg_without_gateway(self):
        self.assertEqual(verify_qr_runtime()['result'], 'PASS')
        for value in (None, '', 'x'*2049):
            with self.assertRaises(ValueError): pairing_qr_base64(value)


if __name__ == '__main__': unittest.main()
