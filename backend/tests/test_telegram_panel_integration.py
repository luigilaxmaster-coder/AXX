"""Actual Axx renderer with simulated local Telegram IPC; no installed app."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[2]
EDGE = Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(sync_playwright and EDGE.is_file(), 'requires Playwright and Microsoft Edge')
class TelegramPanelIntegrationTests(unittest.TestCase):
    def test_real_renderer_registers_searches_and_opens_telegram(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(EDGE), headless=True)
                try:
                    page = browser.new_page(viewport={'width': 1280, 'height': 900})
                    prefix = f'http://127.0.0.1:{server.server_port}/'
                    page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(prefix) else route.abort())
                    page.goto(prefix + '1.AXX/Axx.html', wait_until='domcontentloaded')
                    page.wait_for_function('() => Boolean(window.Axx?.companion && Axx.flow?.renderLibrary)', timeout=30000)
                    page.evaluate('''() => {
                        Axx.isNative = () => true;
                        window.telegramFixtureCalls = [];
                        Axx.backendRequest = async (method, path, body) => {
                            telegramFixtureCalls.push({method,path});
                            if (path === '/axx-api/telegram/desktop/status') return {
                                app_configured:true,
                                account:{configured:true,enabled:true,grants:{conversation:true}},
                                bot:{configured:true,enabled:true,username:'FixtureBot',public_url:'https://fixture.example.org/'},qr:{state:'idle'}};
                            if (path === '/axx-api/telegram/pairing/status') return {bindings:[]};
                            if (path === '/axx-api/telegram/status') return {worker_running:false};
                            return {};
                        };
                    }''')
                    page.add_script_tag(path=str(ROOT / '1.AXX' / 'scripts' / 'telegram-panel.js'))
                    self.assertTrue(page.evaluate("Axx.FEATURES.some(f => f.id === 'telegram')"))
                    page.evaluate("Axx.flow.nav.catalog('assist'); Axx.flow.render(); Axx.flow.renderLibrary();")
                    self.assertEqual(page.locator('#flow-grid [data-tool="telegram"]').count(), 1)
                    page.evaluate("document.querySelector('#flow-search').value='Telegram'; Axx.flow.renderLibrary()")
                    self.assertEqual(page.locator('#flow-grid [data-tool="telegram"]').count(), 1)
                    page.evaluate("document.querySelector('#flow-grid [data-tool=telegram]').click()")
                    page.wait_for_function("() => Axx.companion.currentFeature === 'telegram' && document.querySelector('#panel').dataset.view === 'settings'", timeout=10000)
                    self.assertTrue(page.locator('#telegram-panel').is_visible())
                    page.wait_for_function("() => telegramFixtureCalls.some(c => c.path === '/axx-api/telegram/desktop/status')")
                    page.wait_for_function("() => document.querySelector('#tg-account-status').textContent.includes('guardada')")
                    page.evaluate("""() => {const e=document.createElement('div'); e.textContent='PREVISUALIZACIÓN DE FUENTE · IPC SIMULADO'; e.style.cssText='position:fixed;top:0;left:0;z-index:99999;background:#132436;color:white;padding:8px'; document.body.append(e)}""")
                    target = ROOT / 'build' / 'telegram-desktop-real-renderer-preview.png'
                    target.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(target))
                    page.set_viewport_size({'width': 500, 'height': 850})
                    page.evaluate("document.documentElement.style.zoom='1.7'")
                    page.screenshot(path=str(ROOT / 'build' / 'telegram-desktop-real-renderer-narrow-170-preview.png'))
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
