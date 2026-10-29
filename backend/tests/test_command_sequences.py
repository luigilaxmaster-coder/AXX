import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.action_learning import ActionLearning
from backend.actions.command_language import command_sequence


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

    def test_training_matrix_preserves_clauses_quotes_and_order(self):
        scenarios = [
            ('busca gatos en YouTube y abre Chrome', ['busca gatos en YouTube','abre Chrome']),
            ('en YouTube busca gatos y abre Chrome', ['en YouTube busca gatos','abre Chrome']),
            ('encuentra gatos en YouTube y abre Chrome', ['encuentra gatos en YouTube','abre Chrome']),
            ('cierra Spotify y abre YouTube', ['cierra Spotify','abre YouTube']),
            ('calcula 2+2 y abre YouTube', ['calcula 2+2','abre YouTube']),
            ('primero abre YouTube, busca Faint y abre calculadora', ['abre YouTube','busca Faint','abre calculadora']),
            ('abre YouTube\nbusca Faint', ['abre YouTube','busca Faint']),
            ('abre YouTube y después, busca Faint', ['abre YouTube','busca Faint']),
            ('lista mis ventanas y consulta el estado del sistema', ['lista mis ventanas','consulta el estado del sistema']),
            ('abre Bloc de notas y escribe: rock y abre Chrome', ['abre Bloc de notas','escribe: rock y abre Chrome']),
            ('busca "rock y abre Chrome" en YouTube y abre calculadora', ['busca "rock y abre Chrome" en YouTube','abre calculadora']),
            ('busca «rock; abre Chrome» en YouTube; abre calculadora', ['busca «rock; abre Chrome» en YouTube','abre calculadora']),
            ("busca Linkin Park's Faint en YouTube y abre calculadora", ["busca Linkin Park's Faint en YouTube",'abre calculadora']),
        ]
        for text, parts in scenarios:
            with self.subTest(text=text):
                self.assertEqual(command_sequence(text,'text'),parts)
                self.assertIn(self.commands.resolve(text)['match'], ('sequence','sequence_request'))
        for text in ['busca "rock y abre Chrome"','busca «rock; abre Chrome»','no abras Chrome y abre YouTube','escribe: hola y abre Chrome']:
            with self.subTest(protected=text): self.assertIsNone(command_sequence(text,'text'))
        self.assertEqual(self.executor.list_operations(),[])

    def test_search_destination_cannot_absorb_later_browser_clause(self):
        result=self.commands.resolve('busca gatos en YouTube y abre Chrome')
        self.assertEqual(result['match'],'sequence')
        self.assertEqual(result['steps'][0], {'command_id':'axx.desktop.search','inputs':{'engine':'youtube','query':'gatos'}})
        self.assertEqual(len(result['steps']),2)

    def test_failed_middle_step_stops_later_effects_and_is_not_replayed(self):
        model=Mock();learning=ActionLearning(self.commands,model)
        try:
            plan=learning.prepare_steps('crear, comprobar y continuar',[
                {'command_id':'axx.artifact.write','inputs':{'path':'first.txt','content':'verified first'}},
                {'command_id':'axx.file.sha256','inputs':{'path':str(self.executor.workspace_root/'missing.txt')}},
                {'command_id':'axx.artifact.write','inputs':{'path':'must-not-exist.txt','content':'NO'}}])
            result=learning.execute(plan['operation_id'],True)
            self.assertNotEqual(result['state'],'succeeded')
            self.assertTrue((self.executor.workspace_root/'first.txt').is_file())
            self.assertFalse((self.executor.workspace_root/'must-not-exist.txt').exists())
            count=len(self.executor.list_operations())
            learning.execute(plan['operation_id'],True)
            self.assertEqual(len(self.executor.list_operations()),count)
        finally: learning.close()

    def test_typed_prefix_cannot_bypass_the_same_complete_plan_check(self):
        learning=ActionLearning(self.commands,Mock())
        try:
            plan=learning.prepare_steps('abre YouTube y busca Faint',[
                {'command_id':'axx.desktop.open_url','inputs':{'url':'https://www.youtube.com/'}}])
            self.assertEqual(plan['state'],'needs_input')
            self.assertFalse(plan['preparation_complete'])
            self.assertEqual(self.executor.list_operations(),[])
        finally: learning.close()

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
