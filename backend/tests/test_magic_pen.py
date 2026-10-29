import tempfile
import ctypes
from ctypes import wintypes
import unittest
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from backend.magic_pen import MagicPenService, validate_selection, write_json, physical_dpi_context, monitors


class MagicPenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = MagicPenService(Path(self.temp.name))
        self.addCleanup(self.service.close)
        self.doc = self.service.acquire(Image.new('RGB', (200, 100), 'white'), {'id': 'test', 'x': -200, 'y': 0})

    def test_dpi_scope_preserves_pointer_sized_prior_context_and_restores_after_error(self):
        previous = wintypes.HANDLE(-2).value
        setter = Mock(side_effect=[previous, wintypes.HANDLE(-4).value])
        user = SimpleNamespace(SetThreadDpiAwarenessContext=setter)
        with patch('backend.magic_pen.ctypes.WinDLL', return_value=user):
            with self.assertRaisesRegex(RuntimeError, 'capture error'):
                with physical_dpi_context():
                    self.assertEqual(setter.call_args.args[0].value, wintypes.HANDLE(-4).value)
                    raise RuntimeError('capture error')
        self.assertEqual(setter.call_args_list[1].args[0].value, previous)
        self.assertEqual(setter.argtypes, [wintypes.HANDLE])
        self.assertIs(setter.restype, wintypes.HANDLE)

    def test_dpi_scope_rejects_null_and_reports_restore_failure(self):
        setter = Mock(return_value=None)
        user = SimpleNamespace(SetThreadDpiAwarenessContext=setter)
        with patch('backend.magic_pen.ctypes.WinDLL', return_value=user):
            with self.assertRaisesRegex(OSError, 'establecer'):
                with physical_dpi_context(): self.fail('must not enter an invalid context')
        self.assertEqual(setter.call_count, 1)
        setter.side_effect = [wintypes.HANDLE(-2).value, None]
        with patch('backend.magic_pen.ctypes.WinDLL', return_value=user):
            with self.assertRaisesRegex(OSError, 'restaurar'):
                with physical_dpi_context(): pass

    def test_monitor_enumeration_uses_physical_scope_and_restores(self):
        state = {'context': wintypes.HANDLE(-2).value}
        def switch(context):
            previous = state['context']; state['context'] = context.value; return previous
        def enumerate_physical(_dc, _rect, callback, data):
            self.assertEqual(state['context'], wintypes.HANDLE(-4).value)
            rect = wintypes.RECT(1920, 0, 3840, 1080)
            self.assertTrue(callback(None, None, ctypes.pointer(rect), data))
            return True
        user = SimpleNamespace(SetThreadDpiAwarenessContext=Mock(side_effect=switch),
                               EnumDisplayMonitors=Mock(side_effect=enumerate_physical))
        with patch('backend.magic_pen.ctypes.WinDLL', return_value=user):
            result = monitors()
        self.assertEqual(result, [{'id': '1920,0,3840,1080', 'x': 1920, 'y': 0, 'width': 1920, 'height': 1080}])
        self.assertEqual(state['context'], wintypes.HANDLE(-2).value)
        self.assertEqual(user.SetThreadDpiAwarenessContext.call_count, 2)

    def test_capture_keeps_dpi_scope_through_grab_and_revalidation(self):
        state = {'context': wintypes.HANDLE(-2).value}
        def switch(context):
            previous = state['context']; state['context'] = context.value; return previous
        user = SimpleNamespace(SetThreadDpiAwarenessContext=Mock(side_effect=switch))
        physical = {'id': '1920,0,3840,1080', 'x': 1920, 'y': 0, 'width': 1920, 'height': 1080}
        def check_monitors():
            self.assertEqual(state['context'], wintypes.HANDLE(-4).value)
            return [physical]
        def grab(**options):
            self.assertEqual(state['context'], wintypes.HANDLE(-4).value)
            self.assertEqual(options['bbox'], (1920, 0, 3840, 1080))
            return Image.new('RGB', (1920, 1080), 'white')
        with patch('backend.magic_pen.ctypes.WinDLL', return_value=user), patch('backend.magic_pen.monitors', side_effect=check_monitors) as enum, \
                patch('backend.magic_pen.ImageGrab.grab', side_effect=grab):
            result = self.service.capture({'monitor': physical['id']})
        self.assertEqual(enum.call_count, 2)
        self.assertEqual(result['source']['width'], 1920)
        self.assertEqual(state['context'], wintypes.HANDLE(-2).value)
        with patch('backend.magic_pen.ctypes.WinDLL', return_value=user), patch('backend.magic_pen.monitors', return_value=[physical]), \
                patch('backend.magic_pen.ImageGrab.grab', side_effect=RuntimeError('capture failed')):
            with self.assertRaisesRegex(RuntimeError, 'capture failed'): self.service.capture({'monitor': physical['id']})
        self.assertEqual(state['context'], wintypes.HANDLE(-2).value)

    def test_invalid_and_lasso_geometry(self):
        for bounds in [[0, 0, 0, 5], [-1, 0, 3, 5], [0, 0, 201, 5], [0, 0, float('nan'), 5]]:
            with self.assertRaises(ValueError):
                validate_selection({'shape': 'rect', 'bounds': bounds}, 200, 100)
        good = {'shape': 'lasso', 'bounds': [10, 10, 40, 40], 'points': [[10, 10], [40, 10], [25, 40]]}
        self.assertEqual(validate_selection(good, 200, 100)['shape'], 'lasso')

    def test_edit_recovery_original_and_exclusive_export(self):
        edit = {'id': self.doc['id'], 'expected_revision': 1, 'selection': {'shape': 'rect', 'bounds': [5, 5, 60, 60]},
                'strokes': [{'tool': 'pen', 'color': '#ff0000', 'width': 6, 'points': [[10, 10], [50, 50]]}]}
        self.service.save(edit)
        with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
            self.service.save(edit)
        recovered = MagicPenService(Path(self.temp.name)).get(self.doc['id'])
        self.assertEqual(len(recovered['strokes']), 1)
        for kind in ['original', 'annotated']:
            out = self.service.export({'id': self.doc['id'], 'revision': 2, 'kind': kind, 'directory': self.temp.name, 'name': kind})
            self.assertTrue(out['verified'])
            with Image.open(out['path']) as im:
                self.assertEqual(im.size, (200, 100))
                self.assertEqual(im.getpixel((25, 25)), (255, 255, 255) if kind == 'original' else (255, 0, 0))
            with self.assertRaises(FileExistsError):
                self.service.export({'id': self.doc['id'], 'revision': 2, 'kind': kind, 'directory': self.temp.name, 'name': kind})
        self.assertEqual(recovered['source']['sha256'], self.doc['source']['sha256'])

    def test_failed_write_does_not_publish(self):
        with patch('backend.magic_pen.os.link', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.service.export({'id': self.doc['id'], 'revision': 1, 'kind': 'original', 'directory': self.temp.name, 'name': 'failed'})
        self.assertFalse((Path(self.temp.name) / 'failed.png').exists())
        self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))

    def test_absent_vision_is_real_error_and_query_has_snapshot(self):
        class Adapter:
            config = {'providers': []}
        self.service.adapter = Adapter()
        self.service.save({'id': self.doc['id'], 'expected_revision': 1, 'selection': {'shape': 'point', 'anchor': [25, 25], 'bounds': [5, 5, 60, 60]}, 'strokes': []})
        result = self.service.analyze({'id': self.doc['id'], 'revision': 2, 'question': '¿Qué es esto?'})
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['selection']['anchor'], [25, 25])
        self.assertIn('Análisis visual no configurado', result['error'])
        self.assertEqual(len(self.service.get(self.doc['id'])['queries']), 1)

    def test_vision_respects_existing_provider_billing_authorization(self):
        class Adapter:
            config = {'providers': [
                {'name': 'authorized', 'model': 'vision', 'enabled': True,
                 'free_confirmed': False, 'billing_allowed': True, 'capabilities': ['vision']},
                {'name': 'unauthorized', 'model': 'vision', 'enabled': True,
                 'free_confirmed': False, 'billing_allowed': False, 'capabilities': ['vision']}]}
        self.service.adapter = Adapter()
        self.assertEqual(self.service.capabilities()['vision'], [{'name': 'authorized', 'model': 'vision'}])

    def test_late_response_keeps_original_selection_and_never_sends_ink(self):
        entered, release = threading.Event(), threading.Event()
        class Adapter:
            config = {'providers': [{'name': 'fixture', 'model': 'test', 'enabled': True, 'free_confirmed': True, 'capabilities': ['vision']}]}
            request = None
            def route(self, request):
                self.request = request
                entered.set()
                release.wait(3)
                return {'ok': True, 'message': {'content': 'Contract fixture, not real recognition'}}
        adapter = Adapter()
        self.service.adapter = adapter
        first = {'shape': 'rect', 'bounds': [10, 10, 50, 50]}
        self.service.save({'id': self.doc['id'], 'expected_revision': 1, 'selection': first, 'strokes': []})
        result = []
        thread = threading.Thread(target=lambda: result.append(self.service.analyze({'id': self.doc['id'], 'revision': 2, 'question': 'test'})))
        thread.start()
        self.assertTrue(entered.wait(3))
        self.service.save({'id': self.doc['id'], 'expected_revision': 2, 'selection': {'shape': 'rect', 'bounds': [60, 10, 100, 50]}, 'strokes': []})
        release.set()
        thread.join(3)
        self.assertEqual(result[0]['selection'], first)
        self.assertEqual(result[0]['revision'], 2)
        self.assertEqual(self.service.get(self.doc['id'])['revision'], 3)
        self.assertNotIn('tools', adapter.request['generation'])
        self.assertEqual(adapter.request['messages'][1]['content'][1]['type'], 'image_url')

    def test_rejects_reference_escape_and_corrupt_original(self):
        with self.assertRaises(ValueError):
            self.service.get('../original')
        path = self.service.directory(self.doc['id']) / 'original.png'
        path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'integridad'):
            self.service.get(self.doc['id'], image=True)

    def test_serial_queries_cancel_replace_keep_ids_and_clean_pixels(self):
        import base64
        import io
        entered, release = threading.Event(), threading.Event()
        test = self
        class Adapter:
            config = {'providers': [{'name': 'fixture', 'model': 'test', 'enabled': True,
                                     'free_confirmed': True, 'capabilities': ['vision']}]}
            def route(self, request):
                content = request['messages'][1]['content']
                with Image.open(io.BytesIO(base64.b64decode(content[1]['image_url']['url'].split(',')[1]))) as im:
                    test.assertEqual(im.getpixel((15, 15)), (255, 255, 255))
                if content[0]['text'] == 'first':
                    entered.set()
                    release.wait(3)
                return {'ok': True, 'message': {'content': content[0]['text']}}
        self.service.adapter = Adapter()
        self.service.save({'id': self.doc['id'], 'expected_revision': 1,
            'selection': {'shape': 'rect', 'bounds': [5, 5, 60, 60]},
            'strokes': [{'tool': 'pen', 'color': '#ff0000', 'width': 20, 'points': [[20, 20], [40, 40]]}]})
        results = []
        first = threading.Thread(target=lambda: results.append(self.service.analyze(
            {'id': self.doc['id'], 'revision': 2, 'question': 'first'})))
        first.start()
        self.assertTrue(entered.wait(3))
        with self.assertRaisesRegex(ValueError, 'BUSY'):
            self.service.analyze({'id': self.doc['id'], 'revision': 2, 'question': 'second'})
        original = self.service.get(self.doc['id'])['queries'][0]
        self.service.cancel({'id': self.doc['id'], 'query_id': original['id']})
        second = self.service.start({'id': self.doc['id'], 'revision': 2, 'question': 'second', 'request_id': uuid.uuid4().hex})
        release.set()
        first.join(3)
        second = self.wait_query(second)
        self.assertEqual(second['state'], 'completed')
        self.assertEqual(results[0]['state'], 'cancelled')
        self.assertNotEqual(results[0]['id'], second['id'])
        saved = self.service.get(self.doc['id'])['queries']
        self.assertNotIn('response', saved[0])
        self.assertEqual(saved[1]['response'], 'second')

    def setup_analysis(self, adapter=None):
        class Adapter:
            config = {'allow_paid': False, 'providers': [{'name': 'fixture', 'model': 'visual-model', 'enabled': True,
                'free_confirmed': True, 'capabilities': ['vision']}]}
            def __init__(self): self.calls = []; self.cancelled = []
            def route(self, request):
                self.calls.append(request)
                return {'ok': True, 'message': {'content': 'Respuesta de contrato; no reconocimiento real.'}}
            def cancel(self, request_id):
                self.cancelled.append(request_id)
                return True
        self.service.adapter = adapter or Adapter()
        self.service.save({'id': self.doc['id'], 'expected_revision': 1,
                           'selection': {'shape': 'rect', 'bounds': [5, 5, 60, 60]}, 'strokes': []})
        return self.service.adapter

    def test_perception_uses_shared_policy_without_action_or_translation_contract(self):
        adapter = self.setup_analysis()
        result = self.wait_query(self.service.start(self.request()))
        self.assertEqual(result['state'], 'completed')
        instructions = adapter.calls[0]['messages'][0]['content']
        self.assertIn('AXX_PROMPT axx-contracts-1 mode=perception', instructions)
        self.assertIn('no ejecutes acciones', instructions)
        self.assertNotIn('axx_execute_action', instructions)
        self.assertNotIn('Return only the translation', instructions)

    def request(self, **kw):
        return {'id': self.doc['id'], 'revision': 2, 'question': '¿Qué aparece?',
                'provider': 'fixture', 'model': 'visual-model', 'selection_mode': 'manual',
                'request_id': uuid.uuid4().hex, **kw}

    def wait_query(self, q, timeout=3):
        end = time.monotonic() + timeout
        while q['state'] == 'running' and time.monotonic() < end:
            time.sleep(.01)
            q = self.service.query({'id': q['source_id'], 'query_id': q['id']})
        self.assertNotEqual(q['state'], 'running', q)
        return q

    def test_acquire_no_preview_by_default_get_image_is_explicit(self):
        self.assertNotIn('preview', self.doc)
        self.assertNotIn('preview', self.service.get(self.doc['id']))
        self.assertTrue(self.service.get(self.doc['id'], image=True)['preview'].startswith('data:image/png;base64,'))

    def test_async_start_query_idempotent_snapshot_and_reopen(self):
        adapter = self.setup_analysis()
        request = self.request()
        started = self.service.start(request)
        self.assertEqual(started['id'], request['request_id'])
        done = self.wait_query(started)
        self.assertEqual(done['state'], 'completed')
        self.service.save({'id': self.doc['id'], 'expected_revision': 2,
                           'selection': {'shape': 'rect', 'bounds': [60, 10, 100, 50]}, 'strokes': []})
        self.assertEqual(self.service.start(request), done)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(done['revision'], 2)
        self.assertEqual(done['selection']['bounds'], [5, 5, 60, 60])
        self.service.close()
        reopened = MagicPenService(self.temp.name, adapter)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.start(request), done)
        self.assertEqual(len(adapter.calls), 1)

    def test_reused_request_rejects_changed_question_source_or_model(self):
        self.setup_analysis()
        request = self.request()
        self.wait_query(self.service.start(request))
        for changed in [request | {'question': 'otra'}, request | {'revision': 3}, request | {'model': 'other'},
                        request | {'id': uuid.uuid4().hex}]:
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'REQUEST_ID_CONFLICT'):
                self.service.start(changed)

    def test_manual_selection_never_falls_back_to_other_visual_provider(self):
        adapter = self.setup_analysis()
        for fields in [{'provider': 'unknown'}, {'model': 'wrong'}, {'provider': '', 'model': 'wrong'}]:
            with self.subTest(fields=fields):
                q = self.service.start(self.request(**fields))
                self.assertEqual(q['state'], 'failed')
        self.assertEqual(adapter.calls, [])
        q = self.wait_query(self.service.start(self.request(provider='', model='visual-model')))
        self.assertEqual(q['state'], 'completed')
        self.assertEqual(adapter.calls[0]['provider_name'], 'fixture')
        self.assertEqual(adapter.calls[0]['model'], 'visual-model')
        self.assertFalse(adapter.calls[0]['allow_paid'])

    def test_automatic_selection_is_explicit_and_passes_existing_free_policy(self):
        adapter = self.setup_analysis()
        q = self.wait_query(self.service.start(self.request(provider='not-used', model='not-used', selection_mode='automatic_free')))
        self.assertEqual(q['state'], 'completed')
        self.assertEqual(adapter.calls[0]['selection_mode'], 'automatic_free')
        self.assertEqual(adapter.calls[0]['provider_name'], '')
        self.assertEqual(adapter.calls[0]['model'], '')
        adapter.config = dict(adapter.config, allow_paid=True)
        self.assertEqual(self.service.start(self.request())['state'], 'failed')
        self.assertEqual(len(adapter.calls), 1)

    def test_cancel_before_adapter_registration_retries_and_discards_late_success(self):
        adapter = self.setup_analysis()
        before, register, cancelled = threading.Event(), threading.Event(), threading.Event()
        adapter.registered = False
        def route(request):
            adapter.calls.append(request)
            before.set(); register.wait(3)
            adapter.registered = True
            self.assertTrue(cancelled.wait(3), 'Cancellation must retry after registration')
            return {'ok': True, 'message': {'content': 'late answer must disappear'}}
        def cancel(request_id):
            adapter.cancelled.append(request_id)
            if adapter.registered: cancelled.set()
            return adapter.registered
        adapter.route, adapter.cancel = route, cancel
        q = self.service.start(self.request())
        self.assertTrue(before.wait(3))
        first = self.service.cancel({'id': self.doc['id'], 'query_id': q['id']})
        self.assertEqual(first['state'], 'cancelled')
        register.set()
        self.assertTrue(cancelled.wait(3))
        with self.service.condition:
            self.assertTrue(self.service.condition.wait_for(lambda: self.service.processing is None, timeout=3))
        saved = self.service.query({'id': self.doc['id'], 'query_id': q['id']})
        self.assertEqual(saved['state'], 'cancelled'); self.assertNotIn('response', saved)
        self.assertTrue(all(value == 'pen-' + q['id'] for value in adapter.cancelled))

    def test_cancelled_pending_job_never_enters_adapter(self):
        adapter = self.setup_analysis()
        with patch.object(threading.Thread, 'start'):
            q = self.service.start(self.request())
            self.assertIsNotNone(self.service.pending)
            self.service.cancel({'id': self.doc['id'], 'query_id': q['id']})
            self.assertIsNone(self.service.pending)
        self.service.worker = None
        self.assertEqual(adapter.calls, [])

    def test_cancel_before_start_is_durable_and_never_dispatches(self):
        adapter = self.setup_analysis()
        request = self.request()
        cancelled = self.service.cancel({'id': self.doc['id'], 'query_id': request['request_id']})
        self.assertEqual(cancelled['state'], 'cancelled')
        self.assertTrue(cancelled['preparation_cancelled'])
        self.service.close()
        reopened = MagicPenService(self.temp.name, adapter)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.start(request)['state'], 'cancelled')
        self.assertEqual(reopened.start(request)['state'], 'cancelled')
        with self.assertRaisesRegex(ValueError, 'REQUEST_ID_CONFLICT'):
            reopened.start(request | {'question': 'changed'})
        self.assertEqual(adapter.calls, [])

    def test_shutdown_cancels_running_and_rejects_new_jobs(self):
        adapter = self.setup_analysis()
        entered, stop = threading.Event(), threading.Event()
        def route(request):
            entered.set(); stop.wait(3)
            return {'ok': True, 'message': {'content': 'late'}}
        adapter.route = route
        adapter.cancel = lambda request_id: stop.set() or True
        q = self.service.start(self.request())
        self.assertTrue(entered.wait(3))
        self.service.close()
        self.assertEqual(self.service.query({'id': self.doc['id'], 'query_id': q['id']})['state'], 'cancelled')
        with self.assertRaises(ValueError): self.service.start(self.request())

    def test_reopen_marks_interrupted_and_old_id_cannot_restart(self):
        self.setup_analysis()
        request = self.request()
        with patch.object(threading.Thread, 'start'):
            q = self.service.start(request)
        self.service.worker = None
        reopened = MagicPenService(self.temp.name, self.service.adapter)
        self.addCleanup(reopened.close)
        recovered = reopened.query({'id': self.doc['id'], 'query_id': q['id']})
        self.assertEqual(recovered['state'], 'interrupted')
        self.assertEqual(reopened.start(request)['state'], 'interrupted')

    def test_history_is_bounded_but_pruned_request_id_remains_reserved(self):
        adapter = self.setup_analysis()
        adapter.config = {'providers': []}  # Fast failed jobs exercise durable history without inference.
        with patch('backend.magic_pen.MAX_QUERY_HISTORY', 3):
            requests = [self.request() for _ in range(5)]
            for request in requests: self.service.start(request)
        self.assertEqual(len(self.service.get(self.doc['id'])['queries']), 3)
        with self.assertRaisesRegex(ValueError, 'historial reciente'):
            self.service.start(requests[0])
        with self.assertRaisesRegex(ValueError, 'REQUEST_ID_CONFLICT'):
            self.service.start(requests[0] | {'question': 'otra'})
        self.assertEqual(adapter.calls, [])

    def test_history_pruning_keeps_running_query_locatable(self):
        self.setup_analysis()
        with patch.object(threading.Thread, 'start'):
            q = self.service.start(self.request())
        self.service.worker = None
        with patch('backend.magic_pen.MAX_QUERY_HISTORY', 3):
            for _ in range(5): self.service.cancel({'id': self.doc['id'], 'query_id': uuid.uuid4().hex})
        self.assertEqual(len(self.service.get(self.doc['id'])['queries']), 3)
        self.assertEqual(self.service.query({'id': self.doc['id'], 'query_id': q['id']})['state'], 'running')
        self.assertEqual(self.service.cancel({'id': self.doc['id'], 'query_id': q['id']})['state'], 'cancelled')

    def test_legacy_query_ids_are_reserved_without_reexecuting(self):
        adapter = self.setup_analysis()
        request = self.request()
        d = self.service.get(self.doc['id'])
        d['queries'] = [{'id': request['request_id'], 'source_id': d['id'], 'revision': 2,
                         'question': 'legacy', 'state': 'completed', 'response': 'legacy result'}]
        write_json(self.service.directory(d['id']) / 'document.json', d)
        reopened = MagicPenService(self.temp.name, adapter)
        self.addCleanup(reopened.close)
        with self.assertRaisesRegex(ValueError, 'REQUEST_ID_CONFLICT'): reopened.start(request)
        self.assertEqual(reopened.query({'id': d['id'], 'query_id': request['request_id']})['response'], 'legacy result')
        self.assertEqual(adapter.calls, [])

    def test_invalid_async_input_and_cross_source_query_are_rejected(self):
        self.setup_analysis()
        for change in [{'request_id': '../bad'}, {'revision': True}, {'question': ' '}, {'model': []},
                       {'provider': []}, {'selection_mode': 'anything'}, {'execute': True}]:
            with self.subTest(change=change), self.assertRaises(ValueError): self.service.start(self.request(**change))
        q = self.wait_query(self.service.start(self.request()))
        other = self.service.acquire(Image.new('RGB', (20, 20), 'white'), {'id': 'another'})
        with self.assertRaises(ValueError): self.service.query({'id': other['id'], 'query_id': q['id']})

    def test_fractional_selection_retains_at_least_one_pixel(self):
        self.setup_analysis()
        self.service.save({'id': self.doc['id'], 'expected_revision': 2,
            'selection': {'shape': 'rect', 'bounds': [5.1, 5.1, 5.2, 5.2]}, 'strokes': []})
        self.assertEqual(self.wait_query(self.service.start(self.request(revision=3)))['state'], 'completed')


if __name__ == '__main__':
    unittest.main()
