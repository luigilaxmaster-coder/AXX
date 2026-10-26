import copy
import threading
import unittest
from unittest.mock import Mock, patch

from backend.actions.computer_tools import ADAPTERS, ComputerTool


class ComputerToolContractTests(unittest.TestCase):
    def setUp(self):
        target = {'window_id': 1, 'pid': 2}
        observed = target | {'observation_id': 'issued-token'}
        self.valid = {
            'observe': target,
            'find': target | {'name': 'Target'},
            'state': observed | {'control_id': 'a'*64, 'pattern': 'Toggle', 'state': {'value': True}},
            'input': observed | {'action': 'click', 'x': 10, 'y': 20},
            'grid': observed | {'control_id': 'a'*64, 'rows': 10, 'columns': 10},
        }

    def test_standalone_contract_accepts_valid_shapes_without_observation_io(self):
        with patch('backend.actions.windows_automation.get_observation') as lookup:
            for kind, body in self.valid.items():
                with self.subTest(kind=kind): self.assertTrue(ComputerTool(kind).verify_preconditions(body)[0])
            lookup.assert_not_called()

    def test_required_unknown_boolean_integer_and_length_are_rejected(self):
        for kind, body in self.valid.items():
            invalid = [None, [], dict(body, extra='untrusted'), dict(body, window_id=True), dict(body, pid=2**32)]
            schema = next(a['parameters'] for a in ADAPTERS.values() if a['tool'] == 'computer_' + kind)
            for key in (name for name, spec in schema.items() if spec.get('required')):
                value = copy.deepcopy(body); del value[key]; invalid.append(value)
            if 'observation_id' in body: invalid += [dict(body, observation_id=''), dict(body, observation_id='x'*81)]
            if 'control_id' in body: invalid += [dict(body, control_id='not-a-control'), dict(body, control_id='Z'*64)]
            for candidate in invalid:
                with self.subTest(kind=kind, body=candidate):
                    self.assertFalse(ComputerTool(kind).verify_preconditions(candidate)[0])

    def test_pattern_state_shapes_fail_before_dispatch(self):
        tool = ComputerTool('state')
        for pattern, value in [('Toggle', 1), ('SelectionItem', 'true'), ('RangeValue', float('nan')),
                               ('ExpandCollapse', 'toggle'), ('Scroll', {'vertical': 10}),
                               ('Scroll', {'horizontal': -1, 'vertical': float('inf')}), ('Value', '\ud800')]:
            body = dict(self.valid['state'], pattern=pattern, state={'value': value})
            with self.subTest(pattern=pattern): self.assertFalse(tool.verify_preconditions(body)[0])
        self.assertFalse(tool.verify_preconditions(dict(self.valid['state'], state={'value': True, 'code': 'run'}))[0])

    def test_input_conditional_fields_and_grid_cell_budget(self):
        for body in [dict(self.valid['input'], action='drag'), dict(self.valid['input'], keys=['Escape']),
                     dict(self.valid['input'], x=1.5)]:
            self.assertFalse(ComputerTool('input').verify_preconditions(body)[0])
        self.assertFalse(ComputerTool('grid').verify_preconditions(dict(self.valid['grid'], rows=20, columns=20))[0])
        self.assertFalse(ComputerTool('find').verify_preconditions(dict(self.valid['find'], name='x'*501))[0])

    def test_grounding_schema_requires_authorization_and_exact_fields(self):
        self.assertEqual(ADAPTERS['axx.desktop.ground']['tool'], 'computer_ground')
        body = {'window_id':1,'pid':2,'observation_id':'issued-token','goal':'Target',
                'provider_name':'selected','model':'vision','image_authorized':True}
        self.assertTrue(ComputerTool('ground').verify_preconditions(body)[0])
        for candidate in [dict(body, image_authorized=False), dict(body, image_authorized=1),
                          dict(body, provider_name=''), dict(body, goal='x'*1001), dict(body, code='click()')]:
            self.assertFalse(ComputerTool('ground').verify_preconditions(candidate)[0])

    def test_unknown_tool_is_rejected(self):
        self.assertFalse(ComputerTool('arbitrary').verify_preconditions(self.valid['observe'])[0])

    def test_direct_execution_rejects_malformed_arguments_without_dispatch(self):
        runtime = Mock()
        targets = ['backend.actions.desktop_observation.observe_desktop',
                   'backend.actions.windows_automation.set_control_state',
                   'backend.actions.windows_automation.read_control_grid',
                   'backend.actions.desktop_input.execute_action',
                   'backend.actions.visual_grounding.propose_grounding']
        patches = [patch(name) for name in targets]
        spies = [p.start() for p in patches]
        for p in patches: self.addCleanup(p.stop)
        for kind, body in self.valid.items():
            result = ComputerTool(kind).execute_with_runtime(dict(body, unknown=True), None, threading.Event(), runtime)
            self.assertFalse(result.success)
        result = ComputerTool('ground').execute_with_runtime({}, None, threading.Event(), runtime)
        self.assertFalse(result.success)
        for spy in spies: spy.assert_not_called()
        runtime.input_control.automation.assert_not_called()

    def test_window_selector_returns_typed_ids_for_unique_exact_match(self):
        from backend.actions import windows_automation as uia
        rows = [{'window_id':10,'pid':20,'title':'Other','class_name':'Window'},
                {'window_id':31,'pid':41,'title':'Exact target','class_name':'Window'}]
        tool = ComputerTool('window')
        with patch.object(uia, 'list_windows', return_value=rows), \
             patch.object(uia, 'process_name', return_value='fixture.exe'), \
             patch.object(uia, 'process_started', return_value='12345'):
            result = tool.execute({'title':'Exact target','process_name':'FIXTURE.EXE'})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output, {'window_id':31,'window_id_hex':'0x1f','pid':41,
                                        'title':'Exact target','process_name':'fixture.exe'})
        self.assertFalse(result.evidence['effect_executed'])
        self.assertTrue(tool.verify_postconditions({}, result)[0])

    def test_window_selector_abstains_on_duplicates_absence_and_truncation(self):
        from backend.actions import windows_automation as uia
        row = {'window_id':31,'pid':41,'title':'Exact target','class_name':'Window'}
        for rows in [[], [row, dict(row, window_id=32)], [row]*512, [dict(row, title='Exact target suffix')]]:
            with self.subTest(count=len(rows)), patch.object(uia, 'list_windows', return_value=rows), \
                 patch.object(uia, 'process_name', return_value='fixture.exe'), \
                 patch.object(uia, 'process_started', return_value='12345'):
                self.assertFalse(ComputerTool('window').execute({'title':'Exact target'}).success)

    def test_window_selector_rechecks_identity_and_uniqueness(self):
        from backend.actions import windows_automation as uia
        row = {'window_id':31,'pid':41,'title':'Exact target','class_name':'Window'}
        for second, births in [([dict(row, pid=42)], ['12345']), ([row, dict(row,window_id=32)], ['12345']),
                               ([row], ['12345','67890'])]:
            with self.subTest(second=second, births=births), patch.object(uia, 'list_windows', side_effect=[[row],second]), \
                 patch.object(uia, 'process_name', return_value='fixture.exe'), \
                 patch.object(uia, 'process_started', side_effect=births):
                self.assertFalse(ComputerTool('window').execute({'title':'Exact target'}).success)

    def test_window_selector_can_disambiguate_only_by_exact_process_filename(self):
        from backend.actions import windows_automation as uia
        rows = [{'window_id':31,'pid':41,'title':'Exact target','class_name':'Window'},
                {'window_id':32,'pid':42,'title':'Exact target','class_name':'Window'}]
        with patch.object(uia, 'list_windows', return_value=rows), \
             patch.object(uia, 'process_name', side_effect=lambda pid: 'first.exe' if pid == 41 else 'second.exe'), \
             patch.object(uia, 'process_started', return_value='12345'):
            result = ComputerTool('window').execute({'title':'Exact target','process_name':'SECOND.EXE'})
            self.assertTrue(result.success, result.error)
            self.assertEqual(result.output['window_id'],32)

    def test_window_selector_rejects_unknown_fields_without_enumeration(self):
        with patch('backend.actions.windows_automation.list_windows') as windows:
            for body in [{}, {'title':'Exact','index':0}, {'title':True}, {'title':'x'*2049},
                         {'title':'Exact','process_name':'x'*261}]:
                self.assertFalse(ComputerTool('window').execute(body).success)
            windows.assert_not_called()


if __name__ == '__main__': unittest.main()
