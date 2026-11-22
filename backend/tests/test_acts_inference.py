"""Acts (Evolution 3.1): profile persistence, per-Act inference over the existing chat endpoint, revocation.

The HTTP tests drive the real AXX handler, router and HTTP transport. The loopback responder is a controlled
OpenAI-compatible endpoint (it echoes the model it was sent); the Ollama test uses real local models and is
skipped, never passed, when Ollama is not reachable.
"""
from __future__ import annotations

import http.server
import os
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request

from backend.actions.executor import ActionExecutor
from backend.agents.act_inference import ActInferenceError, ActInferenceService, persona_prompt
from backend.agents.http_api import EvolutionHttpRuntime
from backend.agents.profiles import AgentProfileValidationError, CANONICAL_AXX_FORMS
from backend.agents.registry import AgentRegistry
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.inference.adapter import InferenceAdapter
from backend.magic_pen import MagicPenService
from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.sync.identity_sync import IdentityStore
from backend.tests.test_evolution3_full_functional_audit import _HttpTestClient


def act_spec(agent_id, name, form, provider, model, **extra):
    spec = {
        'schema_version': '1.0', 'agent_id': agent_id, 'revision': 1, 'name': name, 'role': extra.pop('role', 'Programador'),
        'instructions': extra.pop('instructions', ''), 'enabled': True,
        'appearance': {'form_id': CANONICAL_AXX_FORMS.index(form), 'palette_id': 2, 'material_preset': 'optical_glass'},
        'intelligence': {'route': 'manual', 'fallback': 'none', 'provider_profile_ref': provider, 'model_id': model},
        'workspace': {'runtime': 'none', 'foreground_policy': 'deny'},
        'permissions': {'tool_grant_refs': [], 'delegation_enabled': False},
        'limits': {'max_concurrent_jobs': 1, 'max_retries': 0},
        'memory_scope': 'agent',
    }
    spec.update(extra)
    return spec


class ActProfileTests(unittest.TestCase):
    def test_act_identity_appearance_personality_survive_restart_and_never_grant_tools(self):  # ACT-01..04, ACT-06
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'state.db'
            reg = AgentRegistry(db)
            created = reg.create_profile(act_spec(
                'act-dev', 'Dev', 'Helix', 'loop-a', 'model-alpha', instructions='Conserva los contratos públicos.',
                personality={'formality': 'formal', 'concision': 'brief', 'review_style': 'strict', 'default_language': 'es-DO',
                             'coding_preferences': 'Python tipado'},
                autonomy={'mode': 'assisted'}, collaboration={'mention': 'Dev', 'review_required': True}))
            self.assertEqual(created['appearance']['form_name'], 'Helix')
            self.assertEqual(created['appearance']['palette_name'], 'Ocean')
            self.assertEqual(created['personality']['review_style'], 'strict')
            reg.close()
            reopened = AgentRegistry(db).get_profile('act-dev')  # restart: new connection, same file
            self.assertEqual(reopened['personality'], created['personality'])
            self.assertEqual(reopened['autonomy'], {'mode': 'assisted'})
            self.assertEqual(reopened['collaboration']['mention'], 'Dev')
            self.assertEqual(AgentRegistry(db).list_permissions('act-dev'), [])
            prompt = persona_prompt(reopened)
            self.assertIn('Conserva los contratos públicos.', prompt)
            self.assertIn('Usa un tono formal.', prompt)
            self.assertIn('Idioma por defecto: es-DO.', prompt)
            self.assertIn('no conceden permisos', prompt)

    def test_update_keeps_sections_and_old_profiles_stay_v1_shaped(self):
        reg = AgentRegistry()
        v1 = reg.create_profile(act_spec('act-old', 'Old', 'Core', 'loop-a', 'model-alpha'))
        self.assertNotIn('personality', v1)  # AgentProfile v1 output unchanged when sections are absent
        updated = reg.update_profile('act-old', {'personality': {'examples': 'many'}}, expected_revision=1)
        self.assertEqual(updated['personality'], {'examples': 'many'})
        for bad in ({'personality': {'formality': 'rude'}}, {'personality': {'grant': 'all'}},
                    {'autonomy': {'mode': 'root'}}, {'collaboration': {'mention': 'no spaces'}}):
            with self.assertRaises(AgentProfileValidationError):
                reg.update_profile('act-old', bad, expected_revision=2)

    def test_resolution_rejects_disabled_stale_unset_and_wrong_transport(self):
        reg = AgentRegistry()
        acts = ActInferenceService(reg)
        reg.create_profile(act_spec('act-a', 'A', 'Core', 'loop-a', 'model-alpha'))
        reg.create_profile(act_spec('act-gpt', 'G', 'Prism', 'axx-connect', 'gpt-6.1-terra'))
        unset = act_spec('act-unset', 'U', 'Core', 'loop-a', '')
        reg.create_profile(unset)
        self.assertEqual(acts.resolve('act-a', transport='router')['model'], 'model-alpha')
        cases = [('act-missing', 'router', None, 'ACT_NOT_FOUND'), ('act-a', 'router', 7, 'ACT_STALE_REVISION'),
                 ('act-unset', 'router', None, 'ACT_MODEL_UNSET'), ('act-gpt', 'router', None, 'ACT_TRANSPORT_MISMATCH'),
                 ('act-a', 'connect', None, 'ACT_TRANSPORT_MISMATCH')]
        for act_id, transport, rev, code in cases:
            with self.assertRaises(ActInferenceError) as ctx:
                acts.resolve(act_id, transport=transport, expected_revision=rev)
            self.assertEqual(ctx.exception.code, code)
        reg.disable_profile('act-a')
        with self.assertRaises(ActInferenceError) as ctx:
            acts.resolve('act-a', transport='router')
        self.assertEqual(ctx.exception.code, 'ACT_DISABLED')

    def test_connect_body_isolates_thread_and_keeps_text_as_data(self):
        reg = AgentRegistry()
        reg.create_profile(act_spec('act-gpt', 'G', 'Prism', 'axx-connect', 'gpt-6.1-terra', instructions='Revisa la UI.'))
        acts = ActInferenceService(reg)
        act = acts.resolve('act-gpt', transport='connect')
        body = acts.apply_to_connect({'message': 'hola', 'act_id': 'act-gpt', 'model': 'gpt-6.1-sol', 'conversation_id': 'c1'}, act)
        self.assertEqual(body['model'], 'gpt-6.1-terra')
        self.assertEqual(body['act_thread'], 'act-gpt')
        self.assertNotIn('act_id', body)
        self.assertTrue(body['message'].endswith('\n\nhola'))
        self.assertIn('Revisa la UI.', body['message'])


