"""Read-only Telegram command catalog; no network, desktop input, or inference."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.telegram.service import TelegramService


PHRASES = {
    'abre calculadora': 'axx.desktop.open_app',
    'abre bloc de notas': 'axx.desktop.open_app',
    'abre explorador': 'axx.desktop.open_app',
    'abre paint': 'axx.desktop.open_app',
    'mis ventanas': 'axx.desktop.list_windows',
    'aplicaciones instaladas': 'axx.desktop.list_apps',
    'información del sistema': 'axx.system.telemetry',
    'cierra Spotify': 'axx.desktop.window.close',
}


class TelegramCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.chats = ChatStore(self.root / 'state.db')
        self.addCleanup(self.chats.close)
        self.account = {'account_id': 10, 'owner_id': 20, 'session': 'fixture-session', 'enabled': True,
                        'grants': {'conversation': False, 'pc_commands': True}}
        self.policy = {'enabled': True}
        self.commands = Mock()
        self.adapter = Mock()
        ids = set(PHRASES.values())
        self.rows = [{'id': value, 'title': 'Fixture', 'description': 'Fixture',
                      'risk': 'local_state' if value == 'axx.desktop.window.close' else 'read',
                      'requires_approval': False, 'source_kind': 'local_adapter', 'execution_enabled': True,
                      'pc_approval_required': False, 'parameters': {}} for value in ids]
        self.commands.executable_catalog.side_effect = lambda: {'commands': copy.deepcopy(self.rows)}
        for name, callback in [('load_account', lambda _: copy.deepcopy(self.account)),
                               ('confirmation_policy', lambda _: dict(self.policy))]:
            patcher = patch('backend.telegram.service.' + name, side_effect=callback, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = TelegramService(self.root, self.chats, self.commands, self.adapter, lambda: {})

    def test_catalog_returns_only_curated_executable_phrases_without_effects(self):
        result = self.service.command_catalog(20)
        self.assertEqual({item['example']: item['command_id'] for item in result['items']}, PHRASES)
        self.assertEqual(len(result['items']), 8)
        self.assertTrue(all(set(item) == {'id','command_id','title','example','description','category','available','reason'} for item in result['items']))
        self.assertIsInstance(result['text'], str)
        self.commands.prepare.assert_not_called()
        self.commands.execute.assert_not_called()
        self.adapter.route.assert_not_called()

    def test_listing_commands_works_when_conversation_disabled_without_model_or_effect(self):
        for phrase in ('/comandos', 'ver comandos'):
            result = self.service.admit_miniapp(20, phrase, str(uuid.uuid4()))
            self.assertEqual(result['state'], 'succeeded')
            self.assertIn('calculadora', result['text'].lower())
        self.commands.resolve.assert_not_called()
        self.commands.prepare.assert_not_called()
        self.commands.execute.assert_not_called()
        self.adapter.route.assert_not_called()

    def test_wrong_owner_or_disabled_account_cannot_read_catalog(self):
        with self.assertRaises(ValueError):
            self.service.command_catalog(21)
        self.account['enabled'] = False
        with self.assertRaises(ValueError):
            self.service.command_catalog(20)

    def test_permissions_disabled_leave_registered_items_visible_but_unavailable(self):
        for field in ('pc_commands', 'remote_confirmations'):
            with self.subTest(field=field):
                self.account['grants']['pc_commands'] = field != 'pc_commands'
                self.policy['enabled'] = field != 'remote_confirmations'
                items = self.service.command_catalog(20)['items']
                self.assertTrue(items)
                self.assertTrue(all(item['available'] is False and item['reason'] for item in items))

    def test_unregistered_and_nonstatic_entries_are_never_suggested(self):
        self.rows = [row for row in self.rows if row['id'] != 'axx.desktop.list_apps']
        for row in self.rows:
            if row['id'] == 'axx.desktop.list_windows':
                row['source_kind'] = 'generated'
            if row['id'] == 'axx.system.telemetry':
                row['execution_enabled'] = False
        items = self.service.command_catalog(20)['items']
        self.assertNotIn('axx.desktop.list_apps', [item['command_id'] for item in items])
        self.assertNotIn('axx.desktop.list_windows', [item['command_id'] for item in items])
        self.assertNotIn('axx.system.telemetry', [item['command_id'] for item in items])

    def test_pc_approval_required_and_missing_capability_are_not_claimed_available(self):
        for row in self.rows:
            if row['id'] == 'axx.desktop.list_apps':
                row['requires_approval'] = True
                row['pc_approval_required'] = True
        items = self.service.command_catalog(20)['items']
        row = next(item for item in items if item['command_id'] == 'axx.desktop.list_apps')
        self.assertFalse(row['available'])
        self.assertTrue(row['reason'])

    def test_malformed_or_unavailable_core_catalog_is_honest(self):
        for response in ({}, {'commands': 'invalid'}, RuntimeError('private details')):
            with self.subTest(response=type(response).__name__):
                self.commands.executable_catalog.side_effect = response if isinstance(response, Exception) else None
                self.commands.executable_catalog.return_value = response
                result = self.service.command_catalog(20)
                self.assertEqual(result['items'], [])
                self.assertIn('No se pudo consultar', result['text'])
                self.assertNotIn('private details', result['text'])


class TelegramCatalogParserTests(unittest.TestCase):
    def test_eight_examples_resolve_to_expected_registered_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = ActionExecutor(root / 'state.db', root / 'artifacts')
            commands = CommandService(executor)
            try:
                window = {'window_id': 18, 'pid': 45, 'title': 'Spotify'}
                with patch('backend.actions.windows_apps.find_app', return_value=[]), \
                     patch('backend.actions.windows_automation.list_windows', return_value=[window]), \
                     patch('backend.actions.windows_automation.process_name', return_value='spotify.exe'), \
                     patch('backend.actions.windows_automation.process_started', return_value='birth'), \
                     patch('backend.actions.windows_automation.read_window_title', return_value='Spotify'):
                    for phrase, expected in PHRASES.items():
                        with self.subTest(phrase=phrase):
                            result = commands.resolve(phrase, source='text')
                            self.assertEqual((result['match'], result.get('command_id')), ('exact', expected))
            finally:
                commands.close()
                executor.close()


if __name__ == '__main__':
    unittest.main()
