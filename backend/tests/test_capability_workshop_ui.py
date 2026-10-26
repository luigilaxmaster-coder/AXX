"""Edge UI -> authenticated private HTTP -> SQLite -> real pure-code executor.

Only the Tauri IPC transport and proposal model are fixtures. No execution result,
approval state or backend response is fabricated. This is not installed Tauri QA.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.capability_workshop import CapabilityWorkshop
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


XSS = '<img src=x onerror="window.generatedInjected=true">'


def definition():
    return {'kind': 'python_transform', 'title': 'Calcular total ' + XSS,
            'objective': 'Multiplicar cantidad por precio y redondear a dos decimales.',
            'source': 'def run(inputs):\n    # </pre>' + XSS + '\n    return round(inputs["quantity"] * inputs["price"], 2)',
            'schema': {'type': 'object', 'properties': {
                'quantity': {'type': 'integer', 'minimum': 0, 'maximum': 100},
                'price': {'type': 'number', 'minimum': 0, 'maximum': 1000}}, 'required': ['quantity', 'price']},
            'output_schema': {'type': 'number'},
            'tests': [{'inputs': {'quantity': 2, 'price': 3.5}, 'expected': 7.0},
                      {'inputs': {'quantity': 0, 'price': 12.5}, 'expected': 0.0}],
            'readme': 'Cálculo puro. Revisar las unidades y los casos de prueba antes de activar.'}


class ProposalFixture:
    config = {'allow_paid': False}
    def __init__(self): self.calls = []
    def route(self, request):
        self.calls.append(copy.deepcopy(request))
        return {'ok': True, 'message': {'content': json.dumps(definition())}, 'route': {'model': 'offline-ui-fixture'}}


@unittest.skipUnless(os.environ.get('AXX_TEST_BROWSER_NATIVE') == '1', 'requires isolated native Edge')
class CapabilityWorkshopUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); path = Path(self.temporary.name)
        self.executor = ActionExecutor(path / 'state.db', path / 'artifacts')
        self.commands = CommandService(self.executor); self.model = ProposalFixture()
        self.learning = ActionLearning(self.commands, self.model); self.commands.learning = self.learning
        self.workshop = CapabilityWorkshop(self.learning); self.chats = ChatStore(path / 'state.db')
        handler = type('WorkshopUiHandler', (AxxBridgeHandler,), {
            'workshop': self.workshop, 'commands': self.commands, 'learning': self.learning, 'chats': self.chats})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.reject_first_list = False
        self.list_requests = 0
        self.generation_requests = []

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)
        self.workshop.close(); self.learning.close(); self.commands.close(); self.chats.close(); self.executor.close()
        self.temporary.cleanup()

    def native_request(self, request):
        route = request['path']; method = request['method']; body = request.get('body')
        if method not in ('GET', 'POST') or not route.startswith('/axx-api/'):
            raise ValueError('Invalid fixture IPC request')
        if method == 'GET' and route == '/axx-api/capabilities/list':
            self.list_requests += 1
            if self.reject_first_list:
                self.reject_first_list = False
                raise ValueError('Backend is starting')
        if method == 'POST' and route == '/axx-api/capabilities/generate':
            self.generation_requests.append(copy.deepcopy(body))
        req = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}' + route,
            data=None if body is None or method == 'GET' else json.dumps(body).encode(), method=method,
            headers={'Authorization': 'Bearer ' + self.server.host_token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=20) as response: return json.loads(response.read())
        except urllib.error.HTTPError as response:
            with response:
                result = json.loads(response.read())
                raise ValueError(result.get('error', {}).get('message', str(response.code)))

    def new_page(self, browser):
        root = Path(__file__).resolve().parents[2]
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        page.set_default_timeout(20000)
        page.expose_function('nativeWorkshopRequest', self.native_request)
        page.add_init_script('''window.__TAURI__={core:{invoke:async(name,args)=>{
            const desktop={workWidth:1920,workHeight:1080,spaceLeft:960,spaceRight:960,spaceAbove:540,spaceBelow:540};
            if(name==='native_status')return {native:true,backendReady:false,shortcut:'Alt+Shift+A',desktop};
            if(name==='desktop_layout')return {...desktop,...args};
            if(name==='backend_request')return window.nativeWorkshopRequest(args);
            return null;
        }},event:{listen:async()=>()=>{}}};''')
        page.goto((root / '1.AXX/Axx.html').as_uri())
        page.wait_for_function('() => Boolean(window.Axx?.capabilityWorkshop && Axx.resident?.firstFrame)')
        return page

    def test_open_commands_retries_startup_failure_and_propose_still_generates_once(self):
        from playwright.sync_api import sync_playwright, expect
        self.reject_first_list = True
        edge = Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(edge), headless=True)
            try:
                page = self.new_page(browser)
                expect(page.locator('#cap-status')).to_contain_text('Backend is starting')
                expect(page.locator('#capability-workshop')).to_have_attribute('aria-busy', 'false')
                self.assertEqual(self.list_requests, 1)
                self.assertEqual(page.locator('#cap-list .cap-item').count(), 0)
                # Create on the live authenticated API independently of the UI.
                external = self.native_request({'method': 'POST', 'path': '/axx-api/capabilities/create',
                                                'body': {'definition': definition() | {'title': 'Propuesta externa disponible'}}})
                page.evaluate('() => Axx.companion.openFeature("commands")')
                expect(page.locator('#cap-list')).to_contain_text('Propuesta externa disponible')
                expect(page.locator('#capability-workshop')).to_have_attribute('aria-busy', 'false')
                self.assertEqual(self.list_requests, 2)
                self.assertNotIn('Backend is starting', page.locator('#cap-status').text_content())
                self.assertIsNone(self.workshop.get(external['id'])['approval'])
                self.assertEqual(self.model.calls, [])
                # This public helper opens Comandos too. Its own refresh must
                # not collide with the openFeature retry and discard generation.
                page.evaluate('() => Axx.capabilityWorkshop.propose("Calcular total sintético", "python_transform")')
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.definition?.kind === "python_transform"')
                expect(page.locator('#capability-workshop')).to_have_attribute('aria-busy', 'false')
                self.assertEqual(len(self.generation_requests), 1)
                self.assertEqual(self.generation_requests[0]['kind'], 'python_transform')
                self.assertEqual(self.generation_requests[0]['goal'], 'Calcular total sintético')
                self.assertEqual(len(self.model.calls), 1)
                self.assertEqual(len(self.workshop.list()), 2)
                self.assertEqual(self.executor.list_operations(), [])
            finally: browser.close()

    def test_real_review_revision_activation_calculation_and_revocation_through_ui(self):
        from playwright.sync_api import sync_playwright, expect
        edge = Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(edge), headless=True)
            try:
                page = self.new_page(browser)
                page.evaluate('() => Axx.capabilityWorkshop.open()')
                expect(page.locator('#capability-workshop')).to_be_visible()
                page.locator('#cap-kind').select_option('python_transform')
                page.locator('#cap-goal').fill('Crear un comando que calcule el total de cantidad y precio.')
                page.locator('#cap-generate').click()
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.state === "draft"')
                expect(page.locator('#capability-workshop')).to_have_attribute('aria-busy', 'false')
                draft = page.evaluate('Axx.capabilityWorkshop.current')
                self.assertIsNone(draft['approval']); self.assertEqual(self.executor.list_operations(), [])
                self.assertEqual(draft['definition']['source'], definition()['source'])
                self.assertIn(draft['digest'], page.locator('#cap-editor').inner_text())
                self.assertIn(XSS, page.locator('#cap-editor').inner_text())
                self.assertEqual(page.locator('#cap-editor img').count(), 0)
                self.assertFalse(page.evaluate('Boolean(window.generatedInjected)'))
                self.assertEqual(page.get_by_role('button', name='Aprobar este código y sus contratos', exact=True).count(), 0)
                page.get_by_role('button', name='Ejecutar pruebas de esta versión', exact=True).click()
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.validation?.self_tests_passed === true')
                validated = self.workshop.get(draft['id'])
                self.assertEqual(validated['validation']['tests'][0]['actual'], 7.0)
                self.assertEqual(self.executor.list_operations(), [])
                page.get_by_role('button', name='Aprobar este código y sus contratos', exact=True).click()
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.state === "reviewed"')
                expect(page.locator('#capability-workshop')).to_have_attribute('aria-busy', 'false')
                self.assertEqual(self.workshop.get(draft['id'])['approval']['digest'], draft['digest'])

                # A user edit creates a new unapproved revision, including new test receipts.
                page.get_by_text('Revisar y editar la definición', exact=True).click()
                changed = copy.deepcopy(draft['definition']); changed['title'] = 'Total revisado ' + XSS
                page.locator('#cap-definition').fill(json.dumps(changed, ensure_ascii=False))
                page.get_by_role('button', name='Guardar una nueva versión', exact=True).click()
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.revision === 2')
                expect(page.locator('#capability-workshop')).to_have_attribute('aria-busy', 'false')
                revised = self.workshop.get(draft['id'])
                self.assertIsNone(revised['approval']); self.assertFalse(revised['validation']['self_tests_passed'])
                self.assertNotEqual(revised['digest'], draft['digest'])
                self.assertEqual(page.get_by_role('button', name='Activar comando aprobado', exact=True).count(), 0)
                page.get_by_role('button', name='Ejecutar pruebas de esta versión', exact=True).click()
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.validation?.self_tests_passed === true')
                page.get_by_role('button', name='Aprobar este código y sus contratos', exact=True).click()
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.state === "reviewed"')
                page.get_by_role('button', name='Activar comando aprobado', exact=True).click()
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.state === "active"')
                active = self.workshop.get(draft['id']); command_id = active['generated_command_id']
                self.assertIn(command_id, self.executor.dynamic_tools)
                page.get_by_role('button', name='Usar comando', exact=True).click()
                expect(page.locator('#command-library-select')).to_have_value(command_id)
                page.locator('#command-library-fields [name="quantity"]').fill('3')
                page.locator('#command-library-fields [name="price"]').fill('12.5')
                page.locator('#command-library-prepare').click()
                page.wait_for_function('() => Axx.commandLibrary.operation?.state === "awaiting_approval"')
                page.locator('#cw-operation').get_by_role('button', name='Aprobar y ejecutar', exact=True).click()
                page.wait_for_function('() => Axx.commandLibrary.lastOperation?.state === "succeeded"')
                result = self.commands.get(page.evaluate('Axx.commandLibrary.lastOperation.operation_id'))
                self.assertEqual(result['output']['result'], 37.5); self.assertTrue(result['postconditions_passed'])
                self.assertEqual(result['evidence']['verification'], 'bounded_python_transform')
                self.assertIn('37.5', page.locator('#command-library-result').text_content())

                page.evaluate('() => Axx.capabilityWorkshop.open()')
                page.get_by_role('button', name='Desactivar capacidad', exact=True).click()
                page.wait_for_function('() => Axx.capabilityWorkshop.current?.state === "revoked"')
                self.assertNotIn(command_id, self.executor.dynamic_tools)
                self.assertFalse(self.commands.details(command_id)['command']['execution_enabled'])
                with self.assertRaises(ValueError): self.commands.prepare(command_id, {'quantity': 3, 'price': 12.5})
                self.assertFalse(page.evaluate('Boolean(window.generatedInjected)'))
                self.assertEqual(len(self.model.calls), 1); self.assertFalse(self.model.calls[0]['allow_paid'])
            finally: browser.close()


if __name__ == '__main__': unittest.main()
