"""Real generated-code execution, durable linkage and independent file acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.action_learning import ActionLearning
from backend.commands import CommandService, ApprovalRequired
from backend.capability_workshop import CapabilityWorkshop
from backend.goal_contract import contract
from backend.tests.test_generated_commands import transform


class Model:
    config={'allow_paid':False}
    def __init__(self):
        self.calls=[];self.commands=None;self.text=' AXX  FUNCIONA ';self.path='entrega.txt';self.expected='axx funciona'
        self.change_goal=False
    def route(self,request):
        self.calls.append(request)
        goal=contract('normalizar y entregar')
        goal['checks']=[{'path':self.path,'text':self.expected}]
        active=[key for key,item in self.commands.commands.items() if key.startswith('axx.generated.') and item['execution_enabled']]
        if request['task']=='code':data=transform()
        elif not active:
            data={'goal_spec':goal,'capability_request':{'kind':'python_transform','goal':'Normalizar text: quitar espacios y minúsculas; devolver string puro.'}}
        else:
            data={'title':'Normalizar y entregar','steps':[
                {'command_id':active[0],'inputs':{'text':self.text}},
                {'command_id':'axx.artifact.write','inputs':{'path':self.path},'bindings':{'content':{'step':0,'path':['output','result']}}},
                {'command_id':'axx.file.sha256','inputs':{'path':str(self.commands.executor.workspace_root/self.path)}}]}
            if not any(call['task']=='code' for call in self.calls) or self.change_goal:data['goal_spec']=goal
        # Deterministic in-memory responses perform no HTTP, SDK or upstream
        # request. Costed dispatches are covered separately below.
        return {'ok':True,'message':{'content':json.dumps(data)},'route':{'model':'contract-fixture','provider_name':'offline',
            'upstream_attempts':0,'attempt_budget_used':0}}


class GoalCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.model=Model();self.open()
    def open(self):
        self.executor=ActionExecutor(self.root/'state.db',self.root/'artifacts')
        self.commands=CommandService(self.executor);self.model.commands=self.commands
        self.learning=ActionLearning(self.commands,self.model);self.commands.learning=self.learning
        self.workshop=CapabilityWorkshop(self.learning)
    def close(self):
        self.workshop.close();self.learning.close();self.commands.close();self.executor.close()
    def tearDown(self):self.close();self.temp.cleanup()
    def propose(self,key='goal-one'):
        return self.learning.propose('Normaliza estos datos y entrega el archivo',operation_id=key,conversation_id='task-chat')
    def activate(self,plan):
        ref=plan['capability_build']
        self.assertEqual(ref['status'],'review_required',plan)
        args=(ref['id'],ref['revision'],ref['digest'])
        self.workshop.approve(*args,confirmed=True)
        return self.workshop.activate(*args)

    def test_build_register_resume_execute_and_reuse_with_heldout_data(self):
        waiting=self.propose()
        self.assertEqual(waiting['state'],'waiting_capability',waiting)
        self.assertEqual(waiting['capability_build']['status'],'review_required',waiting)
        self.assertEqual([call['task'] for call in self.model.calls],['plan','code'])
        self.assertEqual(waiting['model_calls_used'],0)
        self.assertEqual(waiting['model_calls_confirmed'],0)
        self.assertEqual(waiting['route_requests'],2)
        self.assertTrue(self.workshop.get(waiting['capability_build']['id'])['validation']['self_tests_passed'])
        self.assertEqual(self.propose()['capability_build'],waiting['capability_build'])
        self.assertFalse((self.root/'artifacts/entrega.txt').exists())
        self.assertEqual(self.learning.resume(waiting['operation_id'])['state'],'waiting_capability')
        active=self.activate(waiting)
        resumed=self.learning.retry_waiting()[0]
        self.assertEqual(resumed['operation_id'],waiting['operation_id'])
        self.assertEqual(resumed['goal_spec'],waiting['goal_spec'])
        self.assertEqual(resumed['conversation_id'],'task-chat')
        self.assertEqual(resumed['state'],'awaiting_approval',resumed)
        self.assertIn(active['generated_command_id'],self.model.calls[-1]['messages'][1]['content'])
        with self.assertRaises(ApprovalRequired):self.learning.execute(resumed['operation_id'])
        done=self.learning.execute(resumed['operation_id'],approved=True)
        self.assertEqual(done['state'],'succeeded',done)
        self.assertTrue(done['goal_verification']['passed'])
        self.assertEqual((self.root/'artifacts/entrega.txt').read_text(),'axx funciona')
        self.assertEqual(self.learning.execute(done['operation_id'],True)['state'],'succeeded')
        self.model.text=' OTRO  DOCUMENTO ';self.model.path='otra-entrega.txt';self.model.expected='otro documento'
        second=self.propose('goal-heldout')
        self.assertEqual(second['state'],'awaiting_approval',second)
        result=self.learning.execute(second['operation_id'],True)
        self.assertEqual(result['state'],'succeeded',result)
        self.assertEqual((self.root/'artifacts/otra-entrega.txt').read_text(),'otro documento')
        self.assertEqual(sum(call['task']=='code' for call in self.model.calls),1)

    def test_tool_success_is_insufficient_when_final_file_disagrees(self):
        waiting=self.propose();self.activate(waiting)
        self.model.text=' WRONG VALUE '
        resumed=self.learning.resume(waiting['operation_id'])
        done=self.learning.execute(resumed['operation_id'],True)
        self.assertEqual(done['state'],'failed',done)
        self.assertTrue(all(row['state']=='succeeded' for row in done['step_records']))
        self.assertFalse(done['goal_verification']['passed'])
        self.assertEqual((self.root/'artifacts/entrega.txt').read_text(),'wrong value')

    def test_waiting_goal_survives_restart_and_keeps_exact_build_revision(self):
        waiting=self.propose();self.close();self.open()
        restored=self.learning.get(waiting['operation_id'])
        self.assertEqual(restored['state'],'waiting_capability')
        self.assertEqual(restored['capability_build'],waiting['capability_build'])
        self.activate(restored)
        resumed=self.learning.resume(restored['operation_id'])
        self.assertEqual(resumed['state'],'awaiting_approval',resumed)

    def test_candidate_or_model_cannot_weaken_the_original_contract(self):
        waiting=self.propose();self.activate(waiting)
        self.model.change_goal=True;self.model.expected='different'
        resumed=self.learning.resume(waiting['operation_id'])
        self.assertEqual([call['task'] for call in self.model.calls],['plan','code','plan'])
        self.assertEqual(resumed['state'],'failed',resumed)
        self.assertIn('intentó cambiar el contrato durante la construcción',resumed['message'])
        self.assertEqual(resumed['goal_spec'],waiting['goal_spec'])
        self.assertEqual(resumed['goal_revision'],waiting['goal_revision'])
        self.assertEqual(resumed['operation_id'],waiting['operation_id'])
        self.assertEqual(resumed['conversation_id'],waiting['conversation_id'])
        self.assertFalse((self.root/'artifacts/entrega.txt').exists())
        self.assertEqual(self.commands.operations(),[])
        self.assertEqual(self.executor.list_operations(),[])

    def test_costed_plan_and_build_stop_before_third_dispatch_without_losing_goal_or_capability(self):
        original=self.model.route
        def costed(request):
            response=original(request)
            response['route'].update(upstream_attempts=1,attempt_budget_used=1)
            return response
        with patch.object(self.model,'route',side_effect=costed):
            waiting=self.propose('costed-goal')
            goal=copy.deepcopy(waiting['goal_spec'])
            reference=copy.deepcopy(waiting['capability_build'])
            self.assertEqual([call['task'] for call in self.model.calls],['plan','code'])
            self.assertEqual(waiting['model_call_limit'],2)
            self.assertEqual(waiting['model_calls_used'],2)
            self.assertEqual(waiting['model_calls_confirmed'],2)
            self.assertEqual(waiting['route_requests'],2)
            active=self.activate(waiting)
            resumed=self.learning.resume(waiting['operation_id'])
        self.assertEqual(resumed['state'],'failed',resumed)
        resumed=self.learning.get(waiting['operation_id'])
        self.assertEqual(resumed['state'],'failed',resumed)
        self.assertIn('presupuesto de 2 inferencias',resumed['message'])
        self.assertEqual([call['task'] for call in self.model.calls],['plan','code'])
        self.assertEqual(resumed['model_calls_used'],2)
        self.assertEqual(resumed['model_calls_confirmed'],2)
        self.assertEqual(resumed['model_calls_reserved'],0)
        self.assertEqual(resumed['model_calls_uncertain'],0)
        self.assertEqual(resumed['route_requests'],2)
        self.assertEqual(resumed['operation_id'],waiting['operation_id'])
        self.assertEqual(resumed['conversation_id'],waiting['conversation_id'])
        self.assertEqual(resumed['goal_spec'],goal)
        self.assertEqual(resumed['goal_revision'],waiting['goal_revision'])
        self.assertEqual({key:resumed['capability_build'][key] for key in ('id','revision','digest','goal_revision')},
                         {key:reference[key] for key in ('id','revision','digest','goal_revision')})
        self.assertEqual(resumed['capability_build']['status'],'available')
        capability=self.workshop.get(active['id'])
        self.assertEqual(capability['state'],'active')
        self.assertEqual(capability['active_revision'],reference['revision'])
        self.assertTrue(self.commands.commands[active['generated_command_id']]['execution_enabled'])
        self.assertIsNone(resumed.get('approved_hash'))
        self.assertFalse(resumed['postconditions_passed'])
        self.assertFalse(resumed['mission']['completed'])
        self.assertFalse((self.root/'artifacts/entrega.txt').exists())
        self.assertEqual(self.commands.operations(),[])
        self.assertEqual(self.executor.list_operations(),[])

    def test_cancellation_and_replaced_build_never_resume_effects(self):
        waiting=self.propose();active=self.activate(waiting)
        self.workshop.revoke(active['id'],active['revision'],active['digest'])
        self.assertEqual(self.learning.retry_waiting(),[])
        cancelled=self.learning.cancel(waiting['operation_id'])
        self.assertEqual(cancelled['state'],'cancelled')
        self.assertEqual(self.learning.resume(waiting['operation_id'])['state'],'cancelled')
        self.assertEqual(self.commands.operations(),[])

    def test_contract_rejects_escape_and_candidate_control_fields(self):
        for path in ('../private.txt','C:\\private.txt','/tmp/private.txt'):
            goal=contract('x');goal['checks']=[{'path':path,'text':'secret'}]
            with self.subTest(path=path),self.assertRaises(ValueError):contract('x',goal)
        goal=contract('x');goal['approval']=True
        with self.assertRaises(ValueError):contract('x',goal)
        with self.assertRaises(ValueError):contract('x',{})

    def test_selected_codex_plans_and_builds_without_provider_fallback(self):
        class Codex:
            def __init__(self,model):self.model=model;self.requests=[]
            def generate_plan(self,request):return self.generate_capability(request)
            def generate_capability(self,request):
                self.requests.append(request)
                return self.model.route(request)
        codex=Codex(self.model);self.workshop.provider=codex
        plan=self.learning.propose('Normaliza y conserva una transformación',model='configured-model',provider_name='@codex')
        self.assertEqual(plan['state'],'waiting_capability',plan)
        self.assertEqual([row['task'] for row in codex.requests],['plan','code'])
        self.assertEqual(plan['capability_build']['status'],'review_required',plan)
        self.assertEqual(plan['model_calls_used'],0)
        self.assertEqual(plan['model_calls_confirmed'],0)
        self.assertEqual(plan['route_requests'],2)
        self.assertTrue(all(row['allow_paid'] is False and row['model']=='configured-model' for row in codex.requests))
        self.assertEqual(len(self.model.calls),2)

    def test_failed_generation_has_one_explicit_retry_and_keeps_the_goal(self):
        with patch.object(self.workshop,'generate',side_effect=ValueError('immutable input boundary')) as generate:
            first=self.propose();second=self.learning.resume(first['operation_id'])
            third=self.learning.resume(first['operation_id'])
        self.assertEqual(generate.call_count,2)
        self.assertTrue(all(call.kwargs['max_attempts'] == 1 for call in generate.call_args_list))
        self.assertEqual(second['goal_spec'],first['goal_spec'])
        self.assertEqual(third['capability_build']['attempt'],2)
        self.assertEqual(self.commands.operations(),[])
        self.assertIn('immutable input boundary',generate.call_args.args[0])

    def test_repaired_candidate_requires_an_explicit_compatible_binding(self):
        waiting=self.propose();ref=waiting['capability_build']
        definition=self.workshop.get(ref['id'])['definition']
        definition['source']+='\n'
        revised=self.workshop.revise(ref['id'],ref['revision'],ref['digest'],definition)
        args=(revised['id'],revised['revision'],revised['digest'])
        self.workshop.validate(*args);self.workshop.approve(*args,confirmed=True);self.workshop.activate(*args)
        self.assertEqual(self.learning.resume(waiting['operation_id'])['state'],'waiting_capability')
        with self.assertRaises(ValueError):self.learning.bind_capability(waiting['operation_id'],*args,goal_revision=2)
        rebound=self.learning.bind_capability(waiting['operation_id'],*args,goal_revision=1)
        self.assertEqual(rebound['goal_spec'],waiting['goal_spec'])
        resumed=self.learning.resume(waiting['operation_id'])
        self.assertEqual(resumed['state'],'awaiting_approval',resumed)


if __name__=='__main__':unittest.main()