class _EchoModel(http.server.BaseHTTPRequestHandler):
    """Controlled OpenAI-compatible responder: reports the model it actually received."""
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).seen.append(body)
        persona = next((m['content'] for m in body['messages'] if m['role'] == 'system' and 'un Act de AXX' in m['content']), '')
        reply = json.dumps({'id': 'x', 'model': body['model'], 'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
            'role': 'assistant', 'content': f"ACK {body['model']} persona={persona.split('»')[0][-12:]}"}}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


def provider(name, base_url, model):
    return {'name': name, 'base_url': base_url, 'model': model, 'api_key_env': 'AXX_TEST_NO_KEY', 'enabled': True,
            'free_confirmed': True, 'allow_sensitive': True, 'daily_attempt_limit': 50, 'route_kind': 'direct',
            'capabilities': ['text', 'tools']}


class _Server:
    def __init__(self, root: Path, providers: list):
        state = root / 'state.db'
        self.chats, self.identity = ChatStore(state), IdentityStore(db_path=state)
        self.executor = ActionExecutor(db_path=state, workspace_root=root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.magic_pen = MagicPenService(self.executor.workspace_root, None)
        self.adapter = InferenceAdapter({'allow_paid': False, 'max_attempts': 1, 'timeout_seconds': 60,
                                         'providers': providers}, root / 'router.db')
        handler = type('ActsHandler', (AxxBridgeHandler,), {'chats': self.chats, 'identity': self.identity,
                       'executor': self.executor, 'commands': self.commands, 'magic_pen': self.magic_pen,
                       'adapter': self.adapter})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.rt = self.server.evolution_runtime = EvolutionHttpRuntime(
            db_path=state, storage_dir=root / 'evolution3', chat_store=self.chats, action_executor=self.executor,
            command_service=self.commands, magic_pen=self.magic_pen, identity_store=self.identity)
        threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True).start()
        self.api = _HttpTestClient(self.server.server_port, self.server.host_token)

    def close(self):
        self.rt.close()
        self.server.shutdown()
        self.server.server_close()
        for svc in (self.magic_pen, self.commands, self.chats, self.identity, self.executor, self.adapter):
            getattr(svc, 'close', lambda: None)()


