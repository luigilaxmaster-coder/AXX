"""Mission views use the existing persisted plan and actual executor receipts."""
from pathlib import Path
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.chat_store import ChatStore


class MissionTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Native NTFS compensation')
    def test_quarantined_delivery_blocks_dependency_until_verified_restore_without_repeating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            try:
                source = learning.prepare_steps('Crear origen', [{'command_id': 'axx.artifact.write',
                    'inputs': {'path': 'source.txt', 'content': 'origen'}}], project_id='a')
                completed = learning.execute(source['operation_id'], approved=True)
                self.assertTrue(completed['mission']['completed'])
                operation = completed['step_records'][0]['operation_id']
                original = commands.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?', (operation,)).fetchone()[0]
                def compensate(key):
                    preview = commands.compensation_preview(operation)
                    self.assertTrue(preview['available'], preview)
                    prepared = commands.prepare_compensation(operation, preview['source_receipt_hash'],
                        preview['compensation']['revision'], action=preview['action'], operation_id=key)
                    result = commands.execute(prepared['operation_id'], approved=True)
                    self.assertEqual(result['state'], 'succeeded', result)
                compensate('quarantine-source')
                current = learning.get(source['operation_id'])
                self.assertEqual(current['state'], 'succeeded')
                self.assertFalse(current['mission']['completed'])
                self.assertEqual(current['mission']['pending_steps'], [0])
                self.assertEqual(current['mission']['blockers'][0]['state'], 'quarantined')
                self.assertFalse(learning.list_plans('a')[0]['mission']['completed'])
                chats = ChatStore(executor.db_path)
                try:
                    recovered = {row['operation_id']: row for row in chats.operations()}
                    self.assertFalse(recovered[source['operation_id']]['mission']['completed'])
                    self.assertFalse(recovered[operation]['compensation']['available_current'])
                finally:
                    chats.close()
                guarded = learning.prepare_steps('Comprobar dependencia antes del efecto', [{'command_id': 'axx.artifact.write',
                    'inputs': {'path': 'guarded.txt', 'content': 'no debe escribirse'}}], project_id='a')
                guarded = learning.link_dependencies(guarded['operation_id'], [source['operation_id']], guarded['plan_hash'])
                guarded.update(state='running', approved_hash=guarded['plan_hash'])
                record = guarded['step_records'][0]
                record.update(state='running', resolved_inputs=guarded['steps'][0]['inputs'])
                learning._save(guarded)
                commands.prepare('axx.artifact.write', guarded['steps'][0]['inputs'], operation_id=record['operation_id'])
                rejected = commands.execute(record['operation_id'], approved=True)
                self.assertEqual(rejected['error']['code'], 'DISPATCH_REJECTED', rejected)
                self.assertFalse((executor.workspace_root / 'guarded.txt').exists())
                target = learning.prepare_steps('Crear entrega', [{'command_id': 'axx.artifact.write',
                    'inputs': {'path': 'target.txt', 'content': 'entrega'}}], project_id='a')
                target = learning.link_dependencies(target['operation_id'], [source['operation_id']], target['plan_hash'])
                waiting = learning.execute(target['operation_id'], approved=True)
                self.assertEqual(waiting['state'], 'waiting_dependency')
                self.assertFalse((executor.workspace_root / 'target.txt').exists())
                compensate('restore-source')
                restored = learning.get(source['operation_id'])
                self.assertTrue(restored['mission']['completed'])
                self.assertTrue(restored['mission']['artifact_compensations'][0]['verification']['verified_at'])
                results = learning.retry_dependencies()
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0]['mission']['completed'], results)
                self.assertEqual((executor.workspace_root / 'source.txt').read_text(), 'origen')
                self.assertEqual((executor.workspace_root / 'target.txt').read_text(), 'entrega')
                self.assertEqual(commands.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?', (operation,)).fetchone()[0], original)
                self.assertEqual(sum(row['tool_name'] == 'file_artifact_writer' and row['state'] == 'succeeded'
                                     for row in executor.list_operations()), 2)
            finally:
                learning.close(); commands.close(); executor.close()

    def test_dispatch_rechecks_transitively_expired_context_after_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            try:
                with patch('backend.memory.skill_memory.time.time', return_value=1000):
                    first = learning.update_context('a', {'current_file':'source', 'context_meta':{
                        'current_file':{'kind':'observed','source_id':'source','expires_at':1001}}})
                    child = learning.update_context('a', {'current_folder':'derived', 'context_meta':{
                        'current_folder':{'kind':'inferred','depends_on':[{'field':'current_file','revision':first['context_meta']['current_file']['revision']}]}}})
                plan = learning.prepare_steps('Crear entrega', [{'command_id':'axx.artifact.write',
                    'inputs':{'path':'guarded.txt','content':'approved'}}], project_id='a')
                plan['context_dependencies'] = [{'project_id':'a','field':'current_folder','revision':child['context_meta']['current_folder']['revision']}]
                plan['plan_hash'] = learning._plan_hash(plan)
                plan.update(state='running', approved_hash=plan['plan_hash'])
                record = plan['step_records'][0]
                record.update(state='running', resolved_inputs=plan['steps'][0]['inputs'])
                learning._save(plan)
                commands.prepare('axx.artifact.write', plan['steps'][0]['inputs'], operation_id=record['operation_id'])
                result = commands.execute(record['operation_id'], True)
                self.assertEqual(result['state'], 'failed', result)
                self.assertEqual(result['error']['code'], 'DISPATCH_REJECTED')
                self.assertFalse((executor.workspace_root / 'guarded.txt').exists())
            finally:
                learning.close(); commands.close(); executor.close()

    def test_dependency_waits_for_verified_event_and_never_repeats_source(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            try:
                source = learning.prepare_steps('Crear origen', [{'command_id': 'axx.artifact.write',
                    'inputs': {'path': 'source.txt', 'content': 'origen'}}], project_id='a')
                target = learning.prepare_steps('Crear entrega', [{'command_id': 'axx.artifact.write',
                    'inputs': {'path': 'target.txt', 'content': 'entrega'}}], project_id='a')
                target = learning.link_dependencies(target['operation_id'], [source['operation_id']], target['plan_hash'])
                waiting = learning.execute(target['operation_id'], approved=True)
                self.assertEqual(waiting['state'], 'waiting_dependency')
                self.assertEqual(executor.list_operations(), [])
                self.assertEqual(learning.retry_dependencies(), [])
                learning.close()
                learning = ActionLearning(commands, None)
                self.assertEqual(learning.get(target['operation_id'])['state'], 'waiting_dependency')
                self.assertEqual(learning.execute(source['operation_id'], approved=True)['state'], 'succeeded')
                results = learning.retry_dependencies()
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0]['mission']['completed'], results)
                self.assertEqual((executor.workspace_root / 'target.txt').read_text(), 'entrega')
                count = len(executor.list_operations())
                self.assertEqual(learning.retry_dependencies(), [])
                self.assertEqual(len(executor.list_operations()), count)
            finally:
                learning.close(); commands.close(); executor.close()

    def test_dependency_rejects_cycles_cross_project_and_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            try:
                def prepare(name, project='a'):
                    return learning.prepare_steps('Crear ' + name, [{'command_id': 'axx.artifact.write',
                        'inputs': {'path': name + '.txt', 'content': name}}], project_id=project)
                a, b, foreign = prepare('a'), prepare('b'), prepare('foreign', 'b')
                with self.assertRaises(ValueError): learning.link_dependencies(a['operation_id'], [foreign['operation_id']], a['plan_hash'])
                a = learning.link_dependencies(a['operation_id'], [b['operation_id']], a['plan_hash'])
                with self.assertRaises(ValueError): learning.link_dependencies(b['operation_id'], [a['operation_id']], b['plan_hash'])
                learning.execute(a['operation_id'], approved=True)
                b['goal_revision'] += 1
                learning._save(b)
                self.assertEqual(learning.retry_dependencies(), [])
                self.assertEqual(executor.list_operations(), [])
                step = learning.get(a['operation_id'])['step_records'][0]
                prepared = commands.prepare('axx.artifact.write', {'path': 'a.txt', 'content': 'a'}, operation_id=step['operation_id'])
                rejected = commands.execute(prepared['operation_id'], approved=True)
                self.assertEqual(rejected['state'], 'failed', rejected)
                self.assertFalse((executor.workspace_root / 'a.txt').exists())
            finally:
                learning.close(); commands.close(); executor.close()

    def test_slow_plan_recovery_does_not_stall_local_anticipation(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            entered, release, continued = threading.Event(), threading.Event(), threading.Event()
            calls = []
            def slow():
                calls.append(1)
                entered.set()
                release.wait(15)
            class LocalPolicy:
                def tick(self):
                    if entered.is_set(): continued.set()
            learning.anticipation = LocalPolicy()
            try:
                with patch.object(learning, 'retry_waiting', side_effect=slow):
                    learning.start_recovery()
                    self.assertTrue(continued.wait(13), 'Local anticipation was blocked by provider recovery')
                    self.assertEqual(len(calls), 1, 'An in-flight recovery must not be queued twice')
                    release.set()
            finally:
                release.set()
                learning.close()
                commands.close()
                executor.close()

    def test_mission_persists_goal_scope_budget_and_stops_at_verified_result(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            try:
                plan = learning.prepare_steps('Guardar el ensayo y comprobarlo', [
                    {'command_id': 'axx.artifact.write', 'inputs': {'path': 'mission.txt', 'content': 'Ensayo'}},
                    {'command_id': 'axx.file.sha256', 'inputs': {}, 'bindings': {'path': {'step': 0, 'path': ['output', 'path']}}}
                ], conversation_id='mission-chat', project_id='project-a')
                mission = plan['mission']
                self.assertEqual(mission['scope'], {'project_id': 'project-a', 'task_id': 'mission-chat', 'resources': []})
                self.assertEqual(mission['pending_steps'], [0, 1])
                self.assertFalse(mission['completed'])
                self.assertEqual(mission['budget']['model_calls_used'], 0)
                completed = learning.execute(plan['operation_id'], approved=True)
                self.assertEqual(completed['state'], 'succeeded', completed)
                self.assertTrue(completed['mission']['completed'])
                self.assertEqual(completed['mission']['verified_steps'], [0, 1])
                self.assertEqual(completed['mission']['pending_steps'], [])
                self.assertFalse(completed['mission']['user_confirmed_usefulness'])
                count = len(executor.list_operations())
                learning.close()
                learning = ActionLearning(commands, None)
                restored = learning.get(plan['operation_id'])
                self.assertEqual(restored['mission']['mission_id'], plan['operation_id'])
                self.assertTrue(restored['mission']['completed'])
                learning.execute(plan['operation_id'], approved=True)
                self.assertEqual(len(executor.list_operations()), count)
            finally:
                learning.close()
                commands.close()
                executor.close()

    def test_dispatch_and_acceptance_do_not_complete_mission(self):
        plan = {'operation_id': 'm', 'request': 'Ensayo', 'state': 'running', 'steps': [{}],
                'step_records': [{'state': 'succeeded', 'result': {'state': 'succeeded', 'postconditions_passed': False}}],
                'postconditions_passed': True, 'plan_hash': 'p', 'approved_hash': 'p'}
        mission = ActionLearning._mission(plan)
        self.assertFalse(mission['completed'])
        self.assertEqual(mission['pending_steps'], [0])
        self.assertTrue(mission['permission']['exact_plan_approved'])
        self.assertFalse(mission['permission']['automatic_future_plans_authorized'])
