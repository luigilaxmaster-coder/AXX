"""Local plan checks (warnings only) and the deterministic diagram layout."""
import copy
import unittest

from backend.presentation_plan import check_plan, diagram_overlaps, layout_diagram, validate_plan
from backend.tests.test_presentation_plan import plan


def obj(ident, label, x, y=0, z=0, shape='box', size=(1, 1, 1), **extra):
    return {'id': ident, 'label': label, 'shape': shape, 'size': list(size), 'position': [x, y, z], 'color': '#aabbcc', **extra}


def scene(*objects, s1=None):
    p = plan(scene={'fidelity': 'conceptual', 'objects': list(objects)})
    if s1:
        p['steps'][0]['body'] = s1
    return validate_plan(p)


def diagram(n, edges=None, bounds=lambda i: [.1, .1, .3, .2]):
    nodes = [{'id': f'd{i}', 'label': f'Etapa {i} del flujo', 'step_id': 's1' if i % 2 else 's2', 'bounds': bounds(i)} for i in range(1, n + 1)]
    edges = edges if edges is not None else [{'from': f'd{i}', 'to': f'd{i+1}', 'label': 'sigue'} for i in range(1, n)]
    p = plan(); p['diagram'] = {'nodes': nodes, 'edges': edges}
    return p


class DiagramLayoutTests(unittest.TestCase):
    def assertClean(self, nodes):
        self.assertFalse(diagram_overlaps(nodes), 'nodes must not overlap')
        for node in nodes:
            x, y, w, h = node['bounds']
            self.assertTrue(w >= .03 and h >= .03 and x >= 0 and y >= 0 and x + w <= 1.0001 and y + h <= 1.0001, node)

    def test_overlapping_model_bounds_are_replaced_by_a_flow_without_overlaps(self):
        original = diagram(6); before = copy.deepcopy(original)
        nodes = validate_plan(original)['diagram']['nodes']
        self.assertEqual(original, before)
        self.assertClean(nodes)
        self.assertEqual([(n['id'], n['label'], n['step_id']) for n in nodes], [(n['id'], n['label'], n['step_id']) for n in before['diagram']['nodes']])
        self.assertEqual(nodes, validate_plan(copy.deepcopy(original))['diagram']['nodes'])  # deterministic
        xs = [n['bounds'][0] for n in nodes[:4]]
        self.assertEqual(xs, sorted(xs))  # the flow reads left to right

    def test_a_diagram_that_already_fits_is_left_exactly_as_the_model_drew_it(self):
        spaced = diagram(3, bounds=lambda i: [.05 + (i - 1) * .3, .1, .25, .2])
        self.assertEqual(validate_plan(spaced)['diagram']['nodes'][1]['bounds'], [.35, .1, .25, .2])

    def test_cycles_branches_and_sixteen_nodes_stay_inside_the_canvas(self):
        cyclic = diagram(4, edges=[{'from': 'd1', 'to': 'd2', 'label': 'a'}, {'from': 'd2', 'to': 'd3', 'label': 'b'}, {'from': 'd3', 'to': 'd1', 'label': 'c'}, {'from': 'd1', 'to': 'd4', 'label': 'd'}])
        self.assertClean(validate_plan(cyclic)['diagram']['nodes'])
        self.assertClean(validate_plan(diagram(16))['diagram']['nodes'])
        self.assertClean(validate_plan(diagram(8, edges=[]))['diagram']['nodes'])

    def test_node_links_to_scene_pieces_are_kept_and_validated(self):
        p = plan(scene={'fidelity': 'conceptual', 'objects': [obj('o1', 'Eje', 0)]})
        p['diagram'] = {'nodes': [{'id': 'd1', 'label': 'Eje', 'step_id': 's1', 'bounds': [.1, .1, .3, .2], 'object_id': 'o1'},
                                  {'id': 'd2', 'label': 'Fin', 'step_id': 's2', 'bounds': [.6, .6, .3, .2]}], 'edges': [{'from': 'd1', 'to': 'd2', 'label': 'x'}]}
        self.assertEqual(validate_plan(p)['diagram']['nodes'][0]['object_id'], 'o1')
        p['diagram']['nodes'][0]['object_id'] = 'o9'
        with self.assertRaises(Exception): validate_plan(p)


