import copy
import unittest
from backend.presentation_plan import PlanError, apply_patch, parse_json, validate_plan


def example():
    return {'schema_version': '1.0', 'kind': 'presentation', 'title': 'Motor', 'summary': 'Transforma movimiento.',
        'fidelity': 'conceptual', 'steps': [{'id': 's1', 'title': 'Pistón', 'body': 'Se desplaza.', 'narration': 'Observa el pistón.', 'basis': 'assumed', 'focus': ['o2']},
        {'id': 's2', 'title': 'Eje', 'body': 'Gira.', 'narration': 'Observa el eje.', 'basis': 'assumed', 'focus': ['o4']}],
        'asset': {'kind': 'single_cylinder_engine', 'scale': 1},
        'diagram': {'nodes': [{'id': 'd1', 'label': 'Pistón', 'step_id': 's1', 'bounds': [.1, .1, .3, .2]},
                              {'id': 'd2', 'label': 'Cigüeñal', 'step_id': 's2', 'bounds': [.6, .6, .3, .2]}],
                    'edges': [{'from': 'd1', 'to': 'd2', 'label': 'Transmite movimiento'}]},
        'overlays': [{'id': 'a1', 'kind': 'arrow', 'step_id': 's1', 'start': [.1, .1], 'end': [.5, .5], 'text': 'Pistón', 'photo': False}]}


