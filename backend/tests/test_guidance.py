"""Visual Guidance Engine contracts (GuideSession v1) and the drawing tutor's own geometry."""
import unittest

from PIL import Image, ImageDraw

from backend import drawing_guide
from backend.guidance import GuideError, advance, from_guide_plan, from_presentation, validate_session

PLAN = {'schema_version': '1.0', 'kind': 'presentation', 'title': 'Motor', 'summary': 'x', 'fidelity': 'conceptual', 'steps': [
    {'id': 's1', 'title': 'Qué se observa', 'body': 'Un motor con pistón y cigüeñal', 'narration': 'n1', 'basis': 'observed', 'focus': ['o1', 'o2']},
    {'id': 's2', 'title': 'El pistón', 'body': 'El pistón se desplaza y empuja la biela', 'narration': 'n2', 'basis': 'inferred', 'focus': ['o1']},
    {'id': 's3', 'title': 'El cigüeñal', 'body': 'El cigüeñal gira y transmite el movimiento', 'narration': 'n3', 'basis': 'inferred', 'focus': ['o2']},
    {'id': 's4', 'title': 'Despiece', 'body': 'Vista explotada de las piezas', 'narration': 'n4', 'basis': 'inferred', 'focus': []},
    {'id': 's5', 'title': 'Reensamblado', 'body': 'Reensambla el conjunto', 'narration': 'n5', 'basis': 'inferred'}],
    'scene': {'fidelity': 'conceptual', 'objects': [
        {'id': 'o1', 'label': 'Pistón', 'shape': 'piston', 'size': [1, 1, 1], 'position': [0, 1, 0]},
        {'id': 'o2', 'label': 'Cigüeñal', 'shape': 'crankshaft', 'size': [2, 1, 1], 'position': [0, -1, 0]},
        {'id': 'o3', 'label': 'Bloque', 'shape': 'box', 'size': [3, 3, 3], 'position': [0, 0, 0]}]},
    'diagram': {'nodes': [{'id': 'd1', 'label': 'Combustión', 'step_id': 's2', 'bounds': [.1, .1, .2, .2]},
                          {'id': 'd2', 'label': 'Giro', 'step_id': 's3', 'bounds': [.6, .1, .2, .2]}],
                'edges': [{'from': 'd1', 'to': 'd2', 'label': 'empuja'}]}}
GUIDE = {'schema_version': '1.0', 'kind': 'guide', 'goal': 'Iniciar sesión', 'steps': [
    {'id': 'g1', 'instruction': 'Escribe tu usuario', 'target': {'name': 'Usuario', 'control_type': 'Edit'},
     'postcondition': {'kind': 'value_changed'}},
    {'id': 'g2', 'instruction': 'Pulsa Iniciar sesión', 'target': {'name': 'Iniciar sesión', 'control_type': 'Button'},
     'postcondition': {'kind': 'window_title_contains', 'value': 'Bienvenido'}}]}


class GuideSessionTests(unittest.TestCase):
    def test_system_chooses_camera_motion_and_explode_from_the_plan(self):
        g = from_presentation(PLAN, source_ref='q1', user_goal='Explícame este motor')
        steps = {s['step_id']: s for s in g['steps']}
        self.assertEqual(g['guide_mode'], 'mixed')
        self.assertEqual(steps['s1']['camera_action'], 'frame_targets')
        self.assertEqual((steps['s2']['scene_action'], steps['s2']['motion']['kind']), ('animate', 'translate'))  # piston strokes
        self.assertEqual(steps['s3']['motion']['kind'], 'rotate')                                                  # crankshaft turns
        self.assertEqual((steps['s4']['scene_action'], steps['s4']['camera_action']), ('explode', 'overview'))
        self.assertEqual(steps['s5']['scene_action'], 'assemble')
        kinds = {a['kind'] for a in g['annotations'] if a['annotation_id'].startswith('n-s2-')}
        self.assertTrue({'part_highlight', 'callout', 'dim_others', 'flow', 'motion_direction'} <= kinds)
        self.assertEqual(g['verification_state']['geometry'], 'conceptual')   # 3D-08: plan geometry is never presented as measured
        self.assertFalse(g['verification_state']['measurements_verified'])
        self.assertTrue(all(s.get('motion', {}).get('illustrative', True) for s in g['steps']))

    def test_anchors_only_reference_ids_that_exist(self):
        plan = dict(PLAN, steps=[dict(PLAN['steps'][0], focus=['o1', 'o99'])])
        g = from_presentation(plan, source_ref='q2')
        self.assertEqual(g['steps'][0]['target_anchor_ids'], ['a-o1'])
        bad = dict(g, steps=[dict(g['steps'][0], target_anchor_ids=['a-ghost'])])
        with self.assertRaises(GuideError):
            validate_session(bad)

    def test_sessions_are_never_executable(self):
        g = from_presentation(PLAN, source_ref='q3')
        for patch in ({'command': 'del *'}, {'script': 'x'}, {'url': 'http://x'}):
            with self.subTest(patch=patch), self.assertRaises(GuideError):
                validate_session(dict(g, steps=[dict(g['steps'][0], **patch)] + g['steps'][1:]))
        with self.assertRaises(GuideError):
            validate_session(dict(g, anchors=[dict(g['anchors'][0], target_ref={'html': '<b>'})] + g['anchors'][1:]))

    def test_player_state_persists_with_cas(self):
        g = from_presentation(PLAN, source_ref='q4')
        moved = advance(g, step_id='s3', status='playing', expected_revision=1)
        self.assertEqual((moved['current_step_id'], moved['status'], moved['revision']), ('s3', 'playing', 2))
        with self.assertRaises(GuideError):
            advance(moved, step_id='s4', expected_revision=1)
        with self.assertRaises(GuideError):
            advance(moved, step_id='s99')

    def test_screen_guide_waits_for_observation_and_records_no_credentials(self):
        g = from_guide_plan(GUIDE, source_ref='q5', window={'window_id': 10, 'pid': 20})
        self.assertTrue(all(s['completion_policy'] == 'await_observation' and s['failure_policy'] == 'pause_and_reobserve' for s in g['steps']))
        self.assertTrue(all(a['type'] == 'uia' and a['visibility'] == 'unresolved' and 'geometry' not in a for a in g['anchors']))
        self.assertFalse(g['verification_state']['credentials_recorded'])
        self.assertEqual(g['steps'][1]['expected_observation'], {'kind': 'window_title_contains', 'value': 'Bienvenido'})


