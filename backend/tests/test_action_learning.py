import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService, ApprovalRequired
from backend.action_learning import ActionLearning


class Model:
    calls = 0
    def __init__(self, answer): self.answer = answer
    def route(self, request):
        self.calls += 1
        return {'ok': True, 'message': {'content': json.dumps(self.answer)}}


class ActionLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = Model({'title': 'Estado local', 'steps': [{'command_id': 'axx.system.telemetry', 'inputs': {}}]})
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning

    def tearDown(self):
        self.learning.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    def test_chat_origin_is_durable_and_cannot_be_rebound(self):
        plan=self.learning.propose('prepara un diagnóstico', operation_id='chat-plan', conversation_id='chat-a')
        self.assertEqual(self.learning.get(plan['operation_id'])['conversation_id'],'chat-a')
        self.assertEqual(plan['state'],'awaiting_approval')
        with self.assertRaises(ValueError):
            self.learning.propose('prepara un diagnóstico', operation_id='chat-plan', conversation_id='chat-b')

    def test_api_plan_without_chat_uses_valid_stable_inference_identity(self):
        original=self.model.route;requests=[]
        def checked(request):
            requests.append(request)
            self.assertIsInstance(request['conversation_id'],str)
            self.assertTrue(1<=len(request['conversation_id'])<=128)
            return original(request)
        self.model.route=checked
        plan=self.learning.propose('prepara un diagnóstico',operation_id='api-plan')
        self.assertEqual(plan['state'],'awaiting_approval')
        self.assertEqual(requests[0]['conversation_id'],'api-plan')
        self.assertEqual(self.executor.list_operations(),[])

    def test_model_receives_ordered_clauses_and_cannot_drop_the_suffix(self):
        seen=[];original=self.model.route
        def capture(request):
            seen.append(request);return original(request)
        self.model.route=capture
        plan=self.learning.propose('abre YouTube y busca Faint y abre calculadora')
        self.assertEqual(plan['state'],'needs_input')
        user=json.loads(seen[0]['messages'][-1]['content'])
        self.assertEqual(user['requested_steps'],['abre YouTube','busca Faint','abre calculadora'])
        self.assertEqual(self.model.calls,2)
        self.assertEqual(self.executor.list_operations(),[])

    def test_model_can_correct_an_incomplete_plan_once_before_review(self):
        requests=[]
        def answer(request):
            requests.append(request)
            steps=[{'command_id':'axx.desktop.open_url','inputs':{'url':'https://www.youtube.com/'}}]
            if len(requests)==2: steps.append({'command_id':'axx.desktop.search','inputs':{'engine':'youtube','query':'Faint'}})
            return {'ok':True,'message':{'content':json.dumps({'title':'Abrir y buscar','steps':steps})}}
        self.model.route=answer
        plan=self.learning.propose('abre YouTube y busca Faint')
        self.assertEqual(plan['state'],'awaiting_approval')
        self.assertEqual(len(plan['steps']),2)
        self.assertEqual(plan['model_calls_used'],2)
        self.assertEqual([r['provider_name'] for r in requests],['',''])
        self.assertTrue(all(r['allow_paid'] is False for r in requests))
        self.assertEqual(self.executor.list_operations(),[])

    def test_parameter_contract_reaches_model_and_invalid_path_is_corrected_before_effects(self):
        requests=[]
        def answer(request):
            requests.append(request)
            path=str(self.executor.workspace_root/'training.txt') if len(requests)==1 else 'training.txt'
            return {'ok':True,'message':{'content':json.dumps({'title':'Crear prueba','steps':[
                {'command_id':'axx.artifact.write','inputs':{'path':path,'content':'TRAINING'}}]})}}
        self.model.route=answer
        plan=self.learning.propose('crea un archivo de prueba training.txt con el texto TRAINING')
        self.assertEqual(plan['state'],'awaiting_approval')
        self.assertEqual(plan['steps'][0]['inputs']['path'],'training.txt')
        self.assertEqual(plan['model_calls_used'],2)
        prompt=requests[0]['messages'][0]['content']
        contract=json.JSONDecoder().raw_decode(prompt[prompt.index('{"capabilities":'):])[0]
        command=next(c for c in contract['capabilities'] if c['command_id']=='axx.artifact.write')
        self.assertIn('relativa',command['parameters']['path']['description'])
        self.assertEqual(command['parameters']['path']['maxLength'],240)
        self.assertEqual(command['parameters']['content']['maxBytes'],65536)
        self.assertFalse((self.executor.workspace_root/'training.txt').exists())
        self.assertEqual(self.executor.list_operations(),[])

    def test_non_json_model_reply_can_be_repaired_without_executing_a_promise(self):
        requests=[]
        def answer(request):
            requests.append(request)
            content='Voy a hacerlo.' if len(requests)==1 else json.dumps({'title':'Consultar estado','steps':[{'command_id':'axx.system.telemetry','inputs':{}}]})
            return {'ok':True,'message':{'content':content}}
        self.model.route=answer
        plan=self.learning.propose('consulta el estado del equipo')
        self.assertEqual(plan['state'],'awaiting_approval')
        self.assertEqual(plan['model_calls_used'],2)
        self.assertEqual(plan['steps'],[{'command_id':'axx.system.telemetry','inputs':{}}])
        self.assertEqual(self.executor.list_operations(),[])

    def test_model_plan_writes_real_file_hashes_it_and_learns_only_after_execution(self):
        self.model.answer = {'title': 'Crear y comprobar saludo', 'steps': [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'saludo.txt', 'content': 'hola real'}},
            {'command_id': 'axx.file.sha256', 'inputs': {'path': str(self.executor.workspace_root / 'saludo.txt')}}]}
        plan = self.learning.propose('prepara un saludo y comprueba su hash')
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        self.assertEqual(self.learning.list_actions(), [])
        self.assertFalse((self.executor.workspace_root / 'saludo.txt').exists())
        with self.assertRaises(ApprovalRequired): self.learning.execute(plan['operation_id'])
        result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual((self.executor.workspace_root / 'saludo.txt').read_text(), 'hola real')
        self.assertEqual(result['results'][1]['evidence']['verification'], 'stable_file_sha256')
        self.assertEqual(len(self.learning.list_actions()), 1)
        self.assertEqual(self.commands.resolve('prepara un saludo y comprueba su hash')['match'], 'learned')
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['results'], result['results'])
        self.assertEqual(len(self.executor.list_operations()), 2)

    def test_learned_action_persists_and_repeats_without_a_model_call(self):
        plan = self.learning.propose('prepara un diagnóstico')
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'succeeded')
        self.learning.close()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        repeat = self.learning.propose('prepara un diagnóstico')
        self.assertEqual(repeat['model_calls_used'], 0)
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.learning.execute(repeat['operation_id'], True)['state'], 'succeeded')
        saved = self.learning.list_actions()[0]
        for phrase in (saved['id'], saved['title']):
            repeated = self.learning.propose(phrase)
            self.assertEqual(self.learning.execute(repeated['operation_id'], True)['state'], 'succeeded')
        self.assertEqual(len(self.learning.list_actions()), 1)
        self.assertEqual(self.model.calls, 1)

    def test_new_literal_content_is_not_replaced_by_a_case_folded_memory(self):
        plan = self.learning.propose('prepara Hola')
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'succeeded')
        self.assertIsNone(self.learning.find('prepara hola'))

    def test_local_cancel_remains_effective_if_provider_cancel_fails(self):
        plan = self.learning.propose('prepara diagnóstico cancelable')
        with patch.object(self.model, 'cancel', side_effect=RuntimeError('offline'), create=True):
            self.assertEqual(self.learning.cancel(plan['operation_id'])['state'], 'cancelled')
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'cancelled')
        self.assertEqual(self.executor.list_operations(), [])

    def test_model_cannot_invent_tools_run_shell_or_claim_evidence(self):
        for answer in (
            {'title': 'Fake', 'steps': [{'command_id': 'desktop_click_anything', 'inputs': {}}]},
            {'title': 'Shell', 'steps': [{'command_id': 'axx.shell.powershell', 'inputs': {'script': 'Write-Output NO'}}]},
            {'title': 'Claim', 'steps': [], 'state': 'succeeded'},
            {'title': 'Invalid', 'steps': [{'command_id': 'axx.artifact.write', 'inputs': {'path': '../escape', 'content': 'x'}}]},
        ):
            self.model.answer = answer
            plan = self.learning.propose('prepara algo nuevo')
            self.assertEqual(plan['state'], 'failed', plan)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.learning.list_actions(), [])

    def test_model_generated_cmd_requires_explicit_terminal_request_and_fresh_approval(self):
        self.model.answer = {'title': 'Ver estado', 'steps': [{'command_id': 'axx.shell.cmd',
                             'inputs': {'script': 'echo AXX_MODEL_CMD_OK'}}]}
        self.assertEqual(self.learning.propose('ver estado del sistema')['state'], 'failed')
        plan = self.learning.propose('usa CMD para ver el estado del sistema')
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        self.assertEqual(plan['steps'][0]['inputs']['script'], 'echo AXX_MODEL_CMD_OK')
        self.assertEqual(self.executor.list_operations(), [])
        with self.assertRaises(ApprovalRequired): self.learning.execute(plan['operation_id'])
        self.assertEqual(self.executor.list_operations(), [])
        result = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertIn('AXX_MODEL_CMD_OK', str(result['results'][0]['output']))
        self.assertEqual(self.learning.list_actions(), [])
        self.assertIsNone(result.get('learned_action_id'))
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_terminal_request_never_permits_powershell_or_saved_shell_recipe(self):
        self.model.answer = {'title': 'No permitido', 'steps': [{'command_id': 'axx.shell.powershell',
                             'inputs': {'script': 'Write-Output NO'}}]}
        self.assertEqual(self.learning.propose('usa CMD para ver el estado')['state'], 'failed')
        self.model.answer['steps'][0]['command_id'] = 'axx.shell.cmd'
        self.assertEqual(self.learning.propose('no uses CMD; dame el estado')['state'], 'failed')
        self.assertEqual(self.executor.list_operations(), [])

    def test_failure_stops_later_steps_and_does_not_learn(self):
        self.model.answer = {'title': 'No completar', 'steps': [
            {'command_id': 'axx.file.sha256', 'inputs': {'path': str(self.root / 'missing.txt')}},
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'unexpected.txt', 'content': 'x'}}]}
        plan = self.learning.propose('prepara una prueba incompleta')
        result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(self.learning.list_actions(), [])
        self.assertFalse((self.executor.workspace_root / 'unexpected.txt').exists())

    def test_cancel_during_model_response_blocks_late_execution(self):
        entered = threading.Event(); release = threading.Event()
        original = self.model.route
        def slow(request):
            entered.set(); release.wait(3); return original(request)
        result = []
        with patch.object(self.model, 'route', side_effect=slow):
            worker = threading.Thread(target=lambda: result.append(self.learning.propose('prepara diagnóstico', 'cancel-model')))
            worker.start(); self.assertTrue(entered.wait(3))
            self.learning.cancel('cancel-model'); release.set(); worker.join(5)
        self.assertEqual(result[0]['state'], 'cancelled')
        self.assertEqual(self.learning.execute('cancel-model', True)['state'], 'cancelled')
        self.assertEqual(self.executor.list_operations(), [])
