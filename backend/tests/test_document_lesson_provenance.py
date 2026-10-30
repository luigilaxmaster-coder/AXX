"""Receipt-derived lessons retain captured document lineage through planning and reuse."""
import copy
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch

from backend.action_learning import MemoryCancellation
from backend.chat_store import ChatStore
from backend.memory import task_memory
from backend.memory.skill_memory import assert_lessons_current, lesson_refs, value_hash
from backend.tests import test_document_skill_learning as document_fixture


class DocumentLessonProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = document_fixture.DocumentSkillLearningTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.learning, self.commands, self.model = self.fixture.learning, self.fixture.commands, self.fixture.model
        self.chats = ChatStore(self.fixture.executor.db_path)
        self.addCleanup(self.chats.close)
        self.a = self.chats.mutate('create', {'title': 'Lesson source A'})['id']
        self.b = self.chats.mutate('create', {'title': 'Independent B'})['id']
        self.project = 'document-lessons'
        self.counter = 0

    def scope(self, task):
        chat = self.chats.get(task)
        return {'memory_scope': copy.deepcopy(chat['memory_scope']), 'memory_context_id': chat['context_id']}

    def failure(self, *, references=None, task=None):
        task = task or self.a
        self.counter += 1
        path = self.fixture.executor.workspace_root / ('failure-' + str(self.counter) + '.bin')
        path.write_bytes(b'owned fixture source')
        plan = self.learning.prepare_steps('Leer archivo temporal', [{'command_id': 'axx.file.sha256', 'inputs': {'path': str(path)}}],
            project_id=self.project, conversation_id=task, document_references=references, **self.scope(task))
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        prepare = self.commands.prepare

        def remove_after_prepare(command_id, inputs, *args, **kwargs):
            result = prepare(command_id, inputs, *args, **kwargs)
            if command_id == 'axx.file.sha256' and inputs.get('path') == str(path): path.unlink()
            return result

        with patch.object(self.commands, 'prepare', side_effect=remove_after_prepare):
            failed = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'], **self.scope(task))
        self.assertEqual(failed['state'], 'failed', failed)
        receipt = self.commands.get(failed['step_records'][0]['operation_id'])
        self.assertEqual(receipt['state'], 'failed')
        return receipt, failed

    def lesson(self, failure, *, task=None, allow_provider=True, **extra):
        task = task or self.a
        return self.learning.skills.record_lesson({'operation_id': failure['operation_id'], 'project_id': self.project,
            'task_id': task, 'hypothesis': 'PROBELESSONECHO: hipotesis humana independiente, no causa demostrada.',
            'allow_provider': allow_provider, **self.scope(task), **extra})

    def journal(self):
        return {table: self.commands.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                for table in ('command_runs', 'operations', 'artifact_compensations')}

    def install_model(self, lesson):
        def response(request):
            self.model.calls.append(copy.deepcopy(request))
            payload = json.loads(request['messages'][1]['content'])
            selected = payload['previous_action']['incident_references']['lessons']
            self.assertEqual([item['id'] for item in selected], [lesson['id']])
            self.assertEqual(selected[0]['source_receipt_sha256'], lesson['source_receipt_sha256'])
            values = {'filename': 'lesson-derived.txt', 'content': selected[0]['symptom']}
            data = {'title': 'Controlled copy of receipt symptom',
                'steps': [{'command_id': 'axx.artifact.write', 'inputs': {'path': values['filename'], 'content': values['content']}}],
                'skill_candidate': {'schema': {'type': 'object', 'properties': {'filename': {'type': 'string'},
                    'content': {'type': 'string'}}, 'required': ['filename', 'content']},
                    'templates': [{'command_id': 'axx.artifact.write', 'inputs': {'path': '{{filename}}', 'content': '{{content}}'}}],
                    'examples': [], 'inputs': values}}
            return {'ok': True, 'message': {'content': json.dumps(data)},
                    'route': {'upstream_attempts': 1, 'attempt_budget_used': 1}}
        self.model.route = response
        return response

    def derive(self, lesson, *, task=None):
        task = task or self.a
        self.install_model(lesson)
        plan = self.learning.propose('PROBELESSONECHO', project_id=self.project, conversation_id=task, **self.scope(task))
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        done = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'], **self.scope(task))
        self.assertEqual(done['state'], 'succeeded', done)
        skill = self.learning.skills.get(done['learned_action_id'], project_id=self.project, task_id=task)
        return plan, done, skill

    def test_receipt_lesson_plan_skill_and_reuse_keep_docs_and_block_changed_source(self):
        references = self.fixture.references[:1]
        failure, parent = self.failure(references=references)
        self.assertEqual(failure['document_references'], references)
        lesson = self.lesson(failure)
        self.assertEqual(lesson['document_references'], references)
        self.assertEqual(lesson['source_receipt_sha256'], value_hash(failure))
        self.assertEqual(lesson['provenance']['source_plan_id'], parent['operation_id'])
        self.assertFalse(lesson['cause_confirmed'])
        self.assertEqual(lesson['user_correction'], '')
        plan, done, skill = self.derive(lesson)
        for item in (plan, done, skill): self.assertEqual(item['document_references'], references)
        evidence = json.loads(self.learning.db.execute('SELECT payload FROM skill_evidence WHERE id=?', (skill['id'],)).fetchone()[0])
        self.assertEqual(evidence['document_references'], references)
        self.assertEqual((self.fixture.executor.workspace_root / 'lesson-derived.txt').read_text(encoding='utf-8'), lesson['symptom'])
        reuse = self.learning.propose(skill['id'], inputs={'filename': 'lesson-reuse.txt', 'content': lesson['symptom']},
            project_id=self.project, conversation_id=self.a, **self.scope(self.a))
        self.assertEqual(reuse['model_calls_used'], 0)
        self.assertEqual(reuse['document_references'], references)
        journal = self.journal()
        self.fixture.write_library(tampered=True)
        with self.assertRaises(ValueError): self.learning.skills.get(skill['id'])
        with self.assertRaises(ValueError):
            self.learning.execute(reuse['operation_id'], approved=True, plan_hash=reuse['plan_hash'], **self.scope(self.a))
        self.assertEqual(self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project, task_id=self.a), [])
        self.assertEqual(self.journal(), journal)
        self.assertEqual(len(self.model.calls), 1)
        self.assertFalse((self.fixture.executor.workspace_root / 'lesson-reuse.txt').exists())

    def test_readonly_guard_and_memory_cancellation_use_the_captured_library(self):
        failure, _ = self.failure(references=self.fixture.references[:1])
        lesson = self.lesson(failure)
        refs = lesson_refs(self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project, task_id=self.a))
        self.assertEqual(refs[0]['id'], lesson['id'])
        db = self.learning.db
        denied = []

        def authorize(action, *args):
            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE):
                denied.append(action)
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        before = db.total_changes
        db.set_authorizer(authorize)
        try:
            self.assertEqual(assert_lessons_current(db, refs, self.project, self.a,
                procedure_library=self.commands.procedures), refs)
            self.assertEqual(db.total_changes, before)
            self.assertEqual(denied, [])
        finally:
            db.set_authorizer(None)
        captured = {**self.scope(self.a), 'conversation_id': self.a, 'project_id': self.project,
                    'memory_dependencies': [], 'lesson_dependencies': refs}
        cancel = MemoryCancellation(self.fixture.executor.db_path, captured, threading.Event(), procedure_library=self.commands.procedures)
        self.assertFalse(cancel.is_set())
        self.fixture.write_library(tampered=True)
        self.assertTrue(cancel.is_set())
        with self.assertRaises(ValueError):
            assert_lessons_current(db, refs, self.project, self.a, procedure_library=self.commands.procedures)

    def test_stale_optional_lesson_does_not_cancel_a_new_plan(self):
        failure, _ = self.failure()
        lesson = self.lesson(failure)
        self.fixture.answer()
        with patch('backend.memory.skill_memory.get_action_env_fingerprint', return_value='changed-environment'):
            local = self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project, task_id=self.a)
            self.assertEqual([(item['id'], item['status']) for item in local], [(lesson['id'], 'stale')])
            self.assertEqual(self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project,
                task_id=self.a, allow_provider_only=True), [])
            plan = self.learning.propose('PROBELESSONECHO', project_id=self.project, conversation_id=self.a, **self.scope(self.a))
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        self.assertEqual(plan['lesson_dependencies'], [])
        self.assertEqual(len(self.model.calls), 1)
        payload = json.loads(self.model.calls[0]['messages'][1]['content'])
        self.assertNotIn('incident_references', payload['previous_action'])

    def test_current_lesson_is_not_hidden_by_newer_stale_lessons(self):
        failure, _ = self.failure()
        valid = self.lesson(failure)
        with patch('backend.memory.skill_memory.get_action_env_fingerprint', return_value='obsolete-environment'):
            stale = [self.lesson(failure, hypothesis='PROBELESSONECHO obsolete ' + str(index)) for index in range(3)]
        local = self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project, task_id=self.a)
        self.assertEqual({item['id'] for item in local}, {item['id'] for item in stale})
        for limit in (1, 3):
            selected = self.learning.skills.lessons('PROBELESSONECHO', limit=limit,
                project_id=self.project, task_id=self.a, allow_provider_only=True)
            self.assertEqual([item['id'] for item in selected], [valid['id']])

    def test_failure_parent_and_verification_capture_lineage_once_without_rebasing(self):
        failure, parent = self.failure(references=self.fixture.references[:1])
        path = self.fixture.files[2]
        verified = self.commands.prepare('axx.file.sha256', {'path': str(path)}, conversation_id=self.a,
            _document_references=self.fixture.references[1:2], _memory_dependencies=[self.scope(self.b)['memory_scope']], **self.scope(self.a))
        done = self.commands.execute(verified['operation_id'], approved=True)
        self.assertEqual(done['state'], 'succeeded', done)
        lesson = self.lesson(failure, verification_operation_id=done['operation_id'])
        self.assertEqual(lesson['document_references'], self.fixture.references)
        self.assertIn(self.scope(self.b)['memory_scope'], lesson['memory_dependencies'])
        self.assertFalse(lesson['verification']['proves_cause'])
        raw = self.learning.db.execute('SELECT payload FROM skill_lessons WHERE id=?', (lesson['id'],)).fetchone()[0]
        changed_parent = copy.deepcopy(parent)
        changed_parent['document_references'] = self.fixture.all_references[2:3]
        with self.learning.db:
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(changed_parent), parent['operation_id']))
        selected = self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project, task_id=self.a)
        self.assertEqual(selected[0]['document_references'], self.fixture.references)
        self.assertEqual(self.learning.db.execute('SELECT payload FROM skill_lessons WHERE id=?', (lesson['id'],)).fetchone()[0], raw)
        journal = self.journal()
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            task_memory.begin_forget(self.learning.db, self.b, 'forget-verification-dependency', 0)
        self.assertEqual(self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project, task_id=self.a), [])
        self.assertEqual(self.journal(), journal)

    def test_document_change_at_final_lesson_insert_rolls_back_without_touching_receipts(self):
        failure, _ = self.failure(references=self.fixture.references[:1])
        journal = self.journal()
        resolve = self.learning.skills.resolve_document_references

        def change_after_insert(references):
            if references and self.learning.db.execute('SELECT 1 FROM skill_lessons LIMIT 1').fetchone():
                self.fixture.write_library(tampered=True)
            return resolve(references)

        with patch.object(self.learning.skills, 'resolve_document_references', side_effect=change_after_insert):
            with self.assertRaises(ValueError): self.lesson(failure)
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM skill_lessons').fetchone()[0], 0)
        self.assertEqual(self.journal(), journal)

    def test_held_model_source_change_discards_publication_and_preserves_budget_and_receipts(self):
        failure, _ = self.failure(references=self.fixture.references[:1])
        lesson = self.lesson(failure)
        route = self.install_model(lesson)
        self.model.supports_cancel_event = True
        entered, release = threading.Event(), threading.Event()
        result, errors = {}, []
        cancellation = []

        def held(request, *, cancel_event=None):
            self.assertIsNotNone(cancel_event)
            self.assertFalse(cancel_event.is_set())
            cancellation.append(cancel_event)
            response = route(request)
            entered.set()
            if not release.wait(5): raise AssertionError('Controlled response was not released')
            return response

        self.model.route = held

        def propose():
            try:
                result['plan'] = self.learning.propose('PROBELESSONECHO', operation_id='held-document-lesson',
                    project_id=self.project, conversation_id=self.a, **self.scope(self.a))
            except Exception as exc:
                errors.append(exc)

        journal = self.journal()
        thread = threading.Thread(target=propose)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            self.fixture.write_library(tampered=True)
            self.assertTrue(cancellation[0].is_set())
        finally:
            release.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        checkpoint = self.learning.get('held-document-lesson')
        self.assertEqual(checkpoint['state'], 'needs_input', checkpoint)
        self.assertTrue(checkpoint['selection_invalidated'])
        self.assertFalse(checkpoint.get('memory_forgotten', False))
        self.assertNotEqual(checkpoint.get('title'), 'Aprendizaje de sesión olvidado')
        self.assertEqual(checkpoint['document_references'], self.fixture.references[:1])
        self.assertNotIn('model_data', checkpoint)
        self.assertEqual(checkpoint['model_calls_used'], 1)
        self.assertEqual(checkpoint['model_calls_confirmed'], 1)
        self.assertEqual(checkpoint['model_calls_reserved'], 0)
        self.assertEqual(self.journal(), journal)
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM skill_versions').fetchone()[0], 0)
        self.fixture.write_library()
        with self.assertRaises(ValueError): self.learning.resume(checkpoint['operation_id'], **self.scope(self.a))
        self.assertEqual(len(self.model.calls), 1)

    def test_only_sent_lessons_are_inherited_and_independent_b_survives_source_forget(self):
        source, parent = self.failure(references=self.fixture.references[:1])
        self.lesson(source)
        unsent, _ = self.failure(references=self.fixture.references[:1], task=self.b)
        self.lesson(unsent, task=self.b, allow_provider=False)
        independent, _ = self.failure(task=self.b)
        correction = 'Confirmar la existencia del archivo, instruccion humana independiente.'
        lesson = self.lesson(independent, task=self.b, user_correction=correction)
        self.assertNotIn('document_references', lesson)
        self.assertEqual(lesson['user_correction'], correction)
        self.assertEqual(lesson['correction_provenance'], 'confirmed_user')
        refs = lesson_refs(self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project, task_id=self.b, allow_provider_only=True))
        self.assertEqual(assert_lessons_current(self.learning.db, refs, self.project, self.b), refs)
        plan, _, skill = self.derive(lesson, task=self.b)
        self.assertNotIn('document_references', plan)
        self.assertNotIn('document_references', skill)
        self.assertEqual([ref['id'] for ref in plan['lesson_dependencies']], [lesson['id']])
        journal = self.journal()
        self.learning.forget_session(self.a, 'forget-document-lesson-a', self.scope(self.a)['memory_scope'],
            memory_context_id=self.scope(self.a)['memory_context_id'], chats=self.chats)
        self.assertTrue(self.learning.get(parent['operation_id'])['memory_forgotten'])
        self.fixture.write_library(tampered=True)
        self.assertTrue(self.learning.skills.get(skill['id'])['effect_verified'])
        selected = self.learning.skills.lessons('PROBELESSONECHO', project_id=self.project, task_id=self.b)
        self.assertEqual([item['id'] for item in selected], [lesson['id']])
        self.assertNotIn('document_references', selected[0])
        self.assertEqual(self.journal(), journal)


if __name__ == '__main__':
    unittest.main()
