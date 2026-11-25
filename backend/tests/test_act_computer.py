"""Acts using the computer: the AXX-driven loop over the real ComputerUse admission, ConnectService and executor.

Controlled: Windows UI Automation, capture and the input call are patched exactly like test_computer_use; the Act's
model is a scripted responder. Admission tickets, the executor journal, grants and events are the real services.
The opt-in native test (AXX_REAL_COMPUTER=1) clicks a real Tk window with the real UIA and the real input owner.
"""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend import computer_use as cu
from backend.actions.executor import ActionExecutor
from backend.agents.act_computer import ActComputerRunner, parse_decision, region_expected, valid_expected
from backend.agents.http_api import EvolutionHttpRuntime
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.connect.service import ConnectService
from backend.tests.test_acts_inference import act_spec

BUTTON = {'control_id': 'btn-save', 'name': 'Guardar', 'control_type': 'ControlType.Button', 'enabled': True, 'offscreen': False,
          'bounds': {'x': 40, 'y': 60, 'width': 100, 'height': 30}}


class _ComputerFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.executor = ActionExecutor(root / 'state.db', root / 'artifacts'); self.commands = CommandService(self.executor)
        self.computer = cu.ComputerUse(self.commands); self.executor.computer_use = self.computer
        self.control = SimpleNamespace(is_set=lambda: False, wait=lambda seconds: False)
        self.executor.input_control = SimpleNamespace(automation=lambda event: nullcontext(self.control))
        self.connect = ConnectService(self.commands, None)
        self.chats = ChatStore(root / 'state.db')
        self.rt = EvolutionHttpRuntime(db_path=root / 'state.db', storage_dir=root / 'evo', chat_store=self.chats,
                                       action_executor=self.executor, command_service=self.commands)
        self.rt.flags.set_flag('agent_profiles_v1', True, reason='act computer test')
        self.rt.registry.create_profile(act_spec('act-dev', 'Dev', 'Helix', 'axx-connect', 'gpt-6.1-terra'))
        self.chat = self.chats.get(self.chats.mutate('create', {'title': 'Computadora'})['id'])
        self.patches = [patch.object(cu.uia, 'process_name', return_value='fixture.exe'),
                        patch.object(cu.uia, 'process_started', return_value='birth'),
                        patch.object(cu.uia, 'list_windows', return_value=[{'window_id': 10, 'pid': 20, 'title': 'Editor'}]),
                        patch.object(cu.uia, 'read_window_title', return_value='Editor'), patch.object(cu.uia, 'focus_window')]
        for item in self.patches: item.start()
        self.observed = {'controls': [dict(BUTTON)], 'window_title': 'Editor', 'focused_control_id': None,
                         'observation': {'observation_id': 'obs-1', 'window_id': 10, 'pid': 20, 'process_started': 'birth',
                                         'window_bounds': {'x': 0, 'y': 0, 'width': 400, 'height': 300}, 'monitors': []}}
        self.decisions, self.dispatched = [], []
        self.runner = ActComputerRunner(self.rt, infer=self.fake_infer, resolve=lambda aid: {'act_id': aid, 'name': 'Dev', 'model': 'm', 'revision': 1},
                                        computer_use=self.computer, connect=self.connect, chats=self.chats)

    def tearDown(self):
        self.computer.close(); self.connect.close(); self.rt.close(); self.commands.close(); self.executor.close(); self.chats.close()
        for item in self.patches: item.stop()
        self.temp.cleanup()

    def fake_infer(self, act, envelope, conversation_id, cancel):  # scripted Act model; AXX still verifies everything else
        self.prompts = getattr(self, 'prompts', []) + [envelope['messages'][-1]['content']]
        return {'ok': True, 'message': {'content': json.dumps(self.decisions.pop(0))}}, {'model_verified': True, 'served_model': 'm'}

    def grant(self, ops=('uia',)):
        self.rt.registry.grant_permission(grant_id='g-pc-' + str(time.monotonic_ns()), agent_id='act-dev', tool_id='axx.computer', resource_pattern='*', operation_kinds=list(ops),
                                          approval_mode='auto_safe', expires_at_ms=None, granted_by='owner')

    def authorize(self, allow_input=True):
        self.computer.begin(self.chat['connect_id'], 10, 20, image_authorized=True, allow_input=allow_input)

    def run_task(self, after_click=None):
        observed = self.observed
        shot = {'id': 'obs-1', 'at': time.monotonic(), 'observed': observed, 'hash': 'frame', 'jpeg': b'x', 'width': 400, 'height': 300,
                'image_bounds': {'x': 0, 'y': 0, 'width': 400, 'height': 300}}
        output = {'observation_id': 'obs-1', 'title': 'Editor', 'controls': observed['controls'], 'focused_control_id': None,
                  'image_width': 400, 'image_height': 300, 'image_bounds': shot['image_bounds'], 'truncated': False}
        reads = iter([observed] + [after_click or {'controls': [{'name': 'Guardado'}]}] * 50)
        def observe(grant, event, **kw):
            shot['at'] = time.monotonic(); return dict(shot), output
        with patch.object(self.computer, '_observe', side_effect=observe), \
             patch.object(cu.uia, 'read_window_content', side_effect=lambda *a, **k: next(reads)), \
             patch.object(cu, 'execute_action', side_effect=lambda payload, control: self.dispatched.append(payload) or {'success': True}):
            run = self.runner.start({'act_id': 'act-dev', 'conversation_id': self.chat['id'], 'instruction': 'Guarda el documento', 'max_steps': 3})
            deadline = time.monotonic() + 20
            while self.runner.get(run['run_id'])['state'] == 'running' and time.monotonic() < deadline: time.sleep(.05)
        return self.runner.get(run['run_id'])

    def events(self):
        return [e.get('event_type') or e.get('type') for e in self.rt.event_hub.replay_sse(self.chat['id'])['events']]

