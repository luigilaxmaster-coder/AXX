import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.action_learning import ActionLearning
from backend.commands import CommandService
from backend.actions.tools import get_tool, ToolResult


class Planner:
    def __init__(self, steps): self.steps = steps
    def route(self, request):
        return {'ok': True, 'message': {'content': json.dumps({'title': 'Entrega', 'steps': self.steps})}}


class ComputerTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.planner = Planner([
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'entrega.txt', 'content': 'Entrega verificada'}},
            {'command_id': 'axx.file.sha256', 'inputs': {},
             'bindings': {'path': {'step': 0, 'path': ['output', 'path']}}}])
        self.learning = ActionLearning(self.commands, self.planner)

    def tearDown(self):
        self.learning.close(); self.commands.close(); self.executor.close(); self.tmp.cleanup()

    def test_receipt_binding_reads_real_artifact_and_does_not_replay_completed_steps(self):
        plan = self.learning.propose('Crea la entrega y comprueba su contenido')
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(result['results'][0]['output']['sha256'], result['results'][1]['output']['files'][0]['sha256'])
        self.assertIsNone(result['learned_action_id'])
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.learning.execute(plan['operation_id'], True)
        self.assertEqual(len(self.executor.list_operations()), 2)

    def test_real_find_to_bundle_executes_registered_pipeline_and_preserves_originals(self):
        import hashlib
        import zipfile
        sources = self.root / 'sources'; sources.mkdir()
        expected = {'alpha.txt': b'alpha original', 'beta.txt': 'beta áéíóú'.encode('utf-8')}
        for name, content in expected.items(): (sources / name).write_bytes(content)
        steps = [
            {'command_id': 'axx.file.find', 'inputs': {'directory': str(sources), 'pattern': '*.txt', 'limit': 10}},
            {'command_id': 'axx.file.bundle', 'inputs': {'destination': 'verified-copy', 'archive_name': 'delivery.zip'},
             'bindings': {'paths': {'step': 0, 'path': ['output', 'paths']}}},
        ]
        plan = self.learning.prepare_steps('Busca y copia los archivos de prueba a un ZIP nuevo', steps)
        result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(len(result['step_records']), 2)
        for record in result['step_records']:self.assertTrue(record['result']['postconditions_passed'])
        bundle = result['step_records'][1]['result']['output']
        self.assertEqual(len(bundle['files']), 2)
        with zipfile.ZipFile(bundle['archive']['path']) as archive:
            for row in bundle['files']:
                content = expected[row['name']]
                self.assertEqual((sources / row['name']).read_bytes(), content)
                self.assertEqual(Path(row['path']).read_bytes(), content)
                self.assertEqual(archive.read(row['name']), content)
                self.assertEqual(row['sha256'], hashlib.sha256(content).hexdigest())
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.learning.execute(plan['operation_id'], True)
        self.assertEqual(len(self.executor.list_operations()), 2)

    def test_pause_checkpoint_resume_preserves_completed_ids_and_effects(self):
        plan = self.learning.propose('Prepara una entrega con pausa')
        execute = self.commands.execute
        calls = []
        def paused_execute(key, *args, **kwargs):
            calls.append(key)
            result = execute(key, *args, **kwargs)
            self.learning.pause(plan['operation_id'])
            return result
        self.commands.execute = paused_execute
        paused = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(paused['state'], 'paused', paused)
        self.assertEqual(len(paused['results']), 1)
        self.assertEqual(paused['step_records'][0]['state'], 'succeeded')
        self.commands.execute = execute
        self.learning.close()
        self.learning = ActionLearning(self.commands, self.planner)
        self.assertEqual(self.learning.get(plan['operation_id'])['state'], 'paused')
        done = self.learning.resume(plan['operation_id'], True)
        self.assertEqual(done['state'], 'succeeded', done)
        self.assertEqual(done['step_records'][0]['operation_id'], calls[0])
        self.assertEqual(len(self.executor.list_operations()), 2)

    def test_forward_and_shell_bindings_are_rejected_before_execution(self):
        for command, inputs in [('axx.file.sha256', {}), ('axx.shell.cmd', {}), ('axx.process.run', {})]:
            with self.subTest(command=command):
                steps = [{'command_id': command, 'inputs': inputs,
                          'bindings': {'path': {'step': 0, 'path': ['output', 'path']}}}]
                with self.assertRaises(ValueError): self.learning._validate_steps(steps, allow_shell=True)
        self.assertEqual(self.executor.list_operations(), [])

    def test_typed_plan_rejects_invalid_goal_and_implicit_process(self):
        for text in (None, '', 12):
            with self.assertRaises(ValueError): self.learning.prepare_steps(text, self.planner.steps)
        with self.assertRaises(ValueError):
            self.learning.prepare_steps('Crea un archivo', [{'command_id':'axx.process.run','inputs':{}}])

    def test_planning_catalog_fits_conservative_32k_budget_and_retains_typed_choices(self):
        messages = self.learning._prompt('Prepara un archivo de saludo', {})
        self.assertLess(len(json.dumps({'messages':messages,'tools':None},ensure_ascii=False).encode())+1024+2048,32768)
        catalog = json.loads(messages[0]['content'].split('\n',1)[1])['capabilities']
        state = next(item for item in catalog if item['command_id']=='axx.desktop.state')
        self.assertIn('Toggle',state['parameters']['pattern']['enum'])
        self.assertEqual(state['parameters']['window_id']['type'],'integer')

    def test_pause_during_prepare_does_not_dispatch_and_resume_uses_same_identity(self):
        plan = self.learning.propose('Prepara y espera antes de escribir')
        prepare = self.commands.prepare
        def pause_during_prepare(*args, **kwargs):
            result = prepare(*args, **kwargs)
            self.learning.pause(plan['operation_id'])
            return result
        self.commands.prepare = pause_during_prepare
        paused = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(paused['state'], 'paused', paused)
        self.assertFalse((self.executor.workspace_root / 'entrega.txt').exists())
        self.assertEqual(self.executor.list_operations(), [])
        first = paused['step_records'][0]['operation_id']
        self.commands.prepare = prepare
        done = self.learning.resume(plan['operation_id'], True)
        self.assertEqual(done['state'], 'succeeded', done)
        self.assertEqual(done['step_records'][0]['operation_id'], first)

    def test_missing_receipt_field_fails_without_second_dispatch(self):
        self.planner.steps[1]['bindings']['path']['path'] = ['output', 'absent']
        plan = self.learning.propose('Comprueba un campo ausente')
        result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_plan_mode_is_validated_and_bound_to_approval(self):
        self.planner.steps[0]['delivery_mode'] = 'isolated'
        plan = self.learning.propose('Crea una entrega aislada')
        self.assertNotEqual(plan['state'], 'awaiting_approval')
        self.assertEqual(self.executor.list_operations(), [])

    def _input_step(self, observation='first-observation'):
        return {'command_id': 'axx.desktop.input', 'inputs': {'window_id': 42, 'pid': 7,
                'observation_id': observation, 'action': 'type_text', 'text': 'fixture'}}

    def _unknown_input_result(self):
        return ToolResult(True, output={'dispatch_status': 'delivered', 'effect_status': 'unknown'},
                          evidence={'verification': 'input_delivery_only', 'effect_uncertain': True,
                                    'reconciliation_required': True})

    def test_manual_review_unlocks_new_action_but_never_certifies_or_replays_unknown_effect(self):
        step = self._input_step()
        pending = self.commands.prepare(**step)
        with patch.object(get_tool('computer_input'), 'execute_with_runtime', return_value=self._unknown_input_result()) as dispatch:
            unknown = self.commands.execute(pending['operation_id'], True)
        dispatch.assert_called_once()
        self.assertEqual(unknown['state'], 'unknown')
        for observation in ('first-observation', 'fresh-observation'):
            with self.assertRaises(ValueError):
                self.commands.prepare(**self._input_step(observation))
        with patch.object(self.executor, 'execute_action') as execute:
            for reviewed in (False, None, 1, 'true'):
                with self.assertRaises(ValueError):
                    self.commands.review_unknown(unknown['operation_id'], reviewed)
            reviewed = self.commands.review_unknown(unknown['operation_id'], True)
            self.assertEqual(self.commands.review_unknown(unknown['operation_id'], True), reviewed)
            replay = self.commands.execute(unknown['operation_id'], True)
            self.assertEqual(replay['state'], 'unknown')
            execute.assert_not_called()
        self.assertTrue(reviewed['evidence']['manual_reviewed'])
        self.assertFalse(reviewed['evidence']['reconciliation_required'])
        self.assertEqual(reviewed['state'], 'unknown')
        self.assertEqual(reviewed['effect_status'], 'unknown')
        self.assertFalse(reviewed['postconditions_passed'])
        action = self.executor.get_operation(unknown['action_operation_id'])
        self.assertTrue(action['evidence']['manual_reviewed'])
        self.assertEqual(action['state'], 'unknown')
        self.assertFalse(action['postconditions_passed'])
        fresh = self.commands.prepare(**self._input_step('fresh-observation'))
        self.assertEqual(fresh['state'], 'awaiting_approval')
        self.assertNotEqual(fresh['operation_id'], unknown['operation_id'])
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_manual_review_is_serialized_and_rejects_nonunknown_operations(self):
        with self.assertRaises(ValueError):self.commands.review_unknown('absent', True)
        prepared = self.commands.prepare(**self._input_step())
        with self.assertRaises(ValueError):self.commands.review_unknown(prepared['operation_id'], True)
        self.commands.execution_gate.acquire()
        try:
            with self.assertRaises(ValueError):self.commands.review_unknown(prepared['operation_id'], True)
        finally:self.commands.execution_gate.release()
        self.assertEqual(self.commands.get(prepared['operation_id'])['state'], 'awaiting_approval')

    def test_manual_review_does_not_resume_unknown_plan_or_resolve_its_bindings(self):
        plan = self.learning.prepare_steps('Escribe en la ventana de prueba', [self._input_step()])
        with patch.object(get_tool('computer_input'), 'execute_with_runtime', return_value=self._unknown_input_result()):
            unknown = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(unknown['state'], 'unknown')
        command_id = unknown['step_records'][0]['operation_id']
        self.commands.review_unknown(command_id, True)
        with patch.object(self.executor, 'execute_action') as execute:
            resumed = self.learning.resume(plan['operation_id'], True)
            execute.assert_not_called()
        self.assertEqual(resumed['state'], 'unknown')
        self.assertFalse(resumed['step_records'][0]['result']['postconditions_passed'])


if __name__ == '__main__': unittest.main()
