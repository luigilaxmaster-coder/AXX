"""Catalog components inside presentation plans: expansion, references, learning and token savings."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from backend.presentation_plan import (MAX_OBJECTS, PlanError, apply_patch, expand_components, learn_groups, normalize_model_object_ids,
                                       plan_contract, validate_plan)
from backend.shape_registry import ShapeRegistry
from backend.tests.test_presentation_plan import MagicPenPresentationTests, plan


def reference(ident, component, **extra):
    return {'id': ident, 'label': extra.pop('label', component), 'component': component, 'scale': 1, 'position': [0, 0, 0], 'color': '#b0b4b8', **extra}


def with_refs():
    p = plan(scene={'fidelity': 'conceptual', 'objects': [
        {'id': 'o1', 'label': 'Carcasa', 'shape': 'cylinder', 'size': [3, 5, 3], 'position': [0, 0, 0], 'color': '#c0c4c8'},
        reference('o2', 'ball_bearing', position=[0, 3, 0], label='Rodamiento frontal'),
        reference('o3', 'hex_nut', position=[0, -3, 0], label='Tuerca')],
        'arrows': [{'from': 'o2', 'to': 'o1', 'label': 'apoya'}, {'from': 'o3', 'to': 'o3', 'label': 'x'}]})
    p['steps'][0]['focus'] = ['o2', 'o3']
    p['steps'][1]['focus'] = ['o1']
    return p


class ComponentExpansionTests(unittest.TestCase):
    def setUp(self):
        self.registry = ShapeRegistry()

    def test_references_expand_to_valid_real_parts_and_never_mutate_the_input(self):
        original = with_refs(); before = copy.deepcopy(original)
        expanded = expand_components(normalize_model_object_ids(original), self.registry)
        self.assertEqual(original, before)
        validated = validate_plan(expanded)
        objects = validated['scene']['objects']
        ids = [o['id'] for o in objects]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreater(len(objects), 3)  # bearing and nut are several parts each
        self.assertTrue(all('component' not in o and 'axx_component' not in o for o in objects))
        self.assertTrue(all(o['shape'] and o['size'] for o in objects))

    def test_focus_arrows_and_diagram_links_follow_the_expanded_parts(self):
        p = with_refs(); p['diagram'] = {'nodes': [{'id': 'd1', 'label': 'Rodamiento', 'step_id': 's1', 'bounds': [.1, .1, .3, .2], 'object_id': 'o2'},
                                                   {'id': 'd2', 'label': 'Carcasa', 'step_id': 's2', 'bounds': [.6, .1, .3, .2]}], 'edges': [{'from': 'd1', 'to': 'd2', 'label': 'apoya'}]}
        expanded = expand_components(normalize_model_object_ids(p), self.registry)
        ids = {o['id'] for o in expanded['scene']['objects']}
        focus = expanded['steps'][0]['focus']
        self.assertTrue(focus and set(focus) <= ids and 'o2' not in focus or 'o2' in ids)  # every focus id exists
        self.assertTrue(set(focus) <= ids)
        arrow = expanded['scene']['arrows']
        self.assertEqual(len(arrow), 1)  # the self-arrow collapsed and was dropped
        self.assertTrue({arrow[0]['from'], arrow[0]['to']} <= ids)
        self.assertIn(expanded['diagram']['nodes'][0]['object_id'], ids)
        validate_plan(expanded)

    def test_unknown_component_and_budget_overflow_are_plan_errors(self):
        unknown = with_refs(); unknown['scene']['objects'][1]['component'] = 'warp_drive'
        with self.assertRaises(PlanError): expand_components(unknown, self.registry)
        many = with_refs(); many['scene']['objects'] = [reference(f'o{i}', 'ball_bearing') for i in range(1, 25)]
        with self.assertRaises(PlanError): expand_components(many, self.registry)

    def test_plain_scenes_pass_through_and_the_contract_lists_the_catalog(self):
        plain = plan(scene={'fidelity': 'conceptual', 'objects': [{'id': 'o1', 'label': 'A', 'shape': 'box', 'size': [1, 1, 1], 'position': [0, 0, 0], 'color': '#aabbcc'}]})
        self.assertIs(expand_components(plain, self.registry), plain)
        text = plan_contract(self.registry)
        for needle in ('COMPONENTES DEL CATÁLOGO', 'ball_bearing', 'hex_nut', 'group'):
            self.assertIn(needle, text)

    def test_object_add_accepts_a_component_and_later_focus_follows_it(self):
        base = validate_plan(plan(scene={'fidelity': 'conceptual', 'objects': [
            {'id': 'o1', 'label': 'Eje', 'shape': 'cylinder', 'size': [1, 4, 1], 'position': [0, 0, 0], 'color': '#c0c4c8'}]}))
        patch = {'schema_version': '1.0', 'kind': 'patch', 'answer': 'Añado un rodamiento.', 'ops': [
            {'op': 'object.add', 'object': reference('o9', 'ball_bearing', position=[0, 1, 0])},
            {'op': 'step.update', 'step_id': 's1', 'focus': ['o9']}]}
        patched, _ = apply_patch(base, patch, registry=self.registry)
        ids = [o['id'] for o in patched['scene']['objects']]
        self.assertGreater(len(ids), 2)
        self.assertTrue(set(patched['steps'][0]['focus']) <= set(ids) and 'o9' not in patched['steps'][0]['focus'])
        with self.assertRaises(PlanError):
            apply_patch(base, {**patch, 'ops': [{'op': 'object.add', 'object': reference('o9', 'warp_drive')}]}, registry=self.registry)

    def test_a_catalog_reference_costs_far_fewer_characters_than_the_same_scene_by_hand(self):
        refs = [{k: v for k, v in o.items()} for o in with_refs()['scene']['objects'][1:]]
        by_hand = [part for o in refs for part in self.registry.instantiate(o['component'], scale=1, position=o['position'], color=o['color'])]
        compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        self.assertLess(len(compact(refs)), len(compact(by_hand)) * .5)


class LearnedComponentTests(unittest.TestCase):
    def piece(self, ident, x, group='Soporte articulado', **extra):
        return {'id': ident, 'label': f'Parte {ident}', 'shape': 'cylinder', 'size': [.4, 1, .4], 'position': [x, 0, 0], 'color': '#aabbcc', 'group': group, **extra}

    def scene(self, *objects):
        return validate_plan(plan(scene={'fidelity': 'conceptual', 'objects': list(objects)}))

    def test_a_recognizable_group_is_stored_in_the_user_directory_and_reused(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'shape-registry.json'
            registry = ShapeRegistry(path)
            stored = learn_groups(self.scene(self.piece('o1', 0), self.piece('o2', 1)), registry)
            self.assertEqual(stored, ['soporte_articulado'])
            self.assertTrue(path.is_file())
            reopened = ShapeRegistry(path)  # survives a restart
            self.assertTrue(reopened.has_shape('soporte_articulado'))
            parts = reopened.instantiate('soporte_articulado', scale=2, position=[1, 1, 1])
            validate_plan(plan(scene={'fidelity': 'conceptual', 'objects': [dict(p, id=f'o{i}') for i, p in enumerate(parts, 1)]}))
            self.assertEqual(learn_groups(self.scene(self.piece('o1', 0), self.piece('o2', 1)), reopened), [])  # not stored twice

    def test_generic_single_piece_known_and_invalid_groups_are_not_stored(self):
        registry = ShapeRegistry()
        self.assertEqual(learn_groups(self.scene(self.piece('o1', 0, 'Pieza'), self.piece('o2', 1, 'Pieza')), registry), [])
        self.assertEqual(learn_groups(self.scene(self.piece('o1', 0)), registry), [])
        for bare in ('Motor', 'Soporte', 'Terminal'):  # one generic word is not a reusable component
            self.assertEqual(learn_groups(self.scene(self.piece('o1', 0, bare), self.piece('o2', 1, bare)), registry), [], bare)
        self.assertEqual(learn_groups(self.scene(self.piece('o1', 0, 'Tuerca'), self.piece('o2', 1, 'Tuerca')), registry), [])  # already in the catalog
        self.assertEqual(learn_groups(self.scene(self.piece('o1', 0, 'Tornillo M4'), self.piece('o2', 1, 'Tornillo M4')), registry), [])  # matches the bolt
        broken = self.scene(self.piece('o1', 0), self.piece('o2', 1))
        broken['scene']['objects'][1]['shape'] = 'teapot'  # bypasses validation on purpose: learning must re-validate
        self.assertEqual(learn_groups(broken, registry), [])
        self.assertFalse(registry.has_shape('soporte_articulado'))


class MagicPenComponentFlowTests(MagicPenPresentationTests):
    def test_a_model_answer_with_references_is_expanded_learned_and_persisted_outside_the_repo(self):
        answer = with_refs()
        answer['scene']['objects'][0].update(group='Carcasa de motor')
        answer['scene']['objects'].append(dict(answer['scene']['objects'][0], id='o4', group='Carcasa de motor', position=[0, 0, 2]))
        self.replies.append(json.dumps(answer))
        self.adapter.config['providers'][0]['model'] = 'claude-sonnet-5-5'
        result = self.ask(format='presentation', model='claude-sonnet-5-5')
        self.assertEqual(result['state'], 'completed', result.get('error'))
        objects = result['presentation']['scene']['objects']
        self.assertGreater(len(objects), 4)
        self.assertTrue(all('component' not in o and 'axx_component' not in o for o in objects))
        self.assertLessEqual(len(objects), MAX_OBJECTS)
        self.assertIn('COMPONENTES DEL CATÁLOGO', self.adapter.calls[-1]['messages'][0]['content'])
        stored = Path(self.service.root) / 'shape-registry.json'
        self.assertTrue(stored.is_file())
        self.assertTrue(self.service.shapes.has_shape('carcasa_de_motor'))


    def test_degenerate_point_labels_do_not_reject_the_answer_and_the_drop_is_reported(self):
        answer = plan()
        answer['overlays'] = [{'id': f'a{i}', 'kind': 'label', 'step_id': 's1', 'start': [.1 * i, .5], 'end': [.1 * i, .5], 'text': f'etiqueta {i}', 'photo': False} for i in (1, 2, 3)]
        answer['overlays'].append({'id': 'a4', 'kind': 'box', 'step_id': 's1', 'start': [.2, .2], 'end': [.5, .5], 'text': 'motor', 'photo': False})
        self.replies.append(json.dumps(answer))
        self.adapter.config['providers'][0]['model'] = 'claude-sonnet-5-5'
        result = self.ask(format='presentation', model='claude-sonnet-5-5')
        self.assertEqual(result['state'], 'completed', result.get('error'))
        self.assertEqual([o['id'] for o in result['presentation']['overlays']], ['a4'])
        self.assertEqual(len([w for w in result['warnings'] if w.startswith('Se descartó una anotación')]), 3)


if __name__ == '__main__':
    unittest.main()
