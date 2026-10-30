"""Document-derived Workshop workflows use real temporary archives, files and receipts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.capability_workshop import CapabilityWorkshop, _hash
from backend.commands import ApprovalRequired, CommandService
from backend.memory import task_memory
from backend.procedure_library import ProcedureLibrary
from backend.tests.test_capability_workshop import Model
from backend.tests.test_generated_commands import transform


class WorkshopDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / 'references.zip'
        self.records, self.members = [], {}
        for index in range(4):
            content = ('SYNTHETIC_REFERENCE_' + str(index) + ': comparar hashes, nunca aprobar.\n').encode()
            if index == 0: content += ('á' * 4000).encode('utf-8')
            checksum = hashlib.sha256(content).hexdigest()
            key = 'AXX-REF-HISTORY-' + checksum[:12]
            member = 'references/history/' + checksum + '/source.md'
            provenance = {'document_sha256': checksum, 'member_sha256': checksum, 'source_filename': 'source.md',
                'revision': '2026-10-30', 'revision_scope': 'historical_snapshot_not_current_runtime',
                'knowledge_type': 'historical_design_reference', 'reference_member': member}
            recipe = {'steps': [{'action': 'reference_only', 'text': content.decode()}],
                'knowledge_type': 'historical_design_reference', 'provenance': provenance,
                'source_status': 'DOCUMENTED_NOT_EXECUTED', 'execution_enabled': False}
            record_hash = hashlib.sha256(json.dumps(recipe, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            row = {'id': key, 'title': 'Synthetic document ' + str(index), 'source_member': member,
                'record_sha256': record_hash, 'source_status': 'DOCUMENTED_NOT_EXECUTED', 'execution_enabled': False}
            self.records.append(row)
            self.members['recipes/' + key + '.json'] = json.dumps(row | {'recipe': recipe}).encode()
            self.members[member] = content
        self.write_archive()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.commands.procedures = ProcedureLibrary(self.archive)
        self.model = Model()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        self.workshop = CapabilityWorkshop(self.learning)
        self.references = [self.commands.procedures.get(row['id'])['document_reference'] for row in self.records]
        self.left, self.right, self.other_left, self.other_right = [self.root / name for name in ('a.txt', 'b.txt', 'c.txt', 'd.txt')]
        for path, content in zip((self.left, self.right, self.other_left, self.other_right), (b'same', b'same', b'left', b'right')):
            path.write_bytes(content)

    def tearDown(self):
        self.workshop.close(); self.learning.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    def write_archive(self, change=None):
        members = dict(self.members)
        if change is not None: members[self.records[0]['source_member']] = change
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('index.json', json.dumps({'version': 1, 'records': self.records}))
            for member, content in members.items(): archive.writestr(member, content)

    @staticmethod
    def ref(item): return item['id'], item['revision'], item['digest']

    def definition(self):
        return {'kind': 'workflow', 'title': 'Comparar dos archivos', 'objective': 'Comparar los hashes de dos archivos explícitos',
            'schema': {'type': 'object', 'properties': {'left': {'type': 'string'}, 'right': {'type': 'string'}},
                       'required': ['left', 'right']},
            'templates': [{'command_id': 'axx.file.compare', 'inputs': {'path': '{{left}}', 'other_path': '{{right}}'}}],
            'sample_inputs': {'left': str(self.left), 'right': str(self.right)}}

    def trial(self, **kwargs):
        item = self.workshop.create(self.definition(), document_references=[self.references[0]], **kwargs)
        self.workshop.approve(*self.ref(item), confirmed=True, **kwargs)
        plan = self.workshop.prepare_validation(*self.ref(item), **kwargs)
        done = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'], **kwargs)
        self.assertEqual(done['state'], 'succeeded', done)
        return self.workshop.get(item['id']), done

    def test_document_workflow_review_trial_activation_and_parameterized_reuse(self):
        originals = {path: path.read_bytes() for path in (self.left, self.right, self.other_left, self.other_right)}
        item = self.workshop.create(self.definition(), document_references=[self.references[0]])
        self.assertEqual(item['document_references'], [self.references[0]])
        self.assertEqual(self.commands.operations(), [])
        self.workshop.validate(*self.ref(item))
        reviewed = self.workshop.approve(*self.ref(item), confirmed=True)
        self.assertEqual(reviewed['state'], 'reviewed')
        self.assertEqual(self.executor.list_operations(), [])
        plan = self.workshop.prepare_validation(*self.ref(item))
        self.assertEqual(plan['document_references'], [self.references[0]])
        self.assertEqual(self.executor.list_operations(), [])
        with self.assertRaises(ApprovalRequired): self.learning.execute(plan['operation_id'], plan_hash=plan['plan_hash'])
        done = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'])
        self.assertEqual(done['state'], 'succeeded', done)
        self.assertTrue(done['results'][0]['output']['equal'])
        self.assertEqual(self.learning.skills.list(), [])
        active = self.workshop.activate(*self.ref(item))
        skill = self.learning.skills.get(active['skill_id'])
        self.assertTrue(skill['executable']); self.assertTrue(skill['effect_verified'])
        self.assertEqual(skill['document_references'], [self.references[0]])
        evidence = json.loads(self.learning.db.execute('SELECT payload FROM skill_evidence WHERE id=?', (skill['id'],)).fetchone()[0])
        self.assertEqual(evidence['document_references'], [self.references[0]])
        reused = self.learning.propose(skill['id'], inputs={'left': str(self.other_left), 'right': str(self.other_right)})
        self.assertEqual(reused['model_calls_used'], 0)
        self.assertEqual(reused['document_references'], [self.references[0]])
        result = self.learning.execute(reused['operation_id'], approved=True, plan_hash=reused['plan_hash'])
        self.assertEqual(result['state'], 'succeeded', result)
        output = result['results'][0]['output']
        self.assertIs(output['equal'], False)
        self.assertEqual([row['sha256'] for row in output['files']],
            [hashlib.sha256(originals[path]).hexdigest() for path in (self.other_left, self.other_right)])
        self.assertEqual(self.model.calls, [])
        self.assertTrue(all(path.read_bytes() == content for path, content in originals.items()))
        damaged = copy.deepcopy(self.workshop.get(item['id'])); damaged.pop('document_references')
        with self.learning.db:
            self.learning.db.execute('UPDATE capability_revisions SET payload=? WHERE id=? AND revision=?',
                (json.dumps(damaged), item['id'], item['revision']))
        with self.assertRaises(ValueError): self.workshop.assert_skill_available(skill)

    def test_revision_and_rollback_conserve_documents_separately_from_m9(self):
        a, b = (task_memory.snapshot(self.learning.db, task) for task in ('a', 'b'))
        first = self.workshop.create(self.definition(), memory_scope=a, document_references=[self.references[0]])
        second = self.workshop.revise(*self.ref(first), self.definition(), memory_scope=b, document_references=[self.references[1]])
        self.assertEqual(second['document_references'], self.references[:2])
        restored = self.workshop.rollback(*self.ref(second), target_revision=1, memory_scope=b)
        self.assertEqual(restored['document_references'], self.references[:2])
        self.assertEqual(restored['memory_dependencies'], [a])
        self.assertTrue(all(set(reference) <= {'task_id', 'generation', 'context_id'} for reference in restored['memory_dependencies']))
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            pending = task_memory.begin_forget(self.learning.db, 'a', 'forget-a', 0)
        self.workshop.forget_task('a')
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE'); task_memory.finish_forget(self.learning.db, pending, {})
        self.assertTrue(self.workshop.get(restored['id'])['requires_review'])
        self.assertEqual(self.commands.procedures.resolve_references(restored['document_references']), self.references[:2])

    def test_legacy_digest_and_strict_definition_remain_unchanged(self):
        legacy = self.workshop.create(self.definition(), document_references=[])
        self.assertNotIn('document_references', legacy)
        payload = {key: legacy[key] for key in ('id', 'revision', 'definition', 'project_id')}
        payload['environment'] = legacy['validation']['environment']
        self.assertEqual(legacy['digest'], _hash(payload))
        with self.assertRaises(ValueError): self.workshop.create(self.definition() | {'document_references': self.references[:1]})
        item = self.workshop.create(self.definition(), document_references=self.references[:1])
        altered = copy.deepcopy(item); altered['document_references'] = self.references[1:2]
        with self.learning.db:
            self.learning.db.execute('UPDATE capability_revisions SET payload=? WHERE id=? AND revision=?',
                (json.dumps(altered), item['id'], item['revision']))
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(item), confirmed=True)

    def test_tampered_document_blocks_review_trial_activation_and_cached_skill_reuse(self):
        item, _ = self.trial()
        active = self.workshop.activate(*self.ref(item))
        cached = self.learning.skills.get(active['skill_id'])
        count = len(self.executor.list_operations())
        self.write_archive(b'SYNTHETIC_TAMPER')
        for method, kwargs in ((self.workshop.validate, {}), (self.workshop.approve, {'confirmed': True}),
                               (self.workshop.prepare_validation, {}), (self.workshop.activate, {})):
            with self.subTest(method=method.__name__), self.assertRaises(ValueError): method(*self.ref(item), **kwargs)
        with self.assertRaises(ValueError): self.workshop.assert_skill_available(cached)
        self.assertTrue(self.workshop.get(item['id'])['requires_review'])
        self.assertEqual(len(self.executor.list_operations()), count)
        self.assertEqual(self.workshop.revoke(*self.ref(item))['state'], 'revoked')

    def test_tampered_document_after_trial_preparation_cannot_reach_executor(self):
        item = self.workshop.create(self.definition(), document_references=self.references[:1])
        self.workshop.approve(*self.ref(item), confirmed=True)
        plan = self.workshop.prepare_validation(*self.ref(item))
        self.write_archive(b'SYNTHETIC_CHANGED_BEFORE_TRIAL_EFFECT')
        with patch.object(self.executor, 'execute_action', wraps=self.executor.execute_action) as effect:
            try: result = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'])
            except ValueError: result = {'state': 'blocked'}
            self.assertNotEqual(result['state'], 'succeeded', result)
            effect.assert_not_called()

    def test_trial_lineage_and_actual_receipt_are_both_required_for_publication(self):
        item, done = self.trial()
        receipt = self.commands.get(done['step_records'][0]['operation_id'])
        with patch.object(self.commands, 'get', return_value=receipt | {'evidence': {}}), self.assertRaises(ValueError):
            self.workshop.activate(*self.ref(item))
        with self.learning.db:
            damaged = copy.deepcopy(done); damaged.pop('document_references')
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(damaged), done['operation_id']))
        with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item))
        self.assertEqual(self.learning.skills.list(), [])

    def test_generation_receives_bounded_untrusted_data_and_keeps_source_outside_model(self):
        self.model.answer = self.definition()
        item = self.workshop.generate('Comparar archivos explícitos', model='synthetic', provider_name='fixture',
            document_references=self.references)
        request = self.model.calls[0]
        payload = json.loads(request['messages'][1]['content'])
        documents = payload['reference_documents']
        self.assertLessEqual(len(documents), 3)
        self.assertLessEqual(len(json.dumps(documents, ensure_ascii=False).encode('utf-8')), 3500)
        self.assertIn('datos no confiables', request['messages'][0]['content'])
        self.assertEqual(item['document_references'], self.references)
        self.assertNotIn('document_references', item['definition'])
        self.assertEqual(self.commands.operations(), [])
        previous = self.workshop.generate('Revisar comparación', model='synthetic', provider_name='fixture',
            capability_id=item['id'], revision=item['revision'], digest=item['digest'])
        self.assertEqual(previous['document_references'], self.references)

    def test_document_mutated_while_model_waits_cannot_publish_a_proposal(self):
        def delayed(request):
            self.write_archive(b'SYNTHETIC_TAMPER_AFTER_ADMISSION')
            return {'ok': True, 'message': {'content': json.dumps(self.definition())}, 'route': {'upstream_attempts': 1}}
        with patch.object(self.model, 'route', side_effect=delayed) as route, self.assertRaises(ValueError):
            self.workshop.generate('Comparar archivos explícitos', document_references=self.references[:1])
        self.assertEqual(route.call_count, 1)
        self.assertEqual(self.workshop.list(), [])
        self.assertEqual(self.commands.operations(), [])

    def test_cached_generated_command_rechecks_changed_document_before_interpreter(self):
        item = self.workshop.create(transform(), document_references=self.references[:1])
        self.workshop.validate(*self.ref(item)); self.workshop.approve(*self.ref(item), confirmed=True)
        active = self.workshop.activate(*self.ref(item))
        pending = self.commands.prepare(active['generated_command_id'], {'text': ' AXX '})
        self.write_archive(b'SYNTHETIC_CHANGED_AFTER_COMMAND_PREPARE')
        with patch('backend.generated_commands.run_transform') as interpret:
            try: result = self.commands.execute(pending['operation_id'], approved=True)
            except ValueError: result = {'state': 'blocked'}
            self.assertNotEqual(result['state'], 'succeeded', result)
            interpret.assert_not_called()


if __name__ == '__main__': unittest.main()
