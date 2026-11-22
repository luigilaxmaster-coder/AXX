"""Acts Studio + chat + Code Studio in the real Axx.html page against the real backend; only native IPC is a fixture.

The model endpoints are controlled loopback responders: one echoes the model it received, the other answers code
tasks with one complete file. Code Studio work uses a real Git repository and real test subprocesses.
"""
import functools
import http.server
from pathlib import Path
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright

from backend.tests.test_acts_code_tools import BUGGY, FIXED, _CoderModel, git_repo
from backend.tests.test_acts_inference import _EchoModel, _Server, act_spec, provider

ROOT = Path(__file__).resolve().parents[2]
FAKE_TAURI = """window.__TAURI__={core:{invoke:async(name,args)=>{
    if(name==='backend_request') return window.testBackend(args.method,args.path,args.body);
    if(name==='native_status') return {native:true,backendReady:true,desktop:{workWidth:1920,workHeight:1080,spaceLeft:960,spaceRight:960,spaceAbove:540,spaceBelow:540}};
    if(name==='desktop_layout') return {workWidth:1920,workHeight:1080,...args};
    return null;
}},event:{listen:async()=>()=>{}}};"""


def serve(handler):
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def open_axx(browser, srv, web):
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})

    def request(method, path, body=None):
        code, data = srv.api.request(method, path, body)
        if code >= 400:
            raise RuntimeError(data.get('error', {}).get('message', 'HTTP ' + str(code)))
        return data
    page.expose_function('testBackend', request)
    page.add_init_script(FAKE_TAURI)
    page.goto(f'http://127.0.0.1:{web.server_port}/Axx.html')
    page.wait_for_function('window.Axx?.acts && window.Axx?.codeStudio')
    return page


class ActsUiTests(unittest.TestCase):
    def setUp(self):
        self.web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))

    def tearDown(self):
        self.web.shutdown(); self.web.server_close()

    def test_create_act_in_studio_then_mention_it_in_the_existing_chat(self):  # ACT-01..05, ACT-07, ACT-09 (controlled)
        _EchoModel.seen = []
        echo = serve(_EchoModel)
        with tempfile.TemporaryDirectory() as temp:
            srv = _Server(Path(temp), [provider('loop-a', f'http://127.0.0.1:{echo.server_port}/v1', 'model-alpha')])
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        page = open_axx(browser, srv, self.web)
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
                echo.shutdown(); echo.server_close()

    def test_grant_code_tools_then_dev_writes_qa_reviews_and_owner_integrates(self):  # CODE-04..10 + Dev → QA UI (controlled)
        _CoderModel.seen = []
        coder = serve(_CoderModel)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            repo = git_repo(Path(temp))
            srv = _Server(Path(temp), [provider('loop-a', f'http://127.0.0.1:{coder.server_port}/v1', 'model-alpha')])
            try:
                srv.rt.flags.set_flag('agent_profiles_v1', True, reason='owner enabled Acts')
                srv.rt.registry.create_profile(act_spec('act-dev', 'Dev', 'Helix', 'loop-a', 'model-alpha',
                                                        collaboration={'review_required': True}))
                srv.rt.registry.create_profile(act_spec('act-qa', 'QA', 'Core', 'loop-a', 'model-alpha', role='QA'))
                srv.rt.registry.grant_permission(grant_id='g-qa-review', agent_id='act-qa', tool_id='axx.code',
                                                 resource_pattern='*', operation_kinds=['review'])
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        page = open_axx(browser, srv, self.web)
                        page.on('dialog', lambda d: d.accept('Corrige add para que sume.') if d.type == 'prompt' else d.accept())
                        page.evaluate("Axx.companion.openFeature('agent')")
                        # Owner grants the Code Studio steps in Acts Studio's Herramientas tab.
                        page.get_by_role('button', name='Abrir Acts', exact=True).click()
                        page.locator('.axx-acts-card', has_text='Dev').get_by_role('button', name='Personalizar').click()
                        form = page.locator('.axx-acts-editor')
                        form.get_by_role('tab', name='Herramientas').click()
                        for label in ('Crear su worktree', 'Aplicar parches en su worktree', 'Ejecutar pruebas en su worktree',
                                      'Integrar en el proyecto tras pruebas superadas'):
                            form.get_by_label(label).check()
                        form.get_by_role('button', name='Aplicar y verificar', exact=True).click()
                        page.wait_for_function("document.querySelector('.axx-acts-status').textContent.includes('Guardado y verificado')")
                        grants = [g for g in srv.rt.registry.list_permissions('act-dev') if g['tool_id'] == 'axx.code']
                        self.assertEqual(grants[0]['operation_kinds'], ['worktree', 'patch', 'test', 'integrate'])
                        page.get_by_role('button', name='Cerrar Acts', exact=True).click()

                        page.get_by_role('button', name='Abrir Code Studio', exact=True).click()
                        page.wait_for_function('Axx.codeStudio.editor !== null', timeout=60000)
                        page.locator('[data-code=root]').fill(str(repo))
                        page.get_by_role('button', name='Abrir proyecto', exact=True).click()
                        page.locator('[data-code=browser]').get_by_role('button', name='calc.py', exact=True).click()
                        page.wait_for_function("Axx.codeStudio.editor.getValue().includes('a - b')")
                        page.locator('summary', has_text='Git y pruebas').click()
                        page.locator('[data-code=act]').select_option('act-dev')
                        status = "document.querySelector('[data-code=status]').textContent.includes(%r)"
                        page.get_by_role('button', name='Delegar archivo al Act', exact=True).click()
                        page.wait_for_function(status % 'Revisa el diff', timeout=60000)
                        self.assertEqual(page.evaluate('Axx.codeStudio.diffEditor.getModel().modified.getValue()'), FIXED)
                        self.assertEqual((repo / 'calc.py').read_text(encoding='utf-8'), BUGGY)  # only the Act's worktree changed
                        self.assertEqual(_CoderModel.seen[-1]['model'], 'model-alpha')
                        self.assertIn('+    return a + b', page.locator('[data-code=output]').text_content())

                        page.get_by_role('button', name='Probar en su worktree', exact=True).click()
                        page.wait_for_function(status % 'Pruebas superadas', timeout=60000)
                        integrate = page.get_by_role('button', name='Integrar trabajo del Act', exact=True)
                        self.assertFalse(integrate.is_visible())  # Dev requires another Act's review first
                        page.locator('[data-code=reviewer]').select_option('act-qa')
                        page.get_by_role('button', name='Pedir revisión', exact=True).click()
                        page.wait_for_function(status % 'QA aprobó el cambio', timeout=60000)
                        self.assertIn('VEREDICTO', json_messages := page.evaluate('JSON.stringify(Axx.companion.data.messages.map(m => m.text))'))
                        self.assertIn('〔Dev〕 → 〔QA〕', json_messages)  # the handoff is visible in the existing chat
                        integrate.click()
                        page.wait_for_function(status % 'Cambio integrado', timeout=60000)
                        self.assertEqual((repo / 'calc.py').read_text(encoding='utf-8'), FIXED)
                        page.wait_for_function("Axx.codeStudio.editor.getValue().includes('a + b')")
                    finally:
                        browser.close()
            finally:
                srv.close()
                coder.shutdown(); coder.server_close()


if __name__ == '__main__':
    unittest.main()