class ActComputerLoopTests(_ComputerFixture):
    def test_act_clicks_a_real_control_through_admission_and_executor_then_reports(self):
        self.grant(); self.authorize()
        self.decisions = [{'say': 'Pulso Guardar', 'done': False, 'action': {'action': 'click', 'control_id': 'btn-save'},
                           'expected': {'name': 'Guardado'}}, {'say': 'Documento guardado', 'done': True}]
        run = self.run_task()
        self.assertEqual(run['state'], 'completed', run)
        self.assertEqual(run['summary'], 'Documento guardado')
        step = run['steps'][0]
        self.assertEqual((step['action'], step['control_id'], step['label'], step['x'], step['y'], step['state']),
                         ('click', 'btn-save', 'Guardar', 90, 75, 'succeeded'))
        self.assertEqual(step['verification'], 'computer_expected_control')
        self.assertEqual((self.dispatched[0]['action'], self.dispatched[0]['x'], self.dispatched[0]['y']), ('click', 90, 75))
        self.assertIn('btn-save | Button | Guardar', self.prompts[0])  # the model saw the real controls, never an invented list
        self.assertEqual(self.events(), ['run.started', 'tool.dispatched', 'tool.verified', 'run.completed'])
        journal = {op['command_id'] for op in self.commands.operations()}
        self.assertEqual(journal, {'axx.computer.observe', 'axx.computer.act'})

    def test_without_the_acts_own_grant_nothing_is_observed(self):
        self.authorize()
        with self.assertRaises(PermissionError):
            self.runner.start({'act_id': 'act-dev', 'conversation_id': self.chat['id'], 'instruction': 'x'})
        self.assertEqual(self.commands.operations(), [])

    def test_owner_must_authorize_input_in_this_chat(self):
        self.grant()
        with self.assertRaisesRegex(ValueError, 'Controlar PC'):
            self.runner.start({'act_id': 'act-dev', 'conversation_id': self.chat['id'], 'instruction': 'x'})
        self.authorize(allow_input=False)
        with self.assertRaisesRegex(ValueError, 'Controlar PC'):
            self.runner.start({'act_id': 'act-dev', 'conversation_id': self.chat['id'], 'instruction': 'x'})

    def test_invented_control_stops_before_any_input(self):
        self.grant(); self.authorize()
        self.decisions = [{'say': 'Pulso algo', 'action': {'action': 'click', 'control_id': 'no-existe'}}]
        run = self.run_task()
        self.assertEqual(run['state'], 'failed'); self.assertIn('inexistente', run['error'])
        self.assertEqual(self.dispatched, []); self.assertEqual(run['steps'], [])

    def test_unverified_effect_stops_the_act(self):
        self.grant(); self.authorize()
        self.decisions = [{'say': 'Pulso Guardar', 'action': {'action': 'click', 'control_id': 'btn-save'}, 'expected': {'name': 'Guardado'}},
                          {'done': True}]
        run = self.run_task(after_click={'controls': [dict(BUTTON)]})  # the expected control never appears
        self.assertEqual(run['state'], 'failed', run)
        self.assertEqual(len(self.dispatched), 1)
        self.assertNotEqual(run['steps'][0]['state'], 'succeeded')
        self.assertIn('run.failed', self.events())

    def test_revoking_the_act_grant_stops_the_next_gesture(self):
        self.grant(); self.authorize()
        def infer(act, envelope, conversation_id, cancel):
            for g in self.rt.registry.list_permissions('act-dev'): self.rt.registry.revoke_permission('act-dev', g['grant_id'])
            return {'ok': True, 'message': {'content': json.dumps({'action': {'action': 'click', 'control_id': 'btn-save'}, 'expected': {'name': 'Guardado'}})}}, {'model_verified': True}
        self.runner.infer = infer
        run = self.run_task()
        self.assertEqual(run['state'], 'failed'); self.assertEqual(self.dispatched, [])

    def test_decision_parsing_and_checks(self):
        self.assertEqual(parse_decision('Claro: {"done": true, "say": "ok"} fin'), {'done': True, 'say': 'ok'})
        for bad in ('sin json', '{roto', '[1]'):
            with self.assertRaises(ValueError): parse_decision(bad)
        self.assertTrue(valid_expected({'name': 'Guardado', 'present': True}))
        self.assertFalse(valid_expected({'name': 'x', 'present': 'yes'})); self.assertFalse(valid_expected({'value': 'x'}))
        obs = {'image_bounds': {'x': 0, 'y': 0, 'width': 800, 'height': 600}, 'image_width': 400, 'image_height': 300}
        self.assertEqual(region_expected(BUTTON, obs), {'region_changed': [16, 26, 74, 49]})