class ActChatHttpTests(unittest.TestCase):
    def setUp(self):
        _EchoModel.seen = []
        self.echo = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _EchoModel)
        threading.Thread(target=self.echo.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{self.echo.server_port}/v1'
        self.tmp = tempfile.TemporaryDirectory()
        self.srv = _Server(Path(self.tmp.name), [provider('loop-a', base, 'model-alpha'), provider('loop-b', base, 'model-beta')])

    def tearDown(self):
        self.srv.close()
        self.echo.shutdown()
        self.echo.server_close()
        self.tmp.cleanup()

    def chat(self, act_id, **extra):
        return self.srv.api.request('POST', '/axx-api/chat', {
            'messages': [{'role': 'system', 'content': 'Política AXX'}, {'role': 'user', 'content': 'Hola'}],
            'model': 'whatever-the-ui-had', 'provider_name': 'loop-b', 'request_id': f'req-{act_id}-{len(_EchoModel.seen)}',
            'conversation_id': 'conv-acts-1', 'act_id': act_id, **extra})

    def test_two_acts_use_their_own_models_through_the_existing_chat_endpoint(self):  # ACT-05, ACT-09, ACT-12 (controlled)
        api = self.srv.api
        self.assertEqual(self.chat('act-dev')[0], 403)  # agent_profiles_v1 starts disabled
        self.srv.rt.flags.set_flag('agent_profiles_v1', True, reason='acts test')
        for spec in (act_spec('act-dev', 'Dev', 'Helix', 'loop-a', 'model-alpha'),
                     act_spec('act-qa', 'QA', 'Core', 'loop-b', 'model-beta', role='QA')):
            self.assertEqual(api.request('POST', '/axx-api/agents/v1/profiles', spec)[0], 200)
        code, dev = self.chat('act-dev')
        self.assertEqual(code, 200, dev)
        self.assertEqual(dev['axx_act']['served_model'], 'model-alpha')
        self.assertEqual(dev['axx_act']['responder_model'], 'model-alpha')
        self.assertTrue(dev['axx_act']['model_verified'])
        code, qa = self.chat('act-qa')
        self.assertEqual(code, 200, qa)
        self.assertEqual(qa['axx_router']['provider'], 'loop-b')
        self.assertEqual([b['model'] for b in _EchoModel.seen], ['model-alpha', 'model-beta'])
        roles = [m['role'] for m in _EchoModel.seen[0]['messages']]
        self.assertEqual(roles, ['system', 'system', 'user'])  # AXX policy first, Act persona second
        self.assertIn('«Dev»', _EchoModel.seen[0]['messages'][1]['content'])
        self.assertIn('«QA»', _EchoModel.seen[1]['messages'][1]['content'])
        events = api.request('GET', '/axx-api/agents/v1/events/sse?conversation_id=conv-acts-1')[1]
        types = [(e['agent_id'], e['type']) for e in events.get('events', [])]
        self.assertIn(('act-dev', 'run.completed'), types)
        self.assertIn(('act-qa', 'run.started'), types)

    def test_model_change_disable_and_revocation_take_effect_on_the_next_turn(self):  # ACT-10, ACT-14
        api, rt = self.srv.api, self.srv.rt
        rt.flags.set_flag('agent_profiles_v1', True, reason='acts test')
        api.request('POST', '/axx-api/agents/v1/profiles', act_spec('act-dev', 'Dev', 'Helix', 'loop-a', 'model-alpha'))
        code, upd = api.request('POST', '/axx-api/agents/v1/profiles/update', {
            'agent_id': 'act-dev', 'expected_revision': 1,
            'patch': {'intelligence': {'provider_profile_ref': 'loop-b', 'model_id': 'model-beta'}}})
        self.assertEqual(code, 200, upd)
        self.assertEqual(self.chat('act-dev', act_revision=1)[0], 409)  # stale editor never sends the old model
        code, turn = self.chat('act-dev', act_revision=2)
        self.assertEqual((code, turn['axx_act']['served_model']), (200, 'model-beta'))
        grant = {'agent_id': 'act-dev', 'grant_id': 'g-cmd', 'tool_id': 'axx.commands', 'operation_kinds': ['read'],
                 'approval_mode': 'ask'}
        self.assertEqual(api.request('POST', '/axx-api/agents/v1/profiles/permissions/grant', grant)[0], 200)
        self.assertTrue(rt.acts.resolve('act-dev', transport='router')['tools_allowed'])
        self.assertEqual(api.request('POST', '/axx-api/agents/v1/profiles/permissions/revoke',
                                     {'agent_id': 'act-dev', 'grant_id': 'g-cmd'})[1], {'revoked': True})
        self.assertFalse(rt.acts.resolve('act-dev', transport='router')['tools_allowed'])
        api.request('POST', '/axx-api/agents/v1/profiles/disable', {'agent_id': 'act-dev'})
        code, body = self.chat('act-dev')
        self.assertEqual((code, body['error']['code']), (403, 'ACT_DISABLED'))
        self.assertEqual(len(_EchoModel.seen), 1)  # nothing was sent for the rejected turns

    def test_team_and_preview_routes(self):  # ACT-11
        api, rt = self.srv.api, self.srv.rt
        rt.flags.set_flag('agent_profiles_v1', True, reason='acts test')
        for spec in (act_spec('act-dev', 'Dev', 'Helix', 'loop-a', 'model-alpha'),
                     act_spec('act-qa', 'QA', 'Core', 'loop-b', 'model-beta')):
            api.request('POST', '/axx-api/agents/v1/profiles', spec)
        code, team = api.request('POST', '/axx-api/agents/v1/teams', {'team_id': 'team-1', 'title': 'Code', 'members': [
            {'agent_id': 'act-dev', 'role': 'lead'}, {'agent_id': 'act-qa', 'role': 'reviewer'}]})
        self.assertEqual(code, 200, team)
        self.assertEqual(api.request('GET', '/axx-api/agents/v1/teams?team_id=team-1')[1]['team']['members'][0]['agent_id'], 'act-dev')
        self.assertEqual(rt.registry.list_permissions('act-qa'), [])  # membership grants nothing
        code, preview = api.request('POST', '/axx-api/agents/v1/profiles/preview', {'agent_id': 'act-dev'})
        self.assertEqual((code, preview['transport']), (200, 'router'))
        self.assertIn('«Dev»', preview['persona'])
        self.assertEqual(api.request('GET', '/axx-api/agents/v1/catalog')[1]['form_count'], 24)

    def test_sse_stream_returns_axx_act_and_revoked_grant_omits_tool_catalog(self):  # ACT-14 HTTP dispatch verification
        api, rt = self.srv.api, self.srv.rt
        rt.flags.set_flag('agent_profiles_v1', True, reason='acts sse test')
        api.request('POST', '/axx-api/agents/v1/profiles', act_spec('act-sse', 'SSE', 'Flow', 'loop-a', 'model-alpha'))
        # Stream=True must return axx_act verification receipt
        raw_req = urllib.request.Request(
            f'http://127.0.0.1:{self.srv.server.server_port}/axx-api/chat',
            method='POST',
            headers={
                'Authorization': f'Bearer {self.srv.server.host_token}',
                'Content-Type': 'application/json',
            },
            data=json.dumps({
                'messages': [{'role': 'user', 'content': 'Stream test'}],
                'request_id': 'req-sse-1', 'conversation_id': 'conv-sse-1',
                'act_id': 'act-sse', 'stream': True,
            }).encode('utf-8'),
        )
        with urllib.request.urlopen(raw_req, timeout=10) as resp:
            raw_sse = resp.read().decode('utf-8')
        first_data = json.loads(next(line[6:] for line in raw_sse.splitlines() if line.startswith('data: ') and line != 'data: [DONE]'))
        self.assertTrue(first_data['axx_act']['model_verified'])
        self.assertEqual(first_data['axx_act']['responder_model'], 'model-alpha')

        # Grant axx.commands then revoke -> next turn resolves tools_allowed=False and receives zero tools in upstream request
        grant = {'agent_id': 'act-sse', 'grant_id': 'g-cmd', 'tool_id': 'axx.commands', 'operation_kinds': ['command'], 'approval_mode': 'ask'}
        self.assertEqual(api.request('POST', '/axx-api/agents/v1/profiles/permissions/grant', grant)[0], 200)
        self.assertEqual(api.request('POST', '/axx-api/agents/v1/profiles/permissions/revoke', {'agent_id': 'act-sse', 'grant_id': 'g-cmd'})[1], {'revoked': True})
        code, res = self.chat('act-sse')
        self.assertEqual(code, 200, res)
        self.assertNotIn('tools', _EchoModel.seen[-1])


def _ollama_models():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2) as resp:
            return {m['name'] for m in json.load(resp).get('models', [])}
    except OSError:
        return set()


