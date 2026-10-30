"""Explicit revalidation uses disposable files and the real command/executor journals."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.actions.tools import get_tool
from backend.commands import ApprovalRequired, CommandService
from backend.memory.procedural_memory import get_action_env_fingerprint
from backend.memory.skill_memory import NeedsInput, validate_schema


class NoInference:
    def route(self, request):
        raise AssertionError('Revalidation must never invoke a provider')


class RevalidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, NoInference())
        self.file = self.executor.workspace_root / 'source.txt'
        self.file.write_text('Synthetic revalidation fixture', encoding='utf-8')

    def tearDown(self):
        self.learning.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    def skill(self, key='trial.hash', version=1, *, command='axx.file.sha256', dependencies=None, inference=None):
        writer = command == 'axx.artifact.write'
        inputs = {'path': '{{path}}', **({'content': '{{content}}'} if writer else {})}
        schema = {'type':'object','properties':{'path':{'type':'string','default':str(self.file)}, **({'content':{'type':'string'}} if writer else {})},'required':['path', *(['content'] if writer else [])]}
        return self.learning.skills.insert({'id':key,'version':version,'trigger':key,'title':key,
            'templates':[{'command_id':command,'inputs':inputs}], 'schema':validate_schema(schema),'examples':[],
            'project_id':'project-a','favorite':False,'checks':['executor_postconditions'],'executable':True,
            'environment':get_action_env_fingerprint([command]),'created_at':time.time(),'provenance':{},
            'context_dependencies':dependencies or [],'inference':inference})

    def receipt(self, *, fail=False):
        if not self.file.exists(): self.file.write_text('Synthetic revalidation fixture', encoding='utf-8')
        prepared = self.commands.prepare('axx.file.sha256', {'path':str(self.file)}, conversation_id='task-a')
        if fail: self.file.unlink()
        return self.commands.execute(prepared['operation_id'], approved=True)

    def record(self, receipt, key='trial.hash', version=1):
        self.learning.skills.record(key, version, receipt['operation_id'], {'effect_verified':receipt['state']=='succeeded',
            'results':[receipt],'inputs':{'path':str(self.file)},'task_id':'task-a'})

    def prepare(self, key='trial.hash', version=1, inputs=None, operation_id=None):
        return self.learning.prepare_revalidation(key, version, inputs if inputs is not None else {'path':str(self.file)},
            project_id='project-a', conversation_id='task-a', operation_id=operation_id)

    def test_real_failure_quarantines_and_explicit_trial_recovers_only_exact_version(self):
        self.skill(); self.skill(version=2)
        failed = self.receipt(fail=True)
        self.assertEqual(failed['state'], 'failed', failed)
        self.record(failed); self.record(failed, version=2)
        self.assertTrue(self.learning.skills.get('trial.hash',1)['quarantined'])
        self.file.write_text('Fresh fixture', encoding='utf-8')
        before = len(self.commands.operations())
        context = self.learning.context('project-a')
        definitions = self.learning.db.execute('SELECT id,version,payload FROM skill_versions ORDER BY version').fetchall()
        plan = self.prepare(operation_id='explicit-trial')
        self.assertEqual(plan['state'],'awaiting_approval',plan)
        self.assertEqual(plan['revalidation'],{'id':'trial.hash','version':1})
        self.assertEqual(plan['model_calls_used'],0)
        self.assertEqual(len(self.commands.operations()), before)
        self.assertEqual(self.prepare(operation_id='explicit-trial')['plan_hash'],plan['plan_hash'])
        with self.assertRaises(ApprovalRequired): self.learning.execute(plan['operation_id'])
        completed = self.learning.execute(plan['operation_id'],approved=True)
        self.assertTrue(completed['revalidation_completed'],completed)
        self.assertIsNone(completed['learned_action_id'])
        self.assertTrue(self.learning.skills.get('trial.hash',1)['environment_matches'])
        self.assertTrue(self.learning.skills.get('trial.hash',2)['quarantined'])
        self.assertEqual(self.learning.context('project-a'),context,'A trial cannot become last skill, context preference or habit')
        self.assertEqual(self.learning.db.execute('SELECT id,version,payload FROM skill_versions ORDER BY version').fetchall(),definitions)
        evidence=json.loads(self.learning.db.execute('SELECT payload FROM skill_evidence WHERE id=? AND version=? AND operation_id=?',('trial.hash',1,plan['operation_id'])).fetchone()[0])
        self.assertTrue(evidence['revalidation']); self.assertEqual(evidence['observed_outcome'],'succeeded')
        self.assertFalse(self.learning.skills.get('trial.hash',1)['goal_confirmed'])

    def test_changed_adapter_is_selective_and_trial_adopts_only_its_real_environment(self):
        self.skill(); self.record(self.receipt())
        self.skill('other.writer',command='axx.artifact.write')
        writer_before=self.learning.skills.get('other.writer')['environment_matches']
        tool=get_tool('file_inspection')
        definition=self.learning.db.execute('SELECT payload FROM skill_versions WHERE id=?',('trial.hash',)).fetchone()[0]
        with patch.object(tool,'version',str(tool.version)+'.trial'):
            self.assertFalse(self.learning.skills.get('trial.hash')['environment_matches'])
            self.assertEqual(self.learning.skills.get('other.writer')['environment_matches'],writer_before)
            result=self.learning.execute(self.prepare()['operation_id'],approved=True)
            self.assertTrue(result['revalidation_completed'],result)
            self.assertTrue(self.learning.skills.get('trial.hash')['environment_matches'])
            self.assertEqual(self.learning.skills.get('other.writer')['environment_matches'],writer_before)
        self.assertEqual(self.learning.db.execute('SELECT payload FROM skill_versions WHERE id=?',('trial.hash',)).fetchone()[0],definition)

    def test_missing_stale_defaults_outside_workspace_and_bad_versions_never_prepare_effects(self):
        self.skill(); self.learning.update_context('project-a',{'defaults':{'path':str(self.file)}})
        with self.assertRaises(NeedsInput): self.prepare(inputs={})
        plan=self.prepare()
        self.assertEqual(plan['operational_context']['context_meta'],{})
        self.assertEqual(plan['operational_context'].get('defaults'),{},'A trial cannot retain unrelated defaults')
        self.assertNotIn(str(self.file),json.dumps(plan['operational_context']),'A trial cannot retain unrelated context values')
        outside=self.root/'outside.txt'; outside.write_text('Outside disposable scope',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'fuera del espacio de ensayo'): self.prepare(inputs={'path':str(outside)})
        with self.assertRaises(ValueError): self.prepare(version=True)
        self.skill('trial.writer',command='axx.artifact.write')
        with self.assertRaises(ValueError): self.prepare('trial.writer',inputs={'path':'../outside.txt','content':'unapproved'})
        self.assertEqual(outside.read_text(),'Outside disposable scope')
        self.assertEqual(self.commands.operations(),[])
        self.assertEqual(self.executor.list_operations(),[])

    def test_inference_and_generated_or_input_templates_are_not_revalidation_capabilities(self):
        self.skill(inference={'task':'writing','prompt':'secret prompt','output_parameter':'path'})
        with self.assertRaises(ValueError): self.prepare()
        self.skill('workshop.cap.synthetic')
        with self.assertRaises(ValueError): self.prepare('workshop.cap.synthetic')
        self.skill('trial.ui',command='axx.desktop.window.read')
        with self.assertRaises(ValueError): self.prepare('trial.ui')
        self.assertEqual(self.commands.operations(),[])

    def test_stale_context_requires_new_reviewed_version_and_never_inherits_old_evidence(self):
        context=self.learning.update_context('project-a',{'current_file':str(self.file),'context_meta':{'current_file':{'kind':'confirmed_user','task_id':'task-a','source_id':'manual-file'}}})
        oldref={'project_id':'project-a','field':'current_file','revision':context['context_meta']['current_file']['revision']}
        self.skill(dependencies=[oldref]); self.record(self.receipt())
        newcontext=self.learning.update_context('project-a',{'current_file':str(self.file),'context_meta':{'current_file':{'kind':'confirmed_user','task_id':'task-a','source_id':'manual-file'}}})
        with self.assertRaises(NeedsInput): self.prepare()
        newref=oldref|{'revision':newcontext['context_meta']['current_file']['revision']}
        with self.assertRaisesRegex(ValueError,'borrar ni trasladar'): self.learning.configure('trial.hash',{'version':1,'context_dependencies':[]})
        with self.assertRaises(ValueError): self.learning.configure('trial.hash',{'version':1,'context_dependencies':[newref|{'project_id':'foreign'}]})
        version=self.learning.configure('trial.hash',{'version':1,'context_dependencies':[newref]})
        self.assertEqual(version['version'],2); self.assertFalse(version['effect_verified'])
        self.assertEqual(self.learning.skills.get('trial.hash',1)['context_dependencies'],[oldref])
        completed=self.learning.execute(self.prepare(version=2)['operation_id'],approved=True)
        self.assertTrue(completed['revalidation_completed'],completed)
        self.assertFalse(self.learning.skills.get('trial.hash',1,project_id='project-a',task_id='task-a')['context_matches'])

    def test_adapter_or_context_change_after_review_blocks_effects_and_legacy_hash_stays_identical(self):
        self.skill(); plan=self.prepare()
        plain=self.learning.prepare_steps('Consultar archivo de ensayo',[{'command_id':'axx.file.sha256','inputs':{'path':str(self.file)}}],project_id='project-a',conversation_id='task-a')
        legacy_hash=self.learning._hash({'steps':plain['steps'],'skill_versions':plain['skill_versions'],'project_id':'project-a','dependencies':plain['dependencies'],'identities':[{key:row[key] for key in ('step_id','operation_id','input_hash')} for row in plain['step_records']],'goal_spec':plain['goal_spec'],'goal_revision':plain['goal_revision']})
        self.assertEqual(plain['approval_version'],2)
        self.assertNotEqual(plain['plan_hash'],legacy_hash)
        legacy=copy.deepcopy(plain);legacy.pop('approval_version');legacy['plan_hash']=legacy_hash
        self.assertEqual(self.learning._plan_hash(legacy),legacy_hash)
        self.assertEqual(self.learning._records(legacy),legacy['step_records'])
        changed=copy.deepcopy(plan); changed['revalidation']['version']=2
        self.assertNotEqual(self.learning._plan_hash(changed),plan['plan_hash'])
        tool=get_tool('file_inspection')
        with patch.object(tool,'version',str(tool.version)+'.changed-after-review'):
            result=self.learning.execute(plan['operation_id'],approved=True)
            self.assertEqual(result['state'],'failed',result)
        self.assertEqual(self.commands.operations(),[])

    def test_fabricated_receipts_and_failed_trials_cannot_recover_health(self):
        self.skill(); failed=self.receipt(fail=True); self.record(failed)
        self.file.write_text('Current fixture',encoding='utf-8')
        trial=self.prepare(); fake=copy.deepcopy(trial)
        fake['step_records'][0]['result']={'operation_id':'nonexistent','command_id':'axx.file.sha256','inputs':{'path':str(self.file)},'state':'succeeded','postconditions_passed':True,'evidence':{'untrusted':True}}
        result=self.learning._learn(fake)
        self.assertFalse(result['effect_verified']); self.assertFalse(result['revalidation_completed'])
        self.assertTrue(self.learning.skills.get('trial.hash')['quarantined'])
        actual=self.prepare()
        with patch('backend.actions.file_inspection.hash_file',side_effect=OSError('Controlled local inspection failure')):
            result=self.learning.execute(actual['operation_id'],approved=True)
        self.assertEqual(result['state'],'failed',result)
        self.assertTrue(self.learning.skills.get('trial.hash')['quarantined'])
        self.assertTrue(any(row['state']=='failed' for row in self.commands.operations()))
        renamed=self.learning.configure('trial.hash',{'version':1,'title':'Explicitly renamed'})
        self.assertFalse(renamed['effect_verified'],'Renaming cannot inherit health from a quarantined version')

    def test_writer_trial_creates_only_reviewed_new_copy_and_replays_no_effect(self):
        self.skill('trial.writer',command='axx.artifact.write')
        inputs={'path':r'nested\explicit-copy.txt','content':'New reviewed copy'}
        plan=self.prepare('trial.writer',inputs=inputs,operation_id='writer-trial')
        target=self.executor.workspace_root/Path(*inputs['path'].replace('\\','/').split('/'))
        self.assertFalse(target.exists())
        result=self.learning.execute(plan['operation_id'],approved=True)
        self.assertTrue(result['revalidation_completed'],result)
        self.assertEqual(target.read_text(encoding='utf-8'),inputs['content'])
        count=len(self.executor.list_operations())
        self.assertEqual(self.prepare('trial.writer',inputs=inputs,operation_id='writer-trial')['state'],'succeeded')
        self.assertEqual(self.learning.execute(plan['operation_id'],approved=True)['state'],'succeeded')
        self.assertEqual(len(self.executor.list_operations()),count)
        with self.assertRaises(ValueError): self.prepare('trial.writer',inputs=inputs)

    def test_trial_repair_never_routes_to_provider_or_changes_immutable_parameters(self):
        self.skill(); plan=self.prepare()
        with self.assertRaises(NeedsInput): self.learning.repair(plan['operation_id'],'Use another file')
        current=self.learning.get(plan['operation_id'])
        self.assertEqual(current['plan_hash'],plan['plan_hash'])
        self.assertEqual(current['steps'],plan['steps'])
        self.assertEqual(self.commands.operations(),[])

    def test_bound_chain_records_trial_evidence_without_creating_another_skill(self):
        self.skill('trial.chain',command='axx.artifact.write')
        original=json.loads(self.learning.db.execute('SELECT payload FROM skill_versions WHERE id=?',('trial.chain',)).fetchone()[0])
        chain=original|{'version':2,'templates':[
            {'command_id':'axx.artifact.write','inputs':{'path':'{{path}}','content':'{{content}}'}},
            {'command_id':'axx.file.sha256','inputs':{},'bindings':{'path':{'step':0,'path':['output','path']}}}],
            'environment':get_action_env_fingerprint(['axx.artifact.write','axx.file.sha256'])}
        self.learning.skills.insert(chain)
        count=self.learning.db.execute('SELECT COUNT(*) FROM skill_versions').fetchone()[0]
        plan=self.prepare('trial.chain',version=2,inputs={'path':'bound-copy.txt','content':'Reviewed chain'})
        result=self.learning.execute(plan['operation_id'],approved=True)
        self.assertTrue(result['revalidation_completed'],result)
        self.assertEqual(len(result['step_records']),2)
        self.assertTrue(all(row['result']['postconditions_passed'] for row in result['step_records']))
        self.assertIsNone(result['learned_action_id'])
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM skill_versions').fetchone()[0],count)
        self.assertTrue(self.learning.skills.get('trial.chain',2)['effect_verified'])
        self.assertFalse(self.learning.skills.get('trial.chain',1)['effect_verified'])


if __name__=='__main__': unittest.main()
