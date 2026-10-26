"""Contract tests with real files/SQLite and injected dispatch failures."""
from pathlib import Path
import tempfile
import threading
import unittest
import hashlib
from unittest.mock import patch

from backend.actions.executor import ActionExecutor, ActionExecutionError
from backend.actions.tools import get_tool, ToolResult
from backend.commands import CommandService


class UnifiedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)

    def tearDown(self):
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def test_background_file_write_is_verified_and_mode_bound_to_identity(self):
        inputs = {'path': 'result.txt', 'content': 'Verified local result'}
        pending = self.commands.prepare('axx.artifact.write', inputs, operation_id='background-write', delivery_mode='background')
        result = self.commands.execute(pending['operation_id'], approved=True)
        self.assertEqual((self.root / 'artifacts/result.txt').read_text(), inputs['content'])
        self.assertEqual(result['effect_status'], 'confirmed')
        self.assertEqual(result['delivery_mode'], 'background')
        self.assertEqual(self.commands.execute('background-write', approved=True)['evidence'], result['evidence'])
        with self.assertRaisesRegex(ValueError, 'otros parámetros'):
            self.commands.prepare('axx.artifact.write', inputs, operation_id='background-write', delivery_mode='foreground')
        with self.assertRaisesRegex(ActionExecutionError, 'different delivery mode'):
            self.executor.execute_action('file_artifact_writer', inputs, result['action_operation_id'], delivery_mode='foreground')

    def test_unsupported_mode_rejected_before_any_dispatch_in_both_entry_points(self):
        for mode in ('background', 'isolated'):
            with self.subTest(mode=mode), patch.object(self.executor, 'execute_action') as dispatch:
                with self.assertRaisesRegex(ValueError, mode + '_unavailable'):
                    self.commands.prepare('axx.desktop.open_app', {'app': 'calculator'}, delivery_mode=mode)
                dispatch.assert_not_called()
        with self.assertRaisesRegex(ActionExecutionError, 'background_unavailable'):
            self.executor.execute_action('desktop_powershell', {'script': 'Write-Output nope'}, delivery_mode='background')
        self.assertEqual(self.executor.list_operations(), [])

    def test_cancelled_at_dispatch_boundary_does_not_write(self):
        event = threading.Event()
        event.set()
        result = self.executor.execute_action('file_artifact_writer', {'path':'never.txt','content':'never'}, 'cancelled', event)
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['dispatch_status'], 'not_attempted')
        self.assertFalse((self.root / 'artifacts/never.txt').exists())
        self.assertEqual(self.executor.get_operation('cancelled')['dispatch_status'], 'not_attempted')

    def test_nonzero_shell_exit_is_delivered_but_not_verified(self):
        tool = get_tool('desktop_powershell')
        with patch.object(tool, 'execute_with_control', return_value=ToolResult(False, output={'exit_code':7},
                evidence={'verification':'process_exit', 'exit_code':7}, error='Exit 7')):
            result = self.executor.execute_action('desktop_powershell', {'script':'exit 7'})
        self.assertEqual(result['dispatch_status'], 'delivered')
        self.assertEqual(result['state'], 'failed')
        self.assertFalse(result['postconditions_passed'])

    def test_failed_journal_commit_never_dispatches(self):
        tool = get_tool('file_artifact_writer')
        with self.executor.db:
            self.executor.db.execute("CREATE TRIGGER fail_dispatch BEFORE UPDATE ON operations WHEN NEW.state='running' BEGIN SELECT RAISE(ABORT, 'disk unavailable'); END")
        with patch.object(tool, 'execute_cancellable') as dispatch:
            with self.assertRaisesRegex(Exception, 'disk unavailable'):
                self.executor.execute_action('file_artifact_writer', {'path':'never.txt','content':'never'})
            dispatch.assert_not_called()

    def test_restart_overrides_stale_success_and_never_replays_effect(self):
        result = self.executor.execute_action('file_artifact_writer', {'path':'once.txt','content':'one'}, 'once')
        with self.executor.db:
            self.executor.db.execute("UPDATE operations SET state='running' WHERE operation_id='once'")
        self.commands.close()
        self.executor.close()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        recovered = self.executor.execute_action('file_artifact_writer', {'path':'once.txt','content':'one'}, 'once')
        self.assertEqual(recovered['state'], 'unknown')
        self.assertFalse(recovered['postconditions_passed'])
        self.assertTrue(recovered['replayed'])
        self.assertEqual(recovered['evidence'], result['evidence'])

    def test_unknown_mutation_cannot_be_recreated_with_new_id(self):
        tool = get_tool('desktop_open_app')
        inputs = {'app': 'calculator'}
        pending = self.commands.prepare('axx.desktop.open_app', inputs)
        with patch.object(tool, 'execute_with_control', side_effect=OSError('lost result')):
            result = self.commands.execute(pending['operation_id'])
        self.assertEqual(result['state'], 'unknown')
        with self.assertRaisesRegex(ValueError, 'efecto desconocido'):
            self.commands.prepare('axx.desktop.open_app', inputs)
        inspection = self.commands.prepare('axx.architecture.status', {}, command_mode='ask')
        self.assertEqual(self.commands.execute(inspection['operation_id'], approved=True)['state'], 'succeeded')

    def test_reconciliation_updates_effect_state_in_both_receipts(self):
        inputs = {'window_id':'0x123', 'pid':42, 'control_id':'a'*64, 'value':'confirmed'}
        tool = get_tool('desktop_set_window_value')
        pending = self.commands.prepare('axx.desktop.window.set_value', inputs)
        with patch.object(tool, 'execute_with_control', return_value=ToolResult(False, error='worker timeout',
                evidence={'effect_uncertain':True, 'reconciliation_target':{'window_id':291,'pid':42,'control_id':'a'*64}})):
            unknown = self.commands.execute(pending['operation_id'], approved=True)
        self.assertEqual(unknown['effect_status'], 'unknown')
        readback = {'value_sha256':hashlib.sha256(b'confirmed').hexdigest(), 'value_length':9}
        with patch('backend.actions.windows_automation._uia', return_value=readback):
            result = self.commands.reconcile(pending['operation_id'])
        self.assertEqual(result['effect_status'], 'confirmed')
        self.assertEqual(result['state'], 'succeeded')
        self.assertEqual(self.executor.get_operation(result['action_operation_id'])['effect_status'], 'confirmed')

    def test_component_inventory_never_claims_external_integrations(self):
        pending = self.commands.prepare('axx.architecture.status', {})
        result = self.commands.execute(pending['operation_id'])
        self.assertEqual(result['state'], 'succeeded')
        components = {item['id']:item for item in result['output']['components']}
        for name in ('cua_driver', 'rea', 'isolated_desktop', 'telegram'):
            self.assertEqual(components[name]['state'], 'unavailable')
        self.assertEqual(components['visual_grounding']['state'], 'unknown')
        self.assertIn('autorización', components['visual_grounding']['reason'])
        self.assertEqual(self.commands.resolve('estado de integraciones')['command_id'], 'axx.architecture.status')

    def test_semantic_selection_abstains_without_unique_complete_evidence(self):
        button = {'control_type':'ControlType.Button', 'enabled':True, 'offscreen':False,
                  'name':'Guardar', 'control_id':'a' * 64, 'supports_invoke_pattern':True}
        cases = [([button], False, 'selected'), ([button, button], False, 'ambiguous'),
                 ([], False, 'not_found'), ([button], True, 'ambiguous'),
                 ([button | {'supports_invoke_pattern': False}], False, 'not_found'),
                 ([button | {'enabled': False}], False, 'not_found')]
        for controls, truncated, expected in cases:
            with self.subTest(expected=expected), patch('backend.actions.windows_automation.inspect_controls',
                    return_value={'controls':controls, 'truncated':truncated, 'observation':{'observation_id':'test'}}):
                pending = self.commands.prepare('axx.desktop.window.find', {'window_id':'0x123', 'pid':42, 'name':'Guardar'})
                result = self.commands.execute(pending['operation_id'])
                self.assertEqual(result['state'], 'succeeded', result)
                self.assertEqual(result['output']['selection_status'], expected)
                self.assertFalse(result['output']['effect_executed'])
                self.assertEqual(bool(result['output']['candidate']), expected == 'selected')


if __name__ == '__main__':
    unittest.main()
