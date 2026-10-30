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

    def page(self, init=True, width=390, fail_first=False, permissions=None, conversation=None, reduced_motion='no-preference', fragment='', session_error=None, theme='light'):
        context = self.browser.new_context(viewport={'width': width, 'height': 780}, reduced_motion=reduced_motion)
        context.add_init_script("""(() => {
            let clipboardText = '';
            const realSetInterval = window.setInterval;
            window.setInterval = (fn, delay, ...args) => {
                if (delay === 15000) window.fixturePoll = fn;
                return realSetInterval(fn, delay, ...args);
            };
            Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
                writeText: async value => { clipboardText = String(value); },
                readText: async () => clipboardText
            }});
        })();""")
        self.addCleanup(context.close)
        page = context.new_page()
        fixture = {'calls': [], 'effects': set(), 'fail_first': fail_first, 'mutations': [], 'errors': {}, 'sessions': [], 'commands': None,
                   'chat_result': None, 'review_expiry': 2000000000, 'history_more': False, 'activity': [
                       {'id': 'f27038d4-1e3a-41d1-8085-15f51c59ff70', 'state': 'awaiting_approval',
                        'created_at': 1, 'command_id': '<img src=x onerror=alert(1)>',
                        'can_cancel': True, 'review_available': True, 'postconditions_passed': False},
                       {'id': 'b27038d4-1e3a-41d1-8085-15f51c59ff70', 'state': 'running', 'created_at': 2, 'command_id': 'Orden en curso'},
                       {'id': 'c27038d4-1e3a-41d1-8085-15f51c59ff70', 'state': 'succeeded', 'created_at': 3,
                        'command_id': 'Orden lista', 'postconditions_passed': True},
                       {'id': 'd27038d4-1e3a-41d1-8085-15f51c59ff70', 'state': 'succeeded', 'created_at': 4}]}
        if session_error:
            fixture['errors']['/api/session'] = session_error
        state = {'worker_running': True, 'messages': 'not_verified', 'voice_notes': 'not_implemented',
                 'files': 'not_implemented', 'pc_commands': 'not_verified', 'private_calls': 'unavailable',
                 'permissions': permissions or {'conversation': True, 'voice_notes': False, 'files': False, 'pc_commands': True, 'private_calls': False},
                 'conversation': conversation or {'state': 'configured', 'reason_code': 'READY_FOR_REQUEST',
                     'provider': 'desktop_selected', 'model': '<img src=x onerror=alert(1)>', 'message': 'Selección configurada'},
                 'connection': {'core_bound': True, 'account_running': False, 'bot_running': True, 'checked_at': 1},
                 'observed_at': 1, 'session_expires_at': 2000000000, 'remote_confirmations': True}
        fixture['state'] = state
        colors = {'bg_color':'#101a29', 'text_color':'#ffffff', 'secondary_bg_color':'#24344b', 'button_color':'#6495ed'} if theme == 'dark' else {'bg_color':'#ffffff', 'text_color':'#111827', 'secondary_bg_color':'#eef1f5', 'button_color':'#2864df'}
        def route(request_route):
            request = request_route.request
            url = request.url
            if url == 'https://telegram.org/js/telegram-web-app.js':
                sdk = "window.Telegram={WebApp:{initData:" + json.dumps('fixture-data' if init else '') + ",colorScheme:" + json.dumps(theme) + ",themeParams:" + json.dumps(colors) + ",ready(){},expand(){}}};"
                sdk += "for(const [k,v] of Object.entries(window.Telegram.WebApp.themeParams)) document.documentElement.style.setProperty('--tg-theme-'+k.replaceAll('_','-'),v);"
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
                    'text': '<img src=x onerror=alert(1)> historial', 'status': 'complete', 'at': 1}], 'has_more': fixture['history_more']})
            elif path == '/api/activity':
                request_route.fulfill(status=200, json={'items': fixture['activity']})
            elif path == '/api/commands':
                request_route.fulfill(status=200, json=fixture['commands'] if fixture['commands'] is not None else {'items': [
                    {'id': 'calc', 'command_id': 'open', 'title': 'Calculadora', 'example': 'abre calculadora', 'description': 'Abre la calculadora', 'category': 'Aplicaciones', 'available': True, 'reason': ''},
                    {'id': 'disabled', 'command_id': 'disabled', 'title': '<img src=x>', 'example': 'otro comando', 'description': 'No disponible', 'category': 'Sistema', 'available': False, 'reason': 'Sin permiso'}], 'text': 'Comandos'})
            elif path == '/api/review':
                fixture['mutations'].append((path, json.loads(request.post_data)))
                request_route.fulfill(status=200, json={'state': 'awaiting_approval', 'title': 'Abrir archivo',
                    'description': 'Revisar', 'risk': 'local_state', 'inputs': {'path': '<img src=x onerror=alert(1)>'},
                    'expires_at': fixture['review_expiry'], 'token': 'x' * 43, 'can_confirm': True})
            elif path == '/api/decision':
                fixture['mutations'].append((path, json.loads(request.post_data)))
                request_route.fulfill(status=200, json={'state': 'succeeded', 'postconditions_passed': True, 'text': 'Verificado'})
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
                    request_route.fulfill(status=200, json=fixture['chat_result'] or {'state': 'succeeded', 'text': '<img src=x onerror=alert(1)> respuesta'})
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

    def test_sequence_opens_next_review_without_approving_it(self):
        page, fixture = self.page()
        next_id = 'a27038d4-1e3a-41d1-8085-15f51c59ff70'
        reviews, decisions = [], []
        def review_route(route):
            reviews.append(json.loads(route.request.post_data)['operation_id'])
            route.fulfill(status=200, json={'state':'awaiting_approval','can_confirm':True,
                'title':'Siguiente paso' if reviews[-1] == next_id else 'Primer paso',
                'inputs':{},'token':'x'*32,'expires_at':2000000000})
        def decision_route(route):
            decisions.append(json.loads(route.request.post_data))
            route.fulfill(status=200, json={'state':'succeeded', 'postconditions_passed':True,
                'text':'Paso comprobado', 'next_operation_id':next_id})
        page.route('**/api/review', review_route)
        page.route('**/api/decision', decision_route)
        page.locator('[data-pane="activity"]').click()
        page.get_by_role('button', name='Revisar orden', exact=True).first.click()
        page.locator('#review-confirm').click()
        page.wait_for_function("() => document.querySelector('#review-title').textContent === 'Siguiente paso' && !document.querySelector('#review-confirm').disabled")
        self.assertTrue(page.locator('#review-card').is_visible())
        self.assertEqual(reviews[-1], next_id)
        self.assertEqual(len(decisions), 1)
        self.assertTrue(page.locator('#review-confirm').is_enabled())

    def test_command_catalog_filters_and_only_fills_draft(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="commands"]').click()
        page.wait_for_selector('[data-command-example]')
        self.assertEqual(page.locator('#command-list img').count(), 0)
        self.assertTrue(page.locator('[data-command-example]').nth(1).is_disabled())
        page.locator('#command-category').select_option(label='Aplicaciones')
        self.assertEqual(page.locator('[data-command-example]').count(), 1)
        page.locator('#command-search').fill('calculadora')
        page.locator('[data-command-example]').click()
        self.assertTrue(page.locator('#chat').is_visible())
        self.assertEqual(page.locator('#draft').input_value(), 'abre calculadora')
        self.assertEqual(fixture['mutations'], [])

    def test_command_examples_disabled_while_submission_is_pending(self):
        page, fixture = self.page(fail_first=True)
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        page.locator('#draft').fill('Solicitud original')
        page.locator('#send').click()
        page.wait_for_selector('#recover:not([hidden])')
        page.locator('[data-pane="commands"]').click()
        page.wait_for_selector('[data-command-example]')
        self.assertTrue(page.locator('[data-command-example]').first.is_disabled())
        self.assertEqual(page.locator('#draft').input_value(), 'Solicitud original')
        self.assertEqual(len(fixture['mutations']), 1)

    def test_command_search_ignores_accents_and_case_without_sending(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        fixture['commands'] = {'items': [{'title': 'Información del sistema', 'example': 'información del sistema',
            'description': 'Consulta', 'category': 'Sistema', 'available': True}], 'text': ''}
        page.locator('[data-pane="commands"]').click()
        page.wait_for_selector('[data-command-example]')
        page.locator('#command-search').fill('INFORMACION')
        self.assertEqual(page.locator('[data-command-example]').count(), 1)
        self.assertIn('Información del sistema', page.locator('#command-list').inner_text())
        self.assertEqual(fixture['mutations'], [])

    def test_empty_catalog_explains_backend_reason_and_refreshes(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        fixture['commands'] = {'items': [], 'text': 'No se pudo consultar el catálogo.'}
        page.locator('[data-pane="commands"]').click()
        page.wait_for_function("() => document.querySelector('#command-status').textContent.includes('No se pudo consultar')")
        fixture['commands'] = {'items': [], 'text': 'Aún no hay comandos disponibles.'}
        page.locator('#refresh').click()
        page.wait_for_function("() => document.querySelector('#command-status').textContent.includes('Aún no hay comandos')")

    def test_commands_denial_clears_private_state_and_disables_actions(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('historial')")
        page.locator('[data-pane="activity"]').click()
        page.get_by_role('button', name='Revisar orden').click()
        page.wait_for_selector('#review-card:not([hidden])')
        fixture['errors']['/api/commands'] = (403, 'PERMISSION_DENIED')
        page.locator('[data-pane="commands"]').click()
        page.wait_for_function("() => document.querySelector('#command-status').textContent.includes('No hay acceso')")
        self.assertTrue(page.locator('#review-card').is_hidden())
        self.assertNotIn('historial', page.locator('#messages').inner_text().replace('No hay acceso al historial.', ''))
        self.assertTrue(page.locator('#draft').is_disabled())

    def test_recent_summary_filters_and_examples_are_read_only(self):
        page, fixture = self.page(theme='dark')
        page.wait_for_function("() => document.querySelector('#count-pending').textContent === '1'")
        self.assertEqual(page.locator('.character').get_attribute('data-empty'), 'true')
        self.assertLessEqual(page.locator('.character').bounding_box()['height'], 96)
        self.assertEqual(page.locator('#count-running').inner_text(), '1')
        self.assertEqual(page.locator('#count-completed').inner_text(), '2')
        self.assertIn('30', page.locator('#home').inner_text())
        self.assertEqual(page.locator('#activity-badge').inner_text(), '1')
        self.assertTrue(page.locator('#review-pending').is_visible())
        page.evaluate("""() => {const banner=document.createElement('p'); banner.textContent='DATOS SIMULADOS'; banner.id='fixture-banner'; document.querySelector('main').prepend(banner);} """)
        target = ROOT / 'build' / 'telegram-miniapp-home-preview.png'
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=True)
        page.locator('#review-pending').click()
        self.assertTrue(page.locator('#activity').is_visible())
        self.assertEqual(page.locator('[data-activity-filter="pending"]').get_attribute('aria-pressed'), 'true')
        for group in ('running', 'completed', 'all'):
            page.locator(f'[data-activity-filter="{group}"]').click()
            self.assertEqual(page.locator(f'[data-activity-filter="{group}"]').get_attribute('aria-pressed'), 'true')
        self.assertEqual(fixture['mutations'], [])
        page.screenshot(path=str(ROOT / 'build' / 'telegram-miniapp-activity-preview.png'), full_page=True)
        page.locator('[data-pane="chat"]').click()
        example = page.locator('[data-example]').first
        value = example.get_attribute('data-example')
        example.click()
        self.assertEqual(page.locator('#draft').input_value(), value)
        self.assertEqual(fixture['mutations'], [])

    def test_remote_permission_comes_from_top_level(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="status"]').click()
        self.assertIn('Confirmaciones desde Telegram', page.locator('#permissions').inner_text())
        self.assertEqual(page.locator('#permissions dt').filter(has_text='Confirmaciones desde Telegram').locator('xpath=following-sibling::dd[1]').inner_text(), 'Concedido')
        fixture['state']['remote_confirmations'] = False
        fixture['state']['permissions']['remote_confirmations'] = True
        page.locator('#refresh').click()
        page.wait_for_function("() => [...document.querySelectorAll('#permissions dt')].find(x => x.textContent.includes('Confirmaciones desde Telegram'))?.nextElementSibling.textContent === 'No concedido'")

    def test_poll_and_filters_preserve_review_and_result_without_automatic_decision(self):
        page, fixture = self.page()
        page.locator('[data-pane="activity"]').click()
        page.get_by_role('button', name='Revisar orden').click()
        page.wait_for_selector('#review-card:not([hidden])')
        self.assertEqual(page.locator('#review-state').inner_text(), 'Orden pendiente · No ejecutada')
        self.assertIn('una vez', page.locator('#review-explanation').inner_text())
        self.assertIn('Cambiar estado de aplicación', page.locator('#review-risk').inner_text())
        self.assertEqual(page.locator('#review-confirm').inner_text(), 'Aprobar una vez')
        self.assertEqual(page.locator('#review-cancel').inner_text(), 'Denegar')
        page.locator('[data-activity-filter="running"]').click()
        page.evaluate('window.fixturePoll()')
        page.wait_for_timeout(150)
        self.assertTrue(page.locator('#review-card').is_visible())
        self.assertTrue(page.locator('#review-confirm').is_enabled())
        self.assertEqual([path for path, _ in fixture['mutations'] if path == '/api/decision'], [])
        page.locator('#review-confirm').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.includes('Verificado')")
        page.evaluate('window.fixturePoll()')
        page.wait_for_timeout(150)
        self.assertIn('Verificado', page.locator('#error').inner_text())
        page.reload()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        self.assertEqual(len([path for path, _ in fixture['mutations'] if path == '/api/decision']), 1)

    def test_large_unicode_draft_does_not_post_or_clear(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        text = '😀' * 5000
        page.locator('#draft').fill(text)
        page.locator('#send').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.includes('demasiado largo')")
        self.assertEqual(page.locator('#draft').input_value(), text)
        self.assertEqual([path for path, _ in fixture['mutations'] if path == '/api/chat'], [])
        self.assertEqual(fixture['effects'], set())

    def test_review_displays_exact_inputs_and_confirms_once(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="activity"]').click()
        page.get_by_role('button', name='Revisar orden').click()
        page.wait_for_selector('#review-card:not([hidden])')
        self.assertIn('<img src=x onerror=alert(1)>', page.locator('#review-inputs').inner_text())
        self.assertEqual(page.locator('#review-inputs img').count(), 0)
        page.locator('#review-confirm').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.includes('Verificado')")
        decisions = [body for path, body in fixture['mutations'] if path == '/api/decision']
        self.assertEqual(decisions, [{'token': 'x' * 43, 'decision': 'confirm', 'csrf': 'fixture-csrf'}])

    def test_terminal_review_never_offers_approval_or_claims_pending(self):
        page, _ = self.page()
        page.route('**/api/review', lambda route: route.fulfill(status=200, json={
            'state': 'succeeded', 'title': 'Orden', 'inputs': {}, 'risk': 'read',
            'expires_at': 2000000000, 'token': 'x' * 32, 'can_confirm': True}))
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="activity"]').click()
        page.get_by_role('button', name='Revisar orden').click()
        page.wait_for_selector('#review-card:not([hidden])')
        self.assertEqual(page.locator('#review-state').inner_text(), '')
        self.assertEqual(page.locator('#review-explanation').inner_text(), '')
        self.assertTrue(page.locator('#review-confirm').is_disabled())

    def test_chat_opens_review_and_expiry_blocks_decision(self):
        page, fixture = self.page()
        fixture['chat_result'] = {'state': 'awaiting_approval', 'text': 'Revisa la orden',
                                  'operation_id': 'f27038d4-1e3a-41d1-8085-15f51c59ff70'}
        fixture['review_expiry'] = 1
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.get_by_role('button', name='Chat', exact=True).click()
        page.locator('#draft').fill('Abrir archivo')
        page.locator('#send').click()
        page.wait_for_selector('#review-card:not([hidden])')
        self.assertTrue(page.locator('#activity').is_visible())
        self.assertTrue(page.locator('#review-confirm').is_disabled())
        self.assertIn('venció', page.locator('#review-reason').inner_text())
        self.assertEqual([path for path, _ in fixture['mutations'] if path == '/api/decision'], [])

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
        page.locator('[data-pane="activity"]').click()
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
        self.assertTrue(page.locator('#draft').is_disabled())
        self.assertTrue(page.locator('[data-example]').first.is_disabled())
        page.reload()
        page.wait_for_selector('#recover:not([hidden]):not([disabled])', state='attached')
        page.get_by_role('button', name='Chat', exact=True).click()
        self.assertEqual(page.locator('#draft').input_value(), 'Una solicitud de prueba')
        self.assertTrue(page.locator('[data-example]').first.is_disabled())
        page.locator('#recover').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.includes('Estado consultado')")
        self.assertEqual(len(fixture['calls']), 1)
        page.locator('#retry').click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('respuesta')")
        self.assertEqual(len(fixture['calls']), 2)
        self.assertEqual(fixture['calls'][0]['request_id'], fixture['calls'][1]['request_id'])
        self.assertEqual(len(fixture['effects']), 1)
        self.assertEqual(page.locator('#draft').input_value(), '')

    def test_legacy_oversized_pending_stays_intact_and_cannot_retry(self):
        page, fixture = self.page()
        oversized = '😀' * 5000
        page.evaluate("""text => {sessionStorage.setItem('axx.telegram.draft', text); sessionStorage.setItem('axx.telegram.pending', JSON.stringify({text, request_id:'f27038d4-1e3a-41d1-8085-15f51c59ff70'}));}""", oversized)
        page.reload()
        page.wait_for_selector('#retry:not([hidden]):not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        self.assertTrue(page.locator('#draft').is_disabled())
        self.assertEqual(page.locator('#draft').input_value(), oversized)
        page.locator('#retry').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.includes('Consulta su estado')")
        self.assertNotIn('Acórtalo', page.locator('#error').inner_text())
        self.assertEqual(page.locator('#draft').input_value(), oversized)
        self.assertEqual([path for path, _ in fixture['mutations'] if path == '/api/chat'], [])

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
        page.locator('[data-pane="activity"]').click()
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
        self.assertTrue(page.locator('#send').is_disabled())
        del fixture['errors']['/api/state']
        page.locator('#refresh').click()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        fixture['errors']['/api/state'] = (401, 'SESSION_EXPIRED')
        page.locator('#refresh').click()
        page.wait_for_function("() => document.querySelector('#send').disabled")
        self.assertIn('sesión', page.locator('#connection').inner_text().lower())

    def test_history_permission_denial_clears_history_preserves_draft(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('historial')")
        page.locator('#draft').fill('Borrador que debe conservarse')
        fixture['errors']['/api/history'] = (403, 'PERMISSION_DENIED')
        page.locator('[data-pane="home"]').click()
        page.locator('[data-pane="chat"]').click()
        page.wait_for_function("() => !document.querySelector('#messages').textContent.includes('onerror')")
        self.assertEqual(page.locator('#draft').input_value(), 'Borrador que debe conservarse')

    def test_successful_state_refresh_after_conversation_revocation_hides_existing_history(self):
        page, fixture = self.page(fail_first=True)
        fixture['history_more'] = True
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('onerror')")
        self.assertTrue(page.locator('#history-more').is_visible())
        page.locator('#draft').fill('Borrador pendiente')
        page.locator('#send').click()
        page.wait_for_selector('#recover:not([hidden])')
        pending = page.evaluate("sessionStorage.getItem('axx.telegram.pending')")
        fixture['state']['permissions']['conversation'] = False
        fixture['state']['permissions']['pc_commands'] = True
        page.locator('#refresh').click()
        page.wait_for_function("() => [...document.querySelectorAll('#permissions dt')].find(x => x.textContent === 'Conversación')?.nextElementSibling.textContent === 'No concedido'")
        self.assertNotIn('onerror', page.locator('#messages').text_content())
        self.assertTrue(page.locator('#history-more').is_hidden())
        self.assertEqual(page.locator('#draft').input_value(), 'Borrador pendiente')
        self.assertEqual(page.evaluate("sessionStorage.getItem('axx.telegram.pending')"), pending)
        self.assertEqual(len(fixture['calls']), 1)

    def test_late_review_response_cannot_restore_data_after_activity_permission_denial(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="activity"]').click()
        page.get_by_role('button', name='Revisar orden').wait_for()
        page.evaluate("""() => {
            const original = window.fetch.bind(window);
            window.fetch = (url, options) => {
                if (url !== '/api/review') return original(url, options);
                window.reviewDeferred = true;
                return new Promise(resolve => { window.finishReview = () => resolve(new Response(JSON.stringify({
                    state:'awaiting_approval', title:'Datos de revisión privada', inputs:{secret:'fixture-private'},
                    expires_at:2000000000, token:'x'.repeat(43), can_confirm:true
                }), {status:200, headers:{'Content-Type':'application/json'}})); });
            };
        }""")
        page.get_by_role('button', name='Revisar orden').click()
        page.wait_for_function('() => window.reviewDeferred === true')
        fixture['errors']['/api/activity'] = (403, 'PERMISSION_DENIED')
        page.locator('#activity-refresh').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.toLowerCase().includes('permiso')")
        self.assertTrue(page.locator('#review-card').is_hidden())
        page.evaluate("async () => { window.finishReview(); await new Promise(resolve => setTimeout(resolve, 0)); }")
        self.assertTrue(page.locator('#review-card').is_hidden())
        self.assertNotIn('fixture-private', page.locator('#review-inputs').text_content())
        self.assertTrue(page.locator('#review-confirm').is_disabled())
        self.assertFalse(any(path == '/api/decision' for path, _ in fixture['mutations']))

    def test_activity_permission_denial_hides_history_and_preserves_pending_draft(self):
        page, fixture = self.page(fail_first=True)
        fixture['history_more'] = True
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('onerror')")
        self.assertTrue(page.locator('#history-more').is_visible())
        page.locator('#draft').fill('Borrador pendiente')
        page.locator('#send').click()
        page.wait_for_selector('#recover:not([hidden])')
        pending = page.evaluate("sessionStorage.getItem('axx.telegram.pending')")
        fixture['errors']['/api/activity'] = (403, 'PERMISSION_DENIED')
        page.locator('[data-pane="activity"]').click()
        page.wait_for_function("() => document.querySelector('#error').textContent.toLowerCase().includes('permiso')")
        self.assertNotIn('onerror', page.locator('#messages').text_content())
        self.assertTrue(page.locator('#history-more').is_hidden())
        self.assertEqual(page.locator('#draft').input_value(), 'Borrador pendiente')
        self.assertEqual(page.evaluate("sessionStorage.getItem('axx.telegram.pending')"), pending)

    def test_late_chat_response_after_session_expiry_preserves_pending_and_draft(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        page.evaluate("""() => {
            const original = window.fetch.bind(window);
            window.fetch = (url, options) => {
                if (url !== '/api/chat') return original(url, options);
                window.chatDeferred = true;
                return new Promise(resolve => { window.finishChat = () => resolve(new Response(JSON.stringify({
                    state:'succeeded', text:'fixture-private-late-answer'
                }), {status:200, headers:{'Content-Type':'application/json'}})); });
            };
        }""")
        page.locator('#draft').fill('Borrador pendiente')
        page.locator('#send').click()
        page.wait_for_function('() => window.chatDeferred === true')
        pending = page.evaluate("sessionStorage.getItem('axx.telegram.pending')")
        self.assertTrue(pending)
        fixture['errors']['/api/state'] = (401, 'SESSION_EXPIRED')
        page.locator('#refresh').click()
        page.wait_for_function("() => document.querySelector('#connection').textContent.toLowerCase().includes('sesión')")
        page.evaluate("async () => { window.finishChat(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); }")
        self.assertNotIn('fixture-private-late-answer', page.locator('#messages').text_content())
        self.assertEqual(page.locator('#draft').input_value(), 'Borrador pendiente')
        self.assertEqual(page.evaluate("sessionStorage.getItem('axx.telegram.pending')"), pending)
        self.assertEqual(fixture['calls'], [])

    def test_stale_state_response_cannot_undo_newer_conversation_revocation(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="chat"]').click()
        page.wait_for_function("() => document.querySelector('#messages').textContent.includes('onerror')")
        stale = json.dumps(fixture['state'])
        page.evaluate("""stale => {
            const original = window.fetch.bind(window);
            let first = true;
            window.fetch = (url, options) => {
                if (url !== '/api/state' || !first) return original(url, options);
                first = false; window.stateDeferred = true;
                return new Promise(resolve => { window.finishState = () => resolve(new Response(stale,
                    {status:200, headers:{'Content-Type':'application/json'}})); });
            };
        }""", stale)
        page.locator('#refresh').click()
        page.wait_for_function('() => window.stateDeferred === true')
        fixture['state']['permissions']['conversation'] = False
        page.locator('#refresh').click()
        page.wait_for_function("() => [...document.querySelectorAll('#permissions dt')].find(x => x.textContent === 'Conversación')?.nextElementSibling.textContent === 'No concedido'")
        page.evaluate("async () => { window.finishState(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); }")
        self.assertEqual(page.locator('#permissions dt').filter(has_text='Conversación').locator('xpath=following-sibling::dd[1]').inner_text(), 'No concedido')
        self.assertNotIn('onerror', page.locator('#messages').text_content())

    def test_stale_state_unauthorized_response_does_not_expire_newer_success(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.evaluate("""() => {
            const original = window.fetch.bind(window); let first = true;
            window.fetch = (url, options) => {
                if (url !== '/api/state' || !first) return original(url, options);
                first = false; window.staleStateReady = true;
                return new Promise(resolve => { window.finishStaleState = () => resolve(new Response(
                    JSON.stringify({error:'SESSION_EXPIRED'}), {status:401, headers:{'Content-Type':'application/json'}})); });
            };
        }""")
        page.locator('#refresh').click()
        page.wait_for_function('() => window.staleStateReady === true')
        fixture['state']['connection']['core_bound'] = False
        page.locator('#refresh').click()
        page.wait_for_function("() => !document.querySelector('#connection').textContent.includes('Axx está disponible en tu PC')")
        page.evaluate("async () => { window.finishStaleState(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); }")
        self.assertNotIn('sesión vencida', page.locator('#connection').inner_text().lower())
        self.assertTrue(page.locator('#send').is_enabled())

    def test_stale_activity_denial_does_not_erase_newer_success_or_notice(self):
        page, fixture = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="activity"]').click()
        page.get_by_role('button', name='Revisar orden').wait_for()
        page.evaluate("""() => {
            const original = window.fetch.bind(window); let first = true;
            window.fetch = (url, options) => {
                if (url !== '/api/activity' || !first) return original(url, options);
                first = false; window.staleActivityReady = true;
                return new Promise(resolve => { window.finishStaleActivity = () => resolve(new Response(
                    JSON.stringify({error:'PERMISSION_DENIED'}), {status:403, headers:{'Content-Type':'application/json'}})); });
            };
        }""")
        page.locator('#activity-refresh').click()
        page.wait_for_function('() => window.staleActivityReady === true')
        fixture['activity'][0]['command_id'] = 'new-activity-fixture'
        page.locator('#activity-refresh').click()
        page.wait_for_function("() => document.querySelector('#activity-list').textContent.includes('new-activity-fixture')")
        page.evaluate("document.querySelector('#error').textContent='Resultado fixture conservado'")
        page.evaluate("async () => { window.finishStaleActivity(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); }")
        self.assertTrue(page.get_by_role('button', name='Revisar orden').is_visible())
        self.assertIn('Resultado fixture conservado', page.locator('#error').inner_text())

    def test_closing_pending_review_prevents_late_response_from_reopening(self):
        page, _ = self.page()
        page.wait_for_selector('#send:not([disabled])', state='attached')
        page.locator('[data-pane="activity"]').click()
        page.get_by_role('button', name='Revisar orden').wait_for()
        page.evaluate("""() => {
            const original = window.fetch.bind(window);
            window.fetch = (url, options) => {
                if (url !== '/api/review') return original(url, options);
                window.reviewCloseDeferred = true;
                return new Promise(resolve => { window.finishClosedReview = () => resolve(new Response(JSON.stringify({
                    state:'awaiting_approval', title:'fixture-private-review', inputs:{},
                    expires_at:2000000000, token:'x'.repeat(43), can_confirm:true
                }), {status:200, headers:{'Content-Type':'application/json'}})); });
            };
        }""")
        page.get_by_role('button', name='Revisar orden').click()
        page.wait_for_function('() => window.reviewCloseDeferred === true')
        page.evaluate("document.querySelector('#review-close').click()")
        page.evaluate("async () => { window.finishClosedReview(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); }")
        self.assertTrue(page.locator('#review-card').is_hidden())
        self.assertNotIn('fixture-private-review', page.locator('#review-title').text_content())

    def test_pairing_fragment_is_consumed_once_and_removed_even_on_failure(self):
        pairing = 'axx_' + 'x' * 43
        page, fixture = self.page(fragment='#pairing=' + pairing)
        page.wait_for_selector('#send:not([disabled])', state='attached')
        self.assertEqual(fixture['sessions'][0], {'init_data': 'fixture-data', 'pairing_token': pairing})
        self.assertEqual(page.evaluate('location.hash'), '')
        page, fixture = self.page(fragment='#pairing=' + pairing, session_error=(403, 'PAIRING_REQUIRED'))
        page.wait_for_function("() => document.querySelector('#connection').textContent.includes('QR')")
        self.assertEqual(fixture['sessions'][0]['pairing_token'], pairing)
        self.assertEqual(page.evaluate('location.hash'), '')
        page, fixture = self.page(init=False, fragment='#pairing=' + pairing + '&tab=chat')
        self.assertEqual(page.evaluate('location.hash'), '#tab=chat')
        self.assertEqual(fixture['sessions'], [])

    def test_viewports_text_scaling_keyboard_and_reduced_motion(self):
        for width, theme in ((320, 'light'), (390, 'light'), (390, 'dark'), (768, 'dark')):
            with self.subTest(width=width, theme=theme):
                page, _ = self.page(width=width, reduced_motion='reduce', theme=theme)
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
                self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('nav')).position"), 'sticky')
                for pane in ('activity', 'status', 'home'):
                    page.locator(f'[data-pane="{pane}"]').click()
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)


if __name__ == '__main__':
    unittest.main()
