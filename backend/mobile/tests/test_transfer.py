import base64
import hashlib
import json
import os
import ssl
import stat
from pathlib import Path
import tempfile
import time
import unittest
import uuid
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch

from backend.mobile.transfer import FileTransfer, CHUNK_SIZE
from backend.mobile.trust_store import MobileTrustStore


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.shared = self.root / 'shared'
        self.shared.mkdir()
        self.store = MobileTrustStore(self.root / 'state.db')
        self.device = self.store.consume_pairing(self.store.create_pairing(), 'Phone')['device_id']
        self.files = FileTransfer(self.store, self.root / 'private')

    def tearDown(self):
        self.files.close()
        deadline = time.monotonic() + 3
        while self.files.workers and time.monotonic() < deadline:
            time.sleep(.01)
        self.temp.cleanup()

    def grant(self, read=True, write=True):
        return self.files.configure({'device_id': self.device, 'read': read, 'write': write, 'roots': [str(self.shared)]})

    def wait(self, transfer_id, expected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.files.get(transfer_id, self.device)
            if result['state'] in expected:
                return result
            time.sleep(.01)
        self.fail('Transfer did not reach ' + repr(expected) + ': ' + repr(result))

    def upload(self, content, name='archivo.txt', finish=True):
        transfer_id = str(uuid.uuid4())
        body = {'transfer_id': transfer_id, 'direction': 'to_pc', 'name': name,
                'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        self.files.create(self.device, body)
        for index, offset in enumerate(range(0, len(content), CHUNK_SIZE)):
            self.files.chunk(self.device, {'transfer_id': transfer_id, 'index': index,
                                         'data': base64.b64encode(content[offset:offset + CHUNK_SIZE]).decode()})
        if finish:
            self.files.action('finish', self.device, {'transfer_id': transfer_id})
            self.wait(transfer_id, {'completed', 'failed'})
        return transfer_id, body

    def test_explicit_independent_permissions_and_revocation(self):
        with self.assertRaises(ValueError):
            self.files.search(self.device, {'query': ''})
        self.grant(read=False)
        with self.assertRaises(ValueError):
            self.files.search(self.device, {'query': ''})
        transfer_id, _ = self.upload(b'abc', finish=False)
        self.grant(write=False)
        with self.assertRaises(ValueError):
            self.files.action('finish', self.device, {'transfer_id': transfer_id})
        self.grant()
        self.store.revoke(self.device)
        with self.assertRaises(ValueError):
            self.files.chunk(self.device, {'transfer_id': transfer_id, 'index': 0, 'data': 'YWJj'})

    def test_upload_verified_encrypted_persistent_and_nonoverwriting_export(self):
        self.grant()
        content = b'unique private content' * 20000
        transfer_id, body = self.upload(content)
        result = self.files.get(transfer_id, self.device)
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['confirmed_bytes'], len(content))
        self.assertEqual(self.files.create(self.device, body)['transfer_id'], transfer_id)
        for path in (self.root / 'private').rglob('*'):
            if path.is_file():
                self.assertNotIn(b'unique private content', path.read_bytes())
        self.assertNotIn(b'archivo.txt', (self.root / 'state.db').read_bytes())
        restarted = FileTransfer(self.store, self.root / 'private')
        self.assertEqual(restarted.get(transfer_id, self.device)['state'], 'completed')
        output = self.root / 'export.txt'
        restarted.export({'transfer_id': transfer_id, 'destination': str(output)})
        self.assertEqual(output.read_bytes(), content)
        with self.assertRaises(ValueError):
            restarted.export({'transfer_id': transfer_id, 'destination': str(output)})
        self.assertEqual(output.read_bytes(), content)
        restarted.close()

    def test_search_download_snapshot_and_receipt(self):
        self.grant()
        source = self.shared / 'Presupuesto.pdf'
        content = b'%PDF datos privados' * 25000
        source.write_bytes(content)
        result = self.files.search(self.device, {'query': 'traeme el presupuesto pdf'})
        self.assertEqual(len(result['files']), 1)
        file = result['files'][0]
        self.assertNotIn('source', file)
        self.assertEqual(file['root_name'], 'shared')
        transfer_id = str(uuid.uuid4())
        self.files.create(self.device, {'transfer_id': transfer_id, 'direction': 'to_phone', 'file_ref': file['file_ref']})
        record = self.wait(transfer_id, {'ready', 'failed'})
        self.assertEqual(record['state'], 'ready')
        self.assertEqual(record['confirmed_bytes'], 0)
        received = b''.join(base64.b64decode(self.files.chunk(self.device, {'transfer_id': transfer_id, 'index': i})['data'])
                            for i in range(record['chunk_count']))
        self.assertEqual(received, content)
        self.assertEqual(source.read_bytes(), content)
        with self.assertRaises(ValueError):
            self.files.action('receipt', self.device, {'transfer_id': transfer_id, 'size': len(content), 'sha256': '0' * 64})
        receipt = self.files.action('receipt', self.device, {'transfer_id': transfer_id, 'size': len(content), 'sha256': record['sha256']})
        self.assertEqual(receipt['state'], 'completed')

    def test_save_received_to_downloads_preserves_existing_file(self):
        self.grant()
        downloads = self.root / 'Downloads'
        downloads.mkdir()
        original = downloads / 'archivo.txt'
        original.write_bytes(b'keep existing')
        transfer_id, _ = self.upload(b'from phone')
        with patch('backend.mobile.transfer._downloads_directory', return_value=downloads):
            result = self.files.save_downloads({'transfer_id': transfer_id})
        self.assertEqual(Path(result['path']).name, 'archivo (2).txt')
        self.assertEqual(Path(result['path']).read_bytes(), b'from phone')
        self.assertEqual(original.read_bytes(), b'keep existing')
        self.assertTrue(self.files.get(transfer_id)['stored'])

    def test_save_downloads_rejects_unverified_or_removed_copies(self):
        self.grant()
        transfer_id, _ = self.upload(b'pending', finish=False)
        with self.assertRaises(ValueError):
            self.files.save_downloads({'transfer_id': transfer_id})
        finished, _ = self.upload(b'finished')
        self.files.remove({'transfer_id': finished})
        with self.assertRaises(ValueError):
            self.files.save_downloads({'transfer_id': finished})
        with self.assertRaises(ValueError):
            self.files.save_downloads({'transfer_id': finished, 'destination': str(self.root)})

    def test_changed_source_foreign_ref_and_traversal_are_denied(self):
        self.grant()
        source = self.shared / 'file.txt'
        source.write_bytes(b'one')
        file_ref = self.files.search(self.device, {'query': 'file'})['files'][0]['file_ref']
        source.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.files.create(self.device, {'transfer_id': str(uuid.uuid4()), 'direction': 'to_phone', 'file_ref': file_ref})
        other = self.store.consume_pairing(self.store.create_pairing(), 'Other')['device_id']
        self.files.configure({'device_id': other, 'read': True, 'write': True, 'roots': [str(self.shared)]})
        with self.assertRaises(ValueError):
            self.files.create(other, {'transfer_id': str(uuid.uuid4()), 'direction': 'to_phone', 'file_ref': file_ref})
        for name in ('../escape.txt', 'C:\\secret', 'CON', 'name:stream', '.', 'trailing.'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.upload(b'x', name)
        with self.assertRaises(ValueError):
            self.files.configure({'device_id': self.device, 'read': True, 'write': True, 'roots': [str(self.shared / '..')]})

    def test_pause_restart_resume_duplicate_and_conflicting_chunks(self):
        self.grant()
        transfer_id, body = self.upload(b'private', finish=False)
        self.files.action('pause', self.device, {'transfer_id': transfer_id})
        restarted = FileTransfer(self.store, self.root / 'private')
        self.assertEqual(restarted.get(transfer_id, self.device)['state'], 'paused')
        restarted.action('resume', self.device, {'transfer_id': transfer_id})
        chunk = {'transfer_id': transfer_id, 'index': 0, 'data': base64.b64encode(b'private').decode()}
        self.assertEqual(restarted.chunk(self.device, chunk)['next_index'], 1)
        with self.assertRaises(ValueError):
            restarted.chunk(self.device, {**chunk, 'data': base64.b64encode(b'changed').decode()})
        with self.assertRaises(ValueError):
            restarted.create(self.device, {**body, 'name': 'different.txt'})
        restarted.close()

    def test_integrity_tamper_and_incomplete_transfer_never_complete(self):
        self.grant()
        transfer_id, _ = self.upload(b'private', finish=False)
        path = self.files.directory / transfer_id / '0'
        data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
        self.files.action('finish', self.device, {'transfer_id': transfer_id})
        self.assertEqual(self.wait(transfer_id, {'failed', 'completed'})['state'], 'failed')
        second = str(uuid.uuid4())
        self.files.create(self.device, {'transfer_id': second, 'direction': 'to_pc', 'name': 'two.txt', 'size': 10, 'sha256': '0' * 64})
        with self.assertRaises(ValueError):
            self.files.action('finish', self.device, {'transfer_id': second})
        cancelled = self.files.action('cancel', self.device, {'transfer_id': second})
        self.assertEqual(cancelled['state'], 'cancelled')
        with self.assertRaises(ValueError):
            self.files.chunk(self.device, {'transfer_id': second, 'index': 0, 'data': base64.b64encode(b'0' * 10).decode()})

    def test_zero_byte_files_and_foreign_session_are_supported(self):
        self.grant()
        transfer_id, _ = self.upload(b'')
        self.assertEqual(self.files.get(transfer_id, self.device)['state'], 'completed')
        with self.assertRaises(ValueError):
            self.files.get(transfer_id, str(uuid.uuid4()))

    def test_search_does_not_follow_symlinks(self):
        self.grant()
        secret = self.root / 'secret.txt'; secret.write_bytes(b'not shared')
        try:
            (self.shared / 'link.txt').symlink_to(secret)
        except OSError:
            self.skipTest('Symlink creation not available for this user')
        self.assertEqual(self.files.search(self.device, {'query': ''})['files'], [])

    def test_reparse_roots_are_rejected_and_removed_copies_keep_receipts(self):
        with patch('backend.actions.tools.Path.lstat', return_value=SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)):
            with self.assertRaises(ValueError):
                self.grant()
        self.grant()
        transfer_id, _ = self.upload(b'original')
        exported = self.root / 'original.txt'
        self.files.export({'transfer_id': transfer_id, 'destination': str(exported)})
        result = self.files.remove({'transfer_id': transfer_id})
        self.assertEqual(result['state'], 'completed')
        self.assertFalse(result['stored'])
        self.assertEqual(exported.read_bytes(), b'original')
        self.assertEqual(list((self.files.directory / transfer_id).iterdir()), [])
        with self.assertRaises(ValueError):
            self.files.export({'transfer_id': transfer_id, 'destination': str(self.root / 'again.txt')})


class TransferGatewayTests(unittest.TestCase):
    def test_tls_routes_gate_file_permissions_and_bind_transfer_to_device(self):
        from backend.mobile.gateway import MobileGateway
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shared = root / 'share'; shared.mkdir()
            gateway = MobileGateway(root / 'state.db', root, lambda *args: {}, host_resolver=lambda: '127.0.0.1')
            try:
                info = gateway.start()
                device = gateway.store.consume_pairing(info['pairing_code'], 'Phone')
                context = ssl.create_default_context(cafile=str(gateway._identity[0]))
                def request(path, body=None, credential=None):
                    req = urllib.request.Request(info['endpoint'] + path,
                        data=json.dumps(body).encode() if body is not None else None,
                        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (credential or device['credential'])})
                    with urllib.request.urlopen(req, context=context, timeout=5) as response:
                        return json.load(response)['data']
                self.assertFalse(request('/v1/files/status')['permissions']['read'])
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    request('/v1/files/search', {'query': ''})
                self.assertEqual(denied.exception.code, 403); denied.exception.close()
                gateway.transfers.configure({'device_id': device['device_id'], 'read': True, 'write': True, 'roots': [str(shared)]})
                transfer_id = str(uuid.uuid4())
                request('/v1/transfers/create', {'transfer_id': transfer_id, 'direction': 'to_pc', 'name': 'empty.txt',
                        'size': 0, 'sha256': hashlib.sha256(b'').hexdigest()})
                request('/v1/transfers/finish', {'transfer_id': transfer_id})
                deadline = time.monotonic() + 3
                while request('/v1/transfers?transfer_id=' + transfer_id)['state'] == 'verifying' and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(request('/v1/transfers?transfer_id=' + transfer_id)['state'], 'completed')
                other = gateway.store.consume_pairing(gateway.store.create_pairing(), 'Other')
                with self.assertRaises(urllib.error.HTTPError) as foreign:
                    request('/v1/transfers?transfer_id=' + transfer_id, credential=other['credential'])
                self.assertGreaterEqual(foreign.exception.code, 400); foreign.exception.close()
            finally:
                gateway.close()


if __name__ == '__main__':
    unittest.main()