class ActComputerUiTests(_ComputerFixture):
    """Real Axx.html over the real HTTP endpoints; UIA, capture and the input call are patched in-process as above."""

    def test_cursor_presence_and_indicator_follow_executed_steps(self):
        import functools, http.server
        from playwright.sync_api import sync_playwright
        from backend.tests.test_acts_inference import _Server
        from backend.tests.test_acts_ui import ROOT, open_axx, serve
        (Path(self.temp.name) / 'ui').mkdir()
        srv = _Server(Path(self.temp.name) / 'ui', [])
        try:
            handler = srv.server.RequestHandlerClass
            handler.computer_use, handler.connect, handler.chats = self.computer, self.connect, self.chats
            srv.rt.flags.set_flag('agent_profiles_v1', True, reason='ui')
            spec = act_spec('act-dev', 'Dev', 'Helix', 'axx-connect', 'gpt-6.1-terra'); spec['collaboration'] = {'mention': 'Dev'}
            srv.rt.registry.create_profile(spec)
            srv.rt.registry.grant_permission(grant_id='g-ui', agent_id='act-dev', tool_id='axx.computer', resource_pattern='*',
                                             operation_kinds=['uia'], approval_mode='auto_safe', expires_at_ms=None, granted_by='owner')
            srv.rt.act_computer = ActComputerRunner(srv.rt, infer=self.fake_infer, resolve=lambda aid: {'act_id': aid, 'name': 'Dev', 'model': 'm'},
                                                    computer_use=self.computer, connect=self.connect, chats=self.chats)
            self.authorize()
            self.decisions = [{'say': 'Pulso Guardar', 'action': {'action': 'click', 'control_id': 'btn-save'}, 'expected': {'name': 'Guardado'}},
                              {'say': 'Documento guardado', 'done': True}]
            observed, reads = self.observed, iter([self.observed] + [{'controls': [{'name': 'Guardado'}]}] * 50)
            shot = {'id': 'obs-1', 'observed': observed, 'hash': 'frame', 'jpeg': b'x', 'width': 400, 'height': 300,
                    'image_bounds': {'x': 0, 'y': 0, 'width': 400, 'height': 300}}
            output = {'observation_id': 'obs-1', 'title': 'Editor', 'controls': observed['controls'], 'focused_control_id': None,
                      'image_width': 400, 'image_height': 300, 'image_bounds': shot['image_bounds']}
            web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))
            with patch.object(self.computer, '_observe', side_effect=lambda g, e, **k: (dict(shot, at=time.monotonic()), output)), \
                 patch.object(cu.uia, 'read_window_content', side_effect=lambda *a, **k: next(reads)), \
                 patch.object(cu, 'execute_action', side_effect=lambda payload, control: self.dispatched.append(payload) or {'success': True}), \
                 sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = open_axx(browser, srv, web)
                    page.wait_for_function('Axx.chatWorkspace?.ready === true', timeout=30000)
                    page.evaluate('(id)=>Axx.chatWorkspace.select(id)', self.chat['id'])
                    page.evaluate('Axx.acts.load()')
                    result = page.evaluate("""(async()=>{const act=Axx.acts.acts.find(a=>a.agent_id==='act-dev'),seen=[],lents=[];
                        const t=setInterval(()=>{const c=document.querySelector('.axx-act-cursor');const lent=Axx.inputMaterialOverride?.();lents.push(lent?.key||'');
                          if(c&&!c.hidden)seen.push({transform:c.style.transform,label:c.textContent,state:c.dataset.state,lent:lent?.key||''});},40);
                        const r=await Axx.acts.computerTask(act,'Guarda el documento');clearInterval(t);
                        const c=document.querySelector('.axx-act-cursor');if(c&&!c.hidden)seen.push({transform:c.style.transform,label:c.textContent,state:c.dataset.state,lent:''});
                        return {state:r.state,steps:r.steps.length,seen,lents,lentAfter:!!Axx.inputMaterialOverride,
                                presence:document.querySelector('.axx-act-presence')?.textContent};})()""")
                finally:
                    browser.close()
            web.shutdown(); web.server_close()
            self.assertEqual((result['state'], result['steps']), ('completed', 1), result)
            self.assertTrue(result['seen'], result)
            last = result['seen'][-1]
            self.assertEqual(last['transform'], 'translate(90px, 75px)')  # the executed control's centre, DPR 1
            self.assertIn('Dev · clic en «Guardar»', last['label'])
            self.assertEqual(last['state'], 'succeeded')
            self.assertTrue(any(k.startswith('act:') for k in result['lents']), 'the indicator wore the Act material')
            self.assertFalse(result['lentAfter'])
            self.assertIn('1 gesto(s) verificado(s) por AXX', result['presence'])
            self.assertEqual(len(self.dispatched), 1)
        finally:
            srv.close()