@unittest.skipUnless({'llama3.2:1b', 'qwen2.5:7b-instruct'} <= _ollama_models(), 'Ollama with llama3.2:1b and qwen2.5:7b-instruct not reachable')
class ActRealOllamaTests(unittest.TestCase):
    def test_two_acts_answer_from_two_real_local_models(self):  # ACT-09 / ACT-12 with real inference
        base = 'http://127.0.0.1:11434/v1'
        for model in ('llama3.2:1b', 'qwen2.5:7b-instruct'):  # cold-load only, outside AXX; not counted as evidence
            urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/generate', method='POST',
                                   data=json.dumps({'model': model, 'keep_alive': '10m'}).encode()), timeout=300).read()
        with tempfile.TemporaryDirectory() as tmp:
            srv = _Server(Path(tmp), [provider('ollama-llama', base, 'llama3.2:1b'), provider('ollama-qwen', base, 'qwen2.5:7b-instruct')])
            try:
                srv.rt.flags.set_flag('agent_profiles_v1', True, reason='real acts test')
                for spec in (act_spec('act-dev', 'Dev', 'Helix', 'ollama-llama', 'llama3.2:1b'),
                             act_spec('act-qa', 'QA', 'Core', 'ollama-qwen', 'qwen2.5:7b-instruct', role='QA')):
                    srv.api.request('POST', '/axx-api/agents/v1/profiles', spec)
                for act_id, model in (('act-dev', 'llama3.2:1b'), ('act-qa', 'qwen2.5:7b-instruct')):
                    code, body = srv.api.request('POST', '/axx-api/chat', {
                        'messages': [{'role': 'user', 'content': '¿Cuál es tu nombre de Act? Responde en una línea.'}],
                        'request_id': 'real-' + act_id, 'conversation_id': 'conv-real', 'act_id': act_id, 'max_tokens': 64})
                    self.assertEqual(code, 200, body)
                    self.assertEqual(body['axx_act']['responder_model'], model)
                    self.assertTrue(body['axx_act']['model_verified'])
                    self.assertTrue(body['choices'][0]['message']['content'].strip())
                    print(f"\n[ACT-REAL] {act_id} via {model}: {body['choices'][0]['message']['content'].strip()[:160]}")
            finally:
                srv.close()