class OverlayPruningTests(unittest.TestCase):
    def overlay(self, ident, kind, start, end, step='s1'):
        return {'id': ident, 'kind': kind, 'step_id': step, 'start': start, 'end': end, 'text': f'nota {ident}', 'photo': False}

    def test_invalid_annotations_are_dropped_and_reported_while_good_ones_and_the_plan_survive(self):
        from backend.presentation_plan import prune_invalid_overlays
        p = plan(); p['overlays'] = [self.overlay('a1', 'label', [.1, .8], [.1, .8]), self.overlay('a2', 'box', [.2, .2], [.6, .5]),
                                      self.overlay('a3', 'arrow', [.1, .1], [.1, .1]), self.overlay('a4', 'box', [.1, .1], [.4, .4], step='s9')]
        before = copy.deepcopy(p)
        pruned, notes = prune_invalid_overlays(p)
        self.assertEqual(p, before)  # the input is never mutated
        self.assertEqual([o['id'] for o in pruned['overlays']], ['a2'])
        self.assertEqual(len(notes), 3)
        self.assertTrue(all(n.startswith('Se descartó una anotación') for n in notes))
        self.assertEqual(validate_plan(pruned)['overlays'][0]['id'], 'a2')
        only_bad = plan(); only_bad['overlays'] = [self.overlay('a1', 'label', [.5, .5], [.5, .5])]
        pruned, notes = prune_invalid_overlays(only_bad)
        self.assertNotIn('overlays', pruned)
        validate_plan(pruned)
        clean = plan(); clean['overlays'] = [self.overlay('a1', 'box', [.1, .1], [.4, .4])]
        self.assertEqual(prune_invalid_overlays(clean), (clean, []))


class PlanCheckTests(unittest.TestCase):
    def test_repeated_part_counts_are_compared_with_step_one(self):
        wrong = scene(obj('o1', 'Tornillo A', 0), obj('o2', 'Tornillo B', 1), s1='Se ven cuatro tornillos sujetando la tapa.')
        self.assertTrue(any('4' in w and 'tornillos' in w and '2 pieza' in w for w in check_plan(wrong)))
        right = scene(*[obj(f'o{i}', f'Tornillo {i}', i - 1) for i in range(1, 5)], s1='Se ven cuatro tornillos sujetando la tapa.')
        self.assertEqual(check_plan(right), [])

    def test_a_multi_piece_component_is_not_reported_and_pieces_said_to_be_apart_are_not_floating(self):
        many = scene(obj('o1', 'Escuadra base', 0), obj('o2', 'Escuadra pared', 1), obj('o3', 'Escuadra agujero', 2), s1='Se ve una escuadra negra.')
        self.assertEqual(check_plan(many), [])
        apart = scene(obj('o1', 'Base', 0), obj('o2', 'Pared', 1), obj('o3', 'Soporte negro', 8, 8, 8), s1='Hay una base y, aparte, el soporte negro separado del cuerpo.')
        self.assertEqual(check_plan(apart), [])
        silent = scene(obj('o1', 'Base', 0), obj('o2', 'Pared', 1), obj('o3', 'Soporte negro', 8, 8, 8))
        self.assertTrue(any('Soporte negro' in w for w in check_plan(silent)))

    def test_floating_pieces_leaving_the_volume_and_upside_down_roofs_are_reported(self):
        floating = scene(obj('o1', 'Base', 0), obj('o2', 'Pared', 1), obj('o3', 'Antena', 8, 8, 8))
        self.assertTrue(any('Antena' in w and 'flota' in w for w in check_plan(floating)))
        outside = scene(obj('o1', 'Barra larga', 9.8, size=(2, 1, 1)))
        self.assertTrue(any('sobresale' in w for w in check_plan(outside)))
        upside = scene(obj('o1', 'Muro', 0, size=(4, 2, 3)), obj('o2', 'Tejado', 0, 1.8, shape='gable', size=(4, 1.5, 3), rotation=[180, 0, 0]))
        self.assertTrue(any('Tejado' in w and 'boca abajo' in w for w in check_plan(upside)))
        upright = scene(obj('o1', 'Muro', 0, size=(4, 2, 3)), obj('o2', 'Tejado', 0, 1.8, shape='gable', size=(4, 1.5, 3), rotation=[0, 90, 0]))
        self.assertEqual(check_plan(upright), [])

    def test_touching_parts_and_plans_without_scene_produce_no_warnings(self):
        self.assertEqual(check_plan(scene(obj('o1', 'A', 0), obj('o2', 'B', 1), obj('o3', 'C', 2))), [])
        self.assertEqual(check_plan(validate_plan(plan())), [])


if __name__ == '__main__':
    unittest.main()
