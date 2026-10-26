import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import application_catalog as catalog


class ApplicationCatalogTests(unittest.TestCase):
    def test_profile_scope_and_sensitive_guides(self):
        rows = catalog.profiles()
        self.assertGreaterEqual(len(rows), 35)
        self.assertLessEqual(len(rows), 50)
        self.assertGreaterEqual(sum(len(row['commands']) for row in rows), 140)
        self.assertEqual(catalog.profile_for('CHROME')['id'], 'chrome')
        self.assertEqual(catalog.profile_for('  EXPLORADOR   DE ARCHIVOS  ')['id'], 'explorer')
        self.assertEqual(catalog.profile_for('calculadora')['id'], 'calculator')
        self.assertIsNone(catalog.profile_for('chrom'))
        for app, command in [('telegram', 'send_message'), ('teamviewer', 'remote_session'), ('teamviewer', 'file_transfer')]:
            row = next(item for item in catalog.profile_for(app)['commands'] if item['id'] == command)
            self.assertEqual(row['kind'], 'guide')
            self.assertTrue(row['requires_connection'])
        for row in rows:
            for command in row['commands']:
                if command['kind'] == 'shortcut':
                    self.assertEqual(command['keys'], ['Control', 'T'])
                    self.assertIn(row['id'], ('chrome', 'edge', 'firefox'))
                    self.assertTrue(any('https://' in instruction for instruction in row['instructions']))

    def test_profiles_are_fresh_public_copies(self):
        rows = catalog.profiles()
        rows[0]['aliases'].append('changed')
        rows[0]['commands'][0]['title'] = 'changed'
        again = catalog.profiles()
        self.assertNotIn('changed', again[0]['aliases'])
        self.assertNotEqual(again[0]['commands'][0]['title'], 'changed')

    def test_catalog_joins_only_exact_observed_inventory_without_launching(self):
        apps = [{'name': 'Google Chrome', 'app_id': 'test-only-Chrome', 'inventory_marker': 'observed'},
                {'name': 'Other local tool', 'app_id': 'TestVendor.Tool_abc!App'}]
        with patch.object(catalog, 'installed_apps', return_value=apps) as inventory:
            result = catalog.installed_catalog()
        inventory.assert_called_once_with()
        self.assertEqual(result['applications'], apps)
        chrome = next(row for row in result['profiles'] if row['id'] == 'chrome')
        telegram = next(row for row in result['profiles'] if row['id'] == 'telegram')
        self.assertEqual(chrome['installed_matches'], [apps[0]])
        self.assertEqual(telegram['installed_matches'], [])
        result['applications'][0]['app_id'] = 'changed'
        self.assertEqual(apps[0]['app_id'], 'test-only-Chrome')

    def test_exact_unknown_app_name_and_id_remain_supported(self):
        app = {'name': 'Editor de cálculo', 'app_id': 'TestVendor.Tool_abc!App'}
        with patch.object(catalog, 'installed_apps', return_value=[app]):
            by_id = catalog.resolve_application('TestVendor.Tool_abc!App')
            by_name = catalog.resolve_application('EDITOR DE CALCULO')
            self.assertIsNone(by_id['profile'])
            self.assertEqual(by_id['app'], app)
            self.assertEqual(by_name, by_id)
            with self.assertRaises(ValueError):
                catalog.resolve_application('testvendor.tool_abc!app')
            with self.assertRaises(ValueError):
                catalog.resolve_application('Editor')

    def test_alias_resolution_ambiguity_and_no_installed_claim_from_profile(self):
        apps = [{'name': 'Google Chrome', 'app_id': 'test-only-Chrome-A'},
                {'name': 'Google Chrome', 'app_id': 'test-only-Chrome-B'}]
        with patch.object(catalog, 'installed_apps', return_value=apps):
            with self.assertRaises(ValueError) as ambiguous:
                catalog.resolve_application('chrome')
            self.assertIn(apps[0]['app_id'], str(ambiguous.exception))
            self.assertIn(apps[1]['app_id'], str(ambiguous.exception))
            self.assertEqual(catalog.resolve_application(apps[1]['app_id'])['app'], apps[1])
            self.assertEqual(catalog.resolve_application(apps[1]['app_id'])['profile']['id'], 'chrome')
        with patch.object(catalog, 'installed_apps', return_value=[]):
            self.assertIsNotNone(catalog.profile_for('telegram'))
            with self.assertRaisesRegex(ValueError, 'inventario'):
                catalog.resolve_application('telegram')

    def test_exact_inventory_id_cannot_attach_an_unrelated_profile(self):
        app = {'name': 'Notepad', 'app_id': 'chrome'}
        with patch.object(catalog, 'installed_apps', return_value=[app]):
            with self.assertRaisesRegex(ValueError, 'ambigua') as ambiguous:
                catalog.resolve_application('chrome')
            self.assertIn(app['name'], str(ambiguous.exception))
            self.assertEqual(catalog.resolve_application('Notepad')['app'], app)

    def test_invalid_inventory_and_query_fail_closed(self):
        for apps in (None, [{'name': 'Missing ID'}], [{'name': 'Tool', 'app_id': 'bad\nID'}]):
            with self.subTest(apps=apps), patch.object(catalog, 'installed_apps', return_value=apps):
                with self.assertRaises(ValueError):
                    catalog.installed_catalog()
        for query in ('', '   ', None, 'tool\n.exe', 'a'*1025):
            with self.subTest(query=repr(query)), self.assertRaises(ValueError):
                catalog.resolve_application(query)

    def test_corrupt_or_ambiguous_profile_metadata_is_rejected(self):
        original = {'version': 1, 'profiles': catalog.profiles()}
        cases = []
        duplicate = copy.deepcopy(original)
        duplicate['profiles'][1]['aliases'].append('chrome')
        cases.append(duplicate)
        invalid = copy.deepcopy(original)
        invalid['profiles'][0]['commands'][0]['kind'] = 'shell'
        cases.append(invalid)
        invalid = copy.deepcopy(original)
        invalid['profiles'][0]['process_names'] = [r'C:\invented\chrome.exe']
        cases.append(invalid)
        cases.append(original | {'version': True})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'resources').mkdir()
            for case in cases:
                (root/'resources/application-profiles.json').write_text(json.dumps(case), encoding='utf-8')
                with self.subTest(case=cases.index(case)), patch.object(catalog.sys, '_MEIPASS', directory, create=True), self.assertRaises(ValueError):
                    catalog.profiles()


if __name__ == '__main__':
    unittest.main()
