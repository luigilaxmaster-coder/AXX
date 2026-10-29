"""Project context and version health use persisted sources and real local receipts."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.actions.tools import get_tool
from backend.commands import CommandService
from backend.memory.procedural_memory import get_action_env_fingerprint
from backend.memory.skill_memory import SkillMemory, read_context_state, read_skill_state, validate_schema


class SkillContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'state.db', check_same_thread=False)
        self.db.execute('CREATE TABLE learned_actions(id TEXT PRIMARY KEY,trigger TEXT,title TEXT,steps TEXT,environment TEXT,verified_at REAL)')
        self.memory = SkillMemory(self.db, self.lock)
        self.file = self.executor.workspace_root / 'trial.txt'
        self.file.write_text('ensayo local', encoding='utf-8')

    def tearDown(self):
        self.db.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def skill(self, key='skill.hash', project='a', version=1, dependencies=None, command='axx.file.sha256'):
        inputs = {'path': str(self.file)} if command == 'axx.file.sha256' else {}
        skill = {'id': key, 'version': version, 'trigger': key, 'title': key, 'templates': [{'command_id': command, 'inputs': inputs}],
            'schema': validate_schema({}), 'examples': [key], 'project_id': project, 'favorite': False,
            'environment': get_action_env_fingerprint([command]), 'checks': ['executor_postconditions'],
            'provenance': {}, 'created_at': time.time(), 'executable': True}
        if dependencies is not None: skill['context_dependencies'] = dependencies
        return self.memory.insert(skill)

    def hash(self, *, fail=False):
        command = self.commands.prepare('axx.file.sha256', {'path': str(self.file)})
        if fail: self.file.unlink()
        return self.commands.execute(command['operation_id'], approved=True)

    def record(self, receipt, *, key='skill.hash', version=1, **extra):
        self.memory.record(key, version, receipt['operation_id'], {'effect_verified': receipt['state'] == 'succeeded', 'results': [receipt], **extra})

    def test_legacy_calls_keep_values_and_add_inferred_field_provenance(self):
        updated = self.memory.update_context('a', {'current_file': str(self.file), 'defaults': {'format': 'txt'}})
        self.assertEqual(updated['current_file'], str(self.file))
        self.assertEqual(updated['defaults'], {'format': 'txt'})
        self.assertEqual(updated['context_meta']['current_file']['kind'], 'inferred')
        self.assertEqual(updated['context_meta']['current_file']['origin'], 'legacy_update')
        self.assertEqual(updated['context_revision'], 1)
        self.assertEqual(self.memory.context('b')['last_skill_id'], '')

    def test_context_provenance_persists_and_is_project_and_task_scoped(self):
        updated = self.memory.update_context('a', {'current_file': str(self.file), 'context_meta': {'current_file': {
            'kind': 'observed', 'source_id': 'file-read', 'session_id': 'session-a', 'task_id': 'task-a', 'origin': 'verified_tool'}}})
        dependency = {'project_id': 'a', 'field': 'current_file', 'revision': updated['context_meta']['current_file']['revision']}
        self.skill(dependencies=[dependency])
        self.assertTrue(self.memory.get('skill.hash', project_id='a', task_id='task-a')['context_matches'])
        self.assertFalse(self.memory.get('skill.hash', project_id='a', task_id='task-b')['context_matches'])
        self.assertFalse(self.memory.get('skill.hash', project_id='b', task_id='task-a')['context_matches'])
        self.assertTrue(self.memory.search('skill.hash', 'a', task_id='task-a')[0]['context_matches'])
        self.db.close()
        self.db = sqlite3.connect(self.root / 'state.db', check_same_thread=False)
        self.memory = SkillMemory(self.db, self.lock)
        restored = self.memory.context('a')
        self.assertEqual(restored['current_file'], str(self.file))
        self.assertEqual(restored['context_meta']['current_file']['source_id'], 'file-read')
        self.assertNotIn('current_file', self.memory.context('b'))

    def test_source_invalidation_marks_transitive_derivatives_and_returns_refs(self):
        folder = self.memory.update_context('a', {'current_folder': str(self.file.parent), 'context_meta': {'current_folder': {
            'kind': 'observed', 'source_id': 'folder-scan'}}})
        source_revision = folder['context_meta']['current_folder']['revision']
        child = self.memory.update_context('a', {'current_file': str(self.file), 'context_meta': {'current_file': {
            'kind': 'inferred', 'source_id': 'derived-file', 'depends_on': [{'field': 'current_folder', 'revision': source_revision}]}}})
        self.skill(dependencies=[{'project_id': 'a', 'field': 'current_file', 'revision': child['context_meta']['current_file']['revision']}])
        self.memory.update_context('b', {'current_folder': 'unrelated'})
        before = len(self.commands.operations())
        invalidated = self.memory.invalidate_context('a', {'source_id': 'folder-scan'})
        self.assertEqual({ref['field'] for ref in invalidated['invalidated']}, {'current_folder', 'current_file'})
        self.assertEqual(invalidated['current_file'], str(self.file))
        self.assertEqual(invalidated['context_meta']['current_file']['status'], 'stale')
        self.assertEqual(self.memory.get('skill.hash')['status'], 'stale')
        self.assertEqual(self.memory.context('b')['current_folder'], 'unrelated')
        self.assertEqual(len(self.commands.operations()), before)

    def test_forgetting_session_removes_source_values_and_derived_values(self):
        initial = self.memory.update_context('a', {'defaults': {'private_note': 'only local'}, 'context_meta': {'defaults': {
            'kind': 'confirmed_user', 'session_id': 'session-a'}}})
        rev = initial['context_meta']['defaults']['revision']
        self.memory.update_context('a', {'last_inputs': {'private_copy': 'only local'}, 'context_meta': {'last_inputs': {
            'kind': 'inferred', 'depends_on': [{'field': 'defaults', 'revision': rev}]}}})
        forgotten = self.memory.invalidate_context('a', {'session_id': 'session-a', 'forget': True})
        self.assertEqual(forgotten['defaults'], {})
        self.assertEqual(forgotten['last_inputs'], {})
        self.assertNotIn('defaults', forgotten['context_meta'])
        self.assertEqual(set(forgotten['context_tombstones']), {'defaults', 'last_inputs'})
        raw = self.db.execute('SELECT payload FROM skill_context WHERE project_id=?', ('a',)).fetchone()[0]
        self.assertNotIn('only local', raw)
        self.assertNotIn('session-a', raw)
        self.assertGreater(forgotten['context_revision'], rev)

    def test_forgetting_a_source_erases_derivatives_even_if_they_were_already_stale(self):
        source = self.memory.update_context('a', {'current_folder': 'private folder', 'context_meta': {'current_folder': {'source_id': 'scan'}}})
        self.memory.update_context('a', {'current_file': 'private derived file', 'context_meta': {'current_file': {
            'depends_on': [{'field': 'current_folder', 'revision': source['context_revision']}]}}})
        self.memory.invalidate_context('a', {'source_id': 'scan'})
        forgotten = self.memory.invalidate_context('a', {'source_id': 'scan', 'forget': True})
        self.assertNotIn('current_file', forgotten)
        self.assertNotIn('private', self.db.execute('SELECT payload FROM skill_context WHERE project_id=?', ('a',)).fetchone()[0])

    def test_expiry_and_overwrite_stale_dependencies_without_erasing_values(self):
        now = time.time()
        source = self.memory.update_context('a', {'current_folder': str(self.file.parent), 'context_meta': {'current_folder': {
            'kind': 'observed', 'observed_at': now, 'expires_at': now + 20}}})
        ref = {'field': 'current_folder', 'revision': source['context_meta']['current_folder']['revision']}
        self.memory.update_context('a', {'current_file': str(self.file), 'context_meta': {'current_file': {'depends_on': [ref]}}})
        with patch('backend.memory.skill_memory.time.time', return_value=now + 30):
            expired = self.memory.context('a')
        self.assertEqual(expired['current_folder'], str(self.file.parent))
        self.assertEqual(expired['context_meta']['current_folder']['status'], 'stale')
        self.assertEqual(expired['context_meta']['current_file']['status'], 'stale')
        changed = self.memory.update_context('a', {'current_folder': 'new source'})
        self.assertEqual(changed['context_meta']['current_file']['status'], 'stale')
        self.assertIn('current_file', {ref['field'] for ref in changed['invalidated']})

    def test_only_real_failed_receipt_quarantines_and_new_verified_trial_revalidates(self):
        self.skill()
        success = self.hash()
        self.record(success)
        self.assertEqual(self.memory.get('skill.hash')['status'], 'verified')
        fake = copy.deepcopy(success) | {'state': 'failed', 'postconditions_passed': False, 'error': 'invented'}
        self.memory.record('skill.hash', 1, 'fake', {'effect_verified': False, 'observed': True, 'outcome': 'failed', 'results': [fake]})
        self.assertFalse(self.memory.get('skill.hash')['quarantined'])
        failure = self.hash(fail=True)
        self.assertEqual(failure['state'], 'failed')
        self.record(failure)
        quarantined = self.memory.get('skill.hash')
        self.assertEqual(quarantined['status'], 'quarantined')
        self.assertFalse(quarantined['effect_verified'])
        self.record(success, revalidation=True)
        self.assertTrue(self.memory.get('skill.hash')['quarantined'], 'Old receipt replay cannot revalidate after a later failure')
        self.file.write_text('new real trial', encoding='utf-8')
        self.record(self.hash(), revalidation=True)
        self.assertEqual(self.memory.get('skill.hash')['status'], 'verified')
        self.db.close()
        self.db = sqlite3.connect(self.root / 'state.db', check_same_thread=False)
        self.memory = SkillMemory(self.db, self.lock)
        self.assertFalse(self.memory.get('skill.hash')['quarantined'])

    def test_failure_is_local_to_version_and_command_revalidation_is_selective(self):
        self.skill()
        self.skill(version=2)
        self.skill('skill.telemetry', command='axx.system.telemetry')
        success = self.hash()
        self.record(success, version=2)
        self.record(self.hash(fail=True), version=1)
        self.assertTrue(self.memory.get('skill.hash', 1)['quarantined'])
        self.assertFalse(self.memory.get('skill.hash', 2)['quarantined'])
        self.file.write_text('trial after adapter update', encoding='utf-8')
        tool = get_tool('file_inspection')
        with patch.object(tool, 'version', tool.version + '-test'):
            self.assertFalse(self.memory.get('skill.hash', 2)['command_environment_matches'])
            self.assertTrue(self.memory.get('skill.telemetry')['command_environment_matches'])
            self.record(self.hash(), version=2, revalidation=True)
            self.assertTrue(self.memory.get('skill.hash', 2)['command_environment_matches'])

    def test_invalid_metadata_never_changes_persisted_context(self):
        for body in ({'current_file': 'x', 'context_meta': {'other': {}}},
                     {'current_file': 'x', 'context_meta': {'current_file': {'kind': 'confirmed_by_model'}}},
                     {'current_file': 'x', 'context_meta': {'current_file': {'expires_at': float('inf')}}},
                     {'current_file': 'x', 'context_meta': {'current_file': {'depends_on': [{'field': [], 'revision': 1}]}}},
                     {'current_file': 'x', 'context_meta': {'current_file': {'depends_on': [{'field': 'current_file', 'revision': 1}]}}}):
            before = self.memory.context('a')
            with self.subTest(body=body), self.assertRaises(ValueError): self.memory.update_context('a', body)
            self.assertEqual(self.memory.context('a'), before)

    def test_read_only_projection_uses_caller_sql_connection_without_migration_or_lock(self):
        self.skill()
        self.record(self.hash())
        expected = self.memory.get('skill.hash')
        denied = []
        def authorize(action, first, second, database, trigger):
            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE):
                denied.append(action)
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        self.db.set_authorizer(authorize)
        try:
            self.assertEqual(read_skill_state(self.db, 'skill.hash'), expected)
            self.assertEqual(denied, [])
        finally:
            self.db.set_authorizer(None)

    def test_read_only_context_detects_transitive_expiry_without_stored_status_changes(self):
        now = time.time()
        source = self.memory.update_context('a', {'current_folder': str(self.file.parent), 'context_meta': {'current_folder': {
            'kind': 'observed', 'expires_at': now + 10}}})
        self.memory.update_context('a', {'current_file': str(self.file), 'context_meta': {'current_file': {
            'depends_on': [{'field': 'current_folder', 'revision': source['context_revision']}]}}})
        raw = self.db.execute('SELECT payload FROM skill_context WHERE project_id=?', ('a',)).fetchone()[0]
        self.assertEqual(json.loads(raw)['context_meta']['current_file']['status'], 'active')
        with patch('backend.memory.skill_memory.time.time', return_value=now + 20):
            resolved = read_context_state(self.db, 'a')
        self.assertEqual(resolved['context_meta']['current_file']['status'], 'stale')
        self.assertEqual(self.db.execute('SELECT payload FROM skill_context WHERE project_id=?', ('a',)).fetchone()[0], raw)

    def test_real_incident_preserves_hypothesis_and_verified_test_as_different_claims(self):
        failure = self.hash(fail=True)
        self.file.write_text('correction trial', encoding='utf-8')
        trial = self.hash()
        body = {'operation_id': failure['operation_id'], 'hypothesis': 'La exportación pudo terminar antes de tiempo.',
            'user_correction': 'Comprobar la existencia antes de calcular el hash.',
            'verification_operation_id': trial['operation_id'], 'project_id': 'a'}
        item = self.memory.record_lesson(body)
        self.assertEqual(item['verification']['status'], 'verified_test')
        self.assertFalse(item['verification']['proves_cause'])
        self.assertFalse(item['cause_confirmed'])
        self.assertEqual(item['correction_provenance'], 'confirmed_user')
        self.assertFalse(item['permissions_granted'])
        self.assertFalse(item['preference_inferred'])
        self.assertEqual(self.memory.record_lesson(body)['id'], item['id'])
        selected = self.memory.lessons('exportacion', 'axx.file.sha256', project_id='a')
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['status'], 'reference')
        self.assertNotIn('inputs', selected[0])
        self.assertNotIn('output', selected[0])

    def test_incident_rejects_unrelated_or_old_test_and_invented_receipts(self):
        earlier = self.hash()
        failure = self.hash(fail=True)
        command = self.commands.prepare('axx.system.telemetry', {})
        foreign = self.commands.execute(command['operation_id'], approved=True)
        base = {'operation_id': failure['operation_id'], 'hypothesis': 'Hipótesis sin causa confirmada.'}
        for extra in ({'verification_operation_id': foreign['operation_id']}, {'verification_operation_id': earlier['operation_id']},
                      {'operation_id': 'missing'}, {'operation_id': earlier['operation_id']}, {'cause_confirmed': True},
                      {'permissions_granted': True}, {'hypothesis': ''}):
            with self.subTest(extra=extra), self.assertRaises(ValueError): self.memory.record_lesson(base | extra)
        self.assertEqual(self.memory.lessons(), [])

    def test_incidents_are_bounded_project_scoped_persistent_and_do_not_promote_skills(self):
        self.skill()
        for index in range(4):
            failure = self.hash(fail=True)
            self.memory.record_lesson({'operation_id': failure['operation_id'], 'hypothesis': 'Exportación local ' + str(index), 'project_id': 'a'})
            self.file.write_text('next isolated trial', encoding='utf-8')
        self.assertEqual(self.memory.lessons(project_id='b'), [])
        self.assertEqual(self.memory.lessons('irrelevante', project_id='a'), [])
        selected = self.memory.lessons('exportacion', 'axx.file.sha256', project_id='a')
        self.assertEqual(len(selected), 3)
        self.assertTrue(all(len(json.dumps(item, ensure_ascii=False)) <= 3500 for item in selected))
        self.assertEqual(self.memory.get('skill.hash')['status'], 'candidate')
        self.db.close()
        self.db = sqlite3.connect(self.root / 'state.db', check_same_thread=False)
        self.memory = SkillMemory(self.db, self.lock)
        self.assertEqual(len(self.memory.lessons(project_id='a')), 3)
        for invalid in ({'limit': 4}, {'limit': True}, {'query': []}, {'command_id': 'x' * 129}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): self.memory.lessons(**invalid)

    def test_incident_compatibility_tracks_current_command_and_context_without_claiming_app_version(self):
        context = self.memory.update_context('a', {'current_file': str(self.file), 'context_meta': {'current_file': {'source_id': 'scan'}}})
        failure = self.hash(fail=True)
        item = self.memory.record_lesson({'operation_id': failure['operation_id'], 'hypothesis': 'Archivo ausente.', 'project_id': 'a',
            'context_dependencies': [{'project_id': 'a', 'field': 'current_file', 'revision': context['context_revision']}]})
        self.assertEqual(item['environment_scope'], 'registered_command_at_recording_not_historical_app_version')
        tool = get_tool('file_inspection')
        with patch.object(tool, 'version', tool.version + '-test'):
            stale = self.memory.lessons(command_id='axx.file.sha256', project_id='a')[0]
            self.assertFalse(stale['environment_matches'])
            self.assertEqual(stale['status'], 'stale')
        self.memory.invalidate_context('a', {'source_id': 'scan'})
        self.assertFalse(self.memory.lessons(project_id='a')[0]['context_matches'])

    def test_forget_incident_removes_its_search_data_and_keeps_command_journal(self):
        failure = self.hash(fail=True)
        item = self.memory.record_lesson({'operation_id': failure['operation_id'], 'hypothesis': 'Private trial hypothesis.'})
        count = len(self.commands.operations())
        self.assertTrue(self.memory.forget_lesson(item['id'])['forgotten'])
        self.assertEqual(self.memory.lessons('Private'), [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM skill_lessons').fetchone()[0], 0)
        self.assertEqual(len(self.commands.operations()), count)
        self.assertFalse(self.memory.forget_lesson(item['id'])['forgotten'])

    def test_task_filter_precedes_the_three_incident_limit(self):
        for index in range(4):
            task = 'first-task' if index == 0 else 'other-task'
            command = self.commands.prepare('axx.file.sha256', {'path': str(self.file)}, conversation_id=task)
            self.file.unlink()
            failure = self.commands.execute(command['operation_id'], approved=True)
            self.memory.record_lesson({'operation_id': failure['operation_id'], 'hypothesis': 'Ensayo ' + str(index), 'project_id': 'a', 'task_id': task})
            self.file.write_text('next trial', encoding='utf-8')
        records = self.memory.lessons(project_id='a', task_id='first-task')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['task_id'], 'first-task')

    def test_health_resolves_real_prefix_bindings_before_quarantine_and_revalidation(self):
        self.skill()
        raw = json.loads(self.db.execute('SELECT payload FROM skill_versions WHERE id=?', ('skill.hash',)).fetchone()[0])
        raw.update(id='skill.chain', templates=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'chain.txt', 'content': 'chain trial'}},
            {'command_id': 'axx.file.sha256', 'inputs': {}, 'bindings': {'path': {'step': 0, 'path': ['output', 'path']}}}],
            environment=get_action_env_fingerprint(['axx.artifact.write', 'axx.file.sha256']))
        self.memory.insert(raw)
        def run(fail=False):
            writer = self.commands.prepare('axx.artifact.write', raw['templates'][0]['inputs'])
            written = self.commands.execute(writer['operation_id'], approved=True)
            target = Path(written['output']['path'])
            reader = self.commands.prepare('axx.file.sha256', {'path': str(target)})
            if fail: target.unlink()
            read = self.commands.execute(reader['operation_id'], approved=True)
            return [written, read]
        failed = run(fail=True)
        self.assertEqual(failed[0]['state'], 'succeeded')
        self.assertEqual(failed[1]['state'], 'failed')
        self.memory.record('skill.chain', 1, 'failed-chain', {'effect_verified': False, 'results': failed})
        self.assertTrue(self.memory.get('skill.chain')['quarantined'])
        corrected = run()
        self.memory.record('skill.chain', 1, 'corrected-chain', {'effect_verified': True, 'results': corrected, 'revalidation': True})
        self.assertEqual(self.memory.get('skill.chain')['status'], 'verified')


if __name__ == '__main__':
    unittest.main()
