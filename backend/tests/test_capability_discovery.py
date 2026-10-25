import unittest
from unittest.mock import patch
from backend.actions.cli_anything_engine import CLIAnythingEngine, CLIAppInterface
from backend.actions.desktop import validate_inputs
from backend.commands import ADAPTERS

MOD = 'backend.actions.cli_anything_engine.'

class CapabilityDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.engine = CLIAnythingEngine()
        self.window = dict(window_id=1234, pid=44, title='Owned fixture', class_name='Editor', foreground=True)
        self.control = dict(control_id='a'*64, enabled=True, offscreen=False, supports_value_pattern=True, read_only=False)
        self.app = CLIAppInterface(**self.window, controls=[self.control], truncated=False, observed_at=1)

    def test_exact_and_ambiguous_targets(self):
        with patch(MOD+'list_windows', return_value=[self.window,dict(self.window,window_id=1235)]):
            for target in ('Owned fixture','44'):
                with self.assertRaisesRegex(ValueError,'ambiguo'): self.engine.find_window_by_target(target)
            self.assertIsNone(self.engine.find_window_by_target('Owned'))
            self.assertEqual(self.engine.find_window_by_target('0x4d2')['window_id'],1234)
        with self.assertRaises(ValueError): self.engine.find_window_by_target(True)

    def test_no_arbitrary_active_fallback(self):
        with patch(MOD+'list_windows',return_value=[dict(self.window,foreground=False)]):
            self.assertIsNone(self.engine.get_active_app())

    def test_scan_is_fresh_and_cancellable(self):
        cancel=lambda: False
        with patch(MOD+'list_windows',return_value=[self.window]), patch(MOD+'scrape_window_tree',return_value={'window_title':'Owned fixture','controls':[self.control]}) as scrape:
            self.engine.scan_window(1234,44,cancelled=cancel)
            self.engine.scan_window(1234,44,cancelled=cancel)
            self.assertEqual(scrape.call_count,2)
            self.assertIs(scrape.call_args.kwargs['cancelled'],cancel)

    def test_changed_window_rejected(self):
        with patch(MOD+'list_windows',return_value=[self.window]), patch(MOD+'scrape_window_tree',return_value={'window_title':'Other'}):
            with self.assertRaises(ValueError): self.engine.scan_window(1234,44)

    def test_only_registered_typed_proposals(self):
        with patch.object(self.engine,'resolve',return_value=self.app):
            for name in ('inspect','read','focus'):
                proposal=self.engine.propose('0x4d2',name)
                self.assertIn(proposal['command_id'],ADAPTERS)
                self.assertEqual(proposal['inputs']['window_id'],'0x4d2')
            read=self.engine.propose('0x4d2','read')
            self.assertEqual(read['inputs']['expected_title'],'Owned fixture')
            proposal=self.engine.propose('0x4d2','type',{'control_id':'a'*64,'text':'hola'})
            self.assertEqual(proposal['command_id'],'axx.desktop.window.set_value')
            for name in ('click','save','run','delete'):
                with self.assertRaises(ValueError): self.engine.propose('0x4d2',name)
            with self.assertRaises(ValueError): self.engine.propose('0x4d2','focus',{'approved':True})

    def test_selector_and_read_only_gate(self):
        with patch.object(self.engine,'resolve',return_value=self.app):
            with self.assertRaises(ValueError): self.engine.propose('0x4d2','type',{'control_id':'b'*64,'text':'hi'})
            self.control['read_only']=True
            self.assertNotIn('type',self.app.to_dict()['commands'])
            with self.assertRaises(ValueError): self.engine.propose('0x4d2','type',{'control_id':'a'*64,'text':'hi'})

    def test_observed_button_proposes_only_reviewed_invoke(self):
        button=dict(control_id='b'*64, control_type='ControlType.Button', name='Nuevo chat', enabled=True, offscreen=False)
        self.app.controls.append(button)
        with patch.object(self.engine,'resolve',return_value=self.app):
            self.assertIn('press',self.app.to_dict()['commands'])
            proposal=self.engine.propose('0x4d2','press',{'control_id':'b'*64})
            self.assertEqual(proposal['command_id'],'axx.desktop.window.invoke')
            self.assertEqual(proposal['inputs']['expected_name'],'Nuevo chat')
            with self.assertRaises(ValueError): self.engine.propose('0x4d2','press',{'control_id':'a'*64})
            button['offscreen']=True
            with self.assertRaises(ValueError): self.engine.propose('0x4d2','press',{'control_id':'b'*64})

    def test_no_executor_or_approval_bypass(self):
        self.assertFalse(hasattr(self.engine,'execute_command'))
        self.assertNotIn('axx.desktop.cli_anything.execute',ADAPTERS)
        with self.assertRaises(ValueError): validate_inputs('cli_anything_scan',{'target':'active'})
        validate_inputs('cli_anything_scan',{'window_id':'0x4d2','pid':44})

if __name__ == '__main__': unittest.main()
