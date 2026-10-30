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

    def page(self, init=True, width=390, fail_first=False, permissions=None, conversation=None, reduced_motion='no-preference', fragment='', session_error=None):
        context = self.browser.new_context(viewport={'width': width, 'height': 780}, reduced_motion=reduced_motion)
        context.grant_permissions(['clipboard-read', 'clipboard-write'], origin='https://miniapp.fixture.test')
        self.addCleanup(context.close)
        page = context.new_page()
        fixture = {'calls': [], 'effects': set(), 'fail_first': fail_first, 'mutations': [], 'errors': {}, 'sessions': []}
        if session_error:
            fixture['errors']['/api/session'] = session_error
        state = {'worker_running': True, 'messages': 'not_verified', 'voice_notes': 'not_implemented',
                 'files': 'not_implemented', 'pc_commands': 'not_verified', 'private_calls': 'unavailable',
                 'permissions': permissions or {'conversation': True, 'voice_notes': False, 'files': False, 'pc_commands': True, 'private_calls': False},
                 'conversation': conversation or {'state': 'configured', 'reason_code': 'READY_FOR_REQUEST',
                     'provider': 'desktop_selected', 'model': '<img src=x onerror=alert(1)>', 'message': 'Selección configurada'},
                 'connection': {'core_bound': True, 'account_running': False, 'bot_running': True, 'checked_at': 1},
                 'observed_at': 1, 'session_expires_at': 2000000000}
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
            if path == '/api/session':
                fixture['sessions'].append(json.loads(request.post_data))
            if path in fixture['errors']:
                if fixture['errors'][path] == 'network':
                    request_route.abort('failed')
                else:
                    status, code = fixture['errors'][path]
                    request_route.fulfill(status=status, json={'error': code})
                return
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
            elif path == '/api/history':
                request_route.fulfill(status=200, json={'messages': [{'id': 'history-1', 'role': 'assistant',
                    'text': '<img src=x onerror=alert(1)> historial', 'status': 'complete', 'at': 1}], 'has_more': False})
            elif path == '/api/activity':
                request_route.fulfill(status=200, json={'items': [{'id': 'f27038d4-1e3a-41d1-8085-15f51c59ff70',
                    'state': 'awaiting_approval', 'created_at': 1, 'command_id': '<img src=x onerror=alert(1)>',
                    'can_cancel': True, 'postconditions_passed': False}]})
            elif path == '/api/cancel':
                fixture['mutations'].append((path, json.loads(request.post_data)))
                request_route.fulfill(status=200, json={'state': 'cancel_requested'})
            elif path == '/api/chat':
                body = json.loads(request.post_data)
                fixture['mutations'].append((path, body))
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
        page.goto('https://miniapp.fixture.test/' + fragment)
        return page, fixture

    def test_without_init_data_composer_is_disabled(self):
        page, fixture = self.page(init=False)
        self.assertTrue(page.locator('#draft').is_disabled())
        self.assertTrue(page.locator('#send').is_disabled())
        self.assertIn('Abre esta app', page.locator('#connection').inner_text())
        self.assertEqual(fixture['calls'], [])

    def test_navigation_status_diagnostics_and_escaped_api_text(self):
        page, _ = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        self.assertTrue(page.locator('#home').is_visible())
        page.locator('#home summary').click()
        self.assertIn('Deja Axx abierto', page.locator('#home details').inner_text())
        page.get_by_role('button', name='Ajustes', exact=True).click()
        self.assertTrue(page.locator('#status').is_visible())
        self.assertEqual(page.get_by_role('button', name='Ajustes', exact=True).get_attribute('aria-current'), 'page')
        self.assertIn('Pendiente de prueba', page.locator('#capabilities').inner_text())
        self.assertIn('Todavía no implementado', page.locator('#capabilities').inner_text())
        page.locator('#status summary').click()
        page.locator('#copy-diagnostics').click()
        copied = page.evaluate('navigator.clipboard.readText()')
        self.assertNotIn('fixture-csrf', copied)
        self.assertNotIn('fixture-data', copied)
        self.assertNotIn('fixture-token', copied)
        page.get_by_role('button', name='Chat', exact=True).click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('historial')")
        page.locator('#draft').fill('Hola')
        page.locator('#send').click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('respuesta')")
        self.assertIn('<img src=x', page.locator('#messages').inner_text())
        page.get_by_role('button', name='Actividad', exact=True).click()
        page.wait_for_function("() => document.querySelector('#activity-list').textContent.includes('img')")
        self.assertEqual(page.locator('main img, main svg').count(), 0)
        page.evaluate("""() => {const banner=document.createElement('p'); banner.textContent='PREVISUALIZACIÓN SIMULADA'; banner.id='fixture-banner'; document.querySelector('main').prepend(banner);} """)
        target = ROOT / 'build' / 'telegram-miniapp-v2-preview.png'
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=True)

    def test_failed_send_preserves_draft_and_reuses_operation_id_after_reload(self):
        page, fixture = self.page(fail_first=True)
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.get_by_role('button', name='Chat', exact=True).click()
        page.locator('#draft').fill('Una solicitud de prueba')
        page.locator('#send').click()
        page.wait_for_selector('#recover:not([hidden])')
        self.assertEqual(page.locator('#draft').input_value(), 'Una solicitud de prueba')
        self.assertTrue(page.locator('#send').is_disabled())
        page.reload()
        page.wait_for_selector('#recover:not([hidden]):not([disabled])', state='attached')
        page.get_by_role('button', name='Chat', exact=True).click()
        self.assertEqual(page.locator('#draft').input_value(), 'Una solicitud de prueba')
        page.locator('#recover').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.includes('Estado consultado')")
        self.assertEqual(len(fixture['calls']), 1)
        page.locator('#retry').click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('respuesta')")
        self.assertEqual(len(fixture['calls']), 2)
        self.assertEqual(fixture['calls'][0]['request_id'], fixture['calls'][1]['request_id'])
        self.assertEqual(len(fixture['effects']), 1)
        self.assertEqual(page.locator('#draft').input_value(), '')

    def test_permissions_blocked_provider_and_cancellation_contract(self):
        denied = {'conversation': False, 'voice_notes': False, 'files': False, 'pc_commands': False, 'private_calls': False}
        blocked = {'state': 'blocked', 'reason_code': 'REMOTE_PROVIDER_ISOLATION_REQUIRED',
                   'provider': 'desktop_selected', 'model': 'fixture', 'message': 'Proveedor remoto bloqueado'}
        page, _ = self.page(permissions=denied, conversation=blocked)
        page.wait_for_function("() => document.querySelector('#connection').textContent.includes('Axx está disponible')")
        page.get_by_role('button', name='Chat', exact=True).click()
        self.assertTrue(page.locator('#draft').is_disabled())
        self.assertIn('bloqueado', page.locator('#provider-notice').inner_text())
        page.get_by_role('button', name='Ajustes', exact=True).click()
        self.assertIn('No concedido', page.locator('#permissions').inner_text())
        page, fixture = self.page()
        page.get_by_role('button', name='Actividad', exact=True).click()
        page.get_by_role('button', name='Solicitar cancelación').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.includes('cancelación enviada')")
        self.assertEqual(fixture['mutations'], [('/api/cancel', {'operation_id': 'f27038d4-1e3a-41d1-8085-15f51c59ff70', 'csrf': 'fixture-csrf'})])

    def test_session_denial_and_network_error_are_distinguishable(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        fixture['errors']['/api/state'] = 'network'
        page.locator('#refresh').click()
        page.wait_for_function("() => document.querySelector('#connection').textContent.includes('Sin conexión')")
        self.assertTrue(page.locator('#send').is_enabled())
        fixture['errors']['/api/state'] = (403, 'PERMISSION_DENIED')
        page.locator('#refresh').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.toLowerCase().includes('permiso')")
        self.assertTrue(page.locator('#send').is_enabled())
        fixture['errors']['/api/state'] = (401, 'SESSION_EXPIRED')
        page.locator('#refresh').click()
        page.wait_for_function("() => document.querySelector('#send').disabled")
        self.assertIn('sesión', page.locator('#connection').inner_text().lower())

    def test_pairing_fragment_sent_once_and_cleared_only_after_success(self):
        pairing = 'axx_' + 'x' * 43
        page, fixture = self.page(fragment='#pairing=' + pairing)
        page.wait_for_selector('#send:not([disabled])', state='attached')
        self.assertEqual(fixture['sessions'][0], {'init_data': 'fixture-data', 'pairing_token': pairing})
        self.assertEqual(page.evaluate('location.hash'), '')
        page, fixture = self.page(fragment='#pairing=' + pairing, session_error=(403, 'PAIRING_REQUIRED'))
        page.wait_for_function("() => document.querySelector('#connection').textContent.includes('QR')")
        self.assertEqual(fixture['sessions'][0]['pairing_token'], pairing)
        self.assertEqual(page.evaluate('location.hash'), '#pairing=' + pairing)

    def test_viewports_text_scaling_keyboard_and_reduced_motion(self):
        for width in (339, 390, 768):
            with self.subTest(width=width):
                page, _ = self.page(width=width, reduced_motion='reduce')
                page.wait_for_selector('#send:not([disabled])', state='attached')
                page.evaluate("document.documentElement.style.fontSize='170%'")
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                page.keyboard.press('Tab')
                self.assertEqual(page.evaluate('document.activeElement.id'), 'refresh')
                page.keyboard.press('Tab')
                self.assertEqual(page.evaluate('document.activeElement.dataset.pane'), 'home')
                page.keyboard.press('Tab')
                page.keyboard.press('Enter')
                self.assertTrue(page.locator('#chat').is_visible())
                self.assertTrue(page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"))
                for name in ('Actividad', 'Ajustes', 'Inicio'):
                    page.get_by_role('button', name=name, exact=True).click()
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)


if __name__ == '__main__':
    unittest.main()
