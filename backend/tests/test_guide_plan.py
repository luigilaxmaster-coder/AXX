import copy
import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from PIL import Image
from backend.guide_plan import evaluate, prompt_controls, resolve, snapshot, validate_guide
from backend.magic_pen import MagicPenService
from backend.presentation_plan import PlanError


def control(name, kind='Button', **kw):
    return {'control_id': uuid.uuid4().hex * 2, 'automation_id': kw.pop('automation_id', ''), 'control_type': 'ControlType.' + kind,
            'name': name, 'enabled': True, 'offscreen': False, 'value': kw.pop('value', None), 'state': kw.pop('state', {}),
            'bounds': kw.pop('bounds', {'x': 120, 'y': 80, 'width': 90, 'height': 30}), **kw}


def guide(**kw):
    return {'schema_version': '1.0', 'kind': 'guide', 'goal': 'Activar el ajuste', 'steps': [
        {'id': 'g1', 'instruction': 'Marca «Ajuste automático».', 'target': {'name': 'Ajuste automático', 'control_type': 'CheckBox'},
         'postcondition': {'kind': 'toggle_on'}},
        {'id': 'g2', 'instruction': 'Pulsa Aplicar.', 'target': {'name': 'Aplicar', 'control_type': 'Button'},
         'postcondition': {'kind': 'window_title_contains', 'value': 'guardado'}}], **kw}


class GuideContractTests(unittest.TestCase):
    def test_valid_guide_and_closed_contract(self):
        self.assertEqual(validate_guide(guide())['steps'][1]['postcondition']['value'], 'guardado')
        def variant(change):
            g = guide(); change(g); return g
        bad = {
            'click is not a postcondition': lambda g: g['steps'][0]['postcondition'].update(kind='clicked'),
            'missing value': lambda g: g['steps'][1]['postcondition'].pop('value'),
            'value where not allowed': lambda g: g['steps'][0]['postcondition'].update(value='x'),
            'coordinates': lambda g: g['steps'][0]['target'].update(x=10, y=20),
            'unknown control type': lambda g: g['steps'][0]['target'].update(control_type='Pane'),
            'script': lambda g: g['steps'][0].update(action='powershell'),
            'duplicate id': lambda g: g['steps'][1].update(id='g1'),
            'empty': lambda g: g.update(steps=[]),
            'wrong kind': lambda g: g.update(kind='presentation'),
        }
        for name, change in bad.items():
            with self.subTest(name), self.assertRaises(PlanError):
                validate_guide(variant(change))

    def test_resolution_prefers_automation_id_and_abstains_on_ambiguity(self):
        target = {'name': 'Aplicar', 'control_type': 'Button'}
        self.assertEqual(resolve({'controls': [control('APLICAR '), control('Aplicar', 'Text')]}, target)[0], 'found')
        self.assertEqual(resolve({'controls': [control('Aplicar'), control('Aplicar')]}, target)[0], 'ambiguous')
        self.assertEqual(resolve({'controls': [control('Aplicar', automation_id='ok'), control('Aplicar')]}, {**target, 'automation_id': 'ok'})[1]['automation_id'], 'ok')
        self.assertEqual(resolve({'controls': [control('Aplicar', offscreen=True)]}, target)[0], 'not_found')
        self.assertEqual(resolve({'controls': [], 'truncated': True}, target)[0], 'ambiguous', 'Incomplete trees never prove absence')
        self.assertEqual(resolve({'controls': [control('Aplicar')], 'truncated': True}, target), ('ambiguous', None), 'A cut-off tree may hide a duplicate')

    def test_postconditions_need_fresh_state_and_never_trust_a_click(self):
        box = control('Ajuste', 'CheckBox', state={'Toggle': 'Off'})
        on = copy.deepcopy(box); on['state']['Toggle'] = 'On'
        self.assertEqual(evaluate({'kind': 'toggle_on'}, 'found', box, None, ''), 'WAITING')
        self.assertEqual(evaluate({'kind': 'toggle_on'}, 'found', on, None, ''), 'VERIFIED')
        self.assertEqual(evaluate({'kind': 'toggle_on'}, 'not_found', None, None, ''), 'UNKNOWN')
        self.assertEqual(evaluate({'kind': 'selected'}, 'found', control('A'), None, ''), 'UNKNOWN', 'Missing pattern is not success')
        slider = control('Ganancia', 'Slider', state={'RangeValue': {'value': 3.0}})
        self.assertEqual(evaluate({'kind': 'value_equals', 'value': '3,0'}, 'found', slider, None, ''), 'VERIFIED')
        edit = control('Nombre', 'Edit', value='a')
        self.assertEqual(evaluate({'kind': 'value_changed'}, 'found', edit, snapshot(edit), ''), 'WAITING')
        self.assertEqual(evaluate({'kind': 'value_changed'}, 'found', dict(edit, value='b'), snapshot(edit), ''), 'VERIFIED')
        self.assertEqual(evaluate({'kind': 'exists'}, 'ambiguous', None, None, ''), 'UNKNOWN')
        self.assertEqual(evaluate({'kind': 'window_title_contains', 'value': 'Guardado'}, 'not_found', None, None, 'Doc — GUARDADO'), 'VERIFIED')

    def test_prompt_controls_are_bounded_and_omit_values(self):
        observed = {'window_title': 'App', 'controls': [control('Clave', 'Edit', value='secreto')] + [control(f'B{i}') for i in range(200)]}
        data = json.loads(prompt_controls(observed))
        self.assertEqual(len(data['controls']), 120)
        self.assertNotIn('secreto', json.dumps(data))


