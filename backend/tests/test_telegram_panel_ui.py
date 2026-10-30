"""Offline browser fixture for the actual native Telegram panel script."""
import json
import os
from pathlib import Path
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[2]
EDGE = Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
SCRIPT = (ROOT / '1.AXX' / 'scripts' / 'telegram-panel.js').read_text(encoding='utf-8')
SVG = 'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjwvc3ZnPg=='
ID = 'f27038d4-1e3a-41d1-8085-15f51c59ff70'


@unittest.skipUnless(sync_playwright and EDGE.is_file(), 'requires Playwright and Microsoft Edge')
class TelegramPanelUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=str(EDGE), headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def page(self, *, native=True, configured=True):
        context = self.browser.new_context(viewport={'width': 1100, 'height': 850})
        self.addCleanup(context.close)
        page = context.new_page()
        fixture = {'calls': [], 'unexpected': []}
        account = {'configured': configured, 'enabled': configured,
                   'grants': {'conversation': True, 'voice_notes': False, 'files': False, 'pc_commands': False, 'private_calls': False}}
        state = {'app_configured': True, 'account': account, 'bot': {'configured': True, 'enabled': True, 'username': 'FixtureBot', 'public_url': 'https://fixture.example.org/'},
                 'qr': {'state': 'idle'}, 'bot_job': {'state': 'idle'}}
        routes = {'/axx-api/telegram/desktop/status': state,
                  '/axx-api/telegram/pairing/status': {'bindings': [{'id': ID}]},
                  '/axx-api/telegram/status': {'worker_running': True}}
        html = '''<!doctype html><html><head><style>body{background:#111d2b;color:#eef;font:16px sans-serif}button,input{font:inherit;margin:5px}#telegram-panel{max-width:720px;margin:20px auto;padding:20px;background:#26364a}label{display:block}#tg-permissions{display:grid;gap:3px} [hidden]{display:none!important}</style></head><body><div id="fixture-banner">PREVISUALIZACIÓN SIMULADA</div><div id="panel" data-view="settings"><div id="view-settings"></div></div><input id="flow-search"><div id="flow-grid"></div><div id="dock"></div><script src="/stub.js"></script><script src="/panel.js"></script></body></html>'''
        stub = '''window.Axx={FEATURES:[],isNative:()=>NATIVE,companion:{openFeature(id){window.opened=id;return id}},flow:{nav:{category:'assist'},select(id){Axx.companion.openFeature(id)},renderLibrary(){const query=document.querySelector('#flow-search').value.toLowerCase();document.querySelector('#flow-grid').replaceChildren();if(query)for(const f of Axx.FEATURES.filter(x=>(x.title+' '+x.description).toLowerCase().includes(query))){const b=document.createElement('button');b.dataset.tool=f.id;b.textContent=f.title;b.onclick=()=>this.select(f.id);document.querySelector('#flow-grid').append(b)}}},backendRequest:async(method,path,body)=>{const r=await fetch('/ipc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,path,body})});if(!r.ok)throw Error('fixture failure');return await r.json()}};'''.replace('NATIVE', 'true' if native else 'false')
        def route(handler):
            req = handler.request
            if req.url == 'https://desktop.fixture.test/':
                handler.fulfill(status=200, content_type='text/html', body=html)
            elif req.url == 'https://desktop.fixture.test/stub.js':
                handler.fulfill(status=200, content_type='application/javascript', body=stub)
            elif req.url == 'https://desktop.fixture.test/panel.js':
                handler.fulfill(status=200, content_type='application/javascript', body=SCRIPT)
            elif req.url == 'https://desktop.fixture.test/ipc':
                call = json.loads(req.post_data)
                fixture['calls'].append(call)
                if call['method'] == 'GET':
                    result = routes.get(call['path'], {})
                elif call['path'].endswith('/start_qr'):
                    state['qr'] = {'state': 'waiting_qr', 'image': SVG, 'expires_at': __import__('time').time() + 60}
                    result = {'state': 'starting'}
                elif call['path'].endswith('/pairing/create'):
                    result = {'qr_svg_base64': SVG, 'expires_at': __import__('time').time() + 1}
                else:
                    result = {'state': 'saved'}
                handler.fulfill(status=200, json=result)
            else:
                fixture['unexpected'].append(req.url)
                handler.abort()
        page.route('**/*', route)
        page.goto('https://desktop.fixture.test/')
        return page, fixture, state

    def test_registration_search_and_existing_account(self):
        page, fixture, _ = self.page()
        self.assertEqual(page.locator('#telegram-panel details[open]').count(), 0)
        page.evaluate('Axx.flow.renderLibrary()')
        self.assertEqual(page.locator('[data-tool="telegram"]').count(), 1)
        page.locator('#flow-search').fill('Telegram')
        page.evaluate('Axx.flow.renderLibrary()')
        page.locator('[data-tool="telegram"]').click()
        page.wait_for_function("() => document.querySelector('#tg-account-status').textContent.includes('guardada')")
        self.assertTrue(page.locator('#tg-start-qr').is_hidden())
        self.assertTrue(page.locator('#tg-password-section').is_hidden())
        self.assertEqual(page.evaluate('window.opened'), 'telegram')
        self.assertEqual(fixture['unexpected'], [])
        target = ROOT / 'build' / 'telegram-desktop-wizard-preview.png'
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=True)

    def test_login_qr_password_and_secret_inputs_do_not_persist(self):
        page, fixture, state = self.page(configured=False)
        page.evaluate('Axx.telegramPanel.open()')
        page.wait_for_function("() => document.querySelector('#tg-account-status').textContent.includes('no')")
        page.locator('#tg-start-qr').click()
        page.wait_for_function("() => !document.querySelector('#tg-login-qr').hidden")
        self.assertIn('restantes', page.locator('#tg-login-expiry').inner_text())
        self.assertTrue(page.locator('#tg-password-section').is_hidden())
        state['qr'] = {'state': 'password_required'}
        page.evaluate('Axx.telegramPanel.refresh()')
        page.wait_for_selector('#tg-password-section:not([hidden])')
        page.locator('#tg-password').fill('fixture-password')
        page.locator('#tg-submit-password').click()
        page.wait_for_function("() => document.querySelector('#tg-password').value === ''")
        page.wait_for_function("() => !document.querySelector('#telegram-panel').hasAttribute('aria-busy')")
        page.locator('details summary').click()
        page.locator('#tg-api-id').fill('12345')
        page.locator('#tg-api-hash').fill('fixture-api-hash')
        page.locator('#tg-owner-id').fill('22')
        page.locator('#tg-save-app').click()
        page.wait_for_function("() => document.querySelector('#tg-api-hash').value === ''")
        page.wait_for_function("() => !document.querySelector('#telegram-panel').hasAttribute('aria-busy')")
        page.locator('#tg-bot-token').fill('fixture-bot-token')
        page.locator('#tg-save-bot').click()
        page.wait_for_function("() => document.querySelector('#tg-bot-token').value === ''")
        page.wait_for_function("() => !document.querySelector('#telegram-panel').hasAttribute('aria-busy')")
        submitted = [call['path'] for call in fixture['calls'] if call['method'] == 'POST']
        for path in ('/desktop/password', '/desktop/configure_app', '/desktop/configure_bot'):
            self.assertTrue(any(item.endswith(path) for item in submitted))
        storage = page.evaluate('JSON.stringify(localStorage)')
        for secret in ('fixture-password', 'fixture-api-hash', 'fixture-bot-token'):
            self.assertNotIn(secret, storage)
        self.assertEqual(fixture['unexpected'], [])

    def test_dirty_permissions_survive_refresh_and_pairing_expiry_revokes_owned_id(self):
        page, fixture, _ = self.page()
        page.evaluate('Axx.telegramPanel.open()')
        page.wait_for_selector('#tg-pair-list button')
        page.locator('[data-tg-grant="pc_commands"]').check()
        page.evaluate('Axx.telegramPanel.refresh()')
        page.wait_for_timeout(100)
        self.assertTrue(page.locator('[data-tg-grant="pc_commands"]').is_checked())
        page.locator('#tg-pair-list button').click()
        page.wait_for_function("() => document.querySelector('#tg-panel-status').textContent.includes('desvinculado')")
        calls = [c for c in fixture['calls'] if c['path'].endswith('/pairing/revoke')]
        self.assertEqual(calls[0]['body'], {'binding_id': ID})
        page.locator('#tg-pair-create').click()
        page.wait_for_selector('#tg-pair-qr:not([hidden])')
        page.wait_for_function("() => document.querySelector('#tg-pair-qr').hidden", timeout=4000)
        self.assertNotIn('pairing=', page.locator('#tg-panel-status').inner_text())

    def test_pairing_qr_requires_enabled_account_bot_and_public_url(self):
        page, fixture, state = self.page()
        page.evaluate('Axx.telegramPanel.open()')
        page.wait_for_selector('#tg-pair-list button')
        cases = [('account', 'configured', False), ('account', 'enabled', False),
                 ('bot', 'configured', False), ('bot', 'enabled', False), ('bot', 'public_url', '')]
        for group, key, value in cases:
            with self.subTest(group=group, key=key):
                original = state[group][key]
                state[group][key] = value
                page.evaluate('Axx.telegramPanel.refresh()')
                page.wait_for_function("() => document.querySelector('#tg-pair-create').disabled")
                page.evaluate("document.querySelector('#tg-pair-create').click()")
                self.assertFalse(any(call['path'].endswith('/pairing/create') for call in fixture['calls']))
                state[group][key] = original
                page.evaluate('Axx.telegramPanel.refresh()')
                page.wait_for_function("() => !document.querySelector('#tg-pair-create').disabled")

    def test_nonnative_does_not_install_panel(self):
        page, fixture, _ = self.page(native=False)
        self.assertEqual(page.locator('#telegram-panel').count(), 0)
        self.assertEqual(fixture['calls'], [])
        self.assertEqual(fixture['unexpected'], [])


if __name__ == '__main__':
    unittest.main()
