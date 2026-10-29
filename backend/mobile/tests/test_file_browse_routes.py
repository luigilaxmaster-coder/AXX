"""File browsing uses the same device permission boundary as private search."""
import json
from pathlib import Path
import ssl
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import urllib.error
import urllib.request

from backend.mobile.gateway import MobileGateway
from backend.mobile.http_api import MobileHTTP


class FileBrowseRoutesTests(unittest.TestCase):
    def test_mobile_browse_requires_read_permission_over_real_tls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / 'shared'
            shared.mkdir()
            gateway = MobileGateway(root / 'state.db', root, lambda *args: {},
                                    host_resolver=lambda: '127.0.0.1')
            try:
                info = gateway.start()
                device = gateway.store.consume_pairing(info['pairing_code'], 'Phone')
                context = ssl.create_default_context(cafile=str(gateway._identity[0]))

                def request(body):
                    req = urllib.request.Request(info['endpoint'] + '/v1/files/browse',
                        data=json.dumps(body).encode(),
                        headers={'Content-Type': 'application/json',
                                 'Authorization': 'Bearer ' + device['credential']})
                    return urllib.request.urlopen(req, context=context, timeout=5)

                with self.assertRaises(urllib.error.HTTPError) as denied:
                    request({})
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()
                gateway.transfers.configure({'device_id': device['device_id'],
                    'read': True, 'write': False, 'roots': [str(shared)]})
                with request({}) as response:
                    result = json.load(response)['data']
                self.assertEqual(result['folders'][0]['name'], 'shared')
                self.assertNotIn(str(root), json.dumps(result))
                with self.assertRaises(urllib.error.HTTPError) as invalid:
                    request({'folder_ref': '../private'})
                self.assertEqual(invalid.exception.code, 400)
                invalid.exception.close()
            finally:
                gateway.close()

    def test_desktop_browse_routes_device_without_widening_payload(self):
        browse = Mock(return_value={'folders': [], 'files': []})
        handler = SimpleNamespace(server=SimpleNamespace(mobile=SimpleNamespace(
            transfers=SimpleNamespace(browse=browse))), _send_json=Mock())
        api = MobileHTTP(handler)
        self.assertTrue(api.post('/axx-api/mobile/files/browse',
                                 {'device_id': 'phone', 'folder_ref': 'opaque'}))
        browse.assert_called_once_with('phone', {'folder_ref': 'opaque'})
        handler._send_json.assert_called_once_with(200, {'folders': [], 'files': []})
        with self.assertRaisesRegex(ValueError, 'device_id required'):
            api.post('/axx-api/mobile/files/browse', {})


if __name__ == '__main__':
    unittest.main()
