"""Unit tests for ChatGPT OAuth PKCE, callback rendering, and adapter."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
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

    def test_start_oauth_generates_pkce_and_state(self):
        res = self.auth.start_oauth(port=4173, open_browser=False)
        self.assertIn('auth_url', res)
        self.assertIn('state', res)
        self.assertIn('https://auth.openai.com/api/accounts/authorize', res['auth_url'])
        self.assertIn('dynamic_agent_client', res['auth_url'])
        self.assertIn('code_challenge_method=S256', res['auth_url'])
        self.assertIn('chatgpt.tokens.use.direct', res['auth_url'])
        self.assertIn(res['state'], self.auth.pending_states)

    def test_custom_client_id(self):
        self.assertEqual(self.auth.get_client_id(), 'dynamic_agent_client')
        self.auth.set_client_id('oaiapp_test_custom_id_123')
        self.assertEqual(self.auth.get_client_id(), 'oaiapp_test_custom_id_123')
        status = self.auth.get_status()
        self.assertEqual(status['client_id'], 'oaiapp_test_custom_id_123')
        res = self.auth.start_oauth(port=4173, open_browser=False)
        self.assertIn('client_id=oaiapp_test_custom_id_123', res['auth_url'])
        self.auth.set_client_id('')
        self.assertEqual(self.auth.get_client_id(), 'dynamic_agent_client')

    def test_callback_page_html_rendering(self):
        success_html = get_callback_html(True, "Autorización completada", "Luigi").decode('utf-8')
        self.assertIn('¡Conexión completada!', success_html)
        self.assertIn('Luigi', success_html)
        self.assertIn('Axx Desktop Assistant', success_html)

        error_html = get_callback_html(False, "Error de prueba").decode('utf-8')
        self.assertIn('No se pudo completar la conexión', error_html)
        self.assertIn('Error de prueba', error_html)

    def test_adapter_cooldown_and_fallback(self):
        adapter = ChatGPTSubscriptionAdapter(self.auth)
        self.assertFalse(adapter.is_available())
        # Set artificial cooldown
        adapter.cooldown_until = time.time() + 60
        cooldown = adapter.get_cooldown()
        self.assertIsNotNone(cooldown)
        self.assertTrue(cooldown['active'])
        self.assertGreater(cooldown['remaining_seconds'], 0)

if __name__ == '__main__':
    unittest.main()
