"""Registry boundary checks for observed UIA capabilities."""
import unittest
from backend.actions.cli_anything_engine import CLIAppInterface
from backend.actions.tools import TOOL_REGISTRY
from backend.commands import ADAPTERS, PARALLEL_READ_COMMANDS

class TestCLIAnything(unittest.TestCase):
    def test_patterns_do_not_register_effects(self):
        app = CLIAppInterface(0x123, 99, 'Fixture', 'Editor', True,
            [{'control_id':'a'*64,'name':'Guardar','patterns':['Invoke'],'enabled':True}],False,1)
        self.assertEqual(set(app.to_dict()['commands']), {'inspect','read','focus'})
        self.assertNotIn('save',app.to_dict()['commands'])
        self.assertIn('propuesta',app.generate_cli_help())

    def test_scan_traverses_real_command_service_and_executor(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from backend.commands import CommandService
        from backend.actions.executor import ActionExecutor
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db')
            commands = CommandService(executor)
            try:
                app = CLIAppInterface(0x123,99,'Fixture','Editor',True,[],False,1)
                with patch('backend.actions.cli_anything_engine.ENGINE.scan_window',return_value=app):
                    pending=commands.prepare('axx.desktop.cli_anything.scan',{'window_id':'0x123','pid':99},command_mode='ask')
                    self.assertEqual(pending['state'],'awaiting_approval')
                    result=commands.execute(pending['operation_id'],approved=True)
                    self.assertEqual(result['state'],'succeeded',result)
                    self.assertTrue(result['postconditions_passed'])
                    self.assertEqual(result['output']['window_id'],0x123)
            finally:
                commands.close()
                executor.close()

    def test_scan_uses_existing_registry(self):
        self.assertIn('desktop_cli_anything_scan',TOOL_REGISTRY)
        self.assertNotIn('desktop_cli_anything_execute',TOOL_REGISTRY)
        self.assertEqual(ADAPTERS['axx.desktop.cli_anything.scan']['tool'],'desktop_cli_anything_scan')
        self.assertIn('axx.desktop.cli_anything.scan',PARALLEL_READ_COMMANDS)
        self.assertEqual(set(ADAPTERS['axx.desktop.cli_anything.scan']['parameters']),{'window_id','pid'})

    def test_catalog_uses_fresh_registered_contracts(self):
        from unittest.mock import patch
        from backend.actions.cli_anything_engine import CLIAnythingEngine
        engine = CLIAnythingEngine()
        app = CLIAppInterface(0x123, 99, 'Fixture', 'Editor', True,
            [{'control_id': 'a'*64, 'name': 'Guardar', 'patterns': ['Invoke'], 'enabled': True}], False, 1)
        with patch.object(engine, 'resolve', return_value=app) as resolve:
            first = engine.list_commands('0x123')
            engine.list_commands('0x123')
        self.assertEqual(resolve.call_count, 2)
        self.assertEqual({c['name'] for c in first['commands']}, {'inspect', 'read', 'focus'})
        self.assertTrue(all(c['command_id'] in ADAPTERS for c in first['commands']))
        self.assertFalse(any(c['execution_verified'] for c in first['commands']))
        self.assertFalse(hasattr(engine, 'execute_command'))
        self.assertFalse(hasattr(engine, 'memory'))

    def test_catalog_approval_metadata_matches_registry_risk_defaults(self):
        from unittest.mock import patch
        from backend.actions.cli_anything_engine import CLIAnythingEngine
        engine = CLIAnythingEngine()
        app = CLIAppInterface(0x123,99,'Fixture','Editor',True,[{
            'control_id':'a'*64,'enabled':True,'offscreen':False,
            'supports_value_pattern':True,'read_only':False}],False,1)
        with patch.object(engine,'resolve',return_value=app):
            result = engine.list_commands('0x123')
        approvals = {item['name']:item['requires_approval'] for item in result['commands']}
        self.assertEqual(approvals,{'inspect':False,'read':True,'focus':False,'type':True})

if __name__ == '__main__': unittest.main()
