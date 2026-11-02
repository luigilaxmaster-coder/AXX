import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from PIL import Image
from backend.magic_pen import MagicPenService
from backend.presentation_plan import PlanError, apply_patch, parse_json, validate_plan


def plan(**kw):
    return {'schema_version': '1.0', 'kind': 'presentation', 'title': 'Límite de sin(x)/x', 'summary': 'El cociente tiende a 1.',
            'fidelity': 'conceptual', 'steps': [
                {'id': 's1', 'title': 'Función', 'body': 'f(x)=sin(x)/x', 'narration': 'Empezamos por la función.', 'basis': 'observed'},
                {'id': 's2', 'title': 'Cerca de cero', 'body': 'sin(x)≈x', 'narration': 'Cerca de cero el seno se parece a x.', 'basis': 'assumed'}], **kw}


def scene_plan():
    p = plan(scene={'fidelity': 'conceptual', 'objects': [
        {'id': 'o1', 'label': 'Placa genérica', 'shape': 'box', 'size': [4, .2, 3], 'position': [0, 0, 0], 'color': '#2E8B57', 'explode': [0, -1, 0]},
        {'id': 'o2', 'label': 'Módulo de cámara', 'shape': 'box', 'size': [1, .3, 1], 'position': [0, .5, 0], 'color': '#333333', 'explode': [0, 1.5, 0]}],
        'arrows': [{'from': 'o2', 'to': 'o1', 'label': 'cable plano'}]})
    p['steps'][0]['focus'] = ['o1']
    return p


class SceneContractTests(unittest.TestCase):
    def test_scene_is_validated_normalized_and_focus_is_cross_checked(self):
        result = validate_plan(scene_plan())
        self.assertEqual(result['scene']['objects'][0]['color'], '#2e8b57')
        self.assertEqual(result['scene']['objects'][0]['size'], [4.0, .2, 3.0])
        self.assertEqual(result['steps'][0]['focus'], ['o1'])
        self.assertNotIn('scene', validate_plan(plan()), 'Plans without 3D stay 2D')

    def test_scene_rejects_unlisted_primitives_ranges_refs_and_fidelity(self):
        def variant(change):
            p = scene_plan(); change(p); return p
        cases = {
            'remote asset': lambda p: p['scene']['objects'][0].update(shape='glb'),
            'extra url': lambda p: p['scene']['objects'][0].update(url='https://x/y.glb'),
            'named color': lambda p: p['scene']['objects'][0].update(color='red'),
            'nan': lambda p: p['scene']['objects'][0].update(position=[0, 0, float('nan')]),
            'out of range': lambda p: p['scene']['objects'][0].update(position=[0, 0, 99]),
            'zero size': lambda p: p['scene']['objects'][0].update(size=[0, 1, 1]),
            'bool vector': lambda p: p['scene']['objects'][0].update(size=[True, 1, 1]),
            'too many': lambda p: p['scene'].update(objects=[dict(p['scene']['objects'][0], id=f'o{i}') for i in range(25)]),
            'duplicate id': lambda p: p['scene']['objects'][1].update(id='o1'),
            'arrow unknown': lambda p: p['scene']['arrows'][0].update(to='o9'),
            'arrow self': lambda p: p['scene']['arrows'][0].update(to='o2'),
            'technical scene': lambda p: p['scene'].update(fidelity='technical'),
            'unknown focus': lambda p: p['steps'][1].update(focus=['o7']),
            'focus without scene': lambda p: p.pop('scene'),
        }
        for name, change in cases.items():
            with self.subTest(name), self.assertRaises(PlanError):
                validate_plan(variant(change))

    def test_object_update_patch_is_whitelisted_and_revalidated(self):
        base = validate_plan(scene_plan())
        result, _ = apply_patch(base, {'schema_version': '1.0', 'kind': 'patch', 'answer': 'Marco la cámara.',
                                       'ops': [{'op': 'object.update', 'object_id': 'o2', 'color': '#FF8800', 'position': [0, 1, 0]},
                                               {'op': 'step.update', 'step_id': 's2', 'focus': ['o2']}]})
        self.assertEqual(result['scene']['objects'][1]['color'], '#ff8800')
        self.assertEqual(result['steps'][1]['focus'], ['o2'])
        self.assertEqual(base['scene']['objects'][1]['color'], '#333333')
        for op in ({'op': 'object.update', 'object_id': 'o9', 'color': '#000000'}, {'op': 'object.update', 'object_id': 'o1'},
                   {'op': 'object.update', 'object_id': 'o1', 'script': 'x'}, {'op': 'object.update', 'object_id': 'o1', 'size': [50, 1, 1]}):
            with self.subTest(op=op), self.assertRaises(PlanError):
                apply_patch(base, {'schema_version': '1.0', 'kind': 'patch', 'answer': 'x', 'ops': [op]})
        with self.assertRaises(PlanError):
            apply_patch(validate_plan(plan()), {'schema_version': '1.0', 'kind': 'patch', 'answer': 'x',
                                                'ops': [{'op': 'object.update', 'object_id': 'o1', 'color': '#000000'}]})


