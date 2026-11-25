"""Equipos (node editor) and Rutinas in the real Axx.html over the real backend, with real pointer gestures.

Browser integration receipts (Chromium), NOT installed WebView2 acceptance. The model is a fixture that echoes which
upstream outputs it received; registry, graph validation, TaskGraph, events and scheduler are the real ones.
"""
import functools
import http.server
from pathlib import Path
import tempfile
import threading
import time
import uuid
import unittest
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from backend.agents.http_api import EvolutionHTTP
from backend.tests.test_acts_inference import _Server, act_spec, provider
from backend.tests.test_acts_ui import FAKE_TAURI, ROOT, serve

ASYNC_BRIDGE = """window.testBackend=async(method,path,body)=>{const t=await window.testStart(method,path,body??null);
  for(;;){const r=await window.testPoll(t);if(r)return r.ok?r.data:Promise.reject(new Error(r.error));await new Promise(f=>setTimeout(f,40));}};"""


def open_axx_concurrent(browser, srv, web):
    """Like open_axx, but backend calls run on threads: the page can poll events while teams/run is in flight,
    as it does against the real threaded server (the plain bridge serialises calls through Playwright)."""
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
    results, lock = {}, threading.Lock()

    def start(method, path, body):
        ticket = uuid.uuid4().hex
        def work():
            code, data = srv.api.request(method, path, body)
            with lock:
                results[ticket] = {'ok': True, 'data': data} if code < 400 else {'ok': False, 'error': data.get('error', {}).get('message', 'HTTP %d' % code)}
        threading.Thread(target=work, daemon=True).start()
        return ticket

    def poll(ticket):
        with lock:
            return results.pop(ticket, None)
    page.expose_function('testStart', start)
    page.expose_function('testPoll', poll)
    page.add_init_script(FAKE_TAURI + ASYNC_BRIDGE)
    page.goto(f'http://127.0.0.1:{web.server_port}/Axx.html')
    page.wait_for_function('window.Axx?.acts && window.Axx?.codeStudio')
    return page


class TeamFlowUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.srv = _Server(Path(self.tmp.name), [provider('loop-a', 'http://127.0.0.1:9/v1', 'model-alpha')])
        self.srv.rt.flags.set_flag('agent_profiles_v1', True, reason='team flow ui')
        self.srv.rt.inference_adapter = object()  # routines need a transport; the model itself is the fixture below
        for aid, name, form in (('act-plan', 'Plan', 'Core'), ('act-front', 'Front', 'Flow'), ('act-qa', 'QA', 'Prism')):
            code, body = self.srv.api.request('POST', '/axx-api/agents/v1/profiles', act_spec(aid, name, form, 'loop-a', 'model-alpha'))
            self.assertEqual(code, 200, body)
        self.prompts = {}
        test = self

        def fake_infer(http, act, envelope, conversation_id, cancel_event=None):
            time.sleep(.9)  # long enough to see each node working on the canvas
            test.prompts[act['act_id']] = envelope['messages'][-1]['content']
            return {'ok': True, 'message': {'content': f'salida-de-{act["act_id"]}'}}, {'model_verified': True, 'model': 'model-alpha'}
        patcher = patch.object(EvolutionHTTP, '_infer_act', fake_infer)
        patcher.start(); self.addCleanup(patcher.stop)
        self.web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))

    def tearDown(self):
        self.web.shutdown(); self.web.server_close(); self.srv.close(); self.tmp.cleanup()

    @staticmethod
    def drag_connect(page, src, dst):
        port = page.locator(f'.axx-flow-node[data-agent="{src}"] .axx-flow-out').bounding_box()
        node = page.locator(f'.axx-flow-node[data-agent="{dst}"]').bounding_box()
        page.mouse.move(port['x'] + port['width'] / 2, port['y'] + port['height'] / 2)
        page.mouse.down()
        page.mouse.move(node['x'] + 60, node['y'] + 50, steps=12)
        page.mouse.up()

    def test_build_connect_save_and_run_a_team_then_schedule_it(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = open_axx_concurrent(browser, self.srv, self.web)
                page.evaluate("Axx.companion.openFeature('acts')")
                page.get_by_role('tab', name='Equipos (Teams)').click()
                page.get_by_role('button', name='+ Nuevo equipo').click()
                page.get_by_label('Nombre del equipo').fill('Lanzamiento')
                for name in ('Plan', 'Front', 'QA'):
                    page.locator('.axx-flow-palette').get_by_role('button', name=name).click()
                self.assertEqual(page.locator('.axx-flow-node').count(), 3)
                # real pointer drags from an output port onto another Act
                self.drag_connect(page, 'act-plan', 'act-front')
                self.drag_connect(page, 'act-front', 'act-qa')
                edges = page.evaluate("[...document.querySelectorAll('.axx-flow-edge')].map(g=>g.dataset.from+'>'+g.dataset.to)")
                self.assertEqual(sorted(edges), ['act-front>act-qa', 'act-plan>act-front'])
                self.drag_connect(page, 'act-qa', 'act-plan')  # would close a cycle: refused, explained
                self.assertIn('ciclo', page.locator('.axx-acts-status').text_content())
                self.assertEqual(page.locator('.axx-flow-edge').count(), 2)
                self.assertEqual(page.evaluate("[...document.querySelectorAll('.axx-flow-order')].map(o=>o.textContent).join()"), '1,2,3')
                # the node's own part of the work, edited in the inspector
                page.locator('.axx-flow-node[data-agent="act-qa"]').click(position={'x': 120, 'y': 80})
                page.get_by_label('Su parte en este flujo').fill('Revisa todo antes de entregar')
                page.get_by_role('button', name='Crear equipo').click()
                page.wait_for_function("document.querySelector('.axx-acts-status').textContent.includes('guardado')")
                team = self.srv.rt.registry.list_teams()[0]
                self.assertEqual(sorted((e['from'], e['to']) for e in team['graph']['edges']),
                                 [('act-front', 'act-qa'), ('act-plan', 'act-front')])
                self.assertEqual(next(n for n in team['graph']['nodes'] if n['agent_id'] == 'act-qa')['instruction'], 'Revisa todo antes de entregar')
                # run: nodes and connections light up from that run's events, then each output is readable
                page.get_by_label('Objetivo de la ejecución').fill('Publica la página de precios')
                page.get_by_role('button', name='Ejecutar flujo').click()
                page.wait_for_selector('.axx-flow-node[data-state=working]', timeout=15000)
                page.wait_for_selector('.axx-flow-edge[data-state=flowing] .axx-flow-dot', timeout=15000)
                page.screenshot(path=str(ROOT / 'build' / 'acts-team-flow-live.png'))
                page.wait_for_function("[...document.querySelectorAll('.axx-flow-node')].every(n=>n.dataset.state==='completed')", timeout=30000)
                page.wait_for_function("document.querySelector('.axx-flow-runinfo').textContent.startsWith('Completado')", timeout=10000)
                self.assertEqual(page.locator('.axx-flow-edge[data-state=done]').count(), 2)
                self.assertIn('salida-de-act-front', self.prompts['act-qa'])
                self.assertIn('Revisa todo antes de entregar', self.prompts['act-qa'])
                page.locator('.axx-flow-node[data-agent="act-front"]').click(position={'x': 120, 'y': 80})
                self.assertIn('salida-de-act-front', page.locator('.axx-flow-output pre').text_content())
                page.screenshot(path=str(ROOT / 'build' / 'acts-team-flow.png'))

                # Rutinas: the whole team, on weekdays, with a schedule preview computed by the scheduler
                page.get_by_role('tab', name='Rutinas').click()
                page.get_by_role('button', name='+ Nueva rutina').click()
                editor = page.locator('.axx-rt-editor')
                editor.get_by_label('Nombre').fill('Resumen semanal')
                editor.get_by_role('tab', name='Un equipo').click()
                editor.get_by_role('tab', name='Días de la semana').click()
                editor.get_by_label('Hora').fill('18:30')
                page.wait_for_function("document.querySelector('.axx-rt-preview').textContent.includes('Lunes, Martes, Miércoles, Jueves, Viernes a las 18:30')")
                self.assertEqual(editor.locator('.axx-rt-preview .axx-acts-chip').count(), 3)
                editor.get_by_label('Instrucción').fill('Resume el avance de la semana')
                editor.get_by_role('button', name='Programar rutina').click()
                page.wait_for_selector('.axx-rt-card[data-routine="resumen-semanal"]')
                stored = self.srv.rt.routines.get_routine('resumen-semanal')
                self.assertEqual((stored['schedule_spec'], stored['team_id'], stored['requires_approval']), ('30 18 * * 1,2,3,4,5', team['team_id'], True))
                card = page.locator('.axx-rt-card[data-routine="resumen-semanal"]')
                self.assertIn('Lunes, Martes, Miércoles, Jueves, Viernes a las 18:30', card.text_content())
                card.get_by_role('button', name='Ejecutar ahora').click()
                page.wait_for_selector('.axx-rt-card[data-routine="resumen-semanal"][data-state=awaiting_approval]')
                page.locator('.axx-rt-card[data-routine="resumen-semanal"]').get_by_role('button', name='Aprobar y ejecutar').click()
                page.wait_for_function("document.querySelector('.axx-acts-status').textContent.includes('Completada')", timeout=30000)
                page.locator('.axx-rt-card[data-routine="resumen-semanal"]').get_by_role('button', name='Historial').click()
                page.wait_for_selector('.axx-rt-history [data-state=completed]')
                page.screenshot(path=str(ROOT / 'build' / 'acts-routines.png'))
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