class FakeUia:
    def __init__(self):
        self.started = '111'
        self.controls = [control('Ajuste automático', 'CheckBox', state={'Toggle': 'Off'}, bounds={'x': 300, 'y': 200, 'width': 120, 'height': 24}),
                         control('Aplicar', bounds={'x': 500, 'y': 400, 'width': 80, 'height': 28})]
        self.title = 'Ajustes'
        self.windows = [{'window_id': 7, 'pid': 900, 'title': 'Otra', 'class_name': 'X', 'foreground': False},
                        {'window_id': 9, 'pid': 901, 'title': 'Ajustes', 'class_name': 'X', 'foreground': True}]
        self.inspections = 0

    def list_windows(self): return list(self.windows)
    def process_name(self, pid): return 'app.exe'
    def process_started(self, pid): return self.started
    def observe_geometry(self, window_id):
        bounds = {7: {'x': 2000, 'y': 0, 'width': 400, 'height': 300}, 9: {'x': 0, 'y': 0, 'width': 1000, 'height': 800}}[window_id]
        return {'window_bounds': bounds, 'minimized': False, 'monitors': []}
    def inspect_controls(self, window_id, pid, cancelled=None):
        self.inspections += 1
        assert (window_id, pid) == (9, 901), 'Guidance must observe the window under the selection'
        return {'window_title': self.title, 'process_started': self.started, 'controls': copy.deepcopy(self.controls), 'truncated': False,
                'observation': {'observation_id': uuid.uuid4().hex, 'monitors': [{'id': 'm', 'x': 0, 'y': 0, 'width': 1920, 'height': 1080}]}}


class GuideServiceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.service = MagicPenService(self.root)
        self.addCleanup(self.service.close)
        self.uia = self.service.uia = FakeUia()
        self.doc = self.service.acquire(Image.new('RGB', (1000, 800), 'white'), {'id': 'test', 'x': 0, 'y': 0})
        self.prompts = []
        test = self

        class Adapter:
            config = {'allow_paid': False, 'providers': [{'name': 'fixture', 'model': 'visual-model', 'enabled': True,
                      'free_confirmed': True, 'capabilities': ['vision']}]}
            def route(self, request):
                test.prompts.append(request)
                return {'ok': True, 'message': {'content': json.dumps(guide())}}
            def cancel(self, request_id): return True
        self.service.adapter = Adapter()
        self.service.save({'id': self.doc['id'], 'expected_revision': 1,
                           'selection': {'shape': 'rect', 'bounds': [250, 150, 450, 300]}, 'strokes': []})
        q = self.service.start({'id': self.doc['id'], 'revision': 2, 'question': 'Guíame', 'provider': 'fixture', 'model': 'visual-model',
                                'selection_mode': 'manual', 'request_id': uuid.uuid4().hex, 'format': 'guide'})
        end = time.monotonic() + 3
        while q['state'] == 'running' and time.monotonic() < end:
            time.sleep(.01)
            q = self.service.query({'id': q['source_id'], 'query_id': q['id']})
        self.q = q

    def check(self, step, phase):
        return self.service.guide_check({'id': self.doc['id'], 'query_id': self.q['id'], 'step_id': step, 'phase': phase})

    def test_guide_is_grounded_in_the_window_under_the_selection(self):
        self.assertEqual(self.q['state'], 'completed', self.q.get('error'))
        self.assertEqual(self.q['guide_window'], {'window_id': 9, 'pid': 901, 'title': 'Ajustes', 'process_started': '111'})
        prompt = self.prompts[0]['messages'][1]['content'][0]['text']
        self.assertIn('Ajuste automático', prompt)
        self.assertIn('"kind":"guide"', self.prompts[0]['messages'][0]['content'])

    def test_user_action_is_verified_from_fresh_state_and_persisted(self):
        targeted = self.check('g1', 'target')
        self.assertEqual((targeted['state'], targeted['bounds']['x']), ('WAITING_USER', 300))
        self.assertEqual(self.check('g1', 'verify')['state'], 'WAITING_USER', 'Nothing changed yet')
        self.uia.controls[0]['bounds']['y'] = 260  # Scrolled: the overlay re-anchors to the new bounds.
        self.uia.controls[0]['state']['Toggle'] = 'On'
        verified = self.check('g1', 'verify')
        self.assertEqual((verified['state'], verified['bounds']['y']), ('VERIFIED', 260))
        self.uia.controls[0]['state']['Toggle'] = 'Off'
        self.assertEqual(self.check('g1', 'verify')['state'], 'VERIFIED', 'A verified step is never re-run or downgraded')
        reopened = MagicPenService(self.root)
        self.addCleanup(reopened.close)
        stored = reopened.query({'id': self.doc['id'], 'query_id': self.q['id']})
        self.assertEqual(stored['guide_progress']['g1']['state'], 'VERIFIED')

    def test_uncertain_ambiguous_and_stale_windows_never_advance(self):
        self.assertEqual(self.check('g2', 'target')['state'], 'WAITING_USER')
        self.uia.controls.pop()  # The button vanished: a title change is still required.
        self.assertEqual(self.check('g2', 'verify')['state'], 'WAITING_USER')
        self.uia.title = 'Ajustes — guardado'
        self.assertEqual(self.check('g2', 'verify')['state'], 'VERIFIED')
        self.uia.controls.append(copy.deepcopy(self.uia.controls[0]))
        self.assertEqual(self.check('g1', 'target')['state'], 'AMBIGUOUS')
        with self.assertRaisesRegex(ValueError, 'Señala'):
            self.check('g1', 'verify')
        self.uia.controls.pop()
        self.assertEqual(self.check('g1', 'target')['state'], 'WAITING_USER')
        self.uia.controls.clear()
        self.assertEqual(self.check('g1', 'verify')['state'], 'UNKNOWN')
        self.uia.started = '222'
        self.assertEqual(self.check('g1', 'verify')['state'], 'STALE', 'A restarted application is a different window instance')

    def test_repointing_keeps_the_first_baseline(self):
        first = self.check('g2', 'target')['record']['baseline']
        self.uia.controls[1]['value'] = 'cambiado'  # The user acted, then scrolled and asked to re-point.
        self.assertEqual(self.check('g2', 'target')['record']['baseline'], first)

    def test_already_satisfied_step_is_verified_without_asking_for_action(self):
        self.uia.controls[0]['state']['Toggle'] = 'On'
        self.assertEqual(self.check('g1', 'target')['state'], 'VERIFIED')

    def test_invalid_requests_are_rejected(self):
        for body in ({'id': self.doc['id'], 'query_id': self.q['id'], 'step_id': 'g9', 'phase': 'target'},
                     {'id': self.doc['id'], 'query_id': self.q['id'], 'step_id': 'g1', 'phase': 'click'},
                     {'id': self.doc['id'], 'query_id': self.q['id'], 'step_id': 'g1', 'phase': 'target', 'x': 1}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.service.guide_check(body)


if __name__ == '__main__':
    unittest.main()