class VisualCompilerTests(unittest.TestCase):
    def test_asset_materializes_semantic_parts_and_patch_preserves_assembly(self):
        plan = validate_plan(example())
        self.assertEqual([o['shape'] for o in plan['scene']['objects']], ['engine_cylinder', 'piston', 'connecting_rod', 'crankshaft'])
        changed, _ = apply_patch(plan, {'schema_version': '1.0', 'kind': 'patch', 'answer': 'Pistón marcado.',
            'ops': [{'op': 'object.update', 'object_id': 'o2', 'color': '#ff8800'}]})
        self.assertEqual(changed['scene']['objects'][1]['color'], '#ff8800')
        self.assertEqual(changed['asset'], plan['asset'])
        self.assertEqual(validate_plan(changed), changed)

    def test_every_registered_generator_validates_at_scale_limits_and_keeps_focus(self):
        from backend.presentation_plan import normalize_model_focus, output_schema
        from backend.spatial_assets import KINDS
        self.assertGreaterEqual(len(KINDS), 5)
        self.assertNotIn('asset', output_schema()['properties'])  # presets are not offered to the model (and the grammar would be too large)
        for kind in KINDS:
            for scale in (.2, 1, 2):
                value = example(); value['asset'] = {'kind': kind, 'scale': scale}
                value['steps'][0]['focus'] = ['o1']; value['steps'][1]['focus'] = ['o2']
                with self.subTest(kind=kind, scale=scale):
                    plan = validate_plan(normalize_model_focus(value))
                    self.assertEqual(plan['steps'][1]['focus'], ['o2'])  # focus survives for non-engine assets
                    self.assertEqual(len({o['id'] for o in plan['scene']['objects']}), len(plan['scene']['objects']))
        value = example(); value['asset'] = {'kind': 'gothic_church', 'scale': 1}
        self.assertEqual(len(validate_plan(value)['scene']['objects']), 11)

    def test_contract_analyzes_first_measures_proportions_and_never_advertises_presets(self):
        from backend.presentation_plan import PLAN_CONTRACT, SHAPES, MATERIALS
        for rule in ('PROCESO OBLIGATORIO', 'Qué se observa', 'un motor eléctrico no es un motor de combustión', 'PROPORCIONES',
                     'dimensión mayor del objeto en 8 unidades', 'conteo exacto de piezas repetidas', 'Proporciones y límites',
                     'no uses el campo asset ni ensamblajes predefinidos', 'object_id', 'COMPONENTES DEL CATÁLOGO', 'DEBES referirla'):
            self.assertIn(rule, PLAN_CONTRACT)
        for name in SHAPES[10:] + MATERIALS:  # the new vocabulary is taught to the model
            self.assertIn(name, PLAN_CONTRACT)
        self.assertNotIn('gothic_church', PLAN_CONTRACT)  # presets are not offered, so they cannot bias the answer

    def test_corrections_can_use_the_catalog_and_gpt_plans_get_a_longer_deadline(self):
        from backend.presentation_plan import patch_contract
        text = patch_contract()
        for needle in ('object.add', 'component', 'DEBES usar el catálogo', 'ball_bearing', 'hex_nut'):
            self.assertIn(needle, text)
        from backend.connect.provider import SPATIAL_TIMEOUT, TURN_TIMEOUT
        self.assertGreater(SPATIAL_TIMEOUT, TURN_TIMEOUT)

    def test_new_shapes_materials_and_param_validate_and_reject_bad_values(self):
        value = example(); value.pop('asset'); value.pop('diagram'); value.pop('overlays')
        from backend.presentation_plan import SHAPES, MATERIALS
        value['scene'] = {'fidelity': 'conceptual', 'objects': [{'id': f'o{i}', 'label': shape, 'shape': shape, 'size': [1, 2, 1],
            'position': [0, 0, 0], 'color': '#aabbcc', 'material': MATERIALS[i % len(MATERIALS)], 'param': .3} for i, shape in enumerate(SHAPES[10:] + ('box',), 1)]}
        value['steps'][0]['focus'] = ['o1']; value['steps'][1]['focus'] = ['o2']
        self.assertEqual(len(validate_plan(value)['scene']['objects']), len(SHAPES[10:]) + 1)
        for field, bad in (('material', 'unobtainium'), ('param', 1.5), ('param', float('nan')), ('param', 'x')):
            broken = copy.deepcopy(value); broken['scene']['objects'][0][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(PlanError): validate_plan(broken)
        value['scene']['objects'][0]['shape'] = 'hemisphere'  # a synonym is normalized to a real shape before validation
        from backend.presentation_plan import normalize_model_object_ids
        self.assertEqual(normalize_model_object_ids(value)['scene']['objects'][0]['shape'], 'dome')

    def test_specific_models_accept_32_parts_and_700_character_explanations(self):
        value = example(); value.pop('asset'); value.pop('diagram'); value.pop('overlays')
        value['scene'] = {'fidelity': 'conceptual', 'objects': [{'id': f'o{i}', 'label': f'Pieza {i}', 'shape': 'cylinder',
            'size': [1, 1, 1], 'position': [(i - 16) / 4, 0, 0], 'color': '#aabbcc'} for i in range(1, 33)]}
        value['steps'][0].update(body='x' * 700, focus=['o1']); value['steps'][1].update(focus=['o32'])
        self.assertEqual(len(validate_plan(value)['scene']['objects']), 32)
        value['steps'][0]['body'] = 'x' * 701
        with self.assertRaises(PlanError): validate_plan(value)

    def test_patch_adds_and_removes_parts_without_losing_the_rest_of_the_model(self):
        plan = validate_plan(example())
        part = {'id': 'o5', 'label': 'Tornillo', 'shape': 'hexprism', 'size': [.2, .1, .2], 'position': [1, 1, 1], 'color': '#c0c4c8', 'material': 'metal_polished'}
        patch = lambda *ops: {'schema_version': '1.0', 'kind': 'patch', 'answer': 'Corregido.', 'ops': list(ops)}
        changed, _ = apply_patch(plan, patch({'op': 'object.add', 'object': part}, {'op': 'object.remove', 'object_id': 'o4'}))
        ids = [o['id'] for o in changed['scene']['objects']]
        self.assertEqual(ids, ['o1', 'o2', 'o3', 'o5'])
        self.assertNotIn('focus', changed['steps'][1])  # the removed part leaves no dangling focus
        self.assertEqual(changed['steps'][0]['focus'], ['o2'])
        self.assertEqual(plan['scene']['objects'][3]['id'], 'o4')  # the original plan is never mutated
        for bad in (patch({'op': 'object.add', 'object': dict(part, id='o1')}), patch({'op': 'object.add', 'object': dict(part, size=[0, 0, 0], material='unobtainium')}),
                    patch({'op': 'object.remove', 'object_id': 'o99'}),
                    patch(*[{'op': 'object.remove', 'object_id': f'o{i}'} for i in range(1, 5)])):
            with self.subTest(bad=bad['ops'][0]), self.assertRaises(PlanError): apply_patch(plan, bad)
        from backend.presentation_plan import normalize_model_object_ids
        messy = normalize_model_object_ids(patch({'op': 'object.add', 'object': dict(part, shape='hexagon', color='#fff', rotation=None, param=None)}))
        applied, _ = apply_patch(plan, messy)  # synonyms, short colors and nulls are cleaned for added parts too
        self.assertEqual(applied['scene']['objects'][-1]['shape'], 'hexprism')
        tolerant, _ = apply_patch(plan, patch({'op': 'object.add', 'object': dict(part, shape='teapot', color='red')}))  # existing tolerant mapping
        self.assertEqual((tolerant['scene']['objects'][-1]['shape'], tolerant['scene']['objects'][-1]['color']), ('box', '#888888'))

    def test_compiler_rejects_invalid_geometry_code_references_and_budgets(self):
        edits = [lambda p: p['asset'].update(scale=float('nan')), lambda p: p['asset'].update(kind='download_mesh'),
            lambda p: p['diagram']['nodes'][0].update(bounds=[.9, .1, .4, .3]),
            lambda p: p['diagram']['nodes'][1].update(id='d1'), lambda p: p['diagram']['edges'][0].update(to='d99'),
            lambda p: p['overlays'][0].update(step_id='s9'), lambda p: p['overlays'][0].update(start=[float('inf'), 0]),
            lambda p: p['overlays'][0].update(script='alert(1)'), lambda p: p['overlays'][0].update(photo=True),
            lambda p: p.update(overlays=p['overlays'] * 17)]
        for edit in edits:
            value = copy.deepcopy(example()); edit(value)
            with self.subTest(edit=edit), self.assertRaises(PlanError): validate_plan(value)
        for value in ['{"kind":"presentation","kind":"patch"}', '{"value":NaN}']:
            with self.subTest(value=value), self.assertRaises(PlanError): parse_json(value)


if __name__ == '__main__': unittest.main()
