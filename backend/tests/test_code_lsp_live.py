"""Live LSP over stdio through the real AXX handler (controlled fixture server), crash fallback and confinement."""
from pathlib import Path
import sys
import tempfile
import unittest

from backend.code_studio.language_servers import _works
from backend.tests.test_acts_inference import _Server

FIXTURE = [sys.executable, '-I', str(Path(__file__).with_name('lsp_fixture_server.py'))]


class LiveLspTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        (root / 'proj').mkdir()
        (root / 'proj' / 'main.py').write_text('x = 1\n', encoding='utf-8')
        self.srv = _Server(root, [])
        self.srv.rt.flags.set_flag('code_studio_v1', True, reason='lsp test')
        self.srv.api.request('POST', '/axx-api/code/v1/projects/register', {'project_id': 'proj', 'project_root': str(root / 'proj')})
        self.lsp = self.srv.rt.code_lsp

    def tearDown(self):
        self.srv.close()
        self.tmp.cleanup()

    def sync(self, content, path='main.py'):
        return self.srv.api.request('POST', '/axx-api/code/v1/lsp/sync',
                                    {'project_id': 'proj', 'path': path, 'language': 'python', 'content': content})

    def test_stdio_server_gives_live_diagnostics_and_completion_then_degrades_on_crash(self):
        self.assertFalse(_works('axx-no-such-language-server'))
        self.lsp.commands['pylsp'] = FIXTURE
        status = self.srv.api.request('GET', '/axx-api/code/v1/lsp/status')[1]
        self.assertTrue(status['servers']['python']['installed'])

        code, res = self.sync('x = 1\ny = BAD_TOKEN\n')
        self.assertEqual(code, 200, res)
        self.assertEqual((res['lsp_status'], res['binary']), ('live', 'pylsp'))
        self.assertEqual([d['range']['start']['line'] for d in res['diagnostics']], [1])  # server answered our config reply
        code, res = self.sync('x = 1\n')  # didChange with the full buffer clears it
        self.assertEqual((code, res['diagnostics']), (200, []))
        code, comp = self.srv.api.request('POST', '/axx-api/code/v1/lsp/completion',
                                          {'project_id': 'proj', 'path': 'main.py', 'language': 'python', 'line': 0, 'character': 2})
        self.assertEqual((code, [i['label'] for i in comp['items']]), (200, ['axx_fixture_item']))
        def q(method):
            return self.srv.api.request('POST', '/axx-api/code/v1/lsp/query', {'project_id': 'proj', 'path': 'main.py',
                                        'language': 'python', 'method': method, 'line': 0, 'character': 0})
        self.assertEqual(q('hover')[1]['result'], {'markdown': '**x**: int'})
        self.assertEqual([loc['path'] for loc in q('definition')[1]['result']], ['main.py'])  # outside-root location dropped
        self.assertEqual(len(q('references')[1]['result']), 1)
        self.assertEqual(q('rename')[0], 400)  # only hover/definition/references are forwarded

        self.assertGreaterEqual(self.sync('x = 1\n', path='../outside.py')[0], 400)  # never leaves the project root
        self.lsp.processes[('proj', 'python')].proc.kill()  # crash: the editor keeps working on the AST fallback
        self.lsp.processes[('proj', 'python')].proc.wait(5)
        self.lsp.commands.pop('pylsp')
        # The optional real pylsp may be installed on the QA machine. This case
        # tests an unavailable provider after the controlled process crashes.
        from unittest.mock import patch
        with patch('backend.code_studio.language_servers._works',return_value=False):
            code, res = self.sync('def broken(:\n')
        self.assertEqual((code, res['lsp_status']), (200, 'degraded_syntax_only'), res)
        self.assertTrue(res['editor_usable'])


    def test_monaco_shows_live_markers_and_suggestions(self):
        import functools
        import http.server
        from playwright.sync_api import sync_playwright
        from backend.tests.test_acts_ui import ROOT, open_axx, serve
        self.lsp.commands['pylsp'] = FIXTURE
        web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = open_axx(browser, self.srv, web)
                    page.evaluate("Axx.companion.openFeature('agent')")
                    page.get_by_role('button', name='Abrir Code Studio', exact=True).click()
                    page.wait_for_function('Axx.codeStudio.editor !== null', timeout=60000)
                    page.locator('[data-code=root]').fill(str(Path(self.tmp.name) / 'proj'))
                    page.get_by_role('button', name='Abrir proyecto', exact=True).click()
                    page.locator('[data-code=browser]').get_by_role('button', name='main.py', exact=True).click()
                    page.wait_for_function("document.querySelector('[data-code=draft-status]').textContent.includes('LSP pylsp')")
                    page.evaluate(r"Axx.codeStudio.editor.setValue('x = 1\ny = BAD_TOKEN\n')")
                    page.wait_for_function("document.querySelector('.squiggly-error') !== null", timeout=15000)
                    page.evaluate("Axx.codeStudio.editor.setPosition({lineNumber:1,column:5}); Axx.codeStudio.editor.focus();"
                                  "Axx.codeStudio.editor.trigger('test','editor.action.triggerSuggest',{})")
                    page.wait_for_selector('.suggest-widget .monaco-list-row:has-text("axx_fixture_item")', timeout=15000)
                finally:
                    browser.close()
        finally:
            web.shutdown(); web.server_close()


if __name__ == '__main__':
    unittest.main()
