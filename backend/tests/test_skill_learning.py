"""Offline acceptance tests use disposable SQLite files and actual local commands."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.actions.tools import get_tool, ToolResult
from backend.commands import CommandService
from backend.memory.procedural_memory import get_action_env_fingerprint


class Model:
    def __init__(self):
        self.calls = []
        self.outcomes = []
        self.answer = {'title': 'Diagnóstico', 'steps': [{'command_id': 'axx.system.telemetry', 'inputs': {}}]}

    def route(self, request):
        self.calls.append(request)
        return {'ok': True, 'message': {'content': json.dumps(self.answer)},
                'route': {'task': request['task'], 'provider_name': 'offline-fixture', 'model': 'fixture', 'request_id': request['request_id'],'upstream_attempts':1,'attempt_budget_used':1}}

    def record_outcome(self, route, task, outcome):
        self.outcomes.append((route, task, outcome))


class SkillLearningTests(unittest.TestCase):
    def test_remember_only_verified_application_receipts(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        self.executor.input_control=SimpleNamespace(automation=lambda event:nullcontext(event))
        pending=self.commands.prepare('axx.desktop.explorer.folder',{'path':r'C:\Users'})
        with self.assertRaises(ValueError):self.learning.remember(pending['operation_id'])
        with patch('backend.actions.application_flows.execute_flow',return_value={
            'success':True,'output':{'foreground_verified':True},
            'evidence':{'accepted':True,'verification':'shell_folder_and_foreground_readback'}}):
            done=self.commands.execute(pending['operation_id'])
        self.assertEqual(done['state'],'succeeded')
        saved=self.learning.remember(done['operation_id'])
        self.assertEqual(saved['status'],'verified')
        self.assertEqual(saved['templates'][0]['inputs'],{'path':'{{path}}'})
        self.assertEqual(self.learning.remember(done['operation_id'])['id'],saved['id'])
        plan=self.learning.propose(saved['id'],inputs={'path':r'C:\Windows'})
        self.assertEqual(plan['model_calls_used'],0)
        self.assertEqual(plan['steps'][0]['inputs'],{'path':r'C:\Windows'})

    def test_application_procedure_rebinds_parameters_and_keeps_approval(self):
        skill = self.seed(request='base de control de aplicaciones')
        skill = self.learning.configure(skill['id'], {
            'title':'Editar documento observado', 'schema':{'type':'object','properties':{
                'title':{'type':'string'},'text':{'type':'string'}},'required':['title','text']},
            'templates':[{'command_id':'axx.desktop.notepad.text','inputs':{'window_title':'{{title}}','value':'{{text}}'}}]})
        self.assertEqual(skill['status'],'candidate')
        from contextlib import nullcontext
        from types import SimpleNamespace
        import hashlib
        self.executor.input_control=SimpleNamespace(automation=lambda event:nullcontext(event))
        for title,text in [('one - Notepad','uno'),('two - Notepad','dos')]:
            plan=self.learning.propose(skill['id'],inputs={'title':title,'text':text})
            self.assertEqual(plan['state'],'awaiting_approval')
            self.assertEqual(plan['model_calls_used'],0)
            with patch('backend.actions.application_flows.execute_flow',return_value={
                'success':True,'output':{},'evidence':{'accepted':True,'verification':'uia_value_readback',
                    'value_sha256':hashlib.sha256(text.encode()).hexdigest(),'value_length':len(text)}}) as run:
                result=self.learning.execute(plan['operation_id'],True)
                self.assertEqual(result['state'],'succeeded',result)
                self.assertEqual(run.call_args.args[1],{'window_title':title,'value':text})
        self.assertEqual(self.learning.skills.get(skill['id'])['status'],'verified')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = Model()
        self.learning = ActionLearning(self.commands, self.model)

    def tearDown(self):
        self.learning.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    def restart(self):
        self.learning.close()
        self.learning = ActionLearning(self.commands, self.model)

    def seed(self, request='diagnóstico de prueba', project_id=''):
        plan = self.learning.propose(request, project_id=project_id)
        result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        return self.learning.skills.get(result['learned_action_id'])

    def writer(self, project_id=''):
        skill = self.seed(project_id=project_id)
        return self.learning.configure(skill['id'], {
            'title': 'Escribir entrega', 'schema': {'type': 'object', 'properties': {
                'filename': {'type': 'string'}, 'content': {'type': 'string'}}, 'required': ['filename', 'content']},
            'examples': ['otra entrega', 'prepara archivo'],
            'templates': [{'command_id': 'axx.artifact.write', 'inputs': {'path': '{{filename}}', 'content': '{{content}}'}}]})

    def test_parameter_variations_examples_and_exact_identity_are_zero_call(self):
        skill = self.writer()
        baseline = len(self.model.calls)
        for index, phrase in enumerate((skill['id'], 'otra entrega', 'prepara archivo')):
            plan = self.learning.propose(phrase, inputs={'filename': f'file-{index}.txt', 'content': f'Hola {index}'})
            self.assertEqual(plan['model_calls_used'], 0)
            self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'succeeded')
            self.assertEqual((self.executor.workspace_root / f'file-{index}.txt').read_text(), f'Hola {index}')
        self.assertEqual(len(self.model.calls), baseline)
        self.assertEqual(self.learning.skills.get(skill['id'])['status'], 'verified')

    def test_same_operation_cannot_be_rebound_and_new_request_has_new_step_ids(self):
        skill = self.writer()
        first = self.learning.propose(skill['id'], 'same-request', inputs={'filename': 'one.txt', 'content': 'one'})
        replay = self.learning.propose(skill['id'], 'same-request', inputs={'filename': 'one.txt', 'content': 'one'})
        self.assertEqual(first['step_records'], replay['step_records'])
        with self.assertRaises(ValueError):
            self.learning.propose(skill['id'], 'same-request', inputs={'filename': 'two.txt', 'content': 'one'})
        second = self.learning.propose(skill['id'], inputs={'filename': 'two.txt', 'content': 'one'})
        self.assertNotEqual(first['step_records'][0]['operation_id'], second['step_records'][0]['operation_id'])

    def test_missing_invalid_and_ambiguous_parameters_never_infer_or_execute(self):
        skill = self.writer()
        count = len(self.model.calls)
        for inputs in ({}, {'filename': 12, 'content': 'x'}, {'filename': '../outside', 'content': 'x'}):
            plan = self.learning.propose(skill['id'], inputs=inputs)
            self.assertEqual(plan['state'], 'needs_input', plan)
        another = self.seed('otro diagnóstico')
        self.learning.update_context('', {'aliases': {'mi acción': [skill['id'], another['id']]}})
        count = len(self.model.calls)
        ambiguous = self.learning.propose('mi acción')
        self.assertEqual(ambiguous['state'], 'needs_input')
        self.assertEqual(len(self.model.calls), count)

    def test_project_context_aliases_defaults_and_isolation(self):
        skill = self.writer('office')
        self.learning.update_context('office', {'aliases': {'entrega': skill['id']}, 'defaults': {'filename': 'office.txt', 'content': 'office'}})
        plan = self.learning.propose('entrega', project_id='office')
        self.assertEqual(plan['steps'][0]['inputs']['content'], 'office')
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'succeeded')
        repeat = self.learning.propose('hazlo otra vez', project_id='office', inputs={'filename': 'office-again.txt'})
        self.assertEqual(repeat['steps'][0]['inputs']['path'], 'office-again.txt')
        self.assertEqual(repeat['model_calls_used'], 0)
        self.assertEqual(self.learning.context('home')['last_skill_id'], '')
        self.assertEqual(self.learning.list_actions('home'), [])
        with self.assertRaises(ValueError): self.learning.update_context('home', {'aliases': {'wrong': skill['id']}})
        blocked = self.learning.compose('wrong project', [{'id': skill['id']}], project_id='home')
        self.assertEqual(blocked['state'], 'needs_input')
        self.assertTrue(self.learning.list_plans('office'))
        self.assertTrue(all(plan['project_id'] == 'office' for plan in self.learning.list_plans('office')))

    def test_resolver_recognizes_project_aliases_without_selecting_ambiguous_targets(self):
        skill = self.seed(project_id='Office')
        self.learning.update_context('Office', {'aliases': {'entrega azul': skill['id']}})
        self.assertTrue(self.learning.recognizes('entrega azul', 'Office'))
        self.assertEqual(self.learning.find('entrega azul', 'Office')['id'], skill['id'])
        self.assertFalse(self.learning.recognizes('entrega azul', 'Other'))
        self.assertIsNone(self.learning.find('entrega azul', 'Other'))
        other = self.seed('otro diagnóstico', project_id='Office')
        self.learning.update_context('Office', {'aliases': {'entrega azul': [skill['id'], other['id']]}})
        calls = len(self.model.calls)
        self.assertTrue(self.learning.recognizes('entrega azul', 'Office'))
        self.assertIsNone(self.learning.find('entrega azul', 'Office'))
        self.assertEqual(self.learning.propose('entrega azul', project_id='Office')['state'], 'needs_input')
        self.assertEqual(len(self.model.calls), calls)

    def test_immutable_candidate_revision_and_goal_confirmation(self):
        original = self.seed()
        configured = self.learning.configure(original['id'], {'version': 1, 'examples': ['estado ahora'], 'favorite': True,
                                                              'templates': [{'command_id': 'axx.process.inspect', 'inputs': {}}]})
        self.assertEqual(configured['version'], 2)
        self.assertEqual(configured['status'], 'candidate')
        self.assertEqual(self.learning.skills.get(original['id'], 1)['status'], 'verified')
        with self.assertRaises(ValueError): self.learning.configure(original['id'], {'goal_confirmed': True})
        plan = self.learning.propose('estado ahora')
        self.learning.execute(plan['operation_id'], True)
        confirmed = self.learning.configure(original['id'], {'version': 2, 'goal_confirmed': True})
        self.assertTrue(confirmed['effect_verified']); self.assertTrue(confirmed['goal_confirmed'])
        with self.assertRaises(ValueError): self.learning.configure(original['id'], {'version': 1, 'title': 'stale'})

    def test_legacy_migration_keeps_provenance_without_fabricating_verification(self):
        with self.learning.db:
            self.learning.db.execute('INSERT INTO learned_actions VALUES (?,?,?,?,?,?)',
                ('legacy.skill', 'old request', 'Old skill', json.dumps([{'command_id': 'axx.system.telemetry', 'inputs': {}}]),
                 get_action_env_fingerprint(['axx.system.telemetry']), 123))
            self.learning.db.execute('CREATE TABLE recipes (id TEXT, intent_key TEXT, version INTEGER, status TEXT, steps_json TEXT, verified_at TEXT)')
            self.learning.db.execute('INSERT INTO recipes VALUES (?,?,?,?,?,?)', ('old', 'old recipe', 4, 'verified', '[]', 'yesterday'))
        self.restart()
        migrated = self.learning.skills.get('legacy.skill')
        self.assertEqual(migrated['status'], 'candidate')
        self.assertEqual(migrated['provenance']['legacy_verified_at'], 123)
        recipe = self.learning.skills.get('recipe.old')
        self.assertEqual(recipe['status'], 'candidate'); self.assertFalse(recipe['executable'])
        self.assertEqual(recipe['provenance']['legacy_status'], 'verified')
        self.assertEqual(self.learning.db.execute('SELECT status FROM recipes').fetchone()[0], 'verified')
        plan = self.learning.propose('old request')
        self.assertEqual(plan['model_calls_used'], 0)
        self.learning.execute(plan['operation_id'], True)
        self.assertTrue(self.learning.skills.get('legacy.skill')['effect_verified'])

    def test_restart_reconciles_completed_command_before_plan_receipt_and_skips_it(self):
        self.model.answer = {'title': 'Two writes', 'steps': [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'first.txt', 'content': 'first'}},
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'second.txt', 'content': 'second'}}]}
        plan = self.learning.propose('two real files')
        record, step = plan['step_records'][0], plan['steps'][0]
        plan.update(state='running', approved_hash=plan['plan_hash']); record['state'] = 'running'; self.learning._save(plan)
        self.commands.prepare(step['command_id'], step['inputs'], operation_id=record['operation_id'])
        self.assertEqual(self.commands.execute(record['operation_id'], True)['state'], 'succeeded')
        self.restart()
        recovered = self.learning.resume(plan['operation_id'])
        self.assertEqual(recovered['state'], 'awaiting_approval')
        self.assertEqual(recovered['step_records'][0]['state'], 'succeeded')
        with patch.object(self.commands, 'execute', wraps=self.commands.execute) as execute:
            result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(len(self.executor.list_operations()), 2)

    def test_resume_renews_only_unexecuted_expired_preparation_with_same_identity(self):
        plan = self.learning.propose('renew preparation after restart')
        step, record = plan['steps'][0], plan['step_records'][0]
        self.commands.prepare(step['command_id'], step['inputs'], operation_id=record['operation_id'])
        with self.commands.db:
            self.commands.db.execute('UPDATE command_runs SET expires_at=0 WHERE operation_id=?', (record['operation_id'],))
        self.assertEqual(self.commands.execute(record['operation_id'], True)['state'], 'expired')
        plan['state'] = 'interrupted'; record['state'] = 'prepared'; self.learning._save(plan)
        self.restart()
        resumed = self.learning.resume(plan['operation_id'])
        self.assertEqual(resumed['state'], 'awaiting_approval')
        self.assertEqual(resumed['step_records'][0]['operation_id'], record['operation_id'])
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'succeeded')

    def test_unknown_command_uses_real_executor_receipt_but_unknown_without_receipt_blocks(self):
        plan = self.learning.propose('real interrupted receipt')
        step, record = plan['steps'][0], plan['step_records'][0]
        plan.update(state='running', approved_hash=plan['plan_hash']); record['state'] = 'running'; self.learning._save(plan)
        command = self.commands.prepare(step['command_id'], step['inputs'], operation_id=record['operation_id'])
        self.assertEqual(self.commands.execute(record['operation_id'], True)['state'], 'succeeded')
        with self.commands.lock: self.commands._save(command | {'state': 'unknown', 'postconditions_passed': False})
        plan['state'] = 'unknown'; record['state'] = 'running'; self.learning._save(plan)
        with patch.object(self.commands, 'execute', wraps=self.commands.execute) as execute:
            result = self.learning.resume(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(execute.call_count, 0)
        other = self.learning.propose('different interrupted request')
        other['step_records'][0]['state'] = 'running'; other['state'] = 'unknown'; self.learning._save(other)
        self.assertEqual(self.learning.resume(other['operation_id'], True)['state'], 'unknown')

    def test_unknown_artifact_reconciles_real_file_hash_and_never_rewrites_changed_content(self):
        self.model.answer = {'title': 'Durable file', 'steps': [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'uncertain.txt', 'content': 'expected'}}]}
        plan = self.learning.propose('uncertain file write')
        step, record = plan['steps'][0], plan['step_records'][0]
        plan.update(state='running', approved_hash=plan['plan_hash']); record['state'] = 'running'; self.learning._save(plan)
        command = self.commands.prepare(step['command_id'], step['inputs'], operation_id=record['operation_id'])
        result = self.commands.execute(record['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        action_id = result['action_operation_id']
        with self.commands.lock: self.commands._save(command | {'state': 'unknown', 'postconditions_passed': False})
        with self.executor.db:
            self.executor.db.execute("UPDATE operations SET state='unknown',result_json=NULL,evidence_json='{}' WHERE operation_id=?", (action_id,))
        plan['state'] = 'unknown'; record['state'] = 'running'; self.learning._save(plan)
        path = self.executor.workspace_root / 'uncertain.txt'
        path.write_text('modified')
        self.assertEqual(self.learning.resume(plan['operation_id'])['state'], 'unknown')
        path.write_text('expected')
        with patch.object(self.commands, 'execute', wraps=self.commands.execute) as execute:
            recovered = self.learning.resume(plan['operation_id'], True)
        self.assertEqual(recovered['state'], 'succeeded', recovered)
        self.assertEqual(execute.call_count, 0)
        self.assertEqual(recovered['results'][0]['evidence']['verification'], 'reconciled_artifact_sha256')

    def test_cancel_survives_restart_and_plan_tampering_is_rejected(self):
        plan = self.learning.propose('cancel me')
        self.learning.cancel(plan['operation_id']); self.restart()
        self.assertEqual(self.learning.resume(plan['operation_id'], True)['state'], 'cancelled')
        other = self.learning.propose('tamper')
        other['steps'][0] = {'command_id': 'axx.process.inspect', 'inputs': {}}
        self.learning._save(other)
        result = self.learning.execute(other['operation_id'], True)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(self.executor.list_operations(), [])

    def test_composition_dependencies_versions_and_eight_step_bound(self):
        skill = self.seed()
        plan = self.learning.compose('combined', [
            {'id': skill['id'], 'part_id': 'second', 'depends_on': ['first']},
            {'id': skill['id'], 'part_id': 'first', 'depends_on': []}])
        self.assertEqual(plan['skill_versions'][0]['part_id'], 'first')
        self.assertEqual(plan['dependencies'][plan['step_records'][1]['step_id']], [plan['step_records'][0]['step_id']])
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'succeeded')
        cyclic = self.learning.compose('cyclic', [{'id': skill['id'], 'part_id': 'a', 'depends_on': ['a']}])
        self.assertEqual(cyclic['state'], 'failed')
        revised = self.learning.configure(skill['id'], {'templates': skill['templates'] * 2})
        large = self.learning.compose('too many', [{'id': revised['id']} for _ in range(5)])
        self.assertEqual(large['state'], 'failed')

    def test_independent_reads_overlap_but_effect_waits_for_both_and_dependencies_serialize(self):
        read = self.seed()
        writer = self.learning.configure(read['id'], {'templates': [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'after-reads.txt', 'content': 'done'}}]})
        parts = [{'id': read['id'], 'version': 1, 'part_id': 'a', 'depends_on': []},
                 {'id': read['id'], 'version': 1, 'part_id': 'b', 'depends_on': []},
                 {'id': writer['id'], 'version': 2, 'part_id': 'write', 'depends_on': ['a', 'b']}]
        plan = self.learning.compose('parallel reads then write', parts)
        barrier, guard = threading.Barrier(2), threading.Lock()
        counts = {'active': 0, 'peak': 0}
        tool = get_tool('system_telemetry'); original = tool.execute
        writer_tool = get_tool('file_artifact_writer'); original_write = writer_tool.execute
        def read_tool(inputs):
            with guard:
                counts['active'] += 1; counts['peak'] = max(counts['peak'], counts['active'])
            try:
                barrier.wait(3)
                return original(inputs)
            finally:
                with guard: counts['active'] -= 1
        def write_tool(inputs):
            self.assertEqual(counts['active'], 0)
            return original_write(inputs)
        with patch.object(tool, 'execute', side_effect=read_tool), patch.object(writer_tool, 'execute', side_effect=write_tool):
            result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(counts['peak'], 2)
        self.assertEqual((self.executor.workspace_root / 'after-reads.txt').read_text(), 'done')
        sequential = self.learning.compose('dependent reads', parts[:1] + [parts[1] | {'depends_on': ['a']}])
        counts['peak'] = 0
        def serial_read(inputs):
            with guard:
                counts['active'] += 1; counts['peak'] = max(counts['peak'], counts['active'])
            try:
                time.sleep(0.02)
                return original(inputs)
            finally:
                with guard: counts['active'] -= 1
        with patch.object(tool, 'execute', side_effect=serial_read):
            self.assertEqual(self.learning.execute(sequential['operation_id'], True)['state'], 'succeeded')
        self.assertEqual(counts['peak'], 1)

    def test_failed_parallel_branch_repair_keeps_later_completed_branch_identity(self):
        skill = self.seed()
        self.learning.configure(skill['id'], {'templates': [{'command_id': 'axx.process.inspect', 'inputs': {}}]})
        plan = self.learning.compose('branches', [
            {'id': skill['id'], 'version': 1, 'part_id': 'failure', 'depends_on': []},
            {'id': skill['id'], 'version': 2, 'part_id': 'success', 'depends_on': []}])
        barrier = threading.Barrier(2)
        process = get_tool('process_state_inspector'); original = process.execute
        def failed(inputs):
            barrier.wait(3)
            return ToolResult(False, error='simulated telemetry failure')
        def successful(inputs):
            barrier.wait(3)
            return original(inputs)
        with patch.object(get_tool('system_telemetry'), 'execute', side_effect=failed), patch.object(process, 'execute', side_effect=successful):
            result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(result['step_records'][1]['state'], 'succeeded')
        completed = result['step_records'][1]['operation_id']
        self.model.answer = {'title': 'repaired branches', 'steps': [{'command_id': 'axx.artifact.write', 'inputs': {'path': 'branch.txt', 'content': 'verified'}}]}
        repaired = self.learning.repair(plan['operation_id'], 'replace broken branch with a note')
        self.assertEqual(repaired['step_records'][0]['operation_id'], completed)
        with patch.object(process, 'execute', wraps=original) as executed:
            final = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertEqual(executed.call_count, 0)

    def test_content_inference_is_fresh_per_task_persisted_and_visible_before_effect_approval(self):
        skill = self.writer()
        skill = self.learning.configure(skill['id'], {'inference': {
            'task': 'writing', 'prompt': 'Write content for {{filename}}', 'output_parameter': 'content'}})
        def content(request):
            self.model.calls.append(request)
            return {'ok': True, 'message': {'content': 'fresh:' + request['messages'][-1]['content']},
                    'route': {'task': request['task'], 'request_id': request['request_id'], 'provider_name': 'fixture','upstream_attempts':1,'attempt_budget_used':1}}
        with patch.object(self.model, 'route', side_effect=content):
            first = self.learning.propose(skill['id'], inputs={'filename': 'content-one.txt'})
            self.assertEqual(first['state'], 'awaiting_approval', first)
            self.assertFalse((self.executor.workspace_root / 'content-one.txt').exists())
            self.assertEqual(first['inference_counts'], {'writing': 1})
            calls = len(self.model.calls)
            self.restart()
            self.assertEqual(self.learning.resume(first['operation_id'], True)['state'], 'succeeded')
            self.assertEqual(len(self.model.calls), calls)
            second = self.learning.propose(skill['id'], inputs={'filename': 'content-two.txt'})
            self.assertEqual(second['model_calls_used'], 1)
            self.assertNotEqual(first['steps'][0]['inputs']['content'], second['steps'][0]['inputs']['content'])

    def test_capacity_resume_uses_same_task_and_requires_review_of_new_plan(self):
        with patch.object(self.model, 'route', return_value={'ok': False, 'error': {'code': 'NO_PROVIDER_AVAILABLE', 'retryable': True, 'message': 'quota','upstream_attempts':1,'attempt_budget_used':1}}):
            plan = self.learning.propose('wait for provider')
        self.assertEqual(plan['state'], 'waiting_capacity', plan)
        self.restart()
        resumed = self.learning.resume(plan['operation_id'], True)
        self.assertEqual(resumed['operation_id'], plan['operation_id'])
        self.assertEqual(resumed['state'], 'awaiting_approval', resumed)
        self.assertEqual(resumed['model_calls_used'], 2)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.learning.execute(plan['operation_id'], True)['state'], 'succeeded')

    def test_no_upstream_capacity_requests_do_not_exhaust_inference_budget_and_scheduler_never_executes(self):
        response = {'ok': False, 'error': {'code': 'NO_PROVIDER_AVAILABLE', 'retryable': True, 'upstream_attempted': False, 'message': 'no capacity'}}
        with patch.object(self.model, 'route', return_value=response):
            plan = self.learning.propose('wait indefinitely')
            for _ in range(3):
                plan['next_retry_at'] = 0; self.learning._save(plan)
                plan = self.learning.retry_waiting()[0]
            self.assertEqual(plan['state'], 'waiting_capacity')
            self.assertEqual(plan['model_calls_used'], 0)
            self.assertEqual(plan['route_requests'], 4)
        plan['next_retry_at'] = 0; self.learning._save(plan)
        ready = self.learning.retry_waiting()[0]
        self.assertEqual(ready['state'], 'awaiting_approval')
        self.assertEqual(ready['model_calls_used'], 1)
        self.assertEqual(self.executor.list_operations(), [])
        self.learning.cancel(ready['operation_id'])
        self.assertEqual(self.learning.retry_waiting(), [])

    def test_cancel_during_resumed_inference_uses_real_request_id_without_locking_ui(self):
        with patch.object(self.model, 'route', return_value={'ok': False, 'error': {'code': 'BUSY', 'retryable': True,'upstream_attempted':False}}):
            plan = self.learning.propose('cancel resumed provider')
        entered, release = threading.Event(), threading.Event()
        requests, cancelled = [], []
        def slow(request):
            requests.append(request); entered.set(); release.wait(4)
            return {'ok': True, 'message': {'content': json.dumps(self.model.answer)}}
        results = []
        with patch.object(self.model, 'route', side_effect=slow), patch.object(self.model, 'cancel', side_effect=cancelled.append, create=True):
            worker = threading.Thread(target=lambda: results.append(self.learning.resume(plan['operation_id'])))
            worker.start(); self.assertTrue(entered.wait(3))
            self.learning.cancel(plan['operation_id']); release.set(); worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertIn(requests[0]['request_id'], cancelled)
        self.assertEqual(results[0]['state'], 'cancelled')
        self.assertEqual(self.executor.list_operations(), [])

    def test_actual_upstream_attempts_stop_at_two_and_missing_metadata_is_not_assumed_free(self):
        with patch.object(self.model, 'route', return_value={'ok': False, 'error': {'code': 'NO_PROVIDER_AVAILABLE', 'retryable': True, 'upstream_attempted': True,'upstream_attempts':1,'attempt_budget_used':1}}) as route:
            plan = self.learning.propose('bounded failed inference')
            plan = self.learning.resume(plan['operation_id'])
            self.assertEqual(plan['state'], 'failed')
            self.assertEqual(plan['model_calls_used'], 2)
            self.learning.resume(plan['operation_id'])
            self.assertEqual(route.call_count, 2)

    def test_metadata_revision_keeps_evidence_and_goal_outcome_reaches_adapter(self):
        original = self.seed()
        revised = self.learning.configure(original['id'], {'favorite': True, 'examples': ['diagnostic alias']})
        self.assertTrue(revised['effect_verified'])
        self.assertEqual(revised['outcome_history'][0]['inherited_from_version'], 1)
        self.learning.configure(original['id'], {'goal_confirmed': True})
        self.assertEqual(self.model.outcomes[-1][2], 'user_confirmed')

    def test_scheduler_shutdown_cancels_transport_joins_and_preserves_pending_task(self):
        with patch.object(self.model, 'route', return_value={'ok': False, 'error': {'code': 'BUSY', 'retryable': True,'upstream_attempted':False}}):
            plan = self.learning.propose('recover after shutdown')
        plan['next_retry_at'] = 0; self.learning._save(plan)
        entered, released = threading.Event(), threading.Event()
        cancelled = []
        def route(request):
            entered.set(); released.wait(8)
            return {'ok': False, 'error': {'code': 'CANCELLED', 'retryable': False,'upstream_attempted':False}}
        def cancel(request_id):
            cancelled.append(request_id); released.set()
        with patch.object(self.model, 'route', side_effect=route), patch.object(self.model, 'cancel', side_effect=cancel, create=True):
            self.learning.start_recovery()
            self.assertTrue(entered.wait(7))
            self.learning.close()
        self.assertTrue(cancelled)
        self.assertFalse(self.learning.recovery_thread.is_alive())
        self.assertTrue(self.learning.closed)
        self.learning = ActionLearning(self.commands, self.model)
        saved = self.learning.get(plan['operation_id'])
        self.assertEqual(saved['state'], 'interrupted', saved)
        self.assertFalse(saved.get('cancel_requested', False))
        self.assertEqual(self.learning.resume(plan['operation_id'])['state'], 'awaiting_approval')
        self.assertEqual(self.executor.list_operations(), [])

    def test_planner_authors_parameterized_skill_only_when_candidate_matches_real_execution(self):
        candidate = {'schema': {'type': 'object', 'properties': {'filename': {'type': 'string'}, 'text': {'type': 'string'}},
                                'required': ['filename', 'text']},
                     'templates': [{'command_id': 'axx.artifact.write', 'inputs': {'path': '{{filename}}', 'content': '{{text}}'}}],
                     'examples': ['escribe otra nota'], 'inputs': {'filename': 'authored.txt', 'text': 'first'}}
        self.model.answer = {'title': 'Nota reusable', 'steps': [{'command_id': 'axx.artifact.write', 'inputs': {'path': 'authored.txt', 'content': 'first'}}],
                             'skill_candidate': candidate}
        plan = self.learning.propose('crea una nota reusable')
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        repeated = self.learning.propose('escribe otra nota', inputs={'filename': 'authored-two.txt', 'text': 'second'})
        self.assertEqual(repeated['model_calls_used'], 0)
        self.assertEqual(self.learning.execute(repeated['operation_id'], True)['state'], 'succeeded')
        self.assertEqual((self.executor.workspace_root / 'authored-two.txt').read_text(), 'second')
        self.assertEqual(len(self.model.calls), 1)
        candidate['inputs']['text'] = 'not the actual content'
        mismatch = self.learning.propose('different new request')
        self.assertEqual(mismatch['state'], 'failed', mismatch)

    def test_repair_preserves_completed_effect_ids_and_candidate_requires_execution(self):
        self.model.answer = {'title': 'Fail after file', 'steps': [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'done.txt', 'content': 'done'}},
            {'command_id': 'axx.file.sha256', 'inputs': {'path': str(self.root / 'missing')}}]}
        plan = self.learning.propose('make file and inspect')
        failed = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(failed['state'], 'failed')
        completed_id = failed['step_records'][0]['operation_id']
        old_failed_id = failed['step_records'][1]['operation_id']
        self.model.answer = {'title': 'Fixed inspection', 'steps': [
            {'command_id': 'axx.system.telemetry', 'inputs': {}},
            {'command_id': 'axx.file.sha256', 'inputs': {'path': str(self.executor.workspace_root / 'done.txt')}}]}
        repaired = self.learning.repair(plan['operation_id'], 'inspect the file actually created')
        self.assertEqual(repaired['state'], 'awaiting_approval', repaired)
        self.assertEqual(repaired['step_records'][0]['operation_id'], completed_id)
        self.assertNotIn(old_failed_id, [row['operation_id'] for row in repaired['step_records']])
        self.assertEqual(repaired['model_calls_used'], 2)
        self.assertEqual(self.learning.skills.get(repaired['skill_versions'][0]['id'])['status'], 'candidate')
        with patch.object(self.commands, 'execute', wraps=self.commands.execute) as execute:
            result = self.learning.execute(plan['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual((self.executor.workspace_root / 'done.txt').read_text(), 'done')

    def test_shell_is_unavailable_in_configured_skills_and_powershell_plans(self):
        skill = self.seed()
        for command in ('axx.shell.cmd', 'axx.shell.powershell'):
            with self.assertRaises(ValueError):
                self.learning.configure(skill['id'], {'templates': [{'command_id': command, 'inputs': {'script': 'echo no'}}]})
        self.model.answer = {'title': 'shell', 'steps': [{'command_id': 'axx.shell.powershell', 'inputs': {'script': 'echo no'}}]}
        self.assertEqual(self.learning.propose('run axx.shell.powershell')['state'], 'failed')


if __name__ == '__main__':
    unittest.main()