class ContractTests(unittest.TestCase):
    def test_valid_plan_round_trips_and_trims(self):
        p = plan(title='  Límite  ')
        self.assertEqual(validate_plan(p)['title'], 'Límite')
        self.assertEqual(validate_plan(parse_json('```json\n' + json.dumps(p) + '\n```'))['steps'][1]['id'], 's2')

    def test_rejects_extra_fields_bad_enums_ids_sizes_and_versions(self):
        bad = [plan(script='alert(1)'), plan(fidelity='verified'), plan(schema_version='2.0'), plan(kind='patch'),
               plan(steps=plan()['steps'][:1]), plan(steps=plan()['steps'] * 5), plan(title='x' * 121)]
        dup = plan(); dup['steps'][1]['id'] = 's1'; bad.append(dup)
        html = plan(); html['steps'][0]['onclick'] = 'x'; bad.append(html)
        basis = plan(); basis['steps'][0]['basis'] = 'certain'; bad.append(basis)
        ident = plan(); ident['steps'][0]['id'] = '../s1'; bad.append(ident)
        for case in bad:
            with self.subTest(case=str(case)[:60]), self.assertRaises(PlanError):
                validate_plan(case)
        for text in ('Resumen: no es JSON', '[1,2]', '{"a":'):
            with self.subTest(text=text), self.assertRaises(PlanError):
                validate_plan(parse_json(text))

    def test_patch_updates_inserts_removes_and_revalidates(self):
        base = validate_plan(plan())
        new_step = {'id': 's3', 'title': 'Conclusión', 'body': 'El límite es 1.', 'narration': 'Por eso vale 1.', 'basis': 'inferred'}
        result, answer = apply_patch(base, {'schema_version': '1.0', 'kind': 'patch', 'answer': 'Añado la conclusión.', 'ops': [
            {'op': 'step.update', 'step_id': 's2', 'body': 'sin(x)≈x - x³/6'},
            {'op': 'step.insert_after', 'step_id': 's2', 'step': new_step}]})
        self.assertEqual([s['id'] for s in result['steps']], ['s1', 's2', 's3'])
        self.assertEqual(result['steps'][1]['body'], 'sin(x)≈x - x³/6')
        self.assertEqual(result['steps'][0], base['steps'][0], 'Untouched steps are preserved')
        self.assertEqual(answer, 'Añado la conclusión.')
        self.assertEqual(len(base['steps']), 2, 'The base plan is never mutated')

    def test_patch_rejects_unknown_ops_paths_and_invalid_results(self):
        base = validate_plan(plan())
        bad_ops = [[{'op': 'replace', 'path': '/title', 'value': 'x'}], [{'op': 'step.update', 'step_id': 's9', 'title': 'x'}],
                   [{'op': 'step.update', 'step_id': 's1'}], [{'op': 'step.update', 'step_id': 's1', 'html': '<b>'}],
                   [{'op': 'step.remove', 'step_id': 's1'}],  # would leave one step
                   [{'op': 'step.insert_after', 'step_id': 's1', 'step': dict(base['steps'][1])}],  # duplicate id
                   ['step.remove'], [{'op': 'step.remove', 'step_id': 's1'}] * 9]
        for ops in bad_ops:
            with self.subTest(ops=str(ops)[:60]), self.assertRaises(PlanError):
                apply_patch(base, {'schema_version': '1.0', 'kind': 'patch', 'answer': 'x', 'ops': ops})


class MagicPenPresentationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.service = MagicPenService(self.root)
        self.addCleanup(self.service.close)
        self.doc = self.service.acquire(Image.new('RGB', (200, 100), 'white'), {'id': 'test', 'x': 0, 'y': 0})
        self.replies = []

        class Adapter:
            config = {'allow_paid': False, 'providers': [{'name': 'fixture', 'model': 'visual-model', 'protocol': 'anthropic', 'enabled': True,
                      'free_confirmed': True, 'capabilities': ['vision']}]}
            calls = []
            def route(inner, request):
                inner.calls.append(request)
                return {'ok': True, 'message': {'content': self.replies.pop(0)},
                        'route': {'provider_name': 'fixture', 'model': request['model']}}
            def cancel(inner, request_id): return True
        self.adapter = self.service.adapter = Adapter()
        self.service.save({'id': self.doc['id'], 'expected_revision': 1,
                           'selection': {'shape': 'rect', 'bounds': [5, 5, 60, 60]}, 'strokes': []})

    def ask(self, **kw):
        q = self.service.start({'id': self.doc['id'], 'revision': 2, 'question': '¿Qué aparece?', 'provider': 'fixture',
                                'model': 'visual-model', 'selection_mode': 'manual', 'request_id': uuid.uuid4().hex, **kw})
        end = time.monotonic() + 3
        while q['state'] == 'running' and time.monotonic() < end:
            time.sleep(.01)
            q = self.service.query({'id': q['source_id'], 'query_id': q['id']})
        return q

    def test_presentation_is_validated_persisted_and_patched_without_regeneration(self):
        self.replies.append(json.dumps(plan()))
        first = self.ask(format='presentation')
        self.assertEqual(first['state'], 'completed')
        self.assertEqual(first['presentation']['steps'][0]['title'], 'Función')
        system = self.adapter.calls[0]['messages'][0]['content']
        self.assertIn('"kind":"presentation"', system)
        self.assertEqual(self.adapter.calls[0]['generation']['max_tokens'], 2048)
        self.replies.append(json.dumps({'schema_version': '1.0', 'kind': 'patch', 'answer': 'Detallo el paso 2.',
                                        'ops': [{'op': 'step.update', 'step_id': 's2', 'title': 'Aproximación'}]}))
        second = self.ask(format='presentation', base_query_id=first['id'], question='¿Por qué el paso 2?')
        self.assertEqual(second['state'], 'completed', second.get('error'))
        self.assertEqual(second['answer'], 'Detallo el paso 2.')
        self.assertEqual([s['title'] for s in second['presentation']['steps']], ['Función', 'Aproximación'])
        self.assertIn('"kind":"patch"', self.adapter.calls[1]['messages'][0]['content'])
        self.assertIn('Presentación actual', self.adapter.calls[1]['messages'][1]['content'][0]['text'])
        reopened = MagicPenService(self.root, self.adapter)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.query({'id': self.doc['id'], 'query_id': second['id']})['presentation'], second['presentation'])

    def test_auto_effort_uses_supported_levels_for_new_scene_and_followup(self):
        self.adapter.config['providers'][0]['model'] = 'claude-opus-4-6'
        self.replies.append(json.dumps(plan()))
        first = self.ask(format='presentation', model='claude-opus-4-6')
        self.assertEqual(first['state'], 'completed', first.get('error'))
        self.assertEqual(self.adapter.calls[-1]['generation']['effort'], 'medium')
        self.replies.append(json.dumps({'schema_version': '1.0', 'kind': 'patch', 'answer': 'Lo explico con más detalle.', 'ops': []}))
        second = self.ask(format='presentation', model='claude-opus-4-6', base_query_id=first['id'], question='¿Puedes explicar en detalle por qué ocurre?')
        self.assertEqual(second['state'], 'completed', second.get('error'))
        self.assertEqual(self.adapter.calls[-1]['generation']['effort'], 'high')
        self.assertEqual(MagicPenService._effective_effort({'effort': 'auto', 'base_query_id': first['id'], 'question': '¿Qué pieza es?'},
                                                           {'efforts': ['medium', 'high']}), None)
        self.assertEqual(MagicPenService._effective_effort({'effort': 'auto', 'base_query_id': first['id'], 'question': 'Cambia el color de la pieza.'},
                                                           {'efforts': ['low', 'medium', 'high']}), 'low')

    def test_invalid_model_output_fails_closed_and_text_mode_is_unchanged(self):
        self.replies.append('<script>alert(1)</script>')
        failed = self.ask(format='presentation')
        self.assertEqual(failed['state'], 'failed')
        self.assertNotIn('presentation', failed)
        self.assertIn('presentación válida', failed['error'])
        self.replies.append('Resumen: texto normal.')
        text = self.ask()
        self.assertEqual((text['state'], text['response']), ('completed', 'Resumen: texto normal.'))
        self.assertNotIn('format', text)
        self.assertNotIn('kind', self.adapter.calls[1]['messages'][0]['content'])

    def test_patch_requires_existing_presentation_on_current_revision(self):
        self.replies.append('Resumen: texto.')
        text = self.ask()
        for kw in ({'base_query_id': text['id'], 'format': 'presentation'}, {'base_query_id': uuid.uuid4().hex, 'format': 'presentation'}):
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, 'STALE_PRESENTATION'):
                self.ask(**kw)
        for kw in ({'base_query_id': text['id']}, {'format': 'html'}, {'format': 'presentation', 'base_query_id': '../x'}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.ask(**kw)
        self.assertEqual(len(self.adapter.calls), 1, 'Rejected requests never reach the model')

    def test_scene_png_export_is_verified_exclusive_and_bounded(self):
        import base64, hashlib, io
        def data_url(image, fmt='PNG'):
            buf = io.BytesIO(); image.save(buf, format=fmt)
            return f'data:image/{fmt.lower()};base64,' + base64.b64encode(buf.getvalue()).decode()
        out = self.root / 'exports'
        body = {'id': self.doc['id'], 'revision': 2, 'kind': 'scene', 'directory': str(out), 'name': 'leccion-escena',
                'image': data_url(Image.new('RGBA', (64, 40), (20, 120, 200, 255)))}
        receipt = self.service.export(body)
        self.assertTrue(receipt['verified'])
        self.assertEqual(receipt['sha256'], hashlib.sha256((out / 'leccion-escena.png').read_bytes()).hexdigest())
        with Image.open(out / 'leccion-escena.png') as saved:
            self.assertEqual(saved.size, (64, 40))
        with self.assertRaises(FileExistsError):
            self.service.export(body)
        for name, image in {'jpeg': data_url(Image.new('RGB', (8, 8)), 'JPEG'), 'not base64': 'data:image/png;base64,@@@',
                            'too large': data_url(Image.new('L', (4097, 2))), 'over body limit': 'data:image/png;base64,' + 'A' * 2_000_000,
                            'missing': None}.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, 'PNG'):
                self.service.export({**body, 'name': 'otra', 'image': image})
        self.assertFalse((out / 'otra.png').exists())


if __name__ == '__main__':
    unittest.main()