@unittest.skipUnless(os.environ.get('AXX_REAL_CODEX') == '1', 'Opt-in: set AXX_REAL_CODEX=1 to use the signed-in Codex/ChatGPT account')
class ActRealCodexTests(unittest.TestCase):
    def test_act_turn_runs_on_its_own_codex_model_and_thread_without_touching_the_global_model(self):  # ACT-05/07/10 on axx-connect
        from backend.connect.provider import TERMINAL, CodexProvider
        from backend.connect.service import ConnectService
        from backend.memory.procedural_memory import ProceduralMemory
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            srv = _Server(Path(tmp), [])
            memory = ProceduralMemory(Path(tmp) / 'state.db')
            connect = ConnectService(srv.commands, memory)
            codex = CodexProvider(srv.commands, Path(tmp) / 'state.db', Path(tmp), dispatcher=connect.dispatch)
            srv.server.RequestHandlerClass.connect, srv.server.RequestHandlerClass.provider = connect, codex
            try:
                status = srv.api.request('GET', '/axx-api/connect/status')[1]
                info = codex.status()
                self.assertTrue(info['authenticated'], info.get('diagnostic'))
                models = info['models']
                global_model = codex.selected_model
                act_model = next((m for m in models if m != global_model), global_model)
                srv.rt.flags.set_flag('agent_profiles_v1', True, reason='real codex act test')
                srv.api.request('POST', '/axx-api/agents/v1/profiles',
                                act_spec('act-dev', 'Dev', 'Helix', 'axx-connect', act_model, instructions='Firma como Dev.'))
                code, started = srv.api.request('POST', '/axx-api/connect/start', {
                    'act_id': 'act-dev', 'message': 'Responde en una línea: ¿cuál es tu nombre de Act?',
                    'conversation_id': 'conv-codex', 'request_id': 'codex-act-1', 'purpose': 'chat'})
                self.assertEqual(code, 200, started)
                deadline = time.monotonic() + 240
                while True:
                    run = srv.api.request('GET', '/axx-api/connect/run?request_id=codex-act-1')[1]
                    if run.get('state') in TERMINAL or time.monotonic() > deadline:
                        break
                    time.sleep(1)
                self.assertEqual(run.get('state'), 'completed', run.get('error'))
                self.assertEqual(run.get('model'), act_model)
                self.assertEqual(run.get('act_thread'), 'act-dev')
                self.assertEqual(codex.selected_model, global_model)  # the AXX-wide model choice is untouched
                print(f"\n[ACT-CODEX-REAL] {act_model} (global {global_model}, status={status.get('state')}): {str(run.get('response'))[:200]}")
            finally:
                codex.close(); connect.close(); memory.close(); srv.close()


if __name__ == '__main__':
    unittest.main()
