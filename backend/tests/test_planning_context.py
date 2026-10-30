"""Planning privacy checks use temporary SQLite, real files and an offline model."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory.procedural_memory import get_action_env_fingerprint
from backend.memory.skill_memory import validate_schema, NeedsInput
from backend.anticipation import AnticipationService


class LocalModel:
    def __init__(self):
        self.calls = []
        self.answer = {'needs_input': 'Indica un objetivo explícito.'}
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False

    def route(self, request):
        self.calls.append(copy.deepcopy(request))
        self.entered.set()
        if self.block and not self.release.wait(10):
            raise RuntimeError('The local test did not release the model')
        return {'ok': True, 'message': {'content': json.dumps(self.answer)},
                'route': {'provider_name': 'offline-fixture', 'model': 'fixture'}}


class SourcePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = time.time()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = LocalModel()
        self.model.supports_cancel_event = True
        self.model.supports_dispatch_observer = True
        self.model.route = lambda request, cancel_event=None, dispatch_observer=None: {'ok': True,
            'message': {'content': json.dumps({'title': 'PRIVATE_LATE_ECHO', 'steps': [
                {'command_id': 'axx.artifact.write', 'inputs': {'path': 'source-output.txt', 'content': 'PRIVATE_LATE_ECHO'}}]})},
            'route': {'provider_name': 'offline-fixture', 'model': 'fixture'}}
        self.learning = ActionLearning(self.commands, self.model)
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.learning.anticipation = self.service
        self.commands.learning = self.learning
        self.patchers = [patch.object(self.service, '_clipboard_available', return_value=True),
            patch.object(self.service, '_provider_context_available', return_value=True),
            patch('backend.action_learning.SOURCE_PLANNING_READY', True),
            patch.object(self.service, '_clipboard_snapshot', return_value=(
                {'sequence_number': 1, 'characters': 17, 'content_fingerprint': 'synthetic'},
                {'text': 'PRIVATE_SOURCE_RAW'}, False))]
        for patcher in self.patchers: patcher.start()
        self.target = {'id': 'clipboard-source', 'source': 'clipboard', 'task_id': 'source-task',
            'observe': True, 'retain': True, 'send_to_provider': True, 'project_id': 'project-a'}
        self.service.configure({'profile': 'copiloto', 'sources': {'clipboard': True}, 'observation_targets': [self.target]})
        self.service.tick()
        self.plan, _ = self.learning._new_plan('Preparar tarea sintética', 'source-plan', {}, 'project-a')
        self.plan.update(conversation_id='source-task', operational_context={'context_meta': {}, 'project_id': 'project-a'},
            planning_settings={'provider_name': '', 'model': '', 'selection_mode': 'manual'})
        self.learning._save(self.plan)

    def tearDown(self):
        self.learning.close(); self.service.close(); self.commands.close(); self.executor.close()
        for patcher in reversed(self.patchers): patcher.stop()
        self.temp.cleanup()

    def response(self):
        return self.learning._infer(self.plan, 'plan', self.learning._prompt(self.plan['request'], {}, 'project-a', 'source-task'))

    def revoke(self):
        self.service.configure({'observation_targets': [self.target | {'retain': False, 'send_to_provider': False}]})

    def assert_no_echo(self):
        payload = '\n'.join(row[0] for row in self.learning.db.execute('SELECT payload FROM learning_plans'))
        for text in ('PRIVATE_LATE_ECHO', 'PRIVATE_SOURCE_RAW'):
            self.assertNotIn(text, payload)
            self.assertNotIn(text, json.dumps(self.learning.get('source-plan')))
        self.assertEqual(self.executor.list_operations(), [])
        self.assertFalse(self.learning.db.execute("SELECT 1 FROM skill_versions WHERE json_extract(payload,'$.title')='PRIVATE_LATE_ECHO'").fetchone())

    def test_revoke_after_response_before_ready_never_publishes_echo(self):
        data = self.learning._model_data(self.response())
        self.plan['steps'] = data['steps']
        self.revoke()
        with self.assertRaises(NeedsInput):
            self.learning._ready(self.plan, data['title'])
        self.plan.update(model_data=data, skill_candidate={'title': 'PRIVATE_LATE_ECHO'}, message='PRIVATE_LATE_ECHO')
        saved = self.learning._save(self.plan)
        self.assertTrue(saved['context_invalidated'])
        self.assertIsNone(saved['approved_hash'])
        self.assert_no_echo()

    def test_revoke_before_first_save_write_restores_durable_snapshot(self):
        data = self.learning._model_data(self.response())
        self.plan.update(model_data=data, title='PRIVATE_LATE_ECHO', steps=data['steps'], skill_candidate=data)
        original = self.learning._save_current
        calls = []
        def intercepted(plan, source_recheck=lambda: None):
            if not calls:
                calls.append(True); self.revoke()
            return original(plan, source_recheck)
        with patch.object(self.learning, '_save_current', side_effect=intercepted):
            saved = self.learning._save(self.plan)
        self.assertEqual(saved['state'], 'needs_input')
        self.assert_no_echo()

    def test_expiry_before_commit_rolls_back_new_proposal(self):
        data = self.learning._model_data(self.response())
        self.plan.update(model_data=data, title='PRIVATE_LATE_ECHO', steps=data['steps'])
        original = self.learning._save_current
        checks = []
        def intercepted(plan, source_recheck=lambda: None):
            def expire_before_commit():
                checks.append(True)
                if len(checks) == 3: self.now += 61
                source_recheck()
            return original(plan, expire_before_commit)
        with patch.object(self.learning, '_save_current', side_effect=intercepted):
            saved = self.learning._save(self.plan)
        self.assertTrue(saved['context_invalidated'])
        self.assert_no_echo()

    def test_authorized_retained_plan_persists_but_never_learns_new_skill_or_capability(self):
        data = self.learning._model_data(self.response())
        self.plan.update(model_data=data, steps=data['steps'])
        self.learning._ready(self.plan, data['title'])
        saved = self.learning._save(self.plan)
        self.assertEqual(saved['state'], 'awaiting_approval')
        self.assertIn('PRIVATE_LATE_ECHO', json.dumps(self.learning.get('source-plan')))
        with patch.object(self.learning.skills, 'insert', side_effect=AssertionError('No automatic source-derived skills')), \
                patch.object(self.learning, 'update_context', side_effect=AssertionError('No reusable source-derived context')):
            completed = self.learning.execute('source-plan', approved=True)
            self.assertEqual(completed['state'], 'succeeded', completed)
            self.assertTrue(completed['postconditions_passed'])
        self.assertEqual((self.executor.workspace_root / 'source-output.txt').read_text(), 'PRIVATE_LATE_ECHO')
        with self.assertRaisesRegex(NeedsInput, 'comandos existentes'):
            self.learning._build_capability(self.plan, {'kind': 'python_transform', 'goal': 'PRIVATE_LATE_ECHO'})

    def test_old_source_response_cannot_be_resent_as_ordinary_repair_after_revoke(self):
        with patch.object(self.model, 'route', wraps=self.model.route) as route:
            self.response()
            self.revoke()
            with self.assertRaises(NeedsInput):
                self.learning._infer(self.plan, 'repair', [
                    {'role': 'system', 'content': 'synthetic repair'},
                    {'role': 'user', 'content': 'PRIVATE_LATE_ECHO from previous attempt'}])
        self.assertEqual(route.call_count, 1)
        self.assert_no_echo()

    def test_revocation_at_route_save_aborts_before_backend_and_refunds_unattempted_call(self):
        original = self.learning._save
        def revoke_before_network(plan):
            if plan.get('active_inference_request_id'):
                self.revoke()
            return original(plan)
        with patch.object(self.learning, '_save', side_effect=revoke_before_network), \
                patch.object(self.model, 'route', wraps=self.model.route) as route:
            with self.assertRaises(NeedsInput): self.response()
        route.assert_not_called()
        self.assertEqual(self.learning.get('source-plan')['model_calls_used'], 0)
        self.assert_no_echo()

    def test_repair_retains_reviewable_plan_without_inserting_source_echo_skill(self):
        data = self.learning._model_data(self.response())
        self.plan.update(model_data=data, preparation={'kind': 'repair', 'prefix': [],
            'previous': {'skill_versions': [], 'plan_hash': 'previous'}, 'correction': 'synthetic correction'})
        with patch.object(self.learning.skills, 'insert', side_effect=AssertionError('No premature source-derived skill')):
            self.learning._prepare_repair(self.plan)
        self.assertEqual(self.plan['state'], 'awaiting_approval')
        self.assertEqual(self.plan['skill_versions'], [])

    def test_ready_releases_policy_lock_before_command_catalog_validation(self):
        self.response()
        for references in (False, True):
            with self.subTest(observation_dependencies=references):
                plan = copy.deepcopy(self.plan)
                if not references:
                    plan.pop('observation_dependencies', None)
                plan['steps'] = [{'command_id': 'axx.system.telemetry', 'inputs': {}}]
                command_held = threading.Event()
                validating = threading.Event()
                checked_policy = threading.Event()
                policy_acquired, errors = [], []
                original_validate = self.learning._validate_steps

                def dispatch_order():
                    with self.commands.lock:
                        command_held.set()
                        if not validating.wait(3):
                            errors.append('Preparation did not reach catalog validation')
                        acquired = self.service.lock.acquire(timeout=2)
                        policy_acquired.append(acquired)
                        if acquired:
                            self.service.lock.release()
                        checked_policy.set()

                def validate(*args, **kwargs):
                    validating.set()
                    if not checked_policy.wait(3):
                        raise AssertionError('Dispatch did not complete policy admission')
                    return original_validate(*args, **kwargs)

                def ready():
                    try:
                        self.learning._ready(plan, 'Synthetic lock-order check')
                    except Exception as exc:
                        errors.append(repr(exc))

                dispatcher = threading.Thread(target=dispatch_order, daemon=True)
                preparer = threading.Thread(target=ready, daemon=True)
                with patch.object(self.learning, '_validate_steps', side_effect=validate):
                    dispatcher.start()
                    self.assertTrue(command_held.wait(3))
                    preparer.start()
                    dispatcher.join(5); preparer.join(5)
                self.assertFalse(dispatcher.is_alive() or preparer.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(policy_acquired, [True], 'Preparation held policy while waiting for commands')
                self.assertEqual(self.executor.list_operations(), [])

    def test_list_two_plans_takes_policy_before_first_budget_write(self):
        second, _ = self.learning._new_plan('Segundo objetivo sintético', 'source-plan-two', {}, 'project-a')
        second['conversation_id'] = 'source-task'
        self.learning._save(second)
        for references in (False, True):
            with self.subTest(observation_dependencies=references):
                if references:
                    refs = self.service.provider_context_for_task('source-task', project_id='project-a')['refs']
                    for key in ('source-plan', 'source-plan-two'):
                        plan = self.learning.get(key)
                        plan['observation_dependencies'] = refs
                        self.learning._save(plan)
                first_write, configure_started = threading.Event(), threading.Event()
                errors, results, stores = [], [], []
                original_store = self.learning._store_model_budget

                def store(plan):
                    original_store(plan)
                    stores.append(plan['operation_id'])
                    if len(stores) == 1:
                        # This is the concrete boundary before a second row can
                        # consult policy while the SQL writer is already held.
                        if not self.service.lock._is_owned():
                            raise AssertionError('SQL writer acquired before policy')
                        first_write.set()
                        if not configure_started.wait(3):
                            raise AssertionError('Configuration thread did not start')

                def list_plans():
                    try:
                        results.extend(self.learning.list_plans('project-a'))
                    except Exception as exc:
                        errors.append(repr(exc)); first_write.set()

                def configure():
                    if not first_write.wait(3):
                        errors.append('Budget transaction did not start'); return
                    configure_started.set()
                    try:
                        self.service.configure({'paused': False})
                    except Exception as exc:
                        errors.append(repr(exc))

                listing = threading.Thread(target=list_plans, daemon=True)
                configuring = threading.Thread(target=configure, daemon=True)
                with patch.object(self.learning, '_store_model_budget', side_effect=store):
                    configuring.start(); listing.start()
                    listing.join(5); configuring.join(5)
                self.assertFalse(listing.is_alive() or configuring.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(results), 2)
                self.assertEqual(len(stores), 2)

    def test_repair_cannot_replace_old_permission_with_new_observation_after_revoke(self):
        original_prompt = self.learning._source_prompt
        with patch.object(self.model, 'route', wraps=self.model.route) as route:
            self.response()
            previous = copy.deepcopy(self.plan['observation_dependencies'])

            def replace_source(plan, messages):
                new_target = self.target | {'id': 'clipboard-source-two'}
                self.service.configure({'observation_targets': [new_target]})
                self.service.tick()
                prepared = original_prompt(plan, messages)
                self.assertEqual([ref['target_id'] for ref in prepared[2]], ['clipboard-source-two'])
                return prepared

            with patch.object(self.learning, '_source_prompt', side_effect=replace_source):
                with self.assertRaises(NeedsInput):
                    self.learning._infer(self.plan, 'repair', [
                        {'role': 'system', 'content': 'Synthetic repair'},
                        {'role': 'user', 'content': 'PRIVATE_OLD_SOURCE_ECHO from the prior response'}])
            self.assertEqual(route.call_count, 1)
        self.assertEqual(self.plan['observation_dependencies'], previous)
        self.learning._save(self.plan)
        self.assert_no_echo()
        payload = ''.join(row[0] for row in self.learning.db.execute('SELECT payload FROM learning_plans'))
        self.assertNotIn('PRIVATE_OLD_SOURCE_ECHO', payload)

    def test_failed_source_receipt_never_becomes_skill_evidence_after_revoke(self):
        self.response()
        target = self.executor.workspace_root / 'PRIVATE_FAILED_SOURCE_ECHO.txt'
        target.write_text('Synthetic temporary input', encoding='utf-8')
        prepared = self.commands.prepare('axx.file.sha256', {'path': str(target)}, conversation_id='source-task')
        target.unlink()
        receipt = self.commands.execute(prepared['operation_id'], approved=True)
        self.assertEqual(receipt['state'], 'failed', receipt)
        skill = self.learning.skills.insert({'id': 'fixture.source-hash', 'version': 1,
            'trigger': 'fixture.source-hash', 'title': 'Explicit synthetic hash fixture', 'examples': [],
            'schema': validate_schema({'properties': {'path': {'type': 'string'}}, 'required': ['path']}),
            'templates': [{'command_id': 'axx.file.sha256', 'inputs': {'path': '{{path}}'}}],
            'project_id': 'project-a', 'favorite': False, 'checks': ['executor_postconditions'], 'executable': True,
            'environment': get_action_env_fingerprint(['axx.file.sha256']), 'provenance': {}})
        self.plan.update(skill_versions=[{'id': skill['id'], 'version': skill['version'],
            'inputs': {'path': str(target)}, 'step_start': 0, 'step_count': 1}],
            step_records=[{'operation_id': receipt['operation_id'], 'state': 'failed', 'result': receipt}])
        journal_before = self.commands.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?',
            (receipt['operation_id'],)).fetchone()[0]
        self.revoke()
        with patch.object(self.learning.skills, 'record', wraps=self.learning.skills.record) as record, \
                patch.object(self.model, 'record_outcome', create=True) as metrics:
            self.learning._record_outcome(self.plan, 'failed')
        record.assert_not_called()
        metrics.assert_called_once()
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM skill_evidence').fetchone()[0], 0)
        self.assertEqual(self.commands.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?',
            (receipt['operation_id'],)).fetchone()[0], journal_before)

    def test_repair_leases_old_and_new_refs_even_when_only_new_context_is_selected(self):
        self.response()
        old_refs = copy.deepcopy(self.plan['observation_dependencies'])
        new_target = self.target | {'id': 'clipboard-source-two'}
        self.service.configure({'observation_targets': [self.target, new_target]})
        self.service.tick()
        original_read = self.service.provider_context_for_task

        def select_new(*args, **kwargs):
            source = original_read(*args, **kwargs)
            return source | {key: [row for row in source[key] if row['target_id'] == new_target['id']]
                for key in ('refs', 'observations')}

        def cancel_old(request, cancel_event=None, dispatch_observer=None):
            self.assertEqual({ref['target_id'] for ref in self.plan['observation_dependencies']},
                {self.target['id'], new_target['id']})
            self.assertTrue(all(ref in self.plan['observation_dependencies'] for ref in old_refs))
            self.service.configure({'observation_targets': [new_target]})
            self.assertTrue(cancel_event.is_set(), 'Revoking the old source did not cancel the combined lease')
            return {'ok': True, 'message': {'content': 'PRIVATE_OLD_SOURCE_ECHO'}, 'route': {}}

        with patch.object(self.service, 'provider_context_for_task', side_effect=select_new), \
                patch.object(self.model, 'route', side_effect=cancel_old):
            with self.assertRaises(NeedsInput):
                self.learning._infer(self.plan, 'repair', [
                    {'role': 'system', 'content': 'Synthetic repair'},
                    {'role': 'user', 'content': 'PRIVATE_OLD_SOURCE_ECHO from the earlier context'}])
        self.assert_no_echo()
        self.assertEqual(self.service.provider_context_leases, {})

    def test_more_than_four_combined_source_refs_abstains_before_backend(self):
        self.response()
        old_refs = copy.deepcopy(self.plan['observation_dependencies'])
        new_targets = [self.target | {'id': 'clipboard-source-' + str(index)} for index in range(4)]
        self.service.configure({'observation_targets': [self.target, *new_targets]})
        self.service.tick()
        original_read = self.service.provider_context_for_task

        def select_new(*args, **kwargs):
            # Each new target remains consented and bounded; the total causal
            # dependency set still cannot discard the earlier fifth source.
            with self.service.lock:
                old_target = self.service.source_state.pop(self.target['id'])
                try:
                    return original_read(*args, **kwargs)
                finally:
                    self.service.source_state[self.target['id']] = old_target

        with patch.object(self.service, 'provider_context_for_task', side_effect=select_new), \
                patch.object(self.model, 'route', wraps=self.model.route) as route:
            with self.assertRaises(NeedsInput):
                self.learning._infer(self.plan, 'repair', [
                    {'role': 'system', 'content': 'Synthetic repair'},
                    {'role': 'user', 'content': 'Prior authorized synthetic context'}])
        route.assert_not_called()
        self.assertEqual(self.plan['observation_dependencies'], old_refs)


class PlanningContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = LocalModel()
        self.learning = ActionLearning(self.commands, self.model)
        self.file = self.executor.workspace_root / 'synthetic-source.txt'
        self.file.write_text('Synthetic local fixture.', encoding='utf-8')

    def tearDown(self):
        self.model.release.set()
        self.learning.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def payload(self, context, *, task='task-b', text='context reference'):
        messages = self.learning._prompt(text, context, 'project-a', task)
        return json.loads(messages[-1]['content'])

    def test_remote_observation_gate_blocks_source_echo_before_dispatch_or_persistence(self):
        ref={'target_id':'clipboard-a','consent_digest':'digest','observation_id':'observation-a','generation':1}
        observation={'source':'clipboard','target_id':'clipboard-a','observation_id':'observation-a',
            'observed_at':time.time(),'expires_at':time.time()+60,'context_state':'observed','untrusted':True,
            'metadata':{'characters':27},'content':{'text':'PRIVATE_OBSERVATION_SENTINEL'}}
        self.learning.anticipation=SimpleNamespace(provider_context_for_task=lambda *args,**kwargs:{'refs':[ref],'observations':[observation]})
        plan,_=self.learning._new_plan('Preparar un archivo de ensayo','observation-trial',{},'project-a')
        plan['planning_settings']={'provider_name':'','model':'','selection_mode':'manual'}
        with self.assertRaisesRegex(NeedsInput,'desactivado'):
            self.learning._infer(plan,'plan',self.learning._prompt(plan['request'],{},'project-a'))
        self.assertEqual(self.model.calls,[])
        stored=''.join(row[0] for row in self.learning.db.execute('SELECT payload FROM learning_plans'))
        self.assertNotIn('PRIVATE_OBSERVATION_SENTINEL',stored)

    def test_typed_catalog_and_bounded_observation_fit_conservative_request_budget(self):
        ref={'target_id':'clipboard-a','consent_digest':'digest','observation_id':'observation-a','generation':1}
        self.learning.anticipation=SimpleNamespace(provider_context_for_task=lambda *args,**kwargs:{'refs':[ref],
            'observations':[{'source':'clipboard','target_id':'clipboard-a','observation_id':'observation-a',
                'metadata':{'characters':5000},'content':{'text':'😀'*5000}}]})
        plan,_=self.learning._new_plan('Preparar un archivo de ensayo','bounded-observation',{},'project-a')
        messages=self.learning._prompt(plan['request'],{},'project-a')
        with patch('backend.action_learning.SOURCE_PLANNING_READY',True):
            messages,images,refs=self.learning._source_prompt(plan,messages)
        self.assertEqual(refs,[ref]);self.assertEqual(images,[])
        data=json.loads(messages[1]['content'])['observed_context']['observations'][0]
        self.assertTrue(data['text_truncated']);self.assertLessEqual(len(data['text'].encode()),1000)
        self.assertLess(len(json.dumps({'messages':messages,'tools':None},ensure_ascii=False).encode())+1024+2048,32768)

    def hash_receipt(self, *, task='task-a', fail=False):
        if not self.file.exists(): self.file.write_text('Synthetic local fixture.', encoding='utf-8')
        prepared = self.commands.prepare('axx.file.sha256', {'path': str(self.file)}, conversation_id=task)
        if fail: self.file.unlink()
        return self.commands.execute(prepared['operation_id'], approved=True)

    def insert_hash_skill(self):
        return self.learning.skills.insert({'id': 'synthetic.hash', 'version': 1,
            'trigger': 'synthetic.hash', 'title': 'Synthetic hash', 'examples': [],
            'templates': [{'command_id': 'axx.file.sha256', 'inputs': {'path': str(self.file)}}],
            'schema': validate_schema({}), 'project_id': 'project-a', 'favorite': False,
            'environment': get_action_env_fingerprint(['axx.file.sha256']),
            'checks': ['executor_postconditions'], 'provenance': {}, 'created_at': time.time(), 'executable': True})

    def test_prompt_replaces_foreign_and_expired_cached_ambient_context(self):
        now = time.time()
        self.learning.update_context('project-a', {
            'current_file': 'FOREIGN_TASK_PRIVATE_SENTINEL',
            'current_folder': 'EXPIRED_PRIVATE_SENTINEL',
            'current_project': 'CURRENT_TASK_VISIBLE',
            'context_meta': {
                'current_file': {'kind': 'observed', 'source_id': 'task-source', 'task_id': 'task-a'},
                'current_folder': {'kind': 'observed', 'expires_at': now + 10},
                'current_project': {'kind': 'confirmed_user', 'task_id': 'task-b'}}})
        snapshot = self.learning.context('project-a')
        with patch('backend.memory.skill_memory.time.time', return_value=now + 20):
            payload = self.payload({'operational_context': snapshot, 'context': copy.deepcopy(snapshot)})
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn('FOREIGN_TASK_PRIVATE_SENTINEL', serialized)
        self.assertNotIn('EXPIRED_PRIVATE_SENTINEL', serialized)
        self.assertIn('CURRENT_TASK_VISIBLE', serialized)
        self.assertIn('FOREIGN_TASK_PRIVATE_SENTINEL', json.dumps(snapshot))
        self.assertEqual(self.model.calls, [])

    def test_forgotten_snapshot_is_not_sent_again_and_real_receipts_are_preserved(self):
        receipt = self.hash_receipt()
        self.assertEqual(receipt['state'], 'succeeded', receipt)
        before_command = self.commands.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?',
                                                  (receipt['operation_id'],)).fetchone()[0]
        before_action = self.executor.db.execute('SELECT result_json FROM operations WHERE operation_id=?',
                                                (receipt['action_operation_id'],)).fetchone()[0]
        self.learning.update_context('project-a', {'current_file': 'FORGOTTEN_AMBIENT_SENTINEL',
            'context_meta': {'current_file': {'kind': 'observed', 'source_id': 'forgotten-source', 'task_id': 'task-a'}}})
        snapshot = self.learning.context('project-a')
        self.learning.invalidate_context('project-a', {'source_id': 'forgotten-source', 'forget': True})
        payload = self.payload({'operational_context': snapshot, 'context': copy.deepcopy(snapshot),
                                'completed': [receipt]}, task='task-a')
        self.assertNotIn('FORGOTTEN_AMBIENT_SENTINEL', json.dumps(payload))
        self.assertEqual(payload['previous_action']['completed'], [receipt])
        self.assertEqual(self.commands.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?',
                                                 (receipt['operation_id'],)).fetchone()[0], before_command)
        self.assertEqual(self.executor.db.execute('SELECT result_json FROM operations WHERE operation_id=?',
                                                (receipt['action_operation_id'],)).fetchone()[0], before_action)

    def test_alias_and_repeat_track_the_exact_task_and_forget_invalidates_prepared_plans(self):
        skill = self.insert_hash_skill()
        self.learning.update_context('project-a', {'aliases': {'mi referencia': skill['id']},
            'last_skill_id': skill['id'], 'context_meta': {
                'aliases': {'kind': 'confirmed_user', 'source_id': 'selection-source', 'task_id': 'task-a'},
                'last_skill_id': {'kind': 'observed', 'source_id': 'selection-source', 'task_id': 'task-a'}}})
        plans = []
        for phrase, field in (('mi referencia', 'aliases'), ('hazlo otra vez', 'last_skill_id')):
            with self.subTest(phrase=phrase):
                plan = self.learning.propose(phrase, project_id='project-a', conversation_id='task-a')
                self.assertEqual(plan['state'], 'awaiting_approval', plan)
                self.assertEqual(plan['model_calls_used'], 0)
                self.assertTrue(any(ref['field'] == field and ref['project_id'] == 'project-a'
                                    for ref in plan['context_dependencies']))
                plans.append(plan)
                foreign = self.learning.propose(phrase, project_id='project-a', conversation_id='task-b')
                self.assertNotEqual(foreign['state'], 'awaiting_approval', foreign)
                self.assertEqual(foreign['steps'], [])
        self.learning.invalidate_context('project-a', {'source_id': 'selection-source', 'forget': True})
        for plan in plans:
            persisted = self.learning.get(plan['operation_id'])
            self.assertEqual(persisted['state'], 'needs_input', persisted)
            self.assertFalse(persisted.get('approved_hash'))
            self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'needs_input')
        self.assertEqual(self.executor.list_operations(), [])

    def test_forget_during_model_call_does_not_resurrect_derived_intent_or_effects(self):
        marker = 'INFLIGHT_FORGOTTEN_SENTINEL'
        self.learning.update_context('project-a', {'current_file': marker, 'context_meta': {
            'current_file': {'kind': 'observed', 'source_id': 'inflight-source', 'task_id': 'task-a'}}})
        self.model.block = True
        self.model.answer = {'title': marker, 'steps': [{'command_id': 'axx.artifact.write',
            'inputs': {'path': 'unapproved-derived.txt', 'content': marker}}], 'goal_spec': {'intent': marker}}
        result, failures = [], []
        def propose():
            try:
                result.append(self.learning.propose('Prepara una entrega local', operation_id='inflight-forget',
                    project_id='project-a', conversation_id='task-a'))
            except Exception as exc:
                failures.append(exc)
        worker = threading.Thread(target=propose)
        worker.start()
        try:
            self.assertTrue(self.model.entered.wait(5), 'The local model was not entered')
            self.assertIn(marker, self.model.calls[0]['messages'][-1]['content'])
            self.learning.invalidate_context('project-a', {'source_id': 'inflight-source', 'forget': True})
        finally:
            self.model.release.set()
            worker.join(8)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        persisted = self.learning.get('inflight-forget')
        self.assertEqual(persisted['state'], 'needs_input', persisted)
        self.assertNotIn('model_data', persisted)
        self.assertNotIn(marker, json.dumps(persisted, ensure_ascii=False))
        self.assertEqual(persisted['steps'], [])
        self.assertFalse(persisted.get('approved_hash'))
        self.assertEqual(self.learning.execute('inflight-forget', approved=True)['state'], 'needs_input')
        self.assertFalse((self.executor.workspace_root / 'unapproved-derived.txt').exists())
        self.assertEqual(self.commands.operations(), [])
        self.assertEqual(self.executor.list_operations(), [])

    def test_prompt_caps_total_lessons_and_filters_consent_and_task_before_limit(self):
        failure = self.hash_receipt()
        self.assertEqual(failure['state'], 'succeeded', failure)
        failure = self.hash_receipt(fail=True)
        self.assertEqual(failure['state'], 'failed', failure)
        consented = []
        for index in range(3):
            item = self.learning.skills.record_lesson({'operation_id': failure['operation_id'],
                'hypothesis': 'reference allowed-' + str(index) + ' ' + 'x' * 850,
                'project_id': 'project-a', 'task_id': 'task-a', 'allow_provider': True})
            consented.append(item['id'])
        for index in range(4):
            self.learning.skills.record_lesson({'operation_id': failure['operation_id'],
                'hypothesis': 'reference local-only-' + str(index), 'project_id': 'project-a', 'task_id': 'task-a'})
        foreign = self.hash_receipt(task='task-b', fail=True)
        self.learning.skills.record_lesson({'operation_id': foreign['operation_id'], 'hypothesis': 'reference FOREIGN_LESSON',
            'project_id': 'project-a', 'task_id': 'task-b', 'allow_provider': True})
        local = self.learning.skills.lessons('reference', project_id='project-a', task_id='task-a')
        self.assertEqual(len(local), 3)
        self.assertTrue(all(item['allow_provider'] is False for item in local))
        lessons = self.payload({}, task='task-a', text='reference')['previous_action']['incident_references']['lessons']
        self.assertTrue(lessons)
        self.assertLessEqual(len(lessons), 3)
        self.assertLessEqual(len(json.dumps(lessons, ensure_ascii=False)), 3500)
        self.assertTrue(all(item['id'] in consented and item['allow_provider'] is True and item['task_id'] == 'task-a'
                            for item in lessons))
        self.assertTrue(all(item['permissions_granted'] is False and item['cause_confirmed'] is False for item in lessons))


if __name__ == '__main__':
    unittest.main()
