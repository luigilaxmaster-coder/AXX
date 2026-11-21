"""Unit tests for ChatGPT OAuth PKCE, callback rendering, and adapter."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from backend.auth.chatgpt_auth import ChatGPTAuthManager
from backend.auth.callback_page import get_callback_html
from backend.inference.chatgpt_adapter import ChatGPTSubscriptionAdapter

class TestChatGPTAuth(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.auth = ChatGPTAuthManager(data_dir=Path(self.tmp_dir.name))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_initial_state_unauthenticated(self):
        status = self.auth.get_status()
        self.assertFalse(status['authenticated'])
        self.assertEqual(status['models'], [])
        self.assertIsNone(status['email'])

    def test_retired_auth_never_reads_or_transmits_saved_credentials(self):
        legacy = Path(self.tmp_dir.name) / 'auth' / 'chatgpt.json'
        legacy.parent.mkdir()
        legacy.write_bytes(b'private-test-fixture')
        with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
            auth = ChatGPTAuthManager(data_dir=Path(self.tmp_dir.name))
            with self.assertRaisesRegex(ValueError, 'Codex App Server'):
                auth.start_oauth(port=4173, open_browser=False)
            with self.assertRaisesRegex(ValueError, 'Codex App Server'):
                auth.set_client_id('unregistered-client')
            self.assertIsNone(auth.get_access_token())
            self.assertFalse(auth.refresh_access_token())
            self.assertFalse(auth.handle_callback('code', 'state')[0])
            auth.clear_auth()
        self.assertEqual(legacy.read_bytes(), b'private-test-fixture')

    def test_callback_page_html_rendering(self):
        success_html = get_callback_html(True, "Autorización completada", "Luigi").decode('utf-8')
        self.assertIn('¡Conexión completada!', success_html)
        self.assertIn('Luigi', success_html)
        self.assertIn('Axx Desktop Assistant', success_html)

        error_html = get_callback_html(False, "Error de prueba").decode('utf-8')
        self.assertIn('No se pudo completar la conexión', error_html)
        self.assertIn('Error de prueba', error_html)

    def test_retired_adapter_blocks_every_fallback_path(self):
        adapter = ChatGPTSubscriptionAdapter(self.auth)
        self.assertFalse(adapter.is_available())
        with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
            for allow_fallback in (False, True):
                with self.assertRaisesRegex(ValueError, 'Codex App Server'):
                    adapter.chat('gpt-4o', [{'role': 'user', 'content': 'test'}], allow_fallback=allow_fallback)
            with self.assertRaises(ValueError):
                adapter.query_local_ollama([])

if __name__ == '__main__':
    unittest.main()
