"""Mission-scoped inference accounting uses one real SQLite ledger, without provider traffic."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from backend.action_learning import ActionLearning, CapacityPending, ModelBudgetExceeded
from backend.actions.executor import ActionExecutor
from backend.capability_workshop import CapabilityWorkshop
from backend.commands import CommandService


class Model:
    config={'allow_paid':False}
    def __init__(self): self.calls=[]; self.responses=[]
    def route(self, request):
        self.calls.append(copy.deepcopy(request))
        response=self.responses.pop(0) if self.responses else {'ok':True,'message':{'content':'{}'},'route':{'upstream_attempts':1,'attempt_budget_used':1}}
        if isinstance(response,BaseException): raise response
        return response


class Policy:
    limit=2
    def budget_for_task(self, task_id, project_id=''):
        return {'model_call_limit':self.limit}


class MissionModelBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.executor=ActionExecutor(self.root/'state.db',self.root/'artifacts')
        self.commands=CommandService(self.executor);self.model=Model();self.learning=ActionLearning(self.commands,self.model)
        self.policy=Policy();self.learning.anticipation=self.policy

    def tearDown(self):
        if self.learning.workshop:self.learning.workshop.close()
        self.learning.close();self.commands.close();self.executor.close();self.temp.cleanup()

    def plan(self, key='budget-mission', learning=None):
        learning=learning or self.learning
        plan,_=learning._new_plan('Explicit budget trial',key,{},'project-a')
        plan.update(conversation_id='task-a',planning_settings={'provider_name':'','model':'','selection_mode':'manual'})
        return learning._save(plan)

    def call(self, plan, learning=None):return (learning or self.learning)._infer(plan,'plan',[])

    def test_zero_budget_dispatches_nothing_and_increasing_policy_never_raises_old_mission(self):
        self.policy.limit=0
        plan=self.plan()
        with self.assertRaises(ModelBudgetExceeded):self.call(plan)
        self.assertEqual(self.model.calls,[])
        saved=self.learning.get(plan['operation_id']);self.assertEqual(saved['mission']['budget']['model_call_limit'],0)
        self.assertFalse(saved['mission']['completed'])
        self.policy.limit=2
        with self.assertRaises(ModelBudgetExceeded):self.call(saved)
        self.call(self.plan('fresh-mission'))
        self.assertEqual(len(self.model.calls),1);self.assertEqual(self.model.calls[0]['upstream_attempt_budget'],2)

    def test_authoritative_zero_refunds_but_busy_or_missing_or_inconsistent_counts_hold_budget(self):
        plan=self.plan()
        self.model.responses=[{'ok':False,'error':{'retryable':True,'upstream_attempts':0,'attempt_budget_used':0}}]
        with self.assertRaises(CapacityPending):self.call(plan)
        self.assertEqual(self.learning.get(plan['operation_id'])['model_calls_used'],0)
        self.model.responses=[{'ok':False,'error':{'code':'BUSY','retryable':True}}]
        with self.assertRaises(ValueError):self.call(plan)
        saved=self.learning.get(plan['operation_id']);self.assertEqual(saved['model_calls_used'],2);self.assertEqual(saved['model_calls_uncertain'],2)
        inconsistent=self.plan('inconsistent-mission')
        self.model.responses=[{'ok':False,'error':{'retryable':True,'upstream_attempted':False,'upstream_attempts':1,'attempt_budget_used':1}}]
        with self.assertRaises(ValueError):self.call(inconsistent)
        self.assertEqual(self.learning.get(plan['operation_id'])['model_calls_used'],2)
        self.assertEqual(self.learning.get(inconsistent['operation_id'])['model_calls_uncertain'],2)
        with self.assertRaises(ModelBudgetExceeded):self.call(saved)
        self.assertEqual(len(self.model.calls),3)

    def test_unknown_exception_and_restart_keep_reservation_without_claiming_confirmed_spend(self):
        plan=self.plan();self.model.responses=[RuntimeError('Unknown transport result')]
        with self.assertRaises(RuntimeError):self.call(plan)
        self.learning.close();self.learning=ActionLearning(self.commands,self.model);self.learning.anticipation=self.policy
        saved=self.learning.get(plan['operation_id'])
        self.assertEqual(saved['model_calls_used'],2);self.assertEqual(saved['model_calls_confirmed'],0);self.assertEqual(saved['model_calls_uncertain'],2)
        with self.assertRaises(ModelBudgetExceeded):self.call(saved)
        self.assertEqual(len(self.model.calls),1)

    def test_atomic_reservations_across_two_service_instances_and_stale_plan_saves(self):
        self.policy.limit=1;plan=self.plan()
        other=ActionLearning(self.commands,self.model);other.anticipation=self.policy
        try:
            clones=[copy.deepcopy(plan),copy.deepcopy(plan)];barrier=threading.Barrier(2);admitted=[];errors=[]
            def reserve(index,service):
                try:barrier.wait(3);service._reserve_model_call(clones[index],'race-'+str(index),'plan');admitted.append(index)
                except ModelBudgetExceeded:errors.append(index)
            threads=[threading.Thread(target=reserve,args=(0,self.learning)),threading.Thread(target=reserve,args=(1,other))]
            for worker in threads:worker.start()
            for worker in threads:worker.join(5);self.assertFalse(worker.is_alive())
            self.assertEqual(len(admitted),1);self.assertEqual(len(errors),1)
            self.learning._save(copy.deepcopy(plan));other._save(copy.deepcopy(plan))
            saved=self.learning.get(plan['operation_id'])
            self.assertEqual(saved['model_calls_used'],1);self.assertEqual(saved['model_calls_reserved'],1);self.assertEqual(saved['model_calls_confirmed'],0)
            with self.assertRaises(ModelBudgetExceeded):self.call(saved)
        finally:other.close()

    def test_reduced_limit_survives_stale_save_and_resource_denial_reserves_nothing(self):
        plan=self.plan();stale=copy.deepcopy(plan);self.policy.limit=1
        self.assertEqual(self.learning.get(plan['operation_id'])['model_call_limit'],1)
        self.policy.limit=2;self.learning._save(stale)
        self.assertEqual(self.learning.get(plan['operation_id'])['model_call_limit'],1)
        def deny(*args,**kwargs):raise ValueError('MEMORY_ADMISSION_UNKNOWN')
        self.policy.assert_resource_admission=deny
        with self.assertRaisesRegex(ValueError,'MEMORY_ADMISSION_UNKNOWN'):self.call(plan)
        self.assertEqual(self.model.calls,[])
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM mission_model_calls').fetchone()[0],0)
        del self.policy.assert_resource_admission
        self.call(plan)
        with self.assertRaises(ModelBudgetExceeded):self.call(plan)

    def test_planner_and_child_workshop_share_two_calls_and_child_has_one_upstream_attempt(self):
        workshop=CapabilityWorkshop(self.learning)
        proposal={'kind':'source_proposal','title':'Manual integration reference','objective':'Explicit task','language':'python','source':'print("unexecuted")','readme':'Reference for manual review'}
        self.model.responses=[{'ok':True,'message':{'content':json.dumps({'capability_request':{'kind':'source_proposal','goal':'Prepare manual integration reference'}})},'route':{'upstream_attempts':1,'attempt_budget_used':1}}, {'ok':True,'message':{'content':json.dumps(proposal)},'route':{'upstream_attempts':1,'attempt_budget_used':1}}]
        plan=self.learning.propose('Prepare bounded missing capability',project_id='project-a',conversation_id='task-a')
        self.assertEqual(len(self.model.calls),2)
        self.assertEqual([request['upstream_attempt_budget'] for request in self.model.calls],[2,1])
        self.assertEqual(plan['model_calls_used'],2);self.assertEqual(plan['model_calls_confirmed'],2)
        self.assertEqual(plan['inference_counts'],{'plan':1,'capability_build':1})
        self.assertEqual(plan['capability_build']['status'],'review_required',plan)
        self.assertFalse(plan['mission']['completed']);self.assertEqual(self.commands.operations(),[])
        self.assertEqual(len(workshop.list()),1)
        with self.assertRaises(ModelBudgetExceeded):self.call(plan)

    def test_one_call_budget_blocks_child_workshop_before_dispatch_and_keeps_goal(self):
        CapabilityWorkshop(self.learning);self.policy.limit=1
        self.model.responses=[{'ok':True,'message':{'content':json.dumps({'capability_request':{'kind':'source_proposal','goal':'Needs explicit implementation'}})}}]
        plan=self.learning.propose('Retain this mission',project_id='project-a',conversation_id='task-a')
        self.assertEqual(len(self.model.calls),1);self.assertEqual(plan['model_calls_used'],1)
        self.assertEqual(plan['capability_build']['status'],'failed');self.assertIn('presupuesto',plan['capability_build']['error'])
        self.assertEqual(plan['request'],'Retain this mission');self.assertFalse(plan['mission']['completed']);self.assertEqual(self.commands.operations(),[])

    def test_direct_workshop_keeps_two_proposal_attempts_without_using_an_unrelated_mission(self):
        workshop=CapabilityWorkshop(self.learning)
        proposal={'kind':'source_proposal','title':'Manual reference','objective':'Manual work','language':'python','source':'pass','readme':'Review only'}
        self.model.responses=[{'ok':True,'message':{'content':'bad JSON'},'route':{'upstream_attempts':1,'attempt_budget_used':1}},{'ok':True,'message':{'content':json.dumps(proposal)},'route':{'upstream_attempts':1,'attempt_budget_used':1}}]
        item=workshop.generate('Prepare a manual reference',kind='source_proposal')
        self.assertEqual(len(self.model.calls),2);self.assertEqual(item['provenance']['generation_attempts'],2)
        self.assertEqual([request['upstream_attempt_budget'] for request in self.model.calls],[2,1])
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM mission_model_calls').fetchone()[0],0)

    def test_owned_gateway_two_unit_bound_can_prepare_and_complete_without_another_inference(self):
        self.model.responses=[{'ok':True,'route':{'upstream_attempts':1,'attempt_budget_used':2},'message':{'content':json.dumps({'title':'Local receipt','steps':[{'command_id':'axx.system.telemetry','inputs':{}}]})}}]
        plan=self.learning.propose('Read the local system',conversation_id='task-a')
        self.assertEqual(plan['state'],'awaiting_approval',plan)
        self.assertEqual(plan['model_calls_used'],2);self.assertEqual(len(self.model.calls),1)
        self.assertEqual(self.model.calls[0]['upstream_attempt_budget'],2)
        done=self.learning.execute(plan['operation_id'],approved=True)
        self.assertTrue(done['mission']['completed'],done)
        self.assertEqual(len(self.model.calls),1)
        self.assertFalse(done['mission']['budget']['provider_internal_calls_known'])

    def test_standalone_gateway_bound_and_unknown_response_never_get_a_second_attempt(self):
        workshop=CapabilityWorkshop(self.learning)
        for metadata in ({'upstream_attempts':1,'attempt_budget_used':2},{}):
            self.model.calls=[];self.model.responses=[{'ok':True,'route':metadata,'message':{'content':'invalid JSON'}}]
            with self.assertRaises(ValueError):workshop.generate('Prepare manual proposal',kind='source_proposal')
            self.assertEqual(len(self.model.calls),1)

    def test_codex_single_observable_request_never_reads_unrelated_adapter_config(self):
        class PrivateAdapter:
            @property
            def config(self):raise AssertionError('Codex must not read unrelated private adapter configuration')
        class Codex:
            def __init__(self):self.calls=[]
            def generate_plan(self,request):self.calls.append(request);return {'ok':True,'message':{'content':'{}'},'route':{'provider_name':'@codex'}}
            def generate_capability(self,request):
                self.calls.append(request)
                return {'ok':True,'message':{'content':json.dumps({'kind':'source_proposal','title':'Codex proposal','objective':'Manual reference','language':'python','source':'pass','readme':'Manual review'})},'route':{'provider_name':'@codex'}}
        self.learning.adapter=PrivateAdapter();workshop=CapabilityWorkshop(self.learning);provider=Codex();workshop.provider=provider
        plan=self.plan();plan['planning_settings'].update(provider_name='@codex',model='chosen')
        self.learning._infer(plan,'plan',[{'role':'system','content':'Contract'},{'role':'user','content':'Goal'}])
        workshop.generate('Manual Codex proposal',kind='source_proposal',provider_name='@codex',model='chosen',_budget=self.learning._mission_model_callback(plan,'capability_build',single_request=True))
        saved=self.learning.get(plan['operation_id'])
        self.assertEqual(saved['model_calls_used'],2);self.assertEqual(saved['model_calls_confirmed'],2)
        self.assertEqual(len(provider.calls),2)
        self.assertTrue(all(request['upstream_attempt_budget']==1 for request in provider.calls))

    def test_refunded_zero_history_is_bounded_without_losing_holds_or_request_total(self):
        plan=self.plan()
        with self.learning.budget_db:
            self.learning.budget_db.executemany('''INSERT INTO mission_model_calls
                (plan_id,request_id,kind,state,charge,confirmed,created_at,settled_at) VALUES (?,?,?,?,?,?,?,?)''',
                ((plan['operation_id'],'zero-'+str(i),'plan','refunded',0,0,float(i),float(i)) for i in range(200)))
        self.learning._reserve_model_call(plan,'persistent-hold','plan')
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM mission_model_calls').fetchone()[0],129)
        saved=self.learning.get(plan['operation_id'])
        self.assertEqual(saved['route_requests'],201)
        self.assertEqual(saved['model_calls_reserved'],2)
        self.assertEqual(saved['model_calls_confirmed'],0)
        self.assertEqual(saved['inference_counts'],{'plan':2},'Two hundred zero-cost tickets cannot increase inference counts')
        legacy=self.learning.db.execute('SELECT legacy_used,legacy_requests,legacy_counts FROM mission_model_budgets WHERE plan_id=?',(plan['operation_id'],)).fetchone()
        self.assertEqual(legacy,(0,72,'{}'),'Compaction changes only the zero-ticket request total')
        with self.assertRaises(ModelBudgetExceeded):self.call(saved)


if __name__=='__main__':unittest.main()
