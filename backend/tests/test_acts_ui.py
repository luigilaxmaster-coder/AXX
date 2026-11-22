"""Acts Studio + chat in the real Axx.html page against the real backend; only native IPC is a fixture.

The model endpoint is the controlled loopback responder from test_acts_inference (it echoes the model it received).
"""
import functools
import http.server
from pathlib import Path
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright

from backend.tests.test_acts_inference import _EchoModel, _Server, provider


class ActsUiTests(unittest.TestCase):
    def test_create_act_in_studio_then_mention_it_in_the_existing_chat(self):  # ACT-01..05, ACT-07, ACT-09 (controlled)
        root = Path(__file__).resolve().parents[2]
        _EchoModel.seen = []
        echo = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _EchoModel)
        threading.Thread(target=echo.serve_forever, daemon=True).start()
        web = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root / '1.AXX')))
        threading.Thread(target=web.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory() as temp:
            srv = _Server(Path(temp), [provider('loop-a', f'http://127.0.0.1:{echo.server_port}/v1', 'model-alpha')])
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        page = browser.new_page(viewport={'width': 1440, 'height': 1000})

                        def request(method, path, body=None):
                            code, data = srv.api.request(method, path, body)
                            if code >= 400:
                                raise RuntimeError(data.get('error', {}).get('message', 'HTTP ' + str(code)))
                            return data
                        page.expose_function('testBackend', request)
                        page.add_init_script("""window.__TAURI__={core:{invoke:async(name,args)=>{
                            if(name==='backend_request') return window.testBackend(args.method,args.path,args.body);
                            if(name==='native_status') return {native:true,backendReady:true,desktop:{workWidth:1920,workHeight:1080,spaceLeft:960,spaceRight:960,spaceAbove:540,spaceBelow:540}};
                            if(name==='desktop_layout') return {workWidth:1920,workHeight:1080,...args};
                            return null;
                        }},event:{listen:async()=>()=>{}}};""")
                        page.goto(f'http://127.0.0.1:{web.server_port}/Axx.html')
                        page.wait_for_function('window.Axx?.acts')
                        global_prefs = page.evaluate('JSON.stringify([Axx.companion.data.prefs.provider, Axx.companion.data.prefs.model])')
                        page.evaluate("Axx.companion.openFeature('agent')")
                        page.get_by_role('button', name='Abrir Acts', exact=True).click()
                        page.get_by_role('button', name='Activar Acts', exact=True).click()
                        page.wait_for_function("document.querySelector('.axx-acts-status').textContent.includes('Acts activados')")
                        page.get_by_role('button', name='Crear Act', exact=True).click()
                        form = page.locator('.axx-acts-editor')
                        form.get_by_label('Nombre', exact=True).fill('Dev')
                        form.get_by_label('Nombre corto para @menciones').fill('Dev')
                        form.get_by_label('Especialidad / rol').fill('Programador')
                        form.get_by_label('Instrucciones persistentes').fill('Conserva los contratos públicos.')
                        form.get_by_role('tab', name='Apariencia').click()
                        form.get_by_label('Forma').select_option(label='Helix')
                        form.get_by_label('Paleta').select_option(label='Ocean')
                        form.get_by_role('tab', name='Inteligencia').click()
                        form.get_by_label('Proveedor').select_option('loop-a')
                        self.assertEqual(form.get_by_label('Modelo').input_value(), 'model-alpha')
                        form.get_by_role('tab', name='Personalidad').click()
                        form.get_by_label('Formalidad').select_option('formal')
                        self.assertIn('Cambios sin guardar', page.locator('.axx-acts-dirty').text_content())
                        form.get_by_role('button', name='Aplicar y verificar', exact=True).click()
                        page.wait_for_function("document.querySelector('.axx-acts-status').textContent.includes('Guardado y verificado')")
                        self.assertIn('Usa un tono formal.', page.locator('.axx-acts-preview').text_content())
                        stored = srv.rt.registry.list_profiles()[0]
                        self.assertEqual((stored['appearance']['form_name'], stored['personality'], stored['collaboration']['mention']),
                                         ('Helix', {'formality': 'formal'}, 'Dev'))

                        result = page.evaluate("""(async()=>{const r=await Axx.companion.brain.chat(
                            {...Axx.companion.data.prefs, prompt_mode:'conversation'},
                            [{role:'user',content:'@Dev revisa esto'}], new AbortController().signal, ()=>{});
                            return {text:r.text, act:r.route.act};})()""")
                        self.assertTrue(result['text'].startswith('〔Dev〕 ACK model-alpha'), result)
                        self.assertTrue(result['act']['model_verified'])
                        self.assertEqual(_EchoModel.seen[-1]['model'], 'model-alpha')
                        self.assertIn('Conserva los contratos públicos.', str(_EchoModel.seen[-1]['messages']))
                        # The main AXX avatar/profile/model selection is untouched by Act turns (ACT-07).
                        self.assertEqual(page.evaluate('JSON.stringify([Axx.companion.data.prefs.provider, Axx.companion.data.prefs.model])'), global_prefs)
                    finally:
                        browser.close()
            finally:
                srv.close()
                echo.shutdown(); echo.server_close(); web.shutdown(); web.server_close()


if __name__ == '__main__':
    unittest.main()
