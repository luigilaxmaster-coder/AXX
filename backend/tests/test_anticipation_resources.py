"""Admission budgets over existing processes, SQLite and temporary artifacts."""
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.anticipation import AnticipationService
from backend.tests import test_anticipation_grants as grants


class AnticipationResourceTests(unittest.TestCase):
    setUp = grants.MissionGrantTests.setUp
    tearDown = grants.MissionGrantTests.tearDown
    plan = grants.MissionGrantTests.plan
    grant = grants.MissionGrantTests.grant
    run_granted = grants.MissionGrantTests.run_granted
    authorized = grants.MissionGrantTests.authorized

    def resources(self, **values):
        return self.service.configure({'profiles': {'full': {'resources': values}}})

    def test_nullable_defaults_strict_validation_and_conservative_pre_destination_budget(self):
        status = self.service.status()
        self.assertIsNone(status['profiles']['full']['resources']['max_process_rss_bytes'])
        self.assertIsNone(status['profiles']['full']['resources']['max_storage_bytes'])
        self.assertEqual(self.service.budget_for_task('task-a')['model_call_limit'], 2)
        for key, bad in [('max_process_rss_bytes', 0), ('max_storage_bytes', True), ('max_storage_bytes', 1.1),
                         ('max_process_rss_bytes', 9007199254740992), ('model_call_limit', 3), ('model_call_limit', None), ('model_call_limit', False)]:
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError): self.resources(**{key: bad})
        folder = self.executor.workspace_root / 'scope'; folder.mkdir()
        self.service.configure({'profiles': {'copiloto': {'resources': {'model_call_limit': 0, 'max_process_rss_bytes': 100}},
            'discreto': {'resources': {'model_call_limit': 1}}}, 'scopes': [
            {'task_id': 'task-a', 'root': str(folder), 'profile': 'copiloto'},
            {'task_id': 'task-b', 'profile': 'discreto'}]})
        self.assertEqual(self.service.budget_for_task('task-a')['model_call_limit'], 0)
        self.assertEqual(self.service.budget_for_task('task-a')['max_process_rss_bytes'], 100)
        self.assertEqual(self.service.budget_for_task('task-b')['model_call_limit'], 1)
        self.assertEqual(self.service.budget_for_task('task-c')['model_call_limit'], 2)
        with patch.object(self.learning, 'get', side_effect=AssertionError('foreign lock API')), \
             patch.object(self.commands, 'get', side_effect=AssertionError('foreign lock API')):
            self.assertEqual(self.service.budget_for_task('task-a')['model_call_limit'], 0)
        self.resources(max_process_rss_bytes=None, max_storage_bytes=None, model_call_limit=2)

    def test_rss_snapshot_has_real_backend_identity_and_explicit_scope(self):
        sample = self.service._sample_memory(refresh=True)
        self.assertTrue(sample['known'], sample)
        self.assertGreater(sample['rss_bytes'], 0)
        own = next(row for row in sample['processes'] if row['pid'] == os.getpid())
        self.assertGreater(own['create_time'], 0)
        self.assertFalse(sample['hard_os_limit'])
        self.assertIn('non_descendant_office_com', sample['excludes'])

    def test_legacy_resource_config_migrates_without_enabling_sources_or_caps(self):
        with self.service.lock, self.service.db:
            config = self.service._config()
            for profile in config['profiles'].values():
                for key in ('max_process_rss_bytes', 'max_storage_bytes', 'model_call_limit'):
                    profile['resources'].pop(key)
            self.service.db.execute('UPDATE anticipation_config SET payload=? WHERE id=1', (json.dumps(config),))
        self.service.close(); self.service = AnticipationService(self.commands)
        self.learning.anticipation = self.service; self.commands.dispatch_guard = self.service.dispatch_guard
        self.executor.result_filter = self.service.filter_result
        status = self.service.status()
        self.assertFalse(status['sources']['screen']); self.assertFalse(status['sources']['microphone'])
        self.assertIsNone(status['profiles']['full']['resources']['max_storage_bytes'])
        self.assertIsNone(status['profiles']['full']['resources']['max_process_rss_bytes'])
        self.assertEqual(status['profiles']['full']['resources']['model_call_limit'], 2)

    def test_rss_descendants_unknown_and_pid_reuse_fail_closed_without_effect(self):
        import psutil
        backend = Mock(pid=os.getpid()); child = Mock(pid=987654321)
        backend.create_time.return_value = 1.0; child.create_time.return_value = 2.0
        backend.memory_info.return_value = SimpleNamespace(rss=80)
        child.memory_info.return_value = SimpleNamespace(rss=30)
        backend.children.return_value = [child]; child.parents.return_value = [backend]
        self.service._process_created_at = None
        with patch('psutil.Process', side_effect=lambda pid: backend if pid == backend.pid else child):
            self.resources(max_process_rss_bytes=100)
            self.assertEqual(self.service._sample_memory(refresh=True)['rss_bytes'], 110)
            with self.assertRaisesRegex(ValueError, 'MEMORY_ADMISSION_LIMIT'):
                self.service.assert_resource_admission('task-a')
            plan = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'memory.txt', 'content': 'no'}}])
            with self.assertRaisesRegex(ValueError, 'MEMORY_ADMISSION_LIMIT'):
                self.run_granted(plan, self.grant(command_ids=['axx.artifact.write']))
            child.memory_info.side_effect = psutil.AccessDenied(child.pid)
            with self.assertRaisesRegex(ValueError, 'MEMORY_ADMISSION_UNKNOWN'):
                self.service.assert_resource_admission('task-a')
            child.memory_info.side_effect = None
            child.create_time.side_effect = [2.0, 3.0]
            self.assertFalse(self.service._sample_memory(refresh=True)['known'])
        self.assertEqual(self.executor.list_operations(), [])
        self.assertFalse((self.executor.workspace_root / 'memory.txt').exists())

    def test_exact_utf8_quota_reconciles_completed_output_without_deleting_original(self):
        self.resources(max_storage_bytes=10)
        original = self.executor.workspace_root / 'original.txt'; original.write_bytes(b'1234')
        grant = self.grant(command_ids=['axx.artifact.write'])
        first = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'utf8.txt', 'content': '\u00e1' * 3}}])
        self.assertEqual(self.run_granted(first, grant)['state'], 'succeeded')
        row = self.service.db.execute('SELECT bytes,state FROM anticipation_storage_reservations').fetchone()
        self.assertEqual((row['bytes'], row['state']), (6, 'reserved'))
        too_much = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'extra.txt', 'content': 'x'}}])
        with self.assertRaisesRegex(ValueError, 'STORAGE_ADMISSION_LIMIT'): self.run_granted(too_much, grant)
        self.assertEqual(original.read_bytes(), b'1234')
        self.assertFalse((self.executor.workspace_root / 'extra.txt').exists())
        usage = self.service.status()['resource_usage']['storage'][0]
        self.assertEqual(usage['used_bytes'], 10)
        self.resources(max_storage_bytes=11)
        self.assertEqual(self.run_granted(too_much, grant)['state'], 'succeeded')
        self.assertEqual(self.service.db.execute('SELECT state FROM anticipation_storage_reservations WHERE operation_id=?',
            (first['step_records'][0]['operation_id'],)).fetchone()[0], 'accounted')
        self.assertEqual(original.read_bytes(), b'1234')

    def test_incomplete_storage_metadata_abstains_before_any_write(self):
        self.resources(max_storage_bytes=100, max_entries_scan=1)
        (self.executor.workspace_root / 'one.txt').write_text('one')
        (self.executor.workspace_root / 'two.txt').write_text('two')
        plan = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'new.txt', 'content': 'new'}}])
        with self.assertRaisesRegex(ValueError, 'STORAGE_USAGE_UNKNOWN'):
            self.run_granted(plan, self.grant(command_ids=['axx.artifact.write']))
        self.assertEqual(self.executor.list_operations(), [])
        self.assertFalse(self.service.status()['resource_usage']['storage'][0]['known'])

    def test_overlapping_child_grant_cannot_bypass_parent_root_quota(self):
        child = self.executor.workspace_root / 'child'; child.mkdir()
        (self.executor.workspace_root / 'original.txt').write_bytes(b'x' * 80)
        self.resources(max_storage_bytes=1000)
        self.service.configure({'profiles': {'copiloto': {'mode': 'EXECUTE', 'resources': {'max_storage_bytes': 100}}},
            'scopes': [{'task_id': 'parent-task', 'profile': 'copiloto'}]})
        parent_grant = self.grant(task_id='parent-task', command_ids=['axx.artifact.write'])
        child_grant = self.grant(task_id='child-task', root=str(child), command_ids=['axx.artifact.write'])
        plan = self.plan(task='child-task', steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'child/new.txt', 'content': 'z' * 30}}])
        with self.assertRaisesRegex(ValueError, 'STORAGE_ADMISSION_LIMIT'): self.run_granted(plan, child_grant)
        self.service.revoke(parent_grant['grant_id'])
        self.assertEqual(self.run_granted(plan, child_grant)['state'], 'succeeded')
        self.assertEqual((self.executor.workspace_root / 'original.txt').stat().st_size, 80)

    def test_two_services_reserve_quota_atomically_by_operation(self):
        self.resources(max_storage_bytes=100)
        grant = self.grant(command_ids=['axx.artifact.write'])
        plans = []
        for name in ('left.txt', 'right.txt'):
            plan = self.authorized(self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': name, 'content': 'x' * 60}}]), grant)
            plan.update(state='running', approved_hash=plan['plan_hash']); plan['step_records'][0]['state'] = 'running'
            with self.learning.lock: self.learning._save(plan)
            plans.append(plan)
        other = AnticipationService(self.commands)
        gate, outcomes = threading.Barrier(2), []
        def reserve(service, plan):
            gate.wait()
            try:
                for _ in range(2):
                    service.authorize_mission_step(plan, plan['steps'][0], plan['steps'][0]['inputs'], plan['step_records'][0]['operation_id'], claim=True)
                outcomes.append('reserved')
            except ValueError: outcomes.append('denied')
        try:
            workers = [threading.Thread(target=reserve, args=args) for args in zip((self.service, other), plans)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(10); self.assertFalse(worker.is_alive())
            self.assertCountEqual(outcomes, ['reserved', 'denied'])
            self.assertEqual(self.service.db.execute("SELECT COUNT(*),SUM(bytes) FROM anticipation_storage_reservations WHERE state='reserved'").fetchone()[:], (1, 60))
            self.assertEqual(self.executor.list_operations(), [])
        finally: other.close()

    def test_unknown_crash_reservation_survives_restart_until_existing_manual_review(self):
        self.resources(max_storage_bytes=100)
        grant = self.grant(command_ids=['axx.artifact.write'])
        first = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'uncertain.txt', 'content': 'x' * 60}}])
        invoke = self.executor.invoke_primitive
        def lose_result(*args, **kwargs):
            invoke(*args, **kwargs)
            raise RuntimeError('synthetic interruption after real effect')
        with patch.object(self.executor, 'invoke_primitive', side_effect=lose_result):
            self.assertEqual(self.run_granted(first, grant)['state'], 'unknown')
        self.service.close(); self.service = AnticipationService(self.commands)
        self.learning.anticipation = self.service; self.commands.dispatch_guard = self.service.dispatch_guard
        self.executor.result_filter = self.service.filter_result
        next_plan = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'next.txt', 'content': 'n'}}])
        with self.assertRaisesRegex(ValueError, 'STORAGE_ADMISSION_LIMIT'): self.run_granted(next_plan, grant)
        self.assertEqual((self.executor.workspace_root / 'uncertain.txt').stat().st_size, 60)
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.commands.review_unknown(first['step_records'][0]['operation_id'], reviewed=True)
        self.assertEqual(self.run_granted(next_plan, grant)['state'], 'succeeded')
        self.assertEqual(len(self.executor.list_operations()), 2)
        row = self.service.db.execute('SELECT state FROM anticipation_storage_reservations WHERE operation_id=?', (first['step_records'][0]['operation_id'],)).fetchone()
        self.assertEqual(row[0], 'accounted')

    def test_bundle_requires_actual_enforced_cap_under_finite_quota(self):
        self.resources(max_storage_bytes=2000)
        sources = self.root / 'inputs'; sources.mkdir(); source = sources / 'source.txt'; source.write_text('data')
        grant = self.grant(command_ids=['axx.file.bundle'], read_roots=[str(sources)])
        unbounded = self.plan(steps=[{'command_id': 'axx.file.bundle', 'inputs': {'paths': [str(source)], 'destination': 'unbounded'}}])
        with self.assertRaisesRegex(ValueError, 'STORAGE_OUTPUT_UNBOUNDED'): self.run_granted(unbounded, grant)
        bounded = self.plan(steps=[{'command_id': 'axx.file.bundle', 'inputs': {'paths': [str(source)], 'destination': 'bounded',
            'archive_name': 'copy.zip', 'max_output_bytes': 2000}}])
        self.assertEqual(self.run_granted(bounded, grant)['state'], 'succeeded')
        self.assertEqual(self.service.db.execute('SELECT bytes FROM anticipation_storage_reservations').fetchone()[0], 2000)
        total = sum(path.stat().st_size for path in (self.executor.workspace_root / 'bounded').iterdir())
        self.assertLessEqual(total, 2000)
        self.assertEqual(source.read_text(), 'data')

    def test_office_unknown_output_abstains_with_quota_but_legacy_manual_remains_separate(self):
        self.resources(max_storage_bytes=1000)
        grant = self.grant(command_ids=['axx.artifact.write'])
        with self.service._policy_transaction(immediate=True), self.assertRaisesRegex(ValueError, 'STORAGE_OUTPUT_UNBOUNDED'):
            self.service._storage_admission('axx.office.word.pdf', {'destination': 'office-output'}, grant,
                {'source': 'events', 'device_id': 'host'}, self.service._config(), 'office-op', claim=True)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertFalse((self.executor.workspace_root / 'office-output').exists())

    def test_explicit_manual_execution_remains_available_outside_initiative_admission(self):
        self.resources(max_storage_bytes=1)
        plan = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'manual.txt', 'content': 'approved exact manual content'}}])
        with self.assertRaisesRegex(ValueError, 'STORAGE_ADMISSION_LIMIT'):
            self.run_granted(plan, self.grant(command_ids=['axx.artifact.write']))
        self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'succeeded')
        self.assertEqual((self.executor.workspace_root / 'manual.txt').read_text(), 'approved exact manual content')
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM anticipation_storage_reservations').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
