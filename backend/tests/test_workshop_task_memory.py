"""Workshop approvals bind original callers and transitive memory without replaying effects."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.capability_workshop import CapabilityWorkshop, _hash
from backend.commands import CommandService
from backend.memory import task_memory
from backend.tests.test_capability_workshop import definition
from backend.tests.test_generated_commands import transform


class WorkshopTaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, None)
        self.commands.learning = self.learning
        self.workshop = CapabilityWorkshop(self.learning)
        self.db = sqlite3.connect(self.root / 'state.db')
        self.a, self.b, self.c = (task_memory.snapshot(self.db, task) for task in ('a', 'b', 'c'))

    def tearDown(self):
        self.db.close()
        self.workshop.close()
        self.learning.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    @staticmethod
    def ref(item): return item['id'], item['revision'], item['digest']

    def pending(self, task='a'):
        self.db.execute('BEGIN IMMEDIATE')
        state = task_memory.begin_forget(self.db, task, 'forget-' + task, 0)
        self.db.commit()
        return state

    def finish(self, state):
        result = self.workshop.forget_task(state['task_id'])
        self.db.execute('BEGIN IMMEDIATE')
        task_memory.finish_forget(self.db, state, result)
        self.db.commit()
        return result

    def file_definition(self, path='scoped.txt'):
        return definition('axx.artifact.write', {'path': path, 'content': 'explicit local fixture'})

    def validated(self, scope, path='scoped.txt'):
        item = self.workshop.create(self.file_definition(path), memory_scope=scope)
        self.workshop.approve(*self.ref(item), confirmed=True, memory_scope=scope)
        plan = self.workshop.prepare_validation(*self.ref(item), conversation_id=scope['task_id'], memory_scope=scope)
        done = self.learning.execute(plan['operation_id'], approved=True, memory_scope=scope)
        self.assertEqual(done['state'], 'succeeded')
        return self.workshop.get(item['id'])

    def test_a_workflow_revised_in_b_keeps_dependencies_through_real_file_publication(self):
        original = self.workshop.create(self.file_definition(), memory_scope=self.a, _memory_dependencies=[self.c])
        revised = self.workshop.revise(*self.ref(original), self.file_definition(), memory_scope=self.b)
        self.assertEqual(revised['memory_scope'], self.b)
        self.assertEqual({ref['task_id'] for ref in revised['memory_dependencies']}, {'a', 'c'})
        self.workshop.approve(*self.ref(revised), confirmed=True, memory_scope=self.b)
        plan = self.workshop.prepare_validation(*self.ref(revised), conversation_id='b', memory_scope=self.b)
        self.assertEqual({ref['task_id'] for ref in plan['memory_dependencies']}, {'a', 'c'})
        self.assertEqual(self.learning.execute(plan['operation_id'], approved=True, memory_scope=self.b)['state'], 'succeeded')
        active = self.workshop.activate(*self.ref(revised), memory_scope=self.b)
        skill = self.learning.skills.get(active['skill_id'])
        self.assertEqual({ref['task_id'] for ref in skill['memory_dependencies']}, {'a', 'c'})
        evidence = json.loads(self.db.execute('SELECT payload FROM skill_evidence WHERE id=?', (skill['id'],)).fetchone()[0])
        self.assertEqual({ref['task_id'] for ref in evidence['memory_dependencies']}, {'a', 'c'})
        independent = self.workshop.create(self.file_definition('independent.txt'), memory_scope=self.b)
        independent_bytes = self.db.execute('SELECT payload FROM capability_revisions WHERE id=?', (independent['id'],)).fetchone()[0]
        receipts = self.commands.operations()
        self.finish(self.pending())
        self.assertTrue(self.workshop.get(revised['id'])['requires_review'])
        self.assertEqual(self.db.execute('SELECT payload FROM capability_revisions WHERE id=?', (independent['id'],)).fetchone()[0], independent_bytes)
        self.assertEqual(self.commands.operations(), receipts)
        self.assertEqual((self.executor.workspace_root / 'scoped.txt').read_text(), 'explicit local fixture')

    def test_all_four_mutators_reject_old_client_while_source_a_is_current(self):
        first = self.workshop.create(definition(), memory_scope=self.a)
        second = self.workshop.revise(*self.ref(first), definition(), memory_scope=self.a)
        self.workshop.approve(*self.ref(second), confirmed=True, memory_scope=self.a)
        before = self.db.execute('SELECT payload FROM capability_revisions WHERE id=? AND revision=2', (first['id'],)).fetchone()[0]
        self.finish(self.pending('b'))
        calls = [(self.workshop.validate, {}), (self.workshop.approve, {'confirmed': True}),
                 (self.workshop.activate, {}), (self.workshop.rollback, {'target_revision': 1})]
        for method, kwargs in calls:
            with self.subTest(method=method.__name__), self.assertRaises(ValueError):
                method(*self.ref(second), memory_scope=self.b, **kwargs)
        self.assertEqual(self.db.execute('SELECT payload FROM capability_revisions WHERE id=? AND revision=2', (first['id'],)).fetchone()[0], before)
        self.assertEqual(self.workshop.validate(*self.ref(second), memory_scope=task_memory.snapshot(self.db, 'b'))['status'], 'static_validated')
        self.assertEqual(self.workshop.revoke(*self.ref(second))['state'], 'revoked')

    def test_validate_interpreter_runs_without_sql_writer_and_rechecks_caller_before_save(self):
        item = self.workshop.create(transform(), memory_scope=self.a)
        from backend.generated_commands import run_tests
        def delayed(*args):
            self.assertFalse(self.learning.db.in_transaction)
            self.pending('b')
            return run_tests(*args)
        with patch('backend.capability_workshop.run_tests', side_effect=delayed):
            with self.assertRaises(ValueError): self.workshop.validate(*self.ref(item), memory_scope=self.b)
        self.assertNotIn('tested_digest', self.workshop.get(item['id'])['validation'])

    def test_activate_late_caller_rejection_rolls_back_published_skill_and_active_head(self):
        item = self.validated(self.a)
        receipts = self.workshop._receipts
        def delayed(*args):
            result = receipts(*args)
            self.pending('b')
            return result
        with patch.object(self.workshop, '_receipts', side_effect=delayed):
            with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item), memory_scope=self.b)
        self.assertIsNone(self.workshop.get(item['id'])['active_revision'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM skill_versions WHERE id=?', (item['skill_id'],)).fetchone()[0], 0)

    def test_approve_and_rollback_recheck_original_caller_after_local_validation(self):
        first = self.workshop.create(definition(), memory_scope=self.a)
        validate = self.workshop.validate
        def delayed(*args, **kwargs):
            result = validate(*args, **kwargs)
            self.pending('b')
            return result
        with patch.object(self.workshop, 'validate', side_effect=delayed):
            with self.assertRaises(ValueError): self.workshop.approve(*self.ref(first), confirmed=True, memory_scope=self.b)
        self.assertIsNone(self.workshop.get(first['id'])['approval'])
        second = self.workshop.revise(*self.ref(first), definition(), memory_scope=self.a)
        definition_check = self.workshop._definition
        def delayed_definition(*args):
            result = definition_check(*args)
            self.pending('c')
            return result
        with patch.object(self.workshop, '_definition', side_effect=delayed_definition):
            with self.assertRaises(ValueError): self.workshop.rollback(*self.ref(second), target_revision=1, memory_scope=self.c)
        self.assertEqual(self.workshop.get(first['id'])['revision'], 2)

    def test_rollback_inherits_old_definition_and_current_parent_without_refreshing_refs(self):
        first = self.workshop.create(definition(), memory_scope=self.a, _memory_dependencies=[self.c])
        second = self.workshop.revise(*self.ref(first), definition() | {'title': 'B edit'}, memory_scope=self.b)
        restored = self.workshop.rollback(*self.ref(second), target_revision=1, memory_scope=self.c)
        self.assertEqual(restored['memory_scope'], self.c)
        self.assertEqual({ref['task_id'] for ref in restored['memory_dependencies']}, {'a', 'b'})
        self.pending('a')
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(restored), confirmed=True, memory_scope=self.c)

    def test_new_epoch_can_learn_validate_and_publish_a_new_file_workflow(self):
        self.finish(self.pending())
        scope = task_memory.snapshot(self.db, 'a')
        item = self.validated(scope, 'fresh.txt')
        active = self.workshop.activate(*self.ref(item), memory_scope=scope)
        self.assertEqual(self.learning.skills.get(active['skill_id'])['memory_scope'], {'task_id': 'a', 'generation': 1})
        self.assertTrue((self.executor.workspace_root / 'fresh.txt').is_file())

    def test_scoped_digest_covers_refs_and_legacy_digest_is_unchanged(self):
        legacy = self.workshop.create(definition())
        expected = _hash({key: legacy[key] for key in ('id', 'revision', 'definition', 'project_id')} |
                         {'environment': legacy['validation']['environment']})
        self.assertEqual(legacy['digest'], expected)
        scoped = self.workshop.create(definition(), memory_scope=self.a, _memory_dependencies=[self.b])
        for field, value in [('memory_scope', self.c), ('memory_context_id', 'changed'), ('memory_context_id', ''), ('memory_dependencies', [])]:
            changed = copy.deepcopy(scoped)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.workshop._integrity(changed)

    def test_generation_does_not_send_private_dependencies_upstream_and_rejects_late_a(self):
        case = self
        class Provider:
            supports_task_memory = True
            def generate_capability(provider, request):
                self.assertFalse(case.learning.db.in_transaction)
                self.assertNotIn('memory_dependencies', request)
                self.assertNotIn('_memory_dependencies', request)
                self.assertNotIn('memory_dependencies', request['messages'][1]['content'])
                case.pending('a')
                return {'ok': True, 'message': {'content': json.dumps(definition())}}
        self.workshop.provider = Provider()
        with self.assertRaises(ValueError):
            self.workshop.generate('local proposal', provider_name='@codex', model='fixture', conversation_id='b',
                                  memory_scope=self.b, _memory_dependencies=[self.a])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM capability_revisions').fetchone()[0], 0)

    def chat_b(self):
        with self.db:
            self.db.execute('CREATE TABLE chat_conversations(id TEXT PRIMARY KEY,connect_id TEXT,memory_context_required INTEGER)')
            self.db.execute('INSERT INTO chat_conversations VALUES (?,?,0)', ('b', 'before'))

    def rotate_b(self):
        with self.db:
            self.db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?', ('after', 'b'))

    def test_independent_b_knowledge_survives_context_rotation_but_old_mutator_request_does_not(self):
        self.chat_b()
        item = self.workshop.create(transform(), memory_scope=self.b, memory_context_id='before')
        self.workshop.validate(*self.ref(item), memory_scope=self.b, memory_context_id='before')
        self.workshop.approve(*self.ref(item), confirmed=True, memory_scope=self.b, memory_context_id='before')
        self.rotate_b()
        self.assertFalse(self.workshop.get(item['id'])['requires_review'])
        with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item), memory_scope=self.b, memory_context_id='before')
        active = self.workshop.activate(*self.ref(item), memory_scope=self.b, memory_context_id='after')
        self.assertEqual(active['state'], 'active')
        self.assertEqual(len(self.workshop.active_generated_records()), 1)
        command = self.commands.prepare(active['generated_command_id'], {'text': ' AXX  FUNCIONA '},
            conversation_id='b', memory_scope=self.b, memory_context_id='after')
        result = self.commands.execute(command['operation_id'], approved=True)
        self.assertEqual(result['state'], 'succeeded')
        self.assertEqual(result['output']['result'], 'axx funciona')
        self.assertEqual(task_memory.snapshot(self.db, 'b'), self.b)

    def test_generated_b_command_rejects_its_a_dependency_before_cleanup(self):
        first = self.workshop.create(transform(), memory_scope=self.a)
        item = self.workshop.revise(*self.ref(first), transform(), memory_scope=self.b)
        self.workshop.validate(*self.ref(item), memory_scope=self.b)
        self.workshop.approve(*self.ref(item), confirmed=True, memory_scope=self.b)
        active = self.workshop.activate(*self.ref(item), memory_scope=self.b)
        self.pending('a')
        self.assertEqual(self.workshop.active_generated_records(), [])
        with self.assertRaises(ValueError):
            self.commands.prepare(active['generated_command_id'], {'text': ' old '}, conversation_id='b', memory_scope=self.b)
        self.assertEqual(self.commands.operations(), [])

    def test_generation_callback_keeps_its_context_guard_when_durable_b_scope_did_not_change(self):
        self.chat_b()
        case = self
        class Model:
            def route(model, request):
                case.rotate_b()
                return {'ok': True, 'message': {'content': json.dumps(definition())}}
        self.workshop.adapter = Model()
        with self.assertRaises(ValueError):
            self.workshop.generate('fixture', conversation_id='b', memory_scope=self.b, memory_context_id='before')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM capability_revisions').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
