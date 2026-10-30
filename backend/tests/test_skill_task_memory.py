"""Scoped forgetting follows origins and existing dependencies, never effect journals."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory import selection_policy, task_memory
from backend.memory.procedural_memory import get_action_env_fingerprint
from backend.memory.skill_memory import SkillMemory, assert_lessons_current, lesson_refs, validate_schema


class SkillTaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.db = sqlite3.connect(self.root / 'state.db')
        self.lock = threading.RLock()
        self.db.execute('CREATE TABLE learned_actions(id TEXT PRIMARY KEY,trigger TEXT,title TEXT,steps TEXT,environment TEXT,verified_at REAL)')
        self.db.execute('CREATE TABLE learning_plans(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        self.memory = SkillMemory(self.db, self.lock)
        self.file = self.executor.workspace_root / 'trial.txt'
        self.a, self.b = (task_memory.snapshot(self.db, task) for task in ('task-a', 'task-b'))

    def tearDown(self):
        self.db.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def skill(self, key, task=None):
        provenance = {}
        if task:
            operation = 'plan-' + key
            with self.db:
                self.db.execute('INSERT INTO learning_plans VALUES (?,?)', (operation,
                    json.dumps({'operation_id': operation, 'conversation_id': task,
                                'memory_scope': task_memory.snapshot(self.db, task)})))
            provenance = {'operation_id': operation}
        return self.memory.insert({'id': key, 'version': 1, 'trigger': key, 'title': key,
            'templates': [{'command_id': 'axx.system.telemetry', 'inputs': {}}],
            'schema': validate_schema({}), 'examples': [], 'project_id': 'p', 'favorite': False,
            'environment': get_action_env_fingerprint(['axx.system.telemetry']),
            'checks': ['executor_postconditions'], 'provenance': provenance,
            'created_at': time.time(), 'executable': True})

    def lesson(self, task, **extra):
        self.file.write_text('trial', encoding='utf-8')
        command = self.commands.prepare('axx.file.sha256', {'path': str(self.file)}, conversation_id=task,
                                        memory_scope=task_memory.snapshot(self.db, task))
        self.file.unlink()
        failure = self.commands.execute(command['operation_id'], approved=True)
        body = {'operation_id': failure['operation_id'], 'hypothesis': 'Failure for ' + task,
                'task_id': task, 'project_id': 'p'} | extra
        return self.memory.record_lesson(body), body

    def pending(self):
        self.db.execute('BEGIN IMMEDIATE')
        ref = task_memory.begin_forget(self.db, 'task-a', 'forget-a', 0)
        self.db.commit()
        return ref

    def finish(self, ref):
        self.db.execute('BEGIN IMMEDIATE')
        result = self.memory.forget_task('task-a')
        self.assertTrue(self.db.in_transaction, 'memory cleanup must not commit the coordinator transaction')
        task_memory.finish_forget(self.db, ref, result)
        self.db.commit()
        return result

    def test_forget_follows_origins_across_projects_and_preserves_b_and_journal(self):
        source = self.memory.update_context('p', {'current_folder': 'A private'}, memory_scope=self.a)
        dependency = {'project_id': 'p', 'field': 'current_folder', 'revision': source['context_revision']}
        self.memory.update_context('p', {'current_file': 'derived A', 'context_meta': {'current_file': {
            'depends_on': [{'field': 'current_folder', 'revision': source['context_revision']}]}}})
        self.memory.update_context('other', {'last_result': {'private': 'A'}}, memory_scope=self.a)
        self.memory.update_context('p', {'current_application': 'B kept'}, memory_scope=self.b)
        self.memory.update_context('p', {'last_inputs': {'unknown': 'legacy preserved'}})
        skill_a, skill_b = self.skill('skill.a', 'task-a'), self.skill('skill.b', 'task-b')
        self.memory.record(skill_b['id'], 1, 'plan-skill.a', {'goal_confirmed': True,
                           'task_id': 'task-a', 'route': {'private': 'A used B'}})
        self.assertTrue(self.memory.get(skill_b['id'])['goal_confirmed'])
        self.skill('skill.legacy')
        self.memory.update_context('p', {'aliases': {'A': skill_a['id'], 'B': skill_b['id']}}, memory_scope=self.b)
        lesson_a, _ = self.lesson('task-a', context_dependencies=[dependency])
        lesson_b, _ = self.lesson('task-b')
        receipts = self.commands.operations()
        ref = self.pending()
        self.assertFalse(self.memory.get(skill_b['id'])['goal_confirmed'])
        self.assertTrue(self.memory.get('skill.legacy')['requires_review'])
        self.assertEqual([item['id'] for item in self.memory.search('skill', 'p')], [skill_b['id']])
        self.assertTrue(self.memory.context('p')['context_meta']['last_inputs']['requires_review'])
        self.assertEqual(self.memory.context('p')['context_meta']['current_folder']['status'], 'stale')
        self.assertEqual(self.memory.lessons(project_id='p', task_id='task-a'), [])
        with self.assertRaises(ValueError): self.memory.get('skill.a')
        result = self.finish(ref)
        context = self.memory.context('p')
        self.assertNotIn('current_folder', context)
        self.assertNotIn('current_file', context)
        self.assertNotIn('last_result', self.memory.context('other'))
        self.assertEqual(context['current_application'], 'B kept')
        self.assertEqual(context['last_inputs'], {'unknown': 'legacy preserved'})
        self.assertTrue(context['context_meta']['last_inputs']['requires_review'])
        self.assertEqual(context['aliases'], {'B': skill_b['id']})
        self.assertEqual(self.memory.get('skill.b')['id'], skill_b['id'])
        self.assertFalse(self.memory.get('skill.b')['goal_confirmed'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM skill_evidence').fetchone()[0], 0)
        self.assertEqual([item['id'] for item in self.memory.search('skill', 'p')], [skill_b['id']])
        self.assertEqual([item['id'] for item in self.memory.lessons(project_id='p', task_id='task-b')], [lesson_b['id']])
        self.assertIn(lesson_a['id'], result['forgotten_lessons'])
        self.assertEqual(self.commands.operations(), receipts)
        task_memory.assert_current(self.db, self.b)

    def test_late_context_skill_and_lesson_writes_rejected_after_reopen(self):
        cached = self.skill('skill.a', 'task-a')
        _, body = self.lesson('task-a')
        self.finish(self.pending())
        self.db.close()
        self.db = sqlite3.connect(self.root / 'state.db')
        self.memory = SkillMemory(self.db, self.lock)
        with self.assertRaises(ValueError): self.memory.update_context('p', {'current_file': 'late'}, memory_scope=self.a)
        with self.assertRaises(ValueError): self.memory.update_context('p', {'current_file': 'late',
            'context_meta': {'current_file': {'task_id': 'task-a'}}})
        with self.assertRaises(ValueError): self.memory.insert(cached | {'version': 2})
        with self.assertRaises(ValueError): self.memory.record_lesson(body)
        with self.assertRaises(ValueError): self.memory.record_lesson(body | {'memory_scope': task_memory.snapshot(self.db, 'task-a')})
        fresh = task_memory.snapshot(self.db, 'task-a')
        updated = self.memory.update_context('p', {'current_file': 'new intent'}, memory_scope=fresh)
        meta = updated['context_meta']['current_file']
        self.assertNotIn('task_id', meta, 'ownership must not accidentally create operational task scope')
        self.assertEqual(meta['origin_task_id'], 'task-a')

    def test_repository_opened_before_forget_cannot_commit_its_old_reference(self):
        other_db = sqlite3.connect(self.root / 'state.db')
        other = SkillMemory(other_db, threading.RLock())
        try:
            previous = task_memory.snapshot(other_db, 'task-a')
            self.finish(self.pending())
            with self.assertRaises(ValueError): other.update_context('p', {'current_folder': 'late'}, memory_scope=previous)
            self.assertNotIn('current_folder', self.memory.context('p'))
        finally:
            other_db.close()

    def test_new_direct_receipt_after_forget_can_record_a_current_lesson(self):
        self.finish(self.pending())
        lesson, _ = self.lesson('task-a')
        self.assertEqual(lesson['memory_scope'], {'task_id': 'task-a', 'generation': 1})
        refs = lesson_refs(self.memory.lessons(project_id='p', task_id='task-a'))
        self.assertEqual(len(refs), 1)
        assert_lessons_current(self.db, refs, 'p', 'task-a')

    def test_unknown_context_quarantine_keeps_b_lesson_bytes_but_blocks_reuse(self):
        context = self.memory.update_context('p', {'last_inputs': {'unknown': 'keep'},
            'context_meta': {'last_inputs': {'session_id': 'task-a'}}})
        lesson, _ = self.lesson('task-b', context_dependencies=[{'project_id': 'p', 'field': 'last_inputs',
                                                               'revision': context['context_revision']}])
        self.finish(self.pending())
        row = self.db.execute('SELECT payload FROM skill_lessons WHERE id=?', (lesson['id'],)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row[0]), lesson)
        self.assertEqual(self.memory.context('p')['last_inputs'], {'unknown': 'keep'})
        selected = self.memory.lessons(project_id='p', task_id='task-b')
        self.assertEqual(selected[0]['status'], 'stale')
        with self.assertRaises(ValueError): assert_lessons_current(self.db, lesson_refs(selected), 'p', 'task-b')

    def test_selection_policy_projection_preserves_manual_id_and_technical_environment(self):
        skill = self.skill('skill.b', 'task-b')
        self.db.execute('BEGIN IMMEDIATE')
        selection_policy.apply(self.db, skill, 'retire_procedure', 'p', None, self.b, 'retire-b', 0)
        self.db.commit()
        manual = self.memory.get(skill['id'])
        self.assertTrue(manual['selection_policy']['retired'])
        self.assertFalse(manual['auto_select'])
        self.assertEqual(manual['command_environment_matches'], skill['command_environment_matches'])
        self.assertEqual(manual['environment_matches'], skill['environment_matches'])
        self.assertEqual(self.memory.search('skill.b', 'p'), [])
        self.assertTrue(selection_policy.allowed(manual, manual['selection_policy'], 'p', automatic=False))

    def test_lesson_references_recheck_hash_existence_and_context_without_writes(self):
        context = self.memory.update_context('p', {'current_file': 'A'}, memory_scope=self.a)
        lesson, _ = self.lesson('task-a', context_dependencies=[{'project_id': 'p', 'field': 'current_file',
                                                               'revision': context['context_revision']}])
        selected = self.memory.lessons(project_id='p', task_id='task-a')
        refs = lesson_refs(selected)
        before = self.db.total_changes
        self.assertEqual(assert_lessons_current(self.db, refs, 'p', 'task-a'), refs)
        self.assertEqual(self.db.total_changes, before)
        altered = copy.deepcopy(refs)
        altered[0]['digest'] = '0' * 64
        with self.assertRaises(ValueError): assert_lessons_current(self.db, altered, 'p', 'task-a')
        with self.assertRaises(ValueError): assert_lessons_current(self.db, refs, 'p', 'task-b')
        self.memory.update_context('p', {'current_file': 'changed'}, memory_scope=self.a)
        with self.assertRaises(ValueError): assert_lessons_current(self.db, refs, 'p', 'task-a')
        self.memory.forget_lesson(lesson['id'])
        with self.assertRaises(ValueError): assert_lessons_current(self.db, refs, 'p', 'task-a')

    def _configure_with_durable_evidence_after_context_rotation(self, source):
        with self.db:
            self.db.execute('CREATE TABLE chat_conversations(id TEXT PRIMARY KEY,connect_id TEXT,memory_context_required INTEGER)')
            self.db.executemany('INSERT INTO chat_conversations VALUES (?,?,0)',
                                [(task, 'before-' + task) for task in ('task-a', 'task-b')])
        learning = ActionLearning(self.commands, None)
        self.commands.learning = learning
        try:
            scope = task_memory.snapshot(self.db, source)
            metadata = {'memory_scope': scope, 'memory_context_id': 'before-' + source}
            plan = learning.prepare_steps('Guardar evidencia local', [{'command_id': 'axx.artifact.write',
                'inputs': {'path': 'durable-evidence.txt', 'content': 'isolated fixture'}}],
                conversation_id=source, **metadata)
            done = learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'], **metadata)
            self.assertEqual(done['state'], 'succeeded', done)
            key = done['learned_action_id']
            source_row = self.db.execute('SELECT payload FROM skill_versions WHERE id=?', (key,)).fetchone()[0]
            operation, raw = self.db.execute('SELECT operation_id,payload FROM skill_evidence WHERE id=?', (key,)).fetchone()
            evidence = json.loads(raw)
            journal = {table: self.commands.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                       for table in ('command_runs', 'operations', 'artifact_compensations')}
            with self.db:
                self.db.execute("UPDATE chat_conversations SET connect_id='after-'||id,memory_context_required=1")
            self.assertTrue(learning.skills.get(key)['effect_verified'])
            with self.assertRaises(ValueError):
                learning.configure(key, {'title': 'Old request'}, memory_scope=self.b, memory_context_id='before-task-b')
            with self.assertRaises(ValueError):
                learning.skills.record(key, 1, 'late-' + operation, evidence)
            configured = learning.configure(key, {'version': 1, 'title': 'Reviewed in B'},
                memory_scope=self.b, memory_context_id='after-task-b')
            self.assertEqual(configured['memory_scope'], self.b)
            self.assertTrue(configured['effect_verified'])
            self.assertEqual(configured['memory_dependencies'], [self.a] if source == 'task-a' else [])
            inherited = json.loads(self.db.execute('SELECT payload FROM skill_evidence WHERE id=? AND version=2', (key,)).fetchone()[0])
            for field in ('origin_task_id', 'memory_scope', 'memory_context_id', 'memory_dependencies'):
                self.assertEqual(inherited[field], evidence[field], field)
            self.assertEqual(inherited['inherited_from_version'], 1)
            self.assertEqual(self.db.execute('SELECT payload FROM skill_versions WHERE id=? AND version=1', (key,)).fetchone()[0], source_row)
            self.assertEqual(self.db.execute('SELECT payload FROM skill_evidence WHERE id=? AND version=1', (key,)).fetchone()[0], raw)
            self.pending()
            if source == 'task-a':
                with self.assertRaises(ValueError): learning.skills.get(key, 2)
            else:
                self.assertTrue(learning.skills.get(key, 2)['effect_verified'])
            self.assertEqual({table: self.commands.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                              for table in journal}, journal)
        finally:
            learning.close()

    def test_independent_b_fresh_configuration_preserves_durable_evidence_after_context_rotation(self):
        self._configure_with_durable_evidence_after_context_rotation('task-b')

    def test_a_evidence_configured_in_b_preserves_original_scope_and_forget_dependency(self):
        self._configure_with_durable_evidence_after_context_rotation('task-a')


if __name__ == '__main__':
    unittest.main()
