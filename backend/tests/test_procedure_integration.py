import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from backend.actions.executor import ActionExecutor
from backend.actions.file_inspection import hash_file
from backend.actions.desktop import resolve_desktop, open_target
from backend.commands import CommandService, ApprovalRequired
from backend.procedure_library import ProcedureLibrary
from scripts.import_procedure_folder import build


class ProcedureIntegrationTests(unittest.TestCase):
    def test_recently_created_files_hash_without_timestamp_false_positives(self):
        with tempfile.TemporaryDirectory() as temp:
            for number in range(30):
                target = Path(temp) / str(number)
                target.write_bytes(b'fresh bytes')
                self.assertEqual(hash_file(str(target), threading.Event())['sha256'], hashlib.sha256(b'fresh bytes').hexdigest())

    def test_import_preserves_steps_prefers_reviewed_and_never_enables_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source'; source.mkdir()
            original = {'id': 'AXX-TEST-1', 'title': 'Prueba', 'steps': [{'action': 'base'}], 'execution_enabled': True}
            (source / 'base.jsonl').write_text(json.dumps(original), encoding='utf-8')
            with zipfile.ZipFile(source / 'REVISADO.zip', 'w') as archive:
                archive.writestr('recipes.jsonl', json.dumps(original | {'steps': [{'action': 'revisado'}]}))
            (source / 'ZZ-BORRADOR.jsonl').write_text(json.dumps(original | {'steps': [{'action': 'borrador'}]}), encoding='utf-8')
            target = root / 'procedure-library.zip'
            build(source, target, root / 'audit.json')
            library = ProcedureLibrary(target)
            self.assertIsNone(library.error)
            record = library.get('AXX-TEST-1')
            self.assertFalse(record['execution_enabled'])
            self.assertEqual(record['recipe']['steps'][0]['action'], 'revisado')
            self.assertIsNone(library.get('../../escape'))
            build(source, root / 'second.zip', root / 'audit2.json')
            self.assertEqual(target.read_bytes(), (root / 'second.zip').read_bytes())

    def test_recipe_binding_requires_path_approval_and_returns_real_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executor = ActionExecutor(root / 'state.db', root / 'artifacts')
            service = CommandService(executor)
            try:
                a = root / 'a.txt'; b = root / 'b.txt'
                a.write_bytes(b'actual file'); b.write_bytes(b'actual file')
                pending = service.prepare('AXX-02-0148', {'path': str(a), 'other_path': str(b)})
                self.assertEqual(pending['command_id'], 'axx.file.compare')
                with self.assertRaises(ApprovalRequired): service.execute(pending['operation_id'])
                result = service.execute(pending['operation_id'], True)
                self.assertEqual(result['state'], 'succeeded', result)
                self.assertTrue(result['output']['equal'])
                self.assertEqual(result['output']['files'][0]['sha256'], hashlib.sha256(b'actual file').hexdigest())
                with self.assertRaises(ValueError): service.prepare('axx.file.sha256', {'path': '../outside'})
                cancelled = threading.Event(); cancelled.set()
                with self.assertRaisesRegex(ValueError, 'cancelada'): hash_file(str(a), cancelled)
            finally:
                service.close(); executor.close()

    def test_installed_app_matching_ambiguity_and_unobserved_id(self):
        apps = [{'name': 'Test Editor', 'app_id': 'Observed.App_123!App'}, {'name': 'Test Player', 'app_id': 'Observed.Player!App'}]
        with patch('backend.actions.windows_apps.installed_apps', return_value=apps), patch('os.startfile', create=True) as launch:
            resolved = resolve_desktop('abre Test Editor', 'text')
            self.assertEqual(resolved['inputs']['app_id'], apps[0]['app_id'])
            self.assertEqual(resolve_desktop('abre Test', 'text')['match'], 'ambiguous')
            result = open_target('installed_app', resolved['inputs'])
            self.assertEqual(result['evidence']['verification'], 'os_handoff')
            launch.assert_called_once_with('shell:AppsFolder\\Observed.App_123!App')
            with self.assertRaises(ValueError): open_target('installed_app', {'app_id': 'made-up.exe'})
            with tempfile.TemporaryDirectory() as temp:
                executor = ActionExecutor(Path(temp) / 'state.db', Path(temp) / 'artifacts')
                service = CommandService(executor)
                try:
                    pending = service.prepare(resolved['command_id'], resolved['inputs'])
                    self.assertEqual(service.execute(pending['operation_id'])['state'], 'succeeded')
                    pending = service.prepare('axx.desktop.list_apps', {})
                    result = service.execute(pending['operation_id'])
                    self.assertEqual(result['state'], 'succeeded')
                    self.assertEqual(len(result['output']['applications']), 2)
                finally:
                    service.close(); executor.close()
