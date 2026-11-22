"""Browser editor against the real scoped file service; native IPC is a fixture."""
import functools
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright
from backend.tests.test_evolution3_full_functional_audit import _start_bound_server, _stop_bound_server, _HttpTestClient


class CodeStudioUiTests(unittest.TestCase):
    def test_monaco_edit_save_navigation_and_conflict_against_real_files(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            repo = directory / 'project'; repo.mkdir()
            source = repo / 'hello.py'; source.write_bytes(b'\xef\xbb\xbfVALUE = 1\r\n')
            (repo / 'other.py').write_text('OTHER = 1\n', encoding='utf-8')
            services = _start_bound_server(directory / 'state.db', directory / 'runtime')
            services[0].evolution_runtime.flags.set_flag('code_studio_v1', True, reason='isolated UI test')
            backend = _HttpTestClient(services[0].server_port, services[0].host_token)
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root / '1.AXX'))
            web = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=web.serve_forever, daemon=True); thread.start()
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        page = browser.new_page(viewport={'width':1440,'height':1000})
                        def request(method, path, body=None):
                            code, data = backend.request(method, path, body)
                            if code >= 400:
                                raise RuntimeError(data.get('error', {}).get('message', 'HTTP ' + str(code)))
                            return data
                        page.expose_function('testBackend', request)
                        page.add_init_script("""window.__TAURI__={core:{invoke:async(name,args)=>{
                            if(name==='backend_request') {
                                if(args.path.startsWith('/axx-api/code/') || args.path.startsWith('/axx-api/agents/v1/flags')) return window.testBackend(args.method,args.path,args.body);
                                return {};
                            }
                            if(name==='native_status') return {native:true,backendReady:false,desktop:{workWidth:1920,workHeight:1080,spaceLeft:960,spaceRight:960,spaceAbove:540,spaceBelow:540}};
                            if(name==='desktop_layout') return {workWidth:1920,workHeight:1080,...args};
                            return null;
                        }},event:{listen:async()=>()=>{}}};""")
                        page.goto(f'http://127.0.0.1:{web.server_port}/Axx.html')
                        page.wait_for_function('window.Axx?.codeStudio')
                        page.evaluate("Axx.companion.openFeature('agent')")
                        page.get_by_role('button', name='Abrir Code Studio', exact=True).click()
                        page.wait_for_function('Axx.codeStudio.editor !== null', timeout=60000)
                        page.locator('[data-code=root]').fill(str(repo))
                        page.get_by_role('button', name='Abrir proyecto', exact=True).click()
                        page.locator('[data-code=browser]').get_by_role('button', name='hello.py', exact=True).click()
                        page.wait_for_function("Axx.codeStudio.editor.getValue().includes('VALUE = 1')")
                        page.evaluate('Axx.codeStudio.editor.focus()')
                        page.keyboard.press('Control+a'); page.keyboard.insert_text('VALUE = 2\n')
                        page.locator('[data-code=save]').click()
                        page.wait_for_function("document.querySelector('[data-code=status]').textContent.includes('guardado y verificado')")
                        self.assertEqual(source.read_bytes(), b'\xef\xbb\xbfVALUE = 2\r\n')
                        page.locator('[data-code=browser]').get_by_role('button', name='other.py', exact=True).click()
                        page.wait_for_function("Axx.codeStudio.editor.getValue().includes('OTHER')")
                        page.locator('[data-code=tabs]').get_by_role('tab', name='hello.py', exact=True).click()
                        page.evaluate("Axx.codeStudio.editor.setValue('VALUE = 3\\n')")
                        page.locator('[data-code=diff]').click()
                        page.wait_for_function('Axx.codeStudio.diffEditor?.getModel()?.original')
                        self.assertEqual(page.evaluate('Axx.codeStudio.diffEditor.getModel().original.getValue()'),'VALUE = 2\n')
                        self.assertEqual(page.evaluate('Axx.codeStudio.diffEditor.getModel().modified.getValue()'),'VALUE = 3\n')
                        source.write_bytes(b'\xef\xbb\xbfVALUE = 99\r\n')
                        page.locator('[data-code=save]').click()
                        page.wait_for_function("document.querySelector('[data-code=status]').textContent.includes('conflict')")
                        self.assertEqual(source.read_bytes(), b'\xef\xbb\xbfVALUE = 99\r\n')
                        self.assertEqual(page.evaluate('Axx.codeStudio.editor.getValue()'), 'VALUE = 3\n')
                        self.assertTrue(page.evaluate('[...Axx.codeStudio.tabs.values()].some(tab=>tab.dirty)'))
                        page.get_by_role('button', name='Cerrar Code Studio', exact=True).click()
                        page.get_by_role('button', name='Abrir Code Studio', exact=True).click()
                        self.assertEqual(page.evaluate('Axx.codeStudio.editor.getValue()'), 'VALUE = 3\n')
                        page.evaluate('Axx.codeStudio.flushDrafts()')
                        project_id = page.evaluate('[...Axx.codeStudio.tabs.values()].find(t=>t.path==="hello.py").project_id')
                        page.on('dialog', lambda dialog: dialog.accept())
                        page.reload()
                        page.wait_for_function('window.Axx?.codeStudio')
                        page.evaluate("Axx.companion.openFeature('agent')")
                        page.get_by_role('button', name='Abrir Code Studio', exact=True).click()
                        page.wait_for_function('document.querySelector("[data-code=recent]").options.length > 1')
                        page.locator('[data-code=recent]').select_option(project_id)
                        page.get_by_role('button',name='Abrir proyecto guardado',exact=True).click()
                        page.get_by_role('button',name='Recuperar hello.py',exact=True).click()
                        page.wait_for_function("Axx.codeStudio.editor.getValue()==='VALUE = 3\\n'")
                        self.assertEqual(source.read_bytes(),b'\xef\xbb\xbfVALUE = 99\r\n')
                        page.locator('[data-code=save]').click()
                        page.wait_for_function("document.querySelector('[data-code=status]').textContent.includes('conflict')")
                        self.assertEqual(source.read_bytes(),b'\xef\xbb\xbfVALUE = 99\r\n')
                        output = root / 'build/evolution-audit'; output.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(output / 'code-studio-browser.png'))
                    finally:
                        browser.close()
            finally:
                web.shutdown(); web.server_close(); thread.join(timeout=5)
                _stop_bound_server(*services)
