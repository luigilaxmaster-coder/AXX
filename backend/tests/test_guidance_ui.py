"""Explicación señalizada in the real Axx.html over the real backend (Chromium + SwiftShader WebGL).

These are browser integration receipts (3D-02..05, 3D-07, DIAGRAM-01/03, DRAW-01/02); they are NOT installed WebView2
acceptance. The plan is a fixture; anchors, projection, motions, sessions and drawing regions are the real code.
"""
import functools
import http.server
from pathlib import Path
import tempfile
import time
import unittest

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from backend.magic_pen import write_json
from backend.tests.test_acts_inference import _Server
from backend.tests.test_acts_ui import ROOT, open_axx, serve

LABELS = ['Pistón', 'Cigüeñal', 'Bloque', 'Culata', 'Biela', 'Bujía', 'Válvula de admisión', 'Válvula de escape', 'Cárter',
          'Volante', 'Junta', 'Árbol de levas']
PLAN = {'schema_version': '1.0', 'kind': 'presentation', 'title': 'Motor', 'summary': 'Cómo funciona', 'fidelity': 'conceptual',
        'steps': [{'id': 's1', 'title': 'Qué se observa', 'body': 'Un motor de un cilindro.', 'narration': 'Vista general.', 'basis': 'observed'},
                  {'id': 's2', 'title': 'El pistón', 'body': 'El pistón se desplaza dentro del cilindro.', 'narration': 'El pistón sube y baja.', 'basis': 'inferred', 'focus': ['o1']},
                  {'id': 's3', 'title': 'El cigüeñal', 'body': 'El cigüeñal gira y transmite el movimiento.', 'narration': 'El cigüeñal gira.', 'basis': 'inferred', 'focus': ['o2']},
                  {'id': 's4', 'title': 'Despiece', 'body': 'Vista explotada de las piezas.', 'narration': 'Separamos las piezas.', 'basis': 'inferred'},
                  {'id': 's5', 'title': 'Reensamblado', 'body': 'Reensambla el conjunto.', 'narration': 'Volvemos a unir.', 'basis': 'inferred'}],
        'scene': {'fidelity': 'conceptual', 'objects': [
            {'id': f'o{i + 1}', 'label': label, 'shape': 'piston' if i == 0 else 'crankshaft' if i == 1 else 'box',
             'size': [1, 1, 1], 'position': [(i % 4) * 2.2 - 3.3, (i // 4) * 2.2 - 2.2, 0], 'color': '#7799cc'} for i, label in enumerate(LABELS)],
            'arrows': []},
        'diagram': {'nodes': [{'id': 'd1', 'label': 'Combustión', 'step_id': 's2', 'bounds': [.1, .3, .25, .2]},
                              {'id': 'd2', 'label': 'Giro', 'step_id': 's3', 'bounds': [.6, .3, .25, .2]}],
                    'edges': [{'from': 'd1', 'to': 'd2', 'label': 'empuja'}]}}
LOAD = '''async id=>{const pen=Axx.magicPen;pen.signaled=true;localStorage.setItem('axx.magicPen.signaled','1');pen.active=true;pen.root.hidden=false;
    pen.state='reviewing';const doc=await Axx.backendRequest('POST','/axx-api/pen/get',{id});await pen.load(doc,true);pen.showWidget();}'''


class GuidanceUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.srv = _Server(Path(self.tmp.name), [])
        self.srv.rt.flags.set_flag('magic_scene_v2', True, reason='guidance ui')
        self.srv.api.timeout = 120
        self.web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))

    def tearDown(self):
        self.web.shutdown(); self.web.server_close(); self.srv.close(); self.tmp.cleanup()

    def capture(self, image, plan=None):
        capture = self.srv.magic_pen.acquire(image, {'id': 'fixture'})
        if plan:
            capture['queries'] = [{'id': 'b' * 32, 'source_id': capture['id'], 'revision': 1, 'state': 'completed', 'format': 'presentation',
                                   'question': 'Explícame este motor señalando cada pieza', 'presentation': plan}]
            write_json(self.srv.magic_pen.directory(capture['id']) / 'document.json', capture)
        return capture

    def open(self, browser, capture_id):
        page = open_axx(browser, self.srv, self.web)
        page.evaluate(LOAD, capture_id)
        return page

    def test_3d_steps_are_anchored_animated_and_resumable(self):
        capture = self.capture(Image.new('RGB', (400, 300), 'white'), PLAN)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            try:
                page = self.open(browser, capture['id'])
                page.wait_for_function('Axx.magicPen.player?.scene && Axx.magicPen.presentationQuery()?.guide_session', timeout=60000)
                scene = 'Axx.magicPen.player.scene'
                page.wait_for_function(scene + '.guideState().labels.length>8', timeout=30000)
                overview = page.evaluate(scene + '.guideState()')
                self.assertGreater(len(overview['labels']), 8)  # C: no 8-label cap; budget-based, collision-free
                # 3D-02: the piston step targets o1, draws an anchored callout and frames it.
                page.evaluate('Axx.magicPen.seekPresentation(1)')
                page.wait_for_function(scene + ".guideState().targets.join()==='o1'", timeout=15000)
                same_frame = '(()=>{const s=' + scene + ';s.qa();return {state:s.guideState(),anchor:s.project("o1")};})()'  # label and projection from one render
                page.wait_for_function(scene + ".qa()&&" + scene + ".guideState().labels.some(l=>l.guided)", timeout=30000)
                frame = page.evaluate(same_frame); state, anchor = frame['state'], frame['anchor']
                guided = [l for l in state['labels'] if l['guided']]
                self.assertEqual([l['id'] for l in guided], ['o1'])
                self.assertLessEqual(abs(guided[0]['x'] - anchor['x']) + abs(guided[0]['y'] - anchor['y']), 3)
                self.assertEqual(page.evaluate("document.querySelectorAll('.mp-scene-guide .mp-guide-leader').length"), 1)
                # 3D-05: an illustrative motion actually moves the piston's geometry.
                self.assertEqual(state['motions'], [{'id': 'o1', 'kind': 'translate', 'axis': 'y', 'illustrative': True}])
                first = page.evaluate(scene + ".geometrySnapshot().find(p=>p.object_id==='o1').positions_b64")
                page.wait_for_timeout(2000)  # SwiftShader runs requestAnimationFrame at ~2 fps in headless
                self.assertNotEqual(page.evaluate(scene + ".geometrySnapshot().find(p=>p.object_id==='o1').positions_b64"), first)
                # 3D-03: turn the camera; the callout follows the part's projected anchor (no stale arrow).
                page.evaluate(scene + '.flyTo({theta:2.4,phi:.8})')
                page.wait_for_function('(()=>{const v=' + scene + '.getView();return Math.abs(v.theta-2.4)<.01;})()', timeout=30000)
                frame = page.evaluate(same_frame)
                label = next(l for l in frame['state']['labels'] if l['id'] == 'o1')
                now = frame['anchor']
                self.assertLessEqual(abs(label['x'] - now['x']) + abs(label['y'] - now['y']), 3)
                self.assertGreater(abs(now['x'] - anchor['x']) + abs(now['y'] - anchor['y']), 10)
                # DIAGRAM-01/03: the narrated step's node is active and its connection carries the flow.
                page.wait_for_function("document.querySelector('#mp-answers svg[data-active-nodes]')?.dataset.activeNodes==='d1'", timeout=15000)
                self.assertEqual(page.evaluate("[...document.querySelectorAll('#mp-answers .mp-diagram-flow')].map(l=>l.dataset.from+'>'+l.dataset.to)"), ['d1>d2'])
                # crankshaft step rotates; explode then reassemble (3D-04)
                page.evaluate('Axx.magicPen.seekPresentation(2)')
                page.wait_for_function(scene + ".motions().some(m=>m.id==='o2'&&m.kind==='rotate')", timeout=15000)
                page.wait_for_function("document.querySelector('#mp-answers svg[data-active-nodes]')?.dataset.activeNodes==='d2'", timeout=15000)
                page.evaluate('Axx.magicPen.seekPresentation(3)')
                page.wait_for_function('Axx.magicPen.player.exploded===true', timeout=15000)
                self.assertEqual(page.evaluate(scene + '.motions().length'), 0)
                page.evaluate('Axx.magicPen.seekPresentation(4)')
                page.wait_for_function('Axx.magicPen.player.exploded===false', timeout=15000)
                page.wait_for_timeout(800)
            finally:
                browser.close()
            # 3D-07: the session is persisted; a fresh page resumes at the last step.
            stored = self.srv.magic_pen.query({'id': capture['id'], 'query_id': 'b' * 32})['guide_session']
            self.assertEqual(stored['current_step_id'], 's5')
            self.assertEqual(stored['verification_state']['geometry'], 'conceptual')  # 3D-08
            browser = p.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            try:
                page = self.open(browser, capture['id'])
                page.wait_for_function('Axx.magicPen.player?.scene && Axx.magicPen.player.index===4', timeout=60000)
            finally:
                browser.close()

    def test_drawing_tutor_marks_colour_zones_from_the_image(self):
        im = Image.new('RGB', (500, 360), 'white'); d = ImageDraw.Draw(im)
        d.ellipse([80, 80, 200, 200], fill='#1e4fd8'); d.rectangle([260, 90, 400, 200], fill='#e03030')
        capture = self.capture(im)
        self.srv.magic_pen.save({'id': capture['id'], 'expected_revision': 1, 'selection': {'shape': 'rect', 'bounds': [40, 40, 460, 320]}, 'strokes': []})
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = self.open(browser, capture['id'])
                page.evaluate("Axx.magicPen.startDrawingGuide('azul')")
                page.wait_for_function('Axx.magicPen.drawingGuide?.stages?.length', timeout=20000)
                g = page.evaluate('({stage:Axx.magicPen.drawingGuide.stages[Axx.magicPen.drawingGuide.stage].stage,'
                                  'regions:Axx.magicPen.drawingGuide.color_regions,frame:Axx.magicPen.drawingGuide.frame})')
                self.assertEqual((g['stage'], len(g['regions']), g['frame']), ('color', 1, [40, 40, 420, 280]))
                # DRAW-02: the blue zone is painted translucent over the canvas at the circle; the red one is not.
                pixel = page.evaluate('([x,y])=>[...Axx.magicPen.ctx.getImageData(x,y,1,1).data]', [140, 140])
                other = page.evaluate('([x,y])=>[...Axx.magicPen.ctx.getImageData(x,y,1,1).data]', [330, 145])
                self.assertGreater(pixel[3], 0); self.assertGreater(pixel[2], pixel[0])
                self.assertEqual(other[3], 0)
                # DRAW-01: construction stage draws guide lines (centre axis pixel is non-transparent).
                page.evaluate('Axx.magicPen.drawingGuide.stage=0;Axx.magicPen.render()')
                self.assertTrue(page.evaluate("document.querySelector('.mp-drawing-guide')!==null"))
                axis = page.evaluate('([x,y])=>[...Axx.magicPen.ctx.getImageData(x,y,1,1).data]', [40 + 420 * .5, 80])
                self.assertGreater(axis[3], 0)
                page.evaluate("Axx.magicPen.startDrawingGuide('morado')")
                page.wait_for_function("Axx.magicPen.drawingGuide.color==='morado'", timeout=20000)
                self.assertEqual(page.evaluate('Axx.magicPen.drawingGuide.color_regions.length'), 0)  # never an invented zone
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
