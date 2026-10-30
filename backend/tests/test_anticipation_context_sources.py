"""Synthetic opt-in source fixtures: never read the desktop or clipboard."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image

from backend.actions.executor import ActionExecutor
from backend.actions import windows_automation as windows
from backend.anticipation import AnticipationService
from backend.commands import CommandService


class ContextSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = time.time()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.commands.dispatch_guard = self.service.dispatch_guard
        self.executor.result_filter = self.service.filter_result
        self.patches = [patch.object(self.service, '_window_available', return_value=True),
            patch.object(self.service, '_clipboard_available', return_value=True),
            patch('backend.actions.windows_automation.read_clipboard_text', side_effect=self.clipboard),
            patch('backend.computer_vision.observe', side_effect=self.window),
            patch('backend.actions.windows_automation.process_name', return_value='notepad.exe'),
            patch('backend.actions.windows_automation.process_started', return_value='123456'),
            # Exercise dormant context/lease helpers without claiming that the
            # production provider result path already supports ephemeral output.
            patch.object(self.service, '_provider_context_available', return_value=True)]
        self.mocks = [p.start() for p in self.patches]
        self.clip = {'sequence_number': 1, 'available': True, 'text': 'SYNTHETIC_CLIPBOARD_PRIVATE_TEXT'}
        self.window_id = 0
        self.window_title = 'SYNTHETIC_PRIVATE_WINDOW_TITLE'
        stream = io.BytesIO()
        Image.new('RGB', (10, 12), '#436789').save(stream, format='JPEG')
        self.jpeg = stream.getvalue()

    def tearDown(self):
        self.service.close()
        self.commands.close(); self.executor.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def clipboard(self, *, max_characters, cancelled):
        self.assertFalse(self.service.lock._is_owned())
        self.assertEqual(max_characters, 8192)
        self.assertFalse(cancelled.is_set())
        return copy.deepcopy(self.clip)

    def window(self, grant, event, *, overview, on_observation):
        self.assertFalse(self.service.lock._is_owned())
        self.assertFalse(overview)
        self.assertEqual(grant, {'window_id': 42, 'pid': 7, 'birth': '123456'})
        self.window_id += 1
        observation = {'window_id': 42, 'pid': 7, 'process_started': '123456',
            'observation_id': 'source-uia-' + str(self.window_id), 'completed_monotonic': time.monotonic()}
        observed = {'observation': observation, 'window_title': self.window_title,
            'controls': [{'name': 'SYNTHETIC_PRIVATE_NAME', 'value': 'SYNTHETIC_PRIVATE_VALUE',
                          'text': 'SYNTHETIC_PRIVATE_TEXT', 'offscreen': False}]}
        windows._remember_observation(observed)
        on_observation(observed)
        shot = {'jpeg': self.jpeg, 'width': 10, 'height': 12, 'observed': observed}
        output = {'title': self.window_title, 'window_bounds': {'x': 0, 'y': 0, 'width': 10, 'height': 12},
            'controls': observed['controls'], 'truncated': False}
        return shot, output

    def configure(self, source='clipboard', retain=False, provider=False, observe=True, **target_changes):
        target = {'id': 'fixture-source', 'task_id': 'source-task', 'source': source,
            'observe': observe, 'retain': retain, 'send_to_provider': provider}
        if source == 'window':
            target.update(window_id=42, pid=7, process_started='123456')
        target.update(target_changes)
        flag = 'screen' if source == 'window' else 'clipboard'
        self.service.configure({'profile': 'copiloto', 'sources': {flag: True}, 'observation_targets': [target],
            'profiles': {'copiloto': {'cadence_seconds': 5,
                'resources': {'max_tick_ms': 5000, 'max_cpu_ms_tick': 1000}}}})
        return self.service.status()['observation_targets'][0]

    def advance(self, seconds=5):
        self.now += seconds
        return self.service.tick()

    def assert_private_not_durable(self, values):
        status = json.dumps(self.service.status(), ensure_ascii=False)
        sql = '\n'.join(self.service.db.iterdump())
        disk = self.executor.db_path.read_bytes()
        for value in values:
            self.assertNotIn(value, status)
            self.assertNotIn(value, sql)
            self.assertNotIn(value.encode(), disk)

    def test_defaults_permissions_and_unavailable_sources_fail_closed(self):
        self.service.tick()
        self.mocks[2].assert_not_called(); self.mocks[3].assert_not_called()
        self.assertFalse(self.service.status()['sources']['screen'])
        self.assertFalse(self.service.status()['sources']['clipboard'])
        self.configure(observe=False, retain=True, provider=True)
        self.service.tick()
        self.mocks[2].assert_not_called()
        self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])
        for source, method in (('screen', '_window_available'), ('clipboard', '_clipboard_available')):
            with patch.object(self.service, method, return_value=False):
                with self.assertRaises(ValueError):
                    self.service.configure({'sources': {source: True}})
        with self.assertRaises(ValueError):
            self.service.configure({'sources': {'microphone': True}})

    def test_production_provider_gate_rejects_consent_until_result_privacy_is_complete(self):
        with patch.object(self.service, '_provider_context_available', wraps=AnticipationService._provider_context_available):
            for source in ('clipboard', 'window'):
                self.assertFalse(self.service.status()['capabilities']['provider_context'][source])
                with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'SOURCE_PROVIDER_UNAVAILABLE'):
                    self.configure(source, retain=True, provider=True)
                self.configure(source, retain=True)
                self.service.tick()
                self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])
                self.assertNotIn('raw', self.service.source_state['fixture-source'])

    def test_unverified_application_scope_abstains_before_private_source_reader(self):
        # The application tag is consent data, not proof of the clipboard owner
        # or of a window's currently verified application scope. Provider OFF
        # must not be the only barrier protecting these local readers.
        with patch.object(self.service, '_provider_context_available', wraps=AnticipationService._provider_context_available):
            for source in ('clipboard', 'window'):
                for retain in (False, True):
                    with self.subTest(source=source, retain=retain):
                        self.mocks[2].reset_mock(); self.mocks[3].reset_mock()
                        target = self.configure(source, retain=retain, application_id='notepad.exe',
                            id='scoped-' + source + '-' + str(retain).lower())
                        self.assertFalse(self.service._provider_context_available(source))
                        self.service.tick()
                        self.mocks[2].assert_not_called(); self.mocks[3].assert_not_called()
                        self.assertIsNone(self.service._source_target(target['id']))
                        status = self.service.status()
                        self.assertEqual(status['observation_targets'], [target], 'Saved consent must not be silently rewritten')
                        runtime = next(row for row in status['source_runtime'] if row['id'] == target['id'])
                        self.assertFalse(runtime['active'])
                        self.assertTrue(runtime['error'].startswith('SOURCE_APPLICATION_UNVERIFIED'), runtime)
                        self.assertEqual(runtime['samples'], 0)
                        self.assertEqual(runtime['events'], 0)
                        self.assertFalse(runtime['context_ready'])
                        self.assertFalse(runtime['provider_allowed'])
                        self.assertFalse(any(row.get('target_id') == target['id'] for row in status['source_observations']))
                        self.assertEqual(self.service.db.execute("SELECT COUNT(*) FROM anticipation_events WHERE json_extract(payload,'$.target_id')=?",
                            (target['id'],)).fetchone()[0], 0)
                        self.assertNotIn(target['id'], self.service.source_state)
                        context = self.service.provider_context_for_task('source-task', application_id='notepad.exe')
                        self.assertEqual(context['observations'], [])
                        self.assertEqual(context['refs'], [])
                        self.assertEqual(self.executor.list_operations(), [])
                        self.assertEqual(self.service.suggestions(), [])

                        # Removing an unsupported restriction restores only the
                        # already explicit local consent, without provider use.
                        unscoped = target | {'application_id': ''}
                        self.service.configure({'observation_targets': [unscoped]})
                        self.service.tick()
                        reader = self.mocks[3] if source == 'window' else self.mocks[2]
                        other = self.mocks[2] if source == 'window' else self.mocks[3]
                        reader.assert_called_once(); other.assert_not_called()
                        self.assertEqual(self.service._source_target(target['id']), unscoped)
                        current = self.service.status()
                        runtime = next(row for row in current['source_runtime'] if row['id'] == target['id'])
                        self.assertTrue(runtime['active'])
                        self.assertIsNone(runtime['error'])
                        self.assertEqual(runtime['samples'], 1)
                        self.assertEqual(self.service.db.execute("SELECT COUNT(*) FROM anticipation_events WHERE json_extract(payload,'$.target_id')=?",
                            (target['id'],)).fetchone()[0], int(retain))
                        self.assertNotIn('raw', self.service.source_state[target['id']])
            self.assert_private_not_durable([self.clip['text'], self.window_title, 'SYNTHETIC_PRIVATE_NAME', 'SYNTHETIC_PRIVATE_VALUE'])

    def test_strict_window_identity_and_source_specific_fields(self):
        target = self.configure('window')
        for fields in ({'window_id': True}, {'window_id': 0}, {'pid': -1}, {'pid': 2**32},
                {'process_started': 123456}, {'process_started': 'wrong'}, {'process_started': '1'*33},
                {'root': str(self.root)}, {'process_name': 'notepad.exe'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.service.configure({'observation_targets': [target | fields]})
        target = self.configure()
        for fields in ({'root': str(self.root)}, {'window_id': 42}, {'pid': 7}, {'process_name': 'notepad.exe'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.service.configure({'observation_targets': [target | fields]})

    def test_no_retention_forbids_derived_plans_and_revokes_active_model_lease(self):
        with self.assertRaisesRegex(ValueError, 'Sin conservar contexto'):
            self.configure(provider=True)
        target = self.configure(retain=True, provider=True)
        self.service.tick()
        context = self.service.provider_context_for_task('source-task')
        self.assertTrue(context['refs'])
        lease = self.service.acquire_provider_context('source-task', context['refs'])
        self.service.configure({'observation_targets': [target | {'retain': False, 'send_to_provider': False}]})
        self.assertTrue(lease.is_set())
        with self.assertRaises(ValueError):
            self.service.validate_provider_context_refs('source-task', context['refs'])
        self.advance()
        self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])
        self.assertNotIn('raw', self.service.source_state['fixture-source'])
        runtime = self.service.status()['source_runtime'][0]
        self.assertFalse(runtime['derived_plans_allowed'])
        self.assertFalse(runtime['provider_allowed'])
        self.assertEqual(self.service.suggestions(), [])
        self.assertEqual(self.executor.list_operations(), [])
        self.assert_private_not_durable([self.clip['text']])

    def test_clipboard_observe_and_metadata_retention_are_independent(self):
        for retain in (False, True):
            with self.subTest(retain=retain):
                self.configure(retain=retain)
                self.service.tick()
                state = self.service.source_state['fixture-source']
                self.assertNotIn('raw', state)
                event = self.service.status()['source_observations'][0]
                self.assertEqual(event['type'], 'clipboard.observed')
                self.assertEqual(event['resource']['characters'], len(self.clip['text']))
                self.assertEqual(event['retained'], retain)
                self.assertEqual(self.service.db.execute('SELECT count(*) FROM anticipation_events').fetchone()[0], int(retain))
                self.assert_private_not_durable([self.clip['text']])
                self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.service.suggestions(), [])

    def test_observation_history_cap_preserves_other_sources_and_real_command_receipt(self):
        operation = self.commands.prepare('axx.artifact.write', {'path': 'receipt-before-observation.txt', 'content': 'synthetic receipt'},
            operation_id='prior-effect', conversation_id='source-task')
        receipt = self.commands.execute(operation['operation_id'], approved=True)
        self.assertEqual(receipt['state'], 'succeeded')
        self.configure(retain=True)
        prior = {'event_id': 'prior-folder-event', 'task_id': 'source-task', 'source': 'folders', 'type': 'file.created',
            'profile': 'copiloto', 'at': self.now, 'resource': {'path': 'synthetic metadata'}}
        with self.service.db:
            self.service.db.execute('INSERT INTO anticipation_events VALUES (?,?,?,?)',
                (prior['event_id'], 'source-task', self.now, json.dumps(prior)))
        with patch('backend.anticipation.MAX_CONTEXT_SOURCE_EVENTS', 2):
            for number in range(4):
                self.clip['sequence_number'] = number
                self.advance()
            rows = [json.loads(row[0]) for row in self.service.db.execute('SELECT payload FROM anticipation_events')]
            metadata = [row for row in rows if row.get('history_kind') == 'context_observation_metadata']
            self.assertEqual(len(metadata), 2)
            self.assertEqual({row['resource']['sequence_number'] for row in metadata}, {2, 3})
            self.assertIn(prior, rows)
            status = self.service.status()
            self.assertEqual(status['capabilities']['observation_history_max_events'], 2)
            self.assertIn('not a state.db quota', status['capabilities']['observation_history_scope'])
        self.assertEqual(self.commands.get('prior-effect')['state'], 'succeeded')
        self.assertEqual(self.executor.list_operations()[0]['state'], 'succeeded')
        self.assertEqual((self.executor.workspace_root / 'receipt-before-observation.txt').read_text(), 'synthetic receipt')

    def test_content_fingerprint_is_stable_only_in_session_and_key_is_never_durable(self):
        self.configure(retain=True)
        self.service.tick()
        first = self.service.status()['source_observations'][0]['resource']
        self.assertEqual(first['fingerprint_scope'], 'hmac_sha256_session')
        self.assertNotEqual(first['content_fingerprint'], hashlib.sha256(self.clip['text'].encode()).hexdigest())
        self.assertNotIn('content_sha256', first)
        self.advance()
        current = self.service.source_state['fixture-source']['snapshot']
        self.assertEqual(first['content_fingerprint'], current['content_fingerprint'])
        key = self.service.source_hmac_key
        second = AnticipationService(self.commands, clock=lambda: self.now)
        try:
            self.assertNotEqual(second._content_fingerprint('clipboard_text', self.clip['text'].encode()), first['content_fingerprint'])
            self.assertNotEqual(second.source_hmac_key, key)
        finally:
            second.close()
        sql = '\n'.join(self.service.db.iterdump())
        self.assertNotIn(key.hex(), sql)
        self.assertNotIn(key, self.executor.db_path.read_bytes())
        self.assert_private_not_durable([self.clip['text']])

    def test_window_projection_is_targeted_untrusted_bounded_and_never_durable(self):
        self.configure('window', retain=True, provider=True, project_id='project-a')
        with windows._observation_lock:
            windows._observations['unrelated-observation'] = {'observation': {'completed_monotonic': time.monotonic()}}
        with patch('backend.actions.desktop_input.execute_action', side_effect=AssertionError('No input permitted')):
            self.service.tick()
        self.assertEqual(self.mocks[3].call_count, 1)
        with windows._observation_lock:
            self.assertIn('unrelated-observation', windows._observations)
            self.assertFalse(any(key.startswith('source-uia-') for key in windows._observations))
            windows._observations.pop('unrelated-observation')
        context = self.service.provider_context_for_task('source-task', project_id='project-a')
        self.assertTrue(context['untrusted'])
        self.assertEqual(context['sensitivity'], 'approved_sensitive')
        self.assertEqual(len(context['observations']), 1)
        observation = context['observations'][0]
        self.assertIn(self.window_title, observation['content']['text'])
        self.assertEqual(base64.b64decode(observation['content']['image_url'].split(',', 1)[1]), self.jpeg)
        self.assertEqual(observation['expires_at'] - observation['observed_at'], 60)
        self.assertEqual(self.service.provider_context_for_task('other-task')['observations'], [])
        self.assertEqual(self.service.provider_context_for_task('source-task', project_id='project-b')['observations'], [])
        self.assertTrue(self.service.validate_provider_context_refs('source-task', context['refs'], 'project-a'))
        self.assert_private_not_durable([self.window_title, 'SYNTHETIC_PRIVATE_NAME', 'SYNTHETIC_PRIVATE_VALUE',
            'SYNTHETIC_PRIVATE_TEXT', base64.b64encode(self.jpeg).decode()])
        event = self.service.status()['source_observations'][0]
        self.assertEqual(event['retention_scope'], 'metadata_only')
        self.assertNotIn('controls', event['resource'])

    def test_capture_failure_clears_own_uia_and_hides_private_diagnostic(self):
        self.configure('window', retain=True, provider=True)
        reader = self.window
        def fails(*args, **kwargs):
            reader(*args, **kwargs)
            raise RuntimeError('PRIVATE_PARSER_FRAGMENT')
        self.mocks[3].side_effect = fails
        self.service.tick()
        self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])
        with windows._observation_lock:
            self.assertFalse(any(key.startswith('source-uia-') for key in windows._observations))
        self.assertEqual(self.service.status()['source_runtime'][0]['error'],
            'SOURCE_OBSERVATION_FAILED: no se obtuvo una observación autorizada.')
        self.assert_private_not_durable(['PRIVATE_PARSER_FRAGMENT', self.window_title])

    def test_process_reuse_and_blocked_process_abstain_before_capture(self):
        self.configure('window', retain=True, provider=True)
        for values in ({'process_name': 'powershell.exe'}, {'process_started': 'changed'}):
            with self.subTest(values=values):
                with patch('backend.actions.windows_automation.' + next(iter(values)), return_value=next(iter(values.values()))):
                    self.advance()
                self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])
        self.mocks[3].assert_not_called()

    def test_profiles_and_exclusions_control_sources_without_creating_effects(self):
        self.configure('window')
        self.service.configure({'profile': 'discreto'})
        self.service.tick()
        self.mocks[3].assert_not_called()
        self.service.configure({'profile': 'full'})
        self.service.tick()
        self.assertEqual(self.mocks[3].call_count, 1)
        self.service.configure({'scopes': [{'task_id': 'source-task', 'exclude': True}]})
        self.advance()
        self.assertEqual(self.mocks[3].call_count, 1)
        self.assertFalse(self.service.status()['source_runtime'][0]['active'])
        self.assertEqual(self.service.source_state, {})
        self.assertEqual(self.service.suggestions(), [])
        self.assertEqual(self.executor.list_operations(), [])

    def test_context_leases_expire_on_change_revoke_pause_stop_forget_and_close(self):
        for mutation in ('changed', 'revoke', 'pause', 'stop', 'forget', 'close'):
            with self.subTest(mutation=mutation):
                self.configure(retain=True, provider=True)
                self.service.tick()
                context = self.service.provider_context_for_task('source-task')
                lease = self.service.acquire_provider_context('source-task', context['refs'])
                self.assertIsInstance(lease, threading.Event)
                self.assertFalse(lease.is_set())
                if mutation == 'changed':
                    self.clip['sequence_number'] += 1
                    self.clip['text'] += ' changed'
                    self.advance()
                elif mutation == 'revoke':
                    target = self.service.status()['observation_targets'][0]
                    self.service.configure({'observation_targets': [target | {'send_to_provider': False}]})
                elif mutation == 'pause':
                    self.service.pause()
                elif mutation == 'stop':
                    self.service.cancel()
                elif mutation == 'forget':
                    self.service.forget({'task_id': 'source-task'})
                else:
                    self.service.close()
                self.assertTrue(lease.is_set())
                with self.assertRaises(ValueError):
                    self.service.validate_provider_context_refs('source-task', context['refs'])
                self.service.release_provider_context(lease)
                if mutation != 'close':
                    self.service.configure({'paused': False, 'observation_paused': False})

    def test_wall_and_monotonic_ttl_expire_raw_without_poll_or_persistence(self):
        self.configure(retain=True, provider=True)
        self.service.tick()
        context = self.service.provider_context_for_task('source-task')
        lease = self.service.acquire_provider_context('source-task', context['refs'])
        self.now += 61
        self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])
        self.assertTrue(lease.is_set())
        self.assertNotIn('raw', self.service.source_state['fixture-source'])
        self.service.configure({'observation_targets': []})
        with patch('backend.anticipation.RAW_SOURCE_TTL_SECONDS', .05):
            self.configure(retain=True, provider=True)
            self.service.tick()
            context = self.service.provider_context_for_task('source-task')
            lease = self.service.acquire_provider_context('source-task', context['refs'])
            self.assertTrue(lease.wait(1))
            self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])
        self.assert_private_not_durable([self.clip['text']])

    def test_raw_context_limit_and_ref_validation_are_fail_closed(self):
        target = self.configure(retain=True, provider=True)
        for invalid in ([{'target_id': [], 'consent_digest': '', 'observation_id': '', 'generation': 1}],
                [None], 'wrong', [{}]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.service.validate_provider_context_refs('source-task', invalid)
        targets = [target | {'id': 'source-' + str(number)} for number in range(5)]
        self.service.configure({'observation_targets': targets})
        self.service.tick()
        context = self.service.provider_context_for_task('source-task')
        self.assertEqual(len(context['observations']), 4)
        self.assertLessEqual(len(json.dumps(context).encode()), 1048576)
        self.clip['text'] = 'x' * 8193
        self.advance()
        self.assertEqual(self.service.provider_context_for_task('source-task')['observations'], [])

    def test_worker_revoke_cancels_without_policy_lock_and_discards_late_result(self):
        for mutation in ('revoke', 'stop', 'close'):
            with self.subTest(mutation=mutation):
                self.configure(retain=True, provider=True)
                entered, release = threading.Event(), threading.Event()
                cancellations, errors = [], []
                def held(*, max_characters, cancelled):
                    self.assertFalse(self.service.lock._is_owned())
                    cancellations.append(cancelled)
                    entered.set()
                    self.assertTrue(release.wait(5))
                    return copy.deepcopy(self.clip)
                self.mocks[2].side_effect = held
                def poll():
                    try:
                        self.service.tick()
                    except Exception as exc:
                        errors.append(exc)
                thread = threading.Thread(target=poll)
                thread.start(); self.assertTrue(entered.wait(5))
                if mutation == 'revoke':
                    self.service.configure({'observation_targets': []})
                elif mutation == 'stop':
                    self.service.cancel()
                else:
                    self.service.close()
                self.assertTrue(cancellations[0].is_set())
                release.set(); thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(self.service.source_state, {})
                if mutation != 'close':
                    self.assertEqual(self.service.status()['source_observations'], [])
                    self.service.configure({'paused': False})

    def test_late_window_uia_after_revocation_is_cleaned_without_publishing(self):
        self.configure('window', retain=True, provider=True)
        entered, release = threading.Event(), threading.Event()
        original = self.window
        def late(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(*args, **kwargs)
        self.mocks[3].side_effect = late
        errors = []
        def poll():
            try:
                self.service.tick()
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=poll)
        thread.start(); self.assertTrue(entered.wait(5))
        self.service.configure({'observation_targets': []})
        release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.service.source_state, {})
        self.assertEqual(self.service.status()['source_observations'], [])
        with windows._observation_lock:
            self.assertFalse(any(key.startswith('source-uia-') for key in windows._observations))
        self.assert_private_not_durable([self.window_title])


if __name__ == '__main__':
    unittest.main()
