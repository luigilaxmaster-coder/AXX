"""Explicit resource roles use existing contexts, M1 versions and real temp files."""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning, SOURCE_PLANNING_READY
from backend.goal_criteria import input_version_lease
from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import ApprovalRequired, CommandService
from backend.memory import task_memory
from backend.memory.procedural_memory import get_action_env_fingerprint
from backend.memory.skill_memory import NeedsInput


class NoModel:
    def __init__(self): self.calls = 0
    def route(self, request):
        self.calls += 1
        raise AssertionError('Explicit resource binding must not infer')


class ResourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = NoModel()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        self.commands.mission_guard = self.learning.assert_dispatch_context
        self.chats = ChatStore(self.root / 'state.db')
        self.tasks = [self.chats.mutate('create', {'title': name})['id'] for name in ('Source A', 'Source B', 'Review')]
        self.paths, self.selectors = {}, {}
        for role, project, owner, data in zip(('path', 'other_path'), ('project-a', 'project-b'), self.tasks, (b'left\x00\xff', b'right\x00\xff')):
            path = self.executor.workspace_root / project / 'input.bin'
            path.parent.mkdir()
            path.write_bytes(data)
            self.paths[role] = path
            context = self.learning.update_context(project, {'current_file': str(path),
                'context_meta': {'current_file': {'kind': 'confirmed_user', 'task_id': owner, 'expires_at': time.time() + 3600}}},
                **self.scope(owner))
            self.selectors[role] = {'project_id': project, 'field': 'current_file', 'revision': context['context_meta']['current_file']['revision']}
        self.skill_id = 'resource.compare'
        owner = self.tasks[2]
        self.learning.skills.insert({'id': self.skill_id, 'version': 1, 'trigger': self.skill_id, 'title': 'Comparación explícita',
            'schema': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'other_path': {'type': 'string'}}, 'required': ['path', 'other_path']},
            'templates': [{'command_id': 'axx.file.compare', 'inputs': {'path': '{{path}}', 'other_path': '{{other_path}}'}}],
            'examples': [], 'project_id': '', 'environment': get_action_env_fingerprint(['axx.file.compare']),
            'checks': ['executor_postconditions'], 'provenance': {}, 'created_at': time.time(), 'executable': True,
            'origin_task_id': owner, **self.scope(owner)})

    def tearDown(self):
        self.learning.close(); self.chats.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    def scope(self, owner):
        row = self.chats.get(owner)
        return {'memory_scope': copy.deepcopy(row['memory_scope']), 'memory_context_id': row['context_id']}

    def propose(self, **changes):
        args = {'text': self.skill_id, 'project_id': 'review-project', 'conversation_id': self.tasks[2],
            'resource_bindings': copy.deepcopy(self.selectors), **self.scope(self.tasks[2])}
        args.update(changes)
        return self.learning.propose(**args)

    def raw(self, plan):
        return json.loads(self.learning.db.execute('SELECT payload FROM learning_plans WHERE id=?', (plan['operation_id'],)).fetchone()[0])

    def store(self, plan):
        with self.learning.db:
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(plan), plan['operation_id']))

    def test_explicit_same_basename_two_roles_need_hash_approval_and_compare_real_bytes(self):
        plan = self.propose()
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        self.assertEqual(self.model.calls, 0)

        self.assertFalse(SOURCE_PLANNING_READY)
        self.assertEqual(plan['steps'], [{'command_id': 'axx.file.compare', 'inputs': {role: str(path) for role, path in self.paths.items()}}])
        for role, binding in plan['resource_bindings'].items():
            self.assertEqual(binding['project_id'], self.selectors[role]['project_id'])
            self.assertEqual(binding['input_version']['sha256'], hashlib.sha256(self.paths[role].read_bytes()).hexdigest())
            self.assertFalse(Path(binding['input_version']['path']).is_absolute())
        self.assertEqual({ref['task_id'] for ref in plan['memory_dependencies']}, set(self.tasks[:2]))
        with self.assertRaises(ApprovalRequired): self.learning.execute(plan['operation_id'])
        with self.assertRaises(ValueError): self.learning.execute(plan['operation_id'], approved=True)
        done = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'])
        if os.name != 'nt':
            self.assertFalse(done['postconditions_passed'])
            self.assertEqual(self.executor.list_operations(), [])
            return
        self.assertEqual(done['state'], 'succeeded', done)
        self.assertFalse(done['results'][0]['output']['equal'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.learning.context('review-project')['last_inputs'], {})
        self.assertEqual(self.learning.execute(plan['operation_id'], True, plan_hash=plan['plan_hash'])['state'], 'succeeded')
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_present_empty_malformed_literal_or_non_exact_skill_never_falls_back(self):
        bad = ({}, {'path': self.selectors['path']}, self.selectors | {'extra': {}},
            self.selectors | {'path': self.selectors['path'] | {'path': str(self.paths['path'])}},
            self.selectors | {'path': self.selectors['path'] | {'revision': True}})
        for selectors in bad:
            with self.subTest(selectors=selectors): self.assertEqual(self.propose(resource_bindings=selectors)['state'], 'needs_input')
        for text in ('este y el otro', 'otra vez', 'Comparación explícita'):
            self.assertEqual(self.propose(text=text)['state'], 'needs_input')
        self.assertEqual(self.propose(inputs={'path': str(self.paths['path'])})['state'], 'needs_input')
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.executor.list_operations(), [])

    def test_idempotence_keeps_versions_and_seals_roles_and_incoming_selectors(self):
        plan = self.propose(operation_id='explicit-id')
        self.assertEqual(self.propose(operation_id='explicit-id')['resource_bindings'], plan['resource_bindings'])
        swapped = {'path': self.selectors['other_path'], 'other_path': self.selectors['path']}
        with self.assertRaises(ValueError): self.propose(operation_id='explicit-id', resource_bindings=swapped)
        altered = copy.deepcopy(plan)
        altered['resource_bindings'] = {'path': altered['resource_bindings']['other_path'], 'other_path': altered['resource_bindings']['path']}
        self.assertNotEqual(self.learning._plan_hash(altered), plan['plan_hash'])
        self.assertEqual(self.model.calls, 0)

    def test_context_change_invalidates_approval_without_recapture_and_ordinary_scope_stays_strict(self):
        plan = self.propose()
        before = copy.deepcopy(plan['resource_bindings'])
        owner = self.tasks[0]
        self.learning.update_context('project-a', {'current_file': str(self.paths['path']),
            'context_meta': {'current_file': {'kind': 'confirmed_user', 'task_id': owner}}}, **self.scope(owner))
        changed = self.learning.get(plan['operation_id'])
        self.assertEqual(changed['state'], 'needs_input')
        self.assertIsNone(changed['approved_hash'])
        self.assertEqual(changed['resource_bindings'], before)
        self.assertEqual(self.model.calls, 0)
        ordinary = {'project_id': 'review-project', 'conversation_id': self.tasks[2], 'context_dependencies': [self.selectors['path']]}
        self.assertIsNotNone(self.learning._context_error(ordinary, self.learning.context('project-a')))

    def test_ttl_and_bytes_or_identity_change_abstain_without_refreshing_snapshot(self):
        plan = self.propose()
        before = copy.deepcopy(plan['resource_bindings'])
        expires = before['path']['expires_at']
        with patch('backend.action_learning.time.time', return_value=expires + 1):
            with self.assertRaises(NeedsInput): self.learning._assert_resource_bindings(plan)
        source = self.paths['path']; stamp = source.stat()
        source.write_bytes(b'x' * stamp.st_size)
        os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        done = self.learning.execute(plan['operation_id'], True, plan_hash=plan['plan_hash'])
        self.assertEqual(done['state'], 'needs_input', done)
        self.assertEqual(done['resource_bindings'], before)
        self.assertEqual(self.executor.list_operations(), [])

    def test_same_bytes_replacement_and_hardlinks_are_not_two_new_resources(self):
        plan = self.propose()
        source = self.paths['path']; payload = source.read_bytes()
        replacement = source.with_name('replacement.bin'); replacement.write_bytes(payload); os.replace(replacement, source)
        with self.assertRaises(NeedsInput): self.learning._assert_resource_bindings(plan)
        other = self.paths['other_path']; other.unlink()
        try: os.link(source, other)
        except OSError: self.skipTest('Filesystem does not provide hardlinks')
        self.assertEqual(self.propose()['state'], 'needs_input')
        self.assertEqual(self.executor.list_operations(), [])

    def test_unknown_owner_and_unconfirmed_fields_do_not_create_scope_or_dispatch(self):
        unknown = 'unpersisted-resource-owner'
        self.learning.skills.update_context('project-a', {'current_file': str(self.paths['path']),
            'context_meta': {'current_file': {'kind': 'confirmed_user', 'task_id': unknown}}})
        ref = self.learning.context('project-a')['context_meta']['current_file']['revision']
        selectors = self.selectors | {'path': self.selectors['path'] | {'revision': ref}}
        self.assertEqual(self.propose(resource_bindings=selectors)['state'], 'needs_input')
        self.assertIsNone(self.learning.db.execute('SELECT 1 FROM memory_task_scopes WHERE task_id=?', (unknown,)).fetchone())
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.model.calls, 0)
        for kind in ('observed', 'inferred'):
            owner = self.tasks[0]
            context = self.learning.update_context('project-a', {'current_file': str(self.paths['path']),
                'context_meta': {'current_file': {'kind': kind, 'task_id': owner}}}, **self.scope(owner))
            selectors = self.selectors | {'path': self.selectors['path'] | {'revision': context['context_meta']['current_file']['revision']}}
            self.assertEqual(self.propose(resource_bindings=selectors)['state'], 'needs_input')
        self.assertEqual(self.model.calls, 0)

    def test_failed_duplicate_capture_still_inherits_original_memory_before_forgetting(self):
        owner = self.tasks[1]
        context = self.learning.update_context('project-b', {'current_file': str(self.paths['path']),
            'context_meta': {'current_file': {'kind': 'confirmed_user', 'task_id': owner}}}, **self.scope(owner))
        selectors = self.selectors | {'other_path': self.selectors['other_path'] | {'revision': context['context_meta']['current_file']['revision']}}
        plan = self.propose(resource_bindings=selectors)
        self.assertEqual(plan['state'], 'needs_input')
        self.assertEqual({ref['task_id'] for ref in plan['memory_dependencies']}, set(self.tasks[:2]))
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            task_memory.begin_forget(self.learning.db, self.tasks[0], 'forget-failed-capture', 0)
        hidden = self.learning.get(plan['operation_id'])
        self.assertTrue(hidden['memory_forgotten'])
        self.assertNotIn('resource_bindings', hidden)
        self.assertNotIn('resource_binding_selectors', hidden)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.model.calls, 0)

    def test_explicit_entry_rejects_outside_directory_missing_and_overlimit_before_hash(self):
        outside = self.root / 'outside.bin'; outside.write_bytes(b'outside')
        directory = self.executor.workspace_root / 'directory'; directory.mkdir()
        missing = self.executor.workspace_root / 'missing.bin'
        oversized = self.executor.workspace_root / 'oversized.bin'
        limit = self.learning._goal_file_limit({'operation_id': 'limit-probe', 'conversation_id': self.tasks[2], 'project_id': 'review-project'})
        with oversized.open('wb') as stream: stream.truncate(limit + 1)
        for path in (outside, directory, missing, oversized):
            with self.subTest(path=path):
                context = self.learning.update_context('project-a', {'current_file': str(path),
                    'context_meta': {'current_file': {'kind': 'confirmed_user', 'task_id': self.tasks[0]}}}, **self.scope(self.tasks[0]))
                selectors = self.selectors | {'path': self.selectors['path'] | {'revision': context['context_meta']['current_file']['revision']}}
                with patch('backend.goal_criteria.file_inspection.hash_file', side_effect=AssertionError('Unsafe/oversized input must fail before hashing')):
                    self.assertEqual(self.propose(resource_bindings=selectors)['state'], 'needs_input')
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.model.calls, 0)

    @unittest.skipUnless(os.name == 'nt', 'Native read lease only exists on Windows')
    def test_ttl_expiring_after_native_handles_invalidates_approval_without_quarantine(self):
        plan = self.propose()
        before = copy.deepcopy(plan['resource_bindings'])
        expiry = before['path']['expires_at']
        @contextmanager
        def expire_after_handles(versions, root, cancelled, **kwargs):
            with input_version_lease(versions, root, cancelled, **kwargs):
                with patch('backend.action_learning.time.time', return_value=expiry + 1):
                    yield
        with patch('backend.action_learning.input_version_lease', side_effect=expire_after_handles):
            done = self.learning.execute(plan['operation_id'], True, plan_hash=plan['plan_hash'])
        self.assertEqual(done['state'], 'needs_input', done)
        self.assertIsNone(done['approved_hash'])
        self.assertFalse(done['mission']['permission']['exact_plan_approved'])
        self.assertTrue(done['context_invalidated'])
        self.assertEqual(done['step_records'][0]['result']['state'], 'failed')
        self.assertEqual(done['resource_bindings'], before)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertFalse(self.learning.skills.get(self.skill_id)['quarantined'])
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM skill_evidence').fetchone()[0], 0)
        self.assertEqual(self.model.calls, 0)

    def test_repair_and_restart_keep_original_bindings_without_provider_or_defaults(self):
        plan = self.propose()
        before = copy.deepcopy(plan['resource_bindings'])
        with self.assertRaises(NeedsInput): self.learning.repair(plan['operation_id'], text='Usa otros archivos')
        self.learning.close()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        self.commands.mission_guard = self.learning.assert_dispatch_context
        self.assertEqual(self.learning.get(plan['operation_id'])['resource_bindings'], before)
        self.assertEqual(self.learning.list_plans('review-project')[0]['resource_bindings'], before)
        resumed = self.learning.resume(plan['operation_id'])
        self.assertEqual(resumed['resource_bindings'], before)
        self.assertEqual(resumed['plan_hash'], plan['plan_hash'])
        self.assertEqual(self.model.calls, 0)

    def test_actual_resolved_input_bypass_is_blocked_before_prepare(self):
        plan = self.propose()
        altered = self.raw(plan)
        altered['step_records'][0]['resolved_inputs'] = {'path': str(self.paths['other_path']), 'other_path': str(self.paths['path'])}
        self.store(altered)
        done = self.learning.execute(plan['operation_id'], True, plan_hash=plan['plan_hash'])
        self.assertNotEqual(done['state'], 'succeeded')
        self.assertEqual(self.executor.list_operations(), [])

    def test_forgetting_source_redacts_resource_metadata_and_nested_inputs(self):
        plan = self.propose()
        owner = self.tasks[0]
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            barrier = task_memory.begin_forget(self.learning.db, owner, 'forget-resource-a', 0)
        hidden = self.learning.get(plan['operation_id'])
        self.assertTrue(hidden['memory_forgotten'])
        self.assertNotIn('resource_bindings', hidden)
        self.assertNotIn('resource_binding_selectors', hidden)
        self.assertEqual(hidden['skill_versions'][0]['inputs'], {})
        self.assertEqual(hidden['steps'][0]['inputs'], {})
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(self.learning.db, barrier, {})
        self.assertEqual(self.executor.list_operations(), [])

    @unittest.skipUnless(os.name == 'nt', 'Native read lease only exists on Windows')
    def test_windows_lease_holds_reviewed_bytes_at_executor_entry(self):
        plan = self.propose()
        original = self.executor.execute_action
        blocked = []
        def change_at_entry(tool, *args, **kwargs):
            if tool == 'file_inspection':
                try: self.paths['path'].write_bytes(b'UNREVIEWED')
                except OSError: blocked.append('write')
                try: self.paths['path'].unlink()
                except OSError: blocked.append('delete')
            return original(tool, *args, **kwargs)
        with patch.object(self.executor, 'execute_action', side_effect=change_at_entry):
            done = self.learning.execute(plan['operation_id'], True, plan_hash=plan['plan_hash'])
        self.assertEqual(done['state'], 'succeeded', done)
        self.assertEqual(set(blocked), {'write', 'delete'})
        self.assertEqual(self.paths['path'].read_bytes(), b'left\x00\xff')

    def test_source_opaque_rotation_preserves_durable_binding_but_destination_rotation_fences_request(self):
        plan = self.propose(operation_id='old-destination')
        before = copy.deepcopy(plan['resource_bindings'])
        group = self.chats.mutate('group', {'title': 'Moved source'})['id']
        self.chats.mutate('update', {'id': self.tasks[0], 'group_id': group})
        self.learning._assert_resource_bindings(plan)
        self.assertEqual(self.learning.get(plan['operation_id'])['resource_bindings'], before)
        self.chats.mutate('update', {'id': self.tasks[2], 'group_id': group})
        with self.assertRaises(ValueError): self.learning._assert_request(plan, **self.scope(self.tasks[2]))
        with self.assertRaises(ValueError): self.propose(operation_id='old-destination')
        self.assertEqual(self.propose()['state'], 'awaiting_approval')
        self.assertEqual(self.executor.list_operations(), [])

    def test_transitive_context_dependency_revocation_fences_only_derived_binding(self):
        peer = self.chats.mutate('create', {'title': 'Causal source'})['id']
        dependency = self.chats.get(peer)['memory_scope'] | {'context_id': self.chats.get(peer)['context_id']}
        context = self.learning.update_context('project-a', {'current_file': str(self.paths['path']),
            'context_meta': {'current_file': {'kind': 'confirmed_user', 'task_id': self.tasks[0]}}},
            _memory_dependencies=[dependency], **self.scope(self.tasks[0]))
        selectors = self.selectors | {'path': self.selectors['path'] | {'revision': context['context_meta']['current_file']['revision']}}
        plan = self.propose(resource_bindings=selectors)
        self.assertIn(dependency, plan['memory_dependencies'])
        group = self.chats.mutate('group', {'title': 'Changed causal context'})['id']
        self.chats.mutate('update', {'id': peer, 'group_id': group})
        self.assertTrue(self.learning.get(plan['operation_id'])['memory_forgotten'])
        independent = self.learning.prepare_steps('Independent hash', [{'command_id': 'axx.file.sha256',
            'inputs': {'path': str(self.paths['other_path'])}}], conversation_id=self.tasks[2], **self.scope(self.tasks[2]))
        done = self.learning.execute(independent['operation_id'], True, plan_hash=independent['plan_hash'])
        self.assertEqual(done['state'], 'succeeded', done)
        self.assertEqual(self.model.calls, 0)

    def test_absent_field_keeps_legacy_request_and_approval_hash_payload(self):
        literal = {role: str(path) for role, path in self.paths.items()}
        plan = self.propose(resource_bindings=None, inputs=literal)
        self.assertNotIn('resource_bindings', plan)
        self.assertNotIn('resource_binding_selectors', plan)
        payload = {'steps': plan['steps'], 'skill_versions': plan['skill_versions'], 'project_id': plan['project_id'],
            'dependencies': plan['dependencies'], 'identities': [{key: row[key] for key in ('step_id', 'operation_id', 'input_hash')} for row in plan['step_records']],
            'goal_spec': plan['goal_spec'], 'goal_revision': plan['goal_revision'], 'approval_version': 2,
            'memory_scope': plan['memory_scope'], 'memory_context_id': plan['memory_context_id']}
        if plan.get('memory_dependencies'): payload['memory_dependencies'] = plan['memory_dependencies']
        self.assertEqual(self.learning._hash(payload), plan['plan_hash'])
        old = copy.deepcopy(plan)
        old.pop('approval_version')
        payload.pop('approval_version')
        self.assertEqual(self.learning._plan_hash(old), self.learning._hash(payload))


if __name__ == '__main__': unittest.main()
