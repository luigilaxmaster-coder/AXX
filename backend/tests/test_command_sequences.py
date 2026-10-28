import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.action_learning import ActionLearning


class CommandSequenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.executor=ActionExecutor(Path(self.tmp.name)/'state.db',Path(self.tmp.name)/'artifacts')
        self.commands=CommandService(self.executor)

    def tearDown(self):
        self.commands.close();self.executor.close();self.tmp.cleanup()

    def test_sequence_carries_search_target_without_executing(self):
        result=self.commands.resolve('abre YouTube y luego busca Faint de Linkin Park')
        self.assertEqual(result['match'],'sequence')
        self.assertEqual(result['steps'],[
            {'command_id':'axx.desktop.open_url','inputs':{'url':'https://www.youtube.com/'}},
            {'command_id':'axx.desktop.search','inputs':{'engine':'youtube','query':'Faint de Linkin Park'}}])
        self.assertTrue(result['requires_approval'])
        self.assertEqual(self.executor.list_operations(),[])

    def test_multiple_open_commands_remain_ordered(self):
        result=self.commands.resolve('abre calculadora y abre YouTube')
        self.assertEqual(result['match'],'sequence')
        self.assertEqual([s['command_id'] for s in result['steps']],['axx.desktop.open_app','axx.desktop.open_url'])

    def test_sequence_uses_existing_review_and_dependency_contract_without_a_model(self):
        model=Mock();learning=ActionLearning(self.commands,model)
        try:
            result=self.commands.resolve('abre YouTube y luego busca Faint')
            plan=learning.prepare_steps('abre YouTube y luego busca Faint',result['steps'],conversation_id='sequence-chat')
            self.assertEqual(plan['state'],'awaiting_approval')
            self.assertEqual(plan['conversation_id'],'sequence-chat')
            first,second=plan['step_records']
            self.assertEqual(plan['dependencies'][second['step_id']],[first['step_id']])
            model.route.assert_not_called();self.assertEqual(self.executor.list_operations(),[])
        finally:learning.close()

    def test_unresolved_step_never_executes_the_resolved_prefix(self):
        result=self.commands.resolve('abre YouTube y luego haz algo inexistente')
        self.assertEqual(result['match'],'sequence_request')
        self.assertIn('paso 2',result['message'])
        self.assertEqual(self.executor.list_operations(),[])

    def test_general_multistep_request_goes_to_planning_without_a_partial_effect(self):
        result=self.commands.resolve('crea un informe y luego convierte el informe a PDF')
        self.assertEqual(result['match'],'sequence_request')
        self.assertEqual(self.executor.list_operations(),[])

    def test_payload_negation_and_limit(self):
        for text in ['busca "rock y luego abre YouTube"','no abras YouTube y luego busca gatos']:
            self.assertNotEqual(self.commands.resolve(text)['match'],'sequence')
        result=self.commands.resolve('; '.join(['abre YouTube']*9))
        self.assertEqual(result['match'],'needs_input')


if __name__=='__main__':unittest.main()