@unittest.skipUnless(os.environ.get('AXX_REAL_COMPUTER') == '1' and sys.platform == 'win32',
                     'Native: set AXX_REAL_COMPUTER=1 on Windows; it moves the real mouse in a temporary Win32 window.')
class ActComputerNativeTests(unittest.TestCase):
    """Real Win32 window, real UI Automation, real capture and real SendInput through the executor; only the model is scripted."""

    def test_act_presses_a_real_button(self):
        from backend.actions import windows_automation as uia
        from backend.mobile.control import RemoteControl
        app = subprocess.Popen([sys.executable, '-I', str(Path(__file__).with_name('win32_button_fixture.py'))])
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                rows = [w for w in uia.list_windows() if w['pid'] == app.pid and 'AXX Act native fixture' in (w.get('title') or '')]
                if rows: break
                time.sleep(.2)
            self.assertTrue(rows, 'Tk window did not appear')
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                executor = ActionExecutor(root / 'state.db', root / 'artifacts'); commands = CommandService(executor)
                computer = cu.ComputerUse(commands); executor.computer_use = computer
                executor.input_control = control = RemoteControl(None)  # the server's input owner (mobile.control), without a phone lease
                # The owner only acts while the desktop keeps its cursor indicator material fresh (<5 s), as remote-control.js does.
                import base64
                look = {'key': 'act-native-test', 'reduced': False, 'size': 48, 'intensity': .9, 'glow': .12}
                control.material({**look, 'table': base64.b64encode(bytes([40, 120, 230, 255]) * (128 * 128)).decode()})
                beating = threading.Event()
                def heartbeat():
                    while not beating.wait(1): control.material(look)
                threading.Thread(target=heartbeat, daemon=True).start()
                connect, chats = ConnectService(commands, None), ChatStore(root / 'state.db')
                rt = EvolutionHttpRuntime(db_path=root / 'state.db', storage_dir=root / 'evo', chat_store=chats,
                                          action_executor=executor, command_service=commands)
                try:
                    rt.flags.set_flag('agent_profiles_v1', True, reason='native')
                    rt.registry.create_profile(act_spec('act-dev', 'Dev', 'Helix', 'axx-connect', 'gpt-6.1-terra'))
                    rt.registry.grant_permission(grant_id='g-pc-' + str(time.monotonic_ns()), agent_id='act-dev', tool_id='axx.computer', resource_pattern='*', operation_kinds=['uia'],
                                                 approval_mode='auto_safe', expires_at_ms=None, granted_by='owner')
                    chat = chats.get(chats.mutate('create', {'title': 'Nativo'})['id'])
                    computer.begin(chat['connect_id'], rows[0]['window_id'], app.pid, image_authorized=True, allow_input=True)
                    seen = []
                    def infer(act, envelope, conversation_id, cancel):
                        prompt = envelope['messages'][-1]['content']; seen.append(prompt)
                        button = next((line.split(' | ')[0] for line in prompt.splitlines() if line.endswith(' | Saludar')), None)
                        if button is None: return {'ok': True, 'message': {'content': json.dumps({'say': 'Sin botón', 'done': True})}}, {'model_verified': True}
                        decision = ({'say': 'Pulso Saludar', 'action': {'action': 'click', 'control_id': button}, 'expected': {'name': 'Hola desde el Act'}}
                                    if len(seen) == 1 else {'say': 'Saludo visible', 'done': True})
                        return {'ok': True, 'message': {'content': json.dumps(decision)}}, {'model_verified': True}
                    runner = ActComputerRunner(rt, infer=infer, resolve=lambda aid: {'act_id': aid, 'name': 'Dev', 'model': 'm'},
                                               computer_use=computer, connect=connect, chats=chats)
                    run = runner.start({'act_id': 'act-dev', 'conversation_id': chat['id'], 'instruction': 'Pulsa Saludar', 'max_steps': 3})
                    deadline = time.monotonic() + 60
                    while runner.get(run['run_id'])['state'] == 'running' and time.monotonic() < deadline: time.sleep(.1)
                    run = runner.get(run['run_id'])
                    self.assertEqual(run['state'], 'completed', (run, seen[:1]))
                    self.assertTrue(run['steps'], seen[:1])
                    self.assertEqual(run['steps'][0]['verification'], 'computer_expected_control')
                    self.assertIn('Hola desde el Act', seen[-1])  # the label really changed in the live window
                finally:
                    beating.set(); computer.close(); connect.close(); rt.close(); commands.close(); executor.close(); chats.close()
                    getattr(control, 'close', lambda: None)()
        finally:
            app.kill(); app.wait(5)


if __name__ == '__main__':
    unittest.main()
