"""Opt-in metadata sources and real local verifiers; no desktop input."""
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService, DEFAULTS
from backend.commands import CommandService


class AnticipationSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'selected'
        self.folder.mkdir()
        self.now = time.time()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.commands.dispatch_guard = self.service.dispatch_guard
        self.executor.result_filter = self.service.filter_result

    def tearDown(self):
        self.service.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    def configure_folder(self, retain=False, **changes):
        target = {'id': 'selected-folder', 'source': 'folder', 'task_id': 'source-task',
            'root': str(self.folder), 'observe': True, 'retain': retain, 'send_to_provider': False,
            'expires_at': None, 'device_id': 'host'}
        settings = {'profile': 'copiloto', 'sources': {'folders': True}, 'observation_targets': [target],
            'profiles': {'copiloto': {'cooldown_seconds': 0, 'cadence_seconds': 5,
                'resources': {'max_tick_ms': 5000, 'max_cpu_ms_tick': 1000}}}}
        settings.update(changes)
        self.service.configure(settings)
        return target

    def advance(self, seconds=5):
        self.now += seconds
        return self.service.tick()

    def test_new_sources_are_disabled_by_default_and_permission_dimensions_are_strict(self):
        with patch.object(self.service, '_folder_snapshot') as folder, patch.object(self.service, '_application_snapshot') as applications:
            self.service.tick()
            folder.assert_not_called(); applications.assert_not_called()
        status = self.service.status()
        self.assertFalse(status['sources']['folders'])
        self.assertFalse(status['sources']['applications'])
        self.assertFalse(status['capabilities']['physical_execution'])
        self.configure_folder()
        target = self.service.status()['observation_targets'][0]
        for change in ({'send_to_provider': True}, {'observe': 1}, {'retain': 'true'}, {'device_id': None}, {'device_id': 'unconnected-phone'}, {'unknown': True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.service.configure({'observation_targets': [target | change]})
        for changes in ({'sources': {'screen': True}}, {'sources': {'microphone': True}},
            {'sources': {'clipboard': True}}, {'profiles': {'copiloto': {'cadence_seconds': 0}}},
            {'profiles': {'copiloto': {'resources': {'max_events_tick': 0}}}},
            {'profiles': {'copiloto': {'schedule': {'timezone': 'Invalid/Zone', 'days': [0], 'start': '00:00', 'end': '23:59'}}}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.configure(changes)

    def test_observe_without_retention_has_only_transient_metadata_and_no_actions(self):
        self.configure_folder()
        self.service.tick()
        secret = 'RAW_CONTENT_MUST_NEVER_ENTER_STATE'
        path = self.folder / 'private-fresh-file.txt'
        path.write_text(secret)
        self.service.tick()
        self.assertEqual(self.service.status()['source_observations'], [])
        self.advance()
        status = self.service.status()
        self.assertEqual(status['source_runtime'][0]['samples'], 2)
        self.assertEqual(status['source_runtime'][0]['events'], 1)
        event = status['source_observations'][0]
        self.assertEqual(event['type'], 'file.created')
        self.assertFalse(event['retained'])
        self.assertFalse(event['sent_to_provider'])
        self.assertNotIn(secret, json.dumps(status))
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM anticipation_events').fetchone()[0], 0)
        self.assertEqual(self.service.suggestions(), [])
        self.assertEqual(self.executor.list_operations(), [])
        state = self.executor.db_path.read_bytes()
        self.assertNotIn(secret.encode(), state)
        self.assertNotIn(path.name.encode(), state)
        self.service.pause()
        self.assertEqual(self.service.status()['source_observations'], [])
        self.assertEqual(self.service.source_state, {})

    def test_retained_metadata_can_propose_but_cannot_inspect_until_accepted(self):
        self.configure_folder(retain=True)
        self.service.tick()
        path = self.folder / 'test.docx'
        path.write_bytes(b'a document format is not validated by its hash')
        self.advance()
        item = self.service.suggestions()[0]
        self.assertEqual(item['state'], 'AWAITING_APPROVAL')
        self.assertIsNone(item['plan']['expected_sha256'])
        self.assertEqual(item['plan']['verification_basis'], 'observed_file_snapshot')
        self.assertEqual(item['verification_scope'], 'integrity_only')
        self.assertEqual(self.executor.list_operations(), [])
        result = self.service.accept(item['suggestion_id'], item['plan_hash'])
        self.assertEqual(result['state'], 'VERIFIED')
        self.assertEqual(result['result']['output']['files'][0]['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(result['result']['output']['semantic_verified'])
        self.assertFalse(result['result']['output']['raw_content_retained'])
        second = self.folder / 'pending.txt'
        second.write_text('pending')
        self.advance()
        pending = next(row for row in self.service.suggestions() if row['state'] == 'AWAITING_APPROVAL')
        self.service.configure({'observation_targets': []})
        self.assertEqual(self.service.accept(pending['suggestion_id'], pending['plan_hash'])['state'], 'CANCELLED')
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_folder_limits_defer_events_and_report_truncation_without_replaying(self):
        self.configure_folder(retain=False, profiles={'copiloto': {'cadence_seconds': 5,
            'resources': {'max_events_tick': 1, 'max_entries_scan': 10, 'max_tick_ms': 5000, 'max_cpu_ms_tick': 1000}}})
        self.service.tick()
        (self.folder / 'first').write_bytes(b'a')
        (self.folder / 'second').write_bytes(b'b')
        self.advance()
        self.assertEqual(len(self.service.status()['source_observations']), 1)
        self.assertTrue(self.service.status()['source_runtime'][0]['truncated'])
        self.advance()
        self.assertEqual(len(self.service.status()['source_observations']), 2)
        self.advance()
        self.assertEqual(len(self.service.status()['source_observations']), 2)
        self.service.configure({'profiles': {'copiloto': {'resources': {'max_entries_scan': 1}}}})
        self.advance()
        self.assertTrue(self.service.status()['source_runtime'][0]['truncated'])
        self.assertEqual(len(self.service.source_state['selected-folder']['snapshot']), 1)

    def test_source_target_rebinding_and_retention_revocation_cancel_old_proposals(self):
        target = self.configure_folder(retain=True)
        self.service.tick()
        (self.folder / 'old.txt').write_text('old root')
        self.advance()
        old = self.service.suggestions()[0]
        new_root = self.root / 'new-selected'
        new_root.mkdir()
        target['root'] = str(new_root)
        self.service.configure({'observation_targets': [target]})
        self.assertEqual(self.service.accept(old['suggestion_id'], old['plan_hash'])['state'], 'CANCELLED')
        self.service.tick()
        (new_root / 'pending.txt').write_text('new root')
        self.advance()
        pending = next(item for item in self.service.suggestions() if item['state'] == 'AWAITING_APPROVAL')
        target['retain'] = False
        self.service.configure({'observation_targets': [target]})
        self.assertEqual(self.service.accept(pending['suggestion_id'], pending['plan_hash'])['state'], 'CANCELLED')
        self.assertEqual(self.executor.list_operations(), [])

    def test_overlapping_journal_and_folder_observations_verify_a_generation_once(self):
        self.service.configure({'profile': 'full', 'sources': {'folders': True},
            'profiles': {'full': {'cooldown_seconds': 0, 'cadence_seconds': 5,
                'resources': {'max_tick_ms': 5000, 'max_cpu_ms_tick': 1000}}},
            'observation_targets': [{'id': 'artifacts', 'source': 'folder', 'task_id': 'source-task',
                'root': str(self.executor.workspace_root), 'observe': True, 'retain': True}]})
        self.service.grant({'task_id': 'source-task', 'capability': 'verify_artifact',
            'root': str(self.executor.workspace_root), 'expires_at': None})
        self.service.tick()
        command = self.commands.prepare('axx.artifact.write', {'path': 'overlap.txt', 'content': 'one generation'},
            operation_id='overlap-writer', conversation_id='source-task')
        self.assertEqual(self.commands.execute(command['operation_id'], approved=True)['state'], 'succeeded')
        self.advance()
        items = self.service.suggestions()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['state'], 'VERIFIED')
        self.assertEqual(items[0]['plan']['verification_basis'], 'generation_receipt')
        self.assertEqual(len([row for row in self.executor.list_operations() if row['tool_name'] == 'file_inspection']), 1)
        self.assertEqual(self.service.status()['metrics']['eligible'], 1)

    def test_automatic_backlog_rechecks_elapsed_budget_before_each_dispatch(self):
        self.folder = self.executor.workspace_root
        self.configure_folder(retain=True, profile='full', profiles={'full': {'cooldown_seconds': 0,
            'cadence_seconds': 5, 'resources': {'max_tick_ms': 100, 'max_cpu_ms_tick': 1000}}})
        self.service.grant({'task_id': 'source-task', 'capability': 'verify_artifact',
            'root': str(self.folder), 'expires_at': None})
        self.service.tick()
        for number in range(3):
            (self.folder / ('file-' + str(number))).write_text('read only')
        accepted = self.service.accept
        def slow_receipt(*args, **kwargs):
            result = accepted(*args, **kwargs)
            time.sleep(0.12)
            return result
        with patch.object(self.service, 'accept', side_effect=slow_receipt):
            self.assertEqual(len(self.advance()), 1)
        self.assertEqual(sum(item['state'] == 'AWAITING_APPROVAL' for item in self.service.suggestions()), 2)
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.advance()
        self.assertEqual(sum(item['state'] == 'VERIFIED' for item in self.service.suggestions()), 3)

    def test_application_source_uses_existing_metadata_reader_and_discards_titles(self):
        target = {'id': 'app', 'source': 'application', 'task_id': 'app-task',
            'process_name': 'notepad.exe', 'observe': True, 'retain': False, 'send_to_provider': False}
        windows = [{'window_id': 42, 'pid': 7, 'title': 'PRIVATE_TITLE_MUST_NOT_BE_RETAINED', 'foreground': False}]
        with patch.object(self.service, '_applications_available', return_value=True), \
             patch('backend.actions.windows_automation.list_windows', side_effect=lambda **kwargs: copy.deepcopy(windows)) as reader, \
             patch('backend.actions.windows_automation.process_name', return_value='notepad.exe'), \
             patch('backend.actions.windows_automation.process_started', return_value=100):
            self.service.configure({'profile': 'copiloto', 'sources': {'applications': True},
                'observation_targets': [target], 'profiles': {'copiloto': {'cadence_seconds': 5}}})
            self.service.tick()
            reader.assert_called_with(include_untitled=True, include_titles=False)
            windows[0]['foreground'] = True
            self.advance()
            event = self.service.status()['source_observations'][0]
            self.assertEqual(event['type'], 'application.foreground')
            self.assertEqual(event['resource']['process_name'], 'notepad.exe')
            self.assertNotIn('PRIVATE_TITLE', json.dumps(self.service.status()))
            self.assertNotIn(b'PRIVATE_TITLE', self.executor.db_path.read_bytes())
            windows.clear()
            self.advance()
            self.assertEqual(self.service.status()['source_observations'][-1]['type'], 'application.closed')
        self.assertEqual(self.executor.list_operations(), [])

    def test_project_application_device_scopes_require_known_context_and_exclusions_win(self):
        target = self.configure_folder()
        target.update(project_id='project-a', application_id='notepad.exe')
        scopes = [{'project_id': 'project-a', 'application_id': 'notepad.exe', 'device_id': 'host', 'profile': 'copiloto'}]
        self.service.configure({'profile': 'discreto', 'scopes': scopes, 'observation_targets': [target]})
        name, options = self.service._policy('source-task', str(self.folder), context=self.service._source_context(self.service.status()['observation_targets'][0]))
        self.assertEqual(name, 'copiloto')
        self.assertEqual(options['mode'], 'SUGGEST')
        self.assertEqual(self.service._policy('source-task', str(self.folder))[1]['mode'], 'OFF')
        self.service.configure({'scopes': scopes + [{'project_id': 'project-a', 'exclude': True}]})
        self.service.tick()
        self.assertFalse(self.service.status()['source_runtime'][0]['active'])
        self.service.configure({'scopes': [{'project_id': 'Proyecto de diseño', 'application_id': 'Acme Editor.exe', 'device_id': 'host', 'profile': 'full'}]})
        context = {'project_id': 'Proyecto de diseño', 'application_id': 'Acme Editor.exe', 'device_id': 'host'}
        self.assertEqual(self.service._policy('source-task', str(self.folder), context=context)[0], 'full')

    def test_schedule_and_expiry_stop_observation_and_allow_editing_expired_targets(self):
        try:
            ZoneInfo('UTC')
        except ZoneInfoNotFoundError:
            self.skipTest('IANA timezone database unavailable; configuration already fails closed')
        self.now = dt.datetime(2026, 10, 26, 23, 0, tzinfo=dt.timezone.utc).timestamp()
        target = self.configure_folder()
        target['expires_at'] = self.now + 6 * 3600
        self.service.configure({'observation_targets': [target], 'profiles': {'copiloto': {
            'schedule': {'timezone': 'UTC', 'days': [0], 'start': '22:00', 'end': '02:00'}}}})
        self.service.tick()
        self.now += 2 * 3600
        (self.folder / 'night').write_bytes(b'x')
        self.service.tick()
        self.assertEqual(len(self.service.status()['source_observations']), 1)
        self.now += 2 * 3600
        self.service.tick()
        self.assertFalse(self.service.status()['source_runtime'][0]['active'])
        self.now += 3 * 3600
        self.service.configure({'observation_targets': [target], 'profiles': {'copiloto': {'schedule': None}}})
        self.service.tick()
        self.assertFalse(self.service.status()['source_runtime'][0]['active'])

    def test_cpu_wall_and_file_size_limits_are_effective_admission_controls(self):
        self.configure_folder(retain=True, profiles={'copiloto': {'cadence_seconds': 5,
            'resources': {'max_file_bytes': 1024, 'max_tick_ms': 50, 'max_cpu_ms_tick': 10}}})
        with patch.object(self.service, '_folder_snapshot') as reader:
            self.service.tick_started = (time.perf_counter() - 1, time.process_time())
            self.service._poll_sources()
            reader.assert_not_called()
            self.service.tick_started = (time.perf_counter(), time.process_time() - 1)
            self.service._poll_sources()
            reader.assert_not_called()
        self.service.tick_started = None
        self.service.tick()
        (self.folder / 'big.bin').write_bytes(b'x' * 2048)
        self.advance()
        self.assertEqual(self.service.suggestions(), [])
        self.assertEqual(self.service.status()['metrics']['abstained'], 1)
        self.assertEqual(self.executor.list_operations(), [])

    def test_format_verifiers_are_available_only_with_existing_engines_and_retention_hook(self):
        for extension in ('docx', 'xlsx', 'pptx', 'unknown'):
            descriptor = self.service._verifier('file.' + extension)
            self.assertEqual(descriptor['command_id'], 'axx.file.sha256')
            self.assertEqual(descriptor['verification_scope'], 'integrity_only')
            self.assertFalse(descriptor['semantic_verified'])
        with patch('backend.anticipation.shutil.which', return_value=None):
            self.assertFalse(self.service._verifier('file.mp4')['available'])
        self.executor.result_filter = None
        self.assertFalse(self.service._verifier('file.pdf')['available'])
        self.assertFalse(self.service._verifier('file.png')['available'])

    def pdf(self, path):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        except ImportError:
            self.skipTest('Existing PDF reader unavailable')
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        content = DecodedStreamObject(); content.set_data(b'BT /F1 12 Tf 20 200 Td (RAW_PDF_TEXT_NOT_FOR_STORAGE) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(content)
        with path.open('wb') as stream: writer.write(stream)
        return path

    def test_real_pdf_inspection_retains_structure_and_hash_but_never_extracted_text(self):
        self.configure_folder(retain=True)
        self.service.tick()
        path = self.pdf(self.folder / 'document.pdf')
        self.advance()
        item = self.service.suggestions()[0]
        self.assertEqual(item['plan']['command_id'], 'axx.artifact.pdf')
        result = self.service.accept(item['suggestion_id'], item['plan_hash'])
        self.assertEqual(result['state'], 'VERIFIED', result)
        output = result['result']['output']
        self.assertEqual(output['page_count'], 1)
        self.assertGreater(output['text_characters'], 0)
        self.assertNotIn('text_excerpt', output)
        self.assertEqual(output['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(output['semantic_verified'])
        self.assertNotIn(b'RAW_PDF_TEXT_NOT_FOR_STORAGE', self.executor.db_path.read_bytes())
        self.assertNotIn('RAW_PDF_TEXT_NOT_FOR_STORAGE', json.dumps(self.service.status()))
        metrics = self.service.status()['metrics']
        self.assertEqual(metrics['coverage']['numerator'], 1)
        self.assertEqual(metrics['coverage']['denominator'], 1)
        self.assertEqual(metrics['verification_latency_ms']['samples'], 1)
        self.assertGreaterEqual(metrics['tick_cpu_ms']['samples'], 2)
        self.assertIsNotNone(metrics['tick_cpu_ms']['p95'])

    def test_pdf_parser_errors_cannot_retain_document_fragments(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest('Existing PDF reader unavailable')
        self.configure_folder(retain=True)
        self.service.tick()
        writer = PdfWriter(); writer.add_blank_page(width=300, height=300)
        stream = io.BytesIO(); writer.write(stream)
        raw = stream.getvalue()
        match = re.search(rb'/MediaBox\s*\[([^\]]+)\]', raw)
        start, end = match.span(1)
        secret = b'RAW_PDF_SECRET!'
        self.assertLessEqual(len(secret), end - start)
        path = self.folder / 'malformed.pdf'
        path.write_bytes(raw[:start] + secret.ljust(end - start, b' ') + raw[end:])
        self.advance()
        item = self.service.suggestions()[0]
        result = self.service.accept(item['suggestion_id'], item['plan_hash'])
        self.assertEqual(result['state'], 'FAILED')
        self.assertIn('ARTIFACT_INSPECTION_FAILED', json.dumps(result['result']['error']))
        self.assertNotIn(secret, self.executor.db_path.read_bytes())
        self.assertNotIn(secret.decode(), json.dumps(self.service.status()))

    def test_forget_during_real_inspection_preserves_privacy_without_recreating_suggestion(self):
        self.configure_folder(retain=True)
        self.service.tick()
        self.pdf(self.folder / 'forget.pdf')
        self.advance()
        item = self.service.suggestions()[0]
        invoke = self.executor.invoke_primitive
        def forget_after_read(*args, **kwargs):
            result = invoke(*args, **kwargs)
            self.service.forget({'task_id': 'source-task'})
            return result
        with patch.object(self.executor, 'invoke_primitive', side_effect=forget_after_read):
            result = self.service.accept(item['suggestion_id'], item['plan_hash'])
        self.assertTrue(result['forgotten'])
        self.assertEqual(self.service.suggestions(), [])
        action = self.executor.get_operation(item['action_operation_id'])
        self.assertFalse(action['output']['raw_content_retained'])
        self.assertNotIn('text_excerpt', action['output'])
        self.assertNotIn(b'RAW_PDF_TEXT_NOT_FOR_STORAGE', self.executor.db_path.read_bytes())

    def test_close_waits_for_active_real_inspector_before_closing_privacy_policy(self):
        self.configure_folder(retain=True)
        self.service.tick()
        self.pdf(self.folder / 'closing.pdf')
        self.advance()
        item = self.service.suggestions()[0]
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        errors, results = [], []
        primitive = self.executor.invoke_primitive
        def hold_raw_result(*args, **kwargs):
            result = primitive(*args, **kwargs)
            entered.set()
            if not release.wait(5): raise AssertionError('Read release timed out')
            return result
        def inspect():
            try: results.append(self.service.accept(item['suggestion_id'], item['plan_hash']))
            except Exception as exc: errors.append(exc)
        def close():
            self.service.close(); closed.set()
        with patch.object(self.executor, 'invoke_primitive', side_effect=hold_raw_result):
            worker = threading.Thread(target=inspect); worker.start()
            self.assertTrue(entered.wait(5))
            closer = threading.Thread(target=close); closer.start()
            self.assertFalse(closed.wait(.05), 'Policy must stay open until the inspector commits its redacted receipt')
            release.set()
            worker.join(5); closer.join(5)
            self.assertFalse(worker.is_alive()); self.assertFalse(closer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1)
        receipt = self.executor.list_operations()[0]
        self.assertTrue(receipt['output']['raw_content_retained'] is False)
        self.assertNotIn('text_excerpt', receipt['output'])
        self.assertNotIn(b'RAW_PDF_TEXT_NOT_FOR_STORAGE', self.executor.db_path.read_bytes())
        with self.assertRaises(ValueError): self.service.dispatch_guard(item['operation_id'])

    def test_close_drains_parallel_read_before_privacy_database_is_closed(self):
        self.configure_folder(retain=True)
        self.service.tick()
        (self.folder / 'parallel.txt').write_text('private input')
        self.advance()
        item = self.service.suggestions()[0]
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        errors = []
        primitive, execute = self.executor.invoke_primitive, self.commands.execute
        def hold_read(*args, **kwargs):
            result = primitive(*args, **kwargs)
            result.output['text_excerpt'] = 'PRIVATE_PARALLEL_RESULT'
            entered.set()
            if not release.wait(5): raise AssertionError('Read release timed out')
            return result
        def parallel(*args, **kwargs):
            return execute(*args, **(kwargs | {'allow_parallel_read': True}))
        def inspect():
            try: self.service.accept(item['suggestion_id'], item['plan_hash'])
            except Exception as exc: errors.append(exc)
        def close():
            self.service.close(); closed.set()
        with patch.object(self.executor, 'invoke_primitive', side_effect=hold_read), \
             patch.object(self.commands, 'execute', side_effect=parallel):
            worker = threading.Thread(target=inspect); worker.start()
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.executor.parallel_reads, 1)
            closer = threading.Thread(target=close); closer.start()
            self.assertFalse(closed.wait(.05))
            release.set()
            worker.join(5); closer.join(5)
            self.assertFalse(worker.is_alive()); self.assertFalse(closer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.executor.parallel_reads, 0)
        self.assertNotIn(b'PRIVATE_PARALLEL_RESULT', self.executor.db_path.read_bytes())
        self.assertNotIn('text_excerpt', self.executor.list_operations()[0]['output'])


if __name__ == '__main__':
    unittest.main()
