"""Real HTML in Edge with catalog/IPC fixtures; no Windows input is delivered."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from backend import application_catalog


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@unittest.skipUnless(os.environ.get('AXX_TEST_BROWSER_NATIVE') == '1', 'requires isolated native Edge')
class ApplicationCatalogUiTests(unittest.TestCase):
    def test_menu_filter_guides_and_exact_command_preparation(self):
        from playwright.sync_api import sync_playwright

        root = Path(__file__).resolve().parents[2]
        edge = Path(os.environ['PROGRAMFILES(X86)'])/'Microsoft/Edge/Application/msedge.exe'
        arbitrary = {'name': 'Mi herramienta local', 'app_id': 'TestVendor.LocalTool_AbC!App'}
        untrusted = {'name': '<img src=x onerror="window.catalogInjected=true">',
                     'app_id': 'TestVendor.UntrustedName_AbC!App'}
        with patch.object(application_catalog, 'installed_apps', return_value=[
                {'name': 'Google Chrome', 'app_id': 'test-only-observed-Chrome'}, arbitrary, untrusted]):
            fixture = application_catalog.installed_catalog()
        telegram = next(profile for profile in fixture['profiles'] if profile['id'] == 'telegram')
        telegram['instructions'].append('<svg onload="window.catalogInjected=true">')
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(_QuietHandler, directory=str(root)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(edge), headless=True)
                try:
                    page = browser.new_page(viewport={'width': 1280, 'height': 900})
                    page.add_init_script('''window.__TAURI__ = {core: {invoke: async (name, args) => {
                        const desktop = {workWidth:1280,workHeight:900,spaceLeft:760,spaceRight:520,
                            spaceAbove:450,spaceBelow:450};
                        if (name === 'native_status') return {native:true,backendReady:false,desktop};
                        if (name === 'desktop_layout') return {...desktop,...args};
                        return null;
                    }},event:{listen:async()=>()=>{}}};''')
                    page.goto(f'http://127.0.0.1:{server.server_port}/1.AXX/Axx.html')
                    page.wait_for_function('() => Boolean(window.Axx?.applicationCatalog && Axx.resident?.firstFrame)')
                    page.evaluate('''catalog => {
                        window.appFixture = {catalog, calls: [], prepared: [], opened: 0};
                        Axx.isNative = () => true;
                        Axx.backendRequest = async (method, path, body) => {
                            appFixture.calls.push({method, path, body});
                            if (method === 'GET' && path === '/axx-api/apps/catalog')
                                return structuredClone(appFixture.catalog);
                            // Existing native startup polls and three state sync writes are unrelated
                            // to catalog actions. No command/action endpoint is accepted by this fixture.
                            if (method === 'GET' || (method === 'POST' &&
                                ['/axx-api/connect/ui/claim','/axx-api/chat/migrate',
                                 '/axx-api/mobile/control/material'].includes(path))) return {};
                            throw new Error('Unexpected action request');
                        };
                        Axx.commandLibrary.prepare = async (id, inputs, source) => {
                            appFixture.prepared.push({id, inputs: structuredClone(inputs), source});
                            return 'Preparación registrada por prueba de interfaz';
                        };
                        Axx.commandLibrary.open = () => { appFixture.opened++; };
                        Axx.flow.nav.catalog('create');
                        Axx.flow.render();
                    }''', fixture)
                    page.locator('[data-group="work"]').click()
                    page.locator('[data-tool="applications"]').click()
                    page.wait_for_function('''() => document.getElementById('app-catalog-status')
                        .textContent.includes('48 perfiles')''')
                    self.assertEqual(page.evaluate('Axx.companion.currentFeature'), 'applications')
                    self.assertTrue(page.locator('#application-catalog').is_visible())
                    self.assertEqual(page.evaluate('appFixture.prepared'), [])
                    self.assertEqual(page.locator('#app-catalog-list img, #app-catalog-list svg').count(), 0)
                    self.assertFalse(page.evaluate('Boolean(window.catalogInjected)'))
                    self.assertIn(untrusted['name'], page.locator('#app-catalog-list').text_content())

                    before_refresh = page.evaluate('''appFixture.calls.filter(call =>
                        call.path === '/axx-api/apps/catalog').length''')
                    page.locator('#app-catalog-refresh').click()
                    page.wait_for_function('''previous => appFixture.calls.filter(call =>
                        call.path === '/axx-api/apps/catalog').length > previous''', arg=before_refresh)
                    self.assertEqual(page.evaluate('appFixture.prepared'), [])
                    page.locator('#app-catalog-query').fill('Telegram')
                    self.assertEqual(page.locator('#app-catalog-list > details').count(), 2)
                    telegram_row = page.locator('#app-catalog-list > details').first
                    telegram_row.locator(':scope > summary').click()
                    guide = telegram_row.locator(':scope > details').filter(
                        has=page.locator('summary', has_text='Enviar un mensaje revisado'))
                    self.assertEqual(guide.count(), 1)
                    guide.locator(':scope > summary').click()
                    self.assertEqual(guide.locator('button').count(), 0)
                    self.assertIn('autorización', guide.text_content())
                    self.assertEqual(page.evaluate('appFixture.prepared'), [])
                    self.assertEqual(page.locator('#app-catalog-list svg').count(), 0)

                    page.locator('#app-catalog-query').fill('Chrome')
                    chrome_row = page.locator('#app-catalog-list > details').first
                    chrome_row.locator(':scope > summary').click()
                    navigate = chrome_row.locator(':scope > details').filter(
                        has=page.locator('summary', has_text='Navegar a una URL indicada'))
                    navigate.locator(':scope > summary').click()
                    navigate.locator('input[type="url"]').fill('https://example.test/document?q=checked')
                    navigate.get_by_role('button', name='Preparar Navegar a una URL indicada', exact=True).click()
                    page.wait_for_function('() => appFixture.prepared.length === 1')
                    self.assertEqual(page.evaluate('appFixture.prepared[0]'), {
                        'id': 'axx.app.navigate', 'inputs': {'application': 'chrome', 'command_id': 'navigate',
                                                           'url': 'https://example.test/document?q=checked'},
                        'source': 'text'})

                    page.locator('#app-catalog-query').fill('Mi herramienta local')
                    inventory = page.locator('#app-catalog-list > details').last
                    inventory.locator(':scope > summary').click()
                    inventory.get_by_role('button', name='Abrir Mi herramienta local', exact=True).click()
                    page.wait_for_function('() => appFixture.prepared.length === 2')
                    self.assertEqual(page.evaluate('appFixture.prepared[1]'), {
                        'id': 'axx.desktop.installed_app', 'inputs': {'app_id': arbitrary['app_id']}, 'source': 'text'})
                    self.assertEqual(page.evaluate('appFixture.opened'), 2)
                    self.assertEqual(page.evaluate('''appFixture.calls.filter(call => call.method !== 'GET' &&
                        !(call.method === 'POST' && ['/axx-api/connect/ui/claim','/axx-api/chat/migrate',
                        '/axx-api/mobile/control/material']
                        .includes(call.path))).map(({method,path}) => ({method,path}))'''), [])
                    self.assertFalse(page.evaluate('Boolean(window.catalogInjected)'))
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
