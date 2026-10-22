import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from backend.magic_pen import MagicPenService, validate_selection


class MagicPenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = MagicPenService(Path(self.temp.name))
        self.doc = self.service.acquire(Image.new('RGB', (200, 100), 'white'), {'id': 'test', 'x': -200, 'y': 0})

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

    def test_queries_finishing_out_of_order_keep_ids_and_clean_pixels(self):
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
        second = self.service.analyze({'id': self.doc['id'], 'revision': 2, 'question': 'second'})
        self.assertEqual(second['state'], 'completed')
        release.set()
        first.join(3)
        self.assertEqual(results[0]['state'], 'completed')
        self.assertNotEqual(results[0]['id'], second['id'])
        saved = self.service.get(self.doc['id'])['queries']
        self.assertEqual([q['response'] for q in saved], ['first', 'second'])


if __name__ == '__main__':
    unittest.main()
