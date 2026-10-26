import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('anythingmcp_local', Path(__file__).resolve().parents[2]/'scripts'/'anythingmcp-local.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


class LocalGatewayTests(unittest.TestCase):
    def test_preparation_preserves_keys_and_loopback_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'private'
            local.prepare(root)
            original = (root/'.env').read_bytes()
            local.prepare(root)
            self.assertEqual(original, (root/'.env').read_bytes())
            data = local.compose()
            self.assertTrue(all('@sha256:' in item['image'] for item in data['services'].values()))
            self.assertTrue(all(item.startswith('127.0.0.1:') for item in data['services']['app']['ports']))
            self.assertNotIn('ports', data['services']['postgres'])
            self.assertEqual(data['services']['app']['environment']['MCP_ALLOW_ANONYMOUS'], 'false')
            self.assertNotIn(original.splitlines()[0].split(b'=')[1].decode(), str(data))
            with patch.object(local.shutil, 'which', return_value=None):
                self.assertFalse(local.preflight(root)['ready_to_start'])

    def test_existing_invalid_secret_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'.env').write_text('ENCRYPTION_KEY=existing-data')
            with self.assertRaises(ValueError): local.prepare(root)
            self.assertEqual((root/'.env').read_text(), 'ENCRYPTION_KEY=existing-data')
