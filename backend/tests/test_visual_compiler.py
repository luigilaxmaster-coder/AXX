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