class DrawingGuideTests(unittest.TestCase):
    def figure(self, circle_at=(60, 60)):
        im = Image.new('RGB', (400, 300), 'white'); d = ImageDraw.Draw(im)
        d.ellipse([circle_at[0], circle_at[1], circle_at[0] + 120, circle_at[1] + 120], fill='#1e4fd8')
        d.rectangle([230, 60, 350, 150], fill='#e03030'); d.polygon([(200, 280), (260, 180), (320, 280)], fill='#20a040')
        return im

    def test_regions_shapes_and_colour_zones_come_from_the_image(self):  # DRAW-01 / DRAW-02
        a = drawing_guide.analyze(self.figure())
        shapes = {r['color_name']: r['shape'] for r in a['regions']}
        self.assertEqual(shapes, {'azul': 'círculo', 'rojo': 'rectángulo', 'verde': 'triángulo'})
        blue = drawing_guide.find_color(a, 'azul')
        self.assertEqual(len(blue), 1)
        x, y, w, h = blue[0]['bbox']
        self.assertAlmostEqual(x, 60 / 400, delta=.02); self.assertAlmostEqual(w, 120 / 400, delta=.02)
        self.assertEqual(drawing_guide.find_color(a, 'morado'), [])   # absent colour: no invented zone
        stages = drawing_guide.stages(a)
        self.assertEqual([s['stage'] for s in stages], ['construction', 'contours', 'color', 'shading'])
        self.assertEqual({m['kind'] for m in stages[0]['marks']}, {'guide_line', 'highlight_box', 'outline'})
        self.assertTrue(stages[-1]['assumed'])

    def test_guides_update_after_the_drawing_changes(self):  # DRAW-03
        before, after = drawing_guide.analyze(self.figure()), drawing_guide.analyze(self.figure(circle_at=(110, 120)))
        result = drawing_guide.compare(before, after)
        self.assertTrue(result['changed'])
        self.assertEqual([c['kind'] for c in result['changes']], ['changed'])
        self.assertFalse(drawing_guide.compare(before, drawing_guide.analyze(self.figure()))['changed'])


class DiagramEditTests(unittest.TestCase):  # DIAGRAM-02
    def test_editing_a_node_keeps_the_document_ids_and_guide_place(self):
        import copy, tempfile
        from pathlib import Path
        from backend.magic_pen import MagicPenService, write_json
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.addCleanup(tmp.cleanup)
        pen = MagicPenService(Path(tmp.name)); self.addCleanup(pen.close)
        doc = pen.acquire(Image.new('RGB', (200, 100), 'white'), {'id': 'fixture'})
        doc['queries'] = [{'id': 'b' * 32, 'source_id': doc['id'], 'revision': 1, 'state': 'completed', 'format': 'presentation',
                           'question': 'x', 'presentation': copy.deepcopy(PLAN)}]
        write_json(pen.directory(doc['id']) / 'document.json', doc)
        ref = {'id': doc['id'], 'query_id': 'b' * 32}
        session = pen.guide_session({**ref, 'step_id': 's3', 'expected_revision': 1})
        out = pen.diagram_edit({**ref, 'node_id': 'd2', 'label': '  Giro del eje  '})
        self.assertEqual([(n['id'], n['label']) for n in out['diagram']['nodes']], [('d1', 'Combustión'), ('d2', 'Giro del eje')])
        stored = pen.query(ref)
        self.assertEqual(stored['presentation']['diagram']['edges'], PLAN['diagram']['edges'])
        self.assertEqual(stored['presentation']['steps'], PLAN['steps'])
        self.assertEqual(stored['guide_session']['current_step_id'], session['current_step_id'])
        self.assertEqual(next(a['label'] for a in stored['guide_session']['anchors'] if a['anchor_id'] == 'a-d2'), 'Giro del eje')
        for bad in ({**ref, 'node_id': 'd9', 'label': 'x'}, {**ref, 'node_id': 'd1', 'label': '   '},
                    {**ref, 'node_id': 'd1', 'label': 'x' * 101}, {**ref, 'node_id': 'd1', 'label': 'x', 'object_id': 'o1'}):
            with self.assertRaises(ValueError):
                pen.diagram_edit(bad)
        self.assertEqual(pen.query(ref)['presentation']['diagram']['nodes'][0]['label'], 'Combustión')


if __name__ == '__main__':
    unittest.main()
