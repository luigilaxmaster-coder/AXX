"""Offline Mini App browser fixtures; no Telegram account or real network access."""
import json
import os
from pathlib import Path
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'backend' / 'telegram'
EDGE = Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'


@unittest.skipUnless(sync_playwright and EDGE.is_file(), 'requires Playwright and Microsoft Edge')
class TelegramWebAppUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=str(EDGE), headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def page(self, init=True, width=390, fail_first=False):
        context = self.browser.new_context(viewport={'width': width, 'height': 780})
        self.addCleanup(context.close)
        page = context.new_page()
        fixture = {'calls': [], 'effects': set(), 'fail_first': fail_first}
        state = {'worker_running': True, 'messages': 'not_verified', 'voice_notes': 'not_implemented',
                 'files': 'not_implemented', 'pc_commands': 'not_verified', 'private_calls': 'unavailable'}
        def route(request_route):
            request = request_route.request
            url = request.url
            if url == 'https://telegram.org/js/telegram-web-app.js':
                sdk = "window.Telegram={WebApp:{initData:" + json.dumps('fixture-data' if init else '') + ",ready(){},expand(){}}};"
                request_route.fulfill(status=200, content_type='application/javascript', body=sdk)
                return
            prefix = 'https://miniapp.fixture.test'
            if not url.startswith(prefix + '/'):
                request_route.abort()
                return
            path = url[len(prefix):]
            names = {'/': ('webapp.html', 'text/html'), '/app.css': ('webapp.css', 'text/css'),
                     '/app.js': ('webapp.js', 'application/javascript')}
            if path in names:
                file, mime = names[path]
                request_route.fulfill(status=200, content_type=mime, body=(ASSETS / file).read_text(encoding='utf-8'))
            elif path in ('/desktop-avatar.js', '/avatar-renderer.js'):
                request_route.fulfill(status=200, content_type='application/javascript', body='')
            elif path == '/api/session':
                request_route.fulfill(status=200, json={'csrf': 'fixture-csrf'})
            elif path == '/api/state':
                request_route.fulfill(status=200, json=state)
            elif path == '/api/chat':
                body = json.loads(request.post_data)
                fixture['calls'].append(body)
                fixture['effects'].add(body['request_id'])
                if fixture['fail_first']:
                    fixture['fail_first'] = False
                    request_route.abort('failed')
                else:
                    request_route.fulfill(status=200, json={'state': 'succeeded', 'text': '<img src=x onerror=alert(1)> respuesta'})
            else:
                request_route.fulfill(status=404, json={'error': 'fixture route missing'})
        page.route('**/*', route)
        page.goto('https://miniapp.fixture.test/')
        return page, fixture

    def test_without_init_data_composer_is_disabled(self):
        page, fixture = self.page(init=False)
        self.assertTrue(page.locator('#draft').is_disabled())
        self.assertTrue(page.locator('#send').is_disabled())
        self.assertIn('Abre esta app', page.locator('#connection').inner_text())
        self.assertEqual(fixture['calls'], [])

    def test_capabilities_navigation_and_escaped_response(self):
        page, _ = self.page()
        page.wait_for_selector('#send:not([disabled])')
        page.get_by_role('button', name='Estado', exact=True).click()
        self.assertTrue(page.locator('#status').is_visible())
        self.assertEqual(page.get_by_role('button', name='Estado', exact=True).get_attribute('aria-pressed'), 'true')
        self.assertIn('Pendiente de prueba', page.locator('#capabilities').inner_text())
        self.assertIn('Todavía no implementado', page.locator('#capabilities').inner_text())
        page.get_by_role('button', name='Conversación', exact=True).click()
        page.locator('#draft').fill('Hola')
        page.locator('#send').click()
        page.wait_for_selector('#messages .assistant')
        self.assertIn('<img src=x', page.locator('#messages .assistant').inner_text())
        self.assertEqual(page.locator('#messages img').count(), 0)
        target = ROOT / 'build' / 'telegram-miniapp-preview.png'
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=True)

    def test_failed_send_preserves_draft_and_reuses_operation_id_after_reload(self):
        page, fixture = self.page(fail_first=True)
        page.wait_for_selector('#send:not([disabled])')
        page.locator('#draft').fill('Una solicitud de prueba')
        page.locator('#send').click()
        page.wait_for_selector('#recover:not([hidden])')
        self.assertEqual(page.locator('#draft').input_value(), 'Una solicitud de prueba')
        self.assertTrue(page.locator('#send').is_disabled())
        page.reload()
        page.wait_for_selector('#recover:not([hidden]):not([disabled])')
        self.assertEqual(page.locator('#draft').input_value(), 'Una solicitud de prueba')
        page.locator('#recover').click()
        page.wait_for_selector('#messages .assistant')
        self.assertEqual(len(fixture['calls']), 2)
        self.assertEqual(fixture['calls'][0]['request_id'], fixture['calls'][1]['request_id'])
        self.assertEqual(len(fixture['effects']), 1)
        self.assertEqual(page.locator('#draft').input_value(), '')

    def test_small_viewports_and_keyboard_navigation(self):
        for width in (339, 390):
            with self.subTest(width=width):
                page, _ = self.page(width=width)
                page.wait_for_selector('#send:not([disabled])')
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                page.keyboard.press('Tab')
                self.assertEqual(page.evaluate('document.activeElement.id'), 'refresh')
                page.keyboard.press('Tab')
                self.assertEqual(page.evaluate('document.activeElement.dataset.pane'), 'chat')
                page.keyboard.press('Tab')
                page.keyboard.press('Enter')
                self.assertTrue(page.locator('#status').is_visible())


if __name__ == '__main__':
    unittest.main()
